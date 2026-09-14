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
    """服务层的教师门 —— 与 auth/dependencies.py:require_teacher 是同一道门的两把锁。

    端点上的 Depends(require_teacher) 是主锁；这里是第二把，防的是「绕过端点直接调
    服务函数」的路径（service 层拿到的常常是数据库行，不是 AuthUser，所以必须自己判一次）。

    用 `"teacher_status" in user.keys()` 而不是直接取键：旧库若还没跑迁移，
    直接取会 IndexError → 500，而这里的语义应该是「那就不拦」（= 迁移前的既有行为）。
    """
    if user["role"] not in {"teacher", "admin"}:
        raise PermissionDeniedError("仅 teacher 或 admin 可执行此操作")
    if user["role"] == "teacher" and "teacher_status" in user.keys():
        if user["teacher_status"] == "pending":
            raise PermissionDeniedError("教师账号待管理员审批，审批通过后才能使用教师功能")
        if user["teacher_status"] == "rejected":
            raise PermissionDeniedError("教师账号申请未通过审批，无法使用教师功能")


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
