"""Configurable OpenAI-compatible multimodal vision adapter.

The adapter deliberately stops at the OpenAI-compatible chat-completions
boundary. Platform-specific authentication and request formats must be
provided by configuration or a future provider adapter.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any

import httpx
from pydantic import ValidationError

from backend.chat.exceptions import LLMUnavailableError
from backend.vision.models import VisionParseResponse


VISION_PROMPT = """请识别这张离散数学题目或学生答案图片，并且只返回合法 JSON，不要 Markdown 代码块。JSON 字段必须为：
question_text（题目文字，没有则为空字符串）、student_answer（学生答案，没有则为空字符串）、latex（识别出的 LaTeX 字符串数组）、symbols（离散数学符号数组）、confidence（0 到 1 的数字）、warnings（可能影响识别的说明字符串数组）。保留 ∀、∃、¬、∧、∨、→、↔、∈、∉、⊆、∪、∩ 等符号。"""


class VisionProviderError(RuntimeError):
    """The configured provider could not complete the request."""


class VisionResponseParseError(ValueError):
    """The provider responded, but its content was not a valid result."""


class SparkVLClient:
    """Call a configured OpenAI-compatible multimodal endpoint."""

    def __init__(self) -> None:
        self.base_url = (
            os.getenv("SPARK_VL_BASE_URL") or os.getenv("SPARK_BASE_URL", "")
        ).strip().rstrip("/")
        self.api_key = (
            os.getenv("SPARK_VL_API_KEY") or os.getenv("SPARK_API_KEY", "")
        ).strip()
        self.model = os.getenv("SPARK_VL_MODEL", "").strip()
        self.timeout = float(
            os.getenv("SPARK_VL_TIMEOUT_SECONDS")
            or os.getenv("LLM_TIMEOUT_SECONDS", "60")
        )
        self.max_tokens = int(
            os.getenv("SPARK_VL_MAX_TOKENS") or os.getenv("LLM_MAX_TOKENS", "1024")
        )

    def ensure_available(self) -> None:
        if not self.model:
            raise LLMUnavailableError("视觉模型尚未配置")
        if not self.base_url:
            raise LLMUnavailableError("视觉服务地址尚未配置")

    def parse(self, image_bytes: bytes, content_type: str) -> VisionParseResponse:
        self.ensure_available()
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(image_bytes, content_type),
                timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 20.0)),
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = self._parse_content(content)
            result.elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
            return result
        except LLMUnavailableError:
            raise
        except VisionResponseParseError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise VisionResponseParseError("视觉模型返回格式无效") from exc
        except httpx.HTTPError as exc:
            # Do not include provider response bodies, URLs, or headers: they
            # may contain credentials or other sensitive request information.
            raise VisionProviderError("视觉模型调用失败") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "your_api_key_here":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def recognize_text(self, image_bytes: bytes, content_type: str, prompt: str) -> str:
        """Recognize image content using the configured vision provider.

        OCR consumers need the model's verbatim text rather than the structured
        JSON required by :meth:`parse`. The request still shares the same
        SPARK_VL configuration, authentication, timeout, and safety boundary.
        """
        self.ensure_available()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(image_bytes, content_type, prompt=prompt),
                timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 20.0)),
            )
            response.raise_for_status()
            return self._coerce_text_content(response.json()["choices"][0]["message"]["content"])
        except LLMUnavailableError:
            raise
        except VisionResponseParseError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise VisionResponseParseError("??????????") from exc
        except httpx.HTTPError as exc:
            # Never include provider URLs, headers, response bodies, or keys.
            raise VisionProviderError("????????") from exc

    def _payload(
        self, image_bytes: bytes, content_type: str, *, prompt: str = VISION_PROMPT
    ) -> dict[str, Any]:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{encoded}"
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": self.max_tokens,
        }

    @staticmethod
    def _coerce_text_content(content: Any) -> str:
        if isinstance(content, list):
            content = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
        if not isinstance(content, str) or not content.strip():
            raise VisionResponseParseError("empty vision response")
        return content.strip()

    @staticmethod
    def _parse_content(content: Any) -> VisionParseResponse:
        if isinstance(content, list):
            content = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
        if not isinstance(content, str) or not content.strip():
            raise VisionResponseParseError("empty vision response")
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise VisionResponseParseError("vision response is not an object")
        try:
            return VisionParseResponse(
                question_text=str(data.get("question_text", "") or ""),
                student_answer=str(data.get("student_answer", "") or ""),
                latex=_as_string_list(data.get("latex", [])),
                symbols=_as_string_list(data.get("symbols", [])),
                confidence=float(data.get("confidence", 0.0) or 0.0),
                warnings=_as_string_list(data.get("warnings", [])),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise VisionResponseParseError("vision response fields are invalid") from exc


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []
