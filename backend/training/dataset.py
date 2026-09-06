"""Utilities for preparing deterministic Spark MaaS SFT JSONL datasets."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

SYSTEM_PROMPT = (
    "你是严谨、耐心的离散数学教师。请使用规范的离散数学符号（如 ∀、∃、¬、"
    "∧、∨、→、↔、∈、⊆、∪、∩），并按照已知条件、定义或定理、关键推理步骤、结论"
    "组织证明和计算过程；不得跳过影响结论的关键推理。"
)

_WHITESPACE_RE = re.compile(r"\s+")


def _value(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return None


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def _has_value(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_non_finite(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_non_finite(item) for item in value)
    return False


def _canonical_text(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", _text(value))).strip().casefold()


def _dedupe_key(record: Mapping[str, Any]) -> str:
    question = _value(record, "instruction", "question", "q")
    answer = _value(record, "answer", "response", "a")
    payload = f"{_canonical_text(question)}\n{_canonical_text(answer)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_messages(record: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Convert a source record to Spark MaaS ``messages`` format.

    The question bank uses ``q``/``a``/``kp`` while hand-authored samples use
    ``instruction``/``answer``/``knowledge_point``. Both forms are accepted.
    """
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping")

    question = _value(record, "instruction", "question", "q")
    answer = _value(record, "answer", "response", "a")
    errors = validate_record(record)
    if errors:
        raise ValueError(f"invalid training record: {', '.join(errors)}")

    question_type = _text(_value(record, "type", "question_type", "category")) or "general"
    knowledge_point = _text(_value(record, "knowledge_point", "kp")) or "未指定"
    user_content = (
        f"题型：{question_type}\n"
        f"知识点：{knowledge_point}\n"
        f"题目：{_text(question)}"
    )

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": _text(answer)},
        ]
    }


def validate_record(record: Mapping[str, Any]) -> list[str]:
    """Return canonical validation error names for one source record."""
    if not isinstance(record, Mapping):
        return ["record"]

    errors: list[str] = []
    question = _value(record, "instruction", "question", "q")
    answer = _value(record, "answer", "response", "a")
    if not _has_value(question):
        errors.append("instruction")
    if not _has_value(answer):
        errors.append("answer")
    if _contains_non_finite(record):
        errors.append("non_finite")
    return errors


def split_records(
    records: Sequence[dict[str, Any]], seed: int = 20260903
) -> dict[str, list[dict[str, Any]]]:
    """Deduplicate and deterministically split records into train/validation/test.

    The default target is 80/10/10. For small inputs, the test split receives
    at least one example while the three returned collections stay disjoint.
    """
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError("records must contain mappings")
        key = _dedupe_key(record)
        if key not in seen:
            seen.add(key)
            unique.append(dict(record))

    shuffled = list(unique)
    random.Random(seed).shuffle(shuffled)
    total = len(shuffled)
    if total == 0:
        return {"train": [], "validation": [], "test": []}

    test_count = max(1, int(total * 0.1))
    validation_count = int(total * 0.1) if total >= 3 else 0
    if total >= 3:
        validation_count = max(1, validation_count)
    if test_count + validation_count > total:
        validation_count = max(0, total - test_count - 1)
    train_count = total - validation_count - test_count

    return {
        "train": shuffled[:train_count],
        "validation": shuffled[train_count : train_count + validation_count],
        "test": shuffled[train_count + validation_count :],
    }


def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> int:
    """Write one UTF-8 JSON object per line and reject non-finite numbers."""
    output_path = Path(path)
    lines: list[str] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise ValueError(f"record {index} must be a JSON object")
        if _contains_non_finite(record):
            raise ValueError(f"record {index} contains non-finite value")
        try:
            lines.append(json.dumps(record, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"record {index} is not valid JSON: {exc}") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)
