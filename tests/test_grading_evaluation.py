from __future__ import annotations

from pathlib import Path

import pytest

from backend.grading.evaluation import (
    HumanLabel,
    evaluate_against_human_labels,
    evaluate_benchmark_predictions,
    load_grading_samples,
)


SAMPLE_PATH = Path(__file__).resolve().parents[1] / 'data' / 'evaluation' / 'grading_samples.jsonl'


def test_evaluation_is_explicitly_unavailable_without_human_labels():
    assert evaluate_against_human_labels([], []) == {
        'available': False,
        'sample_size': 0,
        'reason': 'no human-labeled samples available',
    }


def test_evaluation_reports_mae_kappa_and_error_type_f1_for_matched_labels():
    labels = [
        HumanLabel(
            result_id=1,
            total_score=80,
            dimension_scores={
                'conclusion_correctness': 16,
                'key_reasoning_steps': 28,
                'logical_rigor': 20,
                'definition_theorem_usage': 8,
                'expression_notation': 8,
            },
            error_types=['jump_step'],
        ),
        HumanLabel(
            result_id=2,
            total_score=40,
            dimension_scores={
                'conclusion_correctness': 8,
                'key_reasoning_steps': 14,
                'logical_rigor': 10,
                'definition_theorem_usage': 4,
                'expression_notation': 4,
            },
            error_types=['conclusion_error'],
        ),
    ]
    predictions = [
        {
            'result_id': 1,
            'total_score': 82,
            'dimension_scores': {
                'conclusion_correctness': 17,
                'key_reasoning_steps': 28,
                'logical_rigor': 21,
                'definition_theorem_usage': 8,
                'expression_notation': 8,
            },
            'error_types': ['jump_step'],
        },
        {
            'result_id': 2,
            'total_score': 45,
            'dimension_scores': {
                'conclusion_correctness': 9,
                'key_reasoning_steps': 16,
                'logical_rigor': 11,
                'definition_theorem_usage': 5,
                'expression_notation': 4,
            },
            'error_types': ['jump_step', 'conclusion_error'],
        },
    ]

    report = evaluate_against_human_labels(predictions, labels)

    assert report['available'] is True
    assert report['sample_size'] == 2
    assert report['score_mae'] == 3.5
    assert report['score_band_cohen_kappa'] == 1.0
    assert report['error_type_micro']['precision'] == pytest.approx(2 / 3)
    assert report['error_type_micro']['recall'] == 1.0
    assert report['error_type_micro']['f1'] == pytest.approx(0.8)


def test_evaluation_rejects_unmatched_or_invalid_human_labels():
    with pytest.raises(ValueError, match='must match a grading result'):
        evaluate_against_human_labels([], [
            HumanLabel(
                result_id=1,
                total_score=80,
                dimension_scores={
                    'conclusion_correctness': 16,
                    'key_reasoning_steps': 28,
                    'logical_rigor': 20,
                    'definition_theorem_usage': 8,
                    'expression_notation': 8,
                },
                error_types=[],
            )
        ])


def test_expanded_sample_set_covers_question_and_error_types():
    samples = load_grading_samples(SAMPLE_PATH)

    assert len(samples) >= 20
    assert {sample['question_type'] for sample in samples} == {'proof', 'calc'}
    covered_errors = {
        error
        for sample in samples
        for error in sample['expected_error_types']
    }
    assert covered_errors == {
        'circular_reasoning',
        'jump_step',
        'theorem_misuse',
        'notation_error',
        'conclusion_error',
    }


def test_benchmark_report_adds_weighted_kappa_latency_and_review_rate():
    samples = load_grading_samples(SAMPLE_PATH)
    predictions = [
        {
            'id': sample['id'],
            'total_score': sample['expected_total'],
            'dimension_scores': sample['expected_dimensions'],
            'error_types': sample['expected_error_types'],
            'latency_ms': index * 100,
            'needs_manual_review': index < 4,
        }
        for index, sample in enumerate(samples)
    ]

    report = evaluate_benchmark_predictions(predictions, samples)

    assert report['score_mae'] == 0
    assert report['score_quadratic_weighted_kappa'] == 1
    assert report['latency_ms'] == {'sample_size': 20, 'p50': 950.0, 'p95': 1805.0}
    assert report['manual_review_rate'] == 0.2
