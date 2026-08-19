"""Application service coordinating persistence, context, RAG and the LLM."""

from __future__ import annotations

from backend.chat.context import prepare_context
from backend.chat.llm import LLMClient, OpenAICompatibleLLM
from backend.chat.models import ChatRequest, ChatResponse, ContextStatus
from backend.chat.rag import RAGAdapter
from backend.chat.repository import ChatRepository


SYSTEM_PROMPT = """你是"知数·明析"的离散数学助教。回答应准确、循序渐进。
优先利用给出的知识库材料；材料不足时应明确说明，不要编造来源。
结合对话历史回答当前问题，并关注用户尚未理解的概念。

【回答长度要求】
- 概念题控制在300字以内，直接给出定义和要点
- 证明题只写关键推导步骤，总长控制在500字以内，最后以”证毕”结尾
- 公式使用LaTeX行内格式，不用多行公式块"""


class ChatService:
    def __init__(
        self,
        repository: ChatRepository | None = None,
        llm: LLMClient | None = None,
        rag: RAGAdapter | None = None,
    ):
        self.repository = repository or ChatRepository()
        self.llm = llm or OpenAICompatibleLLM()
        self.rag = rag or RAGAdapter()

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.llm.ensure_available()
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
        references, rag_status = self.rag.search(request.message.strip())
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if references:
            knowledge = "\n\n".join(
                f"[资料{i}] {reference.content[:400]}"
                for i, reference in enumerate(references, 1)
            )
            llm_messages.append(
                {"role": "system", "content": f"可参考的知识库材料：\n{knowledge}"}
            )
        llm_messages.extend(prepared.messages)
        answer = self.llm.generate(llm_messages)
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
        )

    @staticmethod
    def _topic_switch_hint(previous: list[str], current: list[str]) -> str | None:
        if not previous or not current or set(previous) & set(current):
            return None
        return (
            f"检测到知识点从 {previous[0]} 切换到 {current[0]}。"
            "如新内容依赖前一知识点，可以先做一个简短回顾。"
        )
