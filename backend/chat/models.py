"""Public request and response models for the chat API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "session_id": None,
                "message": "德摩根律是什么？",
                "node_id": "pl_02_02",
            }
        }
    )

    user_id: int = Field(gt=0, description="用户 ID")
    session_id: int | None = Field(default=None, gt=0, description="为空时创建新会话")
    message: str = Field(min_length=1, max_length=4000)
    node_id: str | None = Field(default=None, min_length=1, max_length=100)
    node_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def normalize_node_ids(self) -> "ChatRequest":
        candidates = ([self.node_id] if self.node_id else []) + self.node_ids
        normalized: list[str] = []
        for node_id in candidates:
            clean_id = node_id.strip()
            if clean_id and clean_id not in normalized:
                normalized.append(clean_id)
        self.node_ids = normalized
        self.node_id = normalized[0] if normalized else None
        return self


class ChatReference(BaseModel):
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextStatus(BaseModel):
    history_messages_used: int = Field(ge=0)
    total_rounds: int = Field(ge=0)
    compressed: bool
    summary_available: bool
    rag_used: bool
    rag_status: str


class ChatResponse(BaseModel):
    answer: str
    session_id: int
    references: list[ChatReference] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    topic_switch_hint: str | None = None
    context: ContextStatus
