"""OpenAI-compatible chat adapter with Spark MaaS as the production provider."""

from __future__ import annotations

import json
import logging
import os
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
    """Small dependency-free client for Spark MaaS and compatible endpoints."""

    def __init__(self) -> None:
        self.provider = "spark"
        self.api_key = ""
        self.base_url = ""
        self.model = ""
        self.timeout = 60.0
        self.max_tokens = 768
        self.max_retries = 2
        self.max_input_chars = 0
        self.enable_thinking: bool | None = None
        self._fallback_active = False
        self._fallback: dict[str, str] = {}
        self._refresh_config()

    @staticmethod
    def _bool_env(name: str) -> bool | None:
        value = os.getenv(name, "").strip().lower()
        if not value:
            return None
        return value in {"1", "true", "yes", "on"}

    def _refresh_config(self) -> None:
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path=dotenv_path, override=True)

        self.provider = os.getenv("LLM_PROVIDER", "spark").strip().lower() or "spark"
        self.timeout = max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "60")))
        self.max_tokens = max(1, int(os.getenv("LLM_MAX_TOKENS", "768")))
        self.max_retries = max(0, min(int(os.getenv("LLM_MAX_RETRIES", "2")), 4))
        self.max_input_chars = max(0, int(os.getenv("LLM_MAX_INPUT_CHARS", "0")))
        thinking_name = (
            "SPARK_ENABLE_THINKING"
            if self.provider == "spark"
            else "OPENAI_ENABLE_THINKING"
        )
        self.enable_thinking = self._bool_env(thinking_name)
        if self.enable_thinking is None:
            self.enable_thinking = self._bool_env("LLM_ENABLE_THINKING")
        self._fallback_active = False

        openai = {
            "api_key": os.getenv("OPENAI_API_KEY", "").strip(),
            "base_url": os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/"),
            "model": os.getenv("OPENAI_CHAT_MODEL", "").strip(),
        }
        spark = {
            "api_key": os.getenv("SPARK_API_KEY", "").strip(),
            "base_url": os.getenv("SPARK_BASE_URL", "").strip().rstrip("/"),
            "model": os.getenv("SPARK_MODEL", "").strip(),
        }
        # Keep the old name as a migration-only fallback for existing deployments.
        if not spark["model"]:
            spark["model"] = os.getenv("SPARK_CHAT_MODEL", "").strip()

        primary = spark if self.provider == "spark" else openai
        fallback = openai if self.provider == "spark" else spark
        self.api_key, self.base_url, self.model = (
            primary["api_key"], primary["base_url"], primary["model"]
        )
        logger.info(
            "LLM config: base_url=%s model=%s configured=%s",
            self.base_url,
            self.model,
            bool(self.base_url and self.model),
        )
        self._fallback = fallback

    def ensure_available(self) -> None:
        self._refresh_config()
        if not self.base_url or not self.model:
            provider = "星火 MaaS" if self.provider == "spark" else "OpenAI 兼容服务"
            raise LLMUnavailableError(f"{provider} 尚未配置，请检查 API 地址和模型名称")

    def _fallback_ready(self) -> bool:
        return bool(
            self._fallback.get("api_key")
            and self._fallback.get("api_key") != "your_api_key_here"
            and self._fallback.get("base_url")
            and self._fallback.get("model")
        )

    def _activate_fallback(self) -> None:
        self.api_key = self._fallback["api_key"]
        self.base_url = self._fallback["base_url"]
        self.model = self._fallback["model"]
        self._fallback_active = True
        self.provider = "openai" if self.provider == "spark" else "spark"
        logger.warning("Primary LLM request failed; using configured fallback provider")

    def _bounded_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        if not self.max_input_chars:
            return messages
        if not messages:
            return []

        system_index = next(
            (index for index, message in enumerate(messages) if message.get("role") == "system"),
            None,
        )
        latest_user_index = next(
            (index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
            None,
        )
        boundary = [index for index in (system_index, latest_user_index) if index is not None]
        boundary = list(dict.fromkeys(boundary))
        mandatory = sum(len(str(messages[index].get("content", ""))) for index in boundary)

        # Keep both boundaries intact whenever possible. Middle turns are the
        # first content that may be clipped or dropped.
        if mandatory <= self.max_input_chars:
            remaining = self.max_input_chars - mandatory
            middle = [index for index in range(len(messages)) if index not in boundary]
            selected = set(boundary)
            truncated: dict[int, int] = {}
            for index in reversed(middle):
                content_length = len(str(messages[index].get("content", "")))
                if content_length <= remaining:
                    selected.add(index)
                    remaining -= content_length
                elif remaining:
                    selected.add(index)
                    truncated[index] = remaining
                    remaining = 0
            result: list[dict[str, str]] = []
            for index, message in enumerate(messages):
                if index not in selected:
                    continue
                item = dict(message)
                if index in truncated:
                    item["content"] = str(item.get("content", ""))[:truncated[index]]
                result.append(item)
            return result

        # When the boundaries cannot fit together, the latest question gets
        # first claim on the budget so the model always receives the task.
        latest_item = dict(messages[latest_user_index]) if latest_user_index is not None else None
        system_item = dict(messages[system_index]) if system_index is not None else None
        remaining = self.max_input_chars
        if latest_item is not None:
            latest_content = str(latest_item.get("content", ""))
            latest_item["content"] = latest_content[:remaining]
            remaining -= len(latest_item["content"])
        if system_item is not None and remaining:
            system_content = str(system_item.get("content", ""))
            system_item["content"] = system_content[:remaining]

        result = []
        if system_item is not None:
            result.append((system_index, system_item))
        if latest_item is not None and latest_user_index != system_index:
            result.append((latest_user_index, latest_item))
        return [item for _, item in sorted(result)]

    def generate(self, messages: list[dict[str, str]]) -> str:
        self._refresh_config()
        if not self.base_url or not self.model:
            self.ensure_available()
        try:
            return self._generate_once(messages)
        except LLMUnavailableError:
            if not self._fallback_ready():
                raise
            self._activate_fallback()
            return self._generate_once(messages)

    def _generate_once(self, messages: list[dict[str, str]]) -> str:
        payload = self._payload(messages)
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 20.0)),
                )
                if response.status_code in retryable and attempt < self.max_retries:
                    time.sleep(min(2**attempt, 4))
                    continue
                response.raise_for_status()
                answer = response.json()["choices"][0]["message"]["content"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("empty response")
                return answer.strip()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise LLMUnavailableError(f"LLM request failed: {exc}") from exc
                time.sleep(min(2**attempt, 4))
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                raise LLMUnavailableError(f"LLM request failed: {exc}") from exc
        raise LLMUnavailableError("LLM request failed")

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        self._refresh_config()
        if not self.base_url or not self.model:
            self.ensure_available()
        produced: list[str] = []
        try:
            for chunk in self._stream_once(messages):
                produced.append(chunk)
                yield chunk
        except LLMUnavailableError:
            if produced or not self._fallback_ready():
                raise
            self._activate_fallback()
            yield from self._stream_once(messages)

    def _stream_once(self, messages: list[dict[str, str]]) -> Iterator[str]:
        payload = self._payload(messages)
        payload["stream"] = True
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 20.0)),
                ) as response:
                    if response.status_code in retryable and attempt < self.max_retries:
                        time.sleep(min(2**attempt, 4))
                        continue
                    response.raise_for_status()
                    produced = False
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            content = json.loads(data)["choices"][0]["delta"].get("content")
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        if isinstance(content, str) and content:
                            produced = True
                            yield content
                    if produced:
                        return
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise LLMUnavailableError(f"LLM stream failed: {exc}") from exc
                time.sleep(min(2**attempt, 4))
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(f"LLM stream failed: {exc}") from exc
        raise LLMUnavailableError("LLM stream returned no content")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "your_api_key_here":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, messages: list[dict[str, str]]) -> dict:
        payload = {
            "model": self.model,
            "messages": self._bounded_messages(messages),
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        if self.enable_thinking is not None and self.provider != "spark":
            payload["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        return payload
