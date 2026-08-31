"""开发模式启动：跳过 KB 自动重建（chroma dump 失效时避免 1 小时预热）。

运行：.venv/Scripts/python run_dev.py
等价于：KB_SKIP_REBUILD=1 uvicorn backend.api:app
"""
import os
import sys
import threading

# 在 uvicorn 启动 lifespan 前 monkey-patch get_stats
def _patch_kb_stats():
    try:
        from backend.kb import router as kb_router
        from backend.kb.vector_store import KnowledgeBaseStore

        original_index_chunks = KnowledgeBaseStore.index_chunks
        def fast_index_chunks(self, chunks):
            # 重建时直接返回 chunks 数（chroma 写入慢，先快速启动 UI）
            return len(chunks)
        KnowledgeBaseStore.index_chunks = fast_index_chunks

        def fast_get_stats(self):
            return {"total_chunks": 999, "total_documents": 99, "chunks_by_type": {},
                    "chapters": [], "vector_dimension": 512,
                    "collection_name": "discrete_math_kb", "embedding_model": "bge-small-zh-v1.5"}
        KnowledgeBaseStore.get_stats = fast_get_stats
    except Exception as e:
        print(f"[run_dev] monkey-patch 失败（不致命）: {e}")


if __name__ == "__main__":
    _patch_kb_stats()
    import uvicorn
    uvicorn.run("backend.api:app", host="127.0.0.1", port=8000, log_level="info")
