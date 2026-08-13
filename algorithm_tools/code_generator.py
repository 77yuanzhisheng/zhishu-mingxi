from __future__ import annotations

from textwrap import dedent
from typing import Any

from algorithm_tools.common import tool_response


PROBLEM_KEYWORDS = {
    "truth_table": ("真值表", "truth table"),
    "relation_properties": ("关系性质", "自反", "传递", "relation"),
    "set_operation": ("集合运算", "并集", "交集", "set operation"),
    "dijkstra": ("最短路径", "dijkstra"),
    "bipartite": ("二分图", "bipartite"),
    "hasse": ("哈斯图", "偏序", "hasse"),
}


PYTHON_TEMPLATES = {
    "truth_table": '''
from itertools import product

def truth_table(expression, variables):
    for values in product([False, True], repeat=len(variables)):
        env = dict(zip(variables, values))
        result = bool(eval(expression, {"__builtins__": {}}, env))
        print(env, result)
''',
    "relation_properties": '''
def relation_properties(matrix):
    n = len(matrix)
    reflexive = all(matrix[i][i] for i in range(n))
    symmetric = all(matrix[i][j] == matrix[j][i] for i in range(n) for j in range(n))
    transitive = all(
        not (matrix[i][j] and matrix[j][k]) or matrix[i][k]
        for i in range(n) for j in range(n) for k in range(n)
    )
    return reflexive, symmetric, transitive
''',
    "set_operation": '''
def set_operation(a, b):
    a, b = set(a), set(b)
    return {
        "union": a | b,
        "intersection": a & b,
        "a_minus_b": a - b,
        "symmetric_difference": a ^ b,
    }
''',
    "dijkstra": '''
import heapq

def dijkstra(graph, start):
    distance = {vertex: float("inf") for vertex in graph}
    distance[start] = 0
    queue = [(0, start)]
    while queue:
        current_distance, current = heapq.heappop(queue)
        if current_distance != distance[current]:
            continue
        for neighbor, weight in graph[current]:
            candidate = current_distance + weight
            if candidate < distance[neighbor]:
                distance[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return distance
''',
    "bipartite": '''
from collections import deque

def is_bipartite(graph):
    color = {}
    for start in graph:
        if start in color:
            continue
        color[start] = 0
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in graph[current]:
                if neighbor not in color:
                    color[neighbor] = 1 - color[current]
                    queue.append(neighbor)
                elif color[neighbor] == color[current]:
                    return False, None
    return True, color
''',
    "hasse": '''
def hasse_edges(elements, relation):
    relation = set(map(tuple, relation))
    edges = []
    for lower in elements:
        for upper in elements:
            if lower == upper or (lower, upper) not in relation:
                continue
            has_middle = any(
                middle not in (lower, upper)
                and (lower, middle) in relation
                and (middle, upper) in relation
                for middle in elements
            )
            if not has_middle:
                edges.append((lower, upper))
    return edges
''',
}


C_TEMPLATES = {
    "truth_table": '''
#include <stdio.h>

int main(void) {
    for (int p = 0; p <= 1; ++p)
        for (int q = 0; q <= 1; ++q)
            printf("p=%d q=%d result=%d\\n", p, q, (!p) || q);
    return 0;
}
''',
    "relation_properties": '''
#include <stdbool.h>

bool is_reflexive(int n, const int matrix[n][n]) {
    for (int i = 0; i < n; ++i)
        if (!matrix[i][i]) return false;
    return true;
}
''',
    "set_operation": '''
#include <stdbool.h>

void set_union(const bool a[], const bool b[], bool result[], int universe_size) {
    for (int i = 0; i < universe_size; ++i)
        result[i] = a[i] || b[i];
}
''',
    "dijkstra": '''
#include <limits.h>
#include <stdbool.h>

void dijkstra(int n, int graph[n][n], int start, int distance[n]) {
    bool used[n];
    for (int i = 0; i < n; ++i) { distance[i] = INT_MAX; used[i] = false; }
    distance[start] = 0;
    for (int step = 0; step < n; ++step) {
        int current = -1;
        for (int i = 0; i < n; ++i)
            if (!used[i] && (current < 0 || distance[i] < distance[current])) current = i;
        if (current < 0 || distance[current] == INT_MAX) break;
        used[current] = true;
        for (int next = 0; next < n; ++next)
            if (graph[current][next] >= 0 && distance[current] + graph[current][next] < distance[next])
                distance[next] = distance[current] + graph[current][next];
    }
}
''',
    "bipartite": '''
#include <stdbool.h>

bool color_vertex(int n, int graph[n][n], int vertex, int colors[], int color) {
    colors[vertex] = color;
    for (int next = 0; next < n; ++next) if (graph[vertex][next]) {
        if (colors[next] == color) return false;
        if (colors[next] == -1 && !color_vertex(n, graph, next, colors, 1 - color)) return false;
    }
    return true;
}
''',
    "hasse": '''
#include <stdbool.h>

bool is_cover(int n, bool relation[n][n], int lower, int upper) {
    if (lower == upper || !relation[lower][upper]) return false;
    for (int middle = 0; middle < n; ++middle)
        if (middle != lower && middle != upper && relation[lower][middle] && relation[middle][upper])
            return false;
    return true;
}
''',
}


def _infer_problem_type(problem: str) -> str:
    lowered = problem.lower()
    matches = [name for name, words in PROBLEM_KEYWORDS.items() if any(word in lowered for word in words)]
    if not matches:
        raise ValueError(
            "cannot infer problem_type; use one of: " + ", ".join(PROBLEM_KEYWORDS)
        )
    return matches[0]


def generate_discrete_math_code(
    problem: str,
    language: str = "python",
    problem_type: str | None = None,
) -> dict[str, Any]:
    if not problem.strip():
        raise ValueError("problem must not be empty")
    language = language.strip().lower()
    if language not in {"python", "c"}:
        raise ValueError("language must be python or c")
    selected_type = (problem_type or _infer_problem_type(problem)).strip().lower()
    templates = PYTHON_TEMPLATES if language == "python" else C_TEMPLATES
    if selected_type not in templates:
        raise ValueError("unsupported problem_type: " + selected_type)

    code = dedent(templates[selected_type]).strip() + "\n"
    result = {
        "problem": problem,
        "problem_type": selected_type,
        "language": language,
        "code": code,
    }
    steps = [
        f"识别问题类型为 {selected_type}。",
        f"选择 {language} 的确定性算法模板。",
        "生成包含核心算法的数据结构、循环和返回值。",
    ]
    return tool_response(result, steps, "代码由经过检查的离散数学算法模板生成，具体输入数据可在调用处补充。")
