"""
嵌入服务
=======

提供统一的文本向量化接口。

后端选择:
    1. sentence-transformers (默认): 本地加载 bge-large-zh-v1.5，无需 API
    2. chroma_default: ChromaDB 内置模型 (all-MiniLM-L6-v2, 384d)
    3. openai: 通过 OpenAI 兼容 API（如队员1的 Qwen 部署）

特性:
    - LRU 缓存避免重复向量化
    - 批量嵌入去重优化
    - 启动时自动下载模型（首次需联网，约 1.3GB）
"""

import os
import logging
import threading
from collections import OrderedDict
from typing import List, Optional

from dotenv import load_dotenv

# 始终从项目根加载 .env，避免启动目录不同导致嵌入模型配置丢失（384d 回退污染索引）
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    统一嵌入服务。

    用法:
        service = EmbeddingService()
        vec = service.embed_query("什么是集合的笛卡尔积？")
        vecs = service.embed_documents(["文本1", "文本2", "文本3"])

    配置（通过环境变量）:
        EMBEDDING_BACKEND: sentence_transformers (默认) | chroma_default | openai
        EMBEDDING_MODEL: BAAI/bge-large-zh-v1.5 (默认)
        EMBEDDING_DEVICE: cpu (默认) | cuda
    """

    def __init__(
        self,
        backend: Optional[str] = None,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        # 从环境变量读取配置
        self.backend_name = backend or os.getenv("EMBEDDING_BACKEND", "sentence_transformers")
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
        self.device = device or os.getenv("EMBEDDING_DEVICE", "cpu")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

        # LRU 缓存
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_max = 500

        # 初始化模型
        self._model = None
        self.dimension = 0
        self._init_backend()

    def _init_backend(self):
        """初始化嵌入后端"""
        if self.backend_name == "sentence_transformers":
            self._init_sentence_transformers()
        elif self.backend_name == "openai":
            self._init_openai()
        elif self.backend_name == "chroma_default":
            self._init_chroma_default()
        else:
            logger.warning(f"未知嵌入后端 '{self.backend_name}'，回退到 sentence_transformers")
            self.backend_name = "sentence_transformers"
            self._init_sentence_transformers()

    def _init_sentence_transformers(self):
        """加载 sentence-transformers 模型"""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载嵌入模型: {self.model_name} (device={self.device})")
            # 相对路径（./local_models/...）基于项目根解析，避免依赖启动时的 cwd
            model_path = self.model_name
            if model_path.startswith("./") or model_path.startswith(".\\") or model_path.startswith("."):
                project_root = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )  # backend/kb/embedder.py → 项目根
                model_path = os.path.join(project_root, model_path.lstrip("./\\"))
            self._model = SentenceTransformer(model_path, device=self.device)
            self.dimension = self._model.get_sentence_embedding_dimension()
            logger.info(f"嵌入模型加载完成，向量维度: {self.dimension} ({model_path})")
        except ImportError:
            logger.error("sentence-transformers 未安装，请执行: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.warning(f"sentence-transformers 加载失败 ({e})，回退到 ChromaDB 默认模型")
            self._init_chroma_default()

    def _init_openai(self):
        """初始化 OpenAI 兼容嵌入"""
        if not self.api_key:
            logger.warning("OPENAI_API_KEY 未设置，回退到 sentence_transformers")
            self._init_sentence_transformers()
            return
        self.dimension = 1536  # OpenAI 默认维度
        logger.info(f"使用 OpenAI 兼容嵌入: {self.base_url or '默认'}")

    def _init_chroma_default(self):
        """初始化 ChromaDB 默认嵌入"""
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            self._model = DefaultEmbeddingFunction()
            self.dimension = 384
            self.backend_name = "chroma_default"
            logger.info("使用 ChromaDB 默认嵌入 (all-MiniLM-L6-v2, 384d)")
        except ImportError:
            raise ImportError("chromadb 未安装，请执行: pip install chromadb")

    # ---------- 缓存 ----------

    def _get_cached(self, text: str) -> Optional[List[float]]:
        with self._cache_lock:
            val = self._cache.get(text)
            if val is not None:
                self._cache.move_to_end(text)
            return val

    def _set_cached(self, text: str, embedding: List[float]):
        with self._cache_lock:
            if len(self._cache) >= self._cache_max:
                self._cache.popitem(last=False)
            self._cache[text] = embedding

    # ---------- 公开接口 ----------

    def embed_query(self, text: str) -> List[float]:
        """将单个查询文本向量化"""
        if not text.strip():
            return [0.0] * max(self.dimension, 384)

        cached = self._get_cached(text)
        if cached is not None:
            return cached

        try:
            if self.backend_name == "sentence_transformers":
                result = self._model.encode(text, normalize_embeddings=True).tolist()
            elif self.backend_name == "openai":
                result = self._embed_openai(text)
            elif self.backend_name == "chroma_default":
                result = self._model([text])[0].tolist()
            else:
                raise RuntimeError(f"未知后端: {self.backend_name}")
        except Exception as e:
            logger.error(f"嵌入查询失败: {e}")
            raise RuntimeError(f"嵌入查询失败 (后端={self.backend_name}): {e}") from e

        self._set_cached(text, result)
        return result

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量向量化文本（带去重优化）"""
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        # 分离已缓存和未缓存
        for i, text in enumerate(texts):
            cached = self._get_cached(text)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            # 去重
            unique_texts = list(dict.fromkeys(uncached_texts))
            try:
                if self.backend_name == "sentence_transformers":
                    unique_results = self._model.encode(
                        unique_texts, normalize_embeddings=True
                    ).tolist()
                elif self.backend_name == "openai":
                    unique_results = [self._embed_openai(t) for t in unique_texts]
                elif self.backend_name == "chroma_default":
                    unique_results = [r.tolist() for r in self._model(unique_texts)]
                else:
                    raise RuntimeError(f"未知后端: {self.backend_name}")
            except Exception as e:
                logger.error(f"批量嵌入失败: {e}")
                raise RuntimeError(f"批量嵌入失败 (后端={self.backend_name}): {e}") from e

            # 写入缓存
            text_to_result = dict(zip(unique_texts, unique_results))
            for text, embedding in text_to_result.items():
                self._set_cached(text, embedding)

            # 按原始顺序组装结果
            for orig_idx, text in zip(uncached_indices, uncached_texts):
                results[orig_idx] = text_to_result[text]

        return results  # type: ignore

    def _embed_openai(self, text: str) -> List[float]:
        """通过 OpenAI 兼容 API 嵌入"""
        import httpx
        url = f"{self.base_url}/embeddings" if self.base_url else "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = httpx.post(
            url, json={"input": text, "model": self.model_name},
            headers=headers, timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]


# ==================== ChromaDB 嵌入适配器 ====================

class ChromaEmbeddingAdapter:
    """
    将 EmbeddingService 适配为 ChromaDB 兼容的 embedding_function。

    用法:
        service = EmbeddingService()
        adapter = ChromaEmbeddingAdapter(service)
        collection = client.create_collection(..., embedding_function=adapter)
    """

    def __init__(self, embedding_service: EmbeddingService):
        self._svc = embedding_service

    def __call__(self, input: List[str]) -> List[List[float]]:
        """ChromaDB 批量嵌入接口"""
        return self._svc.embed_documents(input)

    def embed_query(self, input=None, text=None):
        """ChromaDB 查询嵌入接口（兼容 input= 和 text= 两种调用方式）"""
        query_text = input if input is not None else text
        if isinstance(query_text, list):
            results = self._svc.embed_documents(query_text)
            return results[0] if results else []
        return self._svc.embed_query(query_text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """ChromaDB 批量嵌入接口"""
        return self._svc.embed_documents(texts)

    def name(self) -> str:
        return "chroma_embedding_adapter"

    @staticmethod
    def is_legacy() -> bool:
        return False
