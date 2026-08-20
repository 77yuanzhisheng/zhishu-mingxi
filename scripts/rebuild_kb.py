# -*- coding: utf-8 -*-
"""
rebuild_kb.py — 全量重建知识库索引（一次性进程，不依赖后端 lifespan）
=====================================================================
用法:
    python scripts/rebuild_kb.py [--skip 老师教材]
背景:
    后端启动时的自动重建依赖 uvicorn 长驻进程，环境回收时容易中断；
    本脚本作为一次性进程遍历 data/documents 全部文档并索引，跑完即退出，
    适合在终端/后台任务中完整重建。

可选参数:
    --skip <关键字>   跳过文件名包含该关键字的文档（如 OCR 未完成的 老师教材）
"""

import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "data", "documents")
sys.path.insert(0, BASE_DIR)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip", default=None, help="跳过文件名包含该关键字的文档")
    args = parser.parse_args()

    from backend.kb.loader import DocumentLoader
    from backend.kb.chunker import SmartChunker
    from backend.kb.embedder import EmbeddingService
    from backend.kb.vector_store import KnowledgeBaseStore

    files = sorted(
        os.path.join(DOCS_DIR, f)
        for f in os.listdir(DOCS_DIR)
        if f.endswith((".pdf", ".md", ".txt"))
    )
    if args.skip:
        files = [f for f in files if args.skip not in os.path.basename(f)]

    print(f"待索引文档: {len(files)} 份")
    loader = DocumentLoader()
    chunker = SmartChunker()
    embedding = EmbeddingService()
    store = KnowledgeBaseStore(embedding_service=embedding)
    print(f"向量库就绪: {store.collection_name} (dim={embedding.dimension})")

    total = 0
    t0 = time.time()
    for fp in files:
        name = os.path.basename(fp)
        t1 = time.time()
        try:
            parsed = loader.load(fp)
            chunks = chunker.chunk(parsed)
            count = store.index_chunks(chunks)
            total += count
            print(f"  [{time.time()-t1:6.1f}s] {name}: {count} 块")
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
    print(f"\n索引完成: {total} 块，耗时 {time.time()-t0:.0f}s")

    stats = store.get_stats()
    print(f"库内总数: {stats['total_chunks']} 块 / {stats['total_documents']} 文档")
    print("chunks_by_type:", stats["chunks_by_type"])


if __name__ == "__main__":
    main()
