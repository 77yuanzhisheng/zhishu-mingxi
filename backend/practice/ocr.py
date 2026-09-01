'''Stable image preprocessing and formula-aware OCR orchestration.'''

from __future__ import annotations

import base64
import binascii
import io
import re
import tempfile
import time
from pathlib import Path
from typing import Callable

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError


MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_SIDE = 2400
OCR_MODEL = 'Qwen/Qwen3-VL-8B-Instruct'
OCR_PROMPT = (
    '你是离散数学手写公式 OCR。请从上到下逐行抄录学生答案，保留推导顺序和换行。'
    '准确区分 ∀、∃、∧、∨、¬、→、↔、∈、∉、⊆、⊂、∪、∩、空集、上下标和括号。'
    '不要解题、纠错或补写，只输出识别文本。看不清的位置写 [不清]。'
)
RETRY_PROMPT = OCR_PROMPT + ' 首次识别不完整，请逐字符复核公式，尤其检查易混淆的 1/l、0/O、∈/ε、∧/A、∨/V。'


class OCRInputError(ValueError):
    pass


def _default_runner(image_path: str, prompt: str, model: str) -> str:
    from scripts.vision import describe

    return describe(image_path, prompt, model=model)


def decode_image_base64(value: str) -> bytes:
    payload = value.strip()
    if payload.startswith('data:'):
        if ',' not in payload:
            raise OCRInputError('图片 data URL 格式无效')
        payload = payload.split(',', 1)[1]
    payload = re.sub(r'\s+', '', payload)
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise OCRInputError('图片 base64 解码失败') from exc
    if not raw:
        raise OCRInputError('图片内容为空')
    if len(raw) > MAX_IMAGE_BYTES:
        raise OCRInputError('图片过大（>15MB）')
    return raw


def normalize_formula_text(text: str) -> str:
    replacements = (
        ('<=>', '↔'),
        ('<->', '↔'),
        ('=>', '→'),
        ('->', '→'),
        ('\\forall', '∀'),
        ('\\exists', '∃'),
        ('\\neg', '¬'),
        ('\\land', '∧'),
        ('\\lor', '∨'),
        ('\\subseteq', '⊆'),
        ('\\subset', '⊂'),
        ('\\cup', '∪'),
        ('\\cap', '∩'),
        ('\\in', '∈'),
    )
    normalized = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    for source, target in replacements:
        normalized = normalized.replace(source, target)
    normalized = re.sub(r'[ \t]+', ' ', normalized)
    normalized = re.sub(r' *\n *', '\n', normalized)
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    return normalized


def _text_quality(text: str) -> int:
    compact = re.sub(r'\s+', '', text)
    penalty = 20 if any(marker in text for marker in ('无法识别', '看不清', '未检测到', '[不清]')) else 0
    math_bonus = min(20, 3 * len(re.findall(r'[∀∃∧∨¬→↔∈⊆⊂∪∩=<>]', text)))
    return max(0, min(100, len(compact) * 2 + math_bonus - penalty))


def _prepare_image(raw: bytes) -> tuple[Image.Image, dict, list[str]]:
    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise OCRInputError('上传内容不是可识别的图片') from exc

    width, height = image.size
    if width < 80 or height < 80:
        raise OCRInputError('图片分辨率过低，请重新拍摄')

    grayscale = ImageOps.grayscale(image)
    stats = ImageStat.Stat(grayscale)
    brightness = float(stats.mean[0])
    contrast = float(stats.stddev[0])
    edge = grayscale.filter(ImageFilter.FIND_EDGES)
    edge_strength = float(ImageStat.Stat(edge).mean[0])
    warnings: list[str] = []
    if min(width, height) < 480:
        warnings.append('图片分辨率偏低，建议靠近题纸重新拍摄')
    if brightness < 55:
        warnings.append('图片偏暗，建议增加光照')
    elif brightness > 245:
        warnings.append('图片可能过曝，请避免灯光反射')
    if contrast < 22:
        warnings.append('字迹与背景对比度偏低')
    if edge_strength < 8:
        warnings.append('图片可能模糊，请保持镜头稳定')

    scale = min(1.0, MAX_IMAGE_SIDE / max(width, height))
    if max(width, height) < 1200:
        scale = min(2.0, 1600 / max(width, height))
    if scale != 1.0:
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.18)
    image = ImageEnhance.Sharpness(image).enhance(1.35)

    clarity_score = round(min(100.0, edge_strength * 5), 1)
    quality = {
        'width': width,
        'height': height,
        'brightness': round(brightness, 1),
        'contrast': round(contrast, 1),
        'clarity_score': clarity_score,
        'level': 'good' if not warnings else ('poor' if len(warnings) >= 2 else 'fair'),
    }
    return image, quality, warnings


class OCRService:
    def __init__(self, runner: Callable[[str, str, str], str] | None = None, model: str = OCR_MODEL) -> None:
        self.runner = runner or _default_runner
        self.model = model

    def recognize(self, image_base64: str) -> dict:
        started_at = time.perf_counter()
        raw = decode_image_base64(image_base64)
        image, quality, warnings = _prepare_image(raw)
        attempts = 0
        candidates: list[str] = []

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            image.save(temp_path, format='PNG', optimize=True)
            for prompt in (OCR_PROMPT, RETRY_PROMPT):
                attempts += 1
                result = self.runner(str(temp_path), prompt, self.model)
                candidates.append(result.strip())
                if _text_quality(candidates[-1]) >= 28:
                    break
            raw_text = max(candidates, key=_text_quality, default='')
            text = normalize_formula_text(raw_text)
            if not text:
                raise RuntimeError('模型未返回可识别文字')
            if attempts > 1:
                warnings.append('首次识别结果不完整，已自动复核一次')
            return {
                'ok': True,
                'text': text,
                'raw_text': raw_text,
                'normalized': text != raw_text,
                'seconds': round(time.perf_counter() - started_at, 1),
                'attempts': attempts,
                'quality': quality,
                'warnings': warnings,
            }
        finally:
            temp_path.unlink(missing_ok=True)
