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
        # 强定义直连定位：先做概念/定理定义精确匹配，命中直接返回，不再走相似度检索
        try:
            from backend.kb.definition_search import search_definition

            defs = search_definition(query, top_k=3)
            if defs:
                references = [
                    ChatReference(
                        content=item["definition"],
                        score=float(item["score"]),
                        metadata={
                            "source": "strong_definition",
                            "node_id": item.get("node_id", ""),
                            "term": item.get("term", ""),
                            "origin": item.get("source", ""),
                        },
                    )
                    for item in defs
                ]
                logger.info("强定义命中 %d 条（跳过相似度检索）", len(references))
                return references, "strong_definition"
        except Exception as exc:
            logger.warning("强定义检索不可用，回退向量检索: %s", exc)

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
