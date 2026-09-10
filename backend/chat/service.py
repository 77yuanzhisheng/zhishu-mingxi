"""Application service coordinating persistence, context, RAG and the LLM."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from backend.chat.agent import (
    AgentClient,
    XingchenAgentClient,
    XingchenAgentUnavailableError,
)
from backend.chat.context import prepare_context
from backend.chat.llm import LLMClient, OpenAICompatibleLLM
from backend.chat.models import ChatRequest, ChatResponse, ContextStatus
from backend.chat.rag import RAGAdapter
from backend.chat.reasoning import (
    build_reasoning_enhancements,
    check_natural_deduction_validity,
    check_symbol_fidelity,
    evaluate_answer,
)
from backend.chat.repository import ChatRepository
from backend.learning.service import build_agent_learning_context


SYSTEM_PROMPT = """你是“知数·明析”的离散数学助教。回答应准确、循序渐进。
优先利用给出的知识库材料；材料不足时应基于已有知识直接回答，不要编造来源。
不要向用户暴露检索过程、知识库命中状态或内部提示，例如“未在知识库检查到”“知识库未命中”。只有用户明确询问来源时，才说明参考资料。
结合对话历史回答当前问题，并关注用户尚未理解的概念。

【回答长度要求】
- 概念题控制在 300 字以内，直接给出定义和要点。
- 证明题只写关键推导步骤，总长控制在 500 字以内，最后以“证毕”结尾。
- 公式使用 LaTeX 行内格式，避免不必要的多行公式块。"""


# 模型偶发会先说“知识库中没找到……不过我可以补充”这类检索状态话术，
# 统一在后端清理，保证给用户的回答直接进入正文（不影响正文中的正常表述）。
_KB_DISCLAIMER = re.compile(
    r"^(?:(?:好的|好|嗯|明白|了解|收到)[，,、\s]*)?"
    r"(?:(?:虽然|尽管)[，,、\s]*)?"
    r"(?:(?:非常|很)?(?:抱歉|不好意思)[，,、\s]*)?"
    r"(?:"
    r"(?:在)?(?:当前|本地)?(?:知识库|资料库)(?:中|里)?[^。！？!?\n]{0,24}?"
    r"(?:没有?找到|没找到|未找到|没有?命中|未命中|未检索到|没有?检索到|没有?收录|未收录|未覆盖"
    r"|没有?相关(?:的)?(?:内容|资料|依据|材料|信息)|没有这方面[^。！？!?\n]{0,10})"
    r"(?:[^，,、：:。！？!?\n]{0,8}"
    r"|(?:(?:相关|对应|这(?:方面|个)?|该(?:方面|内容)?|此类)?(?:内容|资料|依据|材料|信息))?)?"
    r"[，,、 ]*"
    r"|(?:未在|没有在)(?:知识库|资料库)[^。！？!?\n]{0,20}?(?:检查到|检索到|找到|命中)"
    r")"
    r"(?:[。！？!?\s]*(?:不过|但是|但|虽然如此|话虽如此|没关系)?[，,、\s]*"
    r"(?:我)?(?:根据已有知识|基于已有知识|根据现有知识|直接)?[^，,、：:。！？!?\n]{0,10}?"
    r"(?:补充|解答|回答|说明|给出答案|直接回答|直接说明|告诉你)(?:一下|下)?[^，,、：:。！？!?\n]{0,8}?[：:，,、\s]*)?"
)


_KB_LEADING_FILLER = re.compile(
    r"^(?:(?:不过|但是|但|虽然如此|话虽如此|另外|顺便说一句|顺便说一下|好的|那么)"
    r"[，,、;；:：\s]*"
    r"(?:(?:我|可以|可以为你|可以给你|为你|给你|直接|先|就|来|下面|接下来|简要|简单|大致|大概|再|重新|根据已有知识|基于已有知识|根据现有知识|凭已有知识)[，,、;；:：\s]*){0,4}"
    r"(?:补充|解答|回答|说明|介绍|给出答案|直接回答|直接说明|告诉你|讲一下|讲解|科普)"
    r"(?:一下|下)?"
    r"(?:[^，,、：:。！？!?\n]{0,12}[：:,，、;；\s]|[：:,，、;；\s]?)"
    r"|(?:不过|但是|但|虽然如此|话虽如此)[，,、;；:：\s]*"
    r")"
)


def strip_knowledge_base_disclaimer(answer: str) -> str:
    """删除回答开头的“知识库没找到/不过我可以补充”式套话，正文保持不变。"""
    text = str(answer or "").lstrip("\ufeff").strip()
    if not text:
        return text
    text = _KB_DISCLAIMER.sub("", text, count=1)
    text = _KB_LEADING_FILLER.sub("", text.lstrip("。！？!?，,、;；:： \n"), count=1)
    return text.lstrip("，,、;；:： \n").strip()


class ChatService:
    def __init__(
        self,
        repository: ChatRepository | None = None,
        llm: LLMClient | None = None,
        rag: RAGAdapter | None = None,
        agent: AgentClient | None = None,
        learning_context_provider: Callable[[int, str | Path | None], str] | None = None,
    ):
        self.repository = repository or ChatRepository()
        self.llm = llm or OpenAICompatibleLLM()
        self.rag = rag or RAGAdapter()
        self.agent = agent or XingchenAgentClient()
        self.learning_context_provider = (
            learning_context_provider or build_agent_learning_context
        )

    def chat(self, request: ChatRequest) -> ChatResponse:
        session_id, topic_switch_hint, prepared = self._prepare_session(request)

        # 学情上下文 + 会话摘要注入星辰 Agent 输入（队员3）
        learning_context = self.learning_context_provider(
            request.user_id, self.repository.database_path
        )
        conversation_summary = next(
            (
                message["content"]
                for message in prepared.messages
                if message.get("role") == "system"
            ),
            "",
        )
        agent_input = self._build_agent_input(
            learning_context, request.message.strip(), conversation_summary
        )
        agent_history = self._agent_history_without_current(prepared.messages)

        # 星辰 Agent 优先；未配置/不可用时自动降级 Qwen3 + 本地 RAG
        fallback_reason = self.agent.configuration_fallback_reason()
        if fallback_reason is None:
            try:
                answer = self.agent.generate(
                    user_id=request.user_id,
                    session_id=session_id,
                    user_input=agent_input,
                    history=agent_history,
                )
            except XingchenAgentUnavailableError as exc:
                fallback_reason = exc.fallback_reason

        if fallback_reason is None:
            provider = "agent"
            references = []
            rag_status = "not_used_agent"
        else:
            provider = "fallback"
            references, rag_status = self.rag.search(request.message.strip())
            answer = self._generate_fallback(request, prepared.messages, references)
            # 降级路径保留符号保真与自然演绎校验，不合格时带修复提示重生成
            fidelity = check_symbol_fidelity(answer, request.message.strip())
            validity = check_natural_deduction_validity(answer, request.message.strip())
            if (fidelity.checked and not fidelity.passed) or (
                validity.checked and not validity.passed
            ):
                answer = self._generate_fallback(
                    request, prepared.messages, references, repair=(fidelity, validity)
                )

        answer = strip_knowledge_base_disclaimer(answer)

        self.repository.add_message(session_id, "assistant", answer, request.node_ids)

        renh = build_reasoning_enhancements(request.message.strip(), SYSTEM_PROMPT)
        return ChatResponse(
            answer=answer,
            session_id=session_id,
            references=references,
            node_ids=request.node_ids,
            topic_switch_hint=topic_switch_hint,
            reasoning=evaluate_answer(answer, request.message.strip(), renh),
            context=ContextStatus(
                history_messages_used=len(prepared.messages),
                total_rounds=prepared.total_rounds,
                compressed=prepared.compressed,
                summary_available=prepared.summary_available,
                rag_used=bool(references),
                rag_status=rag_status,
            ),
            provider=provider,
            fallback_reason=fallback_reason,
        )

    def stream_chat(self, request: ChatRequest) -> Iterator[dict]:
        """流式回答。星辰 Agent 通道暂不支持流式，走 Qwen3+RAG 降级路径并如实标注。"""

        session_id, topic_switch_hint, prepared = self._prepare_session(request)
        references, rag_status = self.rag.search(request.message.strip())
        yield {
            "type": "meta",
            "session_id": session_id,
            "node_ids": request.node_ids,
        }
        chunks: list[str] = []
        messages = self._fallback_messages(request, prepared.messages, references)
        for content in self.llm.stream(messages):
            chunks.append(content)
            yield {"type": "delta", "content": content}

        answer = "".join(chunks).strip()
        fidelity = check_symbol_fidelity(answer, request.message.strip())
        validity = check_natural_deduction_validity(answer, request.message.strip())
        if (fidelity.checked and not fidelity.passed) or (
            validity.checked and not validity.passed
        ):
            answer = self._generate_fallback(
                request, prepared.messages, references, repair=(fidelity, validity)
            )
            yield {"type": "replace", "content": answer}

        self.repository.add_message(session_id, "assistant", answer, request.node_ids)
        renh = build_reasoning_enhancements(request.message.strip(), SYSTEM_PROMPT)
        response = ChatResponse(
            answer=answer,
            session_id=session_id,
            references=references,
            node_ids=request.node_ids,
            topic_switch_hint=topic_switch_hint,
            reasoning=evaluate_answer(answer, request.message.strip(), renh),
            context=ContextStatus(
                history_messages_used=len(prepared.messages),
                total_rounds=prepared.total_rounds,
                compressed=prepared.compressed,
                summary_available=prepared.summary_available,
                rag_used=bool(references),
                rag_status=rag_status,
            ),
            provider="fallback",
            fallback_reason="streaming_not_supported_by_agent",
        )
        yield {"type": "done", **response.model_dump()}

    def _prepare_session(self, request: ChatRequest):
        if request.session_id is None:
            session_id = self.repository.create_session(request.user_id)
        else:
            session_id = request.session_id
            self.repository.validate_session(session_id, request.user_id)

        previous_messages = self.repository.get_messages(session_id)
        previous_node_ids = next(
            (
                message["node_ids"]
                for message in reversed(previous_messages)
                if message["role"] == "user" and message["node_ids"]
            ),
            [],
        )
        topic_switch_hint = self._topic_switch_hint(previous_node_ids, request.node_ids)

        self.repository.add_message(
            session_id, "user", request.message.strip(), request.node_ids
        )
        prepared = prepare_context(self.repository, session_id)
        return session_id, topic_switch_hint, prepared

    def _generate_fallback(
        self,
        request: ChatRequest,
        context_messages: list[dict[str, str]],
        references: list,
        repair: tuple | None = None,
    ) -> str:
        self.llm.ensure_available()
        llm_messages = self._fallback_messages(request, context_messages, references)
        if repair is not None:
            fidelity, validity = repair
            llm_messages.append(
                {
                    "role": "user",
                    "content": self._repair_prompt(
                        request.message.strip(), fidelity, validity
                    ),
                }
            )
        return self.llm.generate(llm_messages)

    def _fallback_messages(
        self,
        request: ChatRequest,
        context_messages: list[dict[str, str]],
        references: list,
    ) -> list[dict[str, str]]:
        # 降级路径保留推理增强系统提示（renh）与知识库材料注入
        renh = build_reasoning_enhancements(request.message.strip(), SYSTEM_PROMPT)
        llm_messages = [{"role": "system", "content": renh.system_prompt}]
        if references:
            knowledge = "\n\n".join(
                f"[资料{i}] {reference.content[:400]}"
                for i, reference in enumerate(references, 1)
            )
            knowledge_note = f"可参考的知识库材料：\n{knowledge}"
            llm_messages.append({"role": "system", "content": knowledge_note})
        llm_messages.extend(context_messages)
        return llm_messages

    @staticmethod
    def _repair_prompt(question: str, fidelity, validity) -> str:
        if validity.checked and not validity.passed:
            return (
                "上一版证明存在无效自然演绎。请重新完整回答，不要解释修改过程。\n"
                f"错误说明：{validity.detail}\n"
                f"原题：{question}\n"
                "禁止从 Q(a) 直接推出 ¬Q(a)。当已有 P(a)→¬Q(a) 与 Q(a) 时，"
                "应反设 P(a)，得到 ¬Q(a)，与 Q(a) 矛盾后推出 ¬P(a)；最后再用存在量词引入。"
            )
        required = "、".join(fidelity.required_symbols)
        missing = "、".join(fidelity.missing_symbols)
        return (
            "上一版证明未通过题设符号保真检查。请重新完整回答，不要解释修改过程。\n"
            f"原题必须保留的关键符号：{required}。\n"
            f"上一版缺失的符号：{missing}。\n"
            f"原题：{question}\n"
            "请在‘已知’部分原样抄写题设公式，再按自然演绎逐步证明；禁止把 ∨ 改成 →，"
            "禁止改变任何量词、否定、合取或析取结构。"
        )

    @staticmethod
    def _build_agent_input(
        learning_context: str,
        question: str,
        conversation_summary: str = "",
    ) -> str:
        sections = []
        if conversation_summary:
            sections.append(conversation_summary)
        if learning_context:
            sections.append(learning_context)
        sections.append(f"【学生问题】\n{question}")
        return "\n\n".join(sections)

    @staticmethod
    def _agent_history_without_current(
        prepared_messages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        history = [
            message
            for message in prepared_messages
            if message.get("role") in {"user", "assistant"}
        ]
        if history and history[-1].get("role") == "user":
            history = history[:-1]
        return history

    @staticmethod
    def _topic_switch_hint(previous: list[str], current: list[str]) -> str | None:
        if not previous or not current or set(previous) & set(current):
            return None
        return (
            f"检测到知识点从 {previous[0]} 切换到 {current[0]}。"
            "如新内容依赖前一知识点，可以先做一个简短回顾。"
        )
