const test = require('node:test');
const assert = require('node:assert/strict');

const { createTypewriter } = require('../frontend/chat-stream-utils');

test('finalize cancels queued streaming updates so they cannot overwrite the final answer', async () => {
  const renders = [];
  const writer = createTypewriter({
    delayMs: 20,
    render: (text) => renders.push(text),
  });

  writer.enqueue('开头内容');
  writer.finalize('这是完整答案，不能被旧的流式更新覆盖。');

  await new Promise((resolve) => setTimeout(resolve, 50));

  assert.equal(renders.at(-1), '这是完整答案，不能被旧的流式更新覆盖。');
});

test('drain resolves only after all queued characters have been rendered', async () => {
  let rendered = '';
  const writer = createTypewriter({
    delayMs: 0,
    render: (text) => { rendered = text; },
  });

  writer.enqueue('完整');
  await writer.drain();

  assert.equal(rendered, '完整');
});
