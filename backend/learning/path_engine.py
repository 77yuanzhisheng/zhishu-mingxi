"""Personalized learning path orchestration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.learning.database import connection_scope, init_database
from backend.learning.path_ai import generate_ai_notes
from backend.learning.path_data import (
    counts_user_evidence,
    load_latest_snapshot,
    load_user_evidence,
    next_version,
    persist_snapshot,
)
from backend.learning.path_models import LearningPathResponse
from backend.learning.path_scoring import build_rule_path


def get_learning_path(user_id: int, database_path: str | Path | None = None) -> LearningPathResponse:
    snapshot = load_latest_snapshot(user_id, database_path)
    if snapshot is not None:
        # 快照过期检测：学情证据量（掌握度/答题/问答/批阅）与快照生成时不一致 → 自动重算
        summary = snapshot.get("source_summary")
        if not summary or counts_user_evidence(user_id, database_path) != summary:
            return refresh_learning_path(user_id, database_path=database_path)
        return LearningPathResponse(**snapshot)
    return refresh_learning_path(user_id, database_path=database_path)


def refresh_learning_path(user_id: int, database_path: str | Path | None = None) -> LearningPathResponse:
    init_database(database_path)
    evidence = load_user_evidence(user_id, database_path)
    stages, diagnosis, data_quality = build_rule_path(evidence)
    try:
        ai_notes = generate_ai_notes(diagnosis, stages)
    except Exception as exc:  # The API must not fail because the LLM layer failed.
        ai_notes = {
            "status": "fallback",
            "summary": "AI 说明生成失败，已返回规则引擎生成的可执行学习路径。",
            "fallback_reason": str(exc),
        }
    with connection_scope(database_path) as connection:
        version = next_version(user_id, connection)
    flat_path: list[str] = []
    for stage in stages:
        for node in stage.get("nodes", []):
            node_id = node.get("node_id")
            if node_id and node_id not in flat_path:
                flat_path.append(node_id)
    path = {
        "user_id": user_id,
        "path_id": f"path-{uuid.uuid4().hex[:12]}",
        "version": version,
        "strategy": "rule_based_with_ai_explanation",
        "data_quality": data_quality,
        "diagnosis": diagnosis,
        "stages": stages,
        "path": flat_path,
        "ai_notes": ai_notes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    persist_snapshot(path, _source_summary(evidence), database_path)
    return LearningPathResponse(**path)


def _source_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "mastery_rows": len(evidence.get("mastery", [])),
        "answer_events": len(evidence.get("events", [])),
        "qa_messages": len(evidence.get("messages", [])),
        "grading_results": len(evidence.get("grading", [])),
    }
