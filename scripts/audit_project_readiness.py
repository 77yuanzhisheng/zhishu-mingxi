"""Emit a secret-free readiness report for the competition handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow execution as ``python scripts/audit_project_readiness.py`` from any cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.training.audit import audit_project_readiness  # noqa: E402


def _markdown(report: dict) -> str:
    curriculum = report["curriculum"]
    question_bank = report["question_bank"]
    finetune = report["finetune"]
    lines = [
        "# 项目准备度审计报告",
        "",
        "## 教材知识库",
        f"- 章节：{curriculum['chapters']}",
        f"- 节：{curriculum['sections']}",
        f"- 知识点：{curriculum['knowledge_points']}",
        f"- 要点：{curriculum['key_points']}",
        "",
        "## 题库映射",
        f"- 题目：{question_bank['total']}",
        f"- 不同 node_id：{question_bank['distinct_node_ids']}",
        f"- 未映射：{question_bank['unmapped']}",
        "",
        "## 微调指令集",
        f"- 文件：`{finetune['file']}`",
        f"- 记录数：{finetune['records']}",
        f"- 重复记录：{finetune['duplicates']}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="项目根目录，默认使用当前脚本所属项目根目录",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="输出格式，默认 json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="可选：同时将报告写入指定文件",
    )
    args = parser.parse_args(argv)

    report = audit_project_readiness(args.root)
    content = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else _markdown(report)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
