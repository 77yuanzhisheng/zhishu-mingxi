from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DEFAULT_JSON_SOURCE = Path("data/documents/??????.json")
_MARKDOWN_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(question|answer|type|kp|knowledge_point)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)


def _normalise_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _iter_json_questions(payload: Any) -> Iterable[tuple[str, Any]]:
    """Yield (question_type, record) pairs from the supported quiz-bank shapes."""
    if isinstance(payload, dict):
        exams = payload.get("exams")
        if isinstance(exams, list):
            for exam in exams:
                if not isinstance(exam, dict):
                    yield "unknown", exam
                    continue
                for question_type, records in exam.items():
                    if question_type in {"id", "title"} or not isinstance(records, list):
                        continue
                    for record in records:
                        yield str(question_type), record
            return
        records = payload.get("questions")
        if isinstance(records, list):
            for record in records:
                yield "unknown", record
            return
    if isinstance(payload, list):
        for record in payload:
            yield "unknown", record


def _source_paths(json_source: Path, markdown_dir: Path | None) -> list[Path]:
    paths = [json_source.resolve()]
    if markdown_dir is not None:
        markdown_dir = markdown_dir.resolve()
        if not markdown_dir.is_dir():
            raise NotADirectoryError(markdown_dir)
        paths.extend(sorted(markdown_dir.rglob("*.md")))
    return paths


def _iter_markdown_questions(text: str) -> list[dict[str, str]]:
    """Parse only explicit Markdown records containing a ``question:`` field.

    A free-form Markdown paragraph is deliberately not treated as a training
    sample. Records start at each explicit ``question:`` field; the remaining
    supported fields may appear in any order until the next question or EOF.
    """
    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    field_names = {
        "question": "question",
        "answer": "answer",
        "type": "type",
        "kp": "knowledge_point",
        "knowledge_point": "knowledge_point",
    }

    for raw_line in text.splitlines():
        match = _MARKDOWN_FIELD_RE.match(raw_line)
        if not match:
            continue
        field, value = match.groups()
        field = field_names[field.lower()]
        if field == "question":
            if current is not None:
                records.append(current)
            current = {"question": value}
            continue
        if current is not None:
            current[field] = value

    if current is not None:
        records.append(current)
    return records


def _record_values(record: Any) -> tuple[str, str, str]:
    if not isinstance(record, dict):
        return "", "", "unknown"
    question = _normalise_text(record.get("q", record.get("question", "")))
    answer = _normalise_text(record.get("a", record.get("answer", "")))
    knowledge_point = _normalise_text(
        record.get("kp", record.get("knowledge_point", ""))
    ) or "unknown"
    return question, answer, knowledge_point


def _add_record(
    question_type: Any,
    record: Any,
    *,
    type_counts: Counter[str],
    knowledge_point_counts: Counter[str],
    question_fingerprints: set[str],
) -> tuple[int, int, int, int]:
    """Return question, missing-answer, invalid, duplicate increments."""
    question, answer, knowledge_point = _record_values(record)
    type_name = _normalise_text(question_type) or "unknown"
    type_counts[type_name] += 1
    knowledge_point_counts[knowledge_point] += 1

    duplicate = 0
    if question:
        fingerprint = hashlib.sha256(question.encode("utf-8")).hexdigest()
        if fingerprint in question_fingerprints:
            duplicate = 1
        question_fingerprints.add(fingerprint)

    return 1, int(not answer), int(not question or not answer), duplicate


def inspect_training_sources(
    json_source: str | Path = DEFAULT_JSON_SOURCE,
    markdown_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect training inputs without modifying any source file."""
    json_path = Path(json_source)
    if not json_path.exists():
        raise FileNotFoundError(json_path)
    markdown_path = Path(markdown_dir) if markdown_dir is not None else None
    sources = _source_paths(json_path, markdown_path)

    type_counts: Counter[str] = Counter()
    knowledge_point_counts: Counter[str] = Counter()
    question_fingerprints: set[str] = set()
    duplicate_count = 0
    missing_answer_count = 0
    invalid_count = 0
    question_count = 0
    encoding_error_count = 0
    markdown_question_count = 0
    markdown_unrecognized_file_count = 0
    markdown_encoding_error_count = 0
    markdown_bytes = 0
    markdown_lines = 0

    try:
        with json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        encoding_error_count = 1
        invalid_count = 1
        payload = None

    if payload is not None:
        for question_type, record in _iter_json_questions(payload):
            q, missing, invalid, duplicate = _add_record(
                question_type,
                record,
                type_counts=type_counts,
                knowledge_point_counts=knowledge_point_counts,
                question_fingerprints=question_fingerprints,
            )
            question_count += q
            missing_answer_count += missing
            invalid_count += invalid
            duplicate_count += duplicate

    if markdown_path is not None:
        for markdown_file in sources[1:]:
            raw = markdown_file.read_bytes()
            markdown_bytes += len(raw)
            markdown_lines += raw.count(b"\n") + int(bool(raw))
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                encoding_error_count += 1
                invalid_count += 1
                markdown_encoding_error_count += 1
                continue

            records = _iter_markdown_questions(text)
            if not records:
                markdown_unrecognized_file_count += 1
                continue

            markdown_question_count += len(records)
            for record in records:
                q, missing, invalid, duplicate = _add_record(
                    record.get("type", "unknown"),
                    record,
                    type_counts=type_counts,
                    knowledge_point_counts=knowledge_point_counts,
                    question_fingerprints=question_fingerprints,
                )
                question_count += q
                missing_answer_count += missing
                invalid_count += invalid
                duplicate_count += duplicate

    content_stats = {
        "markdown_file_count": max(0, len(sources) - 1),
        "markdown_question_count": markdown_question_count,
        "markdown_unrecognized_file_count": markdown_unrecognized_file_count,
        "markdown_bytes": markdown_bytes,
        "markdown_lines": markdown_lines,
        "markdown_encoding_error_count": markdown_encoding_error_count,
    }

    return {
        "sources": [str(path) for path in sources],
        "source_count": len(sources),
        "json_source_count": 1,
        "markdown_file_count": max(0, len(sources) - 1),
        "question_count": question_count,
        "type_counts": dict(sorted(type_counts.items())),
        "knowledge_point_counts": dict(sorted(knowledge_point_counts.items())),
        "missing_answer_count": missing_answer_count,
        "duplicate_count": duplicate_count,
        "invalid_count": invalid_count,
        "encoding_error_count": encoding_error_count,
        "content_stats": content_stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect training data sources.")
    parser.add_argument(
        "--json-source",
        type=Path,
        default=DEFAULT_JSON_SOURCE,
        help="Path to the structured JSON training bank.",
    )
    parser.add_argument(
        "--markdown-dir",
        type=Path,
        default=None,
        help="Optional directory whose Markdown files are included as sources.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional output path for the JSON report; stdout is always emitted.",
    )
    args = parser.parse_args()
    report = inspect_training_sources(args.json_source, args.markdown_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
