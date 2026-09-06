from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

CASES = {
    'proof_complete': {
        'question': '证明：若 n 为偶整数，则 n^2 为偶整数。',
        'reference_answer': '设 n=2k，其中 k 为整数。则 n^2=(2k)^2=4k^2=2(2k^2)，所以 n^2 为偶整数。',
        'student_answer': '因为 n 是偶数，所以 n=2k。于是 n^2=4k^2=2(2k^2)，故 n^2 是偶数。',
        'knowledge_points': ['整数与整除', '直接证明法'],
    },
    'proof_incomplete': {
        'question': '证明：若 n 为偶整数，则 n^2 为偶整数。',
        'reference_answer': '设 n=2k，其中 k 为整数。则 n^2=(2k)^2=4k^2=2(2k^2)，所以 n^2 为偶整数。',
        'student_answer': '偶数的平方当然还是偶数，所以结论成立。',
        'knowledge_points': ['整数与整除', '直接证明法'],
    },
}


def build_request(case_id: str) -> dict[str, Any]:
    try:
        return dict(CASES[case_id])
    except KeyError as exc:
        raise ValueError(f'unknown case: {case_id}') from exc


def extract_result_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    attempts = payload.get('attempts') or {}
    stage_attempts = [int(attempts.get(stage, 0)) for stage in ('analysis', 'scoring', 'review')]
    model_calls = sum(stage_attempts)
    return {
        'total_score': float(payload['total_score']),
        'audit_latency_ms': int((payload.get('audit') or {})['latency_ms']),
        'model_calls': model_calls,
        'repair_calls': max(0, model_calls - 3),
        'needs_manual_review': bool(payload.get('needs_manual_review')),
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    success = [row for row in results if row.get('ok')]
    def average(key: str) -> float | None:
        values = [row[key] for row in success if row.get(key) is not None]
        return statistics.mean(values) if values else None
    return {
        'requests': len(results),
        'http_success_rate': len(success) / len(results) if results else 0.0,
        'average_total_seconds': average('total_seconds'),
        'average_audit_latency_ms': average('audit_latency_ms'),
        'average_model_calls': average('model_calls'),
        'repair_rate': sum(row['repair_calls'] > 0 for row in success) / len(success) if success else 0.0,
        'manual_review_rate': sum(row['needs_manual_review'] for row in success) / len(success) if success else 0.0,
    }


def run_one(client: httpx.Client, case_id: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {'case_id': case_id, 'ok': False}
    try:
        response = client.post('/api/grading/grade', json=build_request(case_id), timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        row.update(extract_result_metrics(payload))
        row['ok'] = True
        row['response'] = payload
    except Exception as exc:
        row['error'] = f'{type(exc).__name__}: {exc}'
    row['total_seconds'] = time.perf_counter() - started
    return row


def run_benchmark(base_url: str, cases: list[str], rounds: int, concurrency: int, timeout: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=base_url.rstrip('/')) as client:
        jobs = [case_id for _ in range(rounds) for case_id in cases]
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(run_one, client, case_id, timeout) for case_id in jobs]
            for future in as_completed(futures):
                results.append(future.result())
    return results


def render_markdown(report: dict[str, Any]) -> str:
    def number(value: Any, digits: int = 3) -> str:
        return '-' if value is None else f'{value:.{digits}f}'
    return '\n'.join([
        '# Qwen3.8-27B End-to-End Grading Benchmark',
        '',
        f"- Requests: {report['requests']}",
        f"- HTTP success: {report['http_success_rate']:.1%}",
        f"- Average API total latency: {number(report['average_total_seconds'])} s",
        f"- Average grading audit latency: {number(report['average_audit_latency_ms'], 0)} ms",
        f"- Average model calls: {number(report['average_model_calls'], 2)}",
        f"- Repair rate: {report['repair_rate']:.1%}",
        f"- Manual review rate: {report['manual_review_rate']:.1%}",
        '',
        '> This report measures the local application API plus its remote-model calls. It is not a direct vLLM throughput benchmark or a human-grading accuracy evaluation.',
        '',
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description='Benchmark /api/grading/grade end to end.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--cases', default='proof_complete,proof_incomplete')
    parser.add_argument('--rounds', type=int, default=1)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=300.0)
    parser.add_argument('--output-prefix', default='outputs/benchmark_grading_e2e')
    args = parser.parse_args()
    cases = [case.strip() for case in args.cases.split(',') if case.strip()]
    results = run_benchmark(args.base_url, cases, args.rounds, args.concurrency, args.timeout)
    report = summarize_results(results)
    report['metadata'] = {
        'base_url': args.base_url, 'cases': cases, 'rounds': args.rounds,
        'concurrency': args.concurrency, 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }
    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix('.json').write_text(json.dumps({'results': results, **report}, ensure_ascii=False, indent=2), encoding='utf-8')
    prefix.with_suffix('.md').write_text(render_markdown(report), encoding='utf-8')
    print(render_markdown(report))


if __name__ == '__main__':
    main()