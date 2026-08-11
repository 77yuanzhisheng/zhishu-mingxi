"""
向量存储
=======

封装 ChromaDB 持久化客户端，提供知识的向量存储与语义搜索。

策略：不使用 ChromaDB 内置 embedding_function（兼容性问题太多），
改为预计算向量后直接传入。chroma_default 后端仍使用原生嵌入。

主要操作:
    - index_chunks: 批量嵌入 → 写入向量库
    - search: 嵌入查询 → 语义搜索（cosine 相似度）
    - delete_document: 按源文档删除所有块
    - get_stats: 获取集合统计信息
"""

import os
import logging
from typing import List, Dict, Optional

import chromadb
from chromadb.config import Settings

from backend.kb.chunker import Chunk, ChunkMetadata
from backend.kb.embedder import EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeBaseStore:
    """知识库向量存储。"""

    COLLECTION_NAME = "discrete_math_kb"

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
        collection_name: Optional[str] = None,
    ):
        self.persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
        os.makedirs(self.persist_dir, exist_ok=True)
        self.embedding = embedding_service or EmbeddingService()
        self.collection_name = collection_name or self.COLLECTION_NAME

        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        # chroma_default: 使用原生嵌入函数（已测试通过）
        # 其他后端：不传 embedding_function，手动预计算向量
        if self.embedding.backend_name == "chroma_default":
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            self._ef = DefaultEmbeddingFunction()
            self._manual_embed = False
        else:
            self._ef = None
            self._manual_embed = True

        kwargs = {"name": self.collection_name, "metadata": {"hnsw:space": "cosine"}}
        if self._ef is not None:
            kwargs["embedding_function"] = self._ef

        self.collection = self.client.get_or_create_collection(**kwargs)
        logger.info(f"ChromaDB '{self.collection_name}' 就绪 "
                     f"(backend={self.embedding.backend_name}, "
                     f"dim={self.embedding.dimension}, "
                     f"manual_embed={self._manual_embed})")

    # ==================== 写入 ====================

    def index_chunks(self, chunks: List[Chunk]) -> int:
        """批量嵌入并写入。返回成功数量。"""
        if not chunks:
            return 0

        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [self._meta_dict(c.metadata) for c in chunks]

        # 手动预计算向量
        kwargs = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if self._manual_embed:
            embeddings = self.embedding.embed_documents(documents)
            kwargs["embeddings"] = embeddings

        try:
            self.collection.upsert(**kwargs)
            return len(chunks)
        except Exception as e:
            logger.error(f"批量索引失败: {e}")
            # 逐条重试
            success = 0
            for chunk in chunks:
                try:
                    single_kwargs = {
                        "ids": [chunk.chunk_id],
                        "documents": [chunk.content],
                        "metadatas": [self._meta_dict(chunk.metadata)],
                    }
                    if self._manual_embed:
                        single_kwargs["embeddings"] = self.embedding.embed_documents([chunk.content])
                    self.collection.upsert(**single_kwargs)
                    success += 1
                except Exception as inner_e:
                    logger.error(f"索引 {chunk.chunk_id} 失败: {inner_e}")
            return success

    def _meta_dict(self, m: ChunkMetadata) -> Dict:
        return {
            "source_document": m.source_document or "",
            "chapter": m.chapter or "",
            "section": m.section or "",
            "subsection": m.subsection or "",
            "page_start": m.page_start or 0,
            "page_end": m.page_end or 0,
            "chunk_type": m.chunk_type or "general",
            "has_formulas": m.has_formulas,
            "is_complete_proof": m.is_complete_proof,
        }

    # ==================== 搜索 ====================

    def search(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float = 0.5,
        chapter_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None,
    ) -> List[Dict]:
        """语义搜索。"""
        where_filter = {}
        if chapter_filter:
            where_filter["chapter"] = chapter_filter
        if chunk_type_filter:
            where_filter["chunk_type"] = chunk_type_filter

        try:
            query_kwargs: Dict = {
                "n_results": top_k * 2,
                "where": where_filter if where_filter else None,
                "include": ["documents", "metadatas", "distances"],
            }
            if self._manual_embed:
                query_vec = self.embedding.embed_query(query_text)
                query_kwargs["query_embeddings"] = [query_vec]
            else:
                query_kwargs["query_texts"] = [query_text]

            results = self.collection.query(**query_kwargs)
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        output = []
        ids = results["ids"][0]
        docs = results["documents"][0] if results.get("documents") else [""] * len(ids)
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
        distances = results["distances"][0]

        for i in range(len(ids)):
            score = 1.0 - distances[i]
            if score < min_score:
                continue
            meta = metas[i] or {}
            output.append({
                "chunk_id": ids[i],
                "content": docs[i] or "",
                "metadata": {
                    "source_document": meta.get("source_document", ""),
                    "chapter": meta.get("chapter"),
                    "section": meta.get("section"),
                    "subsection": meta.get("subsection"),
                    "page_start": meta.get("page_start"),
                    "page_end": meta.get("page_end"),
                    "chunk_type": meta.get("chunk_type", "general"),
                    "is_complete_proof": meta.get("is_complete_proof", False),
                    "has_formulas": meta.get("has_formulas", False),
                    "token_count": meta.get("token_count"),
                },
                "score": round(score, 4),
            })

        output.sort(key=lambda x: x["score"], reverse=True)
        return output[:top_k]

    # ==================== 管理 ====================

    def delete_document(self, source_filename: str) -> int:
        try:
            result = self.collection.get(where={"source_document": source_filename}, include=[])
            if result and result.get("ids"):
                self.collection.delete(ids=result["ids"])
                return len(result["ids"])
            return 0
        except Exception as e:
            logger.error(f"删除失败: {e}")
            return 0

    def get_documents(self) -> List[Dict]:
        try:
            all_data = self.collection.get(include=["metadatas"])
            if not all_data or not all_data.get("metadatas"):
                return []
            doc_map: Dict[str, Dict] = {}
            for meta in all_data["metadatas"]:
                src = meta.get("source_document", "unknown")
                ch = meta.get("chapter", "")
                if src not in doc_map:
                    doc_map[src] = {"filename": src, "chunks_count": 0, "chapters": []}
                doc_map[src]["chunks_count"] += 1
                if ch and ch not in doc_map[src]["chapters"]:
                    doc_map[src]["chapters"].append(ch)
            return list(doc_map.values())
        except Exception as e:
            logger.error(f"获取文档列表失败: {e}")
            return []

    def get_stats(self) -> Dict:
        try:
            all_data = self.collection.get(include=["metadatas"])
            chunks_count = len(all_data["ids"]) if all_data.get("ids") else 0
            chunks_by_type: Dict[str, int] = {}
            chapters = set()
            sources = set()
            if all_data.get("metadatas"):
                for meta in all_data["metadatas"]:
                    ct = meta.get("chunk_type", "general")
                    chunks_by_type[ct] = chunks_by_type.get(ct, 0) + 1
                    if meta.get("chapter"):
                        chapters.add(meta["chapter"])
                    if meta.get("source_document"):
                        sources.add(meta["source_document"])
            return {
                "total_documents": len(sources),
                "total_chunks": chunks_count,
                "chunks_by_type": chunks_by_type,
                "chapters": sorted(list(chapters)),
                "vector_dimension": self.embedding.dimension,
                "collection_name": self.collection_name,
                "embedding_model": self.embedding.model_name,
            }
        except Exception as e:
            logger.error(f"统计失败: {e}")
            return {
                "total_documents": 0, "total_chunks": 0,
                "chunks_by_type": {}, "chapters": [],
                "vector_dimension": self.embedding.dimension,
                "collection_name": self.collection_name,
                "embedding_model": self.embedding.model_name,
            }
