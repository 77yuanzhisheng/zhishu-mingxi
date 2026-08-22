"""
强定义检索（队员2）
==================

知识库问答的「强定义直连定位」：
停用相似度匹配兜底前，先用概念/定理/定义的精确术语匹配直连定位内容。

数据源:
    1. 知识图谱节点定义（backend.kb.router.KG_DATA 的 items：node_id/text/type）
    2. 概念题库.md（**Qn：xxx** / A：xxx 问答）

匹配策略（不做向量计算）:
    - 术语命中：定义条目里的概念名出现在查询中（如查询含「命题」命中「命题：具有确定真值的陈述句」）
    - 疑问模式加权：查询含「什么是/定义/含义/是什么/区别」等词时，命中条目排在前面
    - 精确优先：完全一致的概念名优先于包含关系

集成:
    backend/chat/rag.py 的 RAGAdapter.search 先调 search_definition，
    命中 → 直接返回定义（score=1.0，metadata.source="strong_definition"）；
    未命中 → 回退向量检索（保证其他类型问题仍可回答）。
"""

import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONCEPT_BANK_FILE = os.path.join(BASE_DIR, "data", "documents", "概念题库.md")

# 疑问模式词（命中这些词的查询优先走强定义）
QUESTION_MARKERS = ["什么是", "是什么", "定义", "含义", "意思", "区别", "区分", "解释", "叫做", "称为"]

# 手工别名：概念词 → 图谱/题库里的标准名（覆盖口语/缩略写法）
ALIASES = {
    "德摩根": "德摩根律",
    "析取范式": "DNF",
    "合取范式": "CNF",
    "握手定理": "握手定理",
    "欧拉回路": "欧拉图",
    "哈密顿": "哈密顿图",
    "哈斯图": "哈斯图",
    "幂集": "幂集",
    "重言式": "重言式",
    "永真式": "重言式",
    "矛盾式": "矛盾式",
    "等价关系": "等价关系",
    "偏序": "偏序关系",
    "同余": "同余",
    "最大公因数": "gcd",
    "生成函数": "生成函数",
    "容斥": "容斥原理",
}

_index: List[Dict] = []
_loaded = False


def _term_of(text: str) -> str:
    """从定义文本提取概念名：优先冒号前部分，否则取前 8 字以内的名词短语。"""
    for sep in ("：", ":", "是", "指"):
        if sep in text:
            term = text.split(sep)[0].strip()
            if 1 <= len(term) <= 16 and not term.startswith(("设", "若", "已知")):
                return term
    return text[:8].strip()


def _load() -> List[Dict]:
    global _loaded, _index
    if _loaded:
        return _index
    entries: List[Dict] = []

    # 1) 知识图谱节点定义
    try:
        from backend.kb.router import KG_DATA
        for module in KG_DATA.get("modules", []):
            for child in module.get("children", []):
                child_name = child.get("name", "")
                for item in child.get("items", []):
                    text = item.get("text", "").strip()
                    if not text:
                        continue
                    term = _term_of(text)
                    entries.append({
                        "term": term,
                        "aliases": [term, child_name],
                        "definition": text,
                        "node_id": item.get("node_id", ""),
                        "type": item.get("type", "definition"),
                        "module": module.get("name", ""),
                        "source": "knowledge_graph",
                    })
    except Exception as exc:
        logger.warning("知识图谱定义加载失败: %s", exc)

    # 2) 概念题库.md 问答
    if os.path.exists(CONCEPT_BANK_FILE):
        try:
            with open(CONCEPT_BANK_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            for m in re.finditer(r"\*\*Q\d+[：:]\s*(.+?)\*\*\s*\nA[：:]\s*(.+?)(?=\n\n|\n\*\*|\Z)", content, re.S):
                q_text = m.group(1).strip().strip("*").strip()
                a_text = m.group(2).strip()
                term = re.sub(r"[？?。]$", "", q_text)
                term = re.sub(r"^(什么是|什么叫|何谓|简述|请说明)", "", term).strip()
                term = re.sub(r"(是什么|是什么含义)$", "", term).strip()
                if not term:
                    continue
                entries.append({
                    "term": term,
                    "aliases": [term],
                    "definition": f"{q_text}\nA：{a_text}",
                    "node_id": "",
                    "type": "concept",
                    "module": "",
                    "source": "concept_bank",
                })
        except Exception as exc:
            logger.warning("概念题库加载失败: %s", exc)

    # 3) 别名映射
    for alias, target in ALIASES.items():
        for e in entries:
            if e["term"] == target and alias not in e["aliases"]:
                e["aliases"].append(alias)

    _index = entries
    _loaded = True
    logger.info(f"强定义索引就绪: {len(entries)} 条定义")
    return _index


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。！？；：、（）()\"''《》]", "", text).lower()


def search_definition(query: str, top_k: int = 3) -> List[Dict]:
    """强定义直连定位：返回命中的定义条目（按匹配强度排序）。

    返回格式: [{term, definition, node_id, type, module, source, score}]
    """
    entries = _load()
    q = query or ""
    qn = _normalize(q)
    if len(qn) < 2:
        return []

    hits = []
    for e in entries:
        best_score = 0.0
        for alias in e["aliases"]:
            an = _normalize(alias)
            if not an:
                continue
            if an == qn:
                best_score = max(best_score, 1.0)          # 完全一致
            elif an in qn or qn in an:
                best_score = max(best_score, 0.7)          # 包含关系
            # 查询拆词：长查询中的 2 字词命中（如“什么是命题？”→“命题”）
            elif len(an) >= 2 and an in qn:
                best_score = max(best_score, 0.6)
        if best_score <= 0:
            continue
        # 疑问模式加权
        if any(marker in q for marker in QUESTION_MARKERS):
            best_score = min(best_score + 0.15, 1.0)
        hits.append({**e, "score": round(best_score, 2)})

    hits.sort(key=lambda h: (-h["score"], len(h["term"])))
    seen = set()
    result = []
    for h in hits:
        key = h["definition"][:40]
        if key in seen:
            continue
        seen.add(key)
        result.append(h)
        if len(result) >= top_k:
            break
    return result


# 供 /kb/definitions 端点调试
def get_index_stats() -> Dict:
    entries = _load()
    return {"total": len(entries), "sources": {"graph": sum(1 for e in entries if e["source"] == "knowledge_graph"),
                                               "concept": sum(1 for e in entries if e["source"] == "concept_bank")}}
