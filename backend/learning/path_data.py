"""Evidence loading and snapshot persistence for personalized paths."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.learning.database import connection_scope, init_database
from backend.learning.service import UserNotFoundError


def ensure_user(connection: sqlite3.Connection, user_id: int) -> None:
    if connection.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
        raise UserNotFoundError(f"用户 {user_id} 不存在")


def load_latest_snapshot(user_id: int, database_path: str | Path | None = None) -> dict[str, Any] | None:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        ensure_user(connection, user_id)
        row = connection.execute(
            """
            SELECT * FROM learning_path_snapshots
            WHERE user_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return _snapshot_row_to_response(row) if row else None


def counts_user_evidence(user_id: int, database_path: str | Path | None = None) -> dict[str, int]:
    """轻量统计当前学情证据量，用于判断快照是否过期（与 source_summary 字段对齐）。"""

    init_database(database_path)
    with connection_scope(database_path) as connection:
        ensure_user(connection, user_id)
        mastery = int(connection.execute(
            "SELECT COUNT(*) AS c FROM node_mastery WHERE user_id = ?", (user_id,)
        ).fetchone()["c"])
        events = int(connection.execute(
            "SELECT COUNT(*) AS c FROM answer_events WHERE user_id = ?", (user_id,)
        ).fetchone()["c"])
        messages = int(connection.execute(
            """
            SELECT COUNT(*) AS c FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.user_id = ? AND m.role = 'user'
            """,
            (user_id,),
        ).fetchone()["c"])
        question_ids = sorted({
            str(row["question_id"]).strip()
            for row in connection.execute(
                "SELECT DISTINCT question_id FROM answer_events WHERE user_id = ? AND question_id IS NOT NULL",
                (user_id,),
            ).fetchall()
            if str(row["question_id"]).strip()
        })
        grading = 0
        if question_ids:
            placeholders = ",".join("?" for _ in question_ids)
            grading = int(connection.execute(
                f"""
                SELECT COUNT(*) AS c FROM grading_results
                WHERE question_type = 'proof' AND question_id IN ({placeholders})
                """,
                question_ids,
            ).fetchone()["c"])
    return {
        "mastery_rows": mastery,
        "answer_events": events,
        "qa_messages": messages,
        "grading_results": grading,
    }


def load_user_evidence(user_id: int, database_path: str | Path | None = None) -> dict[str, Any]:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        ensure_user(connection, user_id)
        mastery = [dict(row) for row in connection.execute(
            "SELECT * FROM node_mastery WHERE user_id = ?", (user_id,)
        ).fetchall()]
        events = [dict(row) for row in connection.execute(
            """
            SELECT * FROM answer_events
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 500
            """,
            (user_id,),
        ).fetchall()]
        messages = [dict(row) for row in connection.execute(
            """
            SELECT m.* FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.user_id = ? AND m.role = 'user'
            ORDER BY m.timestamp DESC, m.id DESC
            LIMIT 200
            """,
            (user_id,),
        ).fetchall()]
        question_ids = sorted({str(row.get("question_id") or "").strip() for row in events if row.get("question_id")})
        grading: list[dict[str, Any]] = []
        if question_ids:
            placeholders = ",".join("?" for _ in question_ids)
            grading = [dict(row) for row in connection.execute(
                f"""
                SELECT question_id, question_type, knowledge_points, dimension_scores,
                       total_score, error_types, needs_manual_review, created_at
                FROM grading_results
                WHERE question_type = 'proof' AND question_id IN ({placeholders})
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                question_ids,
            ).fetchall()]
    for message in messages:
        try:
            message["node_ids"] = json.loads(message.get("node_ids") or "[]")
        except json.JSONDecodeError:
            message["node_ids"] = []
    for row in grading:
        for key, default in (("knowledge_points", []), ("dimension_scores", {}), ("error_types", [])):
            try:
                row[key] = json.loads(row.get(key) or json.dumps(default))
            except json.JSONDecodeError:
                row[key] = default
    return {"mastery": mastery, "events": events, "messages": messages, "grading": grading}


def next_version(user_id: int, connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM learning_path_snapshots WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row["version"])


def persist_snapshot(path: dict[str, Any], source_summary: dict[str, Any], database_path: str | Path | None = None) -> None:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        connection.execute(
            """
            INSERT INTO learning_path_snapshots (
                user_id, path_id, version, strategy, data_quality, diagnosis,
                stages, ai_notes, source_summary, status, fallback_reason, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path["user_id"],
                path["path_id"],
                path["version"],
                path["strategy"],
                json.dumps(path["data_quality"], ensure_ascii=False),
                json.dumps(path["diagnosis"], ensure_ascii=False),
                json.dumps(path["stages"], ensure_ascii=False),
                json.dumps(path["ai_notes"], ensure_ascii=False),
                json.dumps(source_summary, ensure_ascii=False),
                path["data_quality"].get("status", "ok"),
                path["ai_notes"].get("fallback_reason"),
                path["generated_at"],
            ),
        )


def _flatten_path(stages: list[dict[str, Any]]) -> list[str]:
    """从嵌套 stages 派生扁平节点列表（兜底旧快照无 path 字段时使用）。"""
    flat: list[str] = []
    for stage in stages:
        for node in stage.get("nodes", []):
            node_id = node.get("node_id")
            if node_id and node_id not in flat:
                flat.append(node_id)
    return flat


def _snapshot_row_to_response(row: sqlite3.Row) -> dict[str, Any]:
    stages = json.loads(row["stages"])
    snapshot = {
        "user_id": row["user_id"],
        "path_id": row["path_id"],
        "version": row["version"],
        "strategy": row["strategy"],
        "data_quality": json.loads(row["data_quality"]),
        "diagnosis": json.loads(row["diagnosis"]),
        "stages": stages,
        "path": _flatten_path(stages),
        "ai_notes": json.loads(row["ai_notes"]),
        "generated_at": row["generated_at"],
    }
    # source_summary 不对外返回，仅供 get_learning_path 判断快照是否过期
    try:
        snapshot["source_summary"] = json.loads(row["source_summary"])
    except (TypeError, json.JSONDecodeError):
        snapshot["source_summary"] = None
    return snapshot
