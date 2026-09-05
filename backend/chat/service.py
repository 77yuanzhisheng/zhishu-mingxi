"""Application service coordinating persistence, context, RAG and the LLM."""

from __future__ import annotations

from collections.abc import Callable
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
from backend.chat.repository import ChatRepository
from backend.learning.service import build_agent_learning_context


SYSTEM_PROMPT = """你是“知数·明析”的离散数学助教。回答应准确、循序渐进。
优先利用给出的知识库材料；材料不足时应明确说明，不要编造来源。
结合对话历史回答当前问题，并关注用户尚未理解的概念。"""


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
            answer = self._generate_fallback(prepared.messages, references)

        self.repository.add_message(session_id, "assistant", answer, request.node_ids)

        return ChatResponse(
            answer=answer,
            session_id=session_id,
            references=references,
            node_ids=request.node_ids,
            topic_switch_hint=topic_switch_hint,
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

    def _generate_fallback(self, context_messages, references) -> str:
        self.llm.ensure_available()
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if references:
            knowledge = "\n\n".join(
                f"[资料{i}] {reference.content}" for i, reference in enumerate(references, 1)
            )
            llm_messages.append(
                {"role": "system", "content": f"可参考的知识库材料：\n{knowledge}"}
            )
        llm_messages.extend(context_messages)
        return self.llm.generate(llm_messages)

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
