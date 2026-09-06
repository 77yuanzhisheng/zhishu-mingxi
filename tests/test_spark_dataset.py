"""Tests for Spark MaaS dataset normalization and JSONL export."""

from __future__ import annotations

import json
import math

import pytest

from backend.training.dataset import (
    build_messages,
    split_records,
    validate_record,
    write_jsonl,
)


def _fingerprints(records):
    return [f"{record.get('instruction', record.get('q', ''))}\n{record.get('answer', record.get('a', ''))}" for record in records]


def test_build_messages_uses_system_user_assistant_roles_and_context():
    record = {
        "instruction": "解释命题逻辑中的蕴含关系。",
        "answer": "命题 P→Q 仅在 P 真且 Q 假时为假。",
        "knowledge_point": "命题逻辑",
        "type": "concept",
    }

    sample = build_messages(record)

    assert [item["role"] for item in sample["messages"]] == [
        "system",
        "user",
        "assistant",
    ]
    assert "命题逻辑" in sample["messages"][1]["content"]
    assert "蕴含" in sample["messages"][1]["content"]


def test_build_messages_accepts_question_bank_aliases():
    sample = build_messages({"q": "求集合交集", "a": "A∩B", "kp": "set-ops"})

    assert "知识点：set-ops" in sample["messages"][1]["content"]
    assert "求集合交集" in sample["messages"][1]["content"]
    assert sample["messages"][2]["content"] == "A∩B"


def test_validate_record_reports_missing_answer_only_for_missing_answer():
    assert validate_record({"instruction": "解释命题"}) == ["answer"]


def test_validate_record_rejects_blank_instruction_and_non_finite_values():
    errors = validate_record({"instruction": " ", "answer": "答案", "score": math.inf})

    assert "instruction" in errors
    assert "non_finite" in errors


def test_split_records_is_deterministic_disjoint_and_uses_default_ratio():
    records = [
        {"id": str(i), "instruction": f"q-{i}", "answer": f"a-{i}"}
        for i in range(10)
    ]

    parts = split_records(records, seed=17)
    again = split_records(records, seed=17)
    ids = {name: {record["id"] for record in values} for name, values in parts.items()}

    assert parts == again
    assert ids["train"].isdisjoint(ids["validation"])
    assert ids["train"].isdisjoint(ids["test"])
    assert ids["validation"].isdisjoint(ids["test"])
    assert {key: len(value) for key, value in parts.items()} == {
        "train": 8,
        "validation": 1,
        "test": 1,
    }


def test_split_records_keeps_a_test_example_for_small_datasets_and_deduplicates():
    records = [
        {"id": "first", "instruction": " Q ", "answer": " A "},
        {"id": "duplicate", "instruction": "q", "answer": "a"},
        {"id": "second", "instruction": "另一个问题", "answer": "另一个答案"},
    ]

    parts = split_records(records, seed=3)
    all_fingerprints = [item for values in parts.values() for item in _fingerprints(values)]

    assert len(parts["test"]) == 1
    assert len(all_fingerprints) == len(set(all_fingerprints)) == 2


def test_write_jsonl_is_utf8_json_per_line_and_rejects_non_finite(tmp_path):
    path = tmp_path / "train.jsonl"
    records = [
        {
            "messages": [
                {"role": "system", "content": "你是离散数学教师。"},
                {"role": "user", "content": "什么是集合？"},
                {"role": "assistant", "content": "集合是确定对象的总体。"},
            ]
        }
    ]

    assert write_jsonl(records, path) == 1
    raw = path.read_bytes()
    assert "离散数学教师" in raw.decode("utf-8")
    assert len(raw.splitlines()) == 1
    assert json.loads(raw.decode("utf-8")) == records[0]

    with pytest.raises(ValueError, match="non-finite|NaN|Infinity"):
        write_jsonl([{"score": float("nan")}], tmp_path / "invalid.jsonl")

from pathlib import Path
import subprocess
import sys

from scripts.build_spark_dataset import build_dataset


def _write_question_bank(path: Path, records):
    path.write_text(
        json.dumps({"total": len(records), "exams": [{"id": "fixture", "title": "测试", "calc": records}]}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_build_dataset_generates_three_jsonl_files_and_summary(tmp_path):
    source = tmp_path / "questions.json"
    records = [
        {"q": f"问题{i}", "a": f"答案{i}", "kp": "logic"}
        for i in range(10)
    ]
    _write_question_bank(source, records)
    rules = tmp_path / "rules.json"
    rules.write_text('{"version": "test"}\n', encoding="utf-8")
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "lesson.md").write_text("# 课程\n", encoding="utf-8")

    summary = build_dataset(source, documents, rules, tmp_path / "out", seed=17)

    assert summary["source_question_count"] == 10
    assert summary["valid_count"] == 10
    assert summary["duplicate_count"] == 0
    assert summary["splits"] == {"train": 8, "validation": 1, "test": 1}
    assert summary["seed"] == 17
    assert summary["manifest_path"] == str((tmp_path / "out" / "manifest.json").resolve())
    assert summary["type_counts"] == {"calc": 10}
    assert summary["knowledge_point_counts"] == {"logic": 10}
    assert set(summary["split_sha256"]) == {"train", "validation", "test"}
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 17
    assert manifest["rules"]["version"] == "test"
    assert manifest["splits"]["train"]["count"] == 8
    assert len(manifest["splits"]["train"]["sha256"]) == 64
    for name, count in summary["splits"].items():
        path = tmp_path / "out" / f"{name}.jsonl"
        assert path.exists()
        assert len(path.read_text(encoding="utf-8").splitlines()) == count
        for line in path.read_text(encoding="utf-8").splitlines():
            sample = json.loads(line)
            assert [m["role"] for m in sample["messages"]] == ["system", "user", "assistant"]


def test_build_dataset_deduplicates_before_splitting(tmp_path):
    source = tmp_path / "questions.json"
    _write_question_bank(source, [
        {"q": "???", "a": "??", "kp": "logic"},
        {"q": " ??? ", "a": "??", "kp": "logic"},
        {"q": "???", "a": "?????", "kp": "logic"},
    ])
    rules = tmp_path / "rules.json"
    rules.write_text('{}', encoding="utf-8")

    summary = build_dataset(source, tmp_path, rules, tmp_path / "out", seed=1)

    assert summary["valid_count"] == 3
    assert summary["duplicate_count"] == 1
    assert sum(summary["splits"].values()) == 2


def test_build_dataset_real_question_bank_is_90_11_11(tmp_path):
    source = next(Path("data/documents").glob("*.json"))
    rules = Path("data/training/symbol_rules.json")

    summary = build_dataset(source, Path("data/documents"), rules, tmp_path / "out", seed=20260903)

    assert summary["source_question_count"] == 112
    assert summary["valid_count"] == 112
    assert summary["splits"] == {"train": 90, "validation": 11, "test": 11}


def test_build_dataset_failure_does_not_overwrite_existing_valid_output(tmp_path):
    source = tmp_path / "questions.json"
    _write_question_bank(source, [{"q": "原题", "a": "原答", "kp": "logic"}])
    rules = tmp_path / "rules.json"
    rules.write_text('{}', encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "train.jsonl"
    sentinel.write_text("KEEP-ME\n", encoding="utf-8")

    invalid_source = tmp_path / "invalid.json"
    _write_question_bank(invalid_source, [{"q": "缺答案", "a": "", "kp": "logic"}])

    with pytest.raises(ValueError, match="validation|invalid"):
        build_dataset(invalid_source, tmp_path, rules, output, seed=1)

    assert sentinel.read_text(encoding="utf-8") == "KEEP-ME\n"
    assert not (output / "validation.jsonl").exists()
    assert not (output / "test.jsonl").exists()


def test_build_dataset_records_documents_and_rules_without_modifying_sources(tmp_path):
    source = tmp_path / "questions.json"
    _write_question_bank(source, [{"q": "题目", "a": "答案", "kp": "logic"}])
    documents = tmp_path / "documents"
    documents.mkdir()
    markdown = documents / "lesson.md"
    markdown.write_text("# 课程\n", encoding="utf-8")
    rules = tmp_path / "rules.json"
    rules.write_text('{"rules": []}\n', encoding="utf-8")
    source_before = source.read_bytes()
    markdown_before = markdown.read_bytes()
    rules_before = rules.read_bytes()

    summary = build_dataset(source, documents, rules, tmp_path / "out", seed=2)

    assert summary["documents_dir"] == str(documents.resolve())
    assert summary["rules_source"] == str(rules.resolve())
    assert source.read_bytes() == source_before
    assert markdown.read_bytes() == markdown_before
    assert rules.read_bytes() == rules_before


def test_build_dataset_manifest_is_deterministic_and_tracks_source_hashes(tmp_path):
    source = tmp_path / "questions.json"
    _write_question_bank(source, [{"q": "题目", "a": "答案", "kp": "logic"}])
    rules = tmp_path / "rules.json"
    rules.write_text('{"version":"v1"}', encoding="utf-8")
    first = tmp_path / "first"
    second = tmp_path / "second"

    build_dataset(source, tmp_path, rules, first, seed=9)
    build_dataset(source, tmp_path, rules, second, seed=9)

    first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert first_manifest["source"]["sha256"] == second_manifest["source"]["sha256"]
    assert first_manifest["rules"]["sha256"] == second_manifest["rules"]["sha256"]
    assert first_manifest["splits"] == second_manifest["splits"]


def test_build_dataset_reports_type_and_knowledge_point_counts_per_split(tmp_path):
    source = tmp_path / "questions.json"
    _write_question_bank(
        source,
        [
            {"q": "计算", "a": "答案", "kp": "counting"},
            {"q": "证明", "a": "答案", "kp": "sets"},
            {"q": "概念", "a": "答案", "kp": "sets"},
        ],
    )
    rules = tmp_path / "rules.json"
    rules.write_text('{"version":"v1"}', encoding="utf-8")

    summary = build_dataset(source, tmp_path, rules, tmp_path / "out", seed=1)

    assert summary["type_counts"] == {"calc": 3}
    assert summary["knowledge_point_counts"] == {"counting": 1, "sets": 2}
    assert sum(summary["split_type_counts"]["calc"].values()) == 3


def test_cli_returns_nonzero_on_validation_error_and_keeps_output(tmp_path):
    source = tmp_path / "questions.json"
    _write_question_bank(source, [{"q": "坏题", "a": "", "kp": "logic"}])
    rules = tmp_path / "rules.json"
    rules.write_text('{}', encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "train.jsonl"
    sentinel.write_text("KEEP\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_spark_dataset.py",
            "--questions", str(source),
            "--documents", str(tmp_path),
            "--rules", str(rules),
            "--output", str(output),
            "--seed", "3",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "invalid" in (completed.stderr + completed.stdout).lower()
    assert sentinel.read_text(encoding="utf-8") == "KEEP\n"
