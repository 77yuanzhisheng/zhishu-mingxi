"""Regression guards for the cost fixes behind 「查看学情」.

These changes only ever *remove* work, so the way to keep them honest is to count
the work rather than to time it. Timings belong to the benchmark, not to a test
suite that has to pass on any machine.

第二版（2026-09-15 晚）：上一版钉住了「每个学生少算一遍」和「建表按文件指纹记忆化」，
两处都生效了，但线上班级页仍是 >20 秒 —— 因为它的**形状**没变：还是「N 个学生各跑一轮
单学生查询、各开一条连接」，而 mtime 指纹在真有人答题的库里永远不命中。这一版钉的是
两条强得多的不变量：

1. 班级页的**库操作数与班级人数无关**（连接数、语句数都不随 N 增长）；
2. 建表检查的判据是**库文件自己的 user_version**，与「有没有人写过库」彻底解耦。
"""

from __future__ import annotations

import re
import sqlite3

import backend.learning.database as database_module
from backend.learning.database import (
    SCHEMA_VERSION,
    _enable_wal,
    connection_scope,
    init_database,
)
from backend.learning.service import (
    build_learning_reports,
    create_user,
    get_learning_report,
    update_mastery,
)
from backend.management.class_service import (
    create_class,
    get_class_report,
    get_class_students,
    join_class,
)


def _class_with_students(database_path, count: int = 4, name: str = "计费班"):
    """A teacher, a class, and ``count`` students that each have some mastery."""

    teacher_id = create_user(f"{name}教师", "teacher", database_path=database_path)
    class_info = create_class(teacher_id, name, database_path)
    for index in range(count):
        student_id = create_user(
            f"{name}学生{index}", "student", database_path=database_path
        )
        join_class(student_id, class_info.invite_code, database_path)
        for node in range(3):
            update_mastery(
                student_id, f"kp_cost_{node}", node % 2 == 0, database_path
            )
    return teacher_id, class_info.class_id


def _count_db_work(monkeypatch):
    """数出这一段代码开了几条连接、跑了多少条语句。

    ``sqlite3.Connection`` 是 C 类型，打不了补丁，所以从 ``get_connection`` 这个工厂
    下手 —— ``connection_scope`` 是模块内的全局查找，所有调用方都会走到它。
    """

    opened: list[sqlite3.Connection] = []
    statements: list[str] = []
    real = database_module.get_connection

    def counting_get_connection(*args, **kwargs):
        connection = real(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        opened.append(connection)
        return connection

    monkeypatch.setattr(database_module, "get_connection", counting_get_connection)
    return opened, statements


class _RecordingConnection:
    """只记录执行过哪些 SQL 的假连接（真的 sqlite3.Connection 打不了补丁）。"""

    def __init__(self, journal_mode_row, error=None):
        self.statements: list[str] = []
        self._journal_mode_row = journal_mode_row
        self._error = error

    def execute(self, sql, *args):
        self.statements.append(sql.strip())
        if "journal_mode" in sql.lower() and self._error is not None:
            raise self._error
        return self

    def fetchone(self):
        return self._journal_mode_row


# --------------------------------------------------------------------------- #
# 班级页：库操作数不随人数增长
# --------------------------------------------------------------------------- #


def test_class_report_reuses_the_reports_it_already_built(tmp_path, monkeypatch):
    """整班只调用一次批量取数，而不是每个学生调用一次。

    ``get_class_report`` 需要 ``_student_items`` 建的那份报告。它曾经对每个学生再调
    一次 ``get_learning_report``，把老师最慢的那一屏的库开销翻倍。
    """

    database_path = tmp_path / "reuse.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    teacher_id, class_id = _class_with_students(database_path, count=4, name="复用班")

    calls: list[list[int]] = []
    real = build_learning_reports

    def counting(connection, user_ids, **kwargs):
        calls.append(sorted(int(item) for item in user_ids))
        return real(connection, user_ids, **kwargs)

    import backend.management.class_service as class_service

    monkeypatch.setattr(class_service, "build_learning_reports", counting)

    report = get_class_report(teacher_id, class_id, database_path)

    assert len(report.students) == 4
    assert len(calls) == 1, f"整班应当只批量取数一次，实际 {len(calls)} 次：{calls}"
    assert calls[0] == [item.user_id for item in report.students], (
        "一次取数必须覆盖全班学生"
    )

    # 汇总字段必须是真算出来的，不能因为复用就变成 0。
    assert report.student_count == 4
    assert report.radar_data, "雷达数据不能为空"
    assert any(item.learning_summary.total_answers for item in report.students), (
        "复用报告后 learning_summary 仍然要有真实数据"
    )


def test_class_report_db_work_does_not_grow_with_student_count(tmp_path, monkeypatch):
    """O(N) → O(1)：4 人班和 12 人班的连接数、语句数必须**相等**。

    这条比看耗时可靠得多，也是「班级页不再随人数线性变慢」的直接证据：改前是
    N+4 条连接、6N 条语句，两个规模之间必然差一大截。
    """

    database_path = tmp_path / "scale.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    teacher_id, small_class = _class_with_students(database_path, count=4, name="小班")
    big_teacher_id, big_class = _class_with_students(database_path, count=12, name="大班")

    opened, statements = _count_db_work(monkeypatch)

    get_class_report(teacher_id, small_class, database_path)
    small_work = (len(opened), len(statements))
    small_statements = list(statements)

    opened.clear()
    statements.clear()
    get_class_report(big_teacher_id, big_class, database_path)
    big_work = (len(opened), len(statements))

    assert small_work == big_work, (
        f"班级页的库操作数不该随人数变化：4 人 {small_work} vs 12 人 {big_work}"
    )
    assert small_work[0] <= 3, f"一次班级报告不该开超过 3 条连接，实际 {small_work[0]}"
    assert small_work[1] <= 24, f"一次班级报告不该跑超过 24 条语句，实际 {small_work[1]}"

    # 改前每个学生都会跑一遍 `... WHERE user_id = ?`；批量之后一句都不该剩。
    per_student = [
        sql for sql in small_statements if re.search(r"user_id\s*=\s*\?", sql, re.I)
    ]
    assert per_student == [], f"班级页里仍有按学生逐条取数的语句：{per_student}"


def test_class_students_and_report_agree(tmp_path, monkeypatch):
    """两条路径都从同一份报告派生，摘要必须一致。"""

    database_path = tmp_path / "agree.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    teacher_id, class_id = _class_with_students(database_path, count=3, name="一致班")

    students = get_class_students(teacher_id, class_id, database_path).students
    report = get_class_report(teacher_id, class_id, database_path)

    assert [item.user_id for item in students] == [item.user_id for item in report.students]
    assert [item.learning_summary for item in students] == [
        item.learning_summary for item in report.students
    ]


def test_empty_class_returns_an_empty_report(tmp_path, monkeypatch):
    """空班返回一份空报告，而不是 500。

    ``user_id IN ()`` 是**语法错误**不是空结果，所以 ``build_learning_reports`` 里那句
    空名单守卫是必须的 —— 这条测试就是钉住它。
    """

    database_path = tmp_path / "empty.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    teacher_id = create_user("空班教师", "teacher", database_path=database_path)
    class_info = create_class(teacher_id, "空班", database_path)

    with connection_scope(database_path) as connection:
        assert build_learning_reports(connection, []) == {}

    report = get_class_report(teacher_id, class_info.class_id, database_path)
    assert report.student_count == 0
    assert report.students == []
    assert report.weak_nodes == []
    assert report.overall_accuracy == 0.0
    assert len(report.radar_data) > 0, "空班也要给出五维雷达，只是全 0"


# --------------------------------------------------------------------------- #
# 批量版与单份版逐字段等价
# --------------------------------------------------------------------------- #


def _seed_rich_class(database_path, count: int = 5) -> list[int]:
    """造一批「什么都有一点」的学生，把单份报告里所有分支都点亮。

    覆盖：判对/判错/待批（``is_correct IS NULL``）、只在 node_mastery 里出现的知识点、
    只在答题记录里出现的知识点、只在聊天里出现的知识点、同一会话里重复提问同一知识点、
    ``last_practice_time`` 有值/为空两种掌握度行。
    """

    teacher_id = create_user("对照教师", "teacher", database_path=database_path)
    class_info = create_class(teacher_id, "对照班", database_path)
    student_ids: list[int] = []
    for index in range(count):
        student_id = create_user(f"对照学生{index}", "student", database_path=database_path)
        join_class(student_id, class_info.invite_code, database_path)
        student_ids.append(student_id)
        shared = f"kp_shared_{index % 2}"          # 相邻学生有重叠知识点，weak_counts 才有内容
        with connection_scope(database_path) as connection:
            session_id = int(
                connection.execute(
                    "INSERT INTO sessions (user_id, start_time) VALUES (?, ?)",
                    (student_id, f"2026-09-1{index % 9}T08:00:00+00:00"),
                ).lastrowid
            )
            for offset, node_ids in enumerate(
                (f'["{shared}"]', f'["{shared}", "kp_chat_only_{index}"]')
            ):
                connection.execute(
                    """
                    INSERT INTO messages (session_id, role, content, node_ids, timestamp)
                    VALUES (?, 'user', ?, ?, ?)
                    """,
                    (
                        session_id,
                        f"第 {offset} 问",
                        node_ids,
                        f"2026-09-1{index % 9}T08:0{offset}:00+00:00",
                    ),
                )
            # 掌握度：一条「掌握」（等级 4）、一条「薄弱」（等级 1），各带不同时间戳形态。
            connection.execute(
                """
                INSERT INTO node_mastery
                    (user_id, node_id, level, correct_count, total_count, last_practice_time)
                VALUES (?, ?, 4, 5, 5, ?)
                """,
                (student_id, shared, f"2026-09-1{index % 9}T09:00:00+00:00"),
            )
            connection.execute(
                """
                INSERT INTO node_mastery
                    (user_id, node_id, level, correct_count, total_count, last_practice_time)
                VALUES (?, ?, 1, 1, 4, NULL)
                """,
                (student_id, f"kp_mastery_only_{index}"),
            )
            # 答题记录：判对、判错、待批各一条。
            events = ((shared, 1), (shared, 0), (f"kp_event_only_{index}", None))
            for event_index, (node_id, is_correct) in enumerate(events):
                connection.execute(
                    """
                    INSERT INTO answer_events
                        (user_id, question_id, question_type, module, node_id,
                         is_correct, duration_ms, answer_text, created_at)
                    VALUES (?, ?, 'single', '数学分析', ?, ?, 1200, '作答', ?)
                    """,
                    (
                        student_id,
                        f"q_{index}_{event_index}",
                        node_id,
                        is_correct,
                        f"2026-09-1{index % 9}T10:0{event_index}:00+00:00",
                    ),
                )
    return student_ids


def test_batched_reports_match_single_reports_field_by_field(tmp_path, monkeypatch):
    """批量版和单份版必须**逐字段**相同 —— 它们共用同一段组装代码，这条钉住这件事。

    这是「班级页换用批量取数」敢上线的唯一理由：两条路径不可能算出两套结果。
    """

    database_path = tmp_path / "equiv.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    student_ids = _seed_rich_class(database_path, count=5)

    singles = [get_learning_report(user_id, database_path) for user_id in student_ids]
    with connection_scope(database_path) as connection:
        batched = build_learning_reports(connection, student_ids)

    assert [batched[user_id].model_dump() for user_id in student_ids] == [
        report.model_dump() for report in singles
    ]

    # 让夹具自己保证不空转：没有这几条，上面的相等断言可能只是在比两个空壳。
    assert any(report.weak_nodes for report in singles), "夹具里应当有薄弱知识点"
    assert any(report.summary["chat_interactions"] for report in singles), (
        "夹具里应当有聊天记录"
    )
    insights = [item for report in singles for item in report.node_insights]
    assert any(item.pending_review_count for item in insights), "夹具里应当有待批改的答题"
    assert any(item.repeated_chat_count for item in insights), "夹具里应当有重复提问"
    assert any(item.accuracy is not None for item in insights), "夹具里应当有已判分的答题"
    assert any(item.status == "掌握" for item in insights), "夹具里应当有已掌握的知识点"


def test_include_details_only_trims_the_detail_fields(tmp_path, monkeypatch):
    """``include_details=False`` 是「少带」不是「少算」。

    班级页读的正是 ``summary`` / ``radar_data`` / ``weak_nodes`` 这三样，所以它们必须
    照常算满 —— 谁要是哪天顺手用这个开关去省事，这条就会炸。
    """

    database_path = tmp_path / "details.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    student_ids = _seed_rich_class(database_path, count=3)

    with connection_scope(database_path) as connection:
        full = build_learning_reports(connection, student_ids, include_details=True)
        lean = build_learning_reports(connection, student_ids, include_details=False)

    for user_id in student_ids:
        assert lean[user_id].summary == full[user_id].summary
        assert lean[user_id].radar_data == full[user_id].radar_data
        assert lean[user_id].weak_nodes == full[user_id].weak_nodes
        assert lean[user_id].node_mastery == []
        assert lean[user_id].node_insights == []
        assert lean[user_id].understanding_nodes == []
        assert lean[user_id].mastered_nodes == []
        assert lean[user_id].recent_chat_nodes == []


# --------------------------------------------------------------------------- #
# 建表检查：按库文件自己的 user_version，而不是文件时间戳
# --------------------------------------------------------------------------- #


def test_init_database_skips_unchanged_schema(tmp_path, monkeypatch):
    """标记已经是最新时，连一条 DDL 都不该再跑 —— 哪怕期间有人写过库。

    ★ 这条测试的关键是**循环里那些真实的写库操作**：上一版按 ``(路径, mtime, size)``
    记忆化，而任何一次 INSERT 都会改 mtime，所以旧的判据在**有真实流量的机器上永远
    不命中** —— 32 人的班就是 32 遍建表检查。user_version 是写进库文件头里的，跟
    「有没有人写过库」无关，这才是这一版要钉住的东西。
    """

    database_path = tmp_path / "memo.db"
    init_database(database_path)

    applied: list[object] = []
    real_apply = database_module._apply_schema

    def counting_apply(connection):
        applied.append(connection)
        return real_apply(connection)

    monkeypatch.setattr(database_module, "_apply_schema", counting_apply)

    for index in range(25):
        # 真实写入：改 mtime、改文件大小，旧判据就是被这个打穿的。
        create_user(f"memo写手{index}", "student", database_path=database_path)
        init_database(database_path)

    assert applied == [], f"标记已是最新就不该重跑 DDL；实际跑了 {len(applied)} 遍"


def test_init_database_stamps_the_schema_version(tmp_path):
    """跑过一遍之后，库文件里就必须留下版本号（下次才能跳过）。"""

    database_path = tmp_path / "stamp.db"
    init_database(database_path)

    with connection_scope(database_path) as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION

    # 再调一次也不该把版本号改坏。
    init_database(database_path)
    with connection_scope(database_path) as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION


def test_init_database_rebuilds_when_the_file_is_replaced(tmp_path):
    """同一个路径换了个库文件（测试里很常见），必须重建，不能拿上一个库的标记糊弄。

    user_version 是**库文件自己的**属性，所以换个文件天然就是 0 —— 不需要额外判断路径。
    """

    database_path = tmp_path / "swap.db"
    init_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute("DROP TABLE node_mastery")
    connection.commit()
    connection.close()

    # 换一个全新的空文件进来：它的 user_version 自然是 0。
    database_path.unlink()
    blank = sqlite3.connect(database_path)
    blank.close()

    init_database(database_path)

    with connection_scope(database_path) as check:
        tables = {
            row["name"]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "node_mastery" in tables, "新的空库应当被重新建表"
    assert "answer_events" in tables


def test_init_database_rebuilds_after_the_marker_is_rolled_back(tmp_path):
    """把 user_version 按回 0 就能强制重建 —— 这也是文档里写的那个恢复办法。"""

    database_path = tmp_path / "rerun.db"
    init_database(database_path)

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA user_version = 0")
    connection.execute("DROP TABLE node_mastery")
    connection.commit()
    connection.close()

    init_database(database_path)

    with connection_scope(database_path) as check:
        tables = {
            row["name"]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version = int(check.execute("PRAGMA user_version").fetchone()[0])
    assert "node_mastery" in tables, "标记被按回去之后必须重新建表"
    assert version == SCHEMA_VERSION, "重建之后必须把标记重新写上"


def test_init_database_always_rebuilds_memory_databases():
    """``:memory:`` 每次连接都是新库，没有「已经建过」这回事。

    新内存库的 user_version 永远是 0，所以它天然走建表那条路，不需要特判。
    """

    init_database(":memory:")
    init_database(":memory:")   # 不许因为"刚建过"就跳过

    with connection_scope(":memory:") as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    # connection_scope 自己开的这条连接是全新的空库，所以这里查不到任何表 ——
    # 正因为如此，init_database(':memory:') 才永远不能跳过建表。
    assert tables == set()


# --------------------------------------------------------------------------- #
# WAL：读不再被写挡住
# --------------------------------------------------------------------------- #


def test_wal_is_enabled_for_new_connections(tmp_path):
    """库文件上的 journal_mode 应当真的变成 wal（读不再被写阻塞）。

    挂载点不支持 WAL 时 ``_enable_wal`` 会静默退回原模式（代码那边是对的行为），
    但那样这条抖动就还在 —— 所以这里必须**硬断言**，让不支持的环境当场暴露出来。
    """

    database_path = tmp_path / "wal.db"
    init_database(database_path)

    with connection_scope(database_path) as connection:
        assert str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        # synchronous 是**每条连接**的属性，0=OFF / 1=NORMAL / 2=FULL / 3=EXTRA。
        assert int(connection.execute("PRAGMA synchronous").fetchone()[0]) == 1

    # 它是库文件自身的持久属性，换一条新连接也该还是 wal。
    with connection_scope(database_path) as connection:
        assert str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"


def test_synchronous_normal_is_only_set_after_wal_takes_effect():
    """★ 安全线，不是风格问题。

    回滚日志模式下把 synchronous 降成 NORMAL 是**有丢库风险**的，所以只有确认切成了
    WAL 才允许设。这里用假连接把两种「没切成」的情形都走一遍。
    """

    # 情形一：SQLite 原样返回旧模式（只读介质、不支持 WAL 的挂载点）。
    fallback = _RecordingConnection(("delete",))
    _enable_wal(fallback)
    assert fallback.statements == ["PRAGMA journal_mode = WAL"], (
        "没切成 wal 就绝不能去动 synchronous"
    )

    # 情形二：直接抛 OperationalError（网络盘、恰有写者持锁）。
    failed = _RecordingConnection(None, error=sqlite3.OperationalError("readonly database"))
    _enable_wal(failed)   # 不该往外抛
    assert failed.statements == ["PRAGMA journal_mode = WAL"]

    # 对照：真的切成了，才设 NORMAL。
    success = _RecordingConnection(("wal",))
    _enable_wal(success)
    assert success.statements == [
        "PRAGMA journal_mode = WAL",
        "PRAGMA synchronous = NORMAL",
    ]
