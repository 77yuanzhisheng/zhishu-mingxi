'''Request and response models for grading.'''

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


DIMENSION_LIMITS = {
    'conclusion_correctness': 20.0,
    'key_reasoning_steps': 35.0,
    'logical_rigor': 25.0,
    'definition_theorem_usage': 10.0,
    'expression_notation': 10.0,
}
ERROR_TYPES = {
    'circular_reasoning',
    'jump_step',
    'theorem_misuse',
    'notation_error',
    'conclusion_error',
}


class GradeRequest(BaseModel):
    question_id: str | None = Field(default=None, max_length=100)
    question: str | None = Field(default=None, min_length=1)
    student_answer: str = Field(min_length=1, max_length=30000)
    reference_answer: str | None = Field(default=None, min_length=1)
    knowledge_points: list[str] = Field(default_factory=list, max_length=25)
    kp: str | None = Field(default=None, max_length=100)
    grading_mode: Literal['fast', 'strict'] = 'fast'
    tolerance: Literal['strict', 'standard', 'lenient'] = 'standard'

    @field_validator('knowledge_points')
    @classmethod
    def normalize_knowledge_points(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode='after')
    def require_source_or_complete_question(self):
        knowledge_points = list(self.knowledge_points)
        if self.kp and self.kp not in knowledge_points:
            knowledge_points.append(self.kp)
        self.knowledge_points = knowledge_points
        if not self.question_id and not (self.question and self.reference_answer):
            raise ValueError('provide question_id or both question and reference_answer')
        return self


class DimensionScores(BaseModel):
    conclusion_correctness: float = Field(ge=0, le=20)
    key_reasoning_steps: float = Field(ge=0, le=35)
    logical_rigor: float = Field(ge=0, le=25)
    definition_theorem_usage: float = Field(ge=0, le=10)
    expression_notation: float = Field(ge=0, le=10)

    def total(self) -> float:
        return round(sum(self.model_dump().values()), 2)


class EvidenceItem(BaseModel):
    dimension: str
    student_excerpt: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('dimension')
    @classmethod
    def dimension_must_be_rubric_dimension(cls, value: str) -> str:
        # 允许 ERROR_TYPES（如 jump_step / theorem_misuse）也作为合法 dimension：
        # LLM 偶尔会把错误类型写到 dimension 字段而不是 error_types 字段，
        # 这里宽容接受，避免重试整次批阅（重试也会同样失败）。
        if value in DIMENSION_LIMITS or value in ERROR_TYPES:
            return value
        raise ValueError(f'unknown rubric dimension: {value}')


class GradingAttempts(BaseModel):
    analysis: int = Field(ge=0, le=2)
    scoring: int = Field(ge=0, le=2)
    review: int = Field(ge=0, le=2)


class GradingAudit(BaseModel):
    prompt_version: str
    llm_provider: str
    llm_model: str
    latency_ms: int = Field(ge=0)
    review_notes: str
    grading_mode: Literal['fast', 'strict']
    tolerance: Literal['strict', 'standard', 'lenient']


class GradeResponse(BaseModel):
    result_id: int
    question_id: str | None
    knowledge_points: list[str]
    total_score: float = Field(ge=0, le=100)
    dimension_scores: DimensionScores
    error_types: list[str]
    evidence: list[EvidenceItem]
    feedback: str
    attempts: GradingAttempts
    audit: GradingAudit
    needs_manual_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

