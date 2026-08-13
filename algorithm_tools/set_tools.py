from __future__ import annotations

from itertools import combinations
from typing import Any

from algorithm_tools.common import stable_unique, tool_response, value_key


SUPPORTED_OPERATIONS = {
    "union",
    "intersection",
    "difference",
    "symmetric_difference",
    "cartesian_product",
    "power_set",
    "complement",
}


def _ordered(values: list[Any]) -> list[Any]:
    return sorted(stable_unique(values), key=value_key)


def calculate_set_operation(
    set_a: list[Any],
    operation: str,
    set_b: list[Any] | None = None,
    universal_set: list[Any] | None = None,
) -> dict[str, Any]:
    operation = operation.strip().lower()
    aliases = {
        "并集": "union",
        "交集": "intersection",
        "差集": "difference",
        "对称差": "symmetric_difference",
        "笛卡尔积": "cartesian_product",
        "幂集": "power_set",
        "补集": "complement",
    }
    operation = aliases.get(operation, operation)
    if operation not in SUPPORTED_OPERATIONS:
        raise ValueError(f"unsupported set operation: {operation}")

    a = _ordered(set_a)
    b = _ordered(set_b or [])
    a_map = {value_key(value): value for value in a}
    b_map = {value_key(value): value for value in b}

    if operation == "union":
        result = _ordered(a + b)
        rule = "A ∪ B 包含至少属于 A 或 B 的元素。"
    elif operation == "intersection":
        result = [value for key, value in a_map.items() if key in b_map]
        rule = "A ∩ B 只保留同时属于 A 和 B 的元素。"
    elif operation == "difference":
        result = [value for key, value in a_map.items() if key not in b_map]
        rule = "A - B 保留属于 A 但不属于 B 的元素。"
    elif operation == "symmetric_difference":
        result = _ordered(
            [value for key, value in a_map.items() if key not in b_map]
            + [value for key, value in b_map.items() if key not in a_map]
        )
        rule = "对称差保留只属于其中一个集合的元素。"
    elif operation == "cartesian_product":
        result = [[left, right] for left in a for right in b]
        rule = "A × B 枚举第一项来自 A、第二项来自 B 的所有有序对。"
    elif operation == "power_set":
        if len(a) > 12:
            raise ValueError("power_set supports at most 12 distinct elements")
        result = [list(choice) for size in range(len(a) + 1) for choice in combinations(a, size)]
        rule = "幂集包含 A 的全部子集，包括空集和 A 本身。"
    else:
        if universal_set is None:
            raise ValueError("universal_set is required for complement")
        universe = _ordered(universal_set)
        universe_map = {value_key(value): value for value in universe}
        if not set(a_map) <= set(universe_map):
            raise ValueError("set_a must be a subset of universal_set")
        result = [value for key, value in universe_map.items() if key not in a_map]
        rule = "A 的补集包含全集中所有不属于 A 的元素。"

    steps = [
        f"集合 A 去重后为 {a}。",
        f"集合 B 去重后为 {b}。" if operation not in {"power_set", "complement"} else rule,
        f"按 {operation} 的定义逐项计算，得到 {result}。",
    ]
    return tool_response({"operation": operation, "value": result}, steps, rule)
