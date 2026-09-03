# -*- coding: utf-8 -*-
"""队员2 · 任务⑥：平台知识图谱补全至 9 模块（与教材 19 章全量对齐）

从 data/teacher_kg.json（教师教材四层结构）生成缺失的模块节点：
  - 集合论(st) 追加：st_04 有穷集的计数(C01.4) / st_05 函数(C03.1-2) / st_06 双射与基数(C03.3)
  - number_theory 初等数论：nt_01..nt_07 ← C04 全部 7 节
  - combinatorics 组合数学：cm_01..cm_07 ← C10(4节) + C11(6节)
  - algebraic_structure 代数结构：ag_01..ag_08 ← C12(3节) + C13(4节) + C14(2节)

输出：scripts/kg_modules_extra.json（供人工审阅 + 拼接入 backend/kb/router.py KG_DATA）
      以及 st_extra_concepts（插入 set_theory.children）。
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "kg_modules_extra.json"


def type_of(title: str) -> str:
    if re.search(r"定理|性质|恒等式|引理|推论", title):
        return "theorem"
    if re.search(r"算法|法则|规则|方法|步骤|解法", title):
        return "rule"
    if re.search(r"例子|例题|实例|应用", title):
        return "example"
    return "definition"


def concept_from_sections(chapter, sections, prefix: str) -> tuple:
    """由教材节列表生成一个平台概念 dict（概念名=节标题去序号）。"""
    names = [s["title"].split(" ", 1)[-1] for s in sections]
    items = []
    for s in sections:
        for k in s["kps"]:
            pts = [p["title"] for p in k.get("points", [])]
            detail = "、".join(pts[:4])
            text = f"{k['title']}：{detail}" if detail else k["title"]
            items.append({
                "type": type_of(k["title"]),
                "node_id": f"{prefix}_{len(items) + 1:02d}",
                "text": text[:80],
                "search_query": " ".join([k["title"]] + pts)[:90],
                "_pre": k.get("pre", []),   # 教材知识点的前置依赖（供学习路径用，不入平台图谱）
                "_chapter": chapter["id"],
            })
    title = " / ".join(names) if len(names) < 3 else f"{names[0]}等"
    sec_nos = "、".join(s["title"].split(" ", 1)[0] + " 节" for s in sections)
    k_titles = "、".join(i["text"].split("：")[0] for i in items[:4])
    desc = f"教材 {sec_nos}：{k_titles}。"
    return {
        "name": title,
        "node_id": prefix,
        "description": desc,
        "search_query": " ".join(i["search_query"] for i in items)[:100],
        "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items],
        "_items_meta": [{"node_id": i["node_id"], "title": i["text"].split("：")[0],
                         "pre": i["_pre"], "chapter": i["_chapter"]} for i in items],
    }


def find(chapter_id: str, kg) -> dict:
    for ch in kg["chapters"]:
        if ch["id"] == chapter_id:
            return ch
    raise KeyError(chapter_id)


def sect(chapter, no: str):
    """no='4.1' → 返回标题以 '4.1' 开头的 section"""
    for s in chapter["sections"]:
        if s["title"].startswith(no):
            return s
    raise KeyError(no)


def build_module(kg, module_id: str, name: str, plan: list, search_kw: str) -> dict:
    """plan: [(concept_prefix, chapter_id, [section_no...])]"""
    children = []
    for _i, (prefix, chid, secs) in enumerate(plan, 1):
        ch = find(chid, kg)
        children.append(concept_from_sections(ch, [sect(ch, s) for s in secs], prefix))
    first_ks = [c["name"] for c in children[:3]]
    return {
        "id": module_id,
        "name": name,
        "description": f"面向离散数学《数学基础》教材的{name}模块，覆盖：{'、'.join(first_ks)}等。",
        "search_query": search_kw,
        "children": children,
    }


def main():
    kg = json.load(open(ROOT / "data" / "teacher_kg.json", encoding="utf-8"))

    # ---- st 追加概念 ----
    c01, c03 = find("C01", kg), find("C03", kg)
    st_extra = [
        concept_from_sections(c01, [sect(c01, "1.4")], "st_04"),
        concept_from_sections(c03, [sect(c03, "3.1"), sect(c03, "3.2")], "st_05"),
        concept_from_sections(c03, [sect(c03, "3.3")], "st_06"),
    ]

    # ---- gt 追加概念（平面图 C08 / 支配集与着色 C09）----
    c08, c09 = find("C08", kg), find("C09", kg)
    gt_extra = [
        concept_from_sections(c08, [sect(c08, "8.1"), sect(c08, "8.2"),
                                    sect(c08, "8.3"), sect(c08, "8.4")], "gt_05"),
        concept_from_sections(c09, [sect(c09, "9.1"), sect(c09, "9.2"),
                                    sect(c09, "9.3"), sect(c09, "9.4")], "gt_06"),
    ]

    # ---- 新模块 ----
    modules = [
        build_module(kg, "number_theory", "初等数论", [
            ("nt_01", "C04", ["4.1"]), ("nt_02", "C04", ["4.2"]), ("nt_03", "C04", ["4.3"]),
            ("nt_04", "C04", ["4.4"]), ("nt_05", "C04", ["4.5"]), ("nt_06", "C04", ["4.6"]),
            ("nt_07", "C04", ["4.7"]),
        ], "初等数论 整除 素数 同余 最大公因数 欧几里得算法 RSA"),
        build_module(kg, "combinatorics", "组合数学", [
            ("cm_01", "C10", ["10.1"]), ("cm_02", "C10", ["10.2"]), ("cm_03", "C10", ["10.3"]),
            ("cm_04", "C10", ["10.4"]),
            ("cm_05", "C11", ["11.1", "11.2", "11.3"]),
            ("cm_06", "C11", ["11.4", "11.5"]), ("cm_07", "C11", ["11.6"]),
        ], "组合数学 排列 组合 二项式定理 递推方程 生成函数 卡特兰数"),
        build_module(kg, "algebraic_structure", "代数结构", [
            ("ag_01", "C12", ["12.1"]), ("ag_02", "C12", ["12.2"]), ("ag_03", "C12", ["12.3"]),
            ("ag_04", "C13", ["13.1"]), ("ag_05", "C13", ["13.2"]), ("ag_06", "C13", ["13.3"]),
            ("ag_07", "C13", ["13.4"]), ("ag_08", "C14", ["14.1", "14.2"]),
        ], "代数系统 群 环 域 格 布尔代数 半群 同态 同构 置换群"),
    ]

    out = {
        "generated": "2026-09-03",
        "source": "data/teacher_kg.json（教材四层结构，19章/73节/150K/376P）",
        "st_extra_concepts": [c for c in st_extra],
        "gt_extra_concepts": [c for c in gt_extra],
        "modules": modules,
        "summary": {
            "modules": [(m["id"], m["name"], len(m["children"]),
                         sum(len(c["items"]) for c in m["children"]),
                         [c["node_id"] for c in m["children"]]) for m in modules],
            "st_extra": [(c["node_id"], c["name"], len(c["items"])) for c in st_extra],
            "gt_extra": [(c["node_id"], c["name"], len(c["items"])) for c in gt_extra],
        },
        "_item_deps": [  # 学习路径用：新节点 教材级前置依赖
            *[i for c in st_extra + gt_extra for i in c["_items_meta"]],
            *[i for m in modules for c in m["children"] for i in c["_items_meta"]],
        ],
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for mid, mname, nc, ni, nids in out["summary"]["modules"]:
        print(f"{mid} {mname}: {nc} 概念 / {ni} 条目")
        print("   ", ", ".join(nids))
    print("st_extra:", out["summary"]["st_extra"])
    print("gt_extra:", out["summary"]["gt_extra"])
    print(f"[OK] {OUT}")


if __name__ == "__main__":
    main()
