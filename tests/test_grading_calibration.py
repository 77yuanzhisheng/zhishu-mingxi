from __future__ import annotations

import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.grading.calibration import (
    HumanLabelInput,
    adjudicate_label,
    build_calibration_report,
    store_human_label,
)
from backend.grading.calibration_router import router
from backend.learning.database import connection_scope, init_database


def label(result_id=1, rater_id="r1", score=80):
    return HumanLabelInput(
        result_id=result_id, rater_id=rater_id, rubric_version="v1",
        total_score=score,
        dimension_scores={"conclusion_correctness": 16, "key_reasoning_steps": 28, "logical_rigor": 20, "definition_theorem_usage": 8, "expression_notation": 8},
        error_types=[], reason="independent review",
    )

def seed(db):
    init_database(db)
    with connection_scope(db) as c:
        c.execute("INSERT INTO grading_results (question_id, question_type, question, student_answer, reference_answer, knowledge_points, grading_guides, dimension_scores, total_score, error_types, evidence, feedback, analysis_json, scoring_json, review_json, prompt_version, llm_provider, llm_model, latency_ms, analysis_attempts, scoring_attempts, review_attempts, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))", ("q1", "proof", "q", "a", "r", "[]", "{}", json.dumps({"conclusion_correctness":20,"key_reasoning_steps":35,"logical_rigor":25,"definition_theorem_usage":10,"expression_notation":10}), 100, "[]", "[]", "ok", "{}", "{}", "{}", "v1", "test", "m", 1, 1, 1, 1))

def test_labels_are_unique_and_adjudication_requires_two_raters(tmp_path):
    db=tmp_path/'g.db'; seed(db)
    store_human_label(db, label())
    with pytest.raises(ValueError, match='duplicate'):
        store_human_label(db, label())
    with pytest.raises(ValueError, match='two independent'):
        adjudicate_label(db, 1, "arb", label(score=80))
    store_human_label(db, label(rater_id="r2", score=75))
    row=adjudicate_label(db, 1, "arb", label(score=78))
    assert row["status"] == "adjudicated"

def test_report_is_unavailable_without_type_specific_threshold(tmp_path):
    db=tmp_path/'g.db'; seed(db)
    store_human_label(db, label())
    report=build_calibration_report(db, question_type="proof", minimum_samples=2)
    assert report["status"] == "needs_calibration"
    assert report["sample_size"] == 1


def test_report_uses_adjudicated_gold_and_excludes_unadjudicated_samples(tmp_path):
    db = tmp_path / "g.db"
    seed(db)
    store_human_label(db, label(score=60))
    store_human_label(db, label(rater_id="r2", score=70))
    adjudicate_label(db, 1, "arb", label(score=90))
    report = build_calibration_report(db, question_type="proof", minimum_samples=1)
    assert report["gold_standard_source"] == "adjudicated"
    assert report["adjudicated_gold_count"] == 1
    assert report["score_mae"] == 10.0


def test_report_distinguishes_single_and_pending_double_reviews(tmp_path):
    db = tmp_path / "g.db"
    seed(db)
    store_human_label(db, label(score=80))
    report = build_calibration_report(db, question_type="proof", minimum_samples=1)
    assert report["status"] == "needs_calibration"
    assert report["gold_standard_sample_size"] == 0
    assert report["single_rater_count"] == 1
    assert report["dual_rater_pending_adjudication_count"] == 0


def test_report_requires_quality_thresholds_after_enough_gold_samples(tmp_path):
    db = tmp_path / "g.db"
    seed(db)
    for index in range(2, 22):
        with connection_scope(db) as c:
            c.execute("INSERT INTO grading_results (question_id, question_type, question, student_answer, reference_answer, knowledge_points, grading_guides, dimension_scores, total_score, error_types, evidence, feedback, analysis_json, scoring_json, review_json, prompt_version, llm_provider, llm_model, latency_ms, analysis_attempts, scoring_attempts, review_attempts, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))", (f"q{index}", "proof", "q", "a", "r", "[]", "{}", json.dumps({"conclusion_correctness":20,"key_reasoning_steps":35,"logical_rigor":25,"definition_theorem_usage":10,"expression_notation":10}), 100, "[]", "[]", "ok", "{}", "{}", "{}", "v1", "test", "m", 1, 1, 1, 1))
        store_human_label(db, label(result_id=index, rater_id="r1", score=0))
        store_human_label(db, label(result_id=index, rater_id="r2", score=0))
        adjudicate_label(db, index, "arb", label(result_id=index, score=0))
    report = build_calibration_report(db, question_type="proof", minimum_samples=20)
    assert report["status"] == "evaluated_not_accepted"
    assert report["release"]["eligible"] is False


def test_calibration_routes_store_labels_adjudicate_and_report(tmp_path, monkeypatch):
    db = tmp_path / "g.db"
    seed(db)
    monkeypatch.setattr("backend.grading.calibration_router.get_database_path", lambda: db)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    payload = {
        "rater_id": "teacher-a",
        "rubric_version": "v1",
        "total_score": 80,
        "dimension_scores": {
            "conclusion_correctness": 16,
            "key_reasoning_steps": 28,
            "logical_rigor": 20,
            "definition_theorem_usage": 8,
            "expression_notation": 8,
        },
        "error_types": [],
        "reason": "Independent teacher review.",
    }

    first = client.post("/api/grading/results/1/human-labels", json=payload)
    assert first.status_code == 201
    assert first.json()["result_id"] == 1

    payload["rater_id"] = "teacher-b"
    second = client.post("/api/grading/results/1/human-labels", json=payload)
    assert second.status_code == 201

    adjudication = client.post(
        "/api/grading/results/1/adjudication",
        json={**payload, "adjudicator_id": "lead-teacher", "total_score": 90},
    )
    assert adjudication.status_code == 201
    assert adjudication.json()["status"] == "adjudicated"

    report = client.get("/api/grading/calibration/report?question_type=proof&minimum_samples=1")
    assert report.status_code == 200
    assert report.json()["gold_standard_sample_size"] == 1


def test_calibration_routes_reject_invalid_rubric_and_insufficient_raters(tmp_path, monkeypatch):
    db = tmp_path / "g.db"
    seed(db)
    monkeypatch.setattr("backend.grading.calibration_router.get_database_path", lambda: db)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    payload = {
        "rater_id": "teacher-a",
        "rubric_version": "v1",
        "total_score": 80,
        "dimension_scores": {
            "conclusion_correctness": 25,
            "key_reasoning_steps": 28,
            "logical_rigor": 20,
            "definition_theorem_usage": 8,
            "expression_notation": 8,
        },
        "error_types": [],
        "reason": "Independent teacher review.",
    }
    invalid = client.post("/api/grading/results/1/human-labels", json=payload)
    assert invalid.status_code == 422

    payload["dimension_scores"]["conclusion_correctness"] = 16
    assert client.post("/api/grading/results/1/human-labels", json=payload).status_code == 201
    insufficient = client.post(
        "/api/grading/results/1/adjudication",
        json={**payload, "adjudicator_id": "lead-teacher"},
    )
    assert insufficient.status_code == 409


def test_calibration_routes_reject_non_positive_result_ids(tmp_path, monkeypatch):
    db = tmp_path / "g.db"
    seed(db)
    monkeypatch.setattr("backend.grading.calibration_router.get_database_path", lambda: db)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    payload = {
        "rater_id": "teacher-a",
        "total_score": 80,
        "dimension_scores": {
            "conclusion_correctness": 16,
            "key_reasoning_steps": 28,
            "logical_rigor": 20,
            "definition_theorem_usage": 8,
            "expression_notation": 8,
        },
        "reason": "Independent teacher review.",
    }
    assert client.post("/api/grading/results/0/human-labels", json=payload).status_code == 422
    assert client.post(
        "/api/grading/results/-1/adjudication",
        json={**payload, "adjudicator_id": "lead-teacher"},
    ).status_code == 422