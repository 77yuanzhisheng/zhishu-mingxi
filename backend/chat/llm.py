"""Explicit adapter for an OpenAI-compatible chat-completions endpoint."""

from __future__ import annotations

import os
import json
import logging
import time
from collections.abc import Iterator
from typing import Protocol

import httpx
from dotenv import find_dotenv, load_dotenv

from backend.chat.exceptions import LLMUnavailableError


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def ensure_available(self) -> None: ...

    def generate(self, messages: list[dict[str, str]]) -> str: ...

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]: ...


class OpenAICompatibleLLM:
    def __init__(self) -> None:
        self.api_key = ""
        self.base_url = ""
        self.model = ""
        self.timeout = 60.0
        self.max_tokens = 1024
        self.max_retries = 2
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
        self.max_retries = max(0, min(int(os.getenv("LLM_MAX_RETRIES", "2")), 4))
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
        headers = self._headers()
        payload = self._payload(messages)
        answer = None
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 20.0)),
                )
                if response.status_code in retryable_statuses and attempt < self.max_retries:
                    logger.warning(
                        "LLM temporary HTTP %s; retry %s/%s",
                        response.status_code,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(min(2 ** attempt, 4))
                    continue
                response.raise_for_status()
                answer = response.json()["choices"][0]["message"]["content"]
                break
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise LLMUnavailableError(f"LLM 调用失败：{exc}") from exc
                logger.warning(
                    "LLM network timeout; retry %s/%s",
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(min(2 ** attempt, 4))
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                raise LLMUnavailableError(f"LLM 调用失败：{exc}") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise LLMUnavailableError("LLM 返回了空回答")
        return answer.strip()

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Yield content deltas from an OpenAI-compatible SSE response."""

        self.ensure_available()
        headers = self._headers()
        payload = self._payload(messages)
        payload["stream"] = True
        retryable_statuses = {429, 500, 502, 503, 504}
        produced_content = False

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 20.0)),
                ) as response:
                    if response.status_code in retryable_statuses and attempt < self.max_retries:
                        logger.warning(
                            "LLM stream temporary HTTP %s; retry %s/%s",
                            response.status_code,
                            attempt + 1,
                            self.max_retries,
                        )
                        time.sleep(min(2 ** attempt, 4))
                        continue
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                            content = event["choices"][0].get("delta", {}).get("content")
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        if isinstance(content, str) and content:
                            produced_content = True
                            yield content
                if produced_content:
                    return
                if attempt >= self.max_retries:
                    break
                logger.warning(
                    "LLM stream returned no content; retry %s/%s",
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(min(2 ** attempt, 4))
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if produced_content or attempt >= self.max_retries:
                    raise LLMUnavailableError(f"LLM 流式调用失败：{exc}") from exc
                logger.warning(
                    "LLM stream network timeout; retry %s/%s",
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(min(2 ** attempt, 4))
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(f"LLM 流式调用失败：{exc}") from exc

        raise LLMUnavailableError("LLM 流式接口未返回回答")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "your_api_key_here":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, messages: list[dict[str, str]]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        return payload
