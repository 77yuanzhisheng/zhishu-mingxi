# -*- coding: utf-8 -*-
"""队员2 · 任务⑥-2：学习路径按图谱依赖重排

图谱 edges 语义（GET /kb/knowledge-graph 的 depends_on 计算）：from → to 表示
from 是 to 的前置知识，即学习路径中 rank(from) < rank(to)。

当前 learning_path（①命题 ②集合 ③谓词 ④归纳 ⑤关系 ⑥图论 ⑦数论 ⑧组合 ⑨代数）
违反的边：predicate_logic→set_theory（谓词在集合之后）、induction→set_theory（归纳在集合之后）；
且存在模块级环 set_theory→relations「关系⊆A×B」与 relations→set_theory「函数=特殊关系」——
后者是模块打包造成的伪环（教材实际顺序 C01 集合 → C02 关系 → C03 函数，函数属于集合论模块）。

处理：SCC 检测找环，环内按模块主章节的教材顺序保留一条链（st=C01 在 rel=C02 前，
保留 st→rel，丢弃 rel→st，该边仅作可视化展示，不参与路径排序）；再对 DAG 做
Kahn 拓扑排序（平手时按当前模块数组顺序），结果即依赖一致的学习路径。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.kb.router import KG_DATA  # noqa: E402

# 模块 → 主教材章节（用于环内邻接裁决：先学章节的模块排前）
MODULE_CHAPTER = {
    "propositional_logic": "C15",  # 命题逻辑（启发式：逻辑先行，见平台原设计）
    "predicate_logic": "C16",
    "set_theory": "C01",          # 集合与函数
    "induction": "C17",           # 数学归纳法
    "relations": "C02",
    "graph_theory": "C05",        # 图论与树
    "number_theory": "C04",
    "combinatorics": "C10",
    "algebraic_structure": "C12",
}
# 路径展示文案（保留原有人工副标题）
LP_TITLE = {
    "propositional_logic": "① 命题逻辑（基础语言）→",
    "predicate_logic": "② 谓词逻辑（扩展推理）→",
    "induction": "③ 数学归纳法（证明工具）→",
    "set_theory": "④ 集合论（数学对象）→",
    "relations": "⑤ 关系（元素间结构）→",
    "graph_theory": "⑥ 图论（可视化网络）→",
    "number_theory": "⑦ 初等数论（整数结构）→",
    "combinatorics": "⑧ 组合数学（计数方法）→",
    "algebraic_structure": "⑨ 代数结构（运算体系）",
}
# 与图谱数组顺序一致（模块数组 = 主目录顺序）
MODULE_TIEBREAK = [m["id"] for m in KG_DATA["modules"]]
MODULE_INDEX = {mid: i for i, mid in enumerate(MODULE_TIEBREAK)}


def edges() -> list[tuple[str, str, str]]:
    out = []
    for e in KG_DATA["edges"]:
        s = e.get("source") or e.get("from")
        t = e.get("target") or e.get("to")
        if s and t:
            out.append((s, t, e.get("label", "")))
    return out


def scc_index(es: list[tuple[str, str, str]], nodes: list[str]) -> dict[str, int]:
    """Tarjan SCC → 每个节点所在 SCC 的索引（同环 = 同索引）。"""
    import sys as _sys
    _sys.setrecursionlimit(10000)
    adj = {n: [] for n in nodes}
    for s, t, _l in es:
        adj[s].append(t)
    index = {}
    low = {}
    on_stack = set()
    stack = []
    counter = [0]
    scc_id = {}

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adj[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc_id[w] = v  # 以代表节点标识环
                if w == v:
                    break

    for v in nodes:
        if v not in index:
            strong(v)
    return scc_id


def main():
    nodes = [m["id"] for m in KG_DATA["modules"]]
    es = edges()
    scc = scc_index(es, nodes)
    rings = {}
    for n, rep in scc.items():
        rings.setdefault(rep, set()).add(n)

    keep, dropped = [], []
    for s, t, label in es:
        scc_of_source = scc.get(s)
        # 环内边：按主章节教材顺序裁决，方向与教材顺序相反的边只留作可视化
        if scc_of_source == scc.get(t) and len(rings[scc_of_source]) > 1:
            if MODULE_CHAPTER[s] < MODULE_CHAPTER[t]:
                keep.append((s, t, label))
            elif MODULE_CHAPTER[s] > MODULE_CHAPTER[t]:
                dropped.append((s, t, label))
            else:  # 同章节（不应出现）：丢弃，仅记录
                dropped.append((s, t, label))
        else:
            keep.append((s, t, label))

    assert dropped, "未检测到环，无需裁决"

    # Kahn 拓扑排序（平手取模块数组顺序）
    indeg = {n: 0 for n in nodes}
    adj = {n: [] for n in nodes}
    for s, t, _l in keep:
        adj[s].append(t)
        indeg[t] += 1
    ready = sorted([n for n in nodes if indeg[n] == 0], key=lambda n: MODULE_INDEX[n])
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for w in adj[n]:
            indeg[w] -= 1
            if indeg[w] == 0:
                # 插入保持数组顺序稳定
                ready.append(w)
                ready.sort(key=lambda x: MODULE_INDEX[x])
    if len(order) != len(nodes):
        print("仍有环未解决：", [n for n in nodes if n not in order])
        return 1

    # 校验：所有保留边是否都满足 rank(from) < rank(to)
    rank = {n: i for i, n in enumerate(order)}
    bad = [(s, t, l) for s, t, l in keep if rank[s] >= rank[t]]
    assert not bad, f"路径违反边: {bad}"

    print("== 保留的排序边 ==")
    for s, t, l in keep:
        print(f"  {s} -> {t} | {l}")
    print("== 被裁决丢弃（仅可视化） ==")
    for s, t, l in dropped:
        print(f"  {s} -> {t} | {l}")
    print("== 重排后学习路径 ==")
    for n in order:
        print("  " + LP_TITLE[n].rstrip("→"))
    if any(t.endswith("→") for t in LP_TITLE.values()):
        pass  # 文案带箭头，打印即路径

    # 输出可直接粘贴的 learning_path 数组
    arr = ",\n".join('            "' + LP_TITLE[n] + '"' if n != order[-1]
                     else '            "' + LP_TITLE[n].rstrip("→") + '"'
                     for n in order)
    print("\n== learning_path 数组（粘贴用） ==\n" + arr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
