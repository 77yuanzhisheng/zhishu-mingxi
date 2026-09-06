from __future__ import annotations

import re
from functools import lru_cache


# A LaTeX command and all of its braced/bracketed arguments are protected as
# one span. This keeps both command names and text such as ``\\text{并且}``
# byte-for-byte unchanged during natural-language normalization.
_LATEX_COMMAND = re.compile(r"\\(?:[A-Za-z]+|[^A-Za-z\s])")
_MATH_ATOM = r"A-Za-z0-9_\)\]\}∈∉⊆⊂ᶜ"
_MATH_ATOM_WITH_OPEN = r"A-Za-z0-9_\(（∀∃¬"


_SYMBOL_ENTRIES: tuple[dict[str, str], ...] = (
    {"symbol": "∀", "meaning": "任意、对所有", "category": "logic", "latex": r"\forall"},
    {"symbol": "∃", "meaning": "存在", "category": "logic", "latex": r"\exists"},
    {"symbol": "¬", "meaning": "非、否定", "category": "logic", "latex": r"\neg"},
    {"symbol": "∧", "meaning": "且、合取", "category": "logic", "latex": r"\land"},
    {"symbol": "∨", "meaning": "或、析取", "category": "logic", "latex": r"\lor"},
    {"symbol": "→", "meaning": "推出、蕴含", "category": "logic", "latex": r"\to"},
    {"symbol": "↔", "meaning": "当且仅当、等价", "category": "logic", "latex": r"\leftrightarrow"},
    {"symbol": "∈", "meaning": "属于", "category": "set", "latex": r"\in"},
    {"symbol": "∉", "meaning": "不属于", "category": "set", "latex": r"\notin"},
    {"symbol": "⊆", "meaning": "子集、包含于", "category": "set", "latex": r"\subseteq"},
    {"symbol": "⊂", "meaning": "真子集", "category": "set", "latex": r"\subset"},
    {"symbol": "∪", "meaning": "并集", "category": "set", "latex": r"\cup"},
    {"symbol": "∩", "meaning": "交集", "category": "set", "latex": r"\cap"},
    {"symbol": "\\", "meaning": "集合差", "category": "set", "latex": r"\setminus"},
    {"symbol": "ᶜ", "meaning": "补集", "category": "set", "latex": r"^c"},
    {"symbol": "R", "meaning": "二元关系", "category": "relation", "latex": "R"},
    {"symbol": "aRb", "meaning": "a 与 b 满足关系 R", "category": "relation", "latex": "aRb"},
    {"symbol": "f: A → B", "meaning": "从 A 到 B 的函数 f", "category": "function", "latex": r"f: A \to B"},
    {"symbol": "V", "meaning": "图的顶点集", "category": "graph", "latex": "V"},
    {"symbol": "E", "meaning": "图的边集", "category": "graph", "latex": "E"},
    {"symbol": "deg(v)", "meaning": "顶点 v 的度数", "category": "graph", "latex": r"\deg(v)"},
)

# Longest phrases are applied first. Ambiguous one-character aliases such as
# bare "并"/"交"/"差"/"或" are intentionally absent: they corrupt ordinary
# words (例如“差错”“交代”“或者”).
_EXACT_ALIASES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            ("当且仅当", "↔"),
            ("等价于", "↔"),
            ("逻辑蕴含", "→"),
            ("蕴含关系", "→"),
            ("推出", "→"),
            ("不属于", "∉"),
            ("包含于", "⊆"),
            ("真子集", "⊂"),
            ("并集", "∪"),
            ("交集", "∩"),
            ("差集", "\\"),
            ("集合差", "\\"),
            ("补集", "ᶜ"),
            ("的补", "ᶜ"),
            ("逻辑非", "¬"),
            ("否定", "¬"),
            ("逻辑且", "∧"),
            ("并且", "∧"),
            ("合取", "∧"),
            ("逻辑或", "∨"),
            ("析取", "∨"),
            ("任意", "∀"),
            ("对所有", "∀"),
            ("存在", "∃"),
            ("有一个", "∃"),
            ("属于", "∈"),
            ("子集", "⊆"),
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)


def _consume_balanced(text: str, start: int) -> int:
    pairs = {"{": "}", "[": "]"}
    opening = text[start]
    closing = pairs[opening]
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "\\":
            # Escaped braces do not affect argument nesting.
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    return len(text)


def _latex_span_end(text: str, start: int) -> int:
    match = _LATEX_COMMAND.match(text, start)
    if match is None:
        return start + 1

    end = match.end()
    cursor = end
    while cursor < len(text):
        if text[cursor].isspace():
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
        if cursor < len(text) and text[cursor] in "{[":
            cursor = _consume_balanced(text, cursor)
            end = cursor
            continue
        return end
    return end


def _iter_latex_spans(text: str):
    cursor = 0
    while cursor < len(text):
        slash = text.find("\\", cursor)
        if slash < 0:
            return
        end = _latex_span_end(text, slash)
        yield slash, end
        cursor = max(end, slash + 1)


def _normalize_plain_text(text: str) -> str:
    for source, target in _EXACT_ALIASES:
        text = text.replace(source, target)

    # Unary negation is normalized only when followed by a math-like operand;
    # this avoids changing ordinary words such as “非法” or “非线性”.
    text = re.sub(
        rf"非(?=\s*[{_MATH_ATOM_WITH_OPEN}])",
        "¬",
        text,
    )
    # Binary conjunction/disjunction are normalized only between math-like
    # operands, while preserving the user's surrounding whitespace.
    text = re.sub(
        rf"(?<=[{_MATH_ATOM}])([ \t]*)且([ \t]*)(?=[{_MATH_ATOM_WITH_OPEN}])",
        r"\1∧\2",
        text,
    )
    text = re.sub(
        rf"(?<=[{_MATH_ATOM}])([ \t]*)或([ \t]*)(?=[{_MATH_ATOM_WITH_OPEN}])",
        r"\1∨\2",
        text,
    )
    text = text.replace("<->", "↔").replace("->", "→")
    return text


def normalize_symbols(text: str) -> str:
    """Normalize mathematical aliases while preserving complete LaTeX spans."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    parts: list[str] = []
    cursor = 0
    for start, end in _iter_latex_spans(text):
        parts.append(_normalize_plain_text(text[cursor:start]))
        parts.append(text[start:end])
        cursor = end
    parts.append(_normalize_plain_text(text[cursor:]))
    return "".join(parts)


@lru_cache(maxsize=1)
def _cached_symbol_table() -> dict[str, dict[str, str]]:
    return {entry["symbol"]: dict(entry) for entry in _SYMBOL_ENTRIES}


def symbol_table() -> dict[str, dict[str, str]]:
    """Return a copy of the canonical discrete-mathematics symbol table."""
    return {symbol: dict(entry) for symbol, entry in _cached_symbol_table().items()}
