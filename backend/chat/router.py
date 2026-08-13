from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.reasoning.service import (
    QuestionType,
    build_proof_plan,
    detect_question_type,
    evaluate_reasoning_answer,
    format_proof_plan_for_prompt,
    merge_reasoning_prompt,
    verify_symbolic_statement,
)

router = APIRouter(tags=["chat"])

DEFAULT_LLM_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
DEFAULT_LLM_MODEL = "Qwen/Qwen3-8B"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="学生问题")
    user_id: str | None = Field(default=None, description="学生 ID，供学情模块使用")
    top_k: int = Field(default=5, ge=1, le=20, description="知识库检索数量")
    min_score: float = Field(default=0.2, ge=0.0, le=1.0, description="知识库最小相似度")
    max_tokens: int | None = Field(default=None, ge=64, le=4096, description="模型最大输出 token")


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reasoning: dict[str, Any]


@dataclass(frozen=True)
class ChatPayload:
    messages: list[dict[str, str]]
    reasoning_enabled: bool
    question_type: str
    symbolic_check: Any
    proof_plan: Any


def answer_token_limit(question: str) -> int:
    question_type = detect_question_type(question)
    if question_type in {QuestionType.PROOF, QuestionType.DERIVATION, QuestionType.CALCULATION}:
        return 1400
    return 800


def request_timeout(max_tokens: int) -> int:
    return 120 if max_tokens > 800 else 60


def compact_context(text: str, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def filter_reasoning_contexts(question: str, results: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    if not results:
        return []

    question_type = detect_question_type(question)
    if question_type == QuestionType.GENERAL:
        return results[:limit]

    def source_name(item: dict[str, Any]) -> str:
        return str(item.get("metadata", {}).get("source_document", ""))

    def rank(item: dict[str, Any]) -> tuple[int, float]:
        source = source_name(item)
        score = float(item.get("score", 0.0))
        priority = 0
        if any(key in source for key in ("命题逻辑", "谓词逻辑", "集合论", "关系", "图论", "证明题库")):
            priority += 3
        if any(key in source for key in ("题库节点映射", "选择题")):
            priority -= 2
        return priority, score

    return sorted(results, key=rank, reverse=True)[:limit]


def symbolic_check_note(question: str) -> str:
    result = verify_symbolic_statement(question)
    if not result.checked:
        return ""
    status = "通过" if result.valid else "未通过"
    note = f"程序侧符号校验结果：{status}；校验方式：{result.detail}。回答中的公式、真值表或中间结论必须与该校验结果一致。"
    if result.evidence:
        note += f"\n程序侧符号证据：\n{result.evidence}"
    return note


def build_chat_payload(question: str, contexts: list[dict[str, Any]]) -> ChatPayload:
    base_system_prompt = (
        "你是离散数学智能助教，名为“知数·明析”。你的职责是帮助学生学习离散数学。\n"
        "请严格遵守以下规则：\n"
        "1. 优先根据提供的参考资料回答问题。\n"
        "2. 如果资料不足，请明确说明资料不足，并给出通用解答。\n"
        "3. 回答时尽量标注信息来源。\n"
        "4. 数学公式使用 LaTeX 格式。\n"
        "5. 对复杂概念进行分步讲解。"
    )
    system_prompt = merge_reasoning_prompt(base_system_prompt, question)
    question_type = detect_question_type(question)
    symbolic_result = verify_symbolic_statement(question)
    proof_plan = build_proof_plan(question)
    proof_plan_text = format_proof_plan_for_prompt(proof_plan)
    check_note = symbolic_check_note(question)

    context_parts = []
    for item in filter_reasoning_contexts(question, contexts, limit=3):
        metadata = item.get("metadata", {})
        src = metadata.get("source_document", "未知来源")
        chapter = metadata.get("chapter") or metadata.get("section") or ""
        page = metadata.get("page_start", "?")
        context_parts.append(f"【来源：{src}；{chapter}；第{page}页】\n{compact_context(str(item.get('content', '')))}")

    context_text = "\n\n---\n\n".join(context_parts)
    if context_text:
        user_prompt = (
            f"## 参考资料\n{context_text}\n\n"
            f"## 符号校验\n{check_note or '暂无程序侧符号校验结果。'}\n\n"
            f"## 符号证明计划\n{proof_plan_text}\n\n"
            f"## 学生问题\n{question}\n\n"
            "请根据以上参考资料回答学生的问题。"
        )
    else:
        user_prompt = (
            f"## 学生问题\n{question}\n\n"
            f"## 符号校验\n{check_note or '暂无程序侧符号校验结果。'}\n\n"
            f"## 符号证明计划\n{proof_plan_text}\n\n"
            "注意：知识库中未找到相关资料，请根据你的通用知识回答，并提醒学生资料不足。"
        )

    return ChatPayload(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        reasoning_enabled=question_type != QuestionType.GENERAL,
        question_type=question_type.value,
        symbolic_check=symbolic_result,
        proof_plan=proof_plan,
    )


async def search_knowledge(question: str, top_k: int, min_score: float) -> list[dict[str, Any]]:
    from backend.kb.router import get_retriever

    result = get_retriever().retrieve(query=question, top_k=top_k, min_score=min_score)
    return list(result.get("results", []))


async def call_llm(messages: list[dict[str, str]], max_tokens: int) -> str:
    api_key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="未配置 SILICONFLOW_API_KEY 或 OPENAI_API_KEY")

    api_url = os.getenv("LLM_API_URL", DEFAULT_LLM_API_URL)
    model = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "enable_thinking": False,
    }
    async with httpx.AsyncClient(timeout=request_timeout(max_tokens)) as client:
        try:
            response = await client.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f"LLM API 返回错误：{exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"LLM API 调用失败：{exc}") from exc
    data = response.json()
    return data["choices"][0]["message"]["content"]


def serialize_source(item: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(item.get("metadata", {}))
    return {
        "content": compact_context(str(item.get("content", "")), limit=220),
        "score": item.get("score"),
        **metadata,
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    question = request.message.strip()
    contexts = await search_knowledge(question, top_k=request.top_k, min_score=request.min_score)
    payload = build_chat_payload(question, contexts)
    max_tokens = request.max_tokens or answer_token_limit(question)
    answer = await call_llm(payload.messages, max_tokens=max_tokens)
    evaluation = evaluate_reasoning_answer(answer, question=question)

    return ChatResponse(
        answer=answer,
        sources=[serialize_source(item) for item in filter_reasoning_contexts(question, contexts, limit=3)],
        reasoning={
            "enabled": payload.reasoning_enabled,
            "question_type": payload.question_type,
            "symbolic_check": asdict(payload.symbolic_check),
            "proof_plan": asdict(payload.proof_plan),
            "evaluation": asdict(evaluation),
        },
    )
