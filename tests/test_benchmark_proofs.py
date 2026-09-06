from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'benchmark_proofs.py'
SPEC = importlib.util.spec_from_file_location('benchmark_proofs', SCRIPT_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark)


def test_configured_model_label_uses_active_spark_model(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'spark')
    monkeypatch.setenv('SPARK_MODEL', 'xop3qwen32b')
    monkeypatch.setenv('OPENAI_CHAT_MODEL', 'stale-fallback-name')

    assert benchmark.configured_model_label() == 'spark/xop3qwen32b'


def test_configured_model_label_uses_openai_fallback(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_CHAT_MODEL', 'qwen3-8b')

    assert benchmark.configured_model_label() == 'openai/qwen3-8b'
