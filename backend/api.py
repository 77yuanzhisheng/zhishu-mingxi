"""
知数·明析 — FastAPI 后端应用
============================

团队成员在各自模块中开发，在此统一注册路由。
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 应用生命周期 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的初始化与清理"""
    # 启动时：初始化学情分析 SQLite 数据库
    from backend.learning.database import init_database
    init_database()
    logger.info("学情分析数据库初始化完成")

    # 启动时：初始化知识库模块
    logger.info("正在初始化知识库模块...")
    try:
        from backend.kb.router import init_kb
        init_kb()
        # 如果知识库为空，自动重建
        from backend.kb.router import get_store
        store = get_store()
        stats = store.get_stats()
        if stats["total_chunks"] == 0:
            logger.info("知识库为空，自动重建中...")
            from backend.kb.loader import DocumentLoader
            from backend.kb.chunker import SmartChunker
            import os
            doc_dir = "data/documents"
            files = [os.path.join(doc_dir, f) for f in os.listdir(doc_dir) if f.endswith(('.pdf','.md','.txt'))]
            loader = DocumentLoader()
            chunker = SmartChunker()
            total = 0
            for fp in sorted(files):
                parsed = loader.load(fp)
                chunks = chunker.chunk(parsed)
                store.index_chunks(chunks)
                total += len(chunks)
            logger.info(f"知识库自动重建完成: {total} 个块")
        logger.info("知识库模块初始化完成")
    except Exception as e:
        logger.warning(f"知识库模块初始化失败（服务仍可启动）: {e}")

    logger.info("知数·明析 后端服务启动完成")

    yield

    # 关闭时的清理工作
    logger.info("服务正在关闭...")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="知数·明析 — 离散数学智能教学大模型",
    description="""
## 知数·明析 API

聚焦离散数学的学科垂类大模型教学系统。

### 模块划分

| 模块 | 队员 | 说明 |
|------|------|------|
| **知识库** `/kb` | 队员2 | 文档解析、分块、向量存储、语义检索 |
| **RAG 问答** `/rag` | 队员3 | 检索增强生成问答 |
| **算法工具** `/tools` | 队员5 | 真值表、关系性质判断等 |
| **LLM** | 队员1 | Qwen 本地部署，OpenAI 兼容 API |

### 队员3 接口契约

队员3 的 RAG 模块通过 `GET /kb/search` 获取检索结果:
- `content` — 拼接后注入 LLM prompt
- `metadata.chapter` / `metadata.section` / `metadata.page_start` — 引用来源
- `score` — 相关性分数，可用于过滤低质量结果
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 注册路由 ====================

# 知识库模块（队员2）
from backend.kb.router import router as kb_router
app.include_router(kb_router)

# 学情分析模块（队员3）
from backend.learning.router import router as learning_router
app.include_router(learning_router)

# 多轮 RAG 对话模块（队员3）
from backend.chat.router import router as chat_router
app.include_router(chat_router)

# TODO: 其他队员的模块
# from backend.rag.router import router as rag_router
# app.include_router(rag_router)
# from backend.tools.router import router as tools_router
# app.include_router(tools_router)


# ==================== 基础端点 ====================

@app.get("/")
async def root():
    """API 根路径"""
    return {
        "name": "知数·明析",
        "description": "离散数学智能教学大模型",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health():
    """全局健康检查"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }
