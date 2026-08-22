import sys
sys.path.insert(0, r"D:\挑战杯\zhishu-mingxi")
from backend.kb.definition_search import search_definition, get_index_stats

print("index:", get_index_stats())
for q in ["什么是命题", "德摩根律是什么", "幂集的元素个数", "握手定理", "哈密顿图的判定", "证明一下欧拉公式"]:
    hits = search_definition(q)
    print(f"--- {q} ---")
    for h in hits[:2]:
        print(f"   [{h['score']}] {h['term']}: {h['definition'][:50]}")
    if not hits:
        print("   (未命中)")
