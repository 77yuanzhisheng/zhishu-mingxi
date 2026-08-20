# -*- coding: utf-8 -*-
"""
vision.py — 让文本模型"看图"的桥接脚本
======================================
用法:
    python scripts/vision.py <图片路径> [问题] [--model 模型名]

原理:
    本环境主模型不支持图像输入，本脚本将图片 base64 编码后发给
    SiliconFlow 视觉大模型(Qwen2.5-VL)，把图片内容转成详细文字描述，
    供文本模型基于描述继续工作。

示例:
    python scripts/vision.py data/vision_test.png "描述这张图片"
    python scripts/vision.py screenshot.png "这个页面有哪些元素？布局如何？"
    python scripts/vision.py 图1.png --model Qwen/Qwen2.5-VL-32B-Instruct
"""

import base64
import json
import os
import sys

from dotenv import load_dotenv
import httpx

# 允许从任意目录运行（脚本位于 scripts/ 下）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DEFAULT_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
}


def describe(image_path: str, question: str, model: str = DEFAULT_MODEL) -> str:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY（请检查 .env）")

    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = MIME.get(ext, "image/png")

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": question},
                ],
            }
        ],
        "max_tokens": 2000,
        "temperature": 0.3,
    }

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    image = sys.argv[1]
    model = DEFAULT_MODEL
    question = "请详细、准确地描述这张图片的全部内容：包括文字（逐字提取）、图形、结构、布局、颜色和任何细节。如果是界面截图，请描述每个功能区域。如果是数学图表，请描述公式和图形。"

    args = [a for a in sys.argv[2:]]
    for i, a in enumerate(args):
        if a == "--model" and i + 1 < len(args):
            model = args[i + 1]
            args = args[:i] + args[i + 2:]
            break
    if args:
        question = " ".join(args)

    try:
        result = describe(image, question, model)
        print("=" * 60)
        print(f"图片: {image}")
        print(f"模型: {model}")
        print("=" * 60)
        print(result)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
