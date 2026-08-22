"""Exam generation, deterministic grading and aggregate result services."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.learning.database import connection_scope, init_database
from backend.learning.service import insert_answer_event, module_for_node, update_mastery
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
    ExamSubmitResponse,
    NodeExamStatistic,
    StudentExamDetail,
    StudentExamInfo,
    StudentExamQuestion,
    StudentExamResult,
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
    """Return published exams for a student's class, including submission state."""

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
            WHERE e.class_id = ? AND e.status = 'published'
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
) -> ExamGenerateResponse:
    init_database(database_path)
    with connection_scope(database_path) as connection:
        teacher = require_user(connection, teacher_id)
        class_row = require_class(connection, class_id)
        require_teacher_or_admin(teacher)
        if teacher["role"] != "admin" and class_row["teacher_id"] != teacher_id:
            raise PermissionDeniedError("只能为自己管理的班级生成考试")

    questions = recommend_exam_questions(node_ids, question_count)
    if len(questions) < question_count:
        raise ConflictError(
            f"现有题库仅找到 {len(questions)} 道匹配题目，少于请求的 {question_count} 道"
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
            insert_answer_event(
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

    # Reuse the established mastery calculation only for deterministically graded answers.
    for item in graded:
        if item["is_correct"] is not None:
            update_mastery(user_id, item["node_id"], item["is_correct"], database_path)
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
