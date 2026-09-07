from pathlib import Path

from scripts.team5_benchmark import (
    answer_one,
    build_comparison,
    load_questions,
    parse_json_object,
    write_reports,
)


class FakeClient:
    def __init__(self, response):
        self.response = response

    def generate(self, _prompt):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _record(label, question_id, latency, score, correct, question_type="proof"):
    return {
        "id": question_id,
        "model_label": label,
        "type": question_type,
        "knowledge_point": "relation",
        "answer_ok": True,
        "correct": correct,
        "score": score,
        "latency_seconds": latency,
    }


def test_loads_complete_112_question_bank():
    questions = load_questions()
    assert len(questions) == 112
    assert sum(q["type"] == "fill" for q in questions) == 56
    assert sum(q["type"] == "calc" for q in questions) == 36
    assert sum(q["type"] == "proof" for q in questions) == 16
    assert sum(q["type"] == "app" for q in questions) == 4
    assert len({q["id"] for q in questions}) == 112


def test_parse_judge_json_accepts_fenced_response():
    parsed = parse_json_object('```json\n{"score": 90, "correct": true}\n```')
    assert parsed == {"score": 90, "correct": True}


def test_answer_one_records_fixed_judge_result():
    question = load_questions()[0]
    result = answer_one(
        question,
        "baseline",
        FakeClient("推导过程。最终答案：A"),
        FakeClient('{"score":88,"correct":true,"reason":"结论正确"}'),
    )
    assert result["answer_ok"] is True
    assert result["score"] == 88
    assert result["correct"] is True
    assert result["judge_reason"] == "结论正确"


def test_comparison_calculates_accuracy_delta_and_strict_proof_gate(tmp_path: Path):
    records = [
        _record("baseline", "p1", 35, 60, False),
        _record("baseline", "p2", 25, 85, True),
        _record("tuned", "p1", 20, 90, True),
        _record("tuned", "p2", 29, 95, True),
    ]
    comparison = build_comparison(records, speed_limit=30, required_proof_rate=1.0)
    assert comparison["delta"]["accuracy_percentage_points"] == 50.0
    assert comparison["models"]["tuned"]["proof"]["under_limit_rate"] == 1.0
    assert comparison["proof_speed_gate"]["passed"] is True

    write_reports(records, tmp_path, comparison)
    assert (tmp_path / "comparison.csv").exists()
    assert (tmp_path / "summary.json").exists()
    assert "通过" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_proof_gate_fails_when_one_question_errors():
    records = [
        _record("baseline", "p1", 10, 80, True),
        {
            "id": "p1",
            "model_label": "tuned",
            "type": "proof",
            "answer_ok": False,
            "correct": False,
            "score": 0,
            "latency_seconds": 2,
        },
    ]
    comparison = build_comparison(records)
    assert comparison["proof_speed_gate"]["passed"] is False

