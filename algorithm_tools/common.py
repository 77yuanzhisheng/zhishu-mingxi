from __future__ import annotations

import json
from typing import Any


def tool_response(result: Any, steps: list[str], explanation: str) -> dict[str, Any]:
    """Build the common response envelope used by every extended tool."""
    return {
        "result": result,
        "steps": steps,
        "explanation": explanation,
    }


def value_key(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("set elements and graph vertices must be JSON-compatible values") from exc


def stable_unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = value_key(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
