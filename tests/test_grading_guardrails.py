from backend.grading.guardrails import evaluate_reliability


def _scores(**overrides):
    values = {
        "conclusion_correctness": 20,
        "key_reasoning_steps": 35,
        "logical_rigor": 25,
        "definition_theorem_usage": 10,
        "expression_notation": 10,
    }
    values.update(overrides)
    return values


def test_marks_missing_evidence_for_a_deducted_dimension():
    result = evaluate_reliability(
        dimension_scores=_scores(key_reasoning_steps=30), error_types=[], evidence=[]
    )
    assert result.needs_manual_review is True
    assert result.reasons == ["missing_evidence:key_reasoning_steps"]


def test_marks_conclusion_error_with_full_conclusion_score_as_conflict():
    result = evaluate_reliability(
        dimension_scores=_scores(),
        error_types=["conclusion_error"],
        evidence=[{"dimension": "conclusion_correctness", "claim": "wrong conclusion"}],
    )
    assert result.needs_manual_review is True
    assert "conflict:conclusion_error_full_conclusion_score" in result.reasons


def test_marks_notation_error_with_full_notation_score_as_conflict():
    result = evaluate_reliability(
        dimension_scores=_scores(),
        error_types=["notation_error"],
        evidence=[{"dimension": "expression_notation", "claim": "bad notation"}],
    )
    assert result.needs_manual_review is True
    assert "conflict:notation_error_full_notation_score" in result.reasons


def test_accepts_fully_supported_deduction():
    result = evaluate_reliability(
        dimension_scores=_scores(
            key_reasoning_steps=30,
            logical_rigor=20,
            definition_theorem_usage=8,
        ),
        error_types=["jump_step", "theorem_misuse"],
        evidence=[
            {"dimension": "key_reasoning_steps", "claim": "step 2 is omitted"},
            {"dimension": "logical_rigor", "claim": "the inference is not justified"},
            {"dimension": "definition_theorem_usage", "claim": "the theorem conditions are not met"},
        ],
    )
    assert result.needs_manual_review is False
    assert result.reasons == []


def test_does_not_invent_error_type_for_an_unsupported_low_score():
    result = evaluate_reliability(
        dimension_scores=_scores(logical_rigor=18),
        error_types=[],
        evidence=[{"dimension": "logical_rigor", "claim": "the explanation is incomplete"}],
    )
    assert result.needs_manual_review is False
    assert result.reasons == []
