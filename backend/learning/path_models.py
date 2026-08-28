"""Models for personalized discrete-math learning paths."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LearningPathRefreshRequest(BaseModel):
    user_id: int = Field(gt=0)
    force: bool = True


class LearningPathNode(BaseModel):
    node_id: str
    module: str
    stage: str
    priority: float = Field(ge=0, le=100)
    title: str
    reason: str
    evidence: dict[str, Any]
    tasks: list[dict[str, Any]]
    mastery_gate: dict[str, Any]
    status: str
    confidence: float = Field(ge=0, le=1)


class LearningPathStage(BaseModel):
    stage: str
    title: str
    objective: str
    nodes: list[LearningPathNode]


class LearningPathResponse(BaseModel):
    user_id: int
    path_id: str
    version: int
    strategy: str
    data_quality: dict[str, Any]
    diagnosis: dict[str, Any]
    stages: list[LearningPathStage]
    # 扁平化后的节点 id 列表（按 stage 顺序），给旧版薄 UI 兜底用。
    path: list[str] = Field(default_factory=list)
    ai_notes: dict[str, Any]
    generated_at: str
