"""Pydantic request/response and persisted-data models for learning APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UserRole = Literal["student", "teacher", "admin"]
MessageRole = Literal["user", "assistant", "system"]


class User(BaseModel):
    id: int
    name: str
    role: UserRole
    class_id: int | None = None


class Class(BaseModel):
    id: int
    name: str
    invite_code: str
    teacher_id: int


class Session(BaseModel):
    id: int
    user_id: int
    start_time: datetime


class Message(BaseModel):
    id: int
    session_id: int
    role: MessageRole
    content: str
    node_ids: list[str] = Field(default_factory=list)
    timestamp: datetime


class NodeMastery(BaseModel):
    user_id: int
    node_id: str
    level: int = Field(ge=0, le=4)
    correct_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    last_practice_time: datetime | None = None


class MasteryUpdateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"user_id": 1, "node_id": "pl_02_02", "correct": True}
        }
    )

    user_id: int = Field(gt=0, description="用户 ID")
    node_id: str = Field(min_length=1, max_length=100, description="知识图谱节点 ID")
    correct: bool = Field(description="本次答题是否正确")


class MasteryDetail(NodeMastery):
    accuracy: float = Field(ge=0.0, le=1.0)
    module: str


class MasteryUpdateResponse(BaseModel):
    message: str
    mastery: MasteryDetail


class RadarModule(BaseModel):
    module: str
    average_level: float = Field(ge=0.0, le=4.0)
    value: float = Field(ge=0.0, le=100.0, description="雷达图百分制数值")
    practiced_nodes: int = Field(ge=0)


class LearningReport(BaseModel):
    user_id: int
    node_mastery: list[MasteryDetail]
    weak_nodes: list[str]
    radar_data: list[RadarModule]
    summary: dict[str, int | float]


AnswerQuestionType = Literal["single", "fill", "calc", "proof", "exam"]


class AnswerEventCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 3,
                "question_id": "q001",
                "question_type": "single",
                "module": "命题逻辑",
                "node_id": "pl_02_02",
                "is_correct": True,
                "duration_ms": 18300,
                "answer_text": "C",
            }
        }
    )

    user_id: int = Field(gt=0)
    question_id: str = Field(min_length=1, max_length=200)
    question_type: AnswerQuestionType
    module: str = Field(min_length=1, max_length=100)
    node_id: str = Field(min_length=1, max_length=100)
    is_correct: bool | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    answer_text: str = Field(default="", max_length=10000)

    @field_validator("question_id", "module", "node_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class AnswerEvent(BaseModel):
    event_id: int
    user_id: int
    question_id: str
    question_type: AnswerQuestionType
    module: str
    node_id: str
    is_correct: bool | None
    duration_ms: int | None
    answer_text: str
    created_at: datetime


class AnswerEventsResponse(BaseModel):
    events: list[AnswerEvent]
    total: int = Field(ge=0)
    user_id: int


class AbilityModule(BaseModel):
    module: str
    score: float = Field(ge=0, le=100)
    mastery_ratio: float = Field(ge=0, le=1)
    accuracy: float = Field(ge=0, le=1)
    practice_score: float = Field(ge=0, le=1)


class AbilityRadarItem(BaseModel):
    module: str
    value: float = Field(ge=0, le=100)


class AbilityWeakNode(BaseModel):
    node_id: str
    module: str
    level: int = Field(ge=0, le=4)
    accuracy: float = Field(ge=0, le=1)
    reason: str


class AbilityTrendItem(BaseModel):
    date: str
    practice_count: int = Field(ge=0)
    graded_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    accuracy: float | None = Field(default=None, ge=0, le=1)


class AbilityProfile(BaseModel):
    user_id: int
    overall_score: float = Field(ge=0, le=100)
    level: Literal["优秀", "良好", "及格", "薄弱"]
    modules: list[AbilityModule]
    radar_data: list[AbilityRadarItem]
    weak_nodes: list[AbilityWeakNode]
    trend: list[AbilityTrendItem]
    calculation_note: str
