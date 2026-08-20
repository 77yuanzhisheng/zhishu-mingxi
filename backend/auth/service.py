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


def _user_from_row(row: sqlite3.Row) -> AuthUser:
    return AuthUser(
        user_id=row["id"],
        username=row["username"],
        name=row["name"],
        role=row["role"],
        class_id=row["class_id"],
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
    try:
        with connection_scope(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash, name, role, class_id)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (username, password_hash, name, role),
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
