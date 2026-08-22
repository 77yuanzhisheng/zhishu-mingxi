"""Answer-event collection and ability-profile contract tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.learning.database import connection_scope, init_database
from backend.learning.router import router as learning_router
from backend.learning.service import (
    MODULE_NODE_TOTALS,
    PRACTICE_TARGET,
    calculate_ability_level,
    create_answer_event,
    create_user,
    get_ability_profile,
    get_answer_events,
)
from backend.management.class_service import create_class, join_class
from backend.management.exam_service import generate_exam, submit_exam
from backend.management.exceptions import ConflictError
from backend.management.models import SubmittedAnswer


@pytest.fixture
def learning_client(tmp_path, monkeypatch):
    database_path = tmp_path / "events.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    user_id = create_user("事件学生", database_path=database_path)
    app = FastAPI()
    app.include_router(learning_router)
    return TestClient(app), database_path, user_id


def event_payload(user_id: int, **overrides):
    payload = {
        "user_id": user_id,
        "question_id": "q001",
        "question_type": "single",
        "module": "命题逻辑",
        "node_id": "pl_02_02",
        "is_correct": True,
        "duration_ms": 18300,
        "answer_text": "C",
    }
    payload.update(overrides)
    return payload


def test_post_event_updates_mastery_only_for_graded_results(learning_client):
    client, database_path, user_id = learning_client
    created = client.post("/api/learning/events", json=event_payload(user_id))
    pending = client.post(
        "/api/learning/events",
        json=event_payload(
            user_id,
            question_id="proof-1",
            question_type="proof",
            is_correct=None,
            duration_ms=None,
            answer_text="证明过程",
        ),
    )
    missing_user = client.post("/api/learning/events", json=event_payload(999999))
    invalid_type = client.post(
        "/api/learning/events",
        json=event_payload(user_id, question_type="choice"),
    )
    negative_duration = client.post(
        "/api/learning/events",
        json=event_payload(user_id, duration_ms=-1),
    )

    assert created.status_code == 200
    assert created.json()["event_id"] > 0
    assert created.json()["module"] == "命题逻辑"
    assert pending.status_code == 200
    assert pending.json()["is_correct"] is None
    assert missing_user.status_code == 404
    assert invalid_type.status_code == 422
    assert negative_duration.status_code == 422
    with connection_scope(database_path) as connection:
        mastery = connection.execute(
            "SELECT * FROM node_mastery WHERE user_id = ?", (user_id,)
        ).fetchall()
    assert len(mastery) == 1
    assert mastery[0]["node_id"] == "pl_02_02"
    assert mastery[0]["total_count"] == 1
    assert mastery[0]["correct_count"] == 1


def test_self_practice_wrong_increments_total_but_not_correct(learning_client):
    client, database_path, user_id = learning_client
    assert client.post(
        "/api/learning/events", json=event_payload(user_id, is_correct=True)
    ).status_code == 200
    assert client.post(
        "/api/learning/events",
        json=event_payload(user_id, question_id="q002", is_correct=False),
    ).status_code == 200
    with connection_scope(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM node_mastery WHERE user_id = ? AND node_id = ?",
            (user_id, "pl_02_02"),
        ).fetchone()
    assert row["total_count"] == 2
    assert row["correct_count"] == 1


def test_get_events_reverse_order_pagination_and_filters(learning_client):
    client, database_path, user_id = learning_client
    create_answer_event(
        **event_payload(user_id, question_id="old", node_id="pl_01_01"),
        database_path=database_path,
        created_at="2026-08-20T08:00:00+00:00",
    )
    create_answer_event(
        **event_payload(
            user_id,
            question_id="middle",
            question_type="fill",
            node_id="st_01_01",
            module="集合论",
            is_correct=False,
        ),
        database_path=database_path,
        created_at="2026-08-21T08:00:00+00:00",
    )
    create_answer_event(
        **event_payload(user_id, question_id="new", node_id="pl_02_02"),
        database_path=database_path,
        created_at="2026-08-22T08:00:00+00:00",
    )

    first_page = client.get(
        "/api/learning/events", params={"user_id": user_id, "limit": 2}
    )
    second_page = client.get(
        "/api/learning/events", params={"user_id": user_id, "limit": 2, "offset": 2}
    )
    filtered_type = client.get(
        "/api/learning/events",
        params={"user_id": user_id, "question_type": "fill"},
    )
    filtered_node = client.get(
        "/api/learning/events",
        params={"user_id": user_id, "node_id": "pl_01_01"},
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert [item["question_id"] for item in first_page.json()["events"]] == [
        "new",
        "middle",
    ]
    assert [item["question_id"] for item in second_page.json()["events"]] == ["old"]
    assert filtered_type.json()["events"][0]["question_id"] == "middle"
    assert filtered_node.json()["events"][0]["question_id"] == "old"


def test_answer_events_schema_and_indexes_are_additive(tmp_path):
    database_path = tmp_path / "migration.db"
    init_database(database_path)
    with connection_scope(database_path) as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(answer_events)")
        }
        indexes = {
            row["name"] for row in connection.execute("PRAGMA index_list(answer_events)")
        }
    assert {
        "id",
        "user_id",
        "question_id",
        "question_type",
        "module",
        "node_id",
        "is_correct",
        "duration_ms",
        "answer_text",
        "created_at",
    } <= columns
    assert {
        "idx_answer_events_user_id",
        "idx_answer_events_node_id",
        "idx_answer_events_created_at",
        "idx_answer_events_user_created_at",
    } <= indexes


def test_ability_profile_uses_real_node_denominator_and_50_30_20_weights(tmp_path):
    database_path = tmp_path / "profile.db"
    user_id = create_user("画像学生", database_path=database_path)
    with connection_scope(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO node_mastery (
                user_id, node_id, level, correct_count, total_count, last_practice_time
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (user_id, "pl_01_01", 3, 4, 5, None),
                (user_id, "pl_01_02", 4, 5, 5, None),
                (user_id, "pl_02_02", 2, 2, 5, None),
                (user_id, "pl_03_08", 2, 1, 4, None),
            ],
        )
    for index in range(12):
        create_answer_event(
            user_id=user_id,
            question_id=f"q{index}",
            question_type="single",
            module="命题逻辑",
            node_id="pl_02_02",
            is_correct=index < 9,
            duration_ms=1000,
            answer_text="A",
            database_path=database_path,
        )

    profile = get_ability_profile(user_id, database_path)
    proposition = next(item for item in profile.modules if item.module == "命题逻辑")
    expected_mastery = 3 / MODULE_NODE_TOTALS["命题逻辑"]
    expected_score = 100 * (0.5 * expected_mastery + 0.3 * 0.75 + 0.2 * 1.0)

    assert PRACTICE_TARGET == 10
    assert proposition.mastery_ratio == round(expected_mastery, 4)
    assert proposition.accuracy == 0.75
    assert proposition.practice_score == 1.0
    assert proposition.score == round(expected_score, 2)
    assert proposition.level == "及格"
    assert profile.overall_score == round(proposition.score / 6, 2)
    assert profile.weak_nodes[0].node_id == "pl_03_08"
    assert profile.weak_nodes[0].reason == "掌握等级较低且正确率不足"


@pytest.mark.parametrize(
    ("score", "expected"),
    [(85, "优秀"), (84.99, "良好"), (70, "良好"), (69.99, "及格"), (50, "及格"), (49.99, "薄弱")],
)
def test_ability_level_boundaries(score, expected):
    assert calculate_ability_level(score) == expected


def test_empty_ability_profile_is_stable(tmp_path):
    database_path = tmp_path / "empty.db"
    user_id = create_user("空画像学生", database_path=database_path)
    profile = get_ability_profile(user_id, database_path)
    assert profile.overall_score == 0
    assert profile.level == "未评估"
    assert len(profile.modules) == 6
    assert all(item.score == 0 for item in profile.modules)
    assert all(item.level == "未评估" for item in profile.modules)
    assert profile.weak_nodes == []
    assert profile.trend == []


def test_consecutive_self_practice_promotes_mastery_and_refreshes_profile(
    learning_client,
):
    client, _, user_id = learning_client
    initial = client.get(
        "/api/learning/ability-profile", params={"user_id": user_id}
    ).json()
    assert initial["level"] == "未评估"

    expected_levels = [1, 2, 3]
    for index, correct in enumerate([False, True, True], start=1):
        response = client.post(
            "/api/learning/events",
            json=event_payload(
                user_id,
                question_id=f"practice-{index}",
                is_correct=correct,
            ),
        )
        assert response.status_code == 200
        report = client.get("/api/learning/report", params={"user_id": user_id})
        assert report.status_code == 200
        assert report.json()["node_mastery"][0]["level"] == expected_levels[index - 1]

    profile = client.get(
        "/api/learning/ability-profile", params={"user_id": user_id}
    )
    assert profile.status_code == 200
    proposition = next(
        item for item in profile.json()["modules"] if item["module"] == "命题逻辑"
    )
    assert proposition["mastery_ratio"] == round(1 / 15, 4)
    assert proposition["accuracy"] == round(2 / 3, 4)
    assert proposition["practice_score"] == 0.3
    assert proposition["level"] != "未评估"


def test_trend_is_daily_event_count_and_accuracy(tmp_path):
    database_path = tmp_path / "trend.db"
    user_id = create_user("趋势学生", database_path=database_path)
    for question_id, result, timestamp in [
        ("d1-correct", True, "2026-08-20T08:00:00+00:00"),
        ("d1-wrong", False, "2026-08-20T09:00:00+00:00"),
        ("d2-pending", None, "2026-08-21T08:00:00+00:00"),
    ]:
        create_answer_event(
            user_id=user_id,
            question_id=question_id,
            question_type="proof" if result is None else "single",
            module="命题逻辑",
            node_id="pl_01_01",
            is_correct=result,
            duration_ms=None,
            answer_text="answer",
            database_path=database_path,
            created_at=timestamp,
        )
    trend = get_ability_profile(user_id, database_path).trend
    assert trend[0].date == "2026-08-20"
    assert trend[0].practice_count == 2
    assert trend[0].graded_count == 2
    assert trend[0].accuracy == 0.5
    assert trend[1].practice_count == 1
    assert trend[1].graded_count == 0
    assert trend[1].accuracy is None


def test_exam_submit_records_events_once_and_mastery_once(tmp_path, monkeypatch):
    database_path = tmp_path / "exam-events.db"
    teacher_id = create_user("考试教师", "teacher", database_path=database_path)
    student_id = create_user("考试学生", database_path=database_path)
    class_info = create_class(teacher_id, "事件考试班", database_path)
    join_class(student_id, class_info.invite_code, database_path)
    monkeypatch.setattr(
        "backend.management.exam_service.recommend_exam_questions",
        lambda node_ids, count: [
            {
                "node_id": "pl_03_01",
                "type": "选择题",
                "content": "客观题",
                "answer": "A",
            },
            {
                "node_id": "pl_02_02",
                "type": "证明题",
                "content": "待批阅题",
                "answer": None,
            },
        ][:count],
    )
    exam = generate_exam(
        teacher_id,
        class_info.class_id,
        "事件考试",
        ["pl_03_01", "pl_02_02"],
        2,
        database_path,
    )
    submitted_answers = [
        SubmittedAnswer(question_id=exam.questions[0].question_id, answer="A"),
        SubmittedAnswer(question_id=exam.questions[1].question_id, answer="证明过程"),
    ]
    submit_exam(
        exam.exam_id,
        student_id,
        submitted_answers,
        database_path,
    )

    with pytest.raises(ConflictError):
        submit_exam(exam.exam_id, student_id, submitted_answers, database_path)

    events = get_answer_events(student_id, database_path=database_path)
    with connection_scope(database_path) as connection:
        mastery = connection.execute(
            "SELECT * FROM node_mastery WHERE user_id = ?", (student_id,)
        ).fetchall()
    assert events.total == 2
    assert all(event.question_type == "exam" for event in events.events)
    by_node = {event.node_id: event for event in events.events}
    assert by_node["pl_03_01"].is_correct is True
    assert by_node["pl_02_02"].is_correct is None
    assert len(mastery) == 1
    assert mastery[0]["node_id"] == "pl_03_01"
    assert mastery[0]["total_count"] == 1
