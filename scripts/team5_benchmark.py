"""Run the 112-question before/after fine-tuning benchmark.

The runner talks to three OpenAI-compatible endpoints: a baseline model, a
fine-tuned model, and one fixed judge.  Keeping the judge fixed avoids letting
either candidate grade its own answers.  Every response is checkpointed as
JSONL so an interrupted full run can resume without repeating completed calls.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_QUIZ = BASE_DIR / "data" / "documents" / "老师训练题库.json"
DEFAULT_OUTPUT = BASE_DIR / "artifacts" / "team5_benchmark"
QUESTION_TYPES = {
    "fill": "填空题",
    "calc": "计算与简答题",
    "proof": "证明题",
    "app": "应用题",
}
ANSWER_PROMPT = """你是一名严谨的离散数学学生。请解答下面的题目。
要求：结论准确；计算题和证明题写出必要步骤；最后一行以“最终答案：”给出结论。

题型：{type_name}
题目：{question}
"""
JUDGE_PROMPT = """你是独立的离散数学评测员。请对照标准答案评价候选答案。
重点检查最终结论、关键步骤、逻辑严密性和符号规范。等价表达应判为正确，不能因措辞不同扣分。

题目：{question}
标准答案：{reference}
候选答案：{candidate}

只输出 JSON，不要 Markdown：
{{"score": 0到100的整数, "correct": true或false, "reason": "不超过60字"}}
其中 correct 仅在答案实质正确且没有关键逻辑错误时为 true。
"""


@dataclass(frozen=True)
class ModelConfig:
    label: str
    base_url: str
    model: str
    api_key: str = ""
    timeout: float = 60.0
    max_tokens: int = 1400
    enable_thinking: bool | None = None

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def validate(self) -> None:
        if not self.base_url or not self.model:
            raise ValueError(f"{self.label} 缺少 base_url 或 model 配置")


class OpenAIChatClient:
    def __init__(self, config: ModelConfig):
        config.validate()
        self.config = config

    def generate(self, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": self.config.max_tokens,
        }
        if self.config.enable_thinking is not None:
            payload["chat_template_kwargs"] = {
                "enable_thinking": self.config.enable_thinking,
            }
        response = httpx.post(
            self.config.endpoint,
            headers=headers,
            json=payload,
            timeout=httpx.Timeout(self.config.timeout, connect=min(20.0, self.config.timeout)),
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("模型返回空答案")
        return content.strip()


def load_questions(path: Path = DEFAULT_QUIZ) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = []
    for exam in data.get("exams", []):
        for question_type, type_name in QUESTION_TYPES.items():
            for index, item in enumerate(exam.get(question_type, []), 1):
                questions.append({
                    "id": f"e{exam['id']}_{question_type}_{index}",
                    "exam_id": exam["id"],
                    "type": question_type,
                    "type_name": type_name,
                    "question": item["q"],
                    "reference_answer": item["a"],
                    "knowledge_point": item.get("kp", ""),
                })
    declared_total = data.get("total")
    if declared_total is not None and declared_total != len(questions):
        raise ValueError(f"题库声明 {declared_total} 题，实际解析 {len(questions)} 题")
    return questions


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("响应中没有 JSON 对象")
    value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("评分响应不是 JSON 对象")
    return value


def normalize_judgement(payload: dict[str, Any]) -> dict[str, Any]:
    raw_score = payload.get("score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise ValueError("评分缺少数值 score")
    score = max(0, min(100, round(float(raw_score), 2)))
    correct = payload.get("correct")
    if not isinstance(correct, bool):
        correct = score >= 80
    return {
        "score": score,
        "correct": correct,
        "reason": str(payload.get("reason", ""))[:200],
    }


def answer_one(
    question: dict[str, Any],
    label: str,
    answer_client: Any,
    judge_client: Any | None,
) -> dict[str, Any]:
    record = {
        "id": question["id"],
        "model_label": label,
        "type": question["type"],
        "type_name": question["type_name"],
        "knowledge_point": question["knowledge_point"],
        "question": question["question"],
        "reference_answer": question["reference_answer"],
    }
    started = time.perf_counter()
    try:
        record["answer"] = answer_client.generate(ANSWER_PROMPT.format(
            type_name=question["type_name"], question=question["question"]
        ))
        record["latency_seconds"] = round(time.perf_counter() - started, 3)
        record["answer_ok"] = True
    except Exception as exc:  # network failures are data, not a full-run crash
        record.update({
            "answer": "",
            "latency_seconds": round(time.perf_counter() - started, 3),
            "answer_ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "score": 0,
            "correct": False,
        })
        return record

    if judge_client is None:
        record.update({"score": None, "correct": None, "judge_reason": "未配置独立裁判模型"})
        return record

    judge_started = time.perf_counter()
    try:
        raw = judge_client.generate(JUDGE_PROMPT.format(
            question=question["question"],
            reference=question["reference_answer"],
            candidate=record["answer"],
        ))
        judgement = normalize_judgement(parse_json_object(raw))
        record.update(judgement)
        record["judge_reason"] = record.pop("reason")
        record["judge_latency_seconds"] = round(time.perf_counter() - judge_started, 3)
    except Exception as exc:
        record.update({
            "score": None,
            "correct": None,
            "judge_error": f"{type(exc).__name__}: {exc}"[:300],
            "judge_latency_seconds": round(time.perf_counter() - judge_started, 3),
        })
    return record


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return round(ordered[low], 3)
    value = ordered[low] + (ordered[high] - ordered[low]) * (index - low)
    return round(value, 3)


def summarize_model(records: list[dict[str, Any]], speed_limit: float = 30.0) -> dict[str, Any]:
    successful = [r for r in records if r.get("answer_ok")]
    judged = [r for r in successful if isinstance(r.get("score"), (int, float))]
    latencies = [float(r["latency_seconds"]) for r in successful]
    proof = [r for r in records if r.get("type") == "proof"]
    proof_successful = [r for r in proof if r.get("answer_ok")]
    proof_latencies = [float(r["latency_seconds"]) for r in proof_successful]
    proof_under_limit = [r for r in proof_successful if float(r["latency_seconds"]) <= speed_limit]
    return {
        "question_count": len(records),
        "successful_count": len(successful),
        "failure_count": len(records) - len(successful),
        "judged_count": len(judged),
        "accuracy": round(sum(bool(r.get("correct")) for r in judged) / len(judged), 4) if judged else None,
        "average_score": round(statistics.fmean(float(r["score"]) for r in judged), 2) if judged else None,
        "average_latency_seconds": round(statistics.fmean(latencies), 3) if latencies else None,
        "p50_latency_seconds": _percentile(latencies, 0.5),
        "p95_latency_seconds": _percentile(latencies, 0.95),
        "proof": {
            "count": len(proof),
            "successful_count": len(proof_successful),
            "under_limit_count": len(proof_under_limit),
            "speed_limit_seconds": speed_limit,
            "under_limit_rate": round(len(proof_under_limit) / len(proof), 4) if proof else None,
            "average_latency_seconds": round(statistics.fmean(proof_latencies), 3) if proof_latencies else None,
            "p50_latency_seconds": _percentile(proof_latencies, 0.5),
            "p95_latency_seconds": _percentile(proof_latencies, 0.95),
            "max_latency_seconds": round(max(proof_latencies), 3) if proof_latencies else None,
        },
    }


def build_comparison(
    records: list[dict[str, Any]],
    speed_limit: float = 30.0,
    required_proof_rate: float = 1.0,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["model_label"], []).append(record)
    models = {label: summarize_model(items, speed_limit) for label, items in grouped.items()}
    baseline = models.get("baseline", {})
    tuned = models.get("tuned", {})
    baseline_accuracy, tuned_accuracy = baseline.get("accuracy"), tuned.get("accuracy")
    baseline_latency, tuned_latency = baseline.get("average_latency_seconds"), tuned.get("average_latency_seconds")
    proof = tuned.get("proof", {})
    proof_rate = proof.get("under_limit_rate")
    proof_gate = {
        "model_label": "tuned",
        "speed_limit_seconds": speed_limit,
        "required_rate": required_proof_rate,
        "observed_rate": proof_rate,
        "passed": bool(
            proof.get("count")
            and proof.get("successful_count") == proof.get("count")
            and isinstance(proof_rate, (int, float))
            and proof_rate >= required_proof_rate
        ),
    }
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "models": models,
        "delta": {
            "accuracy_percentage_points": round((tuned_accuracy - baseline_accuracy) * 100, 2)
            if isinstance(baseline_accuracy, (int, float)) and isinstance(tuned_accuracy, (int, float)) else None,
            "average_score": round(tuned.get("average_score") - baseline.get("average_score"), 2)
            if isinstance(baseline.get("average_score"), (int, float)) and isinstance(tuned.get("average_score"), (int, float)) else None,
            "average_latency_seconds": round(tuned_latency - baseline_latency, 3)
            if isinstance(baseline_latency, (int, float)) and isinstance(tuned_latency, (int, float)) else None,
        },
        "proof_speed_gate": proof_gate,
    }


def _display(value: Any, suffix: str = "") -> str:
    return "-" if value is None else f"{value}{suffix}"


def write_reports(records: list[dict[str, Any]], output_dir: Path, comparison: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "proof_speed_gate.json").write_text(
        json.dumps(comparison["proof_speed_gate"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    columns = [
        "id", "model_label", "type", "knowledge_point", "answer_ok", "correct",
        "score", "latency_seconds", "judge_latency_seconds", "judge_reason", "error",
    ]
    with (output_dir / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(records, key=lambda r: (r["id"], r["model_label"])))

    models = comparison["models"]
    lines = [
        "# 微调前后 112 题评测报告",
        "",
        f"> 生成时间：{comparison['generated_at']}",
        "> 准确率口径：固定独立裁判模型判定 `correct=true` 的比例。",
        "",
        "| 模型 | 完成题数 | 准确率 | 平均分 | 平均耗时 | P95 耗时 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label in ("baseline", "tuned"):
        item = models.get(label, {})
        accuracy = item.get("accuracy")
        accuracy_text = f"{accuracy * 100:.2f}%" if isinstance(accuracy, (int, float)) else "-"
        lines.append(
            f"| {label} | {item.get('successful_count', 0)}/{item.get('question_count', 0)} | "
            f"{accuracy_text} | {_display(item.get('average_score'))} | "
            f"{_display(item.get('average_latency_seconds'), 's')} | "
            f"{_display(item.get('p95_latency_seconds'), 's')} |"
        )
    delta = comparison["delta"]
    gate = comparison["proof_speed_gate"]
    lines.extend([
        "",
        "## 对比结论",
        "",
        f"- 准确率变化：{_display(delta.get('accuracy_percentage_points'), ' 个百分点')}",
        f"- 平均分变化：{_display(delta.get('average_score'), ' 分')}",
        f"- 平均作答耗时变化：{_display(delta.get('average_latency_seconds'), 's')}",
        "",
        "## 证明题速度门禁",
        "",
        f"- 要求：每题不超过 {gate['speed_limit_seconds']}s，达标率至少 {gate['required_rate'] * 100:.1f}%",
        f"- 实测达标率：{_display(None if gate['observed_rate'] is None else round(gate['observed_rate'] * 100, 2), '%')}",
        f"- 结果：{'通过' if gate['passed'] else '未通过或数据不完整'}",
        "",
        "> 原始逐题记录见 `comparison.csv`，机器可读汇总见 `summary.json`。",
    ])
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def _append_jsonl(path: Path, record: dict[str, Any], lock: threading.Lock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_model(
    questions: list[dict[str, Any]],
    label: str,
    answer_client_factory: Callable[[], Any],
    judge_client_factory: Callable[[], Any] | None,
    output_dir: Path,
    workers: int,
    resume: bool,
) -> list[dict[str, Any]]:
    checkpoint = output_dir / f"{label}.jsonl"
    existing = _read_jsonl(checkpoint) if resume else []
    if not resume and checkpoint.exists():
        checkpoint.unlink()
    completed = {r["id"] for r in existing}
    pending = [q for q in questions if q["id"] not in completed]
    lock = threading.Lock()

    def execute(question: dict[str, Any]) -> dict[str, Any]:
        return answer_one(
            question,
            label,
            answer_client_factory(),
            judge_client_factory() if judge_client_factory else None,
        )

    print(f"[{label}] 共 {len(questions)} 题，待运行 {len(pending)} 题，并发 {workers}")
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(execute, q): q for q in pending}
        for index, future in enumerate(as_completed(futures), 1):
            record = future.result()
            existing.append(record)
            _append_jsonl(checkpoint, record, lock)
            print(
                f"[{label} {index}/{len(pending)}] {record['id']} "
                f"score={record.get('score')} latency={record['latency_seconds']}s",
                flush=True,
            )
    return existing


def _config_from_args(args: argparse.Namespace, prefix: str, label: str) -> ModelConfig:
    upper = prefix.upper()
    base_url = getattr(args, f"{prefix}_base_url") or os.getenv(f"{upper}_BASE_URL", "")
    model = getattr(args, f"{prefix}_model") or os.getenv(f"{upper}_MODEL", "")
    key = getattr(args, f"{prefix}_api_key") or os.getenv(f"{upper}_API_KEY", "")
    return ModelConfig(
        label=label,
        base_url=base_url,
        model=model,
        api_key=key,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
        enable_thinking=False if args.disable_thinking else None,
    )


def main() -> int:
    load_dotenv(BASE_DIR / ".env", override=False)
    parser = argparse.ArgumentParser(description="112 题微调前后准确率与速度对比")
    parser.add_argument("--quiz", type=Path, default=DEFAULT_QUIZ)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--types", default="fill,calc,proof,app")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=1400)
    parser.add_argument("--proof-speed-limit", type=float, default=30.0)
    parser.add_argument("--required-proof-rate", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--skip-judge", action="store_true", help="只测速度，不生成准确率")
    for prefix in ("baseline", "tuned", "judge"):
        parser.add_argument(f"--{prefix}-base-url")
        parser.add_argument(f"--{prefix}-model")
        parser.add_argument(f"--{prefix}-api-key")
    args = parser.parse_args()

    selected_types = {part.strip() for part in args.types.split(",") if part.strip()}
    unknown = selected_types - QUESTION_TYPES.keys()
    if unknown:
        parser.error(f"未知题型: {', '.join(sorted(unknown))}")
    questions = [q for q in load_questions(args.quiz) if q["type"] in selected_types]
    if args.limit:
        questions = questions[:args.limit]
    if not questions:
        parser.error("没有可评测题目")

    baseline = _config_from_args(args, "baseline", "baseline")
    tuned = _config_from_args(args, "tuned", "tuned")
    baseline.validate()
    tuned.validate()
    judge = None if args.skip_judge else _config_from_args(args, "judge", "judge")
    if judge:
        judge.validate()
    judge_factory = (lambda: OpenAIChatClient(judge)) if judge else None

    all_records: list[dict[str, Any]] = []
    for config in (baseline, tuned):
        all_records.extend(run_model(
            questions=questions,
            label=config.label,
            answer_client_factory=lambda config=config: OpenAIChatClient(config),
            judge_client_factory=judge_factory,
            output_dir=args.output_dir,
            workers=args.workers,
            resume=args.resume,
        ))
    comparison = build_comparison(
        all_records,
        speed_limit=args.proof_speed_limit,
        required_proof_rate=args.required_proof_rate,
    )
    write_reports(all_records, args.output_dir, comparison)
    print(f"报告已生成：{args.output_dir / 'report.md'}")
    return 0 if comparison["proof_speed_gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
