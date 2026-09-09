import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../frontend/app.js", import.meta.url), "utf8");
const start = source.indexOf("async function requestPreferredAssistant");
const end = source.indexOf("async function requestBasicAssistant", start);
const preferredAssistant = source.slice(start, end);

test("non-streaming chat does not call an undefined typewriter finalizer", () => {
  assert.ok(start >= 0 && end > start, "requestPreferredAssistant must be present");
  assert.match(preferredAssistant, /const writer = createTypewriter\(message\);/);
  assert.match(preferredAssistant, /await writer\.drain\(\);/);
  assert.doesNotMatch(preferredAssistant, /writer\.finalize\(/);
});
