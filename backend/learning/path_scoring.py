"""Rule scoring for personalized discrete-math learning paths."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

MODULE_DEPENDENCIES = {
    "propositional_logic": [],
    "predicate_logic": ["propositional_logic"],
    "set_theory": ["propositional_logic"],
    "induction": ["propositional_logic"],
    "relations": ["set_theory", "predicate_logic"],
    "graph_theory": ["relations", "set_theory"],
}

NODE_MODULE_MAP = {
    "pl": "propositional_logic",
    "fl": "predicate_logic",
    "st": "set_theory",
    "mi": "induction",
    "rel": "relations",
    "gt": "graph_theory",
}

MODULE_TITLES = {
    "propositional_logic": "命题逻辑",
    "predicate_logic": "谓词逻辑",
    "set_theory": "集合论",
    "induction": "数学归纳法",
    "relations": "关系",
    "graph_theory": "图论",
}

DEFAULT_NODES = ["pl_01_01", "fl_01_01", "st_01_01", "mi_01_01", "rel_01_01", "gt_01_01"]

KEYWORD_RULES = [
    (re.compile(r"graph|tree|path|图|树|路径|连通"), "gt_01_01"),
    (re.compile(r"relation|equivalence|partial order|关系|等价|偏序"), "rel_01_01"),
    (re.compile(r"set|集合|交集|并集|补集"), "st_01_01"),
    (re.compile(r"predicate|quantifier|谓词|量词"), "fl_01_01"),
    (re.compile(r"induction|归纳"), "mi_01_01"),
    (re.compile(r"proposition|logic|命题|逻辑|真值"), "pl_01_01"),
]

STAGE_TITLES = {
    "foundation": "补基础",
    "reinforcement": "巩固",
    "advancement": "提升",
}

STAGE_OBJECTIVES = {
    "foundation": "修复概念、定义和前置依赖，避免后续学习建立在不稳定基础上。",
    "reinforcement": "围绕高频错因进行变式练习和证明过程复盘。",
    "advancement": "在基础稳定后进入综合题、证明题和跨知识点迁移。",
}


def module_for_node(node_id: str) -> str:
    return NODE_MODULE_MAP.get(node_id.split("_", 1)[0], "unknown")


def valid_node_id(node_id: str) -> bool:
    return bool(re.fullmatch(r"(pl|fl|st|mi|rel|gt)_\d{2}_\d{2}", node_id.strip()))


def build_rule_path(evidence: dict[str, Any], max_nodes: int = 8) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    scored = _score_nodes(evidence)
    if not scored:
        scored = [_default_score(node_id, index) for index, node_id in enumerate(DEFAULT_NODES)]
    selected = _dependency_order(scored)[:max_nodes]
    stages = _group_stages(selected)
    data_quality = _data_quality(evidence, selected)
    diagnosis = {
        "discrete_math_only": True,
        "weak_node_count": len([node for node in selected if node["priority"] >= 40]),
        "dominant_modules": _dominant_modules(selected),
        "flow": ["diagnosis", "foundation", "reinforcement", "advancement"],
    }
    return stages, diagnosis, data_quality


def _score_nodes(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for row in evidence.get("mastery", []):
        node_id = str(row["node_id"]).strip()
        if not valid_node_id(node_id):
            continue
        item = items.setdefault(node_id, _blank_node(node_id))
        total = int(row.get("total_count") or 0)
        correct = int(row.get("correct_count") or 0)
        accuracy = correct / total if total else 0.0
        level = int(row.get("level") or 0)
        weakness = max(0.0, 1 - max(level / 4, accuracy))
        item["components"]["mastery"] = max(item["components"]["mastery"], weakness * 40)
        item["evidence"]["mastery"] = {"level": level, "accuracy": round(accuracy, 4), "total_count": total}

    grouped_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence.get("events", []):
        node_id = str(row["node_id"]).strip()
        if valid_node_id(node_id):
            grouped_events[node_id].append(row)
    for node_id, rows in grouped_events.items():
        item = items.setdefault(node_id, _blank_node(node_id))
        graded = [row for row in rows if row.get("is_correct") is not None]
        wrong = [row for row in graded if int(row.get("is_correct") or 0) == 0]
        wrong_rate = len(wrong) / len(graded) if graded else 0.35
        severity = min(1.0, wrong_rate + max(0, len(wrong) - 1) * 0.15)
        item["components"]["practice"] = severity * 25
        item["evidence"]["practice"] = {
            "event_count": len(rows),
            "graded_count": len(graded),
            "wrong_count": len(wrong),
            "wrong_rate": round(wrong_rate, 4) if graded else None,
            "question_types": sorted({row.get("question_type") for row in rows if row.get("question_type")}),
        }

    for row in evidence.get("messages", []):
        explicit = [node for node in row.get("node_ids", []) if valid_node_id(str(node))]
        inferred = [] if explicit else infer_nodes(str(row.get("content") or ""))
        for node_id in explicit:
            item = items.setdefault(str(node_id), _blank_node(str(node_id)))
            item["components"]["qa"] += 6
            item["evidence"]["qa"] = _qa_evidence(item, "explicit_node_ids", row)
        for node_id in inferred:
            item = items.setdefault(node_id, _blank_node(node_id))
            item["components"]["qa"] += 3
            item["evidence"]["qa"] = _qa_evidence(item, "keyword_inference", row)

    for row in evidence.get("grading", []):
        for node_id in _nodes_from_grading(row):
            item = items.setdefault(node_id, _blank_node(node_id))
            total_score = float(row.get("total_score") or 0)
            dimension_scores = row.get("dimension_scores") or {}
            errors = row.get("error_types") or []
            severe_dimensions = _severe_proof_dimensions(dimension_scores)
            weakness = max(0.0, 1 - total_score / 100)
            if severe_dimensions:
                weakness = max(weakness, 0.45 + min(len(severe_dimensions), 3) * 0.12)
            item["components"]["practice"] = max(item["components"]["practice"], min(25.0, weakness * 25))
            item["components"]["recency"] = max(item["components"]["recency"], 5)
            current = item["evidence"].get("grading", {"count": 0, "low_score_count": 0, "error_types": [], "severe_dimensions": []})
            current["count"] += 1
            if total_score < 70:
                current["low_score_count"] += 1
            current["latest_total_score"] = round(total_score, 2)
            current["needs_manual_review"] = bool(row.get("needs_manual_review"))
            current["error_types"] = sorted(set(current["error_types"]) | {str(error) for error in errors})
            current["severe_dimensions"] = sorted(set(current["severe_dimensions"]) | set(severe_dimensions))
            item["evidence"]["grading"] = current

    for node_id, item in items.items():
        item["components"]["dependency"] = _dependency_importance(module_for_node(node_id)) * 10
        item["components"]["recency"] = 5 if item["evidence"].get("practice") or item["evidence"].get("qa") or item["evidence"].get("grading") else 1
        item["priority"] = round(min(100.0, sum(item["components"].values())), 2)
        item["stage"] = _stage_for(item)
        item["confidence"] = _confidence(item)
        item.update(_presentation(item))
    return sorted(items.values(), key=lambda item: (-item["priority"], _module_rank(module_for_node(item["node_id"])), item["node_id"]))


def infer_nodes(content: str) -> list[str]:
    text = content.lower()
    return [node_id for pattern, node_id in KEYWORD_RULES if pattern.search(text)]


def _blank_node(node_id: str) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "module": module_for_node(node_id),
        "components": {"mastery": 0.0, "practice": 0.0, "qa": 0.0, "dependency": 0.0, "recency": 0.0},
        "evidence": {},
    }


def _qa_evidence(item: dict[str, Any], source: str, row: dict[str, Any]) -> dict[str, Any]:
    current = item["evidence"].get("qa", {"count": 0, "sources": [], "samples": []})
    current["count"] += 1
    if source not in current["sources"]:
        current["sources"].append(source)
    if len(current["samples"]) < 3:
        current["samples"].append(str(row.get("content") or "")[:120])
    return current


def _dependency_importance(module: str) -> float:
    dependents = sum(module in deps for deps in MODULE_DEPENDENCIES.values())
    return min(1.0, 0.35 + dependents * 0.25)


def _stage_for(item: dict[str, Any]) -> str:
    mastery = item["evidence"].get("mastery", {})
    practice = item["evidence"].get("practice", {})
    grading = item["evidence"].get("grading", {})
    level = mastery.get("level")
    wrong_rate = practice.get("wrong_rate")
    if (level is not None and level <= 1) or (wrong_rate is not None and wrong_rate >= 0.6):
        return "foundation"
    if grading.get("low_score_count") or grading.get("severe_dimensions"):
        return "reinforcement"
    if item["priority"] >= 45 or item["evidence"].get("qa"):
        return "reinforcement"
    return "advancement"


def _confidence(item: dict[str, Any]) -> float:
    confidence = 0.25
    if item["evidence"].get("mastery"):
        confidence += 0.3
    if item["evidence"].get("practice"):
        confidence += 0.3
    if item["evidence"].get("grading"):
        confidence += 0.2
    qa = item["evidence"].get("qa", {})
    if "explicit_node_ids" in qa.get("sources", []):
        confidence += 0.15
    elif qa:
        confidence += 0.05
    return round(min(1.0, confidence), 2)


def _presentation(item: dict[str, Any]) -> dict[str, Any]:
    node_id = item["node_id"]
    module = MODULE_TITLES.get(item["module"], item["module"])
    stage = item["stage"]
    return {
        "title": f"{module}：{node_id}",
        "reason": _reason(item, module),
        "tasks": _tasks(stage, node_id),
        "mastery_gate": _gate(stage, node_id),
        "status": "pending",
    }


def _reason(item: dict[str, Any], module_title: str) -> str:
    parts = []
    practice = item["evidence"].get("practice")
    mastery = item["evidence"].get("mastery")
    qa = item["evidence"].get("qa")
    if mastery:
        parts.append(f"掌握等级 {mastery['level']}/4，正确率 {mastery['accuracy']:.0%}")
    if practice:
        parts.append(f"近阶段错题 {practice['wrong_count']} 道")
    grading = item["evidence"].get("grading")
    if qa:
        parts.append(f"问答中出现 {qa['count']} 次困惑信号")
    if grading:
        parts.append(f"证明题最近得分 {grading.get('latest_total_score')}，薄弱维度 {'、'.join(grading.get('severe_dimensions', [])) or '无'}")
    return f"{module_title}节点优先级 {item['priority']}。" + "；".join(parts)


def _tasks(stage: str, node_id: str) -> list[dict[str, Any]]:
    if stage == "foundation":
        return [
            {"type": "concept_review", "title": "重读定义、定理和适用条件", "target": node_id},
            {"type": "basic_practice", "title": "完成 5 道基础题并订正错因", "target": node_id},
        ]
    if stage == "reinforcement":
        return [
            {"type": "variant_practice", "title": "完成 6 道变式题，记录错误类型", "target": node_id},
            {"type": "qa_review", "title": "回看相关问答，整理一条可复用解题模板", "target": node_id},
        ]
    return [
        {"type": "mixed_practice", "title": "完成跨知识点综合题", "target": node_id},
        {"type": "proof_challenge", "title": "尝试一道完整证明题并自检逻辑严密性", "target": node_id},
    ]


def _gate(stage: str, node_id: str) -> dict[str, Any]:
    if stage == "foundation":
        return {"node_id": node_id, "required_questions": 5, "accuracy_at_least": 0.8, "no_consecutive_same_error": 2}
    if stage == "reinforcement":
        return {"node_id": node_id, "required_questions": 6, "accuracy_at_least": 0.8, "latest_3_pass_at_least": 2}
    return {"node_id": node_id, "required_questions": 4, "accuracy_at_least": 0.85, "mixed_task_pass": True}


def _dependency_order(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["node_id"]: item for item in scored}
    modules_needed = {module_for_node(node_id) for node_id in by_id}
    for module in list(modules_needed):
        modules_needed.update(MODULE_DEPENDENCIES.get(module, []))
    ordered_modules = _topo_sort(modules_needed)
    result = []
    for module in ordered_modules:
        module_items = [item for item in scored if item["module"] == module]
        result.extend(sorted(module_items, key=lambda item: (-item["priority"], item["node_id"])))
    return result


def _topo_sort(modules: set[str]) -> list[str]:
    visited = set()
    result = []

    def visit(module: str) -> None:
        if module in visited:
            return
        visited.add(module)
        for dep in MODULE_DEPENDENCIES.get(module, []):
            if dep in modules:
                visit(dep)
        result.append(module)

    for module in MODULE_DEPENDENCIES:
        if module in modules:
            visit(module)
    return result


def _module_rank(module: str) -> int:
    return list(MODULE_DEPENDENCIES).index(module) if module in MODULE_DEPENDENCIES else 99


def _group_stages(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = []
    for stage in ["foundation", "reinforcement", "advancement"]:
        stage_nodes = [_public_node(node) for node in nodes if node["stage"] == stage]
        if stage_nodes:
            grouped.append({"stage": stage, "title": STAGE_TITLES[stage], "objective": STAGE_OBJECTIVES[stage], "nodes": stage_nodes})
    return grouped


def _public_node(node: dict[str, Any]) -> dict[str, Any]:
    return {key: node[key] for key in ["node_id", "module", "stage", "priority", "title", "reason", "evidence", "tasks", "mastery_gate", "status", "confidence"]}


def _data_quality(evidence: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "mastery": len(evidence.get("mastery", [])),
        "events": len(evidence.get("events", [])),
        "messages": len(evidence.get("messages", [])),
        "grading": len(evidence.get("grading", [])),
    }
    signal_count = counts["mastery"] + counts["events"] + counts["messages"] + counts["grading"]
    status = "insufficient_data" if signal_count == 0 else "partial" if signal_count < 5 else "sufficient"
    return {"status": status, "source_counts": counts, "generated_node_count": len(nodes)}


def _dominant_modules(nodes: list[dict[str, Any]]) -> list[str]:
    totals: dict[str, float] = defaultdict(float)
    for node in nodes:
        totals[node["module"]] += node["priority"]
    return [module for module, _ in sorted(totals.items(), key=lambda item: -item[1])[:3]]


def _default_score(node_id: str, index: int) -> dict[str, Any]:
    item = _blank_node(node_id)
    item["priority"] = max(30, 50 - index * 4)
    item["stage"] = "foundation" if index < 3 else "reinforcement"
    item["confidence"] = 0.25
    item["evidence"] = {"default": {"reason": "no_user_learning_evidence"}}
    item.update(_presentation(item))
    return item


def _nodes_from_grading(row: dict[str, Any]) -> list[str]:
    result = []
    for value in row.get("knowledge_points") or []:
        node_id = str(value).strip()
        if valid_node_id(node_id):
            result.append(node_id)
            continue
        inferred = infer_nodes(node_id)
        result.extend(inferred)
    return sorted(set(result))


def _severe_proof_dimensions(scores: dict[str, Any]) -> list[str]:
    limits = {
        "conclusion_correctness": 20,
        "key_reasoning_steps": 35,
        "logical_rigor": 25,
        "definition_theorem_usage": 10,
        "expression_symbol_norm": 10,
    }
    severe = []
    for dimension, maximum in limits.items():
        try:
            value = float(scores.get(dimension, maximum))
        except (TypeError, ValueError):
            value = maximum
        if value / maximum < 0.6:
            severe.append(dimension)
    return severe
