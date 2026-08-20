# -*- coding: utf-8 -*-
"""
ocr_teacher_slides.py — 把老师教材的幻灯片图片批量 OCR 成文本（知识库素材）
=============================================================================
背景:
    老师提供的 output.rar 中 6 部分教材是 856 张课件截图（slide_images/*.png），
    图片无法直接进入文本向量知识库。本脚本用 SiliconFlow PaddleOCR-VL 视觉模型
    把每张幻灯片转成文字，按章节汇总成 Markdown 放入 data/documents/。

支持并行:
    每个章节使用独立的进度文件（scripts/ocr_progress_<章名>.json），
    可同时启动多个进程处理不同章节，互不干扰。建议 3 路并行：
      python scripts/ocr_teacher_slides.py --part 集合论,初等数论 --resume
      python scripts/ocr_teacher_slides.py --part 图论,组合数学 --resume
      python scripts/ocr_teacher_slides.py --part 代数结构,数理逻辑 --resume

参数:
    --part    章节名，逗号分隔（默认全部，按 CHAPTERS 顺序串行）
    --limit   每章最多处理张数（测试用）
    --resume  跳过已生成的进度（断点续跑）
"""

import argparse
import json
import os
import sys
import time

# 复用 vision.py 的识图能力
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
from vision import describe  # noqa: E402

WORKSPACE = os.path.dirname(BASE_DIR)
SLIDES_ROOT = os.path.join(WORKSPACE, "output_teacher")
OUT_DIR = os.path.join(BASE_DIR, "data", "documents")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
LEGACY_PROGRESS = os.path.join(SCRIPTS_DIR, "ocr_progress.json")

# 章节目录 → 知识库文档名（与现有知识库命名风格一致）
CHAPTERS = [
    ("chap1-3", "集合论"),
    ("chap4", "初等数论"),
    ("chap5-9", "图论"),
    ("chap10-11", "组合数学"),
    ("chap12-14", "代数结构"),
    ("chap15-19", "数理逻辑"),
]

PROMPT = (
    "这是一张离散数学教材课件幻灯片。请完整提取幻灯片上的全部文字内容"
    "（逐字转录，保留标题/公式符号如 ∀∃∈⊆、命题、定理、定义、例题等），"
    "如果包含图形/表格请简述其内容。只输出提取的正文，不要评论。"
)

OCR_MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"  # OCR 专用，约 1-3s/张

BATCH_WAIT = 0.5  # 请求间隔（秒），避免 SiliconFlow 限流


def progress_file(part_name: str) -> str:
    return os.path.join(SCRIPTS_DIR, f"ocr_progress_{part_name}.json")


def load_progress(part_name: str) -> list:
    try:
        with open(progress_file(part_name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        # 兼容旧版单文件进度（ocr_progress.json）
        try:
            with open(LEGACY_PROGRESS, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            key = f"chap-{part_name}"
            for k, v in legacy.items():
                if part_name in k:
                    return v
        except (OSError, ValueError):
            pass
        return []


def save_progress(part_name: str, done: list) -> None:
    with open(progress_file(part_name), "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1)


def process_part(part_dir: str, part_name: str, limit: int | None, resume: bool) -> None:
    img_dir = os.path.join(SLIDES_ROOT, part_dir, "slide_images")
    if not os.path.isdir(img_dir):
        print(f"[skip] {part_dir}: 无 slide_images 目录")
        return
    images = sorted(
        f for f in os.listdir(img_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )
    if not images:
        print(f"[skip] {part_dir}: 无图片")
        return
    if limit:
        images = images[:limit]

    done = set(load_progress(part_name)) if resume else set()
    todo = [img for img in images if img not in done]
    print(f"[{part_name}] {len(todo)}/{len(images)} 张待处理（已跳过 {len(done)}）", flush=True)

    lines = [
        f"# 离散数学教材 · {part_name}（老师课件幻灯片转录）",
        "",
        f"> 来源：指导老师提供的交互式数字化教材（output.rar），本文件由视觉模型从幻灯片 OCR 生成。",
        f"> 共 {len(images)} 张幻灯片。",
        "",
    ]
    for i, img in enumerate(images, 1):
        path = os.path.join(img_dir, img)
        if img in done:
            continue
        print(f"  [{i}/{len(images)}] {img} ...", end="", flush=True)
        text = None
        for attempt in range(3):
            try:
                text = describe(path, PROMPT, model=OCR_MODEL)
                break
            except Exception as exc:
                print(f" 重试{attempt + 1}/3({str(exc)[:40]})", end="", flush=True)
                time.sleep(2 * (attempt + 1))
        if not text:
            print(" 放弃", flush=True)
            continue
        lines.append(f"## 幻灯片 {i}: {img}")
        lines.append("")
        lines.append(text.strip())
        lines.append("")
        done.add(img)
        save_progress(part_name, sorted(done))
        print(" OK", flush=True)
        time.sleep(BATCH_WAIT)

    out_path = os.path.join(OUT_DIR, f"老师教材_{part_name}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[完成] {part_name}: {out_path} ({len(images)} 张)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", default=None, help="章节名，逗号分隔（如 集合论,图论）")
    parser.add_argument("--limit", type=int, default=None, help="每章最多处理张数")
    parser.add_argument("--resume", action="store_true", help="断点续跑")
    args = parser.parse_args()

    if args.part:
        names = [n.strip() for n in args.part.split(",") if n.strip()]
        targets = [c for c in CHAPTERS if c[1] in names]
    else:
        targets = CHAPTERS
    if not targets:
        print(f"未知章节: {args.part}，可选: {[c[1] for c in CHAPTERS]}")
        sys.exit(1)

    for part_dir, part_name in targets:
        process_part(part_dir, part_name, args.limit, args.resume)

    print("全部完成。生成的文件位于 data/documents/老师教材_*.md")


if __name__ == "__main__":
    main()
