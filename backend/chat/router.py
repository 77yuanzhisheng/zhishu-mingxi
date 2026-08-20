"""FastAPI endpoint for multi-turn RAG chat."""

import json
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.chat.exceptions import (
    ChatSessionAccessError,
    ChatSessionNotFoundError,
    ChatUserNotFoundError,
    LLMUnavailableError,
)
from backend.chat.models import ChatRequest, ChatResponse
from backend.chat.service import ChatService


router = APIRouter(tags=["多轮对话"])


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    return ChatService()


@router.post("/chat", response_model=ChatResponse, summary="多轮 RAG 对话")
def chat_endpoint(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        return service.chat(request)
    except ChatUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChatSessionAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat/stream", summary="流式多轮 RAG 对话")
def stream_chat_endpoint(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    def event_stream():
        try:
            for event in service.stream_chat(request):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except (
            ChatUserNotFoundError,
            ChatSessionNotFoundError,
            ChatSessionAccessError,
            LLMUnavailableError,
        ) as exc:
            yield json.dumps(
                {"type": "error", "detail": str(exc)}, ensure_ascii=False
            ) + "\n"
        except Exception as exc:
            yield json.dumps(
                {"type": "error", "detail": f"流式回答失败：{exc}"},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
