# -*- coding: utf-8 -*-
"""
benchmark_proofs.py — 老师训练题库 112 题大模型推理能力评测基线
================================================================
流程（每道题）:
    1. 作答：把题面发给 LLM（Qwen3-8B），要求给出完整推理/证明过程
    2. 评分：LLM-as-judge，按 5 维（结论/关键步骤/严密性/术语/表达）对照标准答案打分
    3. 汇总：按题型与知识点模块统计得分率、平均分、耗时、超时率、错误类型

并发: 默认 3 路并发调用（--workers 调整），每题 LLM 超时 120s，失败记 0 分不阻塞。

用法:
    python scripts/benchmark_proofs.py                     # proof+calc 全量
    python scripts/benchmark_proofs.py --types proof,calc,fill
    python scripts/benchmark_proofs.py --limit 5           # 冒烟测试
    python scripts/benchmark_proofs.py --resume            # 断点续跑
    python scripts/benchmark_proofs.py --workers 4

输出:
    scripts/benchmark_results.json   （每题明细）
    scripts/benchmark_report.md      （Markdown 汇总报告）
"""

import argparse
import json
import os
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

from backend.chat.llm import OpenAICompatibleLLM  # noqa: E402

QUIZ_FILE = os.path.join(BASE_DIR, "data", "documents", "老师训练题库.json")
RESULTS_FILE = os.path.join(BASE_DIR, "scripts", "benchmark_results.json")
REPORT_FILE = os.path.join(BASE_DIR, "scripts", "benchmark_report.md")
PROGRESS_FILE = os.path.join(BASE_DIR, "scripts", "benchmark_progress.json")
LLM_TIMEOUT = 120.0  # 单次调用超时（秒），限流时快速失败记 0 分

TYPE_NAMES = {"fill": "填空题", "calc": "计算与简答题", "proof": "证明题", "app": "应用题"}

ANSWER_PROMPT = (
    "你是一名离散数学助教。请完整解答下面这道题，写出清晰的推理或证明过程，"
    "使用标准数学记号（∀ ∃ ∈ ⊆ → ↔ 等）。\n\n"
    "【题目】（{type_name}）\n{q}\n\n请给出完整解答过程。"
)

JUDGE_PROMPT = (
    "你是一名严谨的离散数学阅卷教师。请按 5 个维度给学生答案评分，每题满分 10 分：\n"
    "- 结论正确性（权重 20%）\n"
    "- 关键推理步骤（权重 35%）\n"
    "- 逻辑严密性（权重 25%）\n"
    "- 定义/定理使用准确性（权重 10%）\n"
    "- 表达与符号规范（权重 10%）\n\n"
    "【题目】\n{q}\n\n"
    "【标准答案】\n{a}\n\n"
    "【学生答案】\n{s}\n\n"
    "请只输出一个 JSON 对象（不要其他文字）：\n"
    '{{"total": 0到10的分数, "dimensions": {{"结论正确性": 0-2, "关键推理步骤": 0-3.5, '
    '"逻辑严密性": 0-2.5, "定义/定理使用准确性": 0-1, "表达与符号规范": 0-1}}, '
    '"error_types": ["循环论证"或"跳步"或"错用定理"或"符号错误"或"结论错误"等，没有则[]], '
    '"comment": "一两句评语"}}'
)

_write_lock = threading.Lock()


def load_questions(types: list[str], limit: int | None) -> list[dict]:
    with open(QUIZ_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = []
    for exam in data["exams"]:
        for t in types:
            for idx, item in enumerate(exam.get(t, []), 1):
                questions.append({
                    "id": f"e{exam['id']}_{t}_{idx}",
                    "exam": exam["id"],
                    "type": t,
                    "type_name": TYPE_NAMES[t],
                    "q": item["q"],
                    "a": item["a"],
                    "kp": item.get("kp", ""),
                })
    if limit:
        questions = questions[:limit]
    return questions


def parse_judge_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}


class _FastLLM(OpenAICompatibleLLM):
    """固定 120s 超时的 LLM 客户端（generate 内部 _refresh_config 会重置 timeout，需每次强制）。"""

    def _refresh_config(self) -> None:
        super()._refresh_config()
        self.timeout = LLM_TIMEOUT


def _new_llm() -> OpenAICompatibleLLM:
    return _FastLLM()


def process_one(item: dict) -> dict:
    """单题：作答 + 评分。每个调用创建独立 LLM 实例（并发安全）。"""
    rec = dict(item)
    llm = _new_llm()
    t0 = time.time()
    try:
        answer = llm.generate([{"role": "user", "content": ANSWER_PROMPT.format(
            type_name=item["type_name"], q=item["q"])}])
        rec["answer"] = answer
        rec["answer_seconds"] = round(time.time() - t0, 1)
        rec["answer_ok"] = True
    except Exception as exc:
        rec["answer"] = ""
        rec["answer_seconds"] = round(time.time() - t0, 1)
        rec["answer_ok"] = False
        rec["answer_error"] = str(exc)[:120]
        rec["score"] = 0.0
        rec["error"] = f"作答失败: {str(exc)[:60]}"
        return rec

    t1 = time.time()
    try:
        judge = llm.generate([{"role": "user", "content": JUDGE_PROMPT.format(
            q=item["q"], a=item["a"], s=answer)}])
        rec["judge_seconds"] = round(time.time() - t1, 1)
        parsed = parse_judge_json(judge)
        score = parsed.get("total")
        rec["score"] = float(score) if isinstance(score, (int, float)) else 0.0
        rec["dimensions"] = parsed.get("dimensions", {})
        rec["error_types"] = parsed.get("error_types", [])
        rec["comment"] = parsed.get("comment", "")
        if not isinstance(rec["score"], (int, float)) or rec["score"] < 0:
            rec["score"] = 0.0
            rec["error"] = "评分 JSON 解析失败"
    except Exception as exc:
        rec["score"] = 0.0
        rec["error"] = f"评分失败: {str(exc)[:60]}"
    return rec


def save_progress(done_ids: list[str]) -> None:
    with _write_lock:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump([{"id": i} for i in done_ids], f, ensure_ascii=False, indent=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--types", default="proof,calc",
                        help="题型，逗号分隔（proof/calc/fill/app）")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=3, help="并发路数")
    parser.add_argument("--retry-failed", action="store_true",
                        help="把此前作答超时/失败的题重新加入待处理")
    args = parser.parse_args()

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    questions = load_questions(types, args.limit)
    print(f"待评测题目: {len(questions)} 道 ({', '.join(TYPE_NAMES[t] for t in types)})，并发 {args.workers} 路")

    done_ids = []
    if args.resume and os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            done_ids = [p["id"] for p in json.load(f)]

    if args.retry_failed and os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            old_results = json.load(f).get("results", [])
        result_ids = {r["id"] for r in old_results}
        failed_ids = {r["id"] for r in old_results if not r.get("answer_ok")}
        # 早期被中断轮次只写了 progress 没写 results 的题，也一并补跑
        missing_ids = {i for i in done_ids if i not in result_ids}
        retry_ids = failed_ids | missing_ids
        removed = [i for i in done_ids if i in retry_ids]
        done_ids = [i for i in done_ids if i not in retry_ids]
        if removed:
            print(f"重试失败/缺失题: {len(removed)} 道 ({', '.join(removed[:8])}...)")

    todo = [q for q in questions if q["id"] not in set(done_ids)]
    print(f"剩余待处理: {len(todo)} 道（已跳过 {len(done_ids)}）", flush=True)

    results = []
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_one, item): item for item in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            item = futures[fut]
            try:
                rec = fut.result()
            except Exception as exc:
                rec = dict(item)
                rec["score"] = 0.0
                rec["error"] = f"异常: {str(exc)[:60]}"
            results.append(rec)
            done_ids.append(rec["id"])
            save_progress(done_ids)
            elapsed = time.time() - t_start
            print(f"  [{i}/{len(todo)}] {rec['id']} ({rec['type_name']}/{rec.get('kp')}) "
                  f"得分={rec.get('score')} 用时={rec.get('answer_seconds', '?')}s "
                  f"总耗时={elapsed:.0f}s", flush=True)

    # 合并历史结果（断点续跑后汇总）
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        merged = {r["id"]: r for r in old.get("results", [])}
        for r in results:
            merged[r["id"]] = r
        results = list(merged.values())

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=1)

    write_report(results, types)
    print(f"\n完成。明细: {RESULTS_FILE}\n报告: {REPORT_FILE}")


def write_report(results: list[dict], types: list[str]) -> None:
    # 只统计「作答成功且有评分」的题；作答超时/失败单独统计，不拖低平均分
    scored = [r for r in results if r.get("answer_ok") and isinstance(r.get("score"), (int, float))]
    failed = [r for r in results if not r.get("answer_ok")]
    lines = [
        "# 大模型数学推理评测报告（老师训练题库）",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
        f"> 题型：{', '.join(TYPE_NAMES[t] for t in types)}",
        f"> 作答模型：SiliconFlow Qwen3-8B（详见 .env OPENAI_CHAT_MODEL）",
        "",
    ]
    if not scored:
        lines.append("（暂无有效评分结果）")
    else:
        total = len(scored)
        avg = sum(r["score"] for r in scored) / total
        lines += [
            f"## 总体",
            "",
            f"- 有效作答/评分：**{total}/{len(results)}** 题",
            f"- 平均得分：**{avg:.2f} / 10**（得分率 {avg * 10:.1f}%）",
            f"- 平均作答耗时：{sum(r.get('answer_seconds', 0) for r in scored) / total:.1f}s",
            f"- 作答失败/超时（不计入平均分）：{len(failed)} 道",
            "",
            "## 按题型",
            "",
            "| 题型 | 题数 | 平均分 | 得分率 |",
            "|---|---|---|---|",
        ]
        by_type = defaultdict(list)
        for r in scored:
            by_type[r["type"]].append(r["score"])
        for t in types:
            arr = by_type.get(t, [])
            if arr:
                m = sum(arr) / len(arr)
                lines.append(f"| {TYPE_NAMES[t]} | {len(arr)} | {m:.2f} | {m * 10:.1f}% |")
            else:
                lines.append(f"| {TYPE_NAMES[t]} | 0 | - | - |")

        lines += ["", "## 按知识点模块", "", "| 知识点 | 题数 | 平均分 | 得分率 |", "|---|---|---|---|"]
        by_kp = defaultdict(list)
        for r in scored:
            by_kp[r["kp"]].append(r["score"])
        for kp, arr in sorted(by_kp.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
            m = sum(arr) / len(arr)
            lines.append(f"| {kp} | {len(arr)} | {m:.2f} | {m * 10:.1f}% |")

        errs = defaultdict(int)
        for r in scored:
            for e in r.get("error_types", []):
                errs[e] += 1
        if errs:
            lines += ["", "## 错误类型分布", ""]
            for e, c in sorted(errs.items(), key=lambda kv: -kv[1]):
                lines.append(f"- {e}: {c} 次")
        lines += ["", "## 低分题（<5 分）", ""]
        low = [r for r in scored if r["score"] < 5]
        if low:
            for r in sorted(low, key=lambda x: x["score"])[:10]:
                lines.append(f"- **{r['id']}**（{r['type_name']}/{r['kp']}）{r['score']:.1f}分 — {r['q'][:50]}…")
        else:
            lines.append("无")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
