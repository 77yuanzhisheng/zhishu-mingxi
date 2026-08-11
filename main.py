#!/usr/bin/env python3
"""
知数·明析 — 离散数学智能教学大模型
==================================

启动方式:
    python main.py                    # 命令行交互模式
    python main.py --api              # 启动 FastAPI 后端服务
    python main.py --query "..."      # 单次查询模式
    python main.py --ingest <file>    # 索引文档

API 模式:
    python main.py --api
    → 后端: http://127.0.0.1:8000
    → 文档: http://127.0.0.1:8000/docs
    → KB搜索: http://127.0.0.1:8000/kb/search?q=集合运算
"""

import os
import sys
import argparse

# Windows 终端 UTF-8 兼容
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()


def run_api(host: str = None, port: int = None, reload: bool = True):
    """启动 FastAPI 后端服务"""
    try:
        import uvicorn
    except ImportError:
        print("请安装 uvicorn: pip install uvicorn")
        sys.exit(1)

    host = host or os.getenv("API_HOST", "127.0.0.1")
    port = port or int(os.getenv("API_PORT", "8000"))

    print(f"=" * 60)
    print(f"  知数·明析 — 离散数学智能教学大模型")
    print(f"=" * 60)
    print(f"  后端服务: http://{host}:{port}")
    print(f"  API 文档: http://localhost:{port}/docs")
    print(f"  知识库搜索: http://localhost:{port}/kb/search?q=命题逻辑")
    print(f"  健康检查: http://localhost:{port}/api/health")
    print(f"-" * 60)

    uvicorn.run("backend.api:app", host=host, port=port, reload=reload)


def run_ingest(file_path: str):
    """索引单个文档到知识库"""
    from backend.kb.loader import DocumentLoader
    from backend.kb.chunker import SmartChunker
    from backend.kb.embedder import EmbeddingService
    from backend.kb.vector_store import KnowledgeBaseStore

    print(f"正在处理: {file_path}")

    # Step 1: 加载文档
    loader = DocumentLoader()
    parsed = loader.load(file_path)
    print(f"  解析完成: {parsed.total_pages} 页, {len(parsed.chapters)} 个章节")
    for ch in parsed.chapters:
        if ch.level == 1:
            print(f"    - {ch.title} ({len(ch.elements)} 个元素)")

    # Step 2: 分块
    chunker = SmartChunker()
    chunks = chunker.chunk(parsed)
    print(f"  分块完成: {len(chunks)} 个块")

    # Step 3: 向量化并存储
    embedding = EmbeddingService()
    store = KnowledgeBaseStore(embedding_service=embedding)
    count = store.index_chunks(chunks)
    print(f"  索引完成: {count}/{len(chunks)} 个块写入向量库")

    # 输出统计
    print(f"\n  块类型分布:")
    type_counts = {}
    for c in chunks:
        t = c.metadata.chunk_type
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, n in sorted(type_counts.items()):
        print(f"    {t}: {n}")

    print(f"\n索引完成!")


def run_search(query: str, top_k: int = 5):
    """测试检索功能"""
    from backend.kb.embedder import EmbeddingService
    from backend.kb.vector_store import KnowledgeBaseStore
    from backend.kb.retriever import KnowledgeBaseRetriever

    embedding = EmbeddingService()
    store = KnowledgeBaseStore(embedding_service=embedding)
    retriever = KnowledgeBaseRetriever(store, embedding)

    result = retriever.retrieve(query, top_k=top_k)

    print(f"\n查询: {query}")
    print(f"耗时: {result['search_time_ms']}ms, 命中: {result['total_hits']}")
    print("-" * 60)

    for i, r in enumerate(result["results"]):
        print(f"\n[{i+1}] 分数: {r['score']}")
        meta = r.get("metadata", {})
        print(f"    来源: {meta.get('source_document', '?')}")
        print(f"    位置: {meta.get('chapter', '?')} / {meta.get('section', '?')}")
        print(f"    页码: {meta.get('page_start', '?')}")
        print(f"    类型: {meta.get('chunk_type', '?')}")
        content_preview = r["content"][:200].replace('\n', ' ')
        print(f"    内容: {content_preview}...")


# ==================== CLI 入口 ====================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="知数·明析 — 离散数学智能教学大模型",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --api                   启动 API 服务
  python main.py --api --port 8080       指定端口
  python main.py --ingest 离散数学.pdf   索引文档
  python main.py --search "命题逻辑"     测试检索
"""
    )
    parser.add_argument("--api", action="store_true", help="启动 FastAPI 后端服务")
    parser.add_argument("--port", type=int, default=8000, help="API 服务端口")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="API 服务地址")
    parser.add_argument("--no-reload", action="store_true", help="禁用热重载")
    parser.add_argument("--ingest", type=str, metavar="FILE", help="索引文档到知识库")
    parser.add_argument("--search", type=str, metavar="QUERY", help="测试知识库检索")
    parser.add_argument("--top-k", type=int, default=5, help="检索返回数量")

    args = parser.parse_args()

    if args.ingest:
        run_ingest(args.ingest)
    elif args.search:
        run_search(args.search, args.top_k)
    elif args.api:
        run_api(host=args.host, port=args.port, reload=not args.no_reload)
    else:
        # 默认启动 API 服务
        run_api()
