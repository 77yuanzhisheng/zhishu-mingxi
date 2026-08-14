"""Adapter over the existing KB recommender plus answer metadata enrichment."""

from __future__ import annotations

import re
from pathlib import Path

from backend.kb.recommender import get_recommender


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHOICE_BANK = PROJECT_ROOT / "data" / "documents" / "选择题题库.md"


def _normalize_question(text: str) -> str:
    text = re.sub(r"\*+Q\d+\**", "", text)
    return re.sub(r"[\s，。？?：:；;]", "", text).lower()


def _load_choice_answers() -> list[tuple[str, str]]:
    if not CHOICE_BANK.exists():
        return []
    content = CHOICE_BANK.read_text(encoding="utf-8")
    blocks = re.findall(
        r"\*\*Q\d+\*\*\s*(.*?)\n答案：\s*([A-D])", content, flags=re.DOTALL
    )
    return [(_normalize_question(question), answer.upper()) for question, answer in blocks]


def _resolve_choice_answer(content: str, answers: list[tuple[str, str]]) -> str | None:
    normalized = _normalize_question(content)
    for bank_question, answer in answers:
        if normalized == bank_question or normalized in bank_question or bank_question in normalized:
            return answer
    return None


def recommend_exam_questions(node_ids: list[str], count: int) -> list[dict]:
    """Reuse KB recommendations; never synthesize questions or answers."""

    recommender = get_recommender()
    answers = _load_choice_answers()
    grouped: list[list[dict]] = []
    seen: set[tuple[str, str]] = set()
    per_node = max(count, 5)
    for node_id in node_ids:
        node_questions: list[dict] = []
        for question in recommender.recommend(node_id=node_id, level=2, count=per_node):
            key = (question["node_id"], question["content"])
            if key in seen:
                continue
            seen.add(key)
            item = dict(question)
            item["answer"] = (
                _resolve_choice_answer(item["content"], answers)
                if item["type"] == "选择题"
                else None
            )
            node_questions.append(item)
        grouped.append(node_questions)

    selected: list[dict] = []
    question_index = 0
    while len(selected) < count:
        added = False
        for node_questions in grouped:
            if question_index < len(node_questions):
                selected.append(node_questions[question_index])
                added = True
                if len(selected) == count:
                    break
        if not added:
            break
        question_index += 1
    return selected[:count]
