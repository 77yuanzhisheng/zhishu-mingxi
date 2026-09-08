(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.ChatStreamUtils = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  function createTypewriter({ render, delayMs = 12 }) {
    const pending = [];
    const waiters = [];
    let displayed = '';
    let timer = null;
    let stopped = false;

    const resolveWaiters = () => {
      while (waiters.length) waiters.shift()();
    };

    const isIdle = () => !timer && pending.length === 0;

    const tick = () => {
      timer = null;
      if (stopped) {
        resolveWaiters();
        return;
      }

      const character = pending.shift();
      if (character === undefined) {
        resolveWaiters();
        return;
      }

      displayed += character;
      render(displayed);
      timer = setTimeout(tick, delayMs);
    };

    const schedule = () => {
      if (!stopped && !timer && pending.length) tick();
    };

    return {
      enqueue(text) {
        if (stopped) return;
        pending.push(...Array.from(String(text || '')));
        schedule();
      },
      replace(text) {
        if (stopped) return;
        pending.length = 0;
        displayed = String(text || '');
        render(displayed);
        resolveWaiters();
      },
      finalize(text) {
        stopped = true;
        pending.length = 0;
        if (timer) clearTimeout(timer);
        timer = null;
        displayed = String(text || '');
        render(displayed);
        resolveWaiters();
      },
      drain() {
        if (isIdle()) return Promise.resolve();
        return new Promise((resolve) => waiters.push(resolve));
      },
    };
  }

  return { createTypewriter };
});
