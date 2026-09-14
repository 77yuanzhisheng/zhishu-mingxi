"""FastAPI routes for users, classes, exams and learning-report sharing."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.auth.dependencies import (
    ensure_can_read_user,
    ensure_self,
    get_current_user,
    require_admin,
    require_teacher,
    resolve_actor,
)
from backend.auth.models import AuthUser
from backend.learning.database import connection_scope, init_database

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
    TeacherAccountInfo,
    TeacherAccountListResponse,
)
from backend.management.share_service import (
    create_share_request,
    decide_share_request,
    get_shared_report,
)
from backend.management.teacher_service import (
    count_pending,
    list_teachers,
    set_teacher_status,
)


router = APIRouter(tags=["用户、班级与考试管理"])


class UserEnsureRequest(BaseModel):
    user_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    # 2026-09-14 收窄：原来是 student|teacher|admin，等于公开送人一个 admin。
    # 本接口不加鉴权，理由有三：① 实测前端 0 处调用（死接口）
    # ② 它只能「不存在则插入」、改不了已有行（所以升不了权）
    # ③ 插入的行没有 username，签不出 token，够不到任何权限。
    # 加 ensure_self 会撞上鸡生蛋：行不存在 → 没 username → 签不出 token 来通过校验。
    # 计划下一轮直接删掉这个接口。
    role: Literal["student", "teacher"] = "student"


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
            # 自报 teacher 的同样按待审批处理，别让这个后门绕过审批。
            connection.execute(
                "INSERT INTO users (id, name, role, teacher_status) VALUES (?, ?, ?, ?)",
                (
                    request.user_id,
                    request.name.strip(),
                    request.role,
                    "pending" if request.role == "teacher" else "approved",
                ),
            )
            row = connection.execute(
                "SELECT id, name, role, class_id FROM users WHERE id = ?",
                (request.user_id,),
            ).fetchone()
    return dict(row)


@router.post("/api/class/create", response_model=ClassInfo)
def create_class_endpoint(
    request: ClassCreateRequest,
    user: AuthUser = Depends(require_teacher),
):
    actor = resolve_actor(user, request.teacher_id, what="teacher_id")
    try:
        return create_class(actor, request.name)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/class/join", response_model=ClassJoinResponse)
def join_class_endpoint(
    request: ClassJoinRequest,
    user: AuthUser = Depends(get_current_user),
):
    # 原先信任 body 里的 user_id：可以把一个刚注册、class_id 还是 NULL 的学生
    # 直接写进攻击者的班，之后 _is_class_teacher_of 成立 ——那是偷学情的另一条路。
    actor = resolve_actor(user, request.user_id, what="user_id")
    try:
        return join_class(actor, request.invite_code)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/class/{class_id}/students", response_model=ClassStudentsResponse)
def class_students_endpoint(
    class_id: int,
    requester_id: int | None = Query(None, gt=0, description="已废弃：以 token 身份为准"),
    user: AuthUser = Depends(require_teacher),
):
    actor = resolve_actor(user, requester_id, what="requester_id")
    try:
        return get_class_students(actor, class_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/class/{class_id}/report", response_model=ClassReportResponse)
def class_report_endpoint(
    class_id: int,
    requester_id: int | None = Query(None, gt=0, description="已废弃：以 token 身份为准"),
    user: AuthUser = Depends(require_teacher),
):
    actor = resolve_actor(user, requester_id, what="requester_id")
    try:
        return get_class_report(actor, class_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/exam/generate", response_model=ExamGenerateResponse)
def generate_exam_endpoint(
    request: ExamGenerateRequest,
    user: AuthUser = Depends(require_teacher),
):
    actor = resolve_actor(user, request.teacher_id, what="teacher_id")
    try:
        return generate_exam(
            actor,
            request.class_id,
            request.title,
            request.node_ids,
            request.question_count,
        )
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/exam/submit", response_model=ExamSubmitResponse)
def submit_exam_endpoint(
    request: ExamSubmitRequest,
    user: AuthUser = Depends(get_current_user),
):
    # 原先信任 body 里的 user_id：可以替别人交卷（写进别人的成绩）。
    actor = resolve_actor(user, request.user_id, what="user_id")
    try:
        return submit_exam(request.exam_id, actor, request.answers)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/exam/student/{user_id}", response_model=list[StudentExamInfo])
def student_exams_endpoint(
    user_id: int,
    user: AuthUser = Depends(get_current_user),
):
    ensure_self(user, user_id)
    try:
        return get_student_exams(user_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/exam/{exam_id}", response_model=StudentExamDetail)
def student_exam_endpoint(
    exam_id: int,
    user: AuthUser = Depends(get_current_user),
):
    # 只要求登录：get_student_exam 的 SELECT 里**没有 answer 列**（只回题干/分值/题型），
    # 所以拿到别人的 exam_id 也偷不到答案。加 ensure_self 反而会把
    # 「老师预览自己班的试卷」这类正常需求挡掉。
    try:
        return get_student_exam(exam_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.get("/api/exam/{exam_id}/results", response_model=ExamResultsResponse)
def exam_results_endpoint(
    exam_id: int,
    requester_id: int | None = Query(None, gt=0, description="已废弃：以 token 身份为准"),
    user: AuthUser = Depends(require_teacher),
):
    actor = resolve_actor(user, requester_id, what="requester_id")
    try:
        return get_exam_results(exam_id, actor)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/share/request", response_model=ShareRequestInfo)
def share_request_endpoint(
    request: ShareRequestCreate,
    user: AuthUser = Depends(get_current_user),
):
    # requester_id 必须是登录者自己 —— 否则可以替别人发起申请。
    actor = resolve_actor(user, request.requester_id, what="requester_id")
    try:
        return create_share_request(actor, request.target_user_id)
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/share/approve", response_model=ShareRequestInfo)
def share_decision_endpoint(
    request: ShareRequestDecision,
    user: AuthUser = Depends(get_current_user),
):
    """⚠️ 这一条是本次修的最高优先级漏洞。

    decide_share_request 拿**请求体里的** target_user_id 去和 share_requests 表里
    **同样由客户端写入的** target_user_id 比对，等于自证自明。攻击链（全程不需要 token）：
        ① POST /api/share/request {requester_id: 我, target_user_id: 受害者}
        ② POST /api/share/approve {request_id, target_user_id: 受害者, approved: true}
        ③ GET  /api/share/受害者/report → 拿到受害者的完整学情
    ensure_self 钉死「只有数据所有者本人能批自己的申请」，这条链就断了。
    """
    ensure_self(user, request.target_user_id)
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
    requester_id: int | None = Query(None, gt=0, description="已废弃：以 token 身份为准"),
    user: AuthUser = Depends(get_current_user),
):
    actor = resolve_actor(user, requester_id, what="requester_id")
    # get_shared_report 自己会查 share_requests；这里再加一层 can_read_user 兜底，
    # 防止将来看 share_service 的人改松了判据。
    ensure_can_read_user(user, target_user_id)
    try:
        return get_shared_report(target_user_id, actor)
    except ManagementError as exc:
        _raise_http(exc)


# ==================== 教师账号审批（仅超级管理员） ====================


@router.get("/api/admin/teachers", response_model=TeacherAccountListResponse)
def list_teacher_accounts_endpoint(
    status: Literal["pending", "approved", "rejected", "all"] = Query(
        "pending", description="按审批状态过滤；all 表示全部"
    ),
    _admin: AuthUser = Depends(require_admin),
):
    return TeacherAccountListResponse(
        teachers=[TeacherAccountInfo(**item) for item in list_teachers(status)],
        pending_count=count_pending(),
    )


@router.post("/api/admin/teachers/{user_id}/approve", response_model=TeacherAccountInfo)
def approve_teacher_endpoint(
    user_id: int,
    _admin: AuthUser = Depends(require_admin),
):
    try:
        return TeacherAccountInfo(**set_teacher_status(user_id, "approved"))
    except ManagementError as exc:
        _raise_http(exc)


@router.post("/api/admin/teachers/{user_id}/reject", response_model=TeacherAccountInfo)
def reject_teacher_endpoint(
    user_id: int,
    _admin: AuthUser = Depends(require_admin),
):
    try:
        return TeacherAccountInfo(**set_teacher_status(user_id, "rejected"))
    except ManagementError as exc:
        _raise_http(exc)
