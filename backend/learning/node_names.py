"""平台知识图谱节点 id → 专业术语名称映射（学习路径 / 学情展示用）。

名称来源与 /kb/knowledge-graph 端点保持一致:
- 模块 id（如 propositional_logic）→ 模块名
- 概念（两段式 id，如 pl_01）→ 概念名
- 条目（三段式 id，如 pl_01_01）→ 条目 text 的术语部分（端点用冒号前缀，
  这里对无冒号的"术语=公式 / 术语，补充说明"句式做了同样的截取）
"""

from __future__ import annotations

import re

_cache: dict[str, str] | None = None

_TRAIL_QUOTES = "'\"“”"


def _item_name(text: str) -> str:
    t = (text or "").strip()
    for sep in ("：", ":"):
        if sep in t:
            return t.split(sep, 1)[0].strip()
    # 无冒号条目：例句型（'北京是首都'是真命题；…）取引号内片段
    quoted = re.match(r"^['“]([^'”]+)['”]", t)
    if quoted:
        return quoted.group(1).strip()
    # 证明型条目（证明1+2+...+n=n(n+1)/2）去掉"证明"后保留完整命题，不截公式
    proof = t.startswith("证明")
    if proof:
        t = t[2:].strip()
    if not proof:
        for sep in ("，", "；", ",", ";"):
            if sep in t:
                t = t.split(sep, 1)[0].strip()
        for sep in ("=", "＝"):
            if sep in t:
                t = t.split(sep, 1)[0].strip()
    return t.strip(_TRAIL_QUOTES).strip()[:22]


def node_name_map() -> dict[str, str]:
    """惰性构建并缓存 id → 名称映射。KB 模块只在首次调用时导入，
    避免单元测试等场景拖入 chromadb / 嵌入模型等重依赖。"""
    global _cache
    if _cache is not None:
        return _cache
    from backend.kb.router import KG_DATA

    names: dict[str, str] = {}
    for module in KG_DATA["modules"]:
        names[module["id"]] = module["name"]
        for concept in module.get("children", []):
            names[concept["node_id"]] = concept["name"]
            for item in concept.get("items", []):
                names[item["node_id"]] = _item_name(item.get("text", ""))
    _cache = names
    return names
