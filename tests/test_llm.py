from __future__ import annotations

import httpx

from backend.chat.llm import OpenAICompatibleLLM


def env(tmp_path, monkeypatch, text):
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)


def test_spark_is_primary_and_uses_spark_settings(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, """LLM_PROVIDER=spark
SPARK_BASE_URL=https://spark.example/v1/
SPARK_API_KEY=secret
SPARK_MODEL=qwen3-32b-ft
LLM_MAX_TOKENS=768
LLM_ENABLE_THINKING=false
""")
    seen = {}
    def post(url, *, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    client = OpenAICompatibleLLM()
    assert client.provider == "spark"
    assert client.generate([{"role": "user", "content": "??"}]) == "ok"
    assert seen["url"] == "https://spark.example/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert seen["json"]["model"] == "qwen3-32b-ft"
    assert seen["json"]["max_tokens"] == 768
    assert "chat_template_kwargs" not in seen["json"]


def test_thinking_can_be_enabled_for_compatible_backend(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, """LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost/v1
OPENAI_CHAT_MODEL=test
OPENAI_ENABLE_THINKING=true
""")
    client = OpenAICompatibleLLM()
    assert client._payload([])["chat_template_kwargs"] == {"enable_thinking": True}


def test_context_is_bounded_preserving_system_and_latest_user(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, """LLM_PROVIDER=spark
SPARK_BASE_URL=http://localhost/v1
SPARK_MODEL=test
LLM_MAX_INPUT_CHARS=100
""")
    client = OpenAICompatibleLLM()
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old " * 30},
        {"role": "assistant", "content": "old answer " * 30},
        {"role": "user", "content": "latest"},
    ]
    bounded = client._bounded_messages(messages)
    assert bounded[0] == messages[0]
    assert bounded[-1] == messages[-1]
    assert sum(len(m["content"]) for m in bounded) <= 100



def test_context_budget_keeps_latest_user_when_system_is_too_long(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, """LLM_PROVIDER=spark
SPARK_BASE_URL=http://localhost/v1
SPARK_MODEL=test
LLM_MAX_INPUT_CHARS=100
""")
    client = OpenAICompatibleLLM()
    messages = [
        {"role": "system", "content": "S" * 160},
        {"role": "user", "content": "LATEST_USER_MUST_SURVIVE"},
    ]

    bounded = client._bounded_messages(messages)
    contents = [message["content"] for message in bounded]

    assert sum(len(content) for content in contents) <= 100
    assert contents[0]
    assert contents[-1]
    assert "LATEST_USER_MUST_SURVIVE" in contents[-1]

def test_transient_timeout_is_retried(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, """LLM_PROVIDER=spark
SPARK_BASE_URL=http://localhost/v1
SPARK_MODEL=test
LLM_MAX_RETRIES=1
""")
    attempts = 0
    def post(url, *, headers, json, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("temporary", request=httpx.Request("POST", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("backend.chat.llm.time.sleep", lambda _: None)
    assert OpenAICompatibleLLM().generate([]) == "ok"
    assert attempts == 2


def test_spark_failure_keeps_legacy_openai_fallback(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, """LLM_PROVIDER=openai
OPENAI_BASE_URL=http://primary/v1
OPENAI_CHAT_MODEL=primary
OPENAI_API_KEY=primary-key
SPARK_BASE_URL=http://spark/v1
SPARK_CHAT_MODEL=4.0Ultra
SPARK_API_KEY=spark-key
LLM_MAX_RETRIES=0
""")
    urls = []
    def post(url, *, headers, json, timeout):
        urls.append((url, headers["Authorization"]))
        if "primary" in url:
            return httpx.Response(503, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "fallback"}}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    assert OpenAICompatibleLLM().generate([]) == "fallback"
    assert urls == [("http://primary/v1/chat/completions", "Bearer primary-key"), ("http://spark/v1/chat/completions", "Bearer spark-key")]
