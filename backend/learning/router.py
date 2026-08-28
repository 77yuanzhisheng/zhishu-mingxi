"""FastAPI routes for learning analytics."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from backend.learning.path_router import router as path_router
from backend.learning.models import (
    AbilityProfile,
    AnswerEvent,
    AnswerEventCreate,
    AnswerEventsResponse,
    AnswerQuestionType,
    LearningReport,
    MasteryUpdateRequest,
    MasteryUpdateResponse,
)
from backend.learning.service import (
    UserNotFoundError,
    build_ai_summary,
    create_answer_event,
    get_ability_profile,
    get_answer_events,
    get_learning_report,
    update_mastery,
)


router = APIRouter(prefix="/api/learning", tags=["learning analytics"])
router.include_router(path_router)


@router.post(
    "/events",
    response_model=AnswerEvent,
    summary="记录做题结果，并在已判定时更新掌握度",
)
def create_answer_event_endpoint(request: AnswerEventCreate) -> AnswerEvent:
    try:
        return create_answer_event(**request.model_dump())
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/events",
    response_model=AnswerEventsResponse,
    summary="Get answer-event history",
)
def answer_events_endpoint(
    user_id: int = Query(..., gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    question_type: AnswerQuestionType | None = Query(None),
    node_id: str | None = Query(None, min_length=1, max_length=100),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
) -> AnswerEventsResponse:
    try:
        return get_answer_events(
            user_id,
            limit=limit,
            offset=offset,
            question_type=question_type,
            node_id=node_id,
            start_time=start_time,
            end_time=end_time,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/ability-profile",
    response_model=AbilityProfile,
    summary="获取结合问答与做题证据的六模块能力画像",
)
def ability_profile_endpoint(
    user_id: int = Query(..., gt=0, description="User ID"),
) -> AbilityProfile:
    try:
        return get_ability_profile(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/update-mastery",
    response_model=MasteryUpdateResponse,
    summary="Record one mastery update",
)
def update_mastery_endpoint(request: MasteryUpdateRequest) -> MasteryUpdateResponse:
    try:
        return update_mastery(request.user_id, request.node_id, request.correct)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/report",
    response_model=LearningReport,
    summary="获取结合问答与做题证据的用户学情报告",
)
def learning_report_endpoint(
    user_id: int = Query(..., gt=0, description="User ID"),
) -> LearningReport:
    try:
        return get_learning_report(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/ai-summary",
    summary="AI 综合学情分析（基于问答历史与答题数据，<=50 字）",
)
def ai_summary_endpoint(
    user_id: int = Query(..., gt=0, description="User ID"),
) -> dict[str, str]:
    try:
        return {"summary": build_ai_summary(user_id)}
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
