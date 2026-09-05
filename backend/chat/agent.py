"""Client for the iFlytek Xingchen workflow Agent API."""

from __future__ import annotations

import json
import logging
import os
from time import monotonic
from typing import Any, Callable, Protocol

import httpx
from dotenv import dotenv_values, find_dotenv


logger = logging.getLogger(__name__)

DEFAULT_XINGCHEN_API_URL = (
    "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"
)


class XingchenAgentError(RuntimeError):
    """Base error raised by the Xingchen Agent adapter."""


class XingchenAgentUnavailableError(XingchenAgentError):
    """A recoverable Agent failure that should trigger the Qwen3 fallback."""

    def __init__(
        self,
        message: str,
        fallback_reason: str,
        *,
        branch: str = "unknown",
    ):
        super().__init__(message)
        self.fallback_reason = fallback_reason
        self.branch = branch


class AgentClient(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def is_configured(self) -> bool: ...

    def configuration_fallback_reason(self) -> str | None: ...

    def generate(
        self,
        *,
        user_id: int,
        session_id: int,
        user_input: str,
        history: list[dict[str, Any]],
    ) -> str: ...


class XingchenAgentClient:
    """Synchronous, environment-configured Xingchen workflow client."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        flow_id: str | None = None,
        bot_id: str | None = None,
        timeout: float | None = None,
        post: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self._overrides = {
            "enabled": enabled,
            "api_url": api_url,
            "api_key": api_key,
            "api_secret": api_secret,
            "flow_id": flow_id,
            "bot_id": bot_id,
            "timeout": timeout,
        }
        self._post = post or httpx.post
        self._enabled = False
        self.api_url = DEFAULT_XINGCHEN_API_URL
        self.api_key = ""
        self.api_secret = ""
        self.flow_id = ""
        self.bot_id = "workflow"
        self.timeout = 120.0
        self._debug_enabled = False
        self._refresh_config()

    @staticmethod
    def _parse_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _refresh_config(self) -> None:
        dotenv_path = find_dotenv(usecwd=True)
        dotenv_config = dotenv_values(dotenv_path) if dotenv_path else {}

        def config_value(name: str, default: Any = None) -> Any:
            # Keep the existing file-first Xingchen semantics so a corrected .env
            # takes effect even when a parent shell contains stale credentials.
            # Reading the mapping directly avoids globally overwriting unrelated
            # variables such as LEARNING_DB_PATH.
            file_value = dotenv_config.get(name)
            return file_value if file_value is not None else os.getenv(name, default)

        enabled_override = self._overrides["enabled"]
        self._enabled = (
            bool(enabled_override)
            if enabled_override is not None
            else self._parse_bool(config_value("XINGCHEN_AGENT_ENABLED"))
        )
        self.api_url = str(
            self._overrides["api_url"]
            if self._overrides["api_url"] is not None
            else config_value("XINGCHEN_API_URL", DEFAULT_XINGCHEN_API_URL)
        ).strip()
        self.api_key = str(
            self._overrides["api_key"]
            if self._overrides["api_key"] is not None
            else config_value("XINGCHEN_API_KEY", "")
        ).strip()
        self.api_secret = str(
            self._overrides["api_secret"]
            if self._overrides["api_secret"] is not None
            else config_value("XINGCHEN_API_SECRET", "")
        ).strip()
        self.flow_id = str(
            self._overrides["flow_id"]
            if self._overrides["flow_id"] is not None
            else config_value("XINGCHEN_FLOW_ID", "")
        ).strip()
        self.bot_id = str(
            self._overrides["bot_id"]
            if self._overrides["bot_id"] is not None
            else config_value("XINGCHEN_BOT_ID", "workflow")
        ).strip() or "workflow"
        timeout_value = (
            self._overrides["timeout"]
            if self._overrides["timeout"] is not None
            else config_value("XINGCHEN_TIMEOUT", "120")
        )
        try:
            self.timeout = max(0.1, float(timeout_value))
        except (TypeError, ValueError):
            self.timeout = 120.0
        self._debug_enabled = self._parse_bool(config_value("XINGCHEN_DEBUG"))
        if self._debug_enabled:
            logger.setLevel(logging.DEBUG)

        logger.info(
            "Xingchen config: enabled=%s flow_configured=%s "
            "key_configured=%s secret_configured=%s",
            self._enabled,
            bool(self.flow_id),
            bool(self.api_key),
            bool(self.api_secret),
        )

    @property
    def enabled(self) -> bool:
        self._refresh_config()
        return self._enabled

    @property
    def is_configured(self) -> bool:
        self._refresh_config()
        return bool(
            self._enabled
            and self.api_url
            and self.api_key
            and self.api_secret
            and self.flow_id
        )

    def configuration_fallback_reason(self) -> str | None:
        if self.is_configured:
            return None
        self._debug(
            "Xingchen exception branch: branch=configuration_not_ready "
            "error_type=XingchenAgentUnavailableError"
        )
        return "星辰 Agent 未配置"

    def _debug(self, message: str, *args: Any) -> None:
        if self._debug_enabled:
            logger.debug(message, *args)

    @staticmethod
    def build_history(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        expected_role = "user"
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            if not content.strip():
                continue
            if role != expected_role:
                continue
            history.append(
                {"role": role, "content_type": "text", "content": content}
            )
            expected_role = "assistant" if role == "user" else "user"
        if history and history[-1]["role"] == "user":
            history.pop()
        return history

    def build_payload(
        self,
        *,
        user_id: int,
        session_id: int,
        user_input: str,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "uid": str(user_id),
            "parameters": {"AGENT_USER_INPUT": user_input},
            "ext": {"bot_id": self.bot_id, "caller": "workflow"},
            "stream": False,
            "chat_id": str(session_id),
            "history": self.build_history(history),
        }

    def generate(
        self,
        *,
        user_id: int,
        session_id: int,
        user_input: str,
        history: list[dict[str, Any]],
    ) -> str:
        self._refresh_config()
        if not self.is_configured:
            exc = XingchenAgentUnavailableError(
                "Xingchen Agent is disabled or incompletely configured",
                "星辰 Agent 未配置",
                branch="configuration_not_ready",
            )
            self._debug(
                "Xingchen exception branch: branch=%s error_type=%s",
                exc.branch,
                type(exc).__name__,
            )
            raise exc

        payload = self.build_payload(
            user_id=user_id,
            session_id=session_id,
            user_input=user_input,
            history=history,
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {self.api_key}:{self.api_secret}",
        }
        self._debug(
            "Xingchen request debug: stream=%s history_count=%d "
            "agent_input_chars=%d timeout_seconds=%s",
            payload["stream"],
            len(payload["history"]),
            len(user_input),
            self.timeout,
        )
        started_at = monotonic()
        try:
            response = self._post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            self._debug_response_shape(response, payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning(
                "Xingchen request failed: error_type=%s elapsed_ms=%d",
                type(exc).__name__,
                int((monotonic() - started_at) * 1000),
            )
            unavailable = XingchenAgentUnavailableError(
                "Xingchen Agent request timed out",
                "星辰 Agent 请求超时",
                branch="request_timeout",
            )
            self._debug(
                "Xingchen exception branch: branch=%s error_type=%s",
                unavailable.branch,
                type(unavailable).__name__,
            )
            raise unavailable from exc
        except httpx.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning(
                "Xingchen request failed: status=%s error_type=%s elapsed_ms=%d",
                status,
                type(exc).__name__,
                int((monotonic() - started_at) * 1000),
            )
            unavailable = XingchenAgentUnavailableError(
                "Xingchen Agent HTTP request failed",
                "星辰 Agent 服务暂不可用",
                branch="http_status_or_transport_error",
            )
            self._debug(
                "Xingchen exception branch: branch=%s error_type=%s",
                unavailable.branch,
                type(unavailable).__name__,
            )
            raise unavailable from exc

        logger.info(
            "Xingchen request completed: status=%s elapsed_ms=%d",
            response.status_code,
            int((monotonic() - started_at) * 1000),
        )
        try:
            return self._parse_response(response)
        except XingchenAgentUnavailableError as exc:
            logger.warning(
                "Xingchen response rejected: status=%s error_type=%s",
                response.status_code,
                type(exc).__name__,
            )
            self._debug(
                "Xingchen exception branch: branch=%s error_type=%s "
                "fallback_reason=%s",
                exc.branch,
                type(exc).__name__,
                exc.fallback_reason,
            )
            raise

    def _debug_response_shape(
        self,
        response: httpx.Response,
        request_payload: dict[str, Any],
    ) -> None:
        if not self._debug_enabled:
            return

        decoded_items: list[Any] = []
        response_format = "json"
        try:
            decoded = response.json()
            decoded_items = decoded if isinstance(decoded, list) else [decoded]
            top_level_type = type(decoded).__name__
        except ValueError:
            response_format = "non_json_or_sse"
            top_level_type = "unparsed"
            for raw_line in response.text.splitlines():
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    decoded_items.append(json.loads(data))
                except json.JSONDecodeError:
                    continue
            if decoded_items:
                response_format = "sse"
                top_level_type = "sse_frames"

        objects = [item for item in decoded_items if isinstance(item, dict)]
        top_level_keys = sorted(
            {str(key) for item in objects for key in item.keys()}
        )
        codes = [item.get("code") for item in objects if "code" in item]
        messages = [item.get("message") for item in objects if "message" in item]
        data_values = [item.get("data") for item in objects if "data" in item]
        data_types = sorted({type(value).__name__ for value in data_values})
        data_has_execute_id = any(
            self._data_contains_execute_id(value) for value in data_values
        )
        choices_present = any("choices" in item for item in objects)
        choices_nonempty = any(bool(item.get("choices")) for item in objects)
        content_present, content_nonempty = self._field_presence(
            decoded_items, "content"
        )
        answer_present, answer_nonempty = self._field_presence(decoded_items, "answer")
        safe_message = self._safe_debug_text(
            messages[0] if messages else None,
            request_payload,
        )

        self._debug(
            "Xingchen response debug: status=%s content_type=%s "
            "response_format=%s json_top_level_type=%s top_level_keys=%s "
            "code=%s message=%s data_type=%s data_has_execute_id=%s "
            "choices_present=%s choices_nonempty=%s content_present=%s "
            "content_nonempty=%s answer_present=%s answer_nonempty=%s",
            response.status_code,
            response.headers.get("Content-Type", ""),
            response_format,
            top_level_type,
            top_level_keys,
            codes[0] if codes else None,
            safe_message,
            data_types[0] if len(data_types) == 1 else data_types or "missing",
            data_has_execute_id,
            choices_present,
            choices_nonempty,
            content_present,
            content_nonempty,
            answer_present,
            answer_nonempty,
        )

    @staticmethod
    def _data_contains_execute_id(value: Any) -> bool:
        if isinstance(value, dict):
            return "execute_id" in value
        if isinstance(value, list):
            return any(
                isinstance(item, dict) and "execute_id" in item for item in value
            )
        return False

    @classmethod
    def _field_presence(cls, value: Any, field_name: str) -> tuple[bool, bool]:
        present = False
        nonempty = False
        if isinstance(value, dict):
            if field_name in value:
                present = True
                field_value = value[field_name]
                nonempty = isinstance(field_value, str) and bool(field_value.strip())
            for child in value.values():
                child_present, child_nonempty = cls._field_presence(child, field_name)
                present = present or child_present
                nonempty = nonempty or child_nonempty
        elif isinstance(value, list):
            for child in value:
                child_present, child_nonempty = cls._field_presence(child, field_name)
                present = present or child_present
                nonempty = nonempty or child_nonempty
        return present, nonempty

    def _safe_debug_text(
        self,
        value: Any,
        request_payload: dict[str, Any],
        limit: int = 240,
    ) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).split())
        sensitive_values = [self.api_key, self.api_secret]
        parameters = request_payload.get("parameters")
        if isinstance(parameters, dict):
            sensitive_values.extend(
                item for item in parameters.values() if isinstance(item, str)
            )
        history = request_payload.get("history")
        if isinstance(history, list):
            sensitive_values.extend(
                item.get("content", "")
                for item in history
                if isinstance(item, dict) and isinstance(item.get("content"), str)
            )
        for sensitive_value in sensitive_values:
            if sensitive_value:
                text = text.replace(sensitive_value, "[REDACTED]")
        return text if len(text) <= limit else f"{text[: limit - 1]}…"

    @classmethod
    def _parse_response(cls, response: httpx.Response) -> str:
        try:
            decoded = response.json()
            payloads = decoded if isinstance(decoded, list) else [decoded]
        except ValueError:
            payloads = cls._parse_sse_payloads(response.text)

        if not payloads:
            raise XingchenAgentUnavailableError(
                "Xingchen Agent response was not valid JSON or SSE",
                "星辰 Agent 返回异常",
                branch="response_invalid_json_or_sse",
            )

        chunks: list[str] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                raise XingchenAgentUnavailableError(
                    "Xingchen Agent response payload was not an object",
                    "星辰 Agent 返回异常",
                    branch="response_payload_not_object",
                )
            code = payload.get("code", 0)
            if code is not None and str(code) != "0":
                raise XingchenAgentUnavailableError(
                    f"Xingchen Agent returned error code {code}",
                    "星辰 Agent 服务暂不可用",
                    branch="response_code_nonzero",
                )
            content = cls._extract_content(payload)
            if content:
                chunks.append(content)

        answer = "".join(chunks).strip()
        if not answer:
            raise XingchenAgentUnavailableError(
                "Xingchen Agent response did not contain an answer",
                "星辰 Agent 返回异常",
                branch="response_no_answer",
            )
        return answer

    @staticmethod
    def _parse_sse_payloads(text: str) -> list[Any]:
        payloads: list[Any] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payloads.append(json.loads(data))
            except json.JSONDecodeError as exc:
                raise XingchenAgentUnavailableError(
                    "Xingchen Agent SSE frame was invalid JSON",
                    "星辰 Agent 返回异常",
                    branch="response_sse_frame_invalid_json",
                ) from exc
        return payloads

    @classmethod
    def _extract_content(cls, payload: dict[str, Any]) -> str | None:
        choices = payload.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                for container_name in ("delta", "message"):
                    container = choice.get(container_name)
                    if isinstance(container, dict):
                        content = container.get("content")
                        if isinstance(content, str) and content:
                            return content
                for key in ("content", "text"):
                    content = choice.get(key)
                    if isinstance(content, str) and content:
                        return content

        for key in ("answer", "content"):
            content = payload.get(key)
            if isinstance(content, str) and content:
                return content
        output = payload.get("output")
        if isinstance(output, str) and output:
            return output
        for wrapper_name in ("data", "result", "output"):
            wrapper = payload.get(wrapper_name)
            if isinstance(wrapper, dict):
                content = cls._extract_content(wrapper)
                if content:
                    return content
        return None
