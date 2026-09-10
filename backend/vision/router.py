"""HTTP boundary for image-to-text vision parsing."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from backend.chat.exceptions import LLMUnavailableError
from backend.vision.models import VisionParseResponse
from backend.vision.spark_vl import SparkVLClient, VisionProviderError, VisionResponseParseError, normalize_image


router = APIRouter(prefix="/api/vision", tags=["视觉识别"])

_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


@lru_cache(maxsize=1)
def get_vision_client() -> SparkVLClient:
    return SparkVLClient()


@router.post("/parse", response_model=VisionParseResponse, summary="解析题目或答案图片")
async def parse_vision_image(
    file: UploadFile = File(..., description="PNG、JPEG 或 WebP 图片，最大 10 MiB"),
) -> VisionParseResponse:
    content_type = (file.content_type or "").lower().strip()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 PNG、JPEG、WebP 图片",
        )

    try:
        image_bytes = await file.read(_MAX_IMAGE_BYTES + 1)
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE),
                detail="图片大小不能超过 10 MiB",
            )
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="图片内容不能为空",
            )
        normalized_bytes, normalized_type = await run_in_threadpool(normalize_image, image_bytes, content_type)
        return await run_in_threadpool(get_vision_client().parse, normalized_bytes, normalized_type)
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except HTTPException:
        raise
    except (VisionResponseParseError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="视觉模型返回结果无法解析",
        ) from exc
    except VisionProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="视觉识别服务调用失败",
        ) from exc
    except RuntimeError as exc:
        # Keep provider credentials, URLs, and raw upstream messages out of
        # the client response. Detailed diagnostics belong in server logs.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="视觉识别服务调用失败",
        ) from exc
