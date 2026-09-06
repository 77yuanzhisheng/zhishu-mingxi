from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from backend.reasoning.rules import ProofValidation, validate_proof_structure
from backend.reasoning.symbols import normalize_symbols, symbol_table


REQUIRED_SYMBOLS = (
    "∀", "∃", "¬", "∧", "∨", "→", "↔", "∈", "∉", "⊆", "⊂", "∪", "∩", "\\", "ᶜ",
    "R", "aRb", "f: A → B", "V", "E", "deg(v)",
)


def test_normalize_symbols_covers_core_discrete_math_synonyms():
    text = (
        "任意 x 属于 A，存在 y 不属于 B；非 P 且 Q，逻辑或 R，P 推出 Q，P 当且仅当 Q；"
        "A 是 B 的子集，A 是 B 的真子集，A 并集 B，A 交集 B，A 差集 B，A 的补集。"
    )

    result = normalize_symbols(text)

    assert result == (
        "∀ x ∈ A，∃ y ∉ B；¬ P ∧ Q，∨ R，P → Q，P ↔ Q；"
        "A 是 B 的⊆，A 是 B 的⊂，A ∪ B，A ∩ B，A \\ B，A 的ᶜ。"
    )


def test_normalize_symbols_replaces_long_phrases_before_shorter_aliases():
    assert normalize_symbols("P 并且 Q") == "P ∧ Q"
    assert normalize_symbols("A 并集 B") == "A ∪ B"
    assert normalize_symbols("A 交集 B") == "A ∩ B"
    assert normalize_symbols("A 差集 B") == "A \\ B"


def test_normalize_symbols_does_not_rewrite_ambiguous_plain_words_without_math_context():
    text = "或者 差错 交代 并行 交朋友 差不多"

    assert normalize_symbols(text) == text


def test_normalize_symbols_preserves_latex_commands_and_their_contents_exactly():
    text = (
        r"\text{并且 属于 差错 交代 或者} "
        r"\operatorname{属于} \text{A ∈ B} \frac{P 且 Q}{\text{并集}}"
    )

    assert normalize_symbols(text) == text


def test_normalize_symbols_preserves_latex_while_normalizing_outside_it():
    text = r"\text{并且} P 且 Q，x 属于 A，\operatorname{属于}"

    assert normalize_symbols(text) == r"\text{并且} P ∧ Q，x ∈ A，\operatorname{属于}"


def test_symbol_table_contains_logic_sets_relations_functions_and_graphs():
    table = symbol_table()

    for symbol in REQUIRED_SYMBOLS:
        assert symbol in table, symbol
        assert set(table[symbol]) >= {"symbol", "meaning", "category", "latex"}
        assert table[symbol]["symbol"] == symbol
        assert table[symbol]["meaning"]
        assert table[symbol]["latex"]

    assert table["R"]["category"] == "relation"
    assert table["aRb"]["category"] == "relation"
    assert table["f: A → B"]["category"] == "function"
    assert table["V"]["category"] == "graph"
    assert table["E"]["category"] == "graph"
    assert table["deg(v)"]["category"] == "graph"


def test_validate_proof_structure_requires_all_four_sections():
    result = validate_proof_structure({"known": "x", "conclusion": "y"})

    assert isinstance(result, ProofValidation)
    assert is_dataclass(result)
    assert result.valid is False
    assert result.missing_fields == ("definitions_or_theorems", "reasoning_steps")
    assert result.warnings == ()


def test_validate_proof_structure_accepts_complete_nonempty_sections():
    result = validate_proof_structure(
        {
            "known": ["A ⊆ B"],
            "definitions_or_theorems": ["子集定义"],
            "reasoning_steps": ["x ∈ A → x ∈ B"],
            "conclusion": "A ⊆ B",
        }
    )

    assert result.valid is True
    assert result.missing_fields == ()
    assert result.warnings == ()


def test_validate_proof_structure_reports_empty_sections_and_extra_payload_shape():
    result = validate_proof_structure(
        {
            "known": "",
            "definitions_or_theorems": [],
            "reasoning_steps": "step",
            "conclusion": None,
        }
    )

    assert result.valid is False
    assert result.missing_fields == ("known", "definitions_or_theorems", "conclusion")
    assert result.warnings == (
        "known must be non-empty",
        "definitions_or_theorems must be non-empty",
        "conclusion must be non-empty",
    )


def test_proof_validation_is_immutable():
    result = validate_proof_structure(
        {
            "known": "x",
            "definitions_or_theorems": "definition",
            "reasoning_steps": "step",
            "conclusion": "y",
        }
    )

    with pytest.raises(FrozenInstanceError):
        result.valid = False


def test_training_symbol_rules_has_stable_auditable_sections():
    import json
    from pathlib import Path

    path = Path("data/training/symbol_rules.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["version"] == "discrete-math-symbols-v1"
    assert payload["symbols"]
    assert payload["inference_rules"]
    assert payload["proof_sections"] == [
        "known",
        "definitions_or_theorems",
        "reasoning_steps",
        "conclusion",
    ]
    assert {item["name"] for item in payload["inference_rules"]} >= {
        "modus_ponens",
        "universal_instantiation",
        "set_membership_transitivity",
        "conjunction_introduction",
        "conjunction_elimination_left",
        "conjunction_elimination_right",
    }
    assert "conjunction_elimination" not in {
        item["name"] for item in payload["inference_rules"]
    }
