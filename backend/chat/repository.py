"""SQLite repository for sessions, messages and durable context summaries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.chat.exceptions import (
    ChatSessionAccessError,
    ChatSessionNotFoundError,
    ChatUserNotFoundError,
)
from backend.learning.database import connection_scope, init_database


class ChatRepository:
    def __init__(self, database_path: str | Path | None = None):
        self.database_path = database_path
        init_database(database_path)

    def create_session(self, user_id: int) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with connection_scope(self.database_path) as connection:
            if connection.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
                raise ChatUserNotFoundError(f"用户 {user_id} 不存在")
            cursor = connection.execute(
                "INSERT INTO sessions (user_id, start_time) VALUES (?, ?)",
                (user_id, now),
            )
            return int(cursor.lastrowid)

    def validate_session(self, session_id: int, user_id: int) -> None:
        with connection_scope(self.database_path) as connection:
            row = connection.execute(
                "SELECT user_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise ChatSessionNotFoundError(f"会话 {session_id} 不存在")
        if row["user_id"] != user_id:
            raise ChatSessionAccessError("该会话不属于当前用户")

    def add_message(
        self,
        session_id: int,
        role: str,
        content: str,
        node_ids: list[str],
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with connection_scope(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages (session_id, role, content, node_ids, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, json.dumps(node_ids, ensure_ascii=False), now),
            )
            return int(cursor.lastrowid)

    def get_messages(self, session_id: int) -> list[dict[str, Any]]:
        with connection_scope(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "node_ids": json.loads(row["node_ids"]),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def get_summary(self, session_id: int) -> dict[str, Any] | None:
        with connection_scope(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM session_summaries WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_summary(self, session_id: int, content: str, through_message_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connection_scope(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO session_summaries (
                    session_id, content, summarized_through_message_id, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    content = excluded.content,
                    summarized_through_message_id = excluded.summarized_through_message_id,
                    updated_at = excluded.updated_at
                """,
                (session_id, content, through_message_id, now),
            )
