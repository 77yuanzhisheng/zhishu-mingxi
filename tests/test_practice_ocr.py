from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from backend.practice.ocr import OCRInputError, OCRService, decode_image_base64


def sample_image_base64(width: int = 1000, height: int = 700) -> str:
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    draw.line((80, 150, 900, 150), fill='black', width=8)
    draw.text((80, 220), 'P -> Q', fill='black')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def test_decode_rejects_non_image_base64_after_image_validation():
    service = OCRService(runner=lambda *_: 'unused')

    with pytest.raises(OCRInputError, match='不是可识别的图片'):
        service.recognize(base64.b64encode(b'plain text').decode())


def test_decode_accepts_data_url():
    encoded = sample_image_base64()
    assert decode_image_base64(f'data:image/png;base64,{encoded}').startswith(b'\x89PNG')


def test_ocr_preprocesses_image_and_normalizes_formula_text():
    calls = []

    def runner(path: str, prompt: str, model: str) -> str:
        calls.append((path, prompt, model))
        assert Path(path).exists()
        return '已知 P -> Q，且 P\n所以 Q，证明完成。'

    result = OCRService(runner=runner).recognize(sample_image_base64())

    assert result['ok'] is True
    assert 'P → Q' in result['text']
    assert result['normalized'] is True
    assert result['attempts'] == 1
    assert result['quality']['width'] == 1000
    assert not Path(calls[0][0]).exists()


def test_ocr_retries_once_when_first_result_is_incomplete():
    outputs = iter(['[不清]', '∀x(P(x) → Q(x))\nP(a)\n因此 Q(a)，证毕。'])

    result = OCRService(runner=lambda *_: next(outputs)).recognize(sample_image_base64())

    assert result['attempts'] == 2
    assert result['text'].endswith('证毕。')
    assert any('自动复核' in warning for warning in result['warnings'])
