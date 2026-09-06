from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

CASES = [
    {
        'id': 'chat_short', 'label': 'short discrete-math QA', 'json_expected': False,
        'messages': [{'role': 'user', 'content': '离散数学中，命题“如果 n 是偶数，则 n^2 是偶数”是真命题吗？请用两句话说明理由。'}],
        'check': lambda text: '偶数' in text,
    },
    {
        'id': 'calc_judge', 'label': 'calculation judgement', 'json_expected': True,
        'messages': [{'role': 'user', 'content': '判断下面计算是否正确，并只输出 JSON：{"correct": true或false, "reason": "简短理由"}。题目：集合 A={1,2,3}，则 |P(A)|=6。'}],
        'check': lambda text: _json_has(text, 'correct'),
    },
    {
        'id': 'grading_json', 'label': 'proof grading JSON', 'json_expected': True,
        'messages': [{'role': 'user', 'content': '请批阅证明题并只输出 JSON。题目：证明有限集合 A 的幂集 P(A) 的元素个数为 2^|A|。学生答案：每个元素有选或不选两种可能，所以共有 2^|A| 个子集。JSON 格式：{"total_score": 0到100的数字, "error_types": [], "feedback": "一句话"}。'}],
        'check': lambda text: _json_has(text, 'total_score'),
    },
    {
        'id': 'structured_json', 'label': 'structured response', 'json_expected': True,
        'messages': [{'role': 'user', 'content': '只输出 JSON：给出集合 {1,2,3} 的真子集个数，格式为 {"answer": 数字, "reason": "一句话"}。'}],
        'check': lambda text: _json_has(text, 'answer'),
    },
]


def parse_sse_line(line: str) -> dict[str, Any] | None:
    if not line.startswith('data:'):
        return None
    raw = line[5:].strip()
    if not raw or raw == '[DONE]':
        return None
    payload = json.loads(raw)
    choices = payload.get('choices') or []
    delta = choices[0].get('delta') or {} if choices else {}
    content = delta.get('content') or ''
    return {'content': content, 'usage': payload.get('usage')}


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if '```' in cleaned:
        parts = cleaned.split('```')
        candidates = [p[4:] if p.lstrip().startswith('json') else p for p in parts]
        cleaned = max(candidates, key=lambda p: p.count('{'))
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('no JSON object found')
    value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError('JSON value is not an object')
    return value


def _json_has(text: str, key: str) -> bool:
    try:
        return key in extract_json_object(text)
    except (ValueError, json.JSONDecodeError):
        return False


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[(result['case_id'], result['concurrency'])].append(result)
    by_case: dict[str, dict[str, Any]] = defaultdict(dict)
    for (case_id, concurrency), rows in groups.items():
        ttft = [r['ttft_seconds'] for r in rows if r.get('ttft_seconds') is not None]
        total = [r['total_seconds'] for r in rows if r.get('total_seconds') is not None]
        tokens = sum(r.get('completion_tokens') or 0 for r in rows)
        duration = sum(total)
        json_rows = [r for r in rows if r.get('json_valid') is not None]
        checks = [r for r in rows if r.get('basic_check_passed') is not None]
        by_case[case_id][str(concurrency)] = {
            'requests': len(rows),
            'http_success_rate': sum(bool(r.get('ok')) for r in rows) / len(rows),
            'average_ttft_seconds': statistics.mean(ttft) if ttft else None,
            'average_total_seconds': statistics.mean(total) if total else None,
            'generation_tokens_per_second': tokens / duration if duration else 0.0,
            'json_parse_rate': sum(bool(r.get('json_valid')) for r in json_rows) / len(json_rows) if json_rows else None,
            'basic_check_pass_rate': sum(bool(r.get('basic_check_passed')) for r in checks) / len(checks) if checks else None,
        }
    return {'by_case': dict(by_case), 'requests': len(results)}


def run_one(client: httpx.Client, case: dict[str, Any], model: str, concurrency: int, timeout: float, enable_thinking: bool) -> dict[str, Any]:
    started = time.perf_counter()
    first_content = None
    chunks: list[str] = []
    usage = None
    row: dict[str, Any] = {'case_id': case['id'], 'concurrency': concurrency, 'ok': False, 'json_valid': None, 'basic_check_passed': False}
    try:
        payload = {'model': model, 'messages': case['messages'], 'temperature': 0.2, 'top_p': 0.8, 'max_tokens': 256, 'stream': True, 'stream_options': {'include_usage': True}, 'chat_template_kwargs': {'enable_thinking': enable_thinking}}
        with client.stream('POST', '/chat/completions', json=payload, timeout=timeout) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                event = parse_sse_line(line)
                if not event:
                    continue
                if event['content']:
                    first_content = first_content or time.perf_counter()
                    chunks.append(event['content'])
                usage = event['usage'] or usage
        text = ''.join(chunks)
        row.update({'ok': True, 'response': text, 'ttft_seconds': first_content - started if first_content else None, 'total_seconds': time.perf_counter() - started, 'completion_tokens': (usage or {}).get('completion_tokens', 0), 'usage': usage})
        if case['json_expected']:
            try:
                extract_json_object(text)
                row['json_valid'] = True
            except (ValueError, json.JSONDecodeError):
                row['json_valid'] = False
        row['basic_check_passed'] = bool(case['check'](text))
    except Exception as exc:
        row.update({'error': f'{type(exc).__name__}: {exc}', 'ttft_seconds': None, 'total_seconds': time.perf_counter() - started, 'completion_tokens': 0})
    return row



def run_benchmark(
    *,
    base_url: str,
    model: str,
    api_key: str,
    concurrencies: list[int],
    rounds: int,
    timeout: float,
    enable_thinking: bool,
) -> list[dict[str, Any]]:
    headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=base_url.rstrip('/'), headers=headers) as client:
        for concurrency in concurrencies:
            jobs = [case for _ in range(rounds) for case in CASES]
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [
                    pool.submit(run_one, client, case, model, concurrency, timeout, enable_thinking)
                    for case in jobs
                ]
                for future in as_completed(futures):
                    results.append(future.result())
    return results
def render_markdown(report: dict[str, Any]) -> str:
    lines = ['# Qwen3.8-27B Service Benchmark', '', f"Requests: {report['requests']}", '', '| Case | Concurrency | HTTP | Avg TTFT (s) | Avg total (s) | Gen tok/s | JSON | Basic |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for case, values in report['by_case'].items():
        for concurrency, item in values.items():
            def fmt(value: Any) -> str:
                return '-' if value is None else f'{value:.3f}' if isinstance(value, float) else str(value)
            lines.append(f"| {case} | {concurrency} | {item['http_success_rate']:.1%} | {fmt(item['average_ttft_seconds'])} | {fmt(item['average_total_seconds'])} | {fmt(item['generation_tokens_per_second'])} | {fmt(item['json_parse_rate'])} | {fmt(item['basic_check_pass_rate'])} |")
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default=os.getenv('OPENAI_BASE_URL', 'http://127.0.0.1:18000/v1'))
    parser.add_argument('--model', default=os.getenv('OPENAI_CHAT_MODEL', 'qwen38-27b'))
    parser.add_argument('--api-key', default=os.getenv('OPENAI_API_KEY', 'EMPTY'))
    parser.add_argument('--concurrency', default='1,4,8')
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=120.0)
    parser.add_argument('--output-prefix', default='outputs/benchmark_qwen38_service')
    parser.add_argument('--enable-thinking', action='store_true')
    args = parser.parse_args()
    concurrencies = [int(value.strip()) for value in args.concurrency.split(',') if value.strip()]
    results = run_benchmark(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        concurrencies=concurrencies,
        rounds=args.rounds,
        timeout=args.timeout,
        enable_thinking=args.enable_thinking,
    )
    report = summarize_results(results)
    report['metadata'] = {'base_url': args.base_url, 'model': args.model, 'concurrency': args.concurrency, 'rounds': args.rounds, 'enable_thinking': args.enable_thinking, 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix('.json').write_text(json.dumps({'results': results, **report}, ensure_ascii=False, indent=2), encoding='utf-8')
    prefix.with_suffix('.md').write_text(render_markdown(report), encoding='utf-8')
    print(render_markdown(report))


if __name__ == '__main__':
    main()