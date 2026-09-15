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
    username TEXT UNIQUE,
    password_hash TEXT,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    class_id INTEGER,
    -- 教师注册后需超级管理员审批才能使用教师功能。三个状态而不是一个布尔值：
    -- 被拒的人要能看到「申请未通过」，否则会反复找管理员。
    -- DEFAULT 'approved' 就是「存量教师全部已批准」，不需要任何回填 UPDATE。
    teacher_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (teacher_status IN ('pending', 'approved', 'rejected')),
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

CREATE TABLE IF NOT EXISTS answer_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    question_type TEXT NOT NULL
        CHECK (question_type IN ('single', 'fill', 'calc', 'proof', 'exam')),
    module TEXT NOT NULL,
    node_id TEXT NOT NULL,
    is_correct INTEGER CHECK (is_correct IN (0, 1) OR is_correct IS NULL),
    duration_ms INTEGER CHECK (duration_ms >= 0 OR duration_ms IS NULL),
    answer_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    total_score REAL NOT NULL CHECK (total_score >= 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'closed')),
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS exam_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    question_type TEXT NOT NULL,
    content TEXT NOT NULL,
    answer TEXT,
    score REAL NOT NULL CHECK (score >= 0),
    sort_order INTEGER NOT NULL,
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    UNIQUE (exam_id, sort_order)
);

CREATE TABLE IF NOT EXISTS exam_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    total_score REAL NOT NULL DEFAULT 0 CHECK (total_score >= 0),
    status TEXT NOT NULL CHECK (status IN ('graded', 'pending_review')),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (exam_id, user_id)
);

CREATE TABLE IF NOT EXISTS exam_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    student_answer TEXT NOT NULL DEFAULT '',
    is_correct INTEGER CHECK (is_correct IN (0, 1) OR is_correct IS NULL),
    score REAL NOT NULL DEFAULT 0 CHECK (score >= 0),
    review_status TEXT NOT NULL CHECK (review_status IN ('graded', 'pending_review')),
    FOREIGN KEY (submission_id) REFERENCES exam_submissions(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES exam_questions(id) ON DELETE CASCADE,
    UNIQUE (submission_id, question_id)
);

CREATE TABLE IF NOT EXISTS share_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (requester_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK (requester_id != target_user_id)
);

CREATE TABLE IF NOT EXISTS grading_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT,
    question_type TEXT NOT NULL DEFAULT 'direct',
    question TEXT NOT NULL,
    student_answer TEXT NOT NULL,
    reference_answer TEXT NOT NULL,
    knowledge_points TEXT NOT NULL CHECK (json_valid(knowledge_points)),
    grading_guides TEXT NOT NULL CHECK (json_valid(grading_guides)),
    dimension_scores TEXT NOT NULL CHECK (json_valid(dimension_scores)),
    total_score REAL NOT NULL CHECK (total_score BETWEEN 0 AND 100),
    error_types TEXT NOT NULL CHECK (json_valid(error_types)),
    evidence TEXT NOT NULL CHECK (json_valid(evidence)),
    feedback TEXT NOT NULL,
    analysis_json TEXT NOT NULL CHECK (json_valid(analysis_json)),
    scoring_json TEXT NOT NULL CHECK (json_valid(scoring_json)),
    review_json TEXT NOT NULL CHECK (json_valid(review_json)),
    prompt_version TEXT NOT NULL,
    llm_provider TEXT NOT NULL,
    llm_model TEXT NOT NULL,
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    analysis_attempts INTEGER NOT NULL CHECK (analysis_attempts BETWEEN 1 AND 2),
    scoring_attempts INTEGER NOT NULL CHECK (scoring_attempts BETWEEN 1 AND 2),
    review_attempts INTEGER NOT NULL CHECK (review_attempts BETWEEN 1 AND 2),
    needs_manual_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_manual_review IN (0, 1)),
    review_reasons TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(review_reasons)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_path_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    path_id TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    data_quality TEXT NOT NULL CHECK (json_valid(data_quality)),
    diagnosis TEXT NOT NULL CHECK (json_valid(diagnosis)),
    stages TEXT NOT NULL CHECK (json_valid(stages)),
    ai_notes TEXT NOT NULL CHECK (json_valid(ai_notes)),
    source_summary TEXT NOT NULL CHECK (json_valid(source_summary)),
    status TEXT NOT NULL,
    fallback_reason TEXT,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, version)
);
CREATE INDEX IF NOT EXISTS idx_users_class_id ON users(class_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_node_mastery_user_id ON node_mastery(user_id);
CREATE INDEX IF NOT EXISTS idx_answer_events_user_id ON answer_events(user_id);
CREATE INDEX IF NOT EXISTS idx_answer_events_node_id ON answer_events(node_id);
CREATE INDEX IF NOT EXISTS idx_answer_events_created_at ON answer_events(created_at);
CREATE INDEX IF NOT EXISTS idx_answer_events_user_created_at
    ON answer_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_exams_class_id ON exams(class_id);
CREATE INDEX IF NOT EXISTS idx_exam_questions_exam_id ON exam_questions(exam_id);
CREATE INDEX IF NOT EXISTS idx_exam_submissions_exam_id ON exam_submissions(exam_id);
CREATE INDEX IF NOT EXISTS idx_exam_answers_submission_id ON exam_answers(submission_id);
CREATE INDEX IF NOT EXISTS idx_share_requests_target ON share_requests(target_user_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_share_requests_unique_pending
    ON share_requests(requester_id, target_user_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_grading_results_question_id
    ON grading_results(question_id);
CREATE INDEX IF NOT EXISTS idx_grading_results_created_at
    ON grading_results(created_at);
CREATE INDEX IF NOT EXISTS idx_learning_path_snapshots_user_version
    ON learning_path_snapshots(user_id, version);
"""


def _migrate_users_auth_columns(connection: sqlite3.Connection) -> None:
    """Add nullable authentication columns to databases created by older versions."""

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "username" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "password_hash" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique
        ON users(username) WHERE username IS NOT NULL
        """
    )


def _migrate_users_teacher_status(connection: sqlite3.Connection) -> None:
    """给旧库的 users 表补上 teacher_status（教师审批状态）。

    DEFAULT 'approved' 让存量教师一次性全部视为已批准，不需要回填 UPDATE，
    因此线上现有的教师账号（含演示号与指导老师的号）不受影响。

    多进程/热重载启动时可能有两个进程同时 ALTER，后到的那个必然抛
    `duplicate column name` —— 那是正常竞态，吞掉即可（同 _migrate_users_auth_columns 的
    PRAGMA 守卫也挡不掉这种时序）。
    """

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "teacher_status" in columns:
        return
    try:
        connection.execute(
            """
            ALTER TABLE users ADD COLUMN teacher_status TEXT NOT NULL DEFAULT 'approved'
                CHECK (teacher_status IN ('pending', 'approved', 'rejected'))
            """
        )
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _migrate_grading_result_columns(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(grading_results)").fetchall()}
    if "question_type" not in columns:
        connection.execute("ALTER TABLE grading_results ADD COLUMN question_type TEXT NOT NULL DEFAULT 'direct'")
    if "needs_manual_review" not in columns:
        connection.execute("ALTER TABLE grading_results ADD COLUMN needs_manual_review INTEGER NOT NULL DEFAULT 0")
    if "review_reasons" not in columns:
        connection.execute("ALTER TABLE grading_results ADD COLUMN review_reasons TEXT NOT NULL DEFAULT '[]'")

# 建表语句是幂等的，但每一次 init_database() 都要重开连接、重解析整份 SCHEMA_SQL
# （31 条 DDL）再跑三次迁移探测。班级学情会按学生逐个取报告，每个报告又各自 init 一次，
# 32 人的班就是 32 遍同样的建表检查 —— 实测这占了单份报告的 4 成耗时。
# 文件没被动过就跳过：_SCHEMA_READY[解析后路径] 存建完之后的文件指纹。
_SCHEMA_READY: dict[str, tuple[int, int]] = {}


def _schema_fingerprint(database_path: str | Path | None) -> tuple[str, int, int] | None:
    """Return ``(path, mtime_ns, size)`` for this database, or None if it can't be cached.

    The fingerprint is what makes the memo below safe: tests point
    ``LEARNING_DB_PATH`` at a fresh path per case, and a file that is deleted and
    recreated comes back with a different ``(mtime_ns, size)``, so its schema is
    rebuilt rather than assumed.
    """

    path = Path(database_path) if database_path is not None else get_database_path()
    if str(path) == ":memory:":
        # 每次 connect 都是一个全新的空库，没有东西可记。
        return None
    try:
        resolved = path.resolve()
        stat = resolved.stat()
    except OSError:
        # 还没建出来（首次 init 就是这种情况），不缓存。
        return None
    return str(resolved), stat.st_mtime_ns, stat.st_size


def init_database(database_path: str | Path | None = None) -> None:
    """Create tables and apply additive migrations without rebuilding existing data."""

    fingerprint = _schema_fingerprint(database_path)
    if fingerprint is not None and _SCHEMA_READY.get(fingerprint[0]) == fingerprint[1:]:
        return

    with connection_scope(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        _migrate_users_auth_columns(connection)
        _migrate_users_teacher_status(connection)
        _migrate_grading_result_columns(connection)

    # 建表本身会改文件，所以只记建完之后的指纹。
    fingerprint = _schema_fingerprint(database_path)
    if fingerprint is not None:
        _SCHEMA_READY[fingerprint[0]] = fingerprint[1:]

