# Grading Reliability Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable double-rater human-label workflow and deterministic reliability controls for the long-answer grading engine.

**Architecture:** Keep model grading in `backend/grading/service.py`, then run a pure deterministic guardrail over the reviewed result before persistence. Store each independent human label and a separate adjudicated label in SQLite. Generate reports from persisted model results and adjudicated labels, split by `proof` and `calc`; do not report accuracy when the gold sample is incomplete.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, SQLite JSON columns, pytest.

---

## File Structure

- Modify: `backend/grading/models.py` - expose reliability state on grade responses and validate human-label payloads.
- Modify: `backend/grading/service.py` - derive question type, apply guardrails, and persist the review status.
- Create: `backend/grading/guardrails.py` - pure rules for evidence coverage and error/score consistency.
- Create: `backend/grading/calibration.py` - database operations, double-rater comparison, adjudication, and report aggregation.
- Create: `backend/grading/calibration_router.py` - protected-by-contract calibration API endpoints.
- Modify: `backend/grading/router.py` - make existing response model expose the guarded grading result only.
- Modify: `backend/grading/__init__.py` - export only package-level public types if current package convention needs it.
- Modify: `backend/api.py` - register calibration router.
- Modify: `backend/learning/database.py` - create calibration tables and migrate added grading-result columns for existing databases.
- Create: `scripts/build_grading_gold_set.py` - deterministic sampler for balanced proof/calc calibration candidates.
- Create: `tests/test_grading_guardrails.py` - unit tests for every guardrail and non-fabrication behavior.
- Create: `tests/test_grading_calibration.py` - persistence, adjudication, report, and threshold tests.
- Modify: `tests/test_grading.py` - assert guarded response and persisted metadata.
- Modify: `docs/superpowers/specs/2026-08-22-grading-engine-design.md` - record the approved calibration design in Chinese.

### Task 1: Define failing guardrail tests

**Files:**
- Create: `tests/test_grading_guardrails.py`
- Create: `backend/grading/guardrails.py`

- [ ] **Step 1: Write the failing tests for valid output, evidence coverage, and contradictions.**

```python
from backend.grading.guardrails import evaluate_reliability


def test_marks_missing_evidence_for_a_deducted_dimension():
    result = evaluate_reliability(
        dimension_scores={
            "conclusion_correctness": 20,
            "key_reasoning_steps": 30,
            "logical_rigor": 25,
            "definition_theorem_usage": 10,
            "expression_notation": 10,
        },
        error_types=[],
        evidence=[],
    )
    assert result.needs_manual_review is True
    assert result.reasons == ["missing_evidence:key_reasoning_steps"]
```

Add focused tests for `conclusion_error` with a 20-point conclusion score, `notation_error` with a 10-point notation score, a valid fully-supported deduction, and a low score with no declared error type. The final case must remain valid: rules must not invent errors.

- [ ] **Step 2: Run the new test module and confirm collection fails.**

Run: `python -m pytest tests/test_grading_guardrails.py -q`

Expected: FAIL because `backend.grading.guardrails` does not exist.

- [ ] **Step 3: Implement pure reliability rules.**

```python
@dataclass(frozen=True)
class ReliabilityDecision:
    needs_manual_review: bool
    reasons: list[str]


def evaluate_reliability(*, dimension_scores, error_types, evidence):
    reasons = []
    for dimension, maximum in DIMENSION_LIMITS.items():
        if dimension_scores[dimension] < maximum and not any(
            item["dimension"] == dimension for item in evidence
        ):
            reasons.append(f"missing_evidence:{dimension}")
    if "conclusion_error" in error_types and dimension_scores["conclusion_correctness"] == 20:
        reasons.append("conflict:conclusion_error_full_conclusion_score")
    if "notation_error" in error_types and dimension_scores["expression_notation"] == 10:
        reasons.append("conflict:notation_error_full_notation_score")
    return ReliabilityDecision(bool(reasons), reasons)
```

Do not treat an empty `error_types` list as a failure. The existing LLM validators remain responsible for schema and score-range validation.

- [ ] **Step 4: Run guardrail tests.**

Run: `python -m pytest tests/test_grading_guardrails.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the isolated change.**

```bash
git add backend/grading/guardrails.py tests/test_grading_guardrails.py
git commit -m "feat: add grading reliability guardrails"
```

### Task 2: Expose and persist guarded grading state

**Files:**
- Modify: `backend/grading/models.py`
- Modify: `backend/grading/service.py`
- Modify: `backend/learning/database.py`
- Modify: `tests/test_grading.py`

- [ ] **Step 1: Write failing service tests for guardrail response fields and persistence.**

```python
assert result.needs_manual_review is True
assert result.review_reasons == ["missing_evidence:key_reasoning_steps"]
assert row["needs_manual_review"] == 1
assert json.loads(row["review_reasons"]) == result.review_reasons
```

Use the existing `ScriptedLLM` fixture and return valid review JSON with an intentionally uncovered deduction. Also add a valid-evidence test that asserts `False` and an empty list.

- [ ] **Step 2: Run the targeted tests and confirm they fail.**

Run: `python -m pytest tests/test_grading.py -q`

Expected: FAIL because response fields and columns do not exist.

- [ ] **Step 3: Add fields, safe migrations, and service integration.**

Add to `GradeResponse`:

```python
needs_manual_review: bool
review_reasons: list[str] = Field(default_factory=list)
```

Add nullable-safe migrations after `connection.executescript(SCHEMA_SQL)`:

```python
def _migrate_grading_result_columns(connection):
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(grading_results)")}
    if "question_type" not in columns:
        connection.execute("ALTER TABLE grading_results ADD COLUMN question_type TEXT")
    if "needs_manual_review" not in columns:
        connection.execute("ALTER TABLE grading_results ADD COLUMN needs_manual_review INTEGER NOT NULL DEFAULT 0")
    if "review_reasons" not in columns:
        connection.execute("ALTER TABLE grading_results ADD COLUMN review_reasons TEXT NOT NULL DEFAULT '[]'")
```

Resolve `question_type` in `GradingContext` from team member 2 question metadata, use `"direct"` for direct requests, call `evaluate_reliability()` after the review stage, and persist both new fields. Do not reject a model response only because it needs manual review.

- [ ] **Step 4: Run grading tests and a schema migration regression.**

Run: `python -m pytest tests/test_grading.py tests/test_grading_guardrails.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the isolated change.**

```bash
git add backend/grading/models.py backend/grading/service.py backend/grading/knowledge.py backend/learning/database.py tests/test_grading.py
git commit -m "feat: persist grading review state"
```

### Task 3: Add double-rater labels and adjudication

**Files:**
- Create: `backend/grading/calibration.py`
- Modify: `backend/learning/database.py`
- Create: `tests/test_grading_calibration.py`

- [ ] **Step 1: Write failing tests for independent labels and an adjudicated gold label.**

```python
first = save_human_label(result_id=1, rater_id="rater-a", rubric=RUBRIC, error_types=[])
second = save_human_label(result_id=1, rater_id="rater-b", rubric=RUBRIC, error_types=[])
gold = adjudicate_label(result_id=1, adjudicator_id="lead", rubric=RUBRIC, error_types=[], rationale="Reviewed agreement.")
assert gold.result_id == 1
assert list_human_labels(1) == [first, second]
```

Add rejection tests for duplicate labels by the same rater, unknown grading result IDs, a one-rater adjudication attempt, and a non-finite rubric value.

- [ ] **Step 2: Run calibration tests and confirm they fail.**

Run: `python -m pytest tests/test_grading_calibration.py -q`

Expected: FAIL because calibration services and schema are missing.

- [ ] **Step 3: Implement the calibration data model and storage.**

Create tables named `grading_human_labels` and `grading_adjudications`. Store dimension scores and error types as JSON, plus `rater_id`, `rubric_version`, `created_at`, and `rationale`. Put the unique constraint on `(result_id, rater_id, rubric_version)`; store exactly one current adjudication per `(result_id, rubric_version)`.

Reuse the strict rubric validation from `backend.grading.evaluation` rather than duplicating score range logic. `adjudicate_label()` must check that two or more independent labels exist before inserting the gold label.

- [ ] **Step 4: Run calibration persistence tests.**

Run: `python -m pytest tests/test_grading_calibration.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the isolated change.**

```bash
git add backend/grading/calibration.py backend/learning/database.py tests/test_grading_calibration.py
git commit -m "feat: store double-rater grading labels"
```

### Task 4: Build a truthful calibration report

**Files:**
- Modify: `backend/grading/evaluation.py`
- Modify: `backend/grading/calibration.py`
- Modify: `tests/test_grading_evaluation.py`
- Modify: `tests/test_grading_calibration.py`

- [ ] **Step 1: Write failing report tests with proof/calc partitions.**

```python
report = build_calibration_report(database_path)
assert report["available"] is True
assert report["by_question_type"]["proof"]["sample_size"] == 20
assert report["release"]["eligible"] is True
assert report["release"]["status"] == "calibrated"
```

Add a test with fewer than 20 proof samples and a test with a proof MAE above 10. Both must return `eligible=False`, and neither may call the result accurate. Add a test that no adjudicated labels returns `available=False` with an explanatory reason.
