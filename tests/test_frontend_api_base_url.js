const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const appSource = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'app.js'), 'utf8');
const functionSource = appSource.match(/function resolveApiBaseUrl\(\) \{[\s\S]*?\n\}/)?.[0];
assert.ok(functionSource, 'resolveApiBaseUrl must remain a top-level function');
const loadResolver = (window, values = {}) => {
  const localStorage = {
    getItem: (key) => values[key] ?? null,
    setItem: (key, value) => { values[key] = value; },
  };
  return Function('window', 'localStorage', `${functionSource}; return resolveApiBaseUrl;`)(window, localStorage)();
};

test('uses the deployed page origin for API calls outside local development', () => {
  assert.equal(
    loadResolver({
      location: { search: '', origin: 'http://115.175.38.106:32170', hostname: '115.175.38.106', protocol: 'http:' },
    }),
    'http://115.175.38.106:32170',
  );
});

test('ignores a stale localhost override when the page is deployed', () => {
  assert.equal(
    loadResolver(
      {
        location: { search: '', origin: 'http://115.175.38.106:32170', hostname: '115.175.38.106', protocol: 'http:' },
      },
      { dm_api_base_url: 'http://127.0.0.1:8000' },
    ),
    'http://115.175.38.106:32170',
  );
});
