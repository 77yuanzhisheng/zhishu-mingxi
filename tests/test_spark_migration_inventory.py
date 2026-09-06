from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.inspect_training_sources import inspect_training_sources


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRAINING_BANK = REPOSITORY_ROOT / "data" / "documents" / "老师训练题库.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_training_bank_inventory_exposes_stable_contract():
    report = inspect_training_sources(TRAINING_BANK)

    assert {
        "sources",
        "question_count",
        "type_counts",
        "knowledge_point_counts",
        "missing_answer_count",
        "duplicate_count",
        "invalid_count",
        "encoding_error_count",
        "content_stats",
    } <= report.keys()
    assert report["question_count"] == 112
    assert sum(report["type_counts"].values()) == report["question_count"]
    assert report["type_counts"] == {"fill": 56, "calc": 36, "proof": 16, "app": 4}
    assert report["knowledge_point_counts"]["set-ops"] == 4
    assert report["missing_answer_count"] == 0
    assert report["invalid_count"] == 0
    assert report["duplicate_count"] == 0
    assert report["encoding_error_count"] == 0
    assert report["content_stats"]["markdown_question_count"] == 0
    assert report["sources"] == [str(TRAINING_BANK)]


def test_markdown_parser_counts_only_explicit_question_blocks(tmp_path):
    source = tmp_path / "training.json"
    source.write_text(json.dumps({"exams": []}), encoding="utf-8")
    markdown_dir = tmp_path / "markdown"
    markdown_dir.mkdir()
    recognized = markdown_dir / "lesson.md"
    recognized.write_text(
        """# Discrete math notes

## Question 1
question: Prove that A ⊆ B.
answer: Let x ∈ A. Then x ∈ B.
type: proof
kp: set-ops

## Notes
This paragraph mentions a question but has no question field.
""",
        encoding="utf-8",
    )
    ignored = markdown_dir / "notes.md"
    ignored.write_text(
        """# Unstructured notes

A question-like sentence without the explicit question field must not become a sample.
""",
        encoding="utf-8",
    )

    before = {path: _sha256(path) for path in [source, recognized, ignored]}
    report = inspect_training_sources(source, markdown_dir)
    after = {path: _sha256(path) for path in [source, recognized, ignored]}

    assert report["sources"] == [str(source), str(recognized), str(ignored)]
    assert report["question_count"] == 1
    assert report["type_counts"] == {"proof": 1}
    assert report["knowledge_point_counts"] == {"set-ops": 1}
    assert report["missing_answer_count"] == 0
    assert report["invalid_count"] == 0
    assert report["content_stats"]["markdown_file_count"] == 2
    assert report["content_stats"]["markdown_question_count"] == 1
    assert report["content_stats"]["markdown_unrecognized_file_count"] == 1
    assert report["content_stats"]["markdown_bytes"] > 0
    assert report["content_stats"]["markdown_lines"] > 0
    assert before == after


def test_markdown_encoding_errors_are_reported_without_fabricating_questions(tmp_path):
    source = tmp_path / "training.json"
    source.write_text(json.dumps({"exams": []}), encoding="utf-8")
    markdown_dir = tmp_path / "markdown"
    markdown_dir.mkdir()
    bad = markdown_dir / "bad.md"
    bad.write_bytes(b"# invalid utf8\xff\xfe")

    report = inspect_training_sources(source, markdown_dir)

    assert report["question_count"] == 0
    assert report["encoding_error_count"] == 1
    assert report["content_stats"]["markdown_encoding_error_count"] == 1
    assert report["invalid_count"] == 1


def test_inventory_cli_emits_json_and_does_not_change_source(tmp_path):
    source = tmp_path / "training.json"
    source.write_text(
        json.dumps(
            {"exams": [{"calc": [{"q": "1+1?", "a": "2", "kp": "counting"}]}]}
        ),
        encoding="utf-8",
    )
    before = _sha256(source)
    output_path = tmp_path / "report.json"
    script = REPOSITORY_ROOT / "scripts" / "inspect_training_sources.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--json-source",
            str(source),
            "--json-out",
            str(output_path),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    stdout_report = json.loads(result.stdout)
    file_report = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_report == file_report
    assert stdout_report["question_count"] == 1
    assert stdout_report["type_counts"] == {"calc": 1}
    assert stdout_report["knowledge_point_counts"] == {"counting": 1}
    assert stdout_report["content_stats"]["markdown_file_count"] == 0
    assert _sha256(source) == before


def test_inventory_rejects_missing_json_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        inspect_training_sources(tmp_path / "missing.json")
