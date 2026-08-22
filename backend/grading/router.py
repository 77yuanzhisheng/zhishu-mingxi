'''HTTP boundary for the grading engine.'''

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from backend.chat.exceptions import LLMUnavailableError
from backend.grading.models import GradeRequest, GradeResponse
from backend.grading.service import GradingService, InvalidGradingOutputError


router = APIRouter(prefix='/api/grading', tags=['grading'])


@lru_cache(maxsize=1)
def get_grading_service() -> GradingService:
    return GradingService()


@router.post('/grade', response_model=GradeResponse, summary='Grade a long-form answer with an auditable rubric')
def grade_endpoint(
    request: GradeRequest,
    service: GradingService = Depends(get_grading_service),
) -> GradeResponse:
    try:
        return service.grade(request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidGradingOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
