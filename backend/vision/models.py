"""Pydantic models for vision parsing."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VisionParseResponse(BaseModel):
    """Normalized, provider-neutral result of parsing a question image."""

    question_text: str = ""
    student_answer: str = ""
    latex: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    elapsed_ms: int = Field(default=0, ge=0)
