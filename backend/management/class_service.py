"""Class membership and aggregate learning-report services."""

from __future__ import annotations

import secrets
import string
from pathlib import Path

from backend.learning.database import connection_scope, init_database
from backend.learning.service import MODULE_PREFIXES, get_learning_report
from backend.management.auth import (
    require_class,
    require_class_manager,
    require_teacher_or_admin,
    require_user,
)
from backend.management.exceptions import ConflictError, ResourceNotFoundError
from backend.management.models import (
    ClassInfo,
    ClassJoinResponse,
    ClassReportResponse,
    ClassStudent,
    ClassStudentsResponse,
    LearningSummary,
    WeakNodeFrequency,
)


def _generate_invite_code(connection, length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if connection.execute(
            "SELECT 1 FROM classes WHERE invite_code = ?", (code,)
        ).fetchone() is None:
            return code
    raise ConflictError("邀请码生成冲突，请重试")


def create_class(teacher_id: int, name: str, database_path=None) -> ClassInfo:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        teacher = require_user(connection, teacher_id)
        require_teacher_or_admin(teacher)
        invite_code = _generate_invite_code(connection)
        cursor = connection.execute(
            "INSERT INTO classes (name, invite_code, teacher_id) VALUES (?, ?, ?)",
            (name.strip(), invite_code, teacher_id),
        )
        return ClassInfo(
            class_id=int(cursor.lastrowid),
            name=name.strip(),
            invite_code=invite_code,
            teacher_id=teacher_id,
        )


def join_class(user_id: int, invite_code: str, database_path=None) -> ClassJoinResponse:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        user = require_user(connection, user_id)
        if user["role"] != "student":
            raise ConflictError("只有 student 用户可以加入班级")
        class_row = connection.execute(
            "SELECT * FROM classes WHERE invite_code = ?", (invite_code.strip().upper(),)
        ).fetchone()
        if class_row is None:
            raise ResourceNotFoundError("邀请码对应的班级不存在")
        already_joined = user["class_id"] == class_row["id"]
        if user["class_id"] is not None and not already_joined:
            raise ConflictError("用户已经加入其他班级")
        if not already_joined:
            connection.execute(
                "UPDATE users SET class_id = ? WHERE id = ?", (class_row["id"], user_id)
            )
        return ClassJoinResponse(
            message="已经在该班级中" if already_joined else "加入班级成功",
            class_info=ClassInfo(
                class_id=class_row["id"],
                name=class_row["name"],
                invite_code=class_row["invite_code"],
                teacher_id=class_row["teacher_id"],
            ),
            already_joined=already_joined,
        )


def _student_items(class_id: int, database_path=None) -> tuple[dict, list[ClassStudent]]:
    with connection_scope(database_path) as connection:
        class_row = require_class(connection, class_id)
        users = connection.execute(
            "SELECT id, name, role FROM users WHERE class_id = ? AND role = 'student' ORDER BY id",
            (class_id,),
        ).fetchall()
    students = []
    for user in users:
        report = get_learning_report(user["id"], database_path)
        students.append(
            ClassStudent(
                user_id=user["id"],
                name=user["name"],
                role=user["role"],
                learning_summary=LearningSummary(**report.summary),
            )
        )
    return dict(class_row), students


def get_class_students(requester_id: int, class_id: int, database_path=None):
    init_database(database_path)
    require_class_manager(requester_id, class_id, database_path)
    class_row, students = _student_items(class_id, database_path)
    return ClassStudentsResponse(
        class_id=class_id, name=class_row["name"], students=students
    )


def get_class_report(requester_id: int, class_id: int, database_path=None):
    init_database(database_path)
    require_class_manager(requester_id, class_id, database_path)
    class_row, students = _student_items(class_id, database_path)
    reports = [get_learning_report(student.user_id, database_path) for student in students]
    radar_data = []
    for index, module_name in enumerate(MODULE_PREFIXES.values()):
        levels = [report.radar_data[index].average_level for report in reports]
        average_level = sum(levels) / len(levels) if levels else 0.0
        from backend.learning.models import RadarModule

        radar_data.append(
            RadarModule(
                module=module_name,
                average_level=round(average_level, 2),
                value=round(average_level / 4 * 100, 2),
                practiced_nodes=sum(report.radar_data[index].practiced_nodes for report in reports),
            )
        )

    total_answers = sum(int(report.summary["total_answers"]) for report in reports)
    with connection_scope(database_path) as connection:
        correct_row = connection.execute(
            """
            SELECT COALESCE(SUM(n.correct_count), 0) AS correct
            FROM node_mastery n JOIN users u ON u.id = n.user_id
            WHERE u.class_id = ? AND u.role = 'student'
            """,
            (class_id,),
        ).fetchone()
    weak_counts: dict[str, int] = {}
    for report in reports:
        for node_id in report.weak_nodes:
            weak_counts[node_id] = weak_counts.get(node_id, 0) + 1
    weak_nodes = [
        WeakNodeFrequency(node_id=node_id, student_count=count)
        for node_id, count in sorted(weak_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return ClassReportResponse(
        class_id=class_id,
        class_name=class_row["name"],
        student_count=len(students),
        radar_data=radar_data,
        overall_accuracy=round(correct_row["correct"] / total_answers, 4) if total_answers else 0.0,
        weak_nodes=weak_nodes,
        students=students,
    )
