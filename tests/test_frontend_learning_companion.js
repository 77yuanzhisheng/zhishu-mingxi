const assert = require("assert");
const fs = require("fs");
const path = require("path");

const appSource = fs.readFileSync(path.join(__dirname, "../frontend/app.js"), "utf8");
const styleSource = fs.readFileSync(path.join(__dirname, "../frontend/style.css"), "utf8");
const loadStart = appSource.indexOf("async function loadCompanionWorkspace");
const assistantStart = appSource.indexOf("async function requestAssistantText", loadStart);
const companionSource = appSource.slice(loadStart, assistantStart);

assert(loadStart >= 0 && assistantStart > loadStart);
assert(companionSource.includes("/api/learning/companion"));
assert(companionSource.includes("data.wrong_review.count"));
assert(companionSource.includes("renderCompanionAdvice(companionState.kind"));
assert(!companionSource.includes("buildCompanionPrompt"));
assert(!companionSource.includes("requestAssistantText"));
assert(appSource.includes('practiceButton.textContent = wrongItems.length ? "复习错题" : "暂无错题"'));
assert(appSource.includes('practiceButton.textContent = "查看今日计划"'));
assert(appSource.includes("question.nodeId === practiceState.focusNodeId"));

const mobileStart = styleSource.indexOf("@media (max-width: 560px)");
const mobileSource = styleSource.slice(mobileStart);
assert(mobileStart >= 0);
assert(mobileSource.includes(".companion-fact-grid"));
assert(mobileSource.includes("grid-template-columns: 1fr"));

console.log("learning companion frontend tests passed");
