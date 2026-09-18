from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.learning.router import router as learning_router
from backend.learning.service import create_answer_event, create_user


def build_client(tmp_path, monkeypatch):
    database_path = tmp_path / "companion.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    user_id = create_user("companion student", database_path=database_path)
    app = FastAPI()
    app.include_router(learning_router)
    return TestClient(app), database_path, user_id


def add_answer(database_path, user_id, question_id, node_id, correct, created_at):
    return create_answer_event(
        user_id=user_id,
        question_id=question_id,
        question_type="single",
        module="测试模块",
        node_id=node_id,
        is_correct=correct,
        duration_ms=60_000,
        answer_text="A",
        created_at=created_at,
        database_path=database_path,
    )


def test_empty_wrong_review_has_no_invented_items(tmp_path, monkeypatch):
    client, _, user_id = build_client(tmp_path, monkeypatch)

    response = client.get("/api/learning/companion", params={"user_id": user_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["wrong_review"]["count"] == 0
    assert payload["wrong_review"]["items"] == []
    assert "没有需要立即巩固的错题" in payload["wrong_review"]["empty_message"]


def test_wrong_review_uses_real_answer_event_nodes_and_matches_count(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)
    add_answer(database_path, user_id, "rel-wrong-1", "rel_01_01", False, "2026-09-17T08:00:00+00:00")
    add_answer(database_path, user_id, "rel-wrong-2", "rel_01_01", False, "2026-09-18T08:00:00+00:00")
    add_answer(database_path, user_id, "graph-wrong", "gt_01_01", False, "2026-09-16T08:00:00+00:00")
    add_answer(database_path, user_id, "set-correct", "st_01_01", True, "2026-09-18T09:00:00+00:00")

    payload = client.get("/api/learning/companion", params={"user_id": user_id}).json()
    review = payload["wrong_review"]

    assert review["count"] == len(review["items"]) == 2
    assert review["total_wrong_answers"] == 3
    assert [item["node_id"] for item in review["items"]] == ["rel_01_01", "gt_01_01"]
    assert review["items"][0]["wrong_count"] == 2
    assert review["items"][0]["recent_error_at"].startswith("2026-09-18")
    assert "st_01_01" not in {item["node_id"] for item in review["items"]}


def test_three_errors_on_one_node_count_as_one_review_item(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)
    for index in range(3):
        add_answer(
            database_path,
            user_id,
            f"relation-wrong-{index}",
            "rel_01_01",
            False,
            f"2026-09-18T0{index + 1}:00:00+00:00",
        )

    payload = client.get("/api/learning/companion", params={"user_id": user_id}).json()
    review = payload["wrong_review"]

    assert review["count"] == len(review["items"]) == 1
    assert review["items"][0]["node_id"] == "rel_01_01"
    assert review["items"][0]["wrong_count"] == 3


def test_today_plan_uses_path_and_real_question_availability(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)
    add_answer(database_path, user_id, "rel-wrong", "rel_01_01", False, "2026-09-18T08:00:00+00:00")
    monkeypatch.setattr(
        "backend.practice.router.count_practice_questions_by_node",
        lambda: {"rel_01_01": 2},
    )

    payload = client.get("/api/learning/companion", params={"user_id": user_id}).json()
    plan = payload["today_plan"]

    assert plan["node_id"] == "rel_01_01"
    assert plan["exercise_count"] == 2
    assert plan["available_question_count"] == 2
    assert plan["target_accuracy"] == 0.8
    assert plan["path_position"] == 1
    assert plan["available"] is True


def test_duration_is_calculated_by_fixed_rule(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)
    add_answer(database_path, user_id, "rel-wrong-1", "rel_01_01", False, "2026-09-17T08:00:00+00:00")
    add_answer(database_path, user_id, "rel-wrong-2", "rel_01_01", False, "2026-09-18T08:00:00+00:00")
    monkeypatch.setattr(
        "backend.practice.router.count_practice_questions_by_node",
        lambda: {"rel_01_01": 3},
    )

    first = client.get("/api/learning/companion", params={"user_id": user_id}).json()
    second = client.get("/api/learning/companion", params={"user_id": user_id}).json()

    expected = {
        "total_minutes": 30,
        "review_minutes": 10,
        "practice_minutes": 15,
        "summary_minutes": 5,
        "min_minutes": 15,
        "max_minutes": 60,
    }
    assert first["duration_advice"] == expected
    assert second["duration_advice"] == expected


def test_no_available_exercise_does_not_invent_practice_minutes(tmp_path, monkeypatch):
    client, _, user_id = build_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "backend.practice.router.count_practice_questions_by_node",
        lambda: {},
    )

    payload = client.get("/api/learning/companion", params={"user_id": user_id}).json()
    duration = payload["duration_advice"]

    assert payload["today_plan"]["exercise_count"] == 0
    assert payload["today_plan"]["available"] is False
    assert duration["review_minutes"] == 0
    assert duration["practice_minutes"] == 0
    assert duration["summary_minutes"] == 5
    assert duration["total_minutes"] == 5


def test_path_explanation_failure_keeps_structured_plan_available(tmp_path, monkeypatch):
    client, _, user_id = build_client(tmp_path, monkeypatch)

    def broken_notes(*args, **kwargs):
        raise RuntimeError("agent unavailable")

    monkeypatch.setattr("backend.learning.path_engine.generate_ai_notes", broken_notes)
    response = client.get("/api/learning/companion", params={"user_id": user_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["today_plan"]["node_id"]
    assert payload["today_plan"]["exercise_count"] >= 0
    assert payload["source"]["learning_profile"] is True


def test_empty_learning_data_returns_initial_plan_without_error(tmp_path, monkeypatch):
    client, _, user_id = build_client(tmp_path, monkeypatch)

    payload = client.get("/api/learning/companion", params={"user_id": user_id}).json()

    assert payload["today_plan"]["status"] == "未评估"
    assert "学情数据较少" in payload["today_plan"]["reason"]
    assert payload["duration_advice"]["total_minutes"] >= 15
    assert payload["wrong_review"]["count"] == 0
