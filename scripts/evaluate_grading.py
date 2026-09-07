'''Evaluate grading predictions against the expanded adjudication sample set.'''

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.grading.evaluation import evaluate_benchmark_predictions, load_grading_samples


DEFAULT_SAMPLES = BASE_DIR / 'data' / 'evaluation' / 'grading_samples.jsonl'


def main() -> None:
    parser = argparse.ArgumentParser(description='计算批阅 MAE、Kappa、错误类型 F1 和延迟指标')
    parser.add_argument('predictions', type=Path, help='模型预测 JSONL，每行包含 id/total_score/dimension_scores/error_types')
    parser.add_argument('--samples', type=Path, default=DEFAULT_SAMPLES, help='人工标注样本 JSONL')
    args = parser.parse_args()

    samples = load_grading_samples(args.samples)
    predictions = load_jsonl(args.predictions)
    print(json.dumps(evaluate_benchmark_predictions(predictions, samples), ensure_ascii=False, indent=2))


def load_jsonl(path: Path) -> list[dict]:
    with path.open('r', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


if __name__ == '__main__':
    main()
