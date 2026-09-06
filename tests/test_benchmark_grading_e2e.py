from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'benchmark_grading_e2e.py'
SPEC = importlib.util.spec_from_file_location('benchmark_grading_e2e', SCRIPT_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark)


def test_extract_result_metrics_captures_audit_and_repair_counts():
    payload = {
        'total_score': 85,
        'audit': {'latency_ms': 3210},
        'attempts': {'analysis': 2, 'scoring': 1, 'review': 1},
        'needs_manual_review': False,
    }

    assert benchmark.extract_result_metrics(payload) == {
        'total_score': 85.0,
        'audit_latency_ms': 3210,
        'model_calls': 4,
        'repair_calls': 1,
        'needs_manual_review': False,
    }


def test_summarize_results_reports_success_latency_and_repairs():
    report = benchmark.summarize_results([
        {'ok': True, 'total_seconds': 2.0, 'audit_latency_ms': 1800, 'model_calls': 3, 'repair_calls': 0, 'needs_manual_review': False},
        {'ok': True, 'total_seconds': 4.0, 'audit_latency_ms': 3500, 'model_calls': 4, 'repair_calls': 1, 'needs_manual_review': True},
        {'ok': False, 'total_seconds': 1.0, 'error': 'HTTPStatusError: 502'},
    ])

    assert report['requests'] == 3
    assert report['http_success_rate'] == pytest.approx(2 / 3)
    assert report['average_total_seconds'] == pytest.approx(3.0)
    assert report['average_audit_latency_ms'] == pytest.approx(2650)
    assert report['average_model_calls'] == pytest.approx(3.5)
    assert report['repair_rate'] == pytest.approx(0.5)
    assert report['manual_review_rate'] == pytest.approx(0.5)


def test_build_request_has_required_full_question_fields():
    request = benchmark.build_request('proof_complete')

    assert request['question']
    assert request['reference_answer']
    assert request['student_answer']
    assert request['knowledge_points']