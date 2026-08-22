"""
知识库模块 — 队员2负责

数据流:
    原始文档 → loader.py (解析) → chunker.py (分块) → embedder.py (向量化)
    → vector_store.py (存储) → retriever.py (检索) → router.py (API)

对外接口:
    - router.py 中的 FastAPI Router, 挂在 /kb 路径下
    - 队员3通过 GET /kb/search 获取检索结果
"""

from backend.kb.loader import DocumentLoader, ParsedDocument
from backend.kb.chunker import SmartChunker, Chunk
from backend.kb.embedder import EmbeddingService


def __getattr__(name: str):
    """Load vector-storage dependencies only for callers that need them."""

    if name == "KnowledgeBaseStore":
        from backend.kb.vector_store import KnowledgeBaseStore

        return KnowledgeBaseStore
    if name == "KnowledgeBaseRetriever":
        from backend.kb.retriever import KnowledgeBaseRetriever

        return KnowledgeBaseRetriever
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
# router 延迟导入（需要 FastAPI 运行时依赖）
def get_router():
    from backend.kb.router import router
    return router

__all__ = [
    "DocumentLoader",
    "ParsedDocument",
    "SmartChunker",
    "Chunk",
    "EmbeddingService",
    "KnowledgeBaseStore",
    "KnowledgeBaseRetriever",
    "get_router",
]
