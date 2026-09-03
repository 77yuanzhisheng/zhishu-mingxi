import json

from scripts.prepare_finetune_dataset import (
    normalize_text,
    question_bank_records,
    validate_and_deduplicate,
    write_jsonl,
)


def test_question_bank_converts_all_112_records():
    records = question_bank_records(
        __import__("pathlib").Path("data/documents/老师训练题库.json")
    )
    assert len(records) == 112
    assert {record["metadata"]["question_type"] for record in records} == {
        "fill", "calc", "proof", "app"
    }


def test_normalize_text_unifies_symbols_and_html():
    value, count = normalize_text(r"\forall x(P(x)\to Q(x))<br>\neg Q(x)\vee P(x)")
    assert value == "∀ x(P(x)→ Q(x))\n¬ Q(x)∨ P(x)"
    assert count == 4


def test_normalize_text_does_not_corrupt_longer_latex_commands():
    value, count = normalize_text(r"\sum_{n=0}^{\infty} a_n, x\in A")
    assert r"\infty" in value
    assert "x∈ A" in value
    assert count == 1


def test_validator_removes_exact_duplicates_and_flags_conflicts():
    base = {"system": "s", "user": "P \\to Q", "assistant": "P→Q"}
    duplicate = {"system": "s", "user": "P → Q", "assistant": "P → Q"}
    conflict = {"system": "s", "user": "P→Q", "assistant": "错误答案"}
    cleaned, report = validate_and_deduplicate([base, duplicate, conflict])
    assert len(cleaned) == 1
    assert report.duplicate_count == 1
    assert report.conflict_count == 1
    assert report.passed is False


def test_validator_accepts_messages_format_and_writes_jsonl(tmp_path):
    records = [{
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
    }]
    cleaned, report = validate_and_deduplicate(records)
    assert report.passed is True
    output = tmp_path / "clean.jsonl"
    write_jsonl(output, cleaned)
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row == {"system": "system", "user": "question", "assistant": "answer"}


def test_validator_rejects_missing_required_fields():
    cleaned, report = validate_and_deduplicate([{"system": "s", "user": "u"}])
    assert cleaned == []
    assert report.invalid_count == 1
    assert report.passed is False
