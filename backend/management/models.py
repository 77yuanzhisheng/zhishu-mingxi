"""Pydantic contracts for class, exam and sharing endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.learning.models import LearningReport, RadarModule


class ClassCreateRequest(BaseModel):
    # 2026-09-14 起可选：省略则一律以 token 里的身份为准（auth/dependencies.py:resolve_actor）。
    # 保留这个字段只是不想把旧客户端打成 422；传了就必须与 token 一致，否则 403。
    teacher_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=100)


class ClassInfo(BaseModel):
    class_id: int
    name: str
    invite_code: str
    teacher_id: int


class ClassJoinRequest(BaseModel):
    # 同 ClassCreateRequest：可选，以 token 身份为准。
    user_id: int | None = Field(default=None, gt=0)
    invite_code: str = Field(min_length=1, max_length=20)


class ClassJoinResponse(BaseModel):
    message: str
    class_info: ClassInfo
    already_joined: bool


class LearningSummary(BaseModel):
    practiced_nodes: int = 0
    mastered_nodes: int = 0
    weak_nodes: int = 0
    total_answers: int = 0
    overall_accuracy: float = 0.0


class ClassStudent(BaseModel):
    user_id: int
    name: str
    role: str
    learning_summary: LearningSummary


class ClassStudentsResponse(BaseModel):
    class_id: int
    name: str
    students: list[ClassStudent]


class WeakNodeFrequency(BaseModel):
    node_id: str
    student_count: int


class ClassReportResponse(BaseModel):
    class_id: int
    class_name: str
    student_count: int
    radar_data: list[RadarModule]
    overall_accuracy: float
    weak_nodes: list[WeakNodeFrequency]
    students: list[ClassStudent]


class ExamGenerateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "teacher_id": 1,
                "class_id": 1,
                "title": "命题逻辑测试",
                "node_ids": ["pl_02_02", "pl_03_01"],
                "question_count": 5,
            }
        }
    )

    # 同 ClassCreateRequest：可选，以 token 身份为准。
    teacher_id: int | None = Field(default=None, gt=0)
    class_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    node_ids: list[str] = Field(min_length=1, max_length=20)
    question_count: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def normalize_nodes(self) -> "ExamGenerateRequest":
        self.node_ids = list(dict.fromkeys(node.strip() for node in self.node_ids if node.strip()))
        if not self.node_ids:
            raise ValueError("node_ids 不能为空")
        return self


class ExamQuestion(BaseModel):
    question_id: int
    node_id: str
    question_type: str
    content: str
    answer: str | None = None
    score: float
    sort_order: int
    grading_mode: Literal["automatic", "pending_review"]


class ExamGenerateResponse(BaseModel):
    exam_id: int
    class_id: int
    teacher_id: int
    title: str
    total_score: float
    status: str
    questions: list[ExamQuestion]


class StudentExamInfo(BaseModel):
    exam_id: int
    title: str
    class_id: int
    status: str
    created_at: datetime
    total_score: float
    submitted: bool


class StudentExamQuestion(BaseModel):
    question_id: int
    node_id: str
    question_type: str
    content: str
    score: float
    sort_order: int


class StudentExamDetail(BaseModel):
    exam_id: int
    title: str
    class_id: int
    status: str
    created_at: datetime
    total_score: float
    questions: list[StudentExamQuestion]


class SubmittedAnswer(BaseModel):
    question_id: int = Field(gt=0)
    answer: str = Field(default="", max_length=10000)


class ExamSubmitRequest(BaseModel):
    exam_id: int = Field(gt=0)
    # 同 ClassCreateRequest：可选，以 token 身份为准。原先信任它 = 可以替别人交卷。
    user_id: int | None = Field(default=None, gt=0)
    answers: list[SubmittedAnswer] = Field(default_factory=list)


class AnswerResult(BaseModel):
    question_id: int
    node_id: str
    is_correct: bool | None
    score: float
    review_status: Literal["graded", "pending_review"]


class ExamSubmitResponse(BaseModel):
    submission_id: int
    exam_id: int
    user_id: int
    total_score: float
    status: Literal["graded", "pending_review"]
    answers: list[AnswerResult]


class StudentExamResult(BaseModel):
    user_id: int
    name: str
    total_score: float
    status: str
    submitted_at: datetime


class NodeExamStatistic(BaseModel):
    node_id: str
    graded_answers: int
    correct_answers: int
    accuracy: float | None
    pending_review: int


class ExamResultsResponse(BaseModel):
    exam: dict[str, Any]
    submitted_count: int
    average_score: float
    highest_score: float
    lowest_score: float
    students: list[StudentExamResult]
    node_statistics: list[NodeExamStatistic]
    weak_nodes: list[str]


class ShareRequestCreate(BaseModel):
    # 可选，以 token 身份为准 —— 否则可以替别人发起共享申请。
    requester_id: int | None = Field(default=None, gt=0)
    target_user_id: int = Field(gt=0)


class ShareRequestDecision(BaseModel):
    request_id: int = Field(gt=0)
    # ⚠️ 这一个**必须传**、且必须等于登录者本人（端点里用 ensure_self 钉死）。
    # 它就是"谁批准了自己这条申请"的凭据，不能从 request_id 反推成可选。
    target_user_id: int = Field(gt=0)
    approved: bool


class ShareRequestInfo(BaseModel):
    request_id: int
    requester_id: int
    target_user_id: int
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    resolved_at: datetime | None = None


class SharedLearningReport(BaseModel):
    authorized: bool
    report: LearningReport


# ==================== 教师账号审批（超级管理员） ====================


class TeacherAccountInfo(BaseModel):
    user_id: int
    username: str | None = None
    name: str
    status: Literal["pending", "approved", "rejected"]
    # 该教师已建的班级数。管理员点「拒绝」前需要知道这个数 ——
    # 审批不回收已有班级关系，建过班的教师被拒后仍能读那些班的学情。
    class_count: int = 0


class TeacherAccountListResponse(BaseModel):
    teachers: list[TeacherAccountInfo]
    # 前端导航项角标用；恒等于「全部 pending 数」，与 teachers 是否被 status 过滤无关。
    pending_count: int = 0
