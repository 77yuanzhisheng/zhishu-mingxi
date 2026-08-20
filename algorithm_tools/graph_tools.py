from __future__ import annotations

from collections import deque
import heapq
import math
from numbers import Real
from typing import Any

from algorithm_tools.common import stable_unique, tool_response, value_key


def _parse_edge(edge: Any, weighted: bool = False) -> tuple[Any, Any, float]:
    if isinstance(edge, dict):
        source = edge.get("source")
        target = edge.get("target")
        weight = edge.get("weight", 1)
    elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
        source, target = edge[0], edge[1]
        weight = edge[2] if len(edge) >= 3 else 1
    else:
        raise ValueError("each edge must be [source, target, weight?] or an object")
    if source is None or target is None:
        raise ValueError("edge source and target must not be null")
    if weighted:
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
            raise ValueError("edge weights must be finite numbers")
        if weight < 0:
            raise ValueError("Dijkstra does not support negative edge weights")
    return source, target, float(weight)


def generate_hasse_diagram(
    elements: list[Any],
    relation: list[Any] | None = None,
    matrix: list[list[int | bool]] | None = None,
    relation_type: str = "explicit",
) -> dict[str, Any]:
    vertices = stable_unique(elements)
    if not vertices:
        raise ValueError("elements must not be empty")
    keys = [value_key(vertex) for vertex in vertices]
    index = {key: position for position, key in enumerate(keys)}
    size = len(vertices)
    mode = relation_type.strip().lower()
    supported_modes = {"explicit", "divisibility", "less_equal", "subset"}
    if mode not in supported_modes:
        raise ValueError(
            "relation_type must be explicit, divisibility, less_equal or subset"
        )

    if mode != "explicit" and (relation is not None or matrix is not None):
        raise ValueError("automatic relation modes do not accept relation or matrix")

    if mode == "divisibility":
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in vertices
        ):
            raise ValueError("divisibility mode requires positive integer elements")
        closure = [
            [target % source == 0 for target in vertices]
            for source in vertices
        ]
    elif mode == "less_equal":
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            for value in vertices
        ):
            raise ValueError("less_equal mode requires finite numeric elements")
        closure = [
            [source <= target for target in vertices]
            for source in vertices
        ]
    elif mode == "subset":
        if any(not isinstance(value, (list, tuple)) for value in vertices):
            raise ValueError("subset mode requires every element to be a JSON array")
        normalized_sets = [
            {value_key(item) for item in value}
            for value in vertices
        ]
        closure = [
            [source.issubset(target) for target in normalized_sets]
            for source in normalized_sets
        ]
    elif matrix is not None:
        if len(matrix) != size or any(len(row) != size for row in matrix):
            raise ValueError("relation matrix size must match elements")
        closure = [[bool(value) for value in row] for row in matrix]
        if any(value not in (0, 1, False, True) for row in matrix for value in row):
            raise ValueError("relation matrix values must be 0/1 or true/false")
    else:
        if relation is None:
            raise ValueError("explicit mode requires relation or matrix")
        closure = [[False] * size for _ in range(size)]
        for pair in relation:
            source, target, _ = _parse_edge(pair)
            source_key, target_key = value_key(source), value_key(target)
            if source_key not in index or target_key not in index:
                raise ValueError("relation pairs may only contain declared elements")
            closure[index[source_key]][index[target_key]] = True

    if not all(closure[i][i] for i in range(size)):
        raise ValueError("relation must be reflexive to define a partial order")
    for i in range(size):
        for j in range(size):
            if i != j and closure[i][j] and closure[j][i]:
                raise ValueError("relation must be antisymmetric to define a partial order")
            for k in range(size):
                if closure[i][j] and closure[j][k] and not closure[i][k]:
                    raise ValueError("relation must be transitive to define a partial order")

    covers: list[tuple[int, int]] = []
    for i in range(size):
        for j in range(size):
            if i == j or not closure[i][j]:
                continue
            if not any(k not in (i, j) and closure[i][k] and closure[k][j] for k in range(size)):
                covers.append((i, j))

    levels = [0] * size
    for _ in range(size):
        changed = False
        for lower, upper in covers:
            if levels[upper] <= levels[lower]:
                levels[upper] = levels[lower] + 1
                changed = True
        if not changed:
            break

    result = {
        "relation_type": mode,
        "relation_pairs": [
            [vertices[i], vertices[j]]
            for i in range(size)
            for j in range(size)
            if closure[i][j]
        ],
        "nodes": [
            {"id": keys[i], "label": str(vertices[i]), "value": vertices[i], "level": levels[i]}
            for i in range(size)
        ],
        "edges": [
            {"source": keys[lower], "target": keys[upper], "relation": "covers"}
            for lower, upper in covers
        ],
        "levels": {
            str(level): [vertices[i] for i in range(size) if levels[i] == level]
            for level in sorted(set(levels))
        },
    }
    steps = [
        (
            "根据元素集合自动构造整除偏序关系。"
            if mode == "divisibility"
            else "根据元素集合自动构造小于等于偏序关系。"
            if mode == "less_equal"
            else "把每个数组视为集合，自动构造子集偏序关系。"
            if mode == "subset"
            else "读取用户提供的有序对或关系矩阵。"
        ),
        "验证关系满足自反性、反对称性和传递性。",
        "删除每个元素到自身的自反边。",
        "删除可经由中间元素推出的传递边，只保留覆盖关系。",
        "按覆盖关系从极小元向上分层，生成节点与边 JSON。",
    ]
    return tool_response(
        result,
        steps,
        "哈斯图仅绘制偏序关系中的覆盖边；自动模式会在元素变化后重新计算全部关系。",
    )


def dijkstra_shortest_path(
    edges: list[Any],
    start: Any,
    end: Any,
    directed: bool = False,
    vertices: list[Any] | None = None,
) -> dict[str, Any]:
    vertex_values = stable_unique((vertices or []) + [start, end])
    values_by_key = {value_key(value): value for value in vertex_values}
    adjacency: dict[str, list[tuple[str, float]]] = {key: [] for key in values_by_key}

    for raw_edge in edges:
        source, target, weight = _parse_edge(raw_edge, weighted=True)
        source_key, target_key = value_key(source), value_key(target)
        values_by_key.setdefault(source_key, source)
        values_by_key.setdefault(target_key, target)
        adjacency.setdefault(source_key, []).append((target_key, weight))
        adjacency.setdefault(target_key, [])
        if not directed:
            adjacency[target_key].append((source_key, weight))

    start_key, end_key = value_key(start), value_key(end)
    distances = {key: math.inf for key in adjacency}
    previous: dict[str, str] = {}
    distances[start_key] = 0.0
    queue: list[tuple[float, str]] = [(0.0, start_key)]
    visited_order: list[str] = []

    while queue:
        distance, current = heapq.heappop(queue)
        if distance != distances[current]:
            continue
        visited_order.append(current)
        if current == end_key:
            break
        for neighbor, weight in adjacency[current]:
            candidate = distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = current
                heapq.heappush(queue, (candidate, neighbor))

    reachable = math.isfinite(distances[end_key])
    path_keys: list[str] = []
    if reachable:
        current = end_key
        while True:
            path_keys.append(current)
            if current == start_key:
                break
            current = previous[current]
        path_keys.reverse()

    distance_value: int | float | None = distances[end_key] if reachable else None
    if isinstance(distance_value, float) and distance_value.is_integer():
        distance_value = int(distance_value)
    result = {
        "reachable": reachable,
        "path": [values_by_key[key] for key in path_keys],
        "distance": distance_value,
        "visited_order": [values_by_key[key] for key in visited_order],
        "distances": {
            key: (int(value) if math.isfinite(value) and value.is_integer() else value if math.isfinite(value) else None)
            for key, value in distances.items()
        },
    }
    steps = [
        f"将起点 {start} 的暂定距离设为 0，其余顶点设为无穷大。",
        f"依次选取暂定距离最小的顶点：{[values_by_key[key] for key in visited_order]}。",
        "对相邻边执行松弛，并记录每个顶点的前驱。",
        f"{'回溯得到最短路径 ' + str(result['path']) if reachable else '终点不可达'}。",
    ]
    return tool_response(result, steps, "Dijkstra 适用于边权非负的有向图或无向图。")


def check_bipartite(matrix: list[list[int | bool]]) -> dict[str, Any]:
    if not matrix:
        raise ValueError("matrix must not be empty")
    size = len(matrix)
    if any(len(row) != size for row in matrix):
        raise ValueError("adjacency matrix must be square")
    if any(value not in (0, 1, False, True) for row in matrix for value in row):
        raise ValueError("adjacency matrix values must be 0/1 or true/false")

    adjacency = [set() for _ in range(size)]
    for i in range(size):
        for j in range(size):
            if matrix[i][j] or matrix[j][i]:
                adjacency[i].add(j)
                adjacency[j].add(i)

    colors: list[int | None] = [None] * size
    conflict: list[int] | None = None
    traversal: list[int] = []
    for source in range(size):
        if colors[source] is not None:
            continue
        colors[source] = 0
        queue = deque([source])
        while queue and conflict is None:
            current = queue.popleft()
            traversal.append(current)
            for neighbor in sorted(adjacency[current]):
                if colors[neighbor] is None:
                    colors[neighbor] = 1 - int(colors[current])
                    queue.append(neighbor)
                elif colors[neighbor] == colors[current]:
                    conflict = [current, neighbor]
                    break

    is_bipartite = conflict is None
    result = {
        "is_bipartite": is_bipartite,
        "partitions": {
            "left": [index for index, color in enumerate(colors) if color == 0],
            "right": [index for index, color in enumerate(colors) if color == 1],
        } if is_bipartite else None,
        "colors": colors,
        "conflict_edge": conflict,
    }
    steps = [
        "把邻接矩阵转换为无向邻接表。",
        "对每个连通分量执行广度优先搜索并交替染成 0、1 两色。",
        f"访问顶点顺序为 {traversal}。",
        "所有相邻顶点颜色均不同。" if is_bipartite else f"边 {conflict} 的两个端点颜色相同，产生冲突。",
    ]
    return tool_response(result, steps, "图可二分当且仅当它可以被二染色；非对称矩阵按无向图处理。")
