"""Build, normalize, deduplicate, and validate fine-tuning JSONL data."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = BASE_DIR / "data" / "documents" / "老师训练题库.json"
DEFAULT_OUTPUT = BASE_DIR / "data" / "finetune" / "teacher_questions_112.jsonl"
DEFAULT_REPORT = BASE_DIR / "data" / "finetune" / "validation_report.json"
SYSTEM_PROMPT = (
    "你是知数明析离散数学助教。使用规范符号和严谨推理作答；"
    "证明题按已知、推导、结论组织，结尾写证毕。"
)

SYMBOL_REPLACEMENTS = (
    (r"\Leftrightarrow", "↔"),
    (r"\leftrightarrow", "↔"),
    (r"\Rightarrow", "→"),
    (r"\rightarrow", "→"),
    (r"\to", "→"),
    (r"\forall", "∀"),
    (r"\exists", "∃"),
    (r"\wedge", "∧"),
    (r"\land", "∧"),
    (r"\vee", "∨"),
    (r"\lor", "∨"),
    (r"\neg", "¬"),
    (r"\subseteq", "⊆"),
    (r"\subset", "⊂"),
    (r"\supseteq", "⊇"),
    (r"\supset", "⊃"),
    (r"\cup", "∪"),
    (r"\cap", "∩"),
    (r"\in", "∈"),
    (r"\notin", "∉"),
    (r"\neq", "≠"),
    (r"\leq", "≤"),
    (r"\geq", "≥"),
    (r"\varnothing", "∅"),
)


@dataclass
class ValidationReport:
    input_count: int = 0
    valid_count: int = 0
    output_count: int = 0
    duplicate_count: int = 0
    conflict_count: int = 0
    invalid_count: int = 0
    symbol_replacement_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.invalid_count == 0 and self.conflict_count == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "input_count": self.input_count,
            "valid_count": self.valid_count,
            "output_count": self.output_count,
            "duplicate_count": self.duplicate_count,
            "conflict_count": self.conflict_count,
            "invalid_count": self.invalid_count,
            "symbol_replacement_count": self.symbol_replacement_count,
            "errors": self.errors,
            "duplicates": self.duplicates,
            "conflicts": self.conflicts,
        }


def normalize_text(value: str) -> tuple[str, int]:
    text = html.unescape(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:p|div|span)[^>]*>", "", text, flags=re.I)
    replacements = 0
    # Longer commands must run first (for example \notin before \in).
    for source, target in sorted(SYMBOL_REPLACEMENTS, key=lambda pair: -len(pair[0])):
        # A command such as ``\in`` must not alter ``\infty``.
        pattern = re.compile(re.escape(source) + r"(?![A-Za-z])")
        text, count = pattern.subn(lambda _match, target=target: target, text)
        replacements += count
    text = text.replace("⇒", "→").replace("⇔", "↔")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), replacements


def _record_key(text: str) -> str:
    compact = re.sub(r"\s+", "", text).casefold()
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def question_bank_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    type_names = {"fill": "填空题", "calc": "计算题", "proof": "证明题", "app": "应用题"}
    for exam in data.get("exams", []):
        for question_type, type_name in type_names.items():
            for index, item in enumerate(exam.get(question_type, []), 1):
                records.append({
                    "system": SYSTEM_PROMPT,
                    "user": f"【{type_name}】{item['q']}",
                    "assistant": item["a"],
                    "metadata": {
                        "id": f"e{exam['id']}_{question_type}_{index}",
                        "exam_id": exam["id"],
                        "question_type": question_type,
                        "knowledge_point": item.get("kp", ""),
                    },
                })
    declared = data.get("total")
    if declared is not None and declared != len(records):
        raise ValueError(f"题库声明 {declared} 题，实际转换 {len(records)} 题")
    return records


def jsonl_records(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("每行必须是 JSON 对象")
                records.append(value)
            except (json.JSONDecodeError, ValueError) as exc:
                errors.append({"line": line_number, "message": str(exc)})
    return records, errors


def _from_messages(record: dict[str, Any]) -> dict[str, Any]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return record
    by_role: dict[str, str] = {}
    for message in messages:
        if isinstance(message, dict) and message.get("role") in {"system", "user", "assistant"}:
            by_role[str(message["role"])] = message.get("content", "")
    converted = {name: by_role.get(name, "") for name in ("system", "user", "assistant")}
    if "metadata" in record:
        converted["metadata"] = record["metadata"]
    return converted


def validate_and_deduplicate(
    records: Iterable[dict[str, Any]],
    parse_errors: list[dict[str, Any]] | None = None,
    max_chars: int = 20000,
    include_metadata: bool = False,
) -> tuple[list[dict[str, Any]], ValidationReport]:
    report = ValidationReport()
    if parse_errors:
        report.errors.extend(parse_errors)
        report.invalid_count += len(parse_errors)
    output: list[dict[str, Any]] = []
    seen: dict[str, tuple[str, str]] = {}

    for index, raw in enumerate(records, 1):
        report.input_count += 1
        record = _from_messages(raw)
        normalized: dict[str, Any] = {}
        reasons = []
        for field_name in ("system", "user", "assistant"):
            value = record.get(field_name)
            if not isinstance(value, str) or not value.strip():
                reasons.append(f"{field_name} 必须是非空字符串")
                continue
            cleaned, replacements = normalize_text(value)
            report.symbol_replacement_count += replacements
            if len(cleaned) > max_chars:
                reasons.append(f"{field_name} 超过 {max_chars} 字符")
            normalized[field_name] = cleaned
        if reasons:
            report.invalid_count += 1
            report.errors.append({"record": index, "messages": reasons})
            continue
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        record_id = str(metadata.get("id", index))
        if include_metadata and metadata:
            normalized["metadata"] = record["metadata"]
        report.valid_count += 1

        user_key = _record_key(normalized["user"])
        answer_key = _record_key(normalized["assistant"])
        if user_key in seen:
            previous_answer, previous_id = seen[user_key]
            if previous_answer == answer_key:
                report.duplicate_count += 1
                report.duplicates.append({"id": record_id, "same_as": previous_id})
            else:
                report.conflict_count += 1
                report.conflicts.append({"id": record_id, "conflicts_with": previous_id})
            continue
        seen[user_key] = (answer_key, record_id)
        output.append(normalized)

    report.output_count = len(output)
    return output, report


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="题库转微调 JSONL，并执行符号规范化、去重和格式校验")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--input-format", choices=("auto", "question-bank", "jsonl"), default="auto")
    parser.add_argument("--max-chars", type=int, default=20000)
    parser.add_argument("--include-metadata", action="store_true", help="输出题号/题型/知识点元数据")
    parser.add_argument("--check-only", action="store_true", help="仅校验，不写清洗后 JSONL")
    args = parser.parse_args()

    input_format = args.input_format
    if input_format == "auto":
        input_format = "jsonl" if args.source.suffix.lower() == ".jsonl" else "question-bank"
    parse_errors: list[dict[str, Any]] = []
    if input_format == "question-bank":
        records = question_bank_records(args.source)
    else:
        records, parse_errors = jsonl_records(args.source)

    cleaned, report = validate_and_deduplicate(
        records, parse_errors, args.max_chars, include_metadata=args.include_metadata
    )
    if not args.check_only:
        write_jsonl(args.output, cleaned)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
