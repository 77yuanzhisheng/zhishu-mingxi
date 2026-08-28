const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeGradingResult, gradingResultRatio } = require('../frontend/grading-utils');

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