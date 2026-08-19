"""
前端兼容层
==========

桥接队员4前端接口契约与队员3后端实现之间的差异。

队员4前端调用的接口（与后端不一致的部分）：
1. POST /api/user/ensure         — 页面初始化时确保用户存在
2. GET  /api/learning-report     — 学情报告（后端是 /api/learning/report）
3. GET  /api/class/student/{uid} — 学生加入的班级
4. GET  /api/class/teacher/{uid} — 老师管理的班级列表
5. GET  /api/share/requests      — 待处理的分享申请
6. class/create、class/join 响应补 id 字段
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.learning.database import connection_scope

router = APIRouter(prefix="/api", tags=["前端兼容"])

# 无前缀路由：前端调用 /chat/stream（不带 /api 前缀）
stream_router = APIRouter(tags=["前端兼容-流式"])


# ==================== 流式聊天（前端 /chat/stream 契约） ====================

class StreamChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: int = Field(gt=0)
    session_id: int | None = Field(default=None, gt=0)
    node_id: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=3, ge=1, le=20)
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)


@stream_router.post("/chat/stream")
def chat_stream(request: StreamChatRequest):
    """
    流式聊天端点（队员4前端契约）。

    响应格式：NDJSON，每行一个事件：
    - {"type": "meta", "session_id": ...}
    - {"type": "delta", "content": "..."}
    - {"type": "done", "answer": "...", "session_id": ..., "references": [...]}
    - {"type": "error", "detail": "..."}
    """
    from backend.chat.router import get_chat_service
    from backend.chat.models import ChatRequest
    from backend.chat.exceptions import ChatUserNotFoundError, ChatSessionNotFoundError, ChatSessionAccessError, LLMUnavailableError

    def generate():
        try:
            service = get_chat_service()
            result = service.chat(ChatRequest(
                user_id=request.user_id,
                session_id=request.session_id,
                message=request.message,
                node_id=request.node_id,
                top_k=request.top_k,
                min_score=request.min_score,
            ))
            yield json.dumps({"type": "meta", "session_id": result.session_id}, ensure_ascii=False) + "\n"

            # 按句子分块模拟流式输出
            answer = result.answer
            chunks = []
            buffer = ""
            for ch in answer:
                buffer += ch
                if len(buffer) >= 24:
                    chunks.append(buffer)
                    buffer = ""
            if buffer:
                chunks.append(buffer)
            for piece in chunks:
                yield json.dumps({"type": "delta", "content": piece}, ensure_ascii=False) + "\n"

            references = [
                {
                    "content": ref.content,
                    "score": ref.score,
                    "metadata": ref.metadata,
                }
                for ref in result.references
            ]
            yield json.dumps({
                "type": "done",
                "answer": result.answer,
                "session_id": result.session_id,
                "references": references,
                "node_ids": result.node_ids,
                "topic_switch_hint": result.topic_switch_hint,
            }, ensure_ascii=False) + "\n"

        except (ChatUserNotFoundError, ChatSessionNotFoundError, ChatSessionAccessError, LLMUnavailableError) as exc:
            yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            yield json.dumps({"type": "error", "detail": f"流式调用失败: {exc}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== 用户确保 ====================

class UserEnsureRequest(BaseModel):
    user_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=50)
    role: str = Field(default="student", pattern="^(student|teacher|admin)$")


@router.post("/user/ensure")
def ensure_user(request: UserEnsureRequest) -> dict[str, Any]:
    """确保用户存在：存在则返回，不存在则创建。前端页面初始化时调用。"""
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT id, name, role, class_id FROM users WHERE id = ?",
            (request.user_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (id, name, role) VALUES (?, ?, ?)",
                (request.user_id, request.name, request.role),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, name, role, class_id FROM users WHERE id = ?",
                (request.user_id,),
            ).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "class_id": row["class_id"],
        }


# ==================== 学情报告别名 ====================

@router.get("/learning-report")
def learning_report_alias(user_id: int = Query(..., gt=0)):
    """GET /api/learning-report — 前端使用的别名"""
    from backend.learning.service import get_learning_report, UserNotFoundError
    try:
        return get_learning_report(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ==================== 班级查询（学生/教师视角） ====================

def _class_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "class_id": row["id"],
        "name": row["name"],
        "invite_code": row["invite_code"],
        "teacher_id": row["teacher_id"],
    }


@router.get("/class/student/{user_id}")
def student_class(user_id: int):
    """学生加入的班级（前端：classState.studentClass = data.class）"""
    with connection_scope() as conn:
        user = conn.execute(
            "SELECT class_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail=f"用户 {user_id} 不存在")
        if user["class_id"] is None:
            return {"class": None}
        cls = conn.execute(
            "SELECT * FROM classes WHERE id = ?", (user["class_id"],)
        ).fetchone()
        if cls is None:
            return {"class": None}
        return {"class": _class_dict(cls)}


@router.get("/class/teacher/{user_id}")
def teacher_classes(user_id: int):
    """老师管理的班级列表"""
    with connection_scope() as conn:
        rows = conn.execute(
            "SELECT * FROM classes WHERE teacher_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return {"classes": [_class_dict(r) for r in rows]}


# ==================== 分享申请列表 ====================

@router.get("/share/requests")
def list_share_requests(target_user_id: int = Query(..., gt=0)):
    """待处理的分享申请（前端班级页面加载时调用）"""
    with connection_scope() as conn:
        rows = conn.execute(
            "SELECT * FROM share_requests WHERE target_user_id = ? ORDER BY id DESC",
            (target_user_id,),
        ).fetchall()
        return {
            "requests": [
                {
                    "request_id": r["id"],
                    "requester_id": r["requester_id"],
                    "target_user_id": r["target_user_id"],
                    "status": r["status"],
                }
                for r in rows
            ]
        }


# ==================== 班级创建/加入响应补 id 字段 ====================

class ClassCreateCompatRequest(BaseModel):
    teacher_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)


@router.post("/class/create")
def create_class_compat(request: ClassCreateCompatRequest):
    """包装队员3 create_class，响应补充 id 字段（前端读 data.id）"""
    from backend.management.class_service import create_class
    from backend.management.exceptions import ManagementError
    try:
        info = create_class(request.teacher_id, request.name)
    except ManagementError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": info.class_id,
        "class_id": info.class_id,
        "name": info.name,
        "invite_code": info.invite_code,
        "teacher_id": info.teacher_id,
    }


class ClassJoinCompatRequest(BaseModel):
    user_id: int = Field(gt=0)
    invite_code: str = Field(min_length=1, max_length=20)


@router.post("/class/join")
def join_class_compat(request: ClassJoinCompatRequest):
    """包装队员3 join_class，直接返回班级对象（前端 classState.studentClass = data）"""
    from backend.management.class_service import join_class
    from backend.management.exceptions import ManagementError
    try:
        result = join_class(request.user_id, request.invite_code)
    except ManagementError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    info = result.class_info
    return {
        "id": info.class_id,
        "class_id": info.class_id,
        "name": info.name,
        "invite_code": info.invite_code,
        "teacher_id": info.teacher_id,
        "already_joined": result.already_joined,
    }
