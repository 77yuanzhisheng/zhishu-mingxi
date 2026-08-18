"""Tests for safe, refreshable OpenAI-compatible LLM configuration."""

from __future__ import annotations

import logging

import httpx

from backend.chat.llm import OpenAICompatibleLLM


def test_env_file_overrides_stale_process_key_and_builds_bearer_header(
    tmp_path, monkeypatch, caplog
):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENAI_BASE_URL=https://api.siliconflow.cn/v1\n"
        "OPENAI_CHAT_MODEL=Qwen/Qwen3-8B\n"
        "OPENAI_API_KEY=sk-current-secret-value\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-stale-process-key")
    monkeypatch.delenv("OPENAI_ENABLE_THINKING", raising=False)
    monkeypatch.delenv("OPENAI_MAX_TOKENS", raising=False)
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "测试成功"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    caplog.set_level(logging.INFO, logger="backend.chat.llm")
    llm = OpenAICompatibleLLM()
    llm.ensure_available()
    answer = llm.generate([{"role": "user", "content": "你好"}])

    assert answer == "测试成功"
    assert captured["url"] == "https://api.siliconflow.cn/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-current-secret-value"
    assert captured["json"]["model"] == "Qwen/Qwen3-8B"
    assert captured["json"]["max_tokens"] == 1024
    assert "enable_thinking" not in captured["json"]
    assert "sk-current-secret-value" not in caplog.text
    assert "key_exists=True" in caplog.text
    assert "key_length=23" in caplog.text
    assert "key_prefix=sk-cur" in caplog.text
