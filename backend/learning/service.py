"""Business logic for mastery updates and learning reports."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.learning.database import connection_scope, init_database
from backend.learning.models import (
    LearningReport,
    MasteryDetail,
    MasteryUpdateResponse,
    RadarModule,
)


MODULE_PREFIXES = {
    "pl": "命题逻辑",
    "fl": "谓词逻辑",
    "st": "集合论",
    "mi": "数学归纳法",
    "rel": "关系",
    "gt": "图论",
}


class UserNotFoundError(LookupError):
    """Raised when a learning operation references an unknown user."""


def calculate_level(correct_count: int, total_count: int) -> int:
    """Calculate the 0-4 mastery level from cumulative accuracy."""

    if total_count == 0:
        return 0
    accuracy = correct_count / total_count
    if accuracy < 0.30:
        return 1
    if accuracy <= 0.60:
        return 2
    if accuracy <= 0.85:
        return 3
    return 4


def module_for_node(node_id: str) -> str:
    """Map a knowledge-graph node ID to one of the six frontend modules."""

    prefix = node_id.strip().lower().split("_", maxsplit=1)[0]
    return MODULE_PREFIXES.get(prefix, "其他")


def _row_to_mastery(row: sqlite3.Row) -> MasteryDetail:
    total_count = int(row["total_count"])
    correct_count = int(row["correct_count"])
    return MasteryDetail(
        user_id=row["user_id"],
        node_id=row["node_id"],
        level=row["level"],
        correct_count=correct_count,
        total_count=total_count,
        last_practice_time=row["last_practice_time"],
        accuracy=round(correct_count / total_count, 4) if total_count else 0.0,
        module=module_for_node(row["node_id"]),
    )


def create_user(
    name: str,
    role: str = "student",
    class_id: int | None = None,
    database_path: str | Path | None = None,
) -> int:
    """Create a user for use by the later user/class API phase."""

    init_database(database_path)
    with connection_scope(database_path) as connection:
        cursor = connection.execute(
            "INSERT INTO users (name, role, class_id) VALUES (?, ?, ?)",
            (name, role, class_id),
        )
        return int(cursor.lastrowid)


def update_mastery(
    user_id: int,
    node_id: str,
    correct: bool,
    database_path: str | Path | None = None,
) -> MasteryUpdateResponse:
    """Atomically record one answer and recalculate mastery level."""

    init_database(database_path)
    clean_node_id = node_id.strip()
    now = datetime.now(timezone.utc).isoformat()

    with connection_scope(database_path) as connection:
        user = connection.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            raise UserNotFoundError(f"用户 {user_id} 不存在")

        connection.execute(
            """
            INSERT INTO node_mastery (
                user_id, node_id, level, correct_count, total_count, last_practice_time
            ) VALUES (?, ?, 0, ?, 1, ?)
            ON CONFLICT(user_id, node_id) DO UPDATE SET
                correct_count = correct_count + excluded.correct_count,
                total_count = total_count + 1,
                last_practice_time = excluded.last_practice_time
            """,
            (user_id, clean_node_id, int(correct), now),
        )
        counts = connection.execute(
            """
            SELECT correct_count, total_count
            FROM node_mastery
            WHERE user_id = ? AND node_id = ?
            """,
            (user_id, clean_node_id),
        ).fetchone()
        level = calculate_level(counts["correct_count"], counts["total_count"])
        connection.execute(
            "UPDATE node_mastery SET level = ? WHERE user_id = ? AND node_id = ?",
            (level, user_id, clean_node_id),
        )
        row = connection.execute(
            "SELECT * FROM node_mastery WHERE user_id = ? AND node_id = ?",
            (user_id, clean_node_id),
        ).fetchone()

    return MasteryUpdateResponse(message="掌握度更新成功", mastery=_row_to_mastery(row))


def get_learning_report(
    user_id: int,
    database_path: str | Path | None = None,
) -> LearningReport:
    """Return per-node mastery, weak nodes and six-module radar data."""

    init_database(database_path)
    with connection_scope(database_path) as connection:
        user = connection.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            raise UserNotFoundError(f"用户 {user_id} 不存在")
        rows = connection.execute(
            """
            SELECT * FROM node_mastery
            WHERE user_id = ?
            ORDER BY level ASC, node_id ASC
            """,
            (user_id,),
        ).fetchall()

    mastery_items = [_row_to_mastery(row) for row in rows]
    weak_nodes = [item.node_id for item in mastery_items if 0 < item.level <= 2]

    grouped_levels: dict[str, list[int]] = {name: [] for name in MODULE_PREFIXES.values()}
    for item in mastery_items:
        if item.module in grouped_levels:
            grouped_levels[item.module].append(item.level)

    radar_data = []
    for module_name, levels in grouped_levels.items():
        average_level = sum(levels) / len(levels) if levels else 0.0
        radar_data.append(
            RadarModule(
                module=module_name,
                average_level=round(average_level, 2),
                value=round(average_level / 4 * 100, 2),
                practiced_nodes=len(levels),
            )
        )

    practiced_count = len(mastery_items)
    mastered_count = sum(item.level >= 3 for item in mastery_items)
    total_answers = sum(item.total_count for item in mastery_items)
    total_correct = sum(item.correct_count for item in mastery_items)
    return LearningReport(
        user_id=user_id,
        node_mastery=mastery_items,
        weak_nodes=weak_nodes,
        radar_data=radar_data,
        summary={
            "practiced_nodes": practiced_count,
            "mastered_nodes": mastered_count,
            "weak_nodes": len(weak_nodes),
            "total_answers": total_answers,
            "overall_accuracy": round(total_correct / total_answers, 4) if total_answers else 0.0,
        },
    )
