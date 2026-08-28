const test = require('node:test');
const assert = require('node:assert/strict');
const {
  normalizeGradingResult,
  gradingResultRatio,
  formatGradingText,
  gradingQuestionSummary,
  gradingErrorLabel,
} = require('../frontend/grading-utils');

test('normalizes the current grading response into a 100-point five-dimension result', () => {
  const result = normalizeGradingResult({
    total_score: 85,
    dimension_scores: {
      conclusion_correctness: 18,
      key_reasoning_steps: 30,
      logical_rigor: 20,
      definition_theorem_usage: 9,
      expression_notation: 8,
    },
    feedback: '请补充中间推理步骤。',
    error_types: ['jump_step'],
  });

  assert.equal(result.score, 85);
  assert.equal(result.maxScore, 100);
  assert.deepEqual(result.dimensions.map((item) => item.maxScore), [20, 35, 25, 10, 10]);
  assert.deepEqual(result.dimensions.map((item) => item.score), [18, 30, 20, 9, 8]);
  assert.equal(result.comment, '请补充中间推理步骤。');
  assert.deepEqual(result.errors, ['jump_step']);
  assert.equal(gradingResultRatio({ total_score: 85 }), 0.85);
});

test('keeps compatibility with the legacy grading response fields', () => {
  const result = normalizeGradingResult({
    score: 7,
    max_score: 10,
    dimensions: [{ name: '结论', score: 7, max_score: 10 }],
    comment: '旧接口评语',
  });

  assert.equal(result.score, 7);
  assert.equal(result.maxScore, 10);
  assert.deepEqual(result.dimensions[0], { name: '结论', score: 7, maxScore: 10 });
  assert.equal(result.comment, '旧接口评语');
});

test('localizes grading error type codes for display', () => {
  assert.equal(gradingErrorLabel('jump_step'), '推理跳步');
  assert.equal(gradingErrorLabel('calculation_error'), '计算错误');
  assert.equal(gradingErrorLabel('unknown_error'), '其他问题');
});

test('creates a readable Chinese mathematical question summary', () => {
  const summary = gradingQuestionSummary('设 $A\\cup B$ 为集合。<br>证明 $A\\cap B$ 的性质，且 $n(\\geq 4)$。');
  assert.equal(summary, '设 A∪B 为集合。 证明 A∩B 的性质，且 n(≥4)。');
  assert.doesNotMatch(summary, /[$\\]|<br>|union|intersection|greater than or equal to/i);
});

test('normalizes word-based mathematical comparisons in question summaries', () => {
  const summary = gradingQuestionSummary('设 n (greater than or equal to 4)，且 A union B。');
  assert.equal(summary, '设 n (≥4)，且 A ∪B。');
});

test('formats question text with safe line breaks and MathJax delimiters', () => {
  const html = formatGradingText('证明 $A\\cup B$。<br><script>alert(1)</script>');
  assert.match(html, /\\\(A\\cup B\\\)/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.equal((html.match(/<br>/g) || []).length, 1);
});
