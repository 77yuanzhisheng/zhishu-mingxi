from __future__ import annotations

from typing import Any, Literal, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from algorithm_tools.code_generator import generate_discrete_math_code
from algorithm_tools.graph_tools import check_bipartite, dijkstra_shortest_path, generate_hasse_diagram
from algorithm_tools.logic_tools import convert_normal_forms, simplify_formula
from algorithm_tools.relation import analyze_relation
from algorithm_tools.set_tools import calculate_set_operation
from algorithm_tools.truth_table import generate_truth_table


router = APIRouter(prefix="/tools", tags=["Extended Tools"])


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
