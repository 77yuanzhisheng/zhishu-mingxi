"""FastAPI routes for classes, exams and learning-report sharing."""

from fastapi import APIRouter, HTTPException, Query

from backend.management.class_service import (
    create_class,
    get_class_report,
    get_class_students,
    join_class,
)
from backend.management.exam_service import (
    generate_exam,
    get_exam_results,
    get_student_exam,
    get_student_exams,
    submit_exam,
)
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
    StudentExamDetail,
    StudentExamInfo,
)
from backend.management.share_service import (
    create_share_request,
    decide_share_request,
    get_shared_report,
)


router = APIRouter(tags=["用户、班级与考试管理"])


def _raise_http(exc: ManagementError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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


@router.get("/api/exam/student/{user_id}", response_model=list[StudentExamInfo])
def student_exams_endpoint(user_id: int):
    try:
        return get_student_exams(user_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/exam/{exam_id}", response_model=StudentExamDetail)
def student_exam_endpoint(exam_id: int):
    try:
        return get_student_exam(exam_id)
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
