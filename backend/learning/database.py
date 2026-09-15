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


def _enable_wal(connection: sqlite3.Connection) -> None:
    """让读不再被写阻塞 —— 前提是这个库文件所在的文件系统支持 WAL。

    默认的 rollback journal 模式下读和写互相排斥，于是一条 1.9 KB 的读请求会被
    并发的写事务（答题、聊天）挡住，线上实测同一个接口因此在 0.10 秒和 1.53 秒之间
    来回跳。WAL 让读写在同一个库上并行，这个抖动就没了。

    journal_mode 是**库文件自身的持久属性**，写一次就一直有效；这里每条连接都设一次，
    是为了让从旧备份恢复回来的库自动补上 —— 已经是 WAL 时这是个空操作，不需要写锁。

    失败时（只读介质、网络盘、恰有写者持锁）SQLite 会抛 OperationalError 或原样返回
    旧模式，**两种都不该让请求失败**：最差就是退回原来的行为。

    ⚠️ synchronous=NORMAL 只在确实切成 WAL 之后才设。rollback journal 模式下用 NORMAL
    是有丢库风险的，所以这个 if 是安全线，不是风格问题。
    """

    try:
        row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
    except sqlite3.OperationalError:
        return
    if row is not None and str(row[0]).lower() == "wal":
        connection.execute("PRAGMA synchronous = NORMAL")


def get_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys and named rows enabled."""

    path = Path(database_path) if database_path is not None else get_database_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(path), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    _enable_wal(connection)
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

# 建表语句本身是幂等的，但重跑的代价不幂等：31 条 DDL 加三次迁移探测，每条都要写事务，
# 在 rollback journal 下还会和答题、聊天的写入互斥。
#
# 上一版拿 `(路径, mtime_ns, size)` 当判据 —— 问题是**任何**一次写库都会改 mtime，
# 线上等于永远不命中，32 人的班就是 32 遍同样的建表检查（实测这是「整个应用都慢」的
# 公共来源，不只班级页）。改用 SQLite 自带的、随库文件持久存在的 PRAGMA user_version：
# 只有标记落后才重跑 DDL，和「有没有人写过库」彻底解耦，也和进程是否重启无关。
#
# ⚠️ 代价：标记一旦写上，之后即使表被人为删掉也不会再重建（老的 mtime 方案会在下次
#    写入时自愈）。真遇到这种情况，把它按回去再重启即可：
#        python -c "import sqlite3;sqlite3.connect('data/learning.db').execute('PRAGMA user_version = 0')"
#    改动 SCHEMA_SQL 或任一 _migrate_* 时，必须把 SCHEMA_VERSION 加一。
SCHEMA_VERSION = 1


def _apply_schema(connection: sqlite3.Connection) -> None:
    """跑一遍建表与三个增量迁移（幂等，可重复执行）。"""

    connection.executescript(SCHEMA_SQL)
    _migrate_users_auth_columns(connection)
    _migrate_users_teacher_status(connection)
    _migrate_grading_result_columns(connection)


def ensure_schema(connection: sqlite3.Connection) -> None:
    """在一个已经打开的连接上保证 schema 是最新的。

    稳态开销 = 一次 `PRAGMA user_version` 读（微秒级），不再重跑 31 条 DDL。
    `:memory:` 无需特判：新内存库的 user_version 永远是 0，自然走建表那条路。
    从更旧的库文件恢复回来的库版本号更低，会自己升上来；更高的库则不动（比较用 >=，
    不做降级）。
    """

    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version >= SCHEMA_VERSION:
        return
    _apply_schema(connection)
    # PRAGMA 不吃参数占位符；SCHEMA_VERSION 是本模块的整数常量，不是外部输入。
    connection.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")


def init_database(database_path: str | Path | None = None) -> None:
    """Create tables and apply additive migrations without rebuilding existing data."""

    with connection_scope(database_path) as connection:
        ensure_schema(connection)

