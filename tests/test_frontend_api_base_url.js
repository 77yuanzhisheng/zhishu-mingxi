import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../frontend/app.js", import.meta.url), "utf8");
const start = source.indexOf("function resolveApiBaseUrl()");
assert.ok(start >= 0, "resolveApiBaseUrl must be present");
const openBrace = source.indexOf("{", start);
let depth = 0;
let end = -1;
for (let index = openBrace; index < source.length; index += 1) {
  if (source[index] === "{") depth += 1;
  if (source[index] === "}") depth -= 1;
  if (depth === 0) {
    end = index + 1;
    break;
  }
}
assert.ok(end > openBrace, "resolveApiBaseUrl must have a complete function body");
const resolverSource = source.slice(start, end);

function resolveFor({ origin, search = "", stored = null }) {
  const store = new Map(stored === null ? [] : [["dm_api_base_url", stored]]);
  const location = { origin, search, protocol: new URL(origin).protocol };
  const localStorage = {
    getItem(key) { return store.get(key) ?? null; },
    setItem(key, value) { store.set(key, value); },
  };
  const resolver = new Function("window", "localStorage", "URLSearchParams", `${resolverSource}; return resolveApiBaseUrl;`)(
    { location },
    localStorage,
    URLSearchParams,
  );
  return resolver();
}

test("public deployment uses the current site origin when no explicit API override exists", () => {
  assert.equal(
    resolveFor({ origin: "http://115.175.38.106:32170" }),
    "http://115.175.38.106:32170",
  );
});

test("local development API override remains supported", () => {
  assert.equal(
    resolveFor({ origin: "http://localhost:5173", search: "?api=http://127.0.0.1:8000" }),
    "http://127.0.0.1:8000",
  );
});
