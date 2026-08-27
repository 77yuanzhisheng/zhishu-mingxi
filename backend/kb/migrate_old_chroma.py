"""迁移旧版 chromadb dump 到新 schema。

旧 dump 的两处不兼容：
1. seq_id 存 INTEGER（新版本期望 bytes）—— 已通过 vector_store.py 顶部 monkey-patch 兼容
2. embedding 字段在 sqlite 里存为 dict，新版本期望 list[float] —— 这条把每条记录读出后
   写回新格式

用法：
    .venv/Scripts/python -m backend.kb.migrate_old_chroma <旧 chroma 路径> <新 chroma 路径>
"""
from __future__ import annotations

import os
import sys
import shutil
import logging
from typing import Iterable

import chromadb
from chromadb.config import Settings

from backend.kb.embedder import EmbeddingService
from backend.kb.vector_store import KnowledgeBaseStore  # 触发 monkey-patch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")


def migrate(old_path: str, new_path: str) -> None:
    if os.path.exists(new_path):
        raise FileExistsError(f"目标路径已存在: {new_path}，请先删除或换路径")

    if not os.path.isdir(old_path):
        raise FileNotFoundError(f"源 chroma 目录不存在: {old_path}")

    logger.info("读取旧 dump: %s", old_path)
    src_client = chromadb.PersistentClient(
        path=old_path, settings=Settings(anonymized_telemetry=False)
    )
    src_collections = src_client.list_collections()
    if not src_collections:
        raise RuntimeError(f"旧 dump 没有 collection: {old_path}")

    logger.info("写入新 dump: %s", new_path)
    dst_client = chromadb.PersistentClient(
        path=new_path, settings=Settings(anonymized_telemetry=False)
    )

    embedder = EmbeddingService()  # 旧 dump 的 embedding 可能是 dict，需要重算

    for src_coll in src_collections:
        name = src_coll.name
        meta = src_coll.metadata or {}
        logger.info("迁移 collection: %s (chunks=%d)", name, src_coll.count())

        dst_coll = dst_client.get_or_create_collection(
            name=name, metadata=meta, embedding_function=None
        )

        # 分批拉取旧数据（避免一次拉太多 OOM）
        batch = 500
        offset = 0
        while True:
            get_kwargs = {
                "limit": batch,
                "offset": offset,
                "include": ["metadatas", "documents"],
            }
            try:
                data = src_coll.get(**get_kwargs)
            except Exception as exc:
                logger.error("  拉取失败 offset=%d: %s", offset, exc)
                break

            ids = data.get("ids") or []
            if not ids:
                break

            docs = data.get("documents") or ["" for _ in ids]
            metas = data.get("metadatas") or [{} for _ in ids]

            # 重算 embedding（旧 dump 里可能是 dict 格式）
            try:
                embeds = embedder.embed_documents(docs)
            except Exception as exc:
                logger.error("  embedding 失败，跳过本批: %s", exc)
                offset += batch
                continue

            dst_coll.upsert(
                ids=list(ids),
                documents=list(docs),
                metadatas=list(metas),
                embeddings=embeds,
            )
            logger.info("  写入 %d 条 (offset=%d)", len(ids), offset)
            offset += batch

    logger.info("迁移完成 ✓ 新路径: %s", new_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python -m backend.kb.migrate_old_chroma <old_path> <new_path>")
        sys.exit(1)
    migrate(sys.argv[1], sys.argv[2])
