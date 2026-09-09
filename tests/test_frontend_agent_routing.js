import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../frontend/app.js", import.meta.url), "utf8");
const start = source.indexOf("async function requestPreferredAssistant");
const end = source.indexOf("function formatAgentFallbackReason", start);
const preferredAssistant = source.slice(start, end);

test("preferred assistant obtains provider metadata from the Agent-first /chat pipeline", () => {
  assert.ok(start >= 0 && end > start, "requestPreferredAssistant must be present");
  assert.match(preferredAssistant, /const data = await requestBasicAssistant\(payload\);/);
  assert.doesNotMatch(preferredAssistant, /requestStreamingChat\(payload, message\)/);
  assert.match(preferredAssistant, /resolveAssistantChannel\(data, fallbackReason\)/);
});
