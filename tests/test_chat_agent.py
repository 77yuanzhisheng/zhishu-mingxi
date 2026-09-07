"""Xingchen Agent primary-channel and Qwen3 fallback regression tests."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.agent import XingchenAgentClient, XingchenAgentUnavailableError
from backend.chat.models import ChatRequest
from backend.chat.repository import ChatRepository
from backend.chat.router import get_chat_service, router as chat_router
from backend.chat.service import ChatService
from backend.learning.service import (
    create_answer_event,
    create_user,
    get_learning_report,
)


class RecordingLLM:
    def __init__(self, answer: str = "Qwen3 fallback answer") -> None:
        self.answer = answer
        self.available_calls = 0
        self.calls: list[list[dict[str, str]]] = []

    def ensure_available(self) -> None:
        self.available_calls += 1

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.answer


class CountingRAG:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str):
        self.calls.append(query)
        return [], "no_results"


class RecordingAgent:
    def __init__(self, answer: str = "星辰 Agent answer") -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return True

    @property
    def is_configured(self) -> bool:
        return True

    def configuration_fallback_reason(self) -> str | None:
        return None

    def generate(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.answer


def configured_client(post) -> XingchenAgentClient:
    return XingchenAgentClient(
        enabled=True,
        api_url="https://agent.example.test/chat/completions",
        api_key="fake-api-key",
        api_secret="fake-api-secret",
        flow_id="fake-flow-id",
        bot_id="workflow",
        timeout=2,
        post=post,
    )


def build_service(database_path, agent, *, learning_context_provider=None):
    llm = RecordingLLM()
    rag = CountingRAG()
    service = ChatService(
        repository=ChatRepository(database_path),
        llm=llm,
        rag=rag,
        agent=agent,
        learning_context_provider=learning_context_provider,
    )
    return service, llm, rag


def successful_response(url: str, answer: str = "星辰回答") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "message": "Success",
            "choices": [
                {
                    "delta": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
        },
        request=httpx.Request("POST", url),
    )


def test_agent_success_skips_fallback_and_persists_nodes_once(tmp_path):
    database_path = tmp_path / "agent-success.db"
    user_id = create_user("Agent 学生", database_path=database_path)
    agent = RecordingAgent()
    service, llm, rag = build_service(database_path, agent)

    response = service.chat(
        ChatRequest(user_id=user_id, message="解释德摩根律", node_id="pl_02_02")
    )

    assert response.provider == "agent"
    assert response.fallback_reason is None
    assert response.answer == "星辰 Agent answer"
    assert response.node_ids == ["pl_02_02"]
    assert response.references == []
    assert response.context.rag_used is False
    assert response.context.rag_status == "not_used_agent"
    assert llm.available_calls == 0
    assert llm.calls == []
    assert rag.calls == []
    messages = service.repository.get_messages(response.session_id)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert all(message["node_ids"] == ["pl_02_02"] for message in messages)
    report = get_learning_report(user_id, database_path)
    assert report.node_insights[0].chat_count == 1
    assert report.node_insights[0].graded_question_count == 0


def test_unconfigured_agent_falls_back_without_duplicate_messages(tmp_path):
    database_path = tmp_path / "agent-unconfigured.db"
    user_id = create_user("降级学生", database_path=database_path)
    service, llm, rag = build_service(
        database_path, XingchenAgentClient(enabled=False)
    )

    response = service.chat(ChatRequest(user_id=user_id, message="什么是集合？"))

    assert response.provider == "fallback"
    assert response.fallback_reason == "星辰 Agent 未配置"
    assert response.answer == "Qwen3 fallback answer"
    assert len(llm.calls) == 1
    assert rag.calls == ["什么是集合？"]
    messages = service.repository.get_messages(response.session_id)
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_timeout_falls_back_through_chat_endpoint(tmp_path):
    database_path = tmp_path / "agent-timeout.db"
    user_id = create_user("超时学生", database_path=database_path)

    def timeout_post(url, **kwargs):
        raise httpx.ReadTimeout("timed out", request=httpx.Request("POST", url))

    service, llm, _ = build_service(database_path, configured_client(timeout_post))
    app = FastAPI()
    app.include_router(chat_router)
    app.dependency_overrides[get_chat_service] = lambda: service

    response = TestClient(app).post(
        "/chat", json={"user_id": user_id, "message": "请解释主范式"}
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "fallback"
    assert response.json()["fallback_reason"] == "星辰 Agent 请求超时"
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    ("response_factory", "expected_reason"),
    [
        (
            lambda url: httpx.Response(
                503,
                text="unavailable",
                request=httpx.Request("POST", url),
            ),
            "星辰 Agent 服务暂不可用",
        ),
        (
            lambda url: httpx.Response(
                200,
                text="not-json-or-sse",
                request=httpx.Request("POST", url),
            ),
            "星辰 Agent 返回异常",
        ),
        (
            lambda url: httpx.Response(
                200,
                json={"code": 0, "choices": [{"delta": {"content": ""}}]},
                request=httpx.Request("POST", url),
            ),
            "星辰 Agent 返回异常",
        ),
        (
            lambda url: httpx.Response(
                200,
                json={"code": 22302, "message": "node failed"},
                request=httpx.Request("POST", url),
            ),
            "星辰 Agent 服务暂不可用",
        ),
    ],
)
def test_agent_response_failures_trigger_fallback(
    tmp_path, response_factory, expected_reason
):
    database_path = tmp_path / "agent-error.db"
    user_id = create_user("异常降级学生", database_path=database_path)

    def fake_post(url, **kwargs):
        return response_factory(url)

    service, llm, _ = build_service(database_path, configured_client(fake_post))
    response = service.chat(ChatRequest(user_id=user_id, message="测试异常降级"))

    assert response.provider == "fallback"
    assert response.fallback_reason == expected_reason
    assert len(llm.calls) == 1
    assert [
        message["role"] for message in service.repository.get_messages(response.session_id)
    ] == ["user", "assistant"]


def test_payload_history_and_compact_learning_context(tmp_path):
    database_path = tmp_path / "agent-payload.db"
    user_id = create_user("学情注入学生", database_path=database_path)
    captured: list[dict[str, Any]] = []

    def fake_post(url, *, headers, json, timeout):
        captured.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return successful_response(url, answer=f"第{len(captured)}次星辰回答")

    service, _, _ = build_service(database_path, configured_client(fake_post))
    first = service.chat(
        ChatRequest(user_id=user_id, message="德摩根律是什么？", node_id="pl_02_02")
    )
    for index, correct in enumerate([True, True, False], start=1):
        create_answer_event(
            user_id=user_id,
            question_id=f"graded-{index}",
            question_type="single",
            module="命题逻辑",
            node_id="pl_02_02",
            is_correct=correct,
            duration_ms=100,
            answer_text="A",
            database_path=database_path,
        )
    question = "请再给我讲一下德摩根律。"
    second = service.chat(
        ChatRequest(
            user_id=user_id,
            session_id=first.session_id,
            message=question,
            node_id="pl_02_02",
        )
    )

    payload = captured[1]["json"]
    assert second.provider == "agent"
    assert payload["flow_id"] == "fake-flow-id"
    assert payload["uid"] == str(user_id)
    assert payload["chat_id"] == str(first.session_id)
    assert payload["stream"] is False
    assert payload["ext"] == {"bot_id": "workflow", "caller": "workflow"}
    assert payload["history"] == [
        {
            "role": "user",
            "content_type": "text",
            "content": "德摩根律是什么？",
        },
        {
            "role": "assistant",
            "content_type": "text",
            "content": "第1次星辰回答",
        },
    ]
    assert all(item["content"] != question for item in payload["history"])
    agent_input = payload["parameters"]["AGENT_USER_INPUT"]
    assert "【当前学生学情】" in agent_input
    assert "近期关注：pl_02_02" in agent_input
    assert "近期重复追问：pl_02_02" in agent_input
    assert "命题逻辑已判定做题正确率：67%（3题）" in agent_input
    assert agent_input.count(question) == 1
    assert captured[1]["headers"]["Authorization"] == (
        "Bearer fake-api-key:fake-api-secret"
    )


def test_agent_still_works_without_learning_evidence(tmp_path):
    database_path = tmp_path / "agent-no-learning.db"
    user_id = create_user("无学情学生", database_path=database_path)
    agent = RecordingAgent()
    service, llm, _ = build_service(database_path, agent)

    response = service.chat(ChatRequest(user_id=user_id, message="你好，介绍一下你自己"))

    assert response.provider == "agent"
    assert llm.calls == []
    agent_input = agent.calls[0]["user_input"]
    assert "【当前学生学情】" not in agent_input
    assert "你好，介绍一下你自己" in agent_input


def test_parser_accepts_official_json_and_sse_chunks():
    url = "https://agent.example.test/chat/completions"
    official = successful_response(url, "完整回答")
    sse = httpx.Response(
        200,
        text=(
            'data: {"code":0,"choices":[{"delta":{"content":"分段"}}]}\n\n'
            'data: {"code":0,"choices":[{"delta":{"content":"回答"}}]}\n\n'
            "data: [DONE]\n"
        ),
        headers={"Content-Type": "text/event-stream"},
        request=httpx.Request("POST", url),
    )

    assert XingchenAgentClient._parse_response(official) == "完整回答"
    assert XingchenAgentClient._parse_response(sse) == "分段回答"


def test_agent_reuses_compressed_summary_and_sends_valid_history(tmp_path):
    database_path = tmp_path / "agent-compression.db"
    user_id = create_user("压缩上下文学生", database_path=database_path)
    agent = RecordingAgent()
    service, _, _ = build_service(database_path, agent)
    session_id = None

    for round_number in range(1, 12):
        response = service.chat(
            ChatRequest(
                user_id=user_id,
                session_id=session_id,
                message=f"第{round_number}轮问题",
            )
        )
        session_id = response.session_id

    last_call = agent.calls[-1]
    assert "以下是较早对话的结构化摘要" in last_call["user_input"]
    assert last_call["user_input"].count("第11轮问题") == 1
    converted = XingchenAgentClient.build_history(last_call["history"])
    assert converted[0]["role"] == "user"
    assert converted[-1]["role"] == "assistant"
    assert all(
        item["role"] != converted[index - 1]["role"]
        for index, item in enumerate(converted[1:], start=1)
    )


def test_debug_logging_reports_execute_id_shape_without_sensitive_data(
    monkeypatch, caplog
):
    monkeypatch.setenv("XINGCHEN_DEBUG", "true")
    url = "https://agent.example.test/chat/completions"

    def fake_post(request_url, **kwargs):
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "Success",
                "data": [{"execute_id": "private-execute-id"}],
            },
            request=httpx.Request("POST", request_url),
        )

    client = configured_client(fake_post)
    caplog.set_level(logging.DEBUG, logger="backend.chat.agent")
    with pytest.raises(XingchenAgentUnavailableError) as raised:
        client.generate(
            user_id=1,
            session_id=2,
            user_input="完整私密问题",
            history=[{"role": "user", "content": "完整私密历史"}],
        )

    assert raised.value.fallback_reason == "星辰 Agent 返回异常"
    assert raised.value.branch == "response_no_answer"
    assert "status=200" in caplog.text
    assert "content_type=application/json" in caplog.text
    assert "top_level_keys=['code', 'data', 'message']" in caplog.text
    assert "code=0" in caplog.text
    assert "message=Success" in caplog.text
    assert "data_type=list" in caplog.text
    assert "data_has_execute_id=True" in caplog.text
    assert "choices_present=False" in caplog.text
    assert "content_present=False" in caplog.text
    assert "answer_present=False" in caplog.text
    assert "branch=response_no_answer" in caplog.text
    for secret in (
        "fake-api-key",
        "fake-api-secret",
        "private-execute-id",
        "完整私密问题",
        "完整私密历史",
        "Authorization",
    ):
        assert secret not in caplog.text


def test_dotenv_refresh_only_applies_xingchen_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEARNING_DB_PATH", "isolated-test.db")
    monkeypatch.setenv("XINGCHEN_AGENT_ENABLED", "false")
    (tmp_path / ".env").write_text(
        "XINGCHEN_AGENT_ENABLED=true\n"
        "XINGCHEN_API_KEY=test-key\n"
        "XINGCHEN_API_SECRET=test-secret\n"
        "XINGCHEN_FLOW_ID=test-flow\n"
        "LEARNING_DB_PATH=must-not-win.db\n",
        encoding="utf-8",
    )

    client = XingchenAgentClient()

    assert client.enabled is True
    assert client.is_configured is True
    assert os.environ["LEARNING_DB_PATH"] == "isolated-test.db"
