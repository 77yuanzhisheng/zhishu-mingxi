"""Build deterministic Spark MaaS SFT JSONL files from the question bank."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

# Allow direct execution from the repository root or from any working directory.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from backend.training.dataset import build_messages, split_records, validate_record, write_jsonl


DEFAULT_QUESTIONS = Path("data/documents/\u8001\u5e08\u8bad\u7ec3\u9898\u5e93.json")
DEFAULT_DOCUMENTS = Path("data/documents")
DEFAULT_RULES = Path("data/training/symbol_rules.json")
DEFAULT_OUTPUT = Path("outputs/spark_dataset")


def _iter_question_records(payload: Any) -> Iterable[dict[str, Any]]:
    """Yield normalized source records from supported question-bank shapes."""
    if isinstance(payload, dict):
        exams = payload.get("exams")
        if isinstance(exams, list):
            for exam in exams:
                if not isinstance(exam, dict):
                    yield exam  # type: ignore[misc]
                    continue
                for question_type, records in exam.items():
                    if question_type in {"id", "title"} or not isinstance(records, list):
                        continue
                    for record in records:
                        if isinstance(record, dict):
                            normalized = dict(record)
                            normalized.setdefault("type", question_type)
                            yield normalized
                        else:
                            yield record  # type: ignore[misc]
            return
        records = payload.get("questions")
        if isinstance(records, list):
            for record in records:
                yield record  # type: ignore[misc]
            return
    elif isinstance(payload, list):
        for record in payload:
            yield record  # type: ignore[misc]
        return
    raise ValueError("questions JSON must contain an exams/questions list or be a list")


def _load_questions(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read questions source {path}: {exc}") from exc
    return list(_iter_question_records(payload))


def _validate_rules(path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read rules source {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_info(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    return {"path": str(resolved), "sha256": _sha256(resolved)}


def _source_summary(documents: Path) -> dict[str, Any]:
    if not documents.is_dir():
        raise ValueError(f"documents directory does not exist: {documents}")
    markdown_files = sorted(documents.rglob("*.md"))
    return {
        "documents_dir": str(documents.resolve()),
        "markdown_file_count": len(markdown_files),
        "markdown_sources": [str(path.resolve()) for path in markdown_files],
        "markdown_source_hashes": {str(path.resolve()): _sha256(path) for path in markdown_files},
    }


def _validate_and_build(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    valid: list[dict[str, Any]] = []
    invalid_count = 0
    error_counts: Counter[str] = Counter()
    for index, record in enumerate(records, start=1):
        errors = validate_record(record)
        if errors:
            invalid_count += 1
            error_counts.update(errors)
            continue
        valid.append(build_messages(record))
    return valid, {"invalid_count": invalid_count, "error_counts": dict(sorted(error_counts.items()))}


def _atomic_write_dataset(splits: dict[str, list[dict[str, Any]]], output: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        for name in ("train", "validation", "test"):
            write_jsonl(splits[name], temp_dir / f"{name}.jsonl")
        split_meta = {
            name: {"count": len(splits[name]), "sha256": _sha256(temp_dir / f"{name}.jsonl")}
            for name in ("train", "validation", "test")
        }
        manifest["splits"] = split_meta
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            if not output.is_dir():
                raise ValueError(f"output path is not a directory: {output}")
            backup = output.parent / f".{output.name}.old-{next(tempfile._get_candidate_names())}"
            output.rename(backup)
            try:
                temp_dir.rename(output)
            except Exception:
                backup.rename(output)
                raise
            shutil.rmtree(backup)
        else:
            temp_dir.rename(output)
        return split_meta
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def build_dataset(
    questions: str | Path = DEFAULT_QUESTIONS,
    documents: str | Path = DEFAULT_DOCUMENTS,
    rules: str | Path = DEFAULT_RULES,
    output: str | Path = DEFAULT_OUTPUT,
    *,
    seed: int = 20260903,
) -> dict[str, Any]:
    """Build and atomically publish Spark dataset files.

    Existing output is untouched until all input validation, transformation,
    JSON serialization, and temporary writes succeed.
    """
    questions_path = Path(questions)
    documents_path = Path(documents)
    rules_path = Path(rules)
    output_path = Path(output)
    if not questions_path.is_file():
        raise ValueError(f"questions source does not exist: {questions_path}")
    if not rules_path.is_file():
        raise ValueError(f"rules source does not exist: {rules_path}")

    source_records = _load_questions(questions_path)
    source_info = _source_summary(documents_path)
    _validate_rules(rules_path)
    rules_payload = json.loads(rules_path.read_text(encoding="utf-8"))
    valid_source_records, validation = _validate_and_build(source_records)
    if validation["invalid_count"]:
        details = ", ".join(
            f"{key}={value}" for key, value in validation["error_counts"].items()
        )
        raise ValueError(
            f"invalid training records: {validation['invalid_count']} ({details})"
        )

    # Deduplication is performed by the shared splitter. Since the splitter
    # operates on source-shaped records, rebuild messages after the split.
    # This preserves the exact dedupe semantics of backend.training.dataset.
    source_unique_and_split = split_records(source_records, seed=seed)
    unique_count = sum(map(len, source_unique_and_split.values()))
    splits = {
        name: [build_messages(record) for record in records]
        for name, records in source_unique_and_split.items()
    }
    split_counts = {name: len(records) for name, records in splits.items()}
    type_counts = Counter(
        str(item.get("type", "unknown"))
        for records in source_unique_and_split.values()
        for item in records
    )
    knowledge_point_counts = Counter(
        str(item.get("kp", item.get("knowledge_point", "unknown")))
        for records in source_unique_and_split.values()
        for item in records
    )
    split_type_counts: dict[str, dict[str, int]] = {}
    split_knowledge_point_counts: dict[str, dict[str, int]] = {}
    for split_name, records in source_unique_and_split.items():
        for item in records:
            question_type = str(item.get("type", "unknown"))
            knowledge_point = str(item.get("kp", item.get("knowledge_point", "unknown")))
            split_type_counts.setdefault(question_type, {name: 0 for name in splits})[split_name] += 1
            split_knowledge_point_counts.setdefault(knowledge_point, {name: 0 for name in splits})[split_name] += 1
    type_counts = dict(sorted(type_counts.items()))
    knowledge_point_counts = dict(sorted(knowledge_point_counts.items()))
    manifest = {
        "format": "spark-maas-sft",
        "seed": seed,
        "source": _file_info(questions_path),
        "rules": {**(rules_payload if isinstance(rules_payload, dict) else {}), **_file_info(rules_path)},
        "documents": source_info,
        "splits": split_counts,
        "type_counts": type_counts,
        "knowledge_point_counts": knowledge_point_counts,
        "split_type_counts": split_type_counts,
        "split_knowledge_point_counts": split_knowledge_point_counts,
    }
    split_meta = _atomic_write_dataset(splits, output_path, manifest)
    return {
        "seed": seed,
        "questions_source": str(questions_path.resolve()),
        "rules_source": str(rules_path.resolve()),
        "source_question_count": len(source_records),
        "valid_count": len(valid_source_records),
        "invalid_count": validation["invalid_count"],
        "duplicate_count": len(valid_source_records) - unique_count,
        "splits": split_counts,
        "type_counts": type_counts,
        "knowledge_point_counts": knowledge_point_counts,
        "split_type_counts": split_type_counts,
        "split_knowledge_point_counts": split_knowledge_point_counts,
        "output_dir": str(output_path.resolve()),
        "manifest_path": str((output_path / "manifest.json").resolve()),
        "split_sha256": {name: meta["sha256"] for name, meta in split_meta.items()},
        **source_info,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Spark MaaS messages JSONL dataset.")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260903)
    args = parser.parse_args(argv)
    try:
        summary = build_dataset(
            args.questions,
            args.documents,
            args.rules,
            args.output,
            seed=args.seed,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
