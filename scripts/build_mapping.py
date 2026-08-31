# -*- coding: utf-8 -*-
"""队员2 · 映射表 v2：整合自动 bigram + 题库映射别名 + 章→模块降级规则，产出人工校准清单"""
import json, re, sys, io, os, csv
from urllib.request import urlopen, Request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

teacher = json.load(open(BASE + "/data/teacher_kg.json", encoding="utf-8"))
platform = json.loads(urlopen(Request("http://127.0.0.1:8000/kb/knowledge-graph"), timeout=30).read())

# ---------- 平台词典：name + 题库映射.md 概念别名 ----------
concept_names = []  # 别名：{name} 优先
for m in platform.get("modules", []):
    concept_names.append(m.get("name", ""))
    for c in m.get("children", []):
        concept_names.append(c.get("name", ""))
doc = open(BASE + "/data/documents/题库节点映射.md", encoding="utf-8").read()
for m in re.finditer(r"^###\s+(.+?)\s+\(", doc, re.M):
    concept_names.append(m.group(1).strip())

plat_nodes = []
for m in platform.get("modules", []):
    plat_nodes.append((m.get("node_id", m.get("id")), m.get("name", ""), "module"))
    for c in m.get("children", []):
        plat_nodes.append((c.get("node_id", c.get("id")), c.get("name", ""), "concept"))
        for it in c.get("items", []):
            plat_nodes.append((it.get("node_id", it.get("id")), it.get("name", ""), "item"))

def norm(s):
    s = re.sub(r"^\s*\d+(\.\d+)*[\s、\.]*", "", str(s))
    s = re.sub(r"[（\(][^）\)]*[）\)]", "", s)
    s = re.sub(r"[^0-9一-鿿A-Za-z]", "", s)
    return s

def bigrams(s):
    return set(s[i:i+2] for i in range(len(s) - 1)) if len(s) > 1 else {s}

def dice(a, b):
    A, B = bigrams(a), bigrams(b)
    return 2 * len(A & B) / (len(A) + len(B)) if (A and B) else 0.0

# 章 -> 平台模块（我们已验证的真对应）
CH_MODULE = {
    "C01": "st", "C02": "rel", "C03": "st", "C04": "gt", "C05": "gt", "C06": "gt",
    "C07": "gt", "C08": "gt", "C09": "gt", "C10": "st", "C11": "st", "C12": "st",
    "C13": "st", "C14": "st", "C15": "pl", "C16": "pl", "C17": "pl", "C18": "fl", "C19": "fl",
}
MODULE_NODE = {"pl": "propositional_logic", "fl": "predicate_logic", "st": "set_theory",
               "mi": "induction", "rel": "relations", "gt": "graph_theory"}

def score_k(kn, name):
    return dice(kn, norm(name))

rows = []
for ch in teacher["chapters"]:
    aid = ch.get("id", "")
    mod = CH_MODULE.get(aid, "")
    mod_node = MODULE_NODE.get(mod, "")
    for sec in ch.get("sections", []):
        for k in sec.get("kps", []):
            kn = norm(k.get("title", ""))
            best, bs, best_lv = None, 0.0, None
            cands = []
            for (nid, name, lv) in plat_nodes:
                s = score_k(kn, name)
                if s > 0.40:
                    cands.append({"node": nid, "name": name, "level": lv, "score": round(s, 3)})
                if s > bs:
                    bs, best, best_lv = s, nid, lv
            rows.append({
                "k_id": k["id"], "k_name": k.get("title", ""), "ch": ch.get("title", ""),
                "sec": sec.get("title", ""), "module": mod if mod else "-",
                "best_node": best or "", "best_name": best or "", "best_level": best_lv or "",
                "score": round(bs, 3),
                "cands": sorted(cands, key=lambda x: -x["score"])[:3],
            })

# v1 自动映射（>=0.55）+ 章节降级
mapping, rev = {}, {}
for r in rows:
    target = None
    if r["score"] >= 0.55 and r["best_node"]:
        target = r["best_node"]
    elif r["module"]:
        target = MODULE_NODE[r["module"]]  # 降级到模块
    if target:
        mapping[r["k_id"]] = {"platform_node_id": target,
                              "platform_name": r["best_name"] if r["score"] >= 0.55 else r["module"],
                              "kind": "auto" if r["score"] >= 0.55 else "module_fallback",
                              "score": r["score"]}
        rev.setdefault(target, []).append(r["k_id"])

json.dump({"generated": "2026-08-31", "count": len(mapping), "mapping": mapping, "reverse": rev},
          open(BASE + "/data/mapping_v1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 人工校准清单：按分数排序前 80 条
rows.sort(key=lambda x: -x["score"])
md = ["# 节点映射 · 人工校准清单（前端学情染色/推荐题依赖待确认）",
      "",
      "说明：教师课件 K 节点 → 平台 node_id。「自动」= 已入 mapping_v1；「候选」为最佳匹配，请确认或修正。",
      "",
      "| K.id | 课件知识点 | 归属章节 | 当前映射 | 类型 | 最佳候选（该行可改） | 置信 |",
      "|---|---|---|---|---|---|---|"]
for r in rows[:80]:
    kind = "自动入表" if r["score"] >= 0.55 else ("模块降级" if r["module"] else "待定")
    cand_txt = "；".join(f"{c['name']}({c['node']},{c['score']})" for c in r["cands"][:2]) or "-"
    md.append(f"| {r['k_id']} | {r['k_name']} | {r['ch']} | {r['best_node'] or r['module'] or '-'} | {kind} | {cand_txt} | {r['score']} |")
open(BASE + "/data/映射表_人工校准清单.md", "w", encoding="utf-8").write("\n".join(md))

auto = sum(1 for v in mapping.values() if v["kind"] == "auto")
fb = sum(1 for v in mapping.values() if v["kind"] == "module_fallback")
print(f"mapping v1: {len(mapping)}/{len(rows)}（自动 {auto} + 模块降级 {fb}）")
print("saved: data/mapping_v1.json + data/映射表_人工校准清单.md")
