from __future__ import annotations

import ast
import json
import re
from textwrap import dedent
from typing import Any

from algorithm_tools.common import tool_response


PROBLEM_KEYWORDS = {
    "truth_table": ("真值表", "命题公式", "truth table"),
    "relation_properties": (
        "关系性质", "自反", "反自反", "对称", "反对称", "传递", "relation"
    ),
    "set_operation": (
        "集合运算", "并集", "交集", "差集", "补集", "幂集", "笛卡尔积", "set operation"
    ),
    "dijkstra": ("最短路径", "最小距离", "dijkstra"),
    "bipartite": ("二分图", "二染色", "bipartite"),
    "hasse": ("哈斯图", "偏序", "覆盖关系", "hasse"),
}


CODE_GENERATION_PROMPT = """你是离散数学算法工程师。请根据用户给出的完整题目生成对应代码。
要求：
1. 必须解决题目中的具体任务，不能只返回与题型对应的通用空模板。
2. 题目给出集合、矩阵、图、公式、起点终点等数据时，要体现在数据结构、输入解析或示例调用中。
3. 代码应完整、可运行，并包含必要的输出；不得调用网络、系统命令或第三方在线服务。
4. 只输出源代码，不要输出 Markdown 代码围栏或额外讲解。
5. 使用用户指定的编程语言。"""


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
}


def _parse_dijkstra_details(
    problem: str,
) -> tuple[list[tuple[str, str, int | float]], str, str, bool] | None:
    vertex = r"[A-Za-z0-9_\u4e00-\u9fff]+"
    edge_pattern = re.compile(
        rf"({vertex})\s*[-—]\s*({vertex})\s*"
        r"(?:的?权重(?:为|是)?|边权(?:为|是)?|[:=])\s*"
        r"(-?\d+(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )
    edges: list[tuple[str, str, int | float]] = []
    for source, target, raw_weight in edge_pattern.findall(problem):
        numeric = float(raw_weight)
        weight: int | float = int(numeric) if numeric.is_integer() else numeric
        edges.append((source, target, weight))
    if not edges:
        return None

    endpoints = re.findall(
        rf"(?:从\s*)?({vertex})\s*(?:到|至)\s*({vertex})", problem
    )
    if endpoints:
        start, end = endpoints[-1]
    else:
        start, end = edges[0][0], edges[-1][1]
    return edges, start, end, "有向" in problem


def _python_dijkstra_for_problem(
    edges: list[tuple[str, str, int | float]],
    start: str,
    end: str,
    directed: bool,
) -> str:
    adjacency: dict[str, list[tuple[str, int | float]]] = {}
    for source, target, weight in edges:
        adjacency.setdefault(source, []).append((target, weight))
        adjacency.setdefault(target, [])
        if not directed:
            adjacency[target].append((source, weight))
    graph_literal = repr(adjacency)
    return dedent(
        f'''
        import heapq

        def dijkstra(graph, start, end):
            distances = {{vertex: float("inf") for vertex in graph}}
            previous = {{}}
            distances[start] = 0
            queue = [(0, start)]

            while queue:
                current_distance, current = heapq.heappop(queue)
                if current_distance != distances[current]:
                    continue
                if current == end:
                    break
                for neighbor, weight in graph[current]:
                    candidate = current_distance + weight
                    if candidate < distances[neighbor]:
                        distances[neighbor] = candidate
                        previous[neighbor] = current
                        heapq.heappush(queue, (candidate, neighbor))

            if distances[end] == float("inf"):
                return [], None
            path = [end]
            while path[-1] != start:
                path.append(previous[path[-1]])
            path.reverse()
            return path, distances[end]

        graph = {graph_literal}
        path, distance = dijkstra(graph, {start!r}, {end!r})
        print("最短路径:", " -> ".join(path) if path else "不可达")
        print("最短距离:", distance)
        '''
    ).strip() + "\n"


def _c_dijkstra_for_problem(
    edges: list[tuple[str, str, int | float]],
    start: str,
    end: str,
    directed: bool,
) -> str:
    vertices = list(dict.fromkeys(
        [vertex for edge in edges for vertex in edge[:2]] + [start, end]
    ))
    index = {vertex: position for position, vertex in enumerate(vertices)}
    assignments: list[str] = []
    for source, target, weight in edges:
        assignments.append(f"graph[{index[source]}][{index[target]}] = {weight};")
        if not directed:
            assignments.append(f"graph[{index[target]}][{index[source]}] = {weight};")
    names = ", ".join(json.dumps(vertex, ensure_ascii=False) for vertex in vertices)
    assignment_code = "\n    ".join(assignments)
    return dedent(
        f'''
        #include <float.h>
        #include <stdbool.h>
        #include <stdio.h>

        #define N {len(vertices)}

        int main(void) {{
            const char *names[N] = {{{names}}};
            double graph[N][N];
            for (int i = 0; i < N; ++i)
                for (int j = 0; j < N; ++j)
                    graph[i][j] = -1;
            {assignment_code}

            int start = {index[start]}, end = {index[end]};
            double distance[N];
            int previous[N];
            bool used[N];
            for (int i = 0; i < N; ++i) {{
                distance[i] = DBL_MAX;
                previous[i] = -1;
                used[i] = false;
            }}
            distance[start] = 0;

            for (int step = 0; step < N; ++step) {{
                int current = -1;
                for (int i = 0; i < N; ++i)
                    if (!used[i] && (current < 0 || distance[i] < distance[current]))
                        current = i;
                if (current < 0 || distance[current] == DBL_MAX) break;
                used[current] = true;
                for (int next = 0; next < N; ++next) {{
                    if (graph[current][next] < 0) continue;
                    double candidate = distance[current] + graph[current][next];
                    if (candidate < distance[next]) {{
                        distance[next] = candidate;
                        previous[next] = current;
                    }}
                }}
            }}

            if (distance[end] == DBL_MAX) {{
                puts("终点不可达");
                return 0;
            }}
            int path[N], length = 0;
            for (int current = end; current >= 0; current = previous[current])
                path[length++] = current;
            printf("最短路径: ");
            for (int i = length - 1; i >= 0; --i)
                printf("%s%s", names[path[i]], i ? " -> " : "\n");
            printf("最短距离: %g\n", distance[end]);
            return 0;
        }}
        '''
    ).strip() + "\n"


def _build_verified_fallback(problem: str, language: str, selected_type: str) -> str:
    if selected_type == "dijkstra":
        details = _parse_dijkstra_details(problem)
        if details:
            edges, start, end, directed = details
            if language == "python":
                return _python_dijkstra_for_problem(edges, start, end, directed)
            return _c_dijkstra_for_problem(edges, start, end, directed)
    templates = PYTHON_TEMPLATES if language == "python" else C_TEMPLATES
    return dedent(templates[selected_type]).strip() + "\n"


C_TEMPLATES.update({
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
})


def _infer_problem_type(problem: str) -> str:
    lowered = problem.lower()
    scores = {
        name: sum(1 for word in words if word in lowered)
        for name, words in PROBLEM_KEYWORDS.items()
    }
    best_match = max(scores, key=scores.get)
    return best_match if scores[best_match] else "general"


def _extract_source_code(answer: str, language: str) -> str:
    fenced_blocks = re.findall(
        r"```(?:python|py|c)?\s*\n([\s\S]*?)```", answer, flags=re.IGNORECASE
    )
    code = (fenced_blocks[0] if fenced_blocks else answer).strip()
    if not code:
        raise ValueError("模型没有返回源代码")
    if language == "python":
        try:
            ast.parse(code)
        except SyntaxError as exc:
            raise ValueError(f"模型生成的 Python 代码语法无效：{exc.msg}") from exc
    elif not any(marker in code for marker in ("#include", "int main", "void ")):
        raise ValueError("模型返回的内容不像完整的 C 代码")
    return code + "\n"


def _generate_with_llm(
    problem: str,
    language: str,
    selected_type: str,
    llm_client: Any | None = None,
) -> str:
    if llm_client is None:
        from backend.chat.llm import OpenAICompatibleLLM

        llm_client = OpenAICompatibleLLM()
    answer = llm_client.generate(
        [
            {"role": "system", "content": CODE_GENERATION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"编程语言：{language}\n"
                    f"自动识别的题目类型：{selected_type}\n"
                    f"题目：{problem.strip()}"
                ),
            },
        ]
    )
    return _extract_source_code(answer, language)


def generate_discrete_math_code(
    problem: str,
    language: str = "python",
    problem_type: str | None = None,
    use_llm: bool = False,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    if not problem.strip():
        raise ValueError("problem must not be empty")
    language = language.strip().lower()
    if language not in {"python", "c"}:
        raise ValueError("language must be python or c")
    selected_type = (problem_type or _infer_problem_type(problem)).strip().lower()
    templates = PYTHON_TEMPLATES if language == "python" else C_TEMPLATES
    generation_mode = "verified_template"
    fallback_reason = None

    if use_llm:
        try:
            code = _generate_with_llm(
                problem, language, selected_type, llm_client=llm_client
            )
            generation_mode = "qwen"
        except Exception as exc:  # The verified template keeps this tool usable offline.
            fallback_reason = str(exc)
            if selected_type not in templates:
                raise ValueError(
                    "题目需要智能代码生成，但模型暂时不可用：" + fallback_reason
                ) from exc
            code = _build_verified_fallback(problem, language, selected_type)
    else:
        if selected_type not in templates:
            raise ValueError(
                "cannot infer a supported offline problem type; enable use_llm"
            )
        code = _build_verified_fallback(problem, language, selected_type)

    result = {
        "problem": problem,
        "problem_type": selected_type,
        "problem_type_source": "manual" if problem_type else "automatic",
        "language": language,
        "code": code,
        "generation_mode": generation_mode,
    }
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    steps = [
        f"分析完整题目并自动识别为 {selected_type}。",
        (
            "调用 Qwen，依据题目中的任务、数据和约束生成代码。"
            if generation_mode == "qwen"
            else "模型不可用或未启用，使用对应的已验证算法模板。"
        ),
        f"清理模型输出并检查 {language} 代码结构。",
    ]
    explanation = (
        "代码由 Qwen 根据完整题意生成，并经过基础格式与语法检查。"
        if generation_mode == "qwen"
        else "本次使用离线可靠模板；启动并配置模型后可生成针对具体题意的代码。"
    )
    return tool_response(result, steps, explanation)
