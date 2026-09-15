"""Regression guards for the two cost fixes behind 「查看学情」.

Both changes only ever *remove* work, so the way to keep them honest is to count
the work rather than to time it. Timings belong to the benchmark, not to a test
suite that has to pass on any machine.
"""

from __future__ import annotations

import sqlite3

from backend.learning.database import connection_scope, init_database
from backend.learning.service import create_user, get_learning_report, update_mastery
from backend.management.class_service import (
    create_class,
    get_class_report,
    get_class_students,
    join_class,
)


def _class_with_students(database_path, count: int = 4):
    """A teacher, a class, and ``count`` students that each have some mastery."""

    teacher_id = create_user("计费教师", "teacher", database_path=database_path)
    class_info = create_class(teacher_id, "计费班", database_path)
    for index in range(count):
        student_id = create_user(f"计费学生{index}", "student", database_path=database_path)
        join_class(student_id, class_info.invite_code, database_path)
        for node in range(3):
            update_mastery(
                student_id, f"kp_cost_{node}", node % 2 == 0, database_path
            )
    return teacher_id, class_info.class_id


def test_class_report_reuses_the_reports_it_already_built(tmp_path, monkeypatch):
    """One report per student -- not two.

    ``get_class_report`` needs the same per-student reports ``_student_items``
    builds. It used to call ``get_learning_report`` a second time for every
    student, which doubled the DB work of the teacher's slowest screen.
    """

    database_path = tmp_path / "reuse.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    teacher_id, class_id = _class_with_students(database_path, count=4)

    calls: list[int] = []
    real = get_learning_report

    def counting(user_id, path=None):
        calls.append(user_id)
        return real(user_id, path)

    import backend.management.class_service as class_service

    monkeypatch.setattr(class_service, "get_learning_report", counting)

    report = get_class_report(teacher_id, class_id, database_path)

    assert len(report.students) == 4
    assert len(calls) == 4, f"每个学生应当只算一次报告，实际 {len(calls)} 次：{calls}"

    # 汇总字段必须是真算出来的，不能因为复用就变成 0。
    assert report.student_count == 4
    assert report.radar_data, "雷达数据不能为空"
    assert any(item.learning_summary.total_answers for item in report.students), (
        "复用报告后 learning_summary 仍然要有真实数据"
    )


def test_class_students_and_report_agree(tmp_path, monkeypatch):
    """两条路径都从同一份报告派生，摘要必须一致。"""

    database_path = tmp_path / "agree.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    teacher_id, class_id = _class_with_students(database_path, count=3)

    students = get_class_students(teacher_id, class_id, database_path).students
    report = get_class_report(teacher_id, class_id, database_path)

    assert [item.user_id for item in students] == [item.user_id for item in report.students]
    assert [item.learning_summary for item in students] == [
        item.learning_summary for item in report.students
    ]


def test_init_database_skips_unchanged_schema(tmp_path, monkeypatch):
    """建表检查按文件指纹记忆化：文件没动，连连接都不该开。

    数的是 ``connection_scope`` 而不是 ``executescript`` —— 开连接本来就是这笔开销
    的大头，顺带绕开了「C 实现的 sqlite3.Connection 不给打补丁」这件事。
    """

    database_path = tmp_path / "memo.db"
    init_database(database_path)

    import backend.learning.database as database_module

    real_scope = database_module.connection_scope
    opened: list[object] = []

    def counting_scope(*args, **kwargs):
        opened.append(args)
        return real_scope(*args, **kwargs)

    monkeypatch.setattr(database_module, "connection_scope", counting_scope)

    for _ in range(25):
        init_database(database_path)

    assert opened == [], f"库文件没变就不该再开连接重跑建表；实际开了 {len(opened)} 次"


def test_init_database_rebuilds_when_the_file_is_replaced(tmp_path):
    """同一路径换了个库（测试常见），必须重建，不能拿旧记忆糊弄。"""

    database_path = tmp_path / "swap.db"
    init_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute("DROP TABLE node_mastery")
    connection.commit()
    connection.close()

    # 换一个明显不同的文件进来：内容、大小、时间戳都会变。
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


def test_init_database_always_rebuilds_memory_databases():
    """``:memory:`` 每次连接都是新库，记忆化必须绕开它。"""

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
    # 正因为如此，init_database(':memory:') 才永远不能走记忆化那条路。
    assert tables == set()
