from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_REQUIRED_FIELDS = (
    "known",
    "definitions_or_theorems",
    "reasoning_steps",
    "conclusion",
)


@dataclass(frozen=True)
class ProofValidation:
    """Auditable result of checking a structured proof payload."""

    valid: bool
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def validate_proof_structure(payload: Mapping[str, Any]) -> ProofValidation:
    """Check the four required proof sections and return audit metadata.

    This function validates structure only; it does not judge mathematical
    correctness or replace a model's proof.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    missing: list[str] = []
    warnings: list[str] = []
    for field in _REQUIRED_FIELDS:
        if field not in payload or not _is_non_empty(payload[field]):
            missing.append(field)
            if field in payload:
                warnings.append(f"{field} must be non-empty")

    # Preserve a predictable audit warning for unsupported extra sections while
    # accepting them for forward compatibility.
    extra = sorted(set(payload) - set(_REQUIRED_FIELDS))
    if extra:
        warnings.append("unsupported fields ignored: " + ", ".join(extra))

    return ProofValidation(
        valid=not missing,
        missing_fields=tuple(missing),
        warnings=tuple(warnings),
    )
