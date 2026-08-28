from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.exceptions import LLMUnavailableError
from backend.grading.models import GradeRequest
from backend.grading.prompts import repair_messages
from backend.grading.router import get_grading_service, router
from backend.grading.service import GradingService, InvalidGradingOutputError
from backend.learning.database import connection_scope


class ScriptedLLM:
    model = 'grading-test-model'

    def __init__(self, outputs: list[dict | str]) -> None:
        self.outputs = [json.dumps(output) if isinstance(output, dict) else output for output in outputs]
        self.messages: list[list[dict[str, str]]] = []

    def ensure_available(self) -> None:
        return None

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        return self.outputs.pop(0)


def valid_analysis() -> dict:
    return {
        'key_steps': ['State the required conclusion.'],
        'missing_steps': [],
        'error_candidates': [],
    }


def valid_scoring() -> dict:
    return {
        'dimension_scores': {
            'conclusion_correctness': 18,
            'key_reasoning_steps': 30,
            'logical_rigor': 20,
            'definition_theorem_usage': 9,
            'expression_notation': 8,
        },
        'error_types': ['jump_step'],
        'evidence': [
            {
                'dimension': 'key_reasoning_steps',
                'student_excerpt': 'therefore the claim holds',
                'reason': 'The supporting derivation is omitted.',
            }
        ],
        'feedback': 'The conclusion is plausible, but the derivation needs an explicit intermediate step.',
    }


def valid_review() -> dict:
    return {
        'approved': True,
        'dimension_scores': {
            'conclusion_correctness': 18,
            'key_reasoning_steps': 30,
            'logical_rigor': 20,
            'definition_theorem_usage': 9,
            'expression_notation': 8,
        },
        'error_types': ['jump_step'],
        'evidence': valid_scoring()['evidence'],
        'feedback': 'The conclusion is plausible, but the derivation needs an explicit intermediate step.',
        'review_notes': 'The proposed score is internally consistent with the cited missing step.',
    }


def test_grading_contract_is_available():
    request = GradeRequest(question_id='e2_proof_4', student_answer='Attempt.')
    assert request.question_id == 'e2_proof_4'


def test_grade_resolves_question_bank_guide_repairs_json_and_persists(tmp_path, monkeypatch):
    question = {
        'id': 'proof-1',
        'type': 'proof',
        'question': 'Prove the statement.',
        'answer': 'A complete proof.',
        'kp': 'semigroup',
        'grading_guide': {
            'focus': 'Use associativity explicitly.',
            'checks': ['Every equality is justified.'],
            'common_errors': ['Skipping associativity.'],
        },
    }
    monkeypatch.setattr(
        'backend.grading.knowledge.get_structured_questions',
        lambda limit: {'questions': [question]},
    )
    llm = ScriptedLLM(['not json', valid_analysis(), valid_scoring(), valid_review()])
    database_path = tmp_path / 'grading.db'

    result = GradingService(llm=llm, database_path=database_path).grade(
        GradeRequest(question_id='proof-1', student_answer='therefore the claim holds')
    )

    assert result.total_score == 85
    assert result.attempts.analysis == 2
    assert result.evidence[0].dimension == 'key_reasoning_steps'
    assert 'Use associativity explicitly.' in llm.messages[2][1]['content']
    with connection_scope(database_path) as connection:
        row = connection.execute('SELECT * FROM grading_results WHERE id = ?', (result.result_id,)).fetchone()
    assert row['question_id'] == 'proof-1'
    assert json.loads(row['dimension_scores'])['key_reasoning_steps'] == 30
    assert json.loads(row['review_json'])['approved'] is True


def test_grade_normalizes_unsupported_error_types_after_review(tmp_path):
    review = valid_review()
    review['error_types'] = ['calculation_error', 'jump_step']
    llm = ScriptedLLM([valid_analysis(), valid_scoring(), review])

    result = GradingService(llm=llm, database_path=tmp_path / 'grading.db').grade(
        GradeRequest(question='Question', reference_answer='Reference', student_answer='Answer')
    )

    assert result.error_types == ['jump_step']


def test_review_repair_prompt_requires_explicit_approval():
    prompt = repair_messages('review', '{dimension_scores: {}}', 'missing approved')

    assert 'approved:true' in prompt[1]['content']

def test_grade_rejects_invalid_model_scores_after_repair(tmp_path):
    invalid_scoring = valid_scoring()
    invalid_scoring['dimension_scores']['conclusion_correctness'] = 21
    llm = ScriptedLLM([valid_analysis(), invalid_scoring, invalid_scoring])

    with pytest.raises(InvalidGradingOutputError, match='scoring output failed validation'):
        GradingService(llm=llm, database_path=tmp_path / 'grading.db').grade(
            GradeRequest(question='Question', reference_answer='Reference', student_answer='Answer')
        )


def test_grade_endpoint_maps_unavailable_model_to_503(tmp_path):
    class UnavailableService:
        def grade(self, request: GradeRequest):
            raise LLMUnavailableError('model unavailable')

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_grading_service] = lambda: UnavailableService()
    client = TestClient(app)

    response = client.post(
        '/api/grading/grade',
        json={'question': 'Question', 'reference_answer': 'Reference', 'student_answer': 'Answer'},
    )

    assert response.status_code == 503
    assert response.json()['detail'] == 'model unavailable'

