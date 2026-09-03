# -*- coding: utf-8 -*-
"""把 scripts/kg_modules_extra.json 拼接入 backend/kb/router.py 的 KG_DATA。

先精确还原上一次的错误拼接（模块插到了数组外），再按正确结构重拼：
  1. set_theory.children 追加 st_04/st_05/st_06（概念块收尾处，20 空格缩进）
  2. modules 数组末尾（graph_theory 之后）追加 number_theory/combinatorics/algebraic_structure（12 空格）
  3. edges 追加 7 条新模块关系，learning_path 扩充到 9 模块
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "backend" / "kb" / "router.py"
EXTRA = json.load(open(ROOT / "scripts" / "kg_modules_extra.json", encoding="utf-8"))

NEW_EDGES = [
    {"from": "set_theory", "to": "number_theory", "label": "整除是整数集合的性质"},
    {"from": "set_theory", "to": "combinatorics", "label": "排列组合=计数集合"},
    {"from": "number_theory", "to": "combinatorics", "label": "模运算服务于递推计数"},
    {"from": "set_theory", "to": "algebraic_structure", "label": "代数系统基于集合与运算"},
    {"from": "number_theory", "to": "algebraic_structure", "label": "模n同余构成循环群"},
    {"from": "graph_theory", "to": "combinatorics", "label": "卡特兰数=树形结构计数"},
    {"from": "relations", "to": "set_theory", "label": "函数=特殊关系"},
]

LP_OLD = '''        "learning_path": [
            "① 命题逻辑（基础语言）→",
            "② 集合论（数学对象）→",
            "③ 谓词逻辑（扩展推理）→",
            "④ 数学归纳法（证明工具）→",
            "⑤ 关系（元素间结构）→",
            "⑥ 图论（可视化网络）",
        ],'''
LP_NEW = '''        "learning_path": [
            "① 命题逻辑（基础语言）→",
            "② 谓词逻辑（扩展推理）→",
            "③ 数学归纳法（证明工具）→",
            "④ 集合论（数学对象）→",
            "⑤ 关系（元素间结构）→",
            "⑥ 图论（可视化网络）→",
            "⑦ 初等数论（整数结构）→",
            "⑧ 组合数学（计数方法）→",
            "⑨ 代数结构（运算体系）",
        ],'''


def blob(obj, indent: int) -> str:
    t = json.dumps(obj, ensure_ascii=False, indent=2)
    return "\n".join(" " * indent + line for line in t.splitlines())


def clean(obj):
    """剔除入图不需要的 _ 前缀辅助字段（_items_meta/_pre/_chapter）。"""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def revert(src: str) -> str:
    """精确还原上次的错误拼接（全部断言失败则中止）。"""
    # 4) learning_path
    assert src.count(LP_NEW) == 1, "lp_new 未找到，状态异常"
    src = src.replace(LP_NEW, LP_OLD, 1)
    # 3) edges 7 条
    edge_block = "\n".join(
        f'            {{"from": "{e["from"]}", "to": "{e["to"]}", "label": "{e["label"]}"}},'
        for e in NEW_EDGES
    )
    last_edge = '            {"from": "induction", "to": "graph_theory", "label": "树边数证明"},'
    src = src.replace(last_edge + "\n" + edge_block, last_edge, 1)
    # 2) 模块（含周围的破坏性位置）
    start_marker = '        ],\n        {\n          "id": "number_theory",'
    end_marker = '        },\n        "edges": ['
    assert src.count(start_marker) == 1 and src.count(end_marker) == 1, "模块区域锚点异常"
    i, j = src.index(start_marker), src.index(end_marker)
    src = src[:i] + '        ],' + src[j + len('        },'):]
    # 1) st_extra
    st_block = ",".join(blob(c, 20) for c in EXTRA["st_extra_concepts"])
    src = src.replace("                    },\n" + st_block + ",\n                ],\n", "                    },\n                ],\n", 1)
    return src


def splice(src: str) -> str:
    st_extra = [clean(c) for c in EXTRA["st_extra_concepts"]]
    # 1) st_extra → set_theory.children 末尾、induction 模块之前
    anchor_st = '                    },\n                ],\n            },\n            {\n                "id": "induction",'
    assert src.count(anchor_st) == 1
    st_block = ",".join(blob(c, 20) for c in st_extra)
    src = src.replace(anchor_st, "                    },\n" + st_block + ",\n                ],\n            },\n            {\n                \"id\": \"induction\",", 1)
    # 1b) gt_extra → graph_theory.children 末尾（gt_04 概念收尾后）
    anchor_gt = '                    },\n                ],\n            },\n        ],\n        "edges": ['
    assert src.count(anchor_gt) == 1
    gt_extra = [clean(c) for c in EXTRA["gt_extra_concepts"]]
    gt_block = ",".join(blob(c, 20) for c in gt_extra)
    src = src.replace(anchor_gt, "                    },\n" + gt_block + ",\n                ],\n            },\n        ],\n        \"edges\": [", 1)
    # 2) 新模块 → modules 数组末尾（graph_theory 模块 `},` 之后、数组 `],` 之前）
    anchor_mods = '            },\n        ],\n        "edges": ['
    assert src.count(anchor_mods) == 1
    mod_block = ",".join(blob(m, 12) for m in [clean(x) for x in EXTRA["modules"]])
    src = src.replace(anchor_mods, "            },\n" + mod_block + ",\n        ],\n        \"edges\": [", 1)
    # 3) edges + learning_path
    last_edge = '            {"from": "induction", "to": "graph_theory", "label": "树边数证明"},'
    assert src.count(last_edge) == 1
    edge_block = "\n".join(
        f'            {{"from": "{e["from"]}", "to": "{e["to"]}", "label": "{e["label"]}"}},'
        for e in NEW_EDGES
    )
    src = src.replace(last_edge, last_edge + "\n" + edge_block, 1)
    assert src.count(LP_OLD) == 1
    src = src.replace(LP_OLD, LP_NEW, 1)
    return src


def main():
    # 以 git HEAD 的干净版本为基线（当前工作区文件已被上一次错误拼接污染）
    import subprocess
    base = subprocess.run(
        ["git", "show", "HEAD:backend/kb/router.py"],
        capture_output=True, text=True, encoding="utf-8", check=True, cwd=str(ROOT),
    ).stdout
    assert '"id": "induction"' in base and "_items_meta" not in base, "基线异常"
    src = splice(base)

    import ast
    ast.parse(src)
    # 运行时校验：以临时模块加载新文本，再落盘
    import importlib
    sys.path.insert(0, str(ROOT))
    tmp = ROOT / "backend" / "kb" / "_router_new.py"
    tmp.write_text(src, encoding="utf-8")
    try:
        kg_mod = importlib.import_module("backend.kb._router_new")
        kg = kg_mod.KG_DATA
    finally:
        tmp.unlink(missing_ok=True)
    mods = [(m["id"], len(m["children"]), sum(len(c["items"]) for c in m["children"])) for m in kg["modules"]]
    nids = [i["node_id"] for m in kg["modules"] for c in m["children"] for i in c["items"]]
    print("模块数:", len(mods), "| items:", len(nids), "| 重复id:", len(nids) != len(set(nids)),
          "| edges:", len(kg["edges"]), "| lp:", len(kg["learning_path"]))
    assert len(mods) == 9 and len(nids) == 157 and len(nids) == len(set(nids))
    ROUTER.write_text(src, encoding="utf-8")
    print("[OK] 已写入", ROUTER)


if __name__ == "__main__":
    main()
