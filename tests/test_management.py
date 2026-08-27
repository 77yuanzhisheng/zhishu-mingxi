"""End-to-end service tests for classes, exams and learning sharing."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.learning.database import connection_scope, init_database
from backend.learning.service import create_user, get_learning_report, update_mastery
from backend.management.class_service import (
    create_class,
    get_class_report,
    get_class_students,
    join_class,
)
from backend.management.exam_service import generate_exam, get_exam_results, submit_exam
from backend.management.exceptions import ConflictError, PermissionDeniedError
from backend.management.models import SubmittedAnswer
from backend.management.share_service import (
    create_share_request,
    decide_share_request,
    get_shared_report,
)
from backend.management.question_source import recommend_exam_questions
from backend.management.router import router as management_router


@pytest.fixture
def setup_users(tmp_path):
    database_path = tmp_path / "management.db"
    init_database(database_path)
    teacher_id = create_user("教师", "teacher", database_path=database_path)
    other_teacher_id = create_user("其他教师", "teacher", database_path=database_path)
    student_id = create_user("学生甲", "student", database_path=database_path)
    peer_id = create_user("学生乙", "student", database_path=database_path)
    admin_id = create_user("管理员", "admin", database_path=database_path)
    return database_path, teacher_id, other_teacher_id, student_id, peer_id, admin_id


def test_class_create_join_students_report_and_permissions(setup_users):
    database_path, teacher_id, other_teacher_id, student_id, _, admin_id = setup_users
    class_info = create_class(teacher_id, "离散数学1班", database_path)
    assert len(class_info.invite_code) == 6

    joined = join_class(student_id, class_info.invite_code, database_path)
    repeated = join_class(student_id, class_info.invite_code, database_path)
    assert joined.already_joined is False
    assert repeated.already_joined is True

    update_mastery(student_id, "pl_02_02", True, database_path)
    update_mastery(student_id, "rel_01_01", False, database_path)
    students = get_class_students(teacher_id, class_info.class_id, database_path)
    assert students.students[0].user_id == student_id
    assert students.students[0].learning_summary.total_answers == 2

    report = get_class_report(teacher_id, class_info.class_id, database_path)
    assert report.student_count == 1
    assert len(report.radar_data) == 6
    assert report.overall_accuracy == 0.5
    # A single wrong answer is insufficient evidence for a confirmed weak node.
    assert report.weak_nodes == []
    assert get_class_report(admin_id, class_info.class_id, database_path).student_count == 1

    with pytest.raises(PermissionDeniedError):
        create_class(student_id, "非法班级", database_path)
    with pytest.raises(PermissionDeniedError):
        get_class_report(other_teacher_id, class_info.class_id, database_path)


def test_exam_generation_grading_mastery_and_results(setup_users, monkeypatch):
    database_path, teacher_id, _, student_id, _, _ = setup_users
    class_info = create_class(teacher_id, "考试班", database_path)
    join_class(student_id, class_info.invite_code, database_path)

    def fixed_questions(node_ids, count):
        return [
            {
                "node_id": "pl_03_01",
                "type": "选择题",
                "content": "公式¬(P∧¬P)属于什么类型？",
                "difficulty": 2,
                "answer": "A",
            },
            {
                "node_id": "pl_02_02",
                "type": "证明题",
                "content": "证明德摩根律",
                "difficulty": 2,
                "answer": None,
            },
        ][:count]

    monkeypatch.setattr(
        "backend.management.exam_service.recommend_exam_questions", fixed_questions
    )
    exam = generate_exam(
        teacher_id,
        class_info.class_id,
        "命题逻辑测试",
        ["pl_03_01", "pl_02_02"],
        2,
        database_path,
    )
    assert exam.exam_id > 0
    assert exam.questions[0].answer == "A"
    assert exam.questions[1].grading_mode == "pending_review"

    submission = submit_exam(
        exam.exam_id,
        student_id,
        [
            SubmittedAnswer(question_id=exam.questions[0].question_id, answer=" a "),
            SubmittedAnswer(question_id=exam.questions[1].question_id, answer="证明过程"),
        ],
        database_path,
    )
    assert submission.total_score == 50
    assert submission.status == "pending_review"
    assert submission.answers[0].is_correct is True
    assert submission.answers[1].is_correct is None

    report = get_learning_report(student_id, database_path)
    assert len(report.node_mastery) == 1
    assert report.node_mastery[0].node_id == "pl_03_01"
    assert report.node_mastery[0].correct_count == 1
    assert report.node_mastery[0].total_count == 1

    results = get_exam_results(exam.exam_id, teacher_id, database_path)
    assert results.submitted_count == 1
    assert results.average_score == 50
    assert results.highest_score == results.lowest_score == 50
    stats = {item.node_id: item for item in results.node_statistics}
    assert stats["pl_03_01"].accuracy == 1.0
    assert stats["pl_02_02"].pending_review == 1

    with pytest.raises(ConflictError):
        submit_exam(exam.exam_id, student_id, [], database_path)


def test_sharing_reject_approve_and_authorized_read(setup_users):
    database_path, _, _, student_id, peer_id, _ = setup_users
    update_mastery(peer_id, "st_01_01", True, database_path)

    with pytest.raises(PermissionDeniedError):
        get_shared_report(peer_id, student_id, database_path)
    rejected = create_share_request(student_id, peer_id, database_path)
    decision = decide_share_request(rejected.request_id, peer_id, False, database_path)
    assert decision.status == "rejected"
    with pytest.raises(PermissionDeniedError):
        get_shared_report(peer_id, student_id, database_path)

    approved = create_share_request(student_id, peer_id, database_path)
    with pytest.raises(PermissionDeniedError):
        decide_share_request(approved.request_id, student_id, True, database_path)
    decision = decide_share_request(approved.request_id, peer_id, True, database_path)
    assert decision.status == "approved"
    shared = get_shared_report(peer_id, student_id, database_path)
    assert shared.authorized is True
    assert shared.report.node_mastery[0].node_id == "st_01_01"
    assert get_shared_report(peer_id, peer_id, database_path).authorized is True

    with pytest.raises(ConflictError):
        create_share_request(student_id, student_id, database_path)


def test_database_migration_adds_all_new_tables(tmp_path):
    database_path = tmp_path / "migration.db"
    init_database(database_path)
    with connection_scope(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {
        "exams",
        "exam_questions",
        "exam_submissions",
        "exam_answers",
        "share_requests",
    } <= tables


def test_existing_kb_question_source_is_reused_without_synthesizing_answers():
    questions = recommend_exam_questions(["pl_03_01"], 2)
    assert len(questions) == 2
    assert all(question["node_id"] == "pl_03_01" for question in questions)
    choice = next(question for question in questions if question["type"] == "选择题")
    assert choice["answer"] == "A"


def test_management_http_routes_and_permission_status(tmp_path, monkeypatch):
    database_path = tmp_path / "http.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    teacher_id = create_user("HTTP教师", "teacher", database_path=database_path)
    student_id = create_user("HTTP学生", "student", database_path=database_path)
    stranger_id = create_user("陌生学生", "student", database_path=database_path)
    app = FastAPI()
    app.include_router(management_router)
    client = TestClient(app)

    ensured = client.post(
        "/api/user/ensure",
        json={"user_id": 99, "name": "前端演示用户", "role": "student"},
    )
    assert ensured.status_code == 200
    assert ensured.json()["id"] == 99

    created = client.post(
        "/api/class/create", json={"teacher_id": teacher_id, "name": "HTTP班级"}
    )
    assert created.status_code == 200
    class_info = created.json()
    joined = client.post(
        "/api/class/join",
        json={"user_id": student_id, "invite_code": class_info["invite_code"]},
    )
    assert joined.status_code == 200
    forbidden = client.get(
        f"/api/class/{class_info['class_id']}/report",
        params={"requester_id": stranger_id},
    )
    assert forbidden.status_code == 403
    allowed = client.get(
        f"/api/class/{class_info['class_id']}/report",
        params={"requester_id": teacher_id},
    )
    assert allowed.status_code == 200

    paths = app.openapi()["paths"]
    assert {
        "/api/user/ensure",
        "/api/class/create",
        "/api/class/join",
        "/api/class/{class_id}/students",
        "/api/class/{class_id}/report",
        "/api/exam/generate",
        "/api/exam/submit",
        "/api/exam/{exam_id}/results",
        "/api/share/request",
        "/api/share/approve",
        "/api/share/{target_user_id}/report",
    } <= set(paths)
