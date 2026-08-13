"""FastAPI routes for learning analytics."""

from fastapi import APIRouter, HTTPException, Query

from backend.learning.models import (
    LearningReport,
    MasteryUpdateRequest,
    MasteryUpdateResponse,
)
from backend.learning.service import UserNotFoundError, get_learning_report, update_mastery


router = APIRouter(prefix="/api/learning", tags=["学情分析"])


@router.post(
    "/update-mastery",
    response_model=MasteryUpdateResponse,
    summary="记录答题结果并更新知识点掌握度",
)
def update_mastery_endpoint(request: MasteryUpdateRequest) -> MasteryUpdateResponse:
    try:
        return update_mastery(request.user_id, request.node_id, request.correct)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/report",
    response_model=LearningReport,
    summary="获取用户学情报告",
)
def learning_report_endpoint(
    user_id: int = Query(..., gt=0, description="用户 ID"),
) -> LearningReport:
    try:
        return get_learning_report(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
