"""Optional AI explanation layer for personalized learning paths.

The production path must remain valid without an LLM. This module therefore
only produces constrained notes that can be replaced by a real model call later.
"""

from __future__ import annotations

from typing import Any


def generate_ai_notes(diagnosis: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    weak = diagnosis.get("weak_node_count", 0)
    if weak == 0:
        summary = "当前可用学习证据不足，已先给出离散数学通用诊断路径。"
    else:
        summary = f"已依据问答历史、做题记录和掌握度识别出 {weak} 个优先知识点。"
    return {
        "status": "rule_based_explanation",
        "summary": summary,
        "constraints": [
            "AI 只解释和微调学习建议，不直接改写规则生成的节点顺序。",
            "当模型不可用时，接口仍返回可执行的规则路径。",
        ],
        "stage_count": len(stages),
    }
