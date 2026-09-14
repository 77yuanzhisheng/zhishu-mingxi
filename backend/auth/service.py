"""Password hashing, JWT handling and authentication persistence."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt

from backend.auth.models import AuthResponse, AuthUser
from backend.learning.database import connection_scope, init_database


JWT_ALGORITHM = "HS256"


class AuthError(RuntimeError):
    status_code = 400


class InvalidCredentialsError(AuthError):
    status_code = 401


class UsernameConflictError(AuthError):
    status_code = 409


class AuthenticationConfigurationError(AuthError):
    status_code = 500


def _jwt_settings() -> tuple[str, int]:
    secret = os.getenv("AUTH_JWT_SECRET", "").strip()
    if not secret:
        raise AuthenticationConfigurationError("AUTH_JWT_SECRET 未配置")
    try:
        expire_minutes = int(os.getenv("AUTH_JWT_EXPIRE_MINUTES", "1440"))
    except ValueError as exc:
        raise AuthenticationConfigurationError(
            "AUTH_JWT_EXPIRE_MINUTES 必须是正整数"
        ) from exc
    if expire_minutes <= 0:
        raise AuthenticationConfigurationError("AUTH_JWT_EXPIRE_MINUTES 必须是正整数")
    return secret, expire_minutes


def _row_value(row: sqlite3.Row, key: str, default):
    """读取一个「理论上一定有、但旧库可能还没有」的列。

    init_database 已经保证迁移跑过，所以正常路径上列一定存在。这里的兜底是让
    「迁移没跑」退化成放行（也就是今天的既有行为），而不是让所有人登录直接 500。
    """
    return row[key] if key in row.keys() else default


def is_configured_super_admin(username: str | None) -> bool:
    """该用户名是否被 .env 的 SUPER_ADMIN_USERNAME 点名为超级管理员。

    ⚠️ 两个 `bool(...)` 短路都是必需的，不是防御性写法：

    裸写 `str(username or "") == configured` 时，只要部署漏配 SUPER_ADMIN_USERNAME，
    空配置就会让**所有 username 为 NULL 的行**（线上有 id=1/2/1003 这些历史数据行）
    一次性全部变成 admin。今天打不中只是因为 get_user_from_token 拒绝 NULL username，
    而这是「以后有人放开一处就立刻致命」的写法，必须用守卫 + 单测钉死。
    """
    configured = os.getenv("SUPER_ADMIN_USERNAME", "").strip()
    if not configured:
        return False
    if not username:
        return False
    return username == configured


def _user_from_row(row: sqlite3.Row) -> AuthUser:
    username = row["username"]
    is_super_admin = is_configured_super_admin(username)
    return AuthUser(
        user_id=row["id"],
        username=username,
        name=row["name"],
        # 配置点名的超管在这里被提升成 admin，于是 require_admin
        # （auth/dependencies.py）一行都不用改就生效，前端 formatRole 也会显示「管理员」。
        # 数据库里写死的 admin 仍然有效 —— 作为 .env 丢失时的后备，测试里也只能这么造。
        role="admin" if is_super_admin else row["role"],
        class_id=row["class_id"],
        teacher_status=_row_value(row, "teacher_status", "approved"),
        is_super_admin=is_super_admin,
    )


def _create_token(user_id: int) -> str:
    secret, expire_minutes = _jwt_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=expire_minutes),
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )


def register_user(
    username: str,
    password: str,
    name: str,
    role: str,
    database_path: str | Path | None = None,
) -> AuthResponse:
    if role not in {"student", "teacher"}:
        raise AuthError("role 只允许 student 或 teacher")
    _jwt_settings()
    init_database(database_path)
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    # 教师注册后是 pending：能正常登录、能当学生用，但教师端点会 403，直到超管批准。
    # 仍然直接返回 token —— 不返回的话待审批的人连"我还在等审批"都看不到。
    teacher_status = "pending" if role == "teacher" else "approved"
    try:
        with connection_scope(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash, name, role, class_id, teacher_status)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (username, password_hash, name, role, teacher_status),
            )
            user_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        if "username" in str(exc).lower():
            raise UsernameConflictError("username 已存在") from exc
        raise
    user = _user_from_row(row)
    return AuthResponse(token=_create_token(user.user_id), user=user)


def login_user(
    username: str,
    password: str,
    database_path: str | Path | None = None,
) -> AuthResponse:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None or not row["password_hash"]:
        raise InvalidCredentialsError("username 或密码错误")
    try:
        password_matches = bcrypt.checkpw(
            password.encode("utf-8"), row["password_hash"].encode("ascii")
        )
    except (ValueError, TypeError, UnicodeError):
        password_matches = False
    if not password_matches:
        raise InvalidCredentialsError("username 或密码错误")
    user = _user_from_row(row)
    return AuthResponse(token=_create_token(user.user_id), user=user)


def get_user_from_token(
    token: str,
    database_path: str | Path | None = None,
) -> AuthUser:
    secret, _ = _jwt_settings()
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidCredentialsError("token 无效或已过期") from exc

    init_database(database_path)
    with connection_scope(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None or not row["username"]:
        raise InvalidCredentialsError("token 无效或已过期")
    return _user_from_row(row)
