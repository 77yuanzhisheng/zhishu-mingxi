"""
检索服务
=======

提供知识库语义检索接口。

这是队员3（RAG 模块）直接调用的核心接口。
检索流程: 用户查询 → 向量化 → ChromaDB 搜索 → 排序 → 返回结果
"""

import time
import logging
from typing import List, Optional, Dict

from backend.kb.vector_store import KnowledgeBaseStore
from backend.kb.embedder import EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeBaseRetriever:
    """
    知识库检索器。

    用法:
        service = EmbeddingService()
        store = KnowledgeBaseStore(embedding_service=service)
        retriever = KnowledgeBaseRetriever(store, service)
        results = retriever.retrieve("什么是命题逻辑？", top_k=5)
    """

    def __init__(self, store: KnowledgeBaseStore, embedding_service: EmbeddingService):
        self.store = store
        self.embedding = embedding_service

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.5,
        chapter: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> Dict:
        """
        检索知识库。

        参数:
            query: 查询文本（自然语言）
            top_k: 返回结果数
            min_score: 最小相似度阈值 (0-1)
            chapter: 可选，按章节过滤
            chunk_type: 可选，按块类型过滤

        返回:
            {
                "query": str,
                "results": [SearchResultItem, ...],
                "total_hits": int,
                "search_time_ms": float
            }
        """
        start_time = time.time()

        results = self.store.search(
            query_text=query,
            top_k=top_k,
            min_score=min_score,
            chapter_filter=chapter,
            chunk_type_filter=chunk_type,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "query": query,
            "results": results,
            "total_hits": len(results),
            "search_time_ms": round(elapsed_ms, 2),
        }
