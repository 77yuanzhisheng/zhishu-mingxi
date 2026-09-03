# -*- coding: utf-8 -*-
"""队员2 · 映射校准：应用人工审阅修正（human_calibrated）生成 mapping_v2"""
import json

BASE = "D:/挑战杯/zhishu-mingxi/data"
v1 = json.load(open(BASE + "/mapping_v1.json", encoding="utf-8"))

# K.id -> platform_node_id（人工确认，学科语义锚定）
FIXES = {
    "K010101": "st_01_01",
    "K010102": "st_01_04",
    "K010201": "st_02",
    "K010301": "st_03",
    "K010302": "st_03",
    "K040502": "gt_03_04",
    "K060102": "gt_04_01",
    "K060201": "gt_04_02",
    "K060202": "gt_04_02",
    "K090301": "gt_01_03",
    "K150103": "pl_01_01",
    "K150201": "pl_01",
    "K160201": "pl_03_02",
    "K160202": "pl_03_02",
    "K180101": "fl_01_01",
    "K180102": "fl_01",
    "K020601": "rel_03_01",
    "K020701": "rel_04_01",
    "K020702": "rel_04_02",
    "K020403": "rel_02_03",
    "K020401": "rel_02_04",
    "K020402": "rel_02_05",
    "K050101": "gt_01",
    "K070201": "gt_04_04",
    "K070202": "gt_04_04",
    "K150101": "pl_01_01",
    "K150102": "pl_01_02",
    "K170201": "pl_03",
    "K160301": "pl_01_02",
}

names = {}
# 从映射 v1 及平台自建表拿名字（若无则保留简称）
for kid, info in v1["mapping"].items():
    names[kid] = info["platform_name"]

mapping = dict(v1["mapping"])
for kid, node in FIXES.items():
    old = mapping.get(kid, {})
    mapping[kid] = {
        "platform_node_id": node,
        "platform_name": old.get("platform_name", ""),
        "kind": "human_calibrated",
        "score": 1.0,
    }

# 重建 reverse
rev = {}
for kid, info in mapping.items():
    rev.setdefault(info["platform_node_id"], []).append(kid)

v2 = {"generated": "2026-08-31", "version": 2, "count": len(mapping),
      "auto": v1["count"], "human_calibrated": len(FIXES),
      "mapping": mapping, "reverse": rev}
json.dump(v2, open(BASE + "/mapping_v2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 直接用 v2 覆盖 v1 供教师图谱接口读取（接口读 mapping_v1.json）
json.dump({"generated": v2["generated"], "count": v2["count"], "mapping": mapping, "reverse": rev},
          open(BASE + "/mapping_v1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"mapping v2: {len(mapping)} 节点（人工校准 {len(FIXES)} 条）")
