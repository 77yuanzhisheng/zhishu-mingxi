"""Project readiness audit for the Spark training and competition handoff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _curriculum_counts(root: Path) -> dict[str, int]:
    data = _load_json(root / "data" / "teacher_kg.json")
    chapters = data.get("chapters", [])
    sections = [section for chapter in chapters for section in chapter.get("sections", [])]
    knowledge_points = [kp for section in sections for kp in section.get("kps", [])]
    key_points = [point for kp in knowledge_points for point in kp.get("points", [])]
    return {
        "chapters": len(chapters),
        "sections": len(sections),
        "knowledge_points": len(knowledge_points),
        "key_points": len(key_points),
    }


def _question_bank(root: Path) -> dict[str, int]:
    path = next((root / "data" / "documents").glob("*????_node_id.json"))
    data = _load_json(path)
    stats = data.get("stats", {})
    questions = data.get("questions", {})
    return {
        "total": int(data.get("total", len(questions))),
        "distinct_node_ids": int(data.get("distinct_node_ids", 0)),
        "unmapped": int(stats.get("unmapped", 0)),
    }


def _finetune_stats(root: Path) -> dict[str, int | str]:
    # Canonical SFT dataset ships as 知数明析_指令集.jsonl; derived samples
    # (e.g. 队员5's teacher_questions_112.jsonl) live in the same directory but
    # must not shadow the flagship dataset in the audit.
    canonical = "知数明析_指令集.jsonl"
    candidates = sorted(
        path for path in (root / "data" / "finetune").glob("*.jsonl")
        if "triplet" not in path.stem
    )
    if not candidates:
        return {"file": "", "records": 0, "duplicates": 0}
    path = next((candidate for candidate in candidates if candidate.name == canonical), candidates[0])
    records: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            # JSON normalization makes duplicate detection independent of whitespace.
            records.append(json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True))
    return {
        "file": str(path.relative_to(root)),
        "records": len(records),
        "duplicates": len(records) - len(set(records)),
    }


def audit_project_readiness(root: str | Path) -> dict[str, Any]:
    """Return deterministic, secret-free readiness metrics for the project."""
    project_root = Path(root).resolve()
    return {
        "curriculum": _curriculum_counts(project_root),
        "question_bank": _question_bank(project_root),
        "finetune": _finetune_stats(project_root),
    }
