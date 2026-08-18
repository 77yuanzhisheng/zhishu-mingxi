"""Learning-report sharing request and authorization services."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.learning.database import connection_scope, init_database
from backend.learning.service import get_learning_report
from backend.management.auth import require_user
from backend.management.exceptions import ConflictError, PermissionDeniedError, ResourceNotFoundError
from backend.management.models import ShareRequestInfo, SharedLearningReport


def create_share_request(requester_id: int, target_user_id: int, database_path=None):
    init_database(database_path)
    if requester_id == target_user_id:
        raise ConflictError("不能申请查看自己的学情")
    with connection_scope(database_path) as connection:
        require_user(connection, requester_id)
        require_user(connection, target_user_id)
        pending = connection.execute(
            """
            SELECT id FROM share_requests
            WHERE requester_id = ? AND target_user_id = ? AND status = 'pending'
            """,
            (requester_id, target_user_id),
        ).fetchone()
        if pending:
            raise ConflictError("已经存在待处理的共享申请")
        now = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            """
            INSERT INTO share_requests (requester_id, target_user_id, status, created_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (requester_id, target_user_id, now),
        )
        request_id = int(cursor.lastrowid)
    return ShareRequestInfo(
        request_id=request_id,
        requester_id=requester_id,
        target_user_id=target_user_id,
        status="pending",
        created_at=now,
    )


def decide_share_request(request_id: int, target_user_id: int, approved: bool, database_path=None):
    init_database(database_path)
    with connection_scope(database_path) as connection:
        require_user(connection, target_user_id)
        row = connection.execute(
            "SELECT * FROM share_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"共享申请 {request_id} 不存在")
        if row["target_user_id"] != target_user_id:
            raise PermissionDeniedError("只有被申请人可以处理共享申请")
        if row["status"] != "pending":
            raise ConflictError("共享申请已经处理")
        status = "approved" if approved else "rejected"
        resolved_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "UPDATE share_requests SET status = ?, resolved_at = ? WHERE id = ?",
            (status, resolved_at, request_id),
        )
    return ShareRequestInfo(
        request_id=request_id,
        requester_id=row["requester_id"],
        target_user_id=target_user_id,
        status=status,
        created_at=row["created_at"],
        resolved_at=resolved_at,
    )


def get_shared_report(target_user_id: int, requester_id: int, database_path=None):
    init_database(database_path)
    with connection_scope(database_path) as connection:
        require_user(connection, target_user_id)
        require_user(connection, requester_id)
        authorized = requester_id == target_user_id
        if not authorized:
            authorized = connection.execute(
                """
                SELECT 1 FROM share_requests
                WHERE requester_id = ? AND target_user_id = ? AND status = 'approved'
                LIMIT 1
                """,
                (requester_id, target_user_id),
            ).fetchone() is not None
    if not authorized:
        raise PermissionDeniedError("没有查看该用户学情的授权")
    return SharedLearningReport(
        authorized=True, report=get_learning_report(target_user_id, database_path)
    )
