# Finetuning Before/After Evaluation Report

Generated: September 6, 2026

## Executive summary

- The full benchmark contains **112 questions**: 16 proofs, 36 calculations/short answers, 56 fill-in questions, and 4 applications.
- The current post-finetuning service **Spark MaaS / xop3qwen32b** completed and scored **112/112**, with an average score of **8.25/10 (82.50%)**.
- On the same 108-question subset as the historical baseline, average response latency is **11.94s** versus **53.23s**, an average speedup of **4.46x**. All 108 current responses finished within 30 seconds.
- Current 108-question average score is **8.27/10**, versus **8.75/10** historically. This is not a strict causal finetuning comparison because the baseline used another service/model and was not run under identical conditions.

## Metric definitions

- **Accuracy:** judge score normalized to percent (average score / 10). Also report pass rate at score >= 6/10.
- **Response speed:** answer-generation latency; average, median, P95, maximum, and completion rate within 30 seconds.
- **Human rating:** manual review of the targeted complex-proof/Four Color sample only. The full 112-question set remains based on the existing automatic judge scores; no human MAE/Kappa is fabricated.

## Same 108-question comparison

| Metric | Historical pre-finetuning | Current post-finetuning | Delta |
|---|---:|---:|---:|
| Questions | 108 | 108 | 0 |
| Average score | 8.75/10 | 8.27/10 | -0.48 |
| Normalized accuracy | 87.50% | 82.69% | -4.81 pp |
| Pass rate (>=6) | 96.30% | 89.81% | -6.49 pp |
| Average latency | 53.23s | 11.94s | -41.29s |
| Median latency | 35.35s | 12.40s | -22.95s |
| P95 latency | 112.50s | 13.10s | -99.40s |
| Within 30 seconds | 45.37% | 100.00% | +54.63 pp |

## Current 112-question breakdown

| Type | Questions | Avg score | Normalized accuracy | Pass rate (>=6) | Avg latency |
|---|---:|---:|---:|---:|---:|
| Proof | 16 | 8.56 | 85.62% | 93.75% | 12.58s |
| Calculation/short answer | 36 | 7.47 | 74.72% | 80.56% | 12.56s |
| Fill-in | 56 | 8.70 | 86.96% | 94.64% | 11.36s |
| Application | 4 | 7.75 | 77.50% | 75.00% | 12.45s |


## Complex proofs and Four Color Theorem

Three Chinese targeted tests were executed. Average latency was **12.42s**, the within-30-second rate was **100%**, and the manual-review average was **9.00/10**.

| Target | Manual score | Finding |
|---|---:|---|
| Set-inclusion proof | 10.0/10 | Pass: complete arbitrary-element/two-way inclusion proof |
| Vertex deletion and non-Hamiltonicity | 8.5/10 | Mostly pass: correct main result; one component argument needs tighter wording |
| Four Color Theorem + K4 coloring | 8.5/10 | Mostly pass: theorem and coloring correct; K4 planarity justification should be improved |

The Four Color check validates the theorem statement, the map/planar-graph correspondence, and a concrete K4 coloring. It does **not** claim that the model has proved the Four Color Theorem itself. Full answers are stored in `data/evaluation/targeted_chinese_plain.json`.

## Risks and next actions

1. For a strict before/after SFT conclusion, run the unfinetuned version of the same base model with the same prompts, judge, and runtime settings.
2. Repeat the current service benchmark over multiple rounds and report P50/P95 and failure rate under stable service conditions.
3. Add symbol normalization, counterexample checks, and theorem-citation validation, especially for Hamiltonian graphs, algebra, normal forms, and coloring.
4. Have the teacher/team manually annotate all 112 answers; only then compute human MAE/Kappa.
