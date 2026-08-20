"""Regression tests for multi-turn context management."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.llm import LLMClient
from backend.chat.exceptions import ChatSessionAccessError
from backend.chat.models import ChatRequest
from backend.chat.rag import RAGAdapter
from backend.chat.repository import ChatRepository
from backend.chat.router import get_chat_service, router as chat_router
from backend.chat.service import ChatService
from backend.learning.database import connection_scope
from backend.learning.router import router as learning_router
from backend.learning.service import create_user


class RecordingLLM(LLMClient):
    def __init__(self):
        self.calls: list[list[dict[str, str]]] = []

    def ensure_available(self) -> None:
        return None

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        user_messages = [message["content"] for message in messages if message["role"] == "user"]
        return f"回答：{user_messages[-1]}"

    def stream(self, messages: list[dict[str, str]]):
        self.calls.append(messages)
        user_messages = [message["content"] for message in messages if message["role"] == "user"]
        yield "回答："
        yield user_messages[-1]


class EmptyRAG(RAGAdapter):
    def search(self, query: str):
        return [], "no_results"


def build_service(database_path):
    llm = RecordingLLM()
    service = ChatService(
        repository=ChatRepository(database_path),
        llm=llm,
        rag=EmptyRAG(),
    )
    return service, llm


def test_new_session_reuses_history_and_persists_messages(tmp_path):
    database_path = tmp_path / "chat.db"
    user_id = create_user("学生甲", database_path=database_path)
    service, llm = build_service(database_path)

    first = service.chat(
        ChatRequest(user_id=user_id, message="德摩根律是什么？", node_id="pl_02_02")
    )
    second = service.chat(
        ChatRequest(
            user_id=user_id,
            session_id=first.session_id,
            message="能举个例子吗？",
            node_ids=["pl_02_02"],
        )
    )

    assert second.session_id == first.session_id
    assert any(
        message["content"] == "德摩根律是什么？" for message in llm.calls[1]
    )
    messages = service.repository.get_messages(first.session_id)
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert all(message["node_ids"] == ["pl_02_02"] for message in messages)


def test_different_sessions_do_not_share_context(tmp_path):
    database_path = tmp_path / "isolated.db"
    user_id = create_user("学生乙", database_path=database_path)
    service, llm = build_service(database_path)
    first = service.chat(ChatRequest(user_id=user_id, message="会话A的秘密"))
    second = service.chat(ChatRequest(user_id=user_id, message="会话B的问题"))

    assert first.session_id != second.session_id
    second_prompt = "\n".join(message["content"] for message in llm.calls[1])
    assert "会话A的秘密" not in second_prompt

    other_user_id = create_user("另一位学生", database_path=database_path)
    with pytest.raises(ChatSessionAccessError):
        service.chat(
            ChatRequest(
                user_id=other_user_id,
                session_id=first.session_id,
                message="尝试读取别人的会话",
            )
        )


def test_topic_switch_hint_is_non_blocking(tmp_path):
    database_path = tmp_path / "topic.db"
    user_id = create_user("学生丙", database_path=database_path)
    service, _ = build_service(database_path)
    first = service.chat(
        ChatRequest(user_id=user_id, message="讲讲德摩根律", node_id="pl_02_02")
    )
    same_topic = service.chat(
        ChatRequest(
            user_id=user_id,
            session_id=first.session_id,
            message="继续",
            node_id="pl_02_02",
        )
    )
    switched = service.chat(
        ChatRequest(
            user_id=user_id,
            session_id=first.session_id,
            message="现在学习关系",
            node_id="rel_01_01",
        )
    )

    assert same_topic.topic_switch_hint is None
    assert "pl_02_02" in switched.topic_switch_hint
    assert "rel_01_01" in switched.topic_switch_hint


def test_compression_only_after_ten_rounds_and_keeps_recent_context(tmp_path):
    database_path = tmp_path / "compression.db"
    user_id = create_user("学生丁", database_path=database_path)
    service, llm = build_service(database_path)
    session_id = None
    responses = []

    for round_number in range(1, 12):
        message = (
            "我不懂德摩根律，为什么这样变换？"
            if round_number == 1
            else f"第{round_number}轮问题"
        )
        response = service.chat(
            ChatRequest(
                user_id=user_id,
                session_id=session_id,
                message=message,
                node_id="pl_02_02",
            )
        )
        session_id = response.session_id
        responses.append(response)

    assert all(not response.context.compressed for response in responses[:10])
    assert responses[9].context.history_messages_used == 19
    assert responses[10].context.compressed is True
    assert responses[10].context.summary_available is True
    assert responses[10].context.history_messages_used <= 9  # 摘要 + 最近 4 轮

    summary = service.repository.get_summary(session_id)
    assert "正在学习的知识点" in summary["content"]
    assert "已讨论的重要概念" in summary["content"]
    assert "用户暴露的薄弱点" in summary["content"]
    assert "仍未解决的问题" in summary["content"]
    assert "pl_02_02" in summary["content"]
    assert "第10轮问题" in "\n".join(item["content"] for item in llm.calls[-1])
    assert len(service.repository.get_messages(session_id)) == 22


def test_chat_router_and_existing_learning_api_work_together(tmp_path, monkeypatch):
    database_path = tmp_path / "api.db"
    monkeypatch.setenv("LEARNING_DB_PATH", str(database_path))
    user_id = create_user("接口用户", database_path=database_path)
    service, _ = build_service(database_path)
    app = FastAPI()
    app.include_router(learning_router)
    app.include_router(chat_router)
    app.dependency_overrides[get_chat_service] = lambda: service
    client = TestClient(app)

    chat_response = client.post(
        "/chat",
        json={"user_id": user_id, "message": "什么是集合？", "node_id": "st_01_01"},
    )
    assert chat_response.status_code == 200
    assert chat_response.json()["session_id"] > 0
    mastery_response = client.post(
        "/api/learning/update-mastery",
        json={"user_id": user_id, "node_id": "st_01_01", "correct": True},
    )
    assert mastery_response.status_code == 200
    report_response = client.get("/api/learning/report", params={"user_id": user_id})
    assert report_response.status_code == 200
    assert report_response.json()["node_mastery"][0]["node_id"] == "st_01_01"

    with connection_scope(database_path) as connection:
        stored = connection.execute(
            "SELECT node_ids FROM messages ORDER BY id LIMIT 1"
        ).fetchone()
    assert json.loads(stored["node_ids"]) == ["st_01_01"]


def test_stream_chat_emits_meta_deltas_done_and_persists_answer(tmp_path):
    database_path = tmp_path / "stream.db"
    user_id = create_user("流式用户", database_path=database_path)
    service, _ = build_service(database_path)

    events = list(
        service.stream_chat(
            ChatRequest(user_id=user_id, message="什么是图？", node_id="gt_01_01")
        )
    )

    assert [event["type"] for event in events] == ["meta", "delta", "delta", "done"]
    assert "".join(event["content"] for event in events if event["type"] == "delta") == "回答：什么是图？"
    assert events[-1]["answer"] == "回答：什么是图？"
    messages = service.repository.get_messages(events[0]["session_id"])
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "回答：什么是图？"
