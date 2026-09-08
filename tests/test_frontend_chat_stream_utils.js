const test = require('node:test');
const assert = require('node:assert/strict');

const { createTypewriter } = require('../frontend/chat-stream-utils');

test('finalize cancels queued stream updates so they cannot overwrite the final answer', async () => {
  const renders = [];
  const writer = createTypewriter({
    delayMs: 20,
    render: (text) => renders.push(text),
  });

  writer.enqueue('partial stream');
  writer.finalize('final answer');

  await new Promise((resolve) => setTimeout(resolve, 50));

  assert.equal(renders.at(-1), 'final answer');
});

test('drain resolves after queued characters have been rendered', async () => {
  let rendered = '';
  const writer = createTypewriter({
    delayMs: 0,
    render: (text) => { rendered = text; },
  });

  writer.enqueue('complete');
  await writer.drain();

  assert.equal(rendered, 'complete');
});