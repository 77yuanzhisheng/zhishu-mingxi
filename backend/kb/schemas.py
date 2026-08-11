"""
知识库模块 — Pydantic 数据模型

定义知识库相关 API 的请求和响应格式。
队员3 依赖这些格式来调用检索接口。
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict


# ==================== 请求模型 ====================

class KBSearchRequest(BaseModel):
    """检索请求"""
    query: str = Field(..., min_length=1, max_length=1000, description="搜索查询（自然语言）")
    top_k: int = Field(default=5, ge=1, le=50, description="返回结果数量")
    min_score: float = Field(default=0.5, ge=0.0, le=1.0, description="最小相关性阈值")
    chapter: Optional[str] = Field(default=None, description="按章节筛选")
    chunk_type: Optional[str] = Field(
        default=None,
        description="按类型筛选: theorem_block / definition / example / general"
    )


class KBIngestResponse(BaseModel):
    """文档摄入响应"""
    filename: str
    status: str          # "success" | "partial" | "error"
    chunks_created: int
    total_pages: int
    chapters_found: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# ==================== 响应模型 ====================

class ChunkMetadata(BaseModel):
    """块元数据"""
    source_document: str
    chapter: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_type: str = "general"         # theorem_block / definition / example / general
    is_complete_proof: bool = False
    has_formulas: bool = False
    token_count: Optional[int] = None


class SearchResultItem(BaseModel):
    """单条搜索结果"""
    chunk_id: str
    content: str                        # 块文本内容（含行内 LaTeX 标记）
    metadata: ChunkMetadata
    score: float                        # 语义相似度 (0-1)


class KBSearchResponse(BaseModel):
    """检索响应"""
    query: str
    results: List[SearchResultItem]
    total_hits: int
    search_time_ms: Optional[float] = None


class KBDocumentInfo(BaseModel):
    """已索引文档信息"""
    filename: str
    chunks_count: int
    chapters: List[str] = Field(default_factory=list)
    indexed_at: Optional[str] = None


class KBDocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[KBDocumentInfo]
    total: int


class KBStatsResponse(BaseModel):
    """知识库统计响应"""
    total_documents: int
    total_chunks: int
    chunks_by_type: Dict[str, int] = Field(default_factory=dict)
    chapters: List[str] = Field(default_factory=list)
    vector_dimension: Optional[int] = None
    collection_name: str
    embedding_model: str


class KBHealthResponse(BaseModel):
    """知识库健康检查响应"""
    status: str  # "ok" | "degraded" | "error"
    chroma_connected: bool
    embedding_model: str
    total_chunks_indexed: int
