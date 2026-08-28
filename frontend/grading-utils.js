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

function escapeGradingHtml(text) {
  return String(text ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function normalizeGradingLatex(text) {
  return String(text ?? '')
    .replace(/\$\$([\s\S]*?)\$\$/g, (_, body) => `\\[${body.trim()}\\]`)
    .replace(/(^|[^\\])\$([^$\n]+?)\$/g, (_, prefix, body) => `${prefix}\\(${body.trim()}\\)`);
}

function formatGradingText(text) {
  const normalized = normalizeGradingLatex(String(text ?? '').replace(/\r\n?/g, '\n'));
  return normalized.split(/<br\s*\/?>|\n/i).map((line) => escapeGradingHtml(line)).join('<br>');
}

function gradingQuestionSummary(text, maxLength = 84) {
  const plain = String(text ?? '')
    .replace(/<br\s*\/?>|\n/gi, ' ')
    .replace(/\$\$?([\s\S]*?)\$\$?/g, '$1')
    .replace(/\\(?:\(|\)|\[|\])/g, '')
    .replace(/\\(cup|cap|in|notin|subseteq|subset|emptyset|leq|geq|neq|to|Rightarrow|Leftrightarrow)/g, (_, command) => ({
      cup: ' union ', cap: ' intersection ', in: ' belongs to ', notin: ' not in ',
      subseteq: ' subset of ', subset: ' proper subset of ', emptyset: ' empty set ',
      leq: ' less than or equal to ', geq: ' greater than or equal to ', neq: ' not equal to ',
      to: ' to ', Rightarrow: ' implies ', Leftrightarrow: ' if and only if ',
    }[command]))
    .replace(/\\([a-zA-Z]+)(?:\{([^{}]*)\})?/g, (_, command, argument) => argument || ` ${command} `)
    .replace(/[{}]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return plain.length > maxLength ? `${plain.slice(0, maxLength - 1).trim()}…` : plain;
}

const api = {
  DIMENSION_RUBRIC,
  gradingResultRatio,
  normalizeGradingResult,
  formatGradingText,
  gradingQuestionSummary,
};

if (typeof window !== "undefined") window.GradingUtils = api;
if (typeof module !== "undefined" && module.exports) module.exports = api;
