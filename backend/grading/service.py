'''Auditable three-stage long-answer grading service.'''

from __future__ import annotations

import json
import math
import time
from pathlib import Path


from backend.chat.llm import LLMClient, OpenAICompatibleLLM
from backend.grading.guardrails import evaluate_reliability
from backend.grading.knowledge import resolve_grading_context
from backend.grading.models import (
    DIMENSION_LIMITS,
    ERROR_TYPES,
    DimensionScores,
    EvidenceItem,
    GradeRequest,
    GradeResponse,
    GradingAttempts,
    GradingAudit,
)
from backend.grading.prompts import (
    PROMPT_VERSION,
    analysis_messages,
    repair_messages,
    review_messages,
    scoring_messages,
)
from backend.learning.database import connection_scope, init_database


class InvalidGradingOutputError(RuntimeError):
    pass


class GradingService:
    def __init__(self, llm: LLMClient | None = None, database_path: str | Path | None = None) -> None:
        self.llm = llm or OpenAICompatibleLLM()
        self.database_path = database_path

    def grade(self, request: GradeRequest) -> GradeResponse:
        context = resolve_grading_context(
            question_id=request.question_id,
            question=request.question,
            reference_answer=request.reference_answer,
            knowledge_points=request.knowledge_points,
        )
        started_at = time.perf_counter()
        analysis, analysis_attempts = self._run_json('analysis', analysis_messages(context, request.student_answer), self._validate_analysis)
        scoring, scoring_attempts = self._run_json('scoring', scoring_messages(context, request.student_answer, analysis), self._validate_scoring)
        review, review_attempts = self._run_json('review', review_messages(context, request.student_answer, scoring), self._validate_review)
        scores = DimensionScores(**review['dimension_scores'])
        errors = review['error_types']
        reliability = evaluate_reliability(
            dimension_scores=scores.model_dump(),
            error_types=errors,
            evidence=review['evidence'],
        )
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        attempts = GradingAttempts(analysis=analysis_attempts, scoring=scoring_attempts, review=review_attempts)
        result_id = self._persist(context, request.student_answer, scores, errors, review['evidence'], analysis, scoring, review, attempts, latency_ms, reliability)
        return GradeResponse(
            result_id=result_id,
            question_id=context.question_id,
            knowledge_points=context.knowledge_points,
            total_score=scores.total(),
            dimension_scores=scores,
            error_types=errors,
            evidence=[EvidenceItem(**item) for item in review['evidence']],
            feedback=review['feedback'],
            attempts=attempts,
            audit=GradingAudit(
                prompt_version=PROMPT_VERSION,
                llm_provider=self.llm.__class__.__name__,
                llm_model=getattr(self.llm, 'model', ''),
                latency_ms=latency_ms,
                review_notes=review['review_notes'],
            ),
            needs_manual_review=reliability.needs_manual_review,
            review_reasons=reliability.reasons,
        )

    def _run_json(self, stage: str, messages: list[dict[str, str]], validator) -> tuple[dict, int]:
        raw = self.llm.generate(messages)
        for attempt in (1, 2):
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError('JSON root must be an object')
                self._normalize_error_types(payload)
                validator(payload)
                return payload, attempt
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                if attempt == 2:
                    raise InvalidGradingOutputError(f'{stage} output failed validation after one repair: {exc}') from exc
                raw = self.llm.generate(repair_messages(stage, raw, str(exc)))
        raise AssertionError('unreachable')

    @staticmethod
    def _validate_analysis(payload: dict) -> None:
        for key in ('key_steps', 'missing_steps', 'error_candidates'):
            if not isinstance(payload.get(key), list) or not all(isinstance(value, str) for value in payload[key]):
                raise ValueError(f'{key} must be a string list')

    @staticmethod
    def _validate_scoring(payload: dict) -> None:
        GradingService._validate_rubric(payload)
        evidence = payload.get('evidence')
        if not isinstance(evidence, list):
            raise ValueError('evidence must be a list')
        for item in evidence:
            EvidenceItem(**item)

    @staticmethod
    def _validate_review(payload: dict) -> None:
        if payload.get('approved') is not True:
            raise ValueError('review must explicitly approve a corrected result')
        GradingService._validate_rubric(payload)
        evidence = payload.get('evidence')
        if not isinstance(evidence, list):
            raise ValueError('evidence must be a list')
        for item in evidence:
            EvidenceItem(**item)
        if not isinstance(payload.get('review_notes'), str) or not payload['review_notes'].strip():
            raise ValueError('review_notes is required')

    @staticmethod
    def _normalize_error_types(payload: dict) -> None:
        errors = payload.get('error_types')
        if not isinstance(errors, list):
            return
        payload['error_types'] = list(dict.fromkeys(
            error for error in errors if isinstance(error, str) and error in ERROR_TYPES
        ))
    @staticmethod
    def _validate_rubric(payload: dict) -> None:
        scores = payload.get('dimension_scores')
        if not isinstance(scores, dict) or set(scores) != set(DIMENSION_LIMITS):
            raise ValueError('dimension_scores must contain exactly the five rubric dimensions')
        for dimension, maximum in DIMENSION_LIMITS.items():
            score = scores[dimension]
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
                raise ValueError(f'{dimension} must be finite')
            if not 0 <= score <= maximum:
                raise ValueError(f'{dimension} is outside its allowed range')
        errors = payload.get('error_types')
        if not isinstance(errors, list) or any(error not in ERROR_TYPES for error in errors):
            raise ValueError('error_types contains unsupported values')
        if len(errors) != len(set(errors)):
            raise ValueError('error_types must not contain duplicates')
        if not isinstance(payload.get('feedback'), str) or not payload['feedback'].strip():
            raise ValueError('feedback is required')

    def _persist(self, context, student_answer: str, scores: DimensionScores, errors: list[str], evidence: list[dict], analysis: dict, scoring: dict, review: dict, attempts: GradingAttempts, latency_ms: int, reliability) -> int:
        init_database(self.database_path)
        with connection_scope(self.database_path) as connection:
            cursor = connection.execute(
                '''INSERT INTO grading_results (
                    question_id, question_type, question, student_answer, reference_answer, knowledge_points,
                    grading_guides, dimension_scores, total_score, error_types, evidence, feedback,
                    analysis_json, scoring_json, review_json, prompt_version, llm_provider,
                    llm_model, latency_ms, analysis_attempts, scoring_attempts, review_attempts,
                    needs_manual_review, review_reasons, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
                (
                    context.question_id, context.question_type, context.question, student_answer, context.reference_answer,
                    json.dumps(context.knowledge_points, ensure_ascii=False),
                    json.dumps(context.grading_guides, ensure_ascii=False),
                    scores.model_dump_json(), scores.total(), json.dumps(errors), json.dumps(evidence, ensure_ascii=False), review['feedback'],
                    json.dumps(analysis, ensure_ascii=False), json.dumps(scoring, ensure_ascii=False), json.dumps(review, ensure_ascii=False),
                    PROMPT_VERSION, self.llm.__class__.__name__, getattr(self.llm, 'model', ''), latency_ms,
                    attempts.analysis, attempts.scoring, attempts.review,
                    int(reliability.needs_manual_review), json.dumps(reliability.reasons, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)
