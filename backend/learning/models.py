"""Pydantic request/response and persisted-data models for learning APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
