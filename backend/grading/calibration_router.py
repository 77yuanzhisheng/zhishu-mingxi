'''HTTP endpoints for human-label calibration of grading results.'''

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.grading.calibration import (
    RUBRIC_VERSION,
    HumanLabelInput,
    adjudicate_label,
    build_calibration_report,
    store_human_label,
)
from backend.grading.models import DIMENSION_LIMITS, ERROR_TYPES
from backend.learning.database import get_database_path


router = APIRouter(prefix="/api/grading", tags=["grading-calibration"])


class HumanLabelPayload(BaseModel):
    rater_id: str = Field(min_length=1, max_length=100)
    rubric_version: str = Field(default=RUBRIC_VERSION, max_length=20)
    total_score: float = Field(ge=0, le=100)
    dimension_scores: dict[str, float]
    error_types: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("rater_id", "reason")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_rubric(self):
        if self.rubric_version != RUBRIC_VERSION:
            raise ValueError("unsupported rubric version")
        if set(self.dimension_scores) != set(DIMENSION_LIMITS):
            raise ValueError("dimension_scores must contain exactly the five rubric dimensions")
        for dimension, maximum in DIMENSION_LIMITS.items():
            score = self.dimension_scores[dimension]
            if not 0 <= score <= maximum:
                raise ValueError(f"{dimension} exceeds its rubric maximum")
        if len(self.error_types) != len(set(self.error_types)):
            raise ValueError("error_types must not contain duplicates")
        if any(error not in ERROR_TYPES for error in self.error_types):
            raise ValueError("error_types contains unsupported values")
        return self

    def to_input(self, result_id: int) -> HumanLabelInput:
        return HumanLabelInput(
            result_id=result_id,
            rater_id=self.rater_id,
            rubric_version=self.rubric_version,
            total_score=self.total_score,
            dimension_scores=self.dimension_scores,
            error_types=self.error_types,
            reason=self.reason,
        )


class AdjudicationPayload(HumanLabelPayload):
    adjudicator_id: str = Field(min_length=1, max_length=100)

    @field_validator("adjudicator_id")
    @classmethod
    def require_nonblank_adjudicator(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


@router.post(
    "/results/{result_id}/human-labels",
    status_code=status.HTTP_201_CREATED,
    summary="Store one independent human grading label",
)
def create_human_label(result_id: Annotated[int, Path(gt=0)], payload: HumanLabelPayload) -> dict:
    try:
        label_id = store_human_label(get_database_path(), payload.to_input(result_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"id": label_id, "result_id": result_id, "status": "recorded"}


@router.post(
    "/results/{result_id}/adjudication",
    status_code=status.HTTP_201_CREATED,
    summary="Store the adjudicated gold label after two independent reviews",
)
def create_adjudication(result_id: Annotated[int, Path(gt=0)], payload: AdjudicationPayload) -> dict:
    try:
        return adjudicate_label(
            get_database_path(),
            result_id,
            payload.adjudicator_id,
            payload.to_input(result_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/calibration/report", summary="Report model agreement against adjudicated human labels")
def calibration_report(question_type: str = "overall", minimum_samples: int = 20) -> dict:
    if question_type not in {"overall", "proof", "calc"}:
        raise HTTPException(status_code=400, detail="question_type must be overall, proof, or calc")
    if not 1 <= minimum_samples <= 10000:
        raise HTTPException(status_code=400, detail="minimum_samples out of range")
    return build_calibration_report(get_database_path(), question_type, minimum_samples)
