"""FastAPI routes for users, classes, exams and learning-report sharing."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.learning.database import connection_scope, init_database

from backend.management.class_service import (
    create_class,
    get_class_report,
    get_class_students,
    join_class,
)
from backend.management.exam_service import generate_exam, get_exam_results, submit_exam
from backend.management.exceptions import ManagementError
from backend.management.models import (
    ClassCreateRequest,
    ClassInfo,
    ClassJoinRequest,
    ClassJoinResponse,
    ClassReportResponse,
    ClassStudentsResponse,
    ExamGenerateRequest,
    ExamGenerateResponse,
    ExamResultsResponse,
    ExamSubmitRequest,
    ExamSubmitResponse,
    ShareRequestCreate,
    ShareRequestDecision,
    ShareRequestInfo,
    SharedLearningReport,
)
from backend.management.share_service import (
    create_share_request,
    decide_share_request,
    get_shared_report,
)


router = APIRouter(tags=["用户、班级与考试管理"])


class UserEnsureRequest(BaseModel):
    user_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    role: Literal["student", "teacher", "admin"] = "student"


def _raise_http(exc: ManagementError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/api/user/ensure", summary="确保前端当前用户存在")
def ensure_user_endpoint(request: UserEnsureRequest):
    """Create the requested demo user once and return the persisted record."""

    init_database()
    with connection_scope() as connection:
        row = connection.execute(
            "SELECT id, name, role, class_id FROM users WHERE id = ?",
            (request.user_id,),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO users (id, name, role) VALUES (?, ?, ?)",
                (request.user_id, request.name.strip(), request.role),
            )
            row = connection.execute(
                "SELECT id, name, role, class_id FROM users WHERE id = ?",
                (request.user_id,),
            ).fetchone()
    return dict(row)


@router.post("/api/class/create", response_model=ClassInfo)
def create_class_endpoint(request: ClassCreateRequest):
    try:
        return create_class(request.teacher_id, request.name)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/class/join", response_model=ClassJoinResponse)
def join_class_endpoint(request: ClassJoinRequest):
    try:
        return join_class(request.user_id, request.invite_code)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/class/{class_id}/students", response_model=ClassStudentsResponse)
def class_students_endpoint(
    class_id: int,
    requester_id: int = Query(..., gt=0, description="当前操作者 ID"),
):
    try:
        return get_class_students(requester_id, class_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/class/{class_id}/report", response_model=ClassReportResponse)
def class_report_endpoint(
    class_id: int,
    requester_id: int = Query(..., gt=0, description="当前操作者 ID"),
):
    try:
        return get_class_report(requester_id, class_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/exam/generate", response_model=ExamGenerateResponse)
def generate_exam_endpoint(request: ExamGenerateRequest):
    try:
        return generate_exam(
            request.teacher_id,
            request.class_id,
            request.title,
            request.node_ids,
            request.question_count,
        )
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/exam/submit", response_model=ExamSubmitResponse)
def submit_exam_endpoint(request: ExamSubmitRequest):
    try:
        return submit_exam(request.exam_id, request.user_id, request.answers)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/exam/{exam_id}/results", response_model=ExamResultsResponse)
def exam_results_endpoint(
    exam_id: int,
    requester_id: int = Query(..., gt=0, description="当前操作者 ID"),
):
    try:
        return get_exam_results(exam_id, requester_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/share/request", response_model=ShareRequestInfo)
def share_request_endpoint(request: ShareRequestCreate):
    try:
        return create_share_request(request.requester_id, request.target_user_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/share/approve", response_model=ShareRequestInfo)
def share_decision_endpoint(request: ShareRequestDecision):
    try:
        return decide_share_request(
            request.request_id, request.target_user_id, request.approved
        )
    except ManagementError as exc:
        _raise_http(exc)


@router.get(
    "/api/share/{target_user_id}/report", response_model=SharedLearningReport
)
def shared_report_endpoint(
    target_user_id: int,
    requester_id: int = Query(..., gt=0, description="查看者用户 ID"),
):
    try:
        return get_shared_report(target_user_id, requester_id)
    except ManagementError as exc:
        _raise_http(exc)
