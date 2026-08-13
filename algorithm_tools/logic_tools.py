from __future__ import annotations

from itertools import combinations, product
from typing import Any

from algorithm_tools.common import tool_response
from algorithm_tools.truth_table import collect_variables, evaluate, parse_expression


MAX_LOGIC_VARIABLES = 10
Pattern = tuple[int | None, ...]


def _truth_rows(expression: str) -> tuple[list[str], list[tuple[tuple[bool, ...], bool]]]:
    ast = parse_expression(expression)
    variables = collect_variables(ast)
    if len(variables) > MAX_LOGIC_VARIABLES:
        raise ValueError(f"at most {MAX_LOGIC_VARIABLES} variables are supported")

    rows = []
    for values in product([False, True], repeat=len(variables)):
        assignment = dict(zip(variables, values))
        rows.append((values, evaluate(ast, assignment)))
    return variables, rows


def _literal(variable: str, value: bool) -> str:
    return variable if value else f"not {variable}"


def _canonical_dnf(variables: list[str], rows: list[tuple[tuple[bool, ...], bool]]) -> str:
    true_rows = [values for values, result in rows if result]
    if not true_rows:
        return "false"
    if len(true_rows) == len(rows):
        return "true"
    terms = [" and ".join(_literal(var, value) for var, value in zip(variables, values)) for values in true_rows]
    return " or ".join(f"({term})" for term in terms)


def _canonical_cnf(variables: list[str], rows: list[tuple[tuple[bool, ...], bool]]) -> str:
    false_rows = [values for values, result in rows if not result]
    if not false_rows:
        return "true"
    if len(false_rows) == len(rows):
        return "false"
    clauses = [
        " or ".join(_literal(var, not value) for var, value in zip(variables, values))
        for values in false_rows
    ]
    return " and ".join(f"({clause})" for clause in clauses)


def convert_normal_forms(expression: str) -> dict[str, Any]:
    variables, rows = _truth_rows(expression)
    minterms = [index for index, (_, result) in enumerate(rows) if result]
    maxterms = [index for index, (_, result) in enumerate(rows) if not result]
    result = {
        "expression": expression,
        "variables": variables,
        "principal_dnf": _canonical_dnf(variables, rows),
        "principal_cnf": _canonical_cnf(variables, rows),
        "minterm_indices": minterms,
        "maxterm_indices": maxterms,
    }
    steps = [
        f"识别命题变量：{', '.join(variables) if variables else '无'}。",
        f"枚举 {len(rows)} 种真值指派。",
        f"取结果为真的行构造主析取范式，极小项编号为 {minterms}。",
        f"取结果为假的行构造主合取范式，极大项编号为 {maxterms}。",
    ]
    return tool_response(result, steps, "主范式由完整真值表唯一确定（仅项的排列次序可能不同）。")


def _combine_patterns(left: Pattern, right: Pattern) -> Pattern | None:
    difference = -1
    for index, (a, b) in enumerate(zip(left, right)):
        if a == b:
            continue
        if a is None or b is None or difference != -1:
            return None
        difference = index
    if difference == -1:
        return None
    combined = list(left)
    combined[difference] = None
    return tuple(combined)


def _prime_implicants(minterms: list[int], variable_count: int) -> dict[Pattern, set[int]]:
    current: dict[Pattern, set[int]] = {
        tuple((number >> (variable_count - index - 1)) & 1 for index in range(variable_count)): {number}
        for number in minterms
    }
    primes: dict[Pattern, set[int]] = {}

    while current:
        used: set[Pattern] = set()
        combined: dict[Pattern, set[int]] = {}
        items = list(current.items())
        for (left, left_cover), (right, right_cover) in combinations(items, 2):
            pattern = _combine_patterns(left, right)
            if pattern is not None:
                used.update((left, right))
                combined.setdefault(pattern, set()).update(left_cover | right_cover)
        for pattern, cover in current.items():
            if pattern not in used:
                primes.setdefault(pattern, set()).update(cover)
        current = combined
    return primes


def _select_implicants(primes: dict[Pattern, set[int]], minterms: list[int]) -> list[Pattern]:
    remaining = set(minterms)
    selected: list[Pattern] = []

    while True:
        essential: list[Pattern] = []
        for minterm in remaining:
            candidates = [pattern for pattern, cover in primes.items() if minterm in cover]
            if len(candidates) == 1 and candidates[0] not in selected:
                essential.append(candidates[0])
        if not essential:
            break
        for pattern in essential:
            if pattern not in selected:
                selected.append(pattern)
                remaining -= primes[pattern]

    if not remaining:
        return selected

    candidates = [pattern for pattern in primes if pattern not in selected and primes[pattern] & remaining]
    best: tuple[int, int, tuple[str, ...], tuple[Pattern, ...]] | None = None
    for size in range(1, len(candidates) + 1):
        for choice in combinations(candidates, size):
            covered = set().union(*(primes[pattern] for pattern in choice))
            if not remaining <= covered:
                continue
            literal_count = sum(sum(bit is not None for bit in pattern) for pattern in choice)
            score = (size, literal_count, tuple(map(str, choice)), choice)
            if best is None or score[:3] < best[:3]:
                best = score
        if best is not None:
            break
    return selected + list(best[3] if best else ())


def _pattern_to_term(pattern: Pattern, variables: list[str]) -> str:
    literals = [
        _literal(variable, bool(bit))
        for variable, bit in zip(variables, pattern)
        if bit is not None
    ]
    return " and ".join(literals) if literals else "true"


def simplify_formula(expression: str) -> dict[str, Any]:
    variables, rows = _truth_rows(expression)
    minterms = [index for index, (_, result) in enumerate(rows) if result]

    if not minterms:
        simplified = "false"
        implicants: list[str] = []
    elif len(minterms) == len(rows):
        simplified = "true"
        implicants = ["true"]
    else:
        primes = _prime_implicants(minterms, len(variables))
        selected = _select_implicants(primes, minterms)
        implicants = [_pattern_to_term(pattern, variables) for pattern in selected]
        simplified = " or ".join(f"({term})" if " and " in term else term for term in implicants)

    result = {
        "original": expression,
        "simplified": simplified,
        "form": "minimal_dnf",
        "variables": variables,
        "implicants": implicants,
    }
    steps = [
        f"解析公式并识别变量：{', '.join(variables) if variables else '无'}。",
        f"由真值表得到结果为真的极小项：{minterms}。",
        "使用 Quine-McCluskey 合并仅有一个变量不同的项。",
        f"选择覆盖全部极小项且项数、文字数尽量少的组合：{simplified}。",
    ]
    return tool_response(result, steps, "结果以最小析取范式表示，并通过原公式真值表构造。")
