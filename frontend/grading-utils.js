const DIMENSION_RUBRIC = [
  ['conclusion_correctness', '结论正确性', 20],
  ['key_reasoning_steps', '关键推理步骤', 35],
  ['logical_rigor', '逻辑严密性', 25],
  ['definition_theorem_usage', '定义和定理使用', 10],
  ['expression_notation', '表达与符号规范', 10],
];

function gradingResultRatio(data) {
  const score = Number(data?.total_score ?? data?.score ?? 0);
  const maxScore = Number(data?.total_score != null ? 100 : data?.max_score ?? 10);
  return maxScore > 0 ? score / maxScore : 0;
}

function normalizeGradingResult(data) {
  const isCurrent = data?.total_score != null || data?.dimension_scores;
  const maxScore = Number(isCurrent ? 100 : data?.max_score ?? 10);
  const dimensions = isCurrent
    ? DIMENSION_RUBRIC.map(([key, name, rubricMax]) => ({
        name,
        score: Number(data.dimension_scores?.[key] ?? 0),
        maxScore: rubricMax,
      }))
    : (Array.isArray(data?.dimensions) ? data.dimensions : []).map((item) => ({
        name: item.name || '评分维度',
        score: Number(item.score ?? 0),
        maxScore: Number(item.max_score ?? maxScore),
      }));
  return {
    score: Number(data?.total_score ?? data?.score ?? 0),
    maxScore,
    dimensions,
    comment: data?.feedback ?? data?.comment ?? '',
    errors: Array.isArray(data?.error_types) ? data.error_types : [],
  };
}

const api = { DIMENSION_RUBRIC, gradingResultRatio, normalizeGradingResult };

if (typeof window !== "undefined") window.GradingUtils = api;
if (typeof module !== "undefined" && module.exports) module.exports = api;