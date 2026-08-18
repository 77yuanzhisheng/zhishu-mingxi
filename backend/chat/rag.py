"""Thin adapter over team member 2's existing knowledge-base retriever."""

from __future__ import annotations

import logging
from typing import Any, Callable

from backend.chat.models import ChatReference


logger = logging.getLogger(__name__)


class RAGAdapter:
    def __init__(self, retriever_provider: Callable[[], Any] | None = None):
        self.retriever_provider = retriever_provider

    def search(self, query: str) -> tuple[list[ChatReference], str]:
        try:
            if self.retriever_provider is None:
                from backend.kb.router import get_retriever

                retriever = get_retriever()
            else:
                retriever = self.retriever_provider()
            result = retriever.retrieve(query=query, top_k=5, min_score=0.5)
        except Exception as exc:
            logger.warning("知识库检索不可用，本轮不注入 RAG: %s", exc)
            return [], "unavailable"

        references = [
            ChatReference(
                content=item["content"],
                score=float(item["score"]),
                metadata=item.get("metadata", {}),
            )
            for item in result.get("results", [])
        ]
        return references, "used" if references else "no_results"
