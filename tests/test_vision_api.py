from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.vision.models import VisionParseResponse
from backend.vision.router import get_vision_client, router
from backend.vision.spark_vl import SparkVLClient


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def vision_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_response_model_exposes_required_fields() -> None:
    response = VisionParseResponse(
        question_text="题目",
        student_answer="答案",
        latex=["A \\subseteq B"],
        symbols=["⊆"],
        confidence=0.9,
        warnings=[],
        elapsed_ms=12,
    )

    assert response.model_dump() == {
        "question_text": "题目",
        "student_answer": "答案",
        "latex": ["A \\subseteq B"],
        "symbols": ["⊆"],
        "confidence": 0.9,
        "warnings": [],
        "elapsed_ms": 12,
    }


def test_client_builds_configurable_openai_multimodal_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_VL_MODEL", "qwen3-vl-32b")
    monkeypatch.setenv("SPARK_VL_BASE_URL", "https://vision.example/v1")
    monkeypatch.setenv("SPARK_VL_API_KEY", "secret-vl-key")

    client = SparkVLClient()
    payload = client._payload(b"fake-png", "image/png")
    content = payload["messages"][0]["content"]

    assert payload["model"] == "qwen3-vl-32b"
    assert payload["messages"][0]["role"] == "user"
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]) == b"fake-png"
    assert "spark" not in json.dumps(payload).lower()



def test_client_prefers_vision_specific_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_VL_BASE_URL", "https://vision.example/v1/")
    monkeypatch.setenv("SPARK_VL_API_KEY", "vision-key")
    monkeypatch.setenv("SPARK_VL_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("SPARK_VL_MAX_TOKENS", "456")
    monkeypatch.setenv("SPARK_BASE_URL", "https://text.example/v1")
    monkeypatch.setenv("SPARK_API_KEY", "text-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("LLM_MAX_TOKENS", "768")

    client = SparkVLClient()

    assert client.base_url == "https://vision.example/v1"
    assert client.api_key == "vision-key"
    assert client.timeout == 12.5
    assert client.max_tokens == 456


def test_client_falls_back_to_shared_spark_and_llm_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SPARK_VL_BASE_URL",
        "SPARK_VL_API_KEY",
        "SPARK_VL_TIMEOUT_SECONDS",
        "SPARK_VL_MAX_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SPARK_BASE_URL", "https://shared.example/v1/")
    monkeypatch.setenv("SPARK_API_KEY", "shared-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("LLM_MAX_TOKENS", "768")

    client = SparkVLClient()

    assert client.base_url == "https://shared.example/v1"
    assert client.api_key == "shared-key"
    assert client.timeout == 45.0
    assert client.max_tokens == 768


def test_parse_valid_image_returns_normalized_response(
    vision_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeClient:
        def parse(self, image_bytes: bytes, content_type: str) -> VisionParseResponse:
            assert image_bytes == b"fake-png"
            assert content_type == "image/png"
            return VisionParseResponse(
                question_text="证明 A⊆B",
                student_answer="因为 x∈A，所以 x∈B",
                latex=["A \\subseteq B"],
                symbols=["∈", "⊆"],
                confidence=0.88,
                warnings=[],
                elapsed_ms=8,
            )

    monkeypatch.setattr("backend.vision.router.get_vision_client", lambda: FakeClient())

    response = TestClient(vision_app).post(
        "/api/vision/parse",
        files={"file": ("question.png", b"fake-png", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["question_text"] == "证明 A⊆B"
    assert response.json()["elapsed_ms"] == 8


def test_parse_rejects_unsupported_media_type(vision_app: FastAPI) -> None:
    response = TestClient(vision_app).post(
        "/api/vision/parse",
        files={"file": ("question.gif", b"gif", "image/gif")},
    )

    assert response.status_code == 415


def test_parse_rejects_images_larger_than_10_mib(vision_app: FastAPI) -> None:
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    response = TestClient(vision_app).post(
        "/api/vision/parse",
        files={"file": ("large.png", oversized, "image/png")},
    )

    assert response.status_code == 413


def test_parse_rejects_empty_image(vision_app: FastAPI) -> None:
    response = TestClient(vision_app).post(
        "/api/vision/parse",
        files={"file": ("empty.png", b"", "image/png")},
    )

    assert response.status_code == 422


def test_missing_vl_model_returns_503(
    vision_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SPARK_VL_MODEL", raising=False)
    monkeypatch.setattr("backend.vision.router.get_vision_client", lambda: SparkVLClient())

    response = TestClient(vision_app).post(
        "/api/vision/parse",
        files={"file": ("question.png", b"png", "image/png")},
    )

    assert response.status_code == 503


def test_upstream_error_does_not_leak_secret(
    vision_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "super-secret-vl-key"

    class FailingClient:
        def parse(self, image_bytes: bytes, content_type: str) -> VisionParseResponse:
            raise RuntimeError(f"upstream failed with {secret}")

    monkeypatch.setattr("backend.vision.router.get_vision_client", lambda: FailingClient())

    response = TestClient(vision_app).post(
        "/api/vision/parse",
        files={"file": ("question.webp", b"webp", "image/webp")},
    )

    assert response.status_code == 502
    assert secret not in response.text
    assert "upstream" not in response.text.lower()


def test_invalid_model_response_returns_unprocessable_entity(
    vision_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    class InvalidResponseClient:
        def parse(self, image_bytes: bytes, content_type: str) -> VisionParseResponse:
            raise ValueError("provider returned malformed JSON")

    monkeypatch.setattr("backend.vision.router.get_vision_client", lambda: InvalidResponseClient())

    response = TestClient(vision_app).post(
        "/api/vision/parse",
        files={"file": ("question.png", b"png", "image/png")},
    )

    assert response.status_code == 422


def test_api_registers_vision_route() -> None:
    api_source = (REPOSITORY_ROOT / "backend" / "api.py").read_text(encoding="utf-8")

    assert "from backend.vision.router import router as vision_router" in api_source
    assert "app.include_router(vision_router)" in api_source

def test_recognize_text_uses_configured_vision_endpoint_and_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_VL_MODEL", "qwen3-vl-32b")
    monkeypatch.setenv("SPARK_VL_BASE_URL", "https://vision.example/v1")
    monkeypatch.setenv("SPARK_VL_API_KEY", "vision-key")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "P \u2227 Q\nP\n\u2192 Q"}}]}

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, object], timeout: object) -> FakeResponse:
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("backend.vision.spark_vl.httpx.post", fake_post)

    result = SparkVLClient().recognize_text(b"fake-png", "image/png", "OCR prompt")

    assert result == "P \u2227 Q\nP\n\u2192 Q"
    assert captured["url"] == "https://vision.example/v1/chat/completions"
    assert captured["headers"] == {"Content-Type": "application/json", "Authorization": "Bearer vision-key"}
    content = captured["payload"]["messages"][0]["content"]  # type: ignore[index]
    assert content[0] == {"type": "text", "text": "OCR prompt"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
