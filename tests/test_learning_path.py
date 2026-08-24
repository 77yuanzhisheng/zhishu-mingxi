"""Personalized learning path tests."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.learning.database import connection_scope, init_database
from backend.learning.router import router as learning_router
from backend.learning.service import create_answer_event, create_user, update_mastery


def build_client(tmp_path, monkeypatch):
    database_path = tmp_path / "path.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    user_id = create_user("path student", database_path=database_path)
    app = FastAPI()
    app.include_router(learning_router)
    return TestClient(app), database_path, user_id


def flatten_nodes(payload):
    return [node for stage in payload["stages"] for node in stage["nodes"]]


def test_no_data_returns_default_path_and_persists_snapshot(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)

    response = client.get("/api/learning/path", params={"user_id": user_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == user_id
    assert payload["version"] == 1
    assert payload["data_quality"]["status"] == "insufficient_data"
    assert payload["diagnosis"]["discrete_math_only"] is True
    assert payload["stages"]
    assert all(node["node_id"].split("_")[0] in {"pl", "fl", "st", "mi", "rel", "gt"} for node in flatten_nodes(payload))
    with connection_scope(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM learning_path_snapshots WHERE user_id = ?", (user_id,)).fetchone()["count"]
    assert count == 1


def test_practice_errors_prioritize_weak_node_and_dependencies(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)
    create_answer_event(user_id=user_id, question_id="g1", question_type="proof", module="graph", node_id="gt_01_01", is_correct=False, duration_ms=1000, answer_text="wrong", database_path=database_path)
    create_answer_event(user_id=user_id, question_id="g2", question_type="proof", module="graph", node_id="gt_01_01", is_correct=False, duration_ms=1000, answer_text="wrong", database_path=database_path)
    create_answer_event(user_id=user_id, question_id="r1", question_type="calc", module="relation", node_id="rel_01_01", is_correct=False, duration_ms=1000, answer_text="wrong", database_path=database_path)
    update_mastery(user_id, "gt_01_01", False, database_path)
    update_mastery(user_id, "rel_01_01", False, database_path)

    response = client.post("/api/learning/path/refresh", json={"user_id": user_id, "force": True})

    assert response.status_code == 200
    nodes = flatten_nodes(response.json())
    node_ids = [node["node_id"] for node in nodes]
    assert "gt_01_01" in node_ids
    assert "rel_01_01" in node_ids
    assert node_ids.index("rel_01_01") < node_ids.index("gt_01_01")
    graph = next(node for node in nodes if node["node_id"] == "gt_01_01")
    assert graph["evidence"]["practice"]["wrong_count"] == 2
    assert graph["priority"] >= 50


def test_qa_node_ids_override_keyword_inference(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)
    init_database(database_path)
    with connection_scope(database_path) as connection:
        session_id = connection.execute("INSERT INTO sessions (user_id, start_time) VALUES (?, ?)", (user_id, "2026-08-23T00:00:00+00:00")).lastrowid
        connection.execute(
            "INSERT INTO messages (session_id, role, content, node_ids, timestamp) VALUES (?, ?, ?, ?, ?)",
            (session_id, "user", "I am confused by graph paths and trees", json.dumps(["pl_02_02"]), "2026-08-23T00:01:00+00:00"),
        )

    response = client.get("/api/learning/path", params={"user_id": user_id})

    assert response.status_code == 200
    node_ids = [node["node_id"] for node in flatten_nodes(response.json())]
    assert "pl_02_02" in node_ids
    assert "gt_keyword" not in node_ids


def test_ai_failure_falls_back_to_rule_path(tmp_path, monkeypatch):
    client, _, user_id = build_client(tmp_path, monkeypatch)

    def broken_notes(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr("backend.learning.path_engine.generate_ai_notes", broken_notes)
    response = client.get("/api/learning/path", params={"user_id": user_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_notes"]["status"] == "fallback"
    assert payload["stages"]


def test_refresh_versions_snapshots(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)

    first = client.get("/api/learning/path", params={"user_id": user_id})
    cached = client.post("/api/learning/path/refresh", json={"user_id": user_id, "force": False})
    second = client.post("/api/learning/path/refresh", json={"user_id": user_id, "force": True})

    assert first.status_code == 200
    assert cached.status_code == 200
    assert second.status_code == 200
    assert first.json()["version"] == 1
    assert cached.json()["version"] == 1
    assert second.json()["version"] == 2
    with connection_scope(database_path) as connection:
        versions = [row["version"] for row in connection.execute("SELECT version FROM learning_path_snapshots WHERE user_id = ? ORDER BY version", (user_id,)).fetchall()]
    assert versions == [1, 2]

def test_grading_results_use_only_user_practiced_questions(tmp_path, monkeypatch):
    client, database_path, user_id = build_client(tmp_path, monkeypatch)
    other_user = create_user("other path student", database_path=database_path)
    create_answer_event(user_id=user_id, question_id="proof-owned", question_type="proof", module="graph", node_id="gt_01_01", is_correct=True, duration_ms=1000, answer_text="ok", database_path=database_path)
    create_answer_event(user_id=other_user, question_id="proof-other", question_type="proof", module="relation", node_id="rel_01_01", is_correct=True, duration_ms=1000, answer_text="ok", database_path=database_path)
    with connection_scope(database_path) as connection:
        for question_id, kp, score in [("proof-owned", "gt_01_01", 42), ("proof-other", "rel_01_01", 20)]:
            connection.execute(
                """
                INSERT INTO grading_results (
                    question_id, question_type, question, student_answer, reference_answer,
                    knowledge_points, grading_guides, dimension_scores, total_score,
                    error_types, evidence, feedback, analysis_json, scoring_json, review_json,
                    prompt_version, llm_provider, llm_model, latency_ms,
                    analysis_attempts, scoring_attempts, review_attempts,
                    needs_manual_review, review_reasons, created_at
                ) VALUES (?, 'proof', 'q', 'a', 'r', ?, '{}', ?, ?, ?, '[]', 'fb', '{}', '{}', '{}', 'v1', 'fake', 'fake', 1, 1, 1, 1, 0, '[]', '2026-08-23T00:00:00+00:00')
                """,
                (
                    question_id,
                    json.dumps([kp]),
                    json.dumps({"conclusion_correctness": 8, "key_reasoning_steps": 10, "logical_rigor": 8, "definition_theorem_usage": 5, "expression_symbol_norm": 5}),
                    score,
                    json.dumps(["跳步"]),
                ),
            )

    response = client.post("/api/learning/path/refresh", json={"user_id": user_id, "force": True})

    assert response.status_code == 200
    payload = response.json()
    nodes = flatten_nodes(payload)
    node_ids = [node["node_id"] for node in nodes]
    assert "gt_01_01" in node_ids
    assert "rel_01_01" not in node_ids
    graph = next(node for node in nodes if node["node_id"] == "gt_01_01")
    assert graph["evidence"]["grading"]["latest_total_score"] == 42
    assert graph["stage"] == "reinforcement"
    assert graph["confidence"] >= 0.7
    assert payload["data_quality"]["source_counts"]["grading"] == 1
