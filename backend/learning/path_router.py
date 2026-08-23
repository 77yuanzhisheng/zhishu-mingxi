"""Routes for personalized learning paths."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.learning.service import UserNotFoundError
from backend.learning.path_engine import get_learning_path, refresh_learning_path
from backend.learning.path_models import LearningPathRefreshRequest, LearningPathResponse

router = APIRouter()


@router.get(
    "/path",
    response_model=LearningPathResponse,
    summary="生成或读取个性化离散数学学习路径",
)
def learning_path_endpoint(user_id: int = Query(..., gt=0)) -> LearningPathResponse:
    try:
        return get_learning_path(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/path/refresh",
    response_model=LearningPathResponse,
    summary="强制刷新个性化离散数学学习路径",
)
def refresh_learning_path_endpoint(request: LearningPathRefreshRequest) -> LearningPathResponse:
    try:
        if not request.force:
            return get_learning_path(request.user_id)
        return refresh_learning_path(request.user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
