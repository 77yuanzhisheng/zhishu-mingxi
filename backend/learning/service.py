"""Business logic for mastery updates and learning reports."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.learning.database import connection_scope, init_database
from backend.learning.models import (
    AbilityModule,
    AbilityProfile,
    AbilityRadarItem,
    AbilityTrendItem,
    AbilityWeakNode,
    AnswerEvent,
    AnswerEventsResponse,
    AnswerQuestionType,
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

MODULES = tuple(MODULE_PREFIXES.values())

# Leaf-item counts from the repository's current /kb/knowledge-graph contract.
# Keeping the snapshot here avoids coupling learning analytics to KB initialization.
MODULE_NODE_TOTALS = {
    "命题逻辑": 15,
    "谓词逻辑": 10,
    "集合论": 12,
    "数学归纳法": 8,
    "关系": 17,
    "图论": 17,
}

PRACTICE_TARGET = 10


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


def _normalized_module(node_id: str, supplied_module: str) -> str:
    """Use the centralized node-prefix mapping whenever the prefix is known."""

    mapped = module_for_node(node_id)
    return mapped if mapped != "其他" else supplied_module.strip()


def _row_to_event(row: sqlite3.Row) -> AnswerEvent:
    return AnswerEvent(
        event_id=row["id"],
        user_id=row["user_id"],
        question_id=row["question_id"],
        question_type=row["question_type"],
        module=row["module"],
        node_id=row["node_id"],
        is_correct=bool(row["is_correct"]) if row["is_correct"] is not None else None,
        duration_ms=row["duration_ms"],
        answer_text=row["answer_text"],
        created_at=row["created_at"],
    )


def insert_answer_event(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    question_id: str | int,
    question_type: AnswerQuestionType,
    module: str,
    node_id: str,
    is_correct: bool | None,
    duration_ms: int | None,
    answer_text: str,
    created_at: datetime | str | None = None,
    validate_user: bool = True,
) -> AnswerEvent:
    """Insert one event using an existing transaction, without changing mastery."""

    if validate_user and connection.execute(
        "SELECT 1 FROM users WHERE id = ?", (user_id,)
    ).fetchone() is None:
        raise UserNotFoundError(f"用户 {user_id} 不存在")
    if question_type not in {"single", "fill", "calc", "proof", "exam"}:
        raise ValueError("不支持的 question_type")
    if duration_ms is not None and duration_ms < 0:
        raise ValueError("duration_ms 不能小于 0")

    clean_node_id = node_id.strip()
    timestamp = created_at or datetime.now(timezone.utc)
    created_at_text = timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
    cursor = connection.execute(
        """
        INSERT INTO answer_events (
            user_id, question_id, question_type, module, node_id,
            is_correct, duration_ms, answer_text, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            str(question_id).strip(),
            question_type,
            _normalized_module(clean_node_id, module),
            clean_node_id,
            int(is_correct) if is_correct is not None else None,
            duration_ms,
            answer_text,
            created_at_text,
        ),
    )
    row = connection.execute(
        "SELECT * FROM answer_events WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return _row_to_event(row)


def create_answer_event(
    *,
    user_id: int,
    question_id: str,
    question_type: AnswerQuestionType,
    module: str,
    node_id: str,
    is_correct: bool | None,
    duration_ms: int | None,
    answer_text: str,
    database_path: str | Path | None = None,
    created_at: datetime | str | None = None,
) -> AnswerEvent:
    """Persist a standalone answer event; deliberately does not update mastery."""

    init_database(database_path)
    with connection_scope(database_path) as connection:
        return insert_answer_event(
            connection,
            user_id=user_id,
            question_id=question_id,
            question_type=question_type,
            module=module,
            node_id=node_id,
            is_correct=is_correct,
            duration_ms=duration_ms,
            answer_text=answer_text,
            created_at=created_at,
        )


def get_answer_events(
    user_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    question_type: AnswerQuestionType | None = None,
    node_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    database_path: str | Path | None = None,
) -> AnswerEventsResponse:
    """Return a filtered, reverse-chronological answer-event timeline."""

    if not 1 <= limit <= 200:
        raise ValueError("limit 必须在 1 到 200 之间")
    if offset < 0:
        raise ValueError("offset 不能小于 0")
    if start_time and end_time and start_time > end_time:
        raise ValueError("start_time 不能晚于 end_time")
    init_database(database_path)
    filters = ["user_id = ?"]
    parameters: list[object] = [user_id]
    if question_type:
        filters.append("question_type = ?")
        parameters.append(question_type)
    if node_id:
        filters.append("node_id = ?")
        parameters.append(node_id.strip())
    if start_time:
        filters.append("created_at >= ?")
        parameters.append(start_time.isoformat())
    if end_time:
        filters.append("created_at <= ?")
        parameters.append(end_time.isoformat())
    where_clause = " AND ".join(filters)

    with connection_scope(database_path) as connection:
        if connection.execute(
            "SELECT 1 FROM users WHERE id = ?", (user_id,)
        ).fetchone() is None:
            raise UserNotFoundError(f"用户 {user_id} 不存在")
        total = connection.execute(
            f"SELECT COUNT(*) AS count FROM answer_events WHERE {where_clause}",
            parameters,
        ).fetchone()["count"]
        rows = connection.execute(
            f"""
            SELECT * FROM answer_events
            WHERE {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*parameters, limit, offset],
        ).fetchall()
    return AnswerEventsResponse(
        events=[_row_to_event(row) for row in rows], total=total, user_id=user_id
    )


def calculate_ability_level(score: float) -> str:
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 50:
        return "及格"
    return "薄弱"


def get_ability_profile(
    user_id: int,
    database_path: str | Path | None = None,
) -> AbilityProfile:
    """Build an equal-weight six-module profile from mastery and real events."""

    init_database(database_path)
    with connection_scope(database_path) as connection:
        if connection.execute(
            "SELECT 1 FROM users WHERE id = ?", (user_id,)
        ).fetchone() is None:
            raise UserNotFoundError(f"用户 {user_id} 不存在")
        mastery_rows = connection.execute(
            "SELECT * FROM node_mastery WHERE user_id = ? ORDER BY node_id", (user_id,)
        ).fetchall()
        event_rows = connection.execute(
            "SELECT module, node_id, is_correct FROM answer_events WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        trend_rows = connection.execute(
            """
            SELECT substr(created_at, 1, 10) AS event_date,
                   COUNT(*) AS practice_count,
                   SUM(CASE WHEN is_correct IS NOT NULL THEN 1 ELSE 0 END) AS graded_count,
                   SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
            FROM answer_events
            WHERE user_id = ?
            GROUP BY substr(created_at, 1, 10)
            ORDER BY event_date
            """,
            (user_id,),
        ).fetchall()

    mastery_by_module: dict[str, list[sqlite3.Row]] = {module: [] for module in MODULES}
    for row in mastery_rows:
        module = module_for_node(row["node_id"])
        if module in mastery_by_module:
            mastery_by_module[module].append(row)

    events_by_module: dict[str, list[sqlite3.Row]] = {module: [] for module in MODULES}
    for row in event_rows:
        module = _normalized_module(row["node_id"], row["module"])
        if module in events_by_module:
            events_by_module[module].append(row)

    modules: list[AbilityModule] = []
    for module in MODULES:
        module_mastery = mastery_by_module[module]
        mastered_nodes = len({row["node_id"] for row in module_mastery if row["level"] >= 3})
        mastery_ratio = min(1.0, mastered_nodes / MODULE_NODE_TOTALS[module])

        module_events = events_by_module[module]
        graded_events = [row for row in module_events if row["is_correct"] is not None]
        if graded_events:
            accuracy = sum(row["is_correct"] == 1 for row in graded_events) / len(graded_events)
        else:
            total_count = sum(row["total_count"] for row in module_mastery)
            correct_count = sum(row["correct_count"] for row in module_mastery)
            accuracy = correct_count / total_count if total_count else 0.0

        if module_events:
            practice_count = len(module_events)
        else:
            practice_count = sum(row["total_count"] for row in module_mastery)
        practice_score = min(1.0, practice_count / PRACTICE_TARGET)
        score = 100 * (0.5 * mastery_ratio + 0.3 * accuracy + 0.2 * practice_score)
        modules.append(
            AbilityModule(
                module=module,
                score=round(score, 2),
                mastery_ratio=round(mastery_ratio, 4),
                accuracy=round(accuracy, 4),
                practice_score=round(practice_score, 4),
            )
        )

    weak_nodes = []
    for row in mastery_rows:
        if row["level"] <= 2:
            accuracy = row["correct_count"] / row["total_count"] if row["total_count"] else 0.0
            reason = (
                "掌握等级较低且正确率不足"
                if accuracy < 0.6
                else "掌握等级较低"
            )
            weak_nodes.append(
                AbilityWeakNode(
                    node_id=row["node_id"],
                    module=module_for_node(row["node_id"]),
                    level=row["level"],
                    accuracy=round(accuracy, 4),
                    reason=reason,
                )
            )

    trend = []
    for row in trend_rows:
        graded_count = row["graded_count"]
        trend.append(
            AbilityTrendItem(
                date=row["event_date"],
                practice_count=row["practice_count"],
                graded_count=graded_count,
                correct_count=row["correct_count"],
                accuracy=(
                    round(row["correct_count"] / graded_count, 4)
                    if graded_count
                    else None
                ),
            )
        )

    overall_score = round(sum(item.score for item in modules) / len(modules), 2)
    return AbilityProfile(
        user_id=user_id,
        overall_score=overall_score,
        level=calculate_ability_level(overall_score),
        modules=modules,
        radar_data=[
            AbilityRadarItem(module=item.module, value=item.score) for item in modules
        ],
        weak_nodes=weak_nodes,
        trend=trend,
        calculation_note=(
            "六模块等权平均；模块分=掌握节点占比×50%+正确率×30%+"
            f"练习量×20%，练习量=min(1, 次数/{PRACTICE_TARGET})"
        ),
    )


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
