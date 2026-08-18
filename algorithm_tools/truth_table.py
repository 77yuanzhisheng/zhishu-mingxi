from __future__ import annotations

from itertools import product
import re
from typing import NamedTuple


TOKEN_PATTERN = re.compile(r"<->|<=>|->|=>|[()~!&|^]|[A-Za-z][A-Za-z0-9_]*")

UNARY_OPERATORS = {"not", "~", "!"}
BINARY_OPERATORS = {
    "<->": 1,
    "<=>": 1,
    "->": 2,
    "=>": 2,
    "or": 3,
    "|": 3,
    "xor": 4,
    "^": 4,
    "and": 5,
    "&": 5,
}
RIGHT_ASSOCIATIVE = {"->", "=>"}
RESERVED_WORDS = {"and", "or", "not", "xor", "true", "false"}


class Token(NamedTuple):
    kind: str
    value: str


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0

    def parse(self) -> tuple:
        if not self.tokens:
            raise ValueError("expression must not be empty")

        node = self._parse_expression(0)
        if self._current() is not None:
            raise ValueError(f"unexpected token: {self._current().value}")
        return node

    def _parse_expression(self, min_precedence: int) -> tuple:
        left = self._parse_prefix()

        while True:
            token = self._current()
            if token is None or token.kind != "operator" or token.value in UNARY_OPERATORS:
                break

            precedence = BINARY_OPERATORS[token.value]
            if precedence < min_precedence:
                break

            self._advance()
            next_min = precedence if token.value in RIGHT_ASSOCIATIVE else precedence + 1
            right = self._parse_expression(next_min)
            left = ("binary", token.value, left, right)

        return left

    def _parse_prefix(self) -> tuple:
        token = self._current()
        if token is None:
            raise ValueError("expression ended unexpectedly")

        if token.kind == "operator" and token.value in UNARY_OPERATORS:
            self._advance()
            return ("not", self._parse_expression(6))

        if token.kind == "literal":
            self._advance()
            return ("literal", token.value == "true")

        if token.kind == "variable":
            self._advance()
            return ("variable", token.value)

        if token.value == "(":
            self._advance()
            node = self._parse_expression(0)
            if self._current() is None or self._current().value != ")":
                raise ValueError("missing closing parenthesis")
            self._advance()
            return node

        raise ValueError(f"unexpected token: {token.value}")

    def _current(self) -> Token | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def _advance(self) -> None:
        self.position += 1


def tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0

    for match in TOKEN_PATTERN.finditer(expression):
        if expression[position : match.start()].strip():
            raise ValueError(f"invalid token near: {expression[position:match.start()]}")

        raw_value = match.group(0)
        value = raw_value.lower()

        if value in {"true", "false"}:
            tokens.append(Token("literal", value))
        elif value in UNARY_OPERATORS or value in BINARY_OPERATORS:
            tokens.append(Token("operator", value))
        elif raw_value in {"(", ")"}:
            tokens.append(Token("parenthesis", raw_value))
        elif value in RESERVED_WORDS:
            raise ValueError(f"reserved word cannot be used as variable: {raw_value}")
        else:
            tokens.append(Token("variable", raw_value))

        position = match.end()

    if expression[position:].strip():
        raise ValueError(f"invalid token near: {expression[position:]}")

    return tokens


def parse_expression(expression: str) -> tuple:
    return Parser(tokenize(expression)).parse()


def collect_variables(node: tuple) -> list[str]:
    variables: set[str] = set()

    def visit(current: tuple) -> None:
        if current[0] == "variable":
            variables.add(current[1])
        elif current[0] == "not":
            visit(current[1])
        elif current[0] == "binary":
            visit(current[2])
            visit(current[3])

    visit(node)
    return sorted(variables)


def evaluate(node: tuple, values: dict[str, bool]) -> bool:
    node_type = node[0]

    if node_type == "literal":
        return node[1]
    if node_type == "variable":
        return values[node[1]]
    if node_type == "not":
        return not evaluate(node[1], values)

    operator = node[1]
    left = evaluate(node[2], values)
    right = evaluate(node[3], values)

    if operator in {"and", "&"}:
        return left and right
    if operator in {"or", "|"}:
        return left or right
    if operator in {"xor", "^"}:
        return left != right
    if operator in {"->", "=>"}:
        return (not left) or right
    if operator in {"<->", "<=>"}:
        return left == right

    raise ValueError(f"unsupported operator: {operator}")


def generate_truth_table(expression: str) -> dict:
    ast = parse_expression(expression)
    variables = collect_variables(ast)
    rows = []

    for combination in product([False, True], repeat=len(variables)):
        values = dict(zip(variables, combination))
        rows.append(
            {
                "values": values,
                "result": evaluate(ast, values),
            }
        )

    return {
        "expression": expression,
        "variables": variables,
        "rows": rows,
    }
