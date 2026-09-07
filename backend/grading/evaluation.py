from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Mapping, Sequence

from backend.grading.models import DIMENSION_LIMITS, ERROR_TYPES


@dataclass(frozen=True)
class HumanLabel:
    """A manually reviewed result used for model-vs-human evaluation."""

    result_id: int
    total_score: float
    dimension_scores: Mapping[str, float]
    error_types: Sequence[str]

    def __post_init__(self) -> None:
        _validate_result(
            self.result_id,
            self.total_score,
            self.dimension_scores,
            self.error_types,
        )


def evaluate_against_human_labels(
    predictions: Sequence[Mapping], labels: Sequence[HumanLabel]
) -> dict:
    """Calculate auditable agreement metrics for matching grading results.

    Predictions and labels are joined by the persisted ``result_id`` so that
    ordering cannot silently produce a misleading evaluation report.
    """

    if not labels:
        return {
            'available': False,
            'sample_size': 0,
            'reason': 'no human-labeled samples available',
        }

    by_id = {}
    for prediction in predictions:
        result_id = prediction.get('result_id')
        if result_id in by_id:
            raise ValueError(f'duplicate grading result: {result_id}')
        _validate_result(
            result_id,
            prediction.get('total_score'),
            prediction.get('dimension_scores'),
            prediction.get('error_types'),
        )
        by_id[result_id] = prediction

    matched = []
    for label in labels:
        prediction = by_id.get(label.result_id)
        if prediction is None:
            raise ValueError(f'human label {label.result_id} must match a grading result')
        matched.append((prediction, label))

    score_errors = [abs(float(pred['total_score']) - label.total_score) for pred, label in matched]
    dimension_mae = {
        dimension: sum(
            abs(float(pred['dimension_scores'][dimension]) - label.dimension_scores[dimension])
            for pred, label in matched
        ) / len(matched)
        for dimension in DIMENSION_LIMITS
    }
    predicted_bands = [_score_band(float(pred['total_score'])) for pred, _ in matched]
    human_bands = [_score_band(label.total_score) for _, label in matched]
    error_metrics = _error_type_metrics(matched)
    return {
        'available': True,
        'sample_size': len(matched),
        'score_mae': round(sum(score_errors) / len(score_errors), 4),
        'dimension_mae': {key: round(value, 4) for key, value in dimension_mae.items()},
        'score_band_cohen_kappa': round(_cohen_kappa(predicted_bands, human_bands), 4),
        'score_quadratic_weighted_kappa': round(
            _quadratic_weighted_kappa(
                [float(pred['total_score']) for pred, _ in matched],
                [label.total_score for _, label in matched],
            ),
            4,
        ),
        'error_type_micro': error_metrics,
    }


def load_grading_samples(path: str | Path) -> list[dict]:
    samples: list[dict] = []
    seen_ids: set[str] = set()
    with Path(path).open('r', encoding='utf-8') as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'invalid JSONL at line {line_number}: {exc}') from exc
            sample_id = sample.get('id')
            if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in seen_ids:
                raise ValueError(f'invalid or duplicate sample id at line {line_number}')
            for key in ('question_type', 'question', 'reference_answer', 'student_answer', 'expected_total', 'expected_dimensions', 'expected_error_types'):
                if key not in sample:
                    raise ValueError(f'missing {key} at line {line_number}')
            HumanLabel(
                result_id=line_number,
                total_score=sample['expected_total'],
                dimension_scores=sample['expected_dimensions'],
                error_types=sample['expected_error_types'],
            )
            seen_ids.add(sample_id)
            samples.append(sample)
    if not samples:
        raise ValueError('grading sample file is empty')
    return samples


def evaluate_benchmark_predictions(predictions: Sequence[Mapping], samples: Sequence[Mapping]) -> dict:
    by_id: dict[str, Mapping] = {}
    for prediction in predictions:
        sample_id = prediction.get('id')
        if not isinstance(sample_id, str) or sample_id in by_id:
            raise ValueError(f'invalid or duplicate prediction id: {sample_id}')
        by_id[sample_id] = prediction

    normalized_predictions = []
    labels = []
    latencies = []
    manual_reviews = 0
    for index, sample in enumerate(samples, 1):
        sample_id = sample['id']
        if sample_id not in by_id:
            raise ValueError(f'missing prediction for sample: {sample_id}')
        prediction = by_id[sample_id]
        normalized_predictions.append({
            'result_id': index,
            'total_score': prediction['total_score'],
            'dimension_scores': prediction['dimension_scores'],
            'error_types': prediction['error_types'],
        })
        labels.append(HumanLabel(
            result_id=index,
            total_score=sample['expected_total'],
            dimension_scores=sample['expected_dimensions'],
            error_types=sample['expected_error_types'],
        ))
        if 'latency_ms' in prediction:
            latency = prediction['latency_ms']
            if not isinstance(latency, (int, float)) or latency < 0:
                raise ValueError(f'invalid latency for sample: {sample_id}')
            latencies.append(float(latency))
        manual_reviews += int(bool(prediction.get('needs_manual_review', False)))

    report = evaluate_against_human_labels(normalized_predictions, labels)
    report['latency_ms'] = {
        'sample_size': len(latencies),
        'p50': round(_percentile(latencies, 0.50), 2) if latencies else None,
        'p95': round(_percentile(latencies, 0.95), 2) if latencies else None,
    }
    report['manual_review_rate'] = round(manual_reviews / len(samples), 4) if samples else 0.0
    return report


def _validate_result(result_id, total_score, dimension_scores, error_types) -> None:
    if not isinstance(result_id, int) or isinstance(result_id, bool):
        raise ValueError('result_id must be an integer')
    if not isinstance(total_score, (int, float)) or isinstance(total_score, bool) or not isfinite(float(total_score)):
        raise ValueError('total_score must be finite')
    if not 0 <= float(total_score) <= 100:
        raise ValueError('total_score must be between 0 and 100')
    if not isinstance(dimension_scores, Mapping) or set(dimension_scores) != set(DIMENSION_LIMITS):
        raise ValueError('dimension_scores must contain exactly the five rubric dimensions')
    for dimension, maximum in DIMENSION_LIMITS.items():
        value = dimension_scores[dimension]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(float(value)):
            raise ValueError(f'{dimension} must be finite')
        if not 0 <= float(value) <= maximum:
            raise ValueError(f'{dimension} exceeds its rubric maximum')
    if not isinstance(error_types, Sequence) or isinstance(error_types, (str, bytes)):
        raise ValueError('error_types must be a sequence')
    if len(set(error_types)) != len(error_types) or any(error not in ERROR_TYPES for error in error_types):
        raise ValueError('error_types contains an unsupported or duplicate value')


def _score_band(score: float) -> str:
    if score < 60:
        return '0-59'
    if score < 80:
        return '60-79'
    return '80-100'


def _cohen_kappa(predicted: Sequence[str], human: Sequence[str]) -> float:
    if not predicted or len(predicted) != len(human):
        raise ValueError('score band samples must have equal non-zero length')
    n = len(predicted)
    observed = sum(p == h for p, h in zip(predicted, human)) / n
    categories = set(predicted) | set(human)
    expected = sum(
        (predicted.count(category) / n) * (human.count(category) / n)
        for category in categories
    )
    return 1.0 if expected == 1.0 else (observed - expected) / (1 - expected)


def _quadratic_weighted_kappa(predicted_scores: Sequence[float], human_scores: Sequence[float]) -> float:
    if not predicted_scores or len(predicted_scores) != len(human_scores):
        raise ValueError('score samples must have equal non-zero length')
    predicted = [max(0, min(10, round(score / 10))) for score in predicted_scores]
    human = [max(0, min(10, round(score / 10))) for score in human_scores]
    categories = 11
    observed = [[0.0] * categories for _ in range(categories)]
    predicted_hist = [0.0] * categories
    human_hist = [0.0] * categories
    for pred, actual in zip(predicted, human):
        observed[pred][actual] += 1
        predicted_hist[pred] += 1
        human_hist[actual] += 1
    count = len(predicted)
    observed_disagreement = expected_disagreement = 0.0
    for pred in range(categories):
        for actual in range(categories):
            weight = ((pred - actual) / (categories - 1)) ** 2
            observed_disagreement += weight * observed[pred][actual] / count
            expected_disagreement += weight * predicted_hist[pred] * human_hist[actual] / (count * count)
    if expected_disagreement == 0:
        return 1.0 if observed_disagreement == 0 else 0.0
    return 1 - observed_disagreement / expected_disagreement


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError('percentile requires values')
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _error_type_metrics(matched) -> dict:
    true_positive = false_positive = false_negative = 0
    for prediction, label in matched:
        predicted = set(prediction['error_types'])
        actual = set(label.error_types)
        true_positive += len(predicted & actual)
        false_positive += len(predicted - actual)
        false_negative += len(actual - predicted)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
    }
