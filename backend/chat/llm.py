"""Explicit adapter for an OpenAI-compatible chat-completions endpoint."""

from __future__ import annotations

import os
import logging
from typing import Protocol

import httpx
from dotenv import find_dotenv, load_dotenv

from backend.chat.exceptions import LLMUnavailableError


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def ensure_available(self) -> None: ...

    def generate(self, messages: list[dict[str, str]]) -> str: ...


class OpenAICompatibleLLM:
    def __init__(self) -> None:
        self.api_key = ""
        self.base_url = ""
        self.model = ""
        self.timeout = 60.0
        self.max_tokens = 1024
        self.enable_thinking: bool | None = None
        self._refresh_config()

    def _refresh_config(self) -> None:
        """Reload .env so a cached service never keeps stale credentials."""

        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path=dotenv_path, override=True)
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
        self.model = os.getenv("OPENAI_CHAT_MODEL", "").strip()
        self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))
        thinking_setting = os.getenv("OPENAI_ENABLE_THINKING", "").strip().lower()
        self.enable_thinking = (
            thinking_setting in {"1", "true", "yes", "on"}
            if thinking_setting
            else None
        )
        logger.info(
            "LLM config: base_url=%s model=%s key_exists=%s key_length=%d key_prefix=%s",
            self.base_url,
            self.model,
            bool(self.api_key),
            len(self.api_key),
            self.api_key[:6] if self.api_key else "",
        )

    def ensure_available(self) -> None:
        self._refresh_config()
        if not self.base_url or not self.model:
            raise LLMUnavailableError(
                "LLM 尚未配置：请设置 OPENAI_BASE_URL 和 OPENAI_CHAT_MODEL"
            )

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.ensure_available()
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "your_api_key_here":
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMUnavailableError(f"LLM 调用失败：{exc}") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise LLMUnavailableError("LLM 返回了空回答")
        return answer.strip()
