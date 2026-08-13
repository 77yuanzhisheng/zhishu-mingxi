"""SQLite connection and schema management for the learning module."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "learning.db"


def get_database_path() -> Path:
    """Return the configured database path.

    ``LEARNING_DB_PATH`` can be set to ``:memory:`` or to a custom file path,
    which is especially useful for tests and deployments.
    """

    configured_path = os.getenv("LEARNING_DB_PATH")
    if configured_path:
        return Path(configured_path) if configured_path != ":memory:" else Path(":memory:")
    return DEFAULT_DATABASE_PATH


def get_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys and named rows enabled."""

    path = Path(database_path) if database_path is not None else get_database_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(path), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def connection_scope(
    database_path: str | Path | None = None,
) -> Iterator[sqlite3.Connection]:
    """Provide a connection and commit or roll back it as one transaction."""

    connection = get_connection(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    class_id INTEGER,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    teacher_id INTEGER NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    node_ids TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(node_ids) AND json_type(node_ids) = 'array'),
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_summaries (
    session_id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    summarized_through_message_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (summarized_through_message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS node_mastery (
    user_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 4),
    correct_count INTEGER NOT NULL DEFAULT 0 CHECK (correct_count >= 0),
    total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),
    last_practice_time TEXT,
    PRIMARY KEY (user_id, node_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK (correct_count <= total_count)
);

CREATE INDEX IF NOT EXISTS idx_users_class_id ON users(class_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_node_mastery_user_id ON node_mastery(user_id);
"""


def init_database(database_path: str | Path | None = None) -> None:
    """Create all learning tables and indexes if they do not exist."""

    with connection_scope(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
