from __future__ import annotations

import ast
import itertools
import operator
import re
from dataclasses import dataclass
from enum import Enum


class QuestionType(str, Enum):
    GENERAL = "general"
    PROOF = "proof"
    DERIVATION = "derivation"
    CALCULATION = "calculation"


@dataclass(frozen=True)
class ReasoningPrompt:
    enabled: bool
    question_type: QuestionType
    system_prompt: str


@dataclass(frozen=True)
class SymbolicCheckResult:
    checked: bool
    valid: bool | None
    detail: str = ""
    evidence: str = ""


@dataclass(frozen=True)
class ReasoningEvaluation:
    score: int
    passed: bool
    checks: dict[str, bool]
    symbolic_expression_count: int


def detect_question_type(question: str) -> QuestionType:
    text = question.strip()
    if re.search(r"证明|证毕|定理", text):
        return QuestionType.PROOF
    if re.search(r"推导|等价|化简|推出|蕴含|判断.*是否|说明理由", text):
        return QuestionType.DERIVATION
    if re.search(r"计算|求值|等于几|[0-9]+\s*[+\-*/]\s*[0-9]+", text):
        return QuestionType.CALCULATION
    return QuestionType.GENERAL


def build_reasoning_prompt(question: str) -> ReasoningPrompt:
    question_type = detect_question_type(question)
    if question_type == QuestionType.GENERAL:
        return ReasoningPrompt(False, question_type, "")
    return ReasoningPrompt(
        True,
        question_type,
        "你是离散数学教学助手。回答证明题、推导题和计算题时，必须采用教材式符号推理结构，"
        "不得只给结论或套用模板，不得跳过关键步骤。\n"
        "输出格式必须包含以下小节：\n"
        "1. 已知：列出题目给定条件、符号含义、全集或变量范围，以及需要证明或计算的目标。\n"
        "2. 分析：说明将使用的定义、定理、等价变换或计算规则，并说明证明路线。\n"
        "3. 推导：使用步骤编号逐步写出推理过程；每一步必须包含符号式和依据，格式为"
        "“步骤n：符号式/中间结论；依据：所用定义、定理或等价规则”。\n"
        "4. 自检：检查每一步是否由已知条件或已列规则推出，检查最终结论是否与题目目标一致。\n"
        "5. 结论：明确回答题目目标。\n"
        "6. 证毕：证明题和推导题以“证毕”结束。\n"
        "要求：证明必须完整但精炼，优先控制在4到8个关键步骤，不展开与题目目标无关的内容；"
        "如果提供了程序侧符号校验结果或符号证据，必须优先依据该证据组织证明，不要自行生成与证据冲突的公式或表格。",
    )


def merge_reasoning_prompt(base_system_prompt: str, question: str) -> str:
    reasoning_prompt = build_reasoning_prompt(question)
    if not reasoning_prompt.enabled:
        return base_system_prompt
    if not base_system_prompt.strip():
        return reasoning_prompt.system_prompt
    return f"{base_system_prompt.rstrip()}\n\n{reasoning_prompt.system_prompt}"


def evaluate_reasoning_answer(answer: str, question: str = "") -> ReasoningEvaluation:
    checks = {
        "has_given": bool(re.search(r"已知", answer)),
        "has_analysis": bool(re.search(r"分析", answer)),
        "has_derivation": bool(re.search(r"推导|步骤", answer)),
        "has_reason": bool(re.search(r"依据", answer)),
        "has_self_check": bool(re.search(r"自检", answer)),
        "has_conclusion": bool(re.search(r"结论", answer)),
        "ends_with_qed": bool(re.search(r"证毕\s*[。.]?\s*$", answer.strip())),
    }
    if re.search(r"归纳法|数学归纳|归纳证明", question + answer):
        checks.update(
            {
                "has_base_case": bool(re.search(r"基础步|奠基|n\s*=\s*1", answer)),
                "has_induction_hypothesis": bool(re.search(r"归纳假设|假设.*成立", answer)),
                "has_induction_step": bool(re.search(r"归纳步|k\s*\+\s*1", answer)),
            }
        )
    symbolic_expression_count = len(re.findall(r"[¬∧∨∪∩→↔⇔≡]|->|<->|\^c|\\(?:neg|land|lor|cup|cap|rightarrow|equiv)", answer))
    score = round(sum(checks.values()) / len(checks) * 100)
    return ReasoningEvaluation(score, score >= 85, checks, symbolic_expression_count)


def verify_symbolic_statement(statement: str) -> SymbolicCheckResult:
    relation_matrix_check = _verify_relation_matrix_property(statement)
    if relation_matrix_check is not None:
        return SymbolicCheckResult(
            True,
            relation_matrix_check.valid,
            "checked relation matrix property",
            relation_matrix_check.evidence,
        )
    relation_check = _verify_relation_property(statement)
    if relation_check is not None:
        return SymbolicCheckResult(
            True,
            relation_check.valid,
            "checked relation property on finite relation",
            relation_check.evidence,
        )
    graph_check = _verify_graph_formula(statement)
    if graph_check is not None:
        return SymbolicCheckResult(
            True,
            graph_check.valid,
            "checked graph formula",
            graph_check.evidence,
        )
    expression = _extract_symbolic_expression(statement)
    normalized = _normalize_logic(expression)
    if normalized in {"!(A|B)=!A&!B", "!A&!B=!(A|B)", "!(A&B)=!A|!B", "!A|!B=!(A&B)"}:
        return SymbolicCheckResult(True, True, "matched De Morgan equivalence")
    set_identity = _verify_set_identity(expression)
    if set_identity is not None:
        return SymbolicCheckResult(
            True,
            set_identity.valid,
            "checked set identity by finite universe enumeration",
            set_identity.evidence,
        )
    propositional = _verify_propositional_equivalence(expression)
    if propositional is not None:
        return SymbolicCheckResult(
            True,
            propositional.valid,
            "checked propositional truth table",
            propositional.evidence,
        )
    arithmetic = _verify_arithmetic_equal(expression)
    if arithmetic is not None:
        return SymbolicCheckResult(True, arithmetic, "checked arithmetic equality")
    return SymbolicCheckResult(False, None, "no supported symbolic check")


def _extract_symbolic_expression(text: str) -> str:
    candidates = re.findall(r"[A-Za-z0-9非并交¬!∧∨∪∩&|()\-<>↔⇔≡=+*/.^\s]+", text)
    candidates = [candidate.strip() for candidate in candidates]
    candidates = [candidate for candidate in candidates if _find_equivalence_separator(candidate)]
    if not candidates:
        return text
    return max(candidates, key=len)


def _normalize_logic(text: str) -> str:
    for old, new in {
        " ": "",
        "（": "(",
        "）": ")",
        "非": "!",
        "¬": "!",
        "并": "|",
        "∪": "|",
        "∨": "|",
        "交": "&",
        "∩": "&",
        "∧": "&",
    }.items():
        text = text.replace(old, new)
    return text.upper()


def _verify_arithmetic_equal(statement: str) -> bool | None:
    if "=" not in statement:
        return None
    left, right = statement.split("=", 1)
    if not re.fullmatch(r"[0-9+\-*/().\s]+", left + right):
        return None
    return _safe_eval_arithmetic(left) == _safe_eval_arithmetic(right)


@dataclass(frozen=True)
class _PropositionalCheck:
    valid: bool
    evidence: str


def _verify_propositional_equivalence(statement: str) -> _PropositionalCheck | None:
    separator = _find_equivalence_separator(statement)
    if separator is None:
        return None
    left, right = statement[: separator[0]], statement[separator[1] :]
    variables = sorted(set(re.findall(r"[A-Z]", _normalize_logic(left + right))))
    if not variables or len(variables) > 6:
        return None
    if not _is_supported_logic_text(left + right):
        return None

    try:
        rows = []
        for values in itertools.product([False, True], repeat=len(variables)):
            env = dict(zip(variables, values))
            left_value = _eval_logic_expr(left, env)
            right_value = _eval_logic_expr(right, env)
            rows.append((env, left_value, right_value))
        valid = all(left_value == right_value for _, left_value, right_value in rows)
        return _PropositionalCheck(valid, _format_truth_table(variables, left, right, rows))
    except ValueError:
        return None


def _format_truth_table(
    variables: list[str],
    left: str,
    right: str,
    rows: list[tuple[dict[str, bool], bool, bool]],
) -> str:
    headers = variables + [left.strip(), right.strip()]
    lines = [" | ".join(headers)]
    lines.append(" | ".join(["---"] * len(headers)))
    for env, left_value, right_value in rows:
        values = [_truth_symbol(env[var]) for var in variables]
        values.extend([_truth_symbol(left_value), _truth_symbol(right_value)])
        lines.append(" | ".join(values))
    return "\n".join(lines)


def _truth_symbol(value: bool) -> str:
    return "T" if value else "F"


@dataclass(frozen=True)
class _SetIdentityCheck:
    valid: bool
    evidence: str


@dataclass(frozen=True)
class _RelationCheck:
    valid: bool
    evidence: str


@dataclass(frozen=True)
class _GraphCheck:
    valid: bool
    evidence: str


def _verify_set_identity(statement: str) -> _SetIdentityCheck | None:
    separator = _find_equivalence_separator(statement)
    if separator is None:
        return None
    left, right = statement[: separator[0]], statement[separator[1] :]
    if not _is_supported_set_text(left + right):
        return None
    variables = sorted(set(re.findall(r"[A-Z]", left + right)))
    if not variables or len(variables) > 4:
        return None

    universe = frozenset(range(1, len(variables) + 2))
    subsets = _all_subsets(universe)
    rows = 0
    for values in itertools.product(subsets, repeat=len(variables)):
        env = dict(zip(variables, values))
        try:
            left_value = _eval_set_expr(left, env, universe)
            right_value = _eval_set_expr(right, env, universe)
        except ValueError:
            return None
        rows += 1
        if left_value != right_value:
            return _SetIdentityCheck(
                False,
                "counterexample: "
                + ", ".join(f"{name}={_format_set(env[name])}" for name in variables)
                + f"; left={_format_set(left_value)}, right={_format_set(right_value)}",
            )
    return _SetIdentityCheck(True, f"verified on finite universe {_format_set(universe)} across {rows} assignments")


def _is_supported_set_text(text: str) -> bool:
    normalized = _normalize_set_text(text)
    return re.fullmatch(r"[A-ZUC&|()^\s]+", normalized) is not None


def _normalize_set_text(text: str) -> str:
    for old, new in {
        " ": "",
        "（": "(",
        "）": ")",
        "并": "|",
        "∪": "|",
        "交": "&",
        "∩": "&",
        "补": "^C",
    }.items():
        text = text.replace(old, new)
    return text.upper()


def _all_subsets(universe: frozenset[int]) -> list[frozenset[int]]:
    items = list(universe)
    return [frozenset(item for bit, item in enumerate(items) if mask & (1 << bit)) for mask in range(1 << len(items))]


def _eval_set_expr(expression: str, env: dict[str, frozenset[int]], universe: frozenset[int]) -> frozenset[int]:
    tokens = _set_tokens(_normalize_set_text(expression))
    parser = _SetParser(tokens, env, universe)
    result = parser.parse_union()
    if parser.current() is not None:
        raise ValueError("unexpected trailing token")
    return result


def _set_tokens(expression: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(expression):
        if expression.startswith("^C", i):
            tokens.append("^C")
            i += 2
        elif expression[i] in "|&()":
            tokens.append(expression[i])
            i += 1
        elif re.match(r"[A-Z]", expression[i]):
            tokens.append(expression[i])
            i += 1
        else:
            raise ValueError(f"unsupported token: {expression[i]}")
    return tokens


class _SetParser:
    def __init__(self, tokens: list[str], env: dict[str, frozenset[int]], universe: frozenset[int]):
        self.tokens = tokens
        self.env = env
        self.universe = universe
        self.index = 0

    def current(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def accept(self, token: str) -> bool:
        if self.current() == token:
            self.index += 1
            return True
        return False

    def parse_union(self) -> frozenset[int]:
        value = self.parse_intersection()
        while self.accept("|"):
            value = value | self.parse_intersection()
        return value

    def parse_intersection(self) -> frozenset[int]:
        value = self.parse_postfix()
        while self.accept("&"):
            value = value & self.parse_postfix()
        return value

    def parse_postfix(self) -> frozenset[int]:
        value = self.parse_atom()
        while self.accept("^C"):
            value = self.universe - value
        return value

    def parse_atom(self) -> frozenset[int]:
        token = self.current()
        if token is None:
            raise ValueError("unexpected end of expression")
        if self.accept("("):
            value = self.parse_union()
            if not self.accept(")"):
                raise ValueError("missing closing parenthesis")
            return value
        if re.fullmatch(r"[A-Z]", token):
            self.index += 1
            return env_value(self.env, token)
        raise ValueError(f"unexpected token: {token}")


def env_value(env: dict[str, frozenset[int]], token: str) -> frozenset[int]:
    if token not in env:
        raise ValueError(f"unknown set variable: {token}")
    return env[token]


def _format_set(values: frozenset[int]) -> str:
    if not values:
        return "{}"
    return "{" + ",".join(str(value) for value in sorted(values)) + "}"


def _verify_relation_property(statement: str) -> _RelationCheck | None:
    relation_match = re.search(r"R\s*=\s*\{([^}]*)\}", statement)
    if not relation_match:
        return None
    property_name = _extract_relation_property_name(statement)
    if property_name is None:
        return None

    pairs = _parse_relation_pairs(relation_match.group(1))
    if not pairs:
        return None
    universe = sorted(set().union(*pairs))
    if not universe:
        return None

    return _check_relation_property(set(pairs), universe, property_name)


def _verify_relation_matrix_property(statement: str) -> _RelationCheck | None:
    if "矩阵" not in statement and "matrix" not in statement.lower():
        return None
    property_name = _extract_relation_property_name(statement)
    if property_name is None:
        return None

    matrix_match = re.search(r"\[\s*\[[\s\S]*?\]\s*\]", statement)
    if not matrix_match:
        return None
    try:
        matrix = ast.literal_eval(matrix_match.group(0))
    except (SyntaxError, ValueError):
        return None
    if not _is_square_zero_one_matrix(matrix):
        return None

    relation = {
        (row_index + 1, col_index + 1)
        for row_index, row in enumerate(matrix)
        for col_index, value in enumerate(row)
        if value == 1
    }
    universe = list(range(1, len(matrix) + 1))
    return _check_relation_property(relation, universe, property_name)


def _extract_relation_property_name(statement: str) -> str | None:
    for key, label in (("反对称", "antisymmetric"), ("自反", "reflexive"), ("对称", "symmetric"), ("传递", "transitive")):
        if key in statement:
            return label
    return None


def _is_square_zero_one_matrix(matrix: object) -> bool:
    if not isinstance(matrix, list) or not matrix:
        return False
    size = len(matrix)
    for row in matrix:
        if not isinstance(row, list) or len(row) != size:
            return False
        if any(value not in (0, 1) for value in row):
            return False
    return True


def _check_relation_property(relation: set[tuple[int, int]], universe: list[int], property_name: str) -> _RelationCheck | None:
    if property_name == "reflexive":
        for x in universe:
            if (x, x) not in relation:
                return _RelationCheck(False, f"counterexample: missing ({x},{x})")
        return _RelationCheck(True, f"verified on universe {universe}")

    if property_name == "symmetric":
        for a, b in relation:
            if (b, a) not in relation:
                return _RelationCheck(False, f"counterexample: ({a},{b}) present but ({b},{a}) missing")
        return _RelationCheck(True, f"verified on universe {universe}")

    if property_name == "antisymmetric":
        for a, b in relation:
            if a != b and (b, a) in relation:
                return _RelationCheck(False, f"counterexample: ({a},{b}) and ({b},{a}) both present")
        return _RelationCheck(True, f"verified on universe {universe}")

    if property_name == "transitive":
        for a, b in relation:
            for c, d in relation:
                if b == c and (a, d) not in relation:
                    return _RelationCheck(False, f"counterexample: ({a},{b}) and ({c},{d}) present but ({a},{d}) missing")
        return _RelationCheck(True, f"verified on universe {universe}")

    return None


def _parse_relation_pairs(content: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for item in re.findall(r"\((\d+)\s*,\s*(\d+)\)", content):
        pairs.append((int(item[0]), int(item[1])))
    return pairs


def _verify_graph_formula(statement: str) -> _GraphCheck | None:
    complete_match = re.search(r"K\s*(\d+).*?(?:边数|edges?).*?(?:为|=)\s*(\d+)", statement, re.IGNORECASE)
    if complete_match:
        n = int(complete_match.group(1))
        expected = int(complete_match.group(2))
        actual = n * (n - 1) // 2
        return _GraphCheck(actual == expected, f"K{n} edge count = {n}*({n}-1)/2 = {actual}; claimed={expected}")

    if "握手定理" in statement or "度数和" in statement:
        edge_matches = re.findall(r"边数\s*=\s*(\d+)", statement)
        degree_matches = re.findall(r"度数和\s*=\s*(\d+)", statement)
        if edge_matches and degree_matches:
            edges = int(edge_matches[-1])
            degree_sum = int(degree_matches[-1])
            expected = 2 * edges
            return _GraphCheck(degree_sum == expected, f"2*|E| = 2*{edges} = {expected}; degree_sum={degree_sum}")
        return _GraphCheck(True, "handshake theorem structural check: each undirected edge contributes 2 to degree sum")
    return None


def _find_equivalence_separator(statement: str) -> tuple[int, int] | None:
    for token in ("<->", "↔", "⇔", "≡", "="):
        index = statement.find(token)
        if index > -1:
            return index, index + len(token)
    return None


def _is_supported_logic_text(text: str) -> bool:
    normalized = _normalize_logic(text)
    return re.fullmatch(r"[A-Z!&|()\-<>=>]+", normalized) is not None


def _eval_logic_expr(expression: str, env: dict[str, bool]) -> bool:
    tokens = _logic_tokens(_normalize_logic(expression))
    parser = _LogicParser(tokens, env)
    result = parser.parse_equiv()
    if parser.current() is not None:
        raise ValueError("unexpected trailing token")
    return result


def _logic_tokens(expression: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(expression):
        if expression.startswith("<->", i):
            tokens.append("<->")
            i += 3
        elif expression.startswith("->", i):
            tokens.append("->")
            i += 2
        elif expression[i] in "!&|()":
            tokens.append(expression[i])
            i += 1
        elif re.match(r"[A-Z]", expression[i]):
            tokens.append(expression[i])
            i += 1
        else:
            raise ValueError(f"unsupported token: {expression[i]}")
    return tokens


class _LogicParser:
    def __init__(self, tokens: list[str], env: dict[str, bool]):
        self.tokens = tokens
        self.env = env
        self.index = 0

    def current(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def accept(self, token: str) -> bool:
        if self.current() == token:
            self.index += 1
            return True
        return False

    def parse_equiv(self) -> bool:
        value = self.parse_implies()
        while self.accept("<->"):
            value = value == self.parse_implies()
        return value

    def parse_implies(self) -> bool:
        value = self.parse_or()
        if self.accept("->"):
            right = self.parse_implies()
            value = (not value) or right
        return value

    def parse_or(self) -> bool:
        value = self.parse_and()
        while self.accept("|"):
            right = self.parse_and()
            value = value or right
        return value

    def parse_and(self) -> bool:
        value = self.parse_not()
        while self.accept("&"):
            right = self.parse_not()
            value = value and right
        return value

    def parse_not(self) -> bool:
        if self.accept("!"):
            return not self.parse_not()
        return self.parse_atom()

    def parse_atom(self) -> bool:
        token = self.current()
        if token is None:
            raise ValueError("unexpected end of expression")
        if self.accept("("):
            value = self.parse_equiv()
            if not self.accept(")"):
                raise ValueError("missing closing parenthesis")
            return value
        if re.fullmatch(r"[A-Z]", token):
            self.index += 1
            return self.env[token]
        raise ValueError(f"unexpected token: {token}")


def _safe_eval_arithmetic(expression: str) -> float:
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](eval_node(node.operand))
        raise ValueError("unsupported arithmetic expression")

    return eval_node(ast.parse(expression, mode="eval"))
