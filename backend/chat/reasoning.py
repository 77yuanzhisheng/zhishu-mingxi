"""Symbolic-reasoning enhancement for the multi-turn chat chain.

将 backend.reasoning 的符号校验/证明计划能力注入多轮对话链路：
- 证明/推导/计算题启用教材式结构提示（已知/分析/推导/自检/结论/证毕）
- 注入程序侧符号校验结果（z3/SymPy），约束 LLM 回答与证据一致
- 回答生成后做结构化评估（是否遵循教材式结构）
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
    return metadata


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
