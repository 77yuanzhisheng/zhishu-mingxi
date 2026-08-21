"""Authentication, additive user migration and student exam API tests."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.router import router as auth_router
from backend.learning.database import connection_scope, init_database
from backend.learning.service import create_user
from backend.management.class_service import create_class, join_class
from backend.management.exam_service import generate_exam, submit_exam
from backend.management.models import SubmittedAnswer
from backend.management.router import router as management_router


@pytest.fixture
def client_and_database(tmp_path, monkeypatch):
    database_path = tmp_path / "auth-exam.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-only-secret-with-sufficient-entropy")
    monkeypatch.setenv("AUTH_JWT_EXPIRE_MINUTES", "60")
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(management_router)
    return TestClient(app), database_path


def register(client: TestClient, username: str, role: str = "student"):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "123456",
            "name": f"{username}姓名",
            "role": role,
        },
    )


def test_student_and_teacher_registration_and_admin_rejection(client_and_database):
    client, _ = client_and_database
    student = register(client, "student-one")
    teacher = register(client, "teacher-one", "teacher")
    admin = register(client, "admin-one", "admin")

    assert student.status_code == 200
    assert student.json()["user"]["role"] == "student"
    assert student.json()["user"]["class_id"] is None
    assert student.json()["token"]
    assert teacher.status_code == 200
    assert teacher.json()["user"]["role"] == "teacher"
    assert admin.status_code == 422


def test_duplicate_username_and_password_hash_storage(client_and_database):
    client, database_path = client_and_database
    assert register(client, "unique-user").status_code == 200
    duplicate = register(client, "unique-user")
    assert duplicate.status_code == 409

    with connection_scope(database_path) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("unique-user",)
        ).fetchone()
    assert row["password_hash"] != "123456"
    assert row["password_hash"].startswith("$2")


def test_login_and_me_success_and_unauthorized_cases(client_and_database):
    client, _ = client_and_database
    registered = register(client, "login-user")
    login = client.post(
        "/api/auth/login", json={"username": "login-user", "password": "123456"}
    )
    wrong_password = client.post(
        "/api/auth/login", json={"username": "login-user", "password": "bad-password"}
    )
    missing_user = client.post(
        "/api/auth/login", json={"username": "missing", "password": "123456"}
    )

    assert login.status_code == 200
    assert login.json()["user"] == registered.json()["user"]
    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401

    valid_me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {login.json()['token']}"}
    )
    invalid_me = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer invalid-token"}
    )
    missing_me = client.get("/api/auth/me")
    assert valid_me.status_code == 200
    assert valid_me.json()["username"] == "login-user"
    assert invalid_me.status_code == 401
    assert missing_me.status_code == 401


def test_existing_users_table_is_migrated_without_rebuilding(tmp_path):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            class_id INTEGER
        )
        """
    )
    connection.execute(
        "INSERT INTO users (name, role, class_id) VALUES ('旧学生', 'student', NULL)"
    )
    connection.commit()
    connection.close()

    init_database(database_path)
    with connection_scope(database_path) as connection:
        columns = {
            row["name"]: row for row in connection.execute("PRAGMA table_info(users)")
        }
        old_user = connection.execute("SELECT * FROM users WHERE id = 1").fetchone()
    assert {"username", "password_hash"} <= set(columns)
    assert columns["username"]["notnull"] == 0
    assert columns["password_hash"]["notnull"] == 0
    assert old_user["name"] == "旧学生"
    assert old_user["username"] is None
    assert old_user["password_hash"] is None


def test_student_exam_list_submission_state_and_safe_detail(
    client_and_database, monkeypatch
):
    client, database_path = client_and_database
    teacher_id = create_user("考试教师", "teacher", database_path=database_path)
    student_id = create_user("考试学生", "student", database_path=database_path)
    class_info = create_class(teacher_id, "认证考试班", database_path)
    join_class(student_id, class_info.invite_code, database_path)

    monkeypatch.setattr(
        "backend.management.exam_service.recommend_exam_questions",
        lambda node_ids, count: [
            {
                "node_id": "pl_03_01",
                "type": "选择题",
                "content": "测试题目",
                "answer": "A",
            }
        ],
    )
    exam = generate_exam(
        teacher_id,
        class_info.class_id,
        "学生端考试",
        ["pl_03_01"],
        1,
        database_path,
    )

    before = client.get(f"/api/exam/student/{student_id}")
    assert before.status_code == 200
    assert before.json()[0]["exam_id"] == exam.exam_id
    assert before.json()[0]["submitted"] is False

    detail = client.get(f"/api/exam/{exam.exam_id}")
    assert detail.status_code == 200
    assert detail.json()["questions"]
    assert "answer" not in detail.json()["questions"][0]
    assert "grading_mode" not in detail.json()["questions"][0]

    submit_exam(
        exam.exam_id,
        student_id,
        [SubmittedAnswer(question_id=exam.questions[0].question_id, answer="A")],
        database_path,
    )
    after = client.get(f"/api/exam/student/{student_id}")
    assert after.status_code == 200
    assert after.json()[0]["submitted"] is True


def test_student_exam_list_validates_user_role(client_and_database):
    client, database_path = client_and_database
    teacher_id = create_user("不是学生", "teacher", database_path=database_path)
    missing = client.get("/api/exam/student/999999")
    wrong_role = client.get(f"/api/exam/student/{teacher_id}")
    assert missing.status_code == 404
    assert wrong_role.status_code == 403
