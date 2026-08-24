from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from backend.grading.models import DIMENSION_LIMITS


@dataclass(frozen=True)
class ReliabilityDecision:
    needs_manual_review: bool
    reasons: list[str]


def evaluate_reliability(
    *,
    dimension_scores: Mapping[str, float],
    error_types: Sequence[str],
    evidence: Sequence[Mapping],
) -> ReliabilityDecision:
    """Check explainability invariants without changing the model's judgment."""
    reasons: list[str] = []
    evidence_dimensions = {
        item.get("dimension") for item in evidence if isinstance(item, Mapping)
    }
    for dimension, maximum in DIMENSION_LIMITS.items():
        if dimension_scores[dimension] < maximum and dimension not in evidence_dimensions:
            reasons.append(f"missing_evidence:{dimension}")

    if (
        "conclusion_error" in error_types
        and dimension_scores["conclusion_correctness"]
        == DIMENSION_LIMITS["conclusion_correctness"]
    ):
        reasons.append("conflict:conclusion_error_full_conclusion_score")
    if (
        "notation_error" in error_types
        and dimension_scores["expression_notation"]
        == DIMENSION_LIMITS["expression_notation"]
    ):
        reasons.append("conflict:notation_error_full_notation_score")

    return ReliabilityDecision(bool(reasons), reasons)
