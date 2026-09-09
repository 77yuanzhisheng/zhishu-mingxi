const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadRenderMarkdownBlocks() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'app.js'), 'utf8');
  const signature = 'function renderMarkdownBlocks(html) {';
  const start = source.indexOf(signature);
  assert.notEqual(start, -1, 'renderMarkdownBlocks must exist');

  let depth = 0;
  let end = start;
  for (; end < source.length; end += 1) {
    if (source[end] === '{') depth += 1;
    if (source[end] === '}') {
      depth -= 1;
      if (depth === 0) {
        end += 1;
        break;
      }
    }
  }
  const context = {};
  vm.runInNewContext(`${source.slice(start, end)}; this.renderMarkdownBlocks = renderMarkdownBlocks;`, context);
  return context.renderMarkdownBlocks;
}

test('continues an ordered answer list when blank lines separate successive items', () => {
  const renderMarkdownBlocks = loadRenderMarkdownBlocks();
  const html = renderMarkdownBlocks('1. Given: relation R is defined on A.\n\n1. Analysis: check two-step links.\n\n1. Conclusion: it is transitive when the definition holds.');

  assert.equal((html.match(/<ol /g) || []).length, 1);
  assert.equal((html.match(/<li>/g) || []).length, 3);
});
