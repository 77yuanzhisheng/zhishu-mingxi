"""Exam generation, deterministic grading and aggregate result services."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.learning.database import connection_scope, init_database
from backend.learning.service import module_for_node, record_learning_result
from backend.management.auth import (
    require_class,
    require_class_manager,
    require_teacher_or_admin,
    require_user,
)
from backend.management.exceptions import ConflictError, PermissionDeniedError, ResourceNotFoundError
from backend.management.models import (
    AnswerResult,
    ExamGenerateResponse,
    ExamQuestion,
    ExamResultsResponse,
    ExamStatusUpdateResponse,
    ExamSubmitResponse,
    NodeExamStatistic,
    StudentExamDetail,
    StudentExamInfo,
    StudentExamQuestion,
    StudentExamResult,
    TeacherExamInfo,
    TeacherExamPaper,
)
from backend.management.question_source import recommend_exam_questions


def _question_from_row(row, include_answer: bool = True) -> ExamQuestion:
    answer = row["answer"] if include_answer else None
    return ExamQuestion(
        question_id=row["id"],
        node_id=row["node_id"],
        question_type=row["question_type"],
        content=row["content"],
        answer=answer,
        score=row["score"],
        sort_order=row["sort_order"],
        grading_mode="automatic" if row["answer"] else "pending_review",
    )


def get_student_exams(user_id: int, database_path=None) -> list[StudentExamInfo]:
    """Return published exams for a student's class, including submission state.

    2026-09-14 起把 'closed' 也纳入：教师「结束考试」之后，学生端那条卷子应当**仍在列表里
    并标示为已结束**（只是不再允许作答），而不是整条消失。作答闸门在 submit_exam 里
    （status != 'published' → ConflictError），所以放宽这个 SELECT 不会放进新的交卷。
    """

    init_database(database_path)
    with connection_scope(database_path) as connection:
        user = require_user(connection, user_id)
        if user["role"] != "student":
            raise PermissionDeniedError("仅 student 用户可以查看学生考试列表")
        if user["class_id"] is None:
            return []
        rows = connection.execute(
            """
            SELECT e.*,
                   EXISTS(
                       SELECT 1 FROM exam_submissions s
                       WHERE s.exam_id = e.id AND s.user_id = ?
                   ) AS submitted
            FROM exams e
            WHERE e.class_id = ? AND e.status IN ('published', 'closed')
            ORDER BY e.created_at DESC, e.id DESC
            """,
            (user_id, user["class_id"]),
        ).fetchall()
    return [
        StudentExamInfo(
            exam_id=row["id"],
            title=row["title"],
            class_id=row["class_id"],
            status=row["status"],
            created_at=row["created_at"],
            total_score=row["total_score"],
            submitted=bool(row["submitted"]),
        )
        for row in rows
    ]


def list_teacher_exams(teacher_id: int, database_path=None) -> list[TeacherExamInfo]:
    """Return exams published across the classes a teacher manages.

    与 get_student_exams 的分工：那个按「学生所在班级」查、且只认 student 角色
    （教师调它会 403），所以教师回看自己发过的卷子必须走这个函数。

    班级归属以 classes.teacher_id 为准，与 require_class_manager / generate_exam
    的判据保持一致（不用 exams.teacher_id —— 班级转手后应以班级归属为准）。
    admin 可以看到全部。
    """

    init_database(database_path)
    with connection_scope(database_path) as connection:
        teacher = require_user(connection, teacher_id)
        require_teacher_or_admin(teacher)
        sql = """
            SELECT e.id AS id,
                   e.title AS title,
                   e.class_id AS class_id,
                   c.name AS class_name,
                   e.status AS status,
                   e.created_at AS created_at,
                   e.total_score AS total_score,
                   (SELECT COUNT(*) FROM exam_questions q WHERE q.exam_id = e.id) AS question_count,
                   (SELECT COUNT(*) FROM exam_submissions s WHERE s.exam_id = e.id) AS submitted_count
            FROM exams e
            JOIN classes c ON c.id = e.class_id
        """
        params: tuple = ()
        if teacher["role"] != "admin":
            sql += " WHERE c.teacher_id = ?"
            params = (teacher_id,)
        sql += " ORDER BY e.created_at DESC, e.id DESC"
        rows = connection.execute(sql, params).fetchall()
    return [
        TeacherExamInfo(
            exam_id=row["id"],
            title=row["title"],
            class_id=row["class_id"],
            class_name=row["class_name"],
            status=row["status"],
            created_at=row["created_at"],
            total_score=row["total_score"],
            question_count=row["question_count"],
            submitted_count=row["submitted_count"],
        )
        for row in rows
    ]


def get_student_exam(exam_id: int, database_path=None) -> StudentExamDetail:
    """Return an exam and its questions without any answer or grading metadata."""

    init_database(database_path)
    with connection_scope(database_path) as connection:
        exam = connection.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
        if exam is None:
            raise ResourceNotFoundError(f"考试 {exam_id} 不存在")
        questions = connection.execute(
            """
            SELECT id, node_id, question_type, content, score, sort_order
            FROM exam_questions
            WHERE exam_id = ?
            ORDER BY sort_order
            """,
            (exam_id,),
        ).fetchall()
    return StudentExamDetail(
        exam_id=exam["id"],
        title=exam["title"],
        class_id=exam["class_id"],
        status=exam["status"],
        created_at=exam["created_at"],
        total_score=exam["total_score"],
        questions=[
            StudentExamQuestion(
                question_id=row["id"],
                node_id=row["node_id"],
                question_type=row["question_type"],
                content=row["content"],
                score=row["score"],
                sort_order=row["sort_order"],
            )
            for row in questions
        ],
    )


def generate_exam(
    teacher_id: int,
    class_id: int,
    title: str,
    node_ids: list[str],
    question_count: int,
    database_path=None,
    # 题型多选。刻意排在 database_path **后面**：现有测试与调用方都是按位置把
    # database_path 传在第 6 个参数上的，插在前面会把它们全部打断。
    question_types: list[str] | None = None,
) -> ExamGenerateResponse:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        teacher = require_user(connection, teacher_id)
        class_row = require_class(connection, class_id)
        require_teacher_or_admin(teacher)
        if teacher["role"] != "admin" and class_row["teacher_id"] != teacher_id:
            raise PermissionDeniedError("只能为自己管理的班级生成考试")

    questions = recommend_exam_questions(node_ids, question_count, question_types)
    if len(questions) < question_count:
        # ⚠️ 「仅找到 N 道匹配题目，少于请求的 M 道」这个子串被前端
        # explainExamGenerateError() 的正则抠出来解析题量 —— 只能在**末尾追加**，
        # 不能改写中间任何一段，否则教师端会退化成直接显示这条面向开发者的原文。
        raise ConflictError(
            f"现有题库仅找到 {len(questions)} 道匹配题目，少于请求的 {question_count} 道"
            + (f"（已按题型筛选：{'、'.join(question_types)}）" if question_types else "")
        )
    question_score = round(100 / question_count, 2)
    scores = [question_score] * question_count
    scores[-1] = round(100 - sum(scores[:-1]), 2)
    now = datetime.now(timezone.utc).isoformat()
    with connection_scope(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO exams (class_id, teacher_id, title, created_at, total_score, status)
            VALUES (?, ?, ?, ?, 100, 'published')
            """,
            (class_id, teacher_id, title.strip(), now),
        )
        exam_id = int(cursor.lastrowid)
        for index, (question, score) in enumerate(zip(questions, scores), start=1):
            connection.execute(
                """
                INSERT INTO exam_questions (
                    exam_id, node_id, question_type, content, answer, score, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exam_id,
                    question["node_id"],
                    question["type"],
                    question["content"],
                    question.get("answer"),
                    score,
                    index,
                ),
            )
        rows = connection.execute(
            "SELECT * FROM exam_questions WHERE exam_id = ? ORDER BY sort_order", (exam_id,)
        ).fetchall()
    return ExamGenerateResponse(
        exam_id=exam_id,
        class_id=class_id,
        teacher_id=teacher_id,
        title=title.strip(),
        total_score=100,
        status="published",
        questions=[_question_from_row(row) for row in rows],
    )


def _normalize_answer(answer: str) -> str:
    return "".join(answer.strip().upper().split())


def submit_exam(exam_id: int, user_id: int, answers, database_path=None):
    init_database(database_path)
    supplied = {answer.question_id: answer.answer for answer in answers}
    if len(supplied) != len(answers):
        raise ConflictError("同一道题不能重复提交答案")

    with connection_scope(database_path) as connection:
        user = require_user(connection, user_id)
        exam = connection.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
        if exam is None:
            raise ResourceNotFoundError(f"考试 {exam_id} 不存在")
        if user["role"] != "student":
            raise PermissionDeniedError("仅 student 可以提交考试")
        if user["class_id"] != exam["class_id"]:
            raise PermissionDeniedError("该考试不属于学生所在班级")
        if exam["status"] != "published":
            raise ConflictError("考试当前不可提交")
        if connection.execute(
            "SELECT 1 FROM exam_submissions WHERE exam_id = ? AND user_id = ?",
            (exam_id, user_id),
        ).fetchone():
            raise ConflictError("该学生已经提交过本次考试")
        questions = connection.execute(
            "SELECT * FROM exam_questions WHERE exam_id = ? ORDER BY sort_order", (exam_id,)
        ).fetchall()
        valid_ids = {row["id"] for row in questions}
        unknown = set(supplied) - valid_ids
        if unknown:
            raise ResourceNotFoundError(f"题目不属于该考试: {sorted(unknown)}")

        graded: list[dict] = []
        total_score = 0.0
        has_pending = False
        for question in questions:
            student_answer = supplied.get(question["id"], "")
            if question["answer"]:
                is_correct = _normalize_answer(student_answer) == _normalize_answer(question["answer"])
                score = float(question["score"]) if is_correct else 0.0
                review_status = "graded"
            else:
                is_correct = None
                score = 0.0
                review_status = "pending_review"
                has_pending = True
            total_score += score
            graded.append(
                {
                    "question_id": question["id"],
                    "node_id": question["node_id"],
                    "student_answer": student_answer,
                    "is_correct": is_correct,
                    "score": score,
                    "review_status": review_status,
                }
            )
        submission_status = "pending_review" if has_pending else "graded"
        submitted_at = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            """
            INSERT INTO exam_submissions (
                exam_id, user_id, submitted_at, total_score, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (exam_id, user_id, submitted_at, total_score, submission_status),
        )
        submission_id = int(cursor.lastrowid)
        for item in graded:
            connection.execute(
                """
                INSERT INTO exam_answers (
                    submission_id, question_id, student_answer, is_correct, score, review_status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    item["question_id"],
                    item["student_answer"],
                    int(item["is_correct"]) if item["is_correct"] is not None else None,
                    item["score"],
                    item["review_status"],
                ),
            )
            record_learning_result(
                connection,
                user_id=user_id,
                question_id=item["question_id"],
                question_type="exam",
                module=module_for_node(item["node_id"]),
                node_id=item["node_id"],
                is_correct=item["is_correct"],
                duration_ms=None,
                answer_text=item["student_answer"],
                created_at=submitted_at,
                validate_user=False,
            )
    return ExamSubmitResponse(
        submission_id=submission_id,
        exam_id=exam_id,
        user_id=user_id,
        total_score=round(total_score, 2),
        status=submission_status,
        answers=[AnswerResult(**{k: item[k] for k in AnswerResult.model_fields}) for item in graded],
    )


def get_exam_results(exam_id: int, requester_id: int, database_path=None):
    init_database(database_path)
    with connection_scope(database_path) as connection:
        exam = connection.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
        if exam is None:
            raise ResourceNotFoundError(f"考试 {exam_id} 不存在")
    require_class_manager(requester_id, exam["class_id"], database_path)
    with connection_scope(database_path) as connection:
        submissions = connection.execute(
            """
            SELECT s.*, u.name FROM exam_submissions s
            JOIN users u ON u.id = s.user_id
            WHERE s.exam_id = ? ORDER BY s.total_score DESC, s.submitted_at ASC
            """,
            (exam_id,),
        ).fetchall()
        node_rows = connection.execute(
            """
            SELECT q.node_id,
                   SUM(CASE WHEN a.is_correct IS NOT NULL THEN 1 ELSE 0 END) graded_answers,
                   SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) correct_answers,
                   SUM(CASE WHEN a.review_status = 'pending_review' THEN 1 ELSE 0 END) pending_review
            FROM exam_questions q
            LEFT JOIN exam_answers a ON a.question_id = q.id
            WHERE q.exam_id = ? GROUP BY q.node_id ORDER BY q.node_id
            """,
            (exam_id,),
        ).fetchall()
    scores = [float(row["total_score"]) for row in submissions]
    node_statistics = []
    weak_nodes = []
    for row in node_rows:
        accuracy = (
            round(row["correct_answers"] / row["graded_answers"], 4)
            if row["graded_answers"]
            else None
        )
        node_statistics.append(
            NodeExamStatistic(
                node_id=row["node_id"],
                graded_answers=row["graded_answers"],
                correct_answers=row["correct_answers"],
                accuracy=accuracy,
                pending_review=row["pending_review"],
            )
        )
        if accuracy is not None and accuracy < 0.6:
            weak_nodes.append(row["node_id"])
    return ExamResultsResponse(
        exam={
            "exam_id": exam["id"],
            "class_id": exam["class_id"],
            "teacher_id": exam["teacher_id"],
            "title": exam["title"],
            "total_score": exam["total_score"],
            "status": exam["status"],
            "created_at": exam["created_at"],
        },
        submitted_count=len(submissions),
        average_score=round(sum(scores) / len(scores), 2) if scores else 0.0,
        highest_score=max(scores) if scores else 0.0,
        lowest_score=min(scores) if scores else 0.0,
        students=[
            StudentExamResult(
                user_id=row["user_id"],
                name=row["name"],
                total_score=row["total_score"],
                status=row["status"],
                submitted_at=row["submitted_at"],
            )
            for row in submissions
        ],
        node_statistics=node_statistics,
        weak_nodes=weak_nodes,
    )


# ==================== 教师校对 / 结束考试 / 学生回看（2026-09-14） ====================

# 允许切换到的状态。'draft' 不在内：generate_exam 一律建成 'published'，
# 全站从来没有写入过 draft，所以不接受。
_STATUS_MESSAGES = {
    "closed": "考试已结束，学生不能再作答；已交卷的学生仍可回看自己的成绩。",
    "published": "考试已重新开放，学生可以继续作答。",
}


def get_exam_paper_for_teacher(
    exam_id: int, requester_id: int, database_path=None
) -> TeacherExamPaper:
    """教师校对视图：题干 + 参考答案（**只读**，不写任何数据）。

    单独开一个函数、而不是给 get_student_exam 加一个 include_answer 开关，是因为两者的
    授权模型根本不同：get_student_exam 只要求登录（学生答自己的卷子也走它），
    连 answer 列都不 SELECT；这里必须先 require_class_manager 钉死班级归属，才敢回答案。
    把开关加进那个函数，等于给「任何登录者 + 任意 exam_id」开了一条偷答案的路。
    """

    init_database(database_path)
    with connection_scope(database_path) as connection:
        exam = connection.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
        if exam is None:
            raise ResourceNotFoundError(f"考试 {exam_id} 不存在")
        class_row = connection.execute(
            "SELECT name FROM classes WHERE id = ?", (exam["class_id"],)
        ).fetchone()
    require_class_manager(requester_id, exam["class_id"], database_path)
    with connection_scope(database_path) as connection:
        questions = connection.execute(
            "SELECT * FROM exam_questions WHERE exam_id = ? ORDER BY sort_order", (exam_id,)
        ).fetchall()
    return TeacherExamPaper(
        exam_id=exam["id"],
        title=exam["title"],
        class_id=exam["class_id"],
        class_name=class_row["name"] if class_row is not None else "",
        status=exam["status"],
        created_at=exam["created_at"],
        total_score=exam["total_score"],
        questions=[_question_from_row(row) for row in questions],
    )


def set_exam_status(
    exam_id: int, requester_id: int, status: str, database_path=None
) -> ExamStatusUpdateResponse:
    """结束考试（closed）/ 重新开放（published）。**只改 exams.status 一列**，不动任何作答数据。

    为什么不需要迁移：'closed' 早就在 exams.status 的 CHECK 约束里
    （learning/database.py 的 SCHEMA_SQL），而交卷闸门 submit_exam 里那句
    `if exam["status"] != "published": raise ConflictError` 本来就认它。
    所以这是真正的「一列一值」改动 —— 没有加列、没有改表、没有动历史数据。

    幂等：本来就是目标状态时直接返回成功（老师连点两下不该看到红色报错）。
    """

    if status not in _STATUS_MESSAGES:
        raise ConflictError(f"不支持的考试状态：{status}")

    init_database(database_path)
    with connection_scope(database_path) as connection:
        exam = connection.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
        if exam is None:
            raise ResourceNotFoundError(f"考试 {exam_id} 不存在")
    require_class_manager(requester_id, exam["class_id"], database_path)

    current = exam["status"]
    if current == status:
        return ExamStatusUpdateResponse(
            exam_id=exam_id,
            status=current,
            message=f"{_STATUS_MESSAGES[status]}（该考试已是此状态，未做改动）",
        )
    if current not in _STATUS_MESSAGES:
        raise ConflictError(f"考试当前状态为 {current}，不支持切换")

    with connection_scope(database_path) as connection:
        # CAS：把「读到的那个状态」一并写进 WHERE。两条请求同时进来时必有一条 rowcount=0，
        # 不存在「先 SELECT 判断、再 UPDATE」中间被别人插一脚的窗口。
        cursor = connection.execute(
            "UPDATE exams SET status = ? WHERE id = ? AND status = ?",
            (status, exam_id, current),
        )
        changed = cursor.rowcount
    if not changed:
        # 只有并发才会走到这里（同状态的重复操作上面已经返回了）。重读一次、如实回报，
        # 而不是报错 —— 老师的意图已经达成了，没有必要给他一个红色提示。
        with connection_scope(database_path) as connection:
            latest = connection.execute(
                "SELECT status FROM exams WHERE id = ?", (exam_id,)
            ).fetchone()
        if latest is None:
            raise ResourceNotFoundError(f"考试 {exam_id} 不存在")
        return ExamStatusUpdateResponse(
            exam_id=exam_id,
            status=latest["status"],
            message=f"该考试的状态已被另一处操作改成了 {latest['status']}，本次未再改动。",
        )
    return ExamStatusUpdateResponse(
        exam_id=exam_id, status=status, message=_STATUS_MESSAGES[status]
    )


def get_student_submission(exam_id: int, user_id: int, database_path=None) -> ExamSubmitResponse:
    """学生回看**自己**已交卷的得分与逐题对错（只读）。

    这是既有缺口，不是「结束考试」造成的：交卷时后端把 ExamSubmitResponse 回了一次，
    前端渲染完就丢了，刷新页面成绩就没了。复用同一个响应模型，前端可以直接用
    渲染交卷结果那套代码。
    """

    init_database(database_path)
    with connection_scope(database_path) as connection:
        submission = connection.execute(
            "SELECT * FROM exam_submissions WHERE exam_id = ? AND user_id = ?",
            (exam_id, user_id),
        ).fetchone()
        if submission is None:
            raise ResourceNotFoundError("尚未提交本次考试")
        rows = connection.execute(
            """
            SELECT a.question_id, q.node_id, a.is_correct, a.score, a.review_status
            FROM exam_answers a
            JOIN exam_questions q ON q.id = a.question_id
            WHERE a.submission_id = ?
            ORDER BY q.sort_order
            """,
            (submission["id"],),
        ).fetchall()
    return ExamSubmitResponse(
        submission_id=submission["id"],
        exam_id=submission["exam_id"],
        user_id=submission["user_id"],
        total_score=submission["total_score"],
        status=submission["status"],
        answers=[
            AnswerResult(
                question_id=row["question_id"],
                node_id=row["node_id"],
                # 库里存的是 0/1/NULL；None 表示这道题是主观题、还没人工复核。
                is_correct=None if row["is_correct"] is None else bool(row["is_correct"]),
                score=row["score"],
                review_status=row["review_status"],
            )
            for row in rows
        ],
    )
