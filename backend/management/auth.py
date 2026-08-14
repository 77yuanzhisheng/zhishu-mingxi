"""Shared resource lookup and authorization helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.learning.database import connection_scope
from backend.management.exceptions import PermissionDeniedError, ResourceNotFoundError


def require_user(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ResourceNotFoundError(f"用户 {user_id} 不存在")
    return row


def require_class(connection: sqlite3.Connection, class_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    if row is None:
        raise ResourceNotFoundError(f"班级 {class_id} 不存在")
    return row


def require_teacher_or_admin(user: sqlite3.Row) -> None:
    if user["role"] not in {"teacher", "admin"}:
        raise PermissionDeniedError("仅 teacher 或 admin 可执行此操作")


def require_class_manager(
    requester_id: int,
    class_id: int,
    database_path: str | Path | None = None,
) -> tuple[dict, dict]:
    with connection_scope(database_path) as connection:
        requester = require_user(connection, requester_id)
        class_row = require_class(connection, class_id)
        require_teacher_or_admin(requester)
        if requester["role"] != "admin" and class_row["teacher_id"] != requester_id:
            raise PermissionDeniedError("只有该班级老师或 admin 可以查看")
        return dict(requester), dict(class_row)
