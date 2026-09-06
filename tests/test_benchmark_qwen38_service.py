from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'benchmark_qwen38_service.py'
SPEC = importlib.util.spec_from_file_location('benchmark_qwen38_service', SCRIPT_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark)


def test_parse_sse_line_reads_content_and_usage():
    event = benchmark.parse_sse_line(
        'data: {"choices":[{"delta":{"content":"answer"}}],'
        '"usage":{"prompt_tokens":12,"completion_tokens":5,"total_tokens":17}}'
    )

    assert event == {
        'content': 'answer',
        'usage': {'prompt_tokens': 12, 'completion_tokens': 5, 'total_tokens': 17},
    }
    assert benchmark.parse_sse_line('data: [DONE]') is None


def test_extract_json_object_accepts_fenced_model_response():
    text = 'Explanation that must be ignored.\n```json\n{"approved": true, "score": 88}\n```'

    assert benchmark.extract_json_object(text) == {'approved': True, 'score': 88}


def test_summarize_results_groups_metrics_by_case_and_concurrency():
    results = [
        {
            'case_id': 'chat_short', 'concurrency': 4, 'ok': True, 'ttft_seconds': 0.2,
            'total_seconds': 1.0, 'completion_tokens': 20, 'json_valid': None,
            'basic_check_passed': True,
        },
        {
            'case_id': 'chat_short', 'concurrency': 4, 'ok': True, 'ttft_seconds': 0.4,
            'total_seconds': 2.0, 'completion_tokens': 20, 'json_valid': None,
            'basic_check_passed': False,
        },
        {
            'case_id': 'grading_json', 'concurrency': 4, 'ok': False, 'ttft_seconds': None,
            'total_seconds': 0.5, 'completion_tokens': 0, 'json_valid': False,
            'basic_check_passed': False,
        },
    ]

    summary = benchmark.summarize_results(results)

    chat = summary['by_case']['chat_short']['4']
    assert chat['requests'] == 2
    assert chat['http_success_rate'] == 1.0
    assert chat['average_ttft_seconds'] == pytest.approx(0.3)
    assert chat['generation_tokens_per_second'] == pytest.approx(40 / 3)
    assert chat['basic_check_pass_rate'] == 0.5

    grading = summary['by_case']['grading_json']['4']
    assert grading['json_parse_rate'] == 0.0
    assert grading['http_success_rate'] == 0.0

def test_run_benchmark_separates_concurrency_batches(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(('client', kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_run_one(client, case, model, concurrency, timeout, enable_thinking):
        calls.append(('request', concurrency, case['id']))
        return {
            'case_id': case['id'], 'concurrency': concurrency, 'ok': True,
            'ttft_seconds': 0.1, 'total_seconds': 0.2, 'completion_tokens': 4,
            'json_valid': True if case['json_expected'] else None,
            'basic_check_passed': True,
        }

    monkeypatch.setattr(benchmark.httpx, 'Client', FakeClient)
    monkeypatch.setattr(benchmark, 'run_one', fake_run_one)

    results = benchmark.run_benchmark(
        base_url='http://example.test/v1', model='test', api_key='key',
        concurrencies=[1, 2], rounds=1, timeout=10, enable_thinking=False,
    )

    assert [row['concurrency'] for row in results[:4]] == [1, 1, 1, 1]
    assert [row['concurrency'] for row in results[4:]] == [2, 2, 2, 2]
    assert len([call for call in calls if call[0] == 'request']) == 8