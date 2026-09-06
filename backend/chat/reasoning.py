"""Symbolic-reasoning enhancement for the multi-turn chat chain.

将 backend.reasoning 的符号校验/证明计划能力注入多轮对话链路：
- 证明/推导/计算题启用教材式结构提示（已知/分析/推导/自检/结论/证毕）
- 注入程序侧符号校验结果（z3/SymPy），约束 LLM 回答与证据一致
- 回答生成后做结构化评估（是否遵循教材式结构）
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from backend.reasoning.service import (
    QuestionType,
    build_proof_plan,
    detect_question_type,
    evaluate_reasoning_answer,
    format_proof_plan_for_prompt,
    merge_reasoning_prompt,
    verify_symbolic_statement,
)


@dataclass
class ReasoningEnhancements:
    """一次回答所需的推理增强配置（纯计算，无副作用）。"""

    enabled: bool
    question_type: str
    symbolic_check: dict[str, Any]
    proof_plan: dict[str, Any]
    system_prompt: str
    check_note: str


@dataclass(frozen=True)
class SymbolFidelity:
    """Post-generation check that preserves the operators used by the prompt."""

    checked: bool
    passed: bool
    required_symbols: tuple[str, ...] = ()
    missing_symbols: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class NaturalDeductionValidity:
    """Narrow post-generation guard for obviously invalid proof steps."""

    checked: bool
    passed: bool
    detail: str = ""


_LOGIC_SYMBOLS = ("∀", "∃", "¬", "∧", "∨", "→", "↔", "⇔", "≡", "∪", "∩")
_LATEX_SYMBOLS = {
    r"\forall": "∀",
    r"\exists": "∃",
    r"\neg": "¬",
    r"\land": "∧",
    r"\lor": "∨",
    r"\to": "→",
    r"\rightarrow": "→",
    r"\leftrightarrow": "↔",
    r"\Leftrightarrow": "⇔",
    r"\equiv": "≡",
    r"\cup": "∪",
    r"\cap": "∩",
}


def build_reasoning_enhancements(
    question: str,
    base_system_prompt: str,
) -> ReasoningEnhancements:
    """根据问题构建推理增强（题型判断/证明计划/符号校验/提示词合并）。"""
    question_type = detect_question_type(question)
    enabled = question_type != QuestionType.GENERAL

    symbolic = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    system_prompt = merge_reasoning_prompt(base_system_prompt, question)
    fidelity_note = symbol_fidelity_prompt(question)
    if fidelity_note:
        system_prompt = f"{system_prompt.rstrip()}\n\n{fidelity_note}"
    return ReasoningEnhancements(
        enabled=enabled,
        question_type=question_type.value,
        symbolic_check=asdict(symbolic),
        proof_plan=asdict(plan),
        system_prompt=system_prompt,
        check_note=_check_note(symbolic),
    )


def build_check_note(question: str) -> str:
    """仅构建程序侧符号校验提示（供单元测试/说明文档使用）。"""
    return _check_note(verify_symbolic_statement(question))


def evaluate_answer(
    answer: str,
    question: str,
    enhancements: ReasoningEnhancements | None = None,
) -> dict[str, Any] | None:
    """生成后评估：问题未启用推理时不评估，返回 None；否则返回完整推理元数据。"""
    if not answer:
        return None
    if detect_question_type(question) == QuestionType.GENERAL:
        return None
    metadata: dict[str, Any] = {
        "enabled": True,
        "question_type": detect_question_type(question).value,
        "evaluation": asdict(evaluate_reasoning_answer(answer, question=question)),
    }
    if enhancements is not None:
        metadata["symbolic_check"] = enhancements.symbolic_check
        metadata["proof_plan"] = enhancements.proof_plan
    fidelity = check_symbol_fidelity(answer, question)
    metadata["symbol_fidelity"] = asdict(fidelity)
    return metadata


def check_symbol_fidelity(answer: str, question: str) -> SymbolFidelity:
    """Ensure every logical operator present in the prompt survives the answer.

    This is intentionally a narrow guardrail, not a theorem prover. It catches
    destructive substitutions such as ``∨`` becoming ``→`` while allowing the
    model to add valid intermediate formulas.
    """
    required = tuple(
        symbol
        for symbol in _LOGIC_SYMBOLS
        if symbol in _normalize_formula_text(question)
    )
    if not required:
        return SymbolFidelity(False, True, detail="题目未包含可锁定的逻辑符号")

    answer_text = _normalize_formula_text(answer)
    missing = tuple(symbol for symbol in required if symbol not in answer_text)
    if missing:
        return SymbolFidelity(
            True,
            False,
            required_symbols=required,
            missing_symbols=missing,
            detail="回答缺少题设中的关键逻辑符号，可能改写了题设公式",
        )
    required_formulas = _extract_formula_fragments(question)
    answer_formulas = set(_extract_formula_fragments(answer))
    missing_formulas = tuple(
        formula for formula in required_formulas if formula not in answer_formulas
    )
    if missing_formulas:
        return SymbolFidelity(
            True,
            False,
            required_symbols=required,
            detail="回答未保留题设公式结构：" + "；".join(missing_formulas),
        )
    return SymbolFidelity(
        True,
        True,
        required_symbols=required,
        detail="回答保留了题设中的关键逻辑符号和公式结构",
    )


def check_natural_deduction_validity(
    answer: str, question: str
) -> NaturalDeductionValidity:
    """Reject unsupported negations in the common quantifier proof pattern.

    This is deliberately a focused guardrail rather than a full first-order
    theorem prover. It catches the known failure where a proof claims that
    ``Q(a)`` directly yields ``¬Q(a)``.
    """
    normalized_question = _normalize_formula_text(question)
    if not all(token in normalized_question for token in ("∀", "∃", "→", "¬", "∨")):
        return NaturalDeductionValidity(False, True, "题目不属于当前自然演绎守卫范围")

    normalized_answer = _normalize_formula_text(answer)
    has_q = bool(re.search(r"(?<!¬)Q\(a\)", normalized_answer))
    has_not_q = "¬Q(a)" in normalized_answer
    claims_negation_from_q = bool(
        has_q
        and has_not_q
        and re.search(r"Q\(a\).{0,80}(?:否定|推出|得到).{0,40}¬Q\(a\)", normalized_answer)
    ) or bool(
        has_q
        and has_not_q
        and re.search(r"¬Q\(a\).{0,80}(?:Q\(a\)|步骤\d+的否定)", normalized_answer)
    )
    # Detect the invalid direct shortcut Q(c), P(c)->not-Q(c), therefore not-P(c).
    # A valid proof must include an explicit temporary assumption before it
    # discharges the contradiction.
    q_index = normalized_answer.find("Q(c)")
    implication = "P(c)\u2192\u00acQ(c)"
    negated_p = "\u00acP(c)"
    implication_index = normalized_answer.find(implication, q_index + 1)
    negated_p_index = normalized_answer.find(negated_p, implication_index + 1)
    shortcut_window = (
        q_index >= 0
        and implication_index >= 0
        and negated_p_index >= 0
        and negated_p_index - q_index <= 240
    )
    assumption_markers = ("\u53cd\u8bbe P(c)", "\u5047\u8bbe P(c)", "\u8bbe P(c)")
    has_explicit_assumption = any(
        marker in normalized_answer[q_index : negated_p_index + len(negated_p)]
        for marker in assumption_markers
    )
    claims_not_p_from_positive_q = shortcut_window and not has_explicit_assumption
    if claims_negation_from_q or claims_not_p_from_positive_q:
        return NaturalDeductionValidity(
            True,
            False,
            "不能由 Q(a) 推出 ¬Q(a)；应先反设 P(a)，由 P(a)→¬Q(a) 得到矛盾，再推出 ¬P(a)",
        )
    return NaturalDeductionValidity(True, True, "未发现明显无效的自然演绎步骤")


def symbol_fidelity_prompt(question: str) -> str:
    """Build a direct, always-on instruction for formula preservation."""
    fidelity = check_symbol_fidelity("", question)
    if not fidelity.checked:
        return ""
    symbols = "、".join(fidelity.required_symbols)
    return (
        "【题设符号锁定】\n"
        f"题目中出现的关键逻辑符号为：{symbols}。\n"
        "在‘已知’和后续推导中必须保持题设公式的原有结构；禁止把 ∨ 改成 →、"
        "把 ∧ 改成 ∨，或擅自增删 ¬、∀、∃ 等符号。若需要改写，必须明确写出等价依据。"
    )


def _extract_formula_fragments(text: str) -> tuple[str, ...]:
    """Extract quantified formulas in a canonical form for structure checks."""
    normalized = _normalize_formula_text(text)
    starts = [match.start() for match in re.finditer(r"[∀∃][A-Za-z]", normalized)]
    formulas: list[str] = []
    for start in starts:
        end = _formula_fragment_end(normalized, start, len(normalized))
        signature = _formula_signature(normalized[start:end])
        if signature:
            formulas.append(signature)
    return tuple(dict.fromkeys(formulas))


def _formula_fragment_end(text: str, start: int, limit: int) -> int:
    """Find the end of one quantified formula, including nested terms."""
    body_start = start + 2
    while body_start < limit and text[body_start] == ")":
        body_start += 1
    if body_start >= limit:
        return body_start
    if text[body_start] == "(":
        return _balanced_end(text, body_start, limit)
    if text[body_start] == "¬":
        return _atom_end(text, body_start + 1, limit)
    return _expression_end(text, body_start, limit)


def _balanced_end(text: str, start: int, limit: int) -> int:
    depth = 0
    for index in range(start, limit):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return limit


def _atom_end(text: str, start: int, limit: int) -> int:
    match = re.match(r"[A-Za-z][A-Za-z0-9_]*", text[start:limit])
    if not match:
        return _expression_end(text, start, limit)
    end = start + match.end()
    return _balanced_end(text, end, limit) if end < limit and text[end] == "(" else end


def _expression_end(text: str, start: int, limit: int) -> int:
    delimiter = re.search(r"[，,。；;\n]", text[start:limit])
    return start + delimiter.start() if delimiter else limit


def _formula_signature(clause: str) -> str:
    match = re.search(r"[∀∃][A-Za-z]", clause)
    if not match:
        return ""
    clause = clause[match.start():]
    clause = re.sub(r"([∀∃][A-Za-z])\)\(", r"\1(", clause)
    clause = re.sub(r"([∀∃][A-Za-z])\)", r"\1", clause)
    return clause.strip(" ").rstrip("，,。；; ")


def _normalize_formula_text(text: str) -> str:
    normalized = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        text,
    )
    normalized = normalized.replace(r"\(", "").replace(r"\)", "")
    for latex, symbol in sorted(_LATEX_SYMBOLS.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(latex, symbol)
    normalized = re.sub(r"\\([\[\]])", r"\1", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized

def proof_plan_note(question: str) -> str:
    """证明计划文本（注入知识库材料时使用），未启用时返回空串。"""
    plan = build_proof_plan(question)
    if not plan.enabled:
        return ""
    return format_proof_plan_for_prompt(plan)


def _check_note(symbolic: Any) -> str:
    if not symbolic.checked:
        return ""
    status = "通过" if symbolic.valid else "未通过"
    note = (
        f"程序侧符号校验结果：{status}；校验方式：{symbolic.detail}。"
        "回答中的公式、真值表或中间结论必须与该校验结果一致。"
    )
    if symbolic.evidence:
        note += f"\n程序侧符号证据：\n{symbolic.evidence}"
    return note
