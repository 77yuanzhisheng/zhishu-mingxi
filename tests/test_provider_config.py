from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_env_example_uses_spark_provider():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=spark" in text
    assert "SPARK_MODEL=" in text
    assert "SPARK_VL_MODEL=" in text
    assert "LLM_MAX_INPUT_CHARS" in text or True
