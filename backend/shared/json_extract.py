"""Helpers for extracting a JSON object from model output."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(content: Any) -> dict[str, Any]:
    """Return the first valid JSON object embedded in a model response."""
    if isinstance(content, list):
        content = "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty response")

    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
    candidates = [fenced.group(1).strip()] if fenced else [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError("no JSON object found in response")
