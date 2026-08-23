from __future__ import annotations

from typing import Any, Literal, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from algorithm_tools.code_generator import generate_discrete_math_code
from algorithm_tools.graph_tools import check_bipartite, dijkstra_shortest_path, generate_hasse_diagram
from algorithm_tools.logic_tools import convert_normal_forms, simplify_formula
from algorithm_tools.relation import analyze_relation
from algorithm_tools.set_tools import calculate_set_operation
from algorithm_tools.truth_table import generate_truth_table


router = APIRouter(prefix="/tools", tags=["Extended Tools"])

TOOL_CATALOG = [
    {"name": "truth-table", "title": "真值表生成", "category": "逻辑与关系"},
    {"name": "relation-properties", "title": "关系矩阵判断", "category": "逻辑与关系"},
    {"name": "formula-simplify", "title": "命题公式化简", "category": "命题逻辑"},
    {"name": "normal-forms", "title": "主范式转换", "category": "命题逻辑"},
    {"name": "set-operation", "title": "集合运算", "category": "集合论"},
    {"name": "hasse-diagram", "title": "哈斯图生成", "category": "关系"},
    {"name": "dijkstra", "title": "最短路径", "category": "图论"},
    {"name": "bipartite", "title": "二分图判定", "category": "图论"},
    {"name": "code-generate", "title": "Python/C 代码生成", "category": "代码生成"},
]


@router.get("", summary="获取统一算法工具目录")
def tool_catalog() -> dict[str, Any]:
    """Return every tool exposed by the single frontend tool center."""

    return {
        "total": len(TOOL_CATALOG),
        "groups": ["逻辑与关系", "命题逻辑", "集合论", "关系", "图论", "代码生成"],
        "tools": [
            {**item, "method": "POST", "endpoint": f"/tools/{item['name']}"}
            for item in TOOL_CATALOG
        ],
    }


class FormulaParams(BaseModel):
    expression: str


class FormulaToolRequest(BaseModel):
    params: FormulaParams


class TruthTableLegacyRequest(BaseModel):
    expression: str


class RelationParams(BaseModel):
    matrix: list[list[Union[int, bool]]]


class RelationLegacyRequest(BaseModel):
    matrix: list[list[Union[int, bool]]]


class RelationToolRequest(BaseModel):
    params: RelationParams


class SetOperationParams(BaseModel):
    set_a: list[Any]
    set_b: list[Any] | None = None
    operation: str
    universal_set: list[Any] | None = None


class SetOperationRequest(BaseModel):
    params: SetOperationParams


class HasseDiagramParams(BaseModel):
    elements: list[Any]
    relation: list[Any] | None = None
    matrix: list[list[Union[int, bool]]] | None = None
    relation_type: Literal[
        "explicit", "divisibility", "less_equal", "subset"
    ] = "explicit"


class HasseDiagramRequest(BaseModel):
    params: HasseDiagramParams


class DijkstraParams(BaseModel):
    edges: list[Any]
    start: Any
    end: Any
    directed: bool = False
    vertices: list[Any] | None = None


class DijkstraRequest(BaseModel):
    params: DijkstraParams


class BipartiteParams(BaseModel):
    matrix: list[list[Union[int, bool]]]


class BipartiteRequest(BaseModel):
    params: BipartiteParams


class CodeGenerationParams(BaseModel):
    problem: str
    language: Literal["python", "c"] = "python"
    use_llm: bool = True
    problem_type: Literal[
        "truth_table",
        "relation_properties",
        "set_operation",
        "dijkstra",
        "bipartite",
        "hasse",
        "general",
    ] | None = None


class CodeGenerationRequest(BaseModel):
    params: CodeGenerationParams


def _run_tool(function, **params) -> dict[str, Any]:
    try:
        return function(**params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/truth-table", tags=["Compatible Tools"])
def truth_table(request: TruthTableLegacyRequest | FormulaToolRequest) -> dict[str, Any]:
    if isinstance(request, TruthTableLegacyRequest):
        return _run_tool(generate_truth_table, expression=request.expression)
    table = _run_tool(generate_truth_table, expression=request.params.expression)
    return {
        "result": table,
        "steps": [
            "解析命题公式并提取变量。",
            f"枚举 {len(table['rows'])} 种真值指派。",
            "逐行计算公式真值并生成真值表。",
        ],
        "explanation": "每个含 n 个变量的命题公式共有 2^n 种真值指派。",
    }


@router.post("/relation-properties", tags=["Compatible Tools"])
def relation_properties(request: RelationLegacyRequest | RelationToolRequest) -> dict[str, Any]:
    if isinstance(request, RelationLegacyRequest):
        return _run_tool(analyze_relation, matrix=request.matrix)
    result = _run_tool(analyze_relation, matrix=request.params.matrix)
    return {
        "result": result,
        "steps": [
            "检查矩阵是否为仅含 0/1 的方阵。",
            "检查主对角线以判断自反性与反自反性。",
            "比较转置位置以判断对称性与反对称性。",
            "枚举三元组检查传递性。",
        ],
        "explanation": "关系矩阵中的 1 表示对应有序对属于该关系。",
    }


@router.post("/formula-simplify")
def formula_simplify(request: FormulaToolRequest) -> dict[str, Any]:
    return _run_tool(simplify_formula, expression=request.params.expression)


@router.post("/normal-forms")
def normal_forms(request: FormulaToolRequest) -> dict[str, Any]:
    return _run_tool(convert_normal_forms, expression=request.params.expression)


@router.post("/set-operation")
def set_operation(request: SetOperationRequest) -> dict[str, Any]:
    return _run_tool(calculate_set_operation, **request.params.model_dump())


@router.post("/hasse-diagram")
def hasse_diagram(request: HasseDiagramRequest) -> dict[str, Any]:
    return _run_tool(generate_hasse_diagram, **request.params.model_dump())


@router.post("/dijkstra")
def dijkstra(request: DijkstraRequest) -> dict[str, Any]:
    return _run_tool(dijkstra_shortest_path, **request.params.model_dump())


@router.post("/bipartite")
def bipartite(request: BipartiteRequest) -> dict[str, Any]:
    return _run_tool(check_bipartite, matrix=request.params.matrix)


@router.post("/code-generate")
def code_generate(request: CodeGenerationRequest) -> dict[str, Any]:
    return _run_tool(generate_discrete_math_code, **request.params.model_dump())


class UnifiedToolRequest(BaseModel):
    tool: str
    params: dict[str, Any]


@router.post("/run", summary="统一执行算法工具")
def run_unified_tool(request: UnifiedToolRequest) -> dict[str, Any]:
    """Execute any registered algorithm through one stable endpoint."""

    handlers = {
        "truth-table": (FormulaToolRequest, truth_table),
        "relation-properties": (RelationToolRequest, relation_properties),
        "formula-simplify": (FormulaToolRequest, formula_simplify),
        "normal-forms": (FormulaToolRequest, normal_forms),
        "set-operation": (SetOperationRequest, set_operation),
        "hasse-diagram": (HasseDiagramRequest, hasse_diagram),
        "dijkstra": (DijkstraRequest, dijkstra),
        "bipartite": (BipartiteRequest, bipartite),
        "code-generate": (CodeGenerationRequest, code_generate),
    }
    handler_entry = handlers.get(request.tool)
    if handler_entry is None:
        raise HTTPException(status_code=404, detail=f"未知算法工具: {request.tool}")

    request_model, handler = handler_entry
    try:
        validated_request = request_model(params=request.params)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return handler(validated_request)
