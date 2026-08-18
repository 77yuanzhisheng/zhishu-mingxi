"""Bounded conversation context and deterministic durable summarization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.chat.repository import ChatRepository


COMPRESSION_AFTER_ROUNDS = 10
RECENT_ROUNDS_TO_KEEP = 4
MAX_HISTORY_MESSAGES = RECENT_ROUNDS_TO_KEEP * 2
MAX_UNCOMPRESSED_MESSAGES = COMPRESSION_AFTER_ROUNDS * 2
UNRESOLVED_MARKERS = ("？", "?", "不会", "不懂", "没明白", "为什么", "怎么")
WEAKNESS_MARKERS = ("不会", "不懂", "没明白", "易错", "困惑", "难", "忘了", "薄弱")


@dataclass
class PreparedContext:
    messages: list[dict[str, str]]
    total_rounds: int
    compressed: bool
    summary_available: bool


def _shorten(text: str, limit: int = 160) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean if len(clean) <= limit else f"{clean[:limit]}…"


def build_summary(previous_summary: str | None, messages: list[dict[str, Any]]) -> str:
    """Build a structured summary without requiring a second LLM call."""

    node_ids: list[str] = []
    concepts: list[str] = []
    weaknesses: list[str] = []
    unresolved: list[str] = []
    for message in messages:
        for node_id in message["node_ids"]:
            if node_id not in node_ids:
                node_ids.append(node_id)
        excerpt = _shorten(message["content"])
        if message["role"] == "assistant":
            concepts.append(excerpt)
        elif any(marker in message["content"] for marker in WEAKNESS_MARKERS):
            weaknesses.append(excerpt)
        if message["role"] == "user" and any(
            marker in message["content"] for marker in UNRESOLVED_MARKERS
        ):
            unresolved.append(excerpt)

    sections = []
    if previous_summary:
        sections.append(f"既有摘要：{_shorten(previous_summary, 500)}")
    sections.extend(
        [
            f"正在学习的知识点：{', '.join(node_ids) if node_ids else '未明确标注'}",
            f"已讨论的重要概念：{'；'.join(concepts[-5:]) if concepts else '暂无'}",
            f"用户暴露的薄弱点：{'；'.join(weaknesses[-4:]) if weaknesses else '暂无明确记录'}",
            f"仍未解决的问题：{'；'.join(unresolved[-4:]) if unresolved else '暂无明确记录'}",
        ]
    )
    return "\n".join(sections)


def prepare_context(repository: ChatRepository, session_id: int) -> PreparedContext:
    all_messages = repository.get_messages(session_id)
    total_rounds = sum(message["role"] == "user" for message in all_messages)
    summary = repository.get_summary(session_id)
    compressed = False

    if total_rounds > COMPRESSION_AFTER_ROUNDS:
        recent_start = max(0, len(all_messages) - MAX_HISTORY_MESSAGES)
        older_messages = all_messages[:recent_start]
        previous_through = summary["summarized_through_message_id"] if summary else 0
        new_messages = [message for message in older_messages if message["id"] > previous_through]
        if new_messages:
            summary_content = build_summary(summary["content"] if summary else None, new_messages)
            repository.save_summary(session_id, summary_content, older_messages[-1]["id"])
            summary = repository.get_summary(session_id)
            compressed = True

    summary_through = summary["summarized_through_message_id"] if summary else 0
    raw_messages = [message for message in all_messages if message["id"] > summary_through]
    history_limit = MAX_HISTORY_MESSAGES if summary else MAX_UNCOMPRESSED_MESSAGES
    raw_messages = raw_messages[-history_limit:]
    context_messages: list[dict[str, str]] = []
    if summary:
        context_messages.append(
            {"role": "system", "content": f"以下是较早对话的结构化摘要：\n{summary['content']}"}
        )
    context_messages.extend(
        {"role": message["role"], "content": message["content"]}
        for message in raw_messages
        if message["role"] in {"user", "assistant"}
    )
    return PreparedContext(
        messages=context_messages,
        total_rounds=total_rounds,
        compressed=compressed,
        summary_available=summary is not None,
    )
