"""符号推理增强测试：题型识别 / 证明计划 / 程序侧符号校验注入。

对应演示「名定理·程序侧符号校验」环节：证明类问题必须在多轮对话链路中
注入教材式结构提示与符号校验证据（原队员1分支 build_chat_payload 方案，
现以 backend.chat.reasoning 纯函数层接入 multi-turn service）。
"""

from __future__ import annotations

import importlib

import pytest

from backend.chat.llm import LLMClient
from backend.chat.models import ChatReference, ChatRequest
from backend.chat.rag import RAGAdapter
from backend.chat.reasoning import build_reasoning_enhancements, build_check_note
from backend.chat.repository import ChatRepository
from backend.chat.service import ChatService
from backend.learning.service import create_user

reasoning = importlib.import_module("backend.chat.reasoning")

PROOF_QUESTION = "证明命题逻辑中的德摩根律：¬(P∧Q) ⇔ ¬P∨¬Q"
GENERAL_QUESTION = "什么是集合？什么是子集关系？"
SET_IDENTITY_QUESTION = "证明集合恒等式：(A∪B)^c = A^c∩B^c"
QUANTIFIER_QUESTION = "证明量词否定律：¬∀xP(x) ⇔ ∃x¬P(x)"

BASE_SYSTEM_PROMPT = "你是离散数学助教。"


class RecordingLLM(LLMClient):
    def __init__(self):
        self.calls: list[list[dict[str, str]]] = []

    def ensure_available(self) -> None:
        return None

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return (
            "已知：目标：证明德摩根律。\n"
            "分析：采用真值表法。\n"
            "推导：步骤1：列出P、Q的真值组合；依据：真值表定义。\n"
            "自检：每一行均已核对。\n"
            "结论：¬(P∧Q) ⇔ ¬P∨¬Q 成立。\n"
            "证毕"
        )


class FakeRAG(RAGAdapter):
    def __init__(self, with_references: bool = True):
        self.with_references = with_references

    def search(self, query: str):
        if not self.with_references:
            return [], "no_results"
        return [
            ChatReference(
                content="德摩根律：¬(P∧Q) ⇔ ¬P∨¬Q，可通过真值表证明。",
                score=0.9,
                metadata={"source_document": "命题逻辑.md", "chapter": "命题逻辑", "page_start": 1},
            )
        ], "ok"


def test_reasoning_enhancements_for_proof():
    """证明题：启用推理、符号校验命中、教材式结构注入。"""
    r = build_reasoning_enhancements(PROOF_QUESTION, BASE_SYSTEM_PROMPT)

    assert r.enabled is True
    assert r.question_type == "proof"
    assert r.symbolic_check["checked"] is True
    assert "已知" in r.system_prompt
    assert "推导" in r.system_prompt
    assert "程序侧符号校验结果" in r.check_note
    assert "T" in r.symbolic_check["evidence"]


def test_reasoning_enhancements_keeps_general_question_unforced():
    """概念题：不强加推理结构与符号校验。"""
    r = build_reasoning_enhancements(GENERAL_QUESTION, BASE_SYSTEM_PROMPT)

    assert r.enabled is False
    assert r.symbolic_check["checked"] is False
    assert r.check_note == ""
    assert "已知" not in r.system_prompt
    assert "证毕" not in r.system_prompt


def test_reasoning_enhancements_injects_proof_plan():
    """集合恒等式：证明计划选择元素归属法。"""
    r = build_reasoning_enhancements(SET_IDENTITY_QUESTION, BASE_SYSTEM_PROMPT)

    assert r.proof_plan["enabled"] is True
    assert r.proof_plan["method"] == "element_chasing"


def test_reasoning_enhancements_injects_quantifier_proof_plan():
    """量词否定律：证明计划选择量词变换法，证据含 quantifier negation。"""
    r = build_reasoning_enhancements(QUANTIFIER_QUESTION, BASE_SYSTEM_PROMPT)

    assert r.proof_plan["enabled"] is True
    assert r.proof_plan["method"] == "quantifier_transformation"
    assert "quantifier negation" in r.check_note


def test_check_note_builder():
    """build_check_note 独立可用。"""
    note = build_check_note(PROOF_QUESTION)
    assert note.startswith("程序侧符号校验结果：")
    assert build_check_note(GENERAL_QUESTION) == ""


def test_chat_service_injects_check_note_and_returns_reasoning(tmp_path):
    """多轮对话链路：知识库材料消息附带符号校验结果，响应带 reasoning 元数据。"""
    database_path = tmp_path / "chat.db"
    user_id = create_user("学生甲", database_path=database_path)
    llm = RecordingLLM()
    service = ChatService(
        repository=ChatRepository(database_path),
        llm=llm,
        rag=FakeRAG(),
    )
    response = service.chat(ChatRequest(user_id=user_id, message=PROOF_QUESTION))

    # 知识库 system 消息（第2条）附带符号校验结果
    knowledge_msg = next(m for m in llm.calls[0] if "可参考的知识库材料" in m["content"])
    assert "程序侧符号校验结果" in knowledge_msg["content"]

    assert response.reasoning is not None
    assert response.reasoning["enabled"] is True
    assert response.reasoning["question_type"] == "proof"
    assert response.reasoning["symbolic_check"]["checked"] is True
    assert response.reasoning["proof_plan"]["enabled"] is True
    assert response.reasoning["evaluation"] is not None
    assert response.reasoning["evaluation"]["passed"] is True


def test_chat_service_general_question_has_no_reasoning(tmp_path):
    """概念题：reasoning 为空，不增加评估负担。"""
    database_path = tmp_path / "chat.db"
    user_id = create_user("学生乙", database_path=database_path)
    service = ChatService(
        repository=ChatRepository(database_path),
        llm=RecordingLLM(),
        rag=FakeRAG(),
    )
    response = service.chat(ChatRequest(user_id=user_id, message=GENERAL_QUESTION))

    assert response.reasoning is None
