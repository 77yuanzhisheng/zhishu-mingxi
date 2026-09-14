"""教师账号审批：列出教师、批准 / 拒绝。

背景（指导老师 2026-09-14 提的需求）：原先注册时自选「教师」就立刻拥有教师功能，
冒充成本为零。现在教师注册后 `users.teacher_status='pending'`，必须由超级管理员批准。

把门在端点上（`Depends(require_admin)`）；本模块只管数据，不重复判角色。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.learning.database import connection_scope, init_database
from backend.management.exceptions import (
    ManagementError,
    PermissionDeniedError,
    ResourceNotFoundError,
)

VALID_STATUSES = ("pending", "approved", "rejected")

_TEACHER_SELECT = """
    SELECT u.id AS user_id,
           u.username,
           u.name,
           u.role,
           u.teacher_status AS status,
           (SELECT COUNT(*) FROM classes AS c WHERE c.teacher_id = u.id) AS class_count
    FROM users AS u
"""


def _is_super_admin(username: str | None) -> bool:
    """函数内导入：backend.auth.service 会拉起 learning.database → learning.router，
    存在真实的导入环（详见 backend/auth/dependencies.py 文件头的说明），模块级导入会踩雷。
    """
    from backend.auth.service import is_configured_super_admin

    return is_configured_super_admin(username)


def list_teachers(
    status: str = "pending",
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """列出教师账号。

    - `status="all"` 返回全部，否则只返回该状态的。
    - 没有 `created_at` 列，用 `id DESC` 当「最新在前」：users.id 是 AUTOINCREMENT，越大越新。
    - 带上 `class_count`：管理员在点「拒绝」前能看出这个人已经建了几个班
      （审批**不回收**已有班级关系，见交付说明里的「已知遗留」）。
    - **超管不出现在列表里**：他被 .env 点名后 role 已提升为 admin，不是待审批的教师；
      而且他要真是以 teacher 身份注册的，库里会留着 pending —— 列出来只会让人误点拒绝。
    """
    if status != "all" and status not in VALID_STATUSES:
        raise ManagementError("status 只允许 " + " / ".join((*VALID_STATUSES, "all")))

    init_database(database_path)
    # 不把 status 拼进 SQL：用 `? IS NULL OR` 让 None 表示「全部」。
    filter_value = None if status == "all" else status
    with connection_scope(database_path) as connection:
        rows = connection.execute(
            _TEACHER_SELECT
            + """
            WHERE u.role = 'teacher'
              AND (? IS NULL OR u.teacher_status = ?)
            ORDER BY u.id DESC
            """,
            (filter_value, filter_value),
        ).fetchall()

    teachers = [dict(row) for row in rows]
    return [t for t in teachers if not _is_super_admin(t["username"])]


def count_pending(database_path: str | Path | None = None) -> int:
    """待审批数量 —— 给前端导航项上的角标用。"""
    init_database(database_path)
    with connection_scope(database_path) as connection:
        rows = connection.execute(
            "SELECT username FROM users WHERE role = 'teacher' AND teacher_status = 'pending'"
        ).fetchall()
    return sum(1 for row in rows if not _is_super_admin(row["username"]))


def set_teacher_status(
    user_id: int,
    status: str,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """把某个教师设为 approved / rejected，返回更新后的账号信息。

    幂等：已经是目标状态就直接返回，不报错 —— 前端多点一次不该看到红字。
    """
    if status not in VALID_STATUSES:
        raise ManagementError("status 只允许 " + " / ".join(VALID_STATUSES))

    init_database(database_path)
    with connection_scope(database_path) as connection:
        row = connection.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"用户 {user_id} 不存在")
        if row["role"] != "teacher":
            raise PermissionDeniedError(
                f"用户 {user_id} 不是教师账号（role={row['role']}）"
            )
        if _is_super_admin(row["username"]):
            raise PermissionDeniedError("不能审批超级管理员账号")

        connection.execute(
            "UPDATE users SET teacher_status = ? WHERE id = ?", (status, user_id)
        )
        connection.commit()
        updated = connection.execute(
            _TEACHER_SELECT + " WHERE u.id = ?", (user_id,)
        ).fetchone()

    return dict(updated)
