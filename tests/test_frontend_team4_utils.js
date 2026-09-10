const assert = require("assert");
const utils = require("../frontend/team4-utils.js");

assert.deepStrictEqual(
  utils.splitProofSteps("1. 已知 P。\n2. 由蕴含规则得 Q。\n3. 因此命题成立。"),
  ["已知 P。", "由蕴含规则得 Q。", "因此命题成立。"],
);
assert.deepStrictEqual(utils.splitProofSteps("先设 n=k。于是结论成立；证毕。"), ["先设 n=k。", "于是结论成立；", "证毕。"]);

const companion = utils.buildCompanionPrompt("today", {
  currentNode: "德摩根律",
  weakNodes: ["命题", "联结词"],
  todayMinutes: 12,
  weeklyQuestions: 8,
});
assert(companion.includes("德摩根律"));
assert(companion.includes("12 分钟"));

const lesson = utils.buildLessonPrompt({
  chapter: "命题逻辑",
  section: "真值表",
  duration: 45,
  audience: "大一学生",
  outputType: "教学设计",
  points: ["命题", "联结词"],
});
assert(lesson.includes("45 分钟"));
assert(lesson.includes("联结词"));

assert.strictEqual(utils.normalizeAgentAnswer({ data: { content: "智能体回答" } }), "智能体回答");
assert.deepStrictEqual(
  utils.resolveAssistantChannel({ provider: "xfyun-agent", channel: "agent" }),
  { kind: "agent", label: "星辰 Agent", detail: "智能体通道正常" },
);
assert.deepStrictEqual(
  utils.resolveAssistantChannel({}, "智能体接口尚未接通"),
  { kind: "fallback", label: "Qwen3 降级", detail: "智能体接口尚未接通" },
);
assert.deepStrictEqual(
  utils.countReadyMaterials({ maas: "a.png", agent: "b.png" }, { application: "c.webm" }),
  { ready: 3, total: 6 },
);

console.log("team4-utils tests passed");


const navCalls = [];
const textbookWindow = {
  kpMeta: (kpId) => ({ sec: { id: kpId === 'K010101' ? 'S0101' : 'S9999' } }),
  renderSection: (...args) => navCalls.push(args),
};
assert.strictEqual(utils.navigateTextbookWindow({}, { sectionId: 'S0101' }), false);
assert.strictEqual(utils.navigateTextbookWindow(textbookWindow, { sectionId: 'S0102' }), true);
assert.deepStrictEqual(navCalls.shift(), ['S0102', undefined]);
assert.strictEqual(utils.navigateTextbookWindow(textbookWindow, { kpId: 'K010101' }), true);
assert.deepStrictEqual(navCalls.shift(), ['S0101', 'K010101']);

// 教材推荐节点选择：薄弱点优先，其次理解中节点
{
  const weak = [{ node_id: "st_01_03", node_name: "集合" }];
  const pickedFromWeak = utils.selectTextbookRecommendationNodes({
    weak,
    understandingNodes: ["rel_02"],
    nodeInsights: [{ node_id: "rel_02", name: "关系", status: "理解中" }],
  });
  assert.strictEqual(pickedFromWeak.source, "weak");
  assert.deepStrictEqual(pickedFromWeak.nodes.map((n) => n.node_id), ["st_01_03"]);

  const pickedFromUnderstanding = utils.selectTextbookRecommendationNodes({
    weak: [],
    understandingNodes: ["st_01_03", "pl_01_01"],
    nodeInsights: [
      { node_id: "st_01_03", name: "集合", status: "理解中" },
      { node_id: "pl_01_01", name: "命题逻辑", status: "理解中" },
    ],
  });
  assert.strictEqual(pickedFromUnderstanding.source, "understanding");
  assert.deepStrictEqual(
    pickedFromUnderstanding.nodes.map((n) => n.node_id),
    ["st_01_03", "pl_01_01"],
  );
  assert.strictEqual(pickedFromUnderstanding.nodes[0].node_name, "集合");

  const pickedFromInsightsOnly = utils.selectTextbookRecommendationNodes({
    weak: [],
    understandingNodes: [],
    nodeInsights: [
      { node_id: "st_01_03", name: "集合", status: "理解中" },
      { node_id: "pl_01_01", name: "命题逻辑", status: "掌握" },
    ],
  });
  assert.strictEqual(pickedFromInsightsOnly.source, "understanding");
  assert.deepStrictEqual(pickedFromInsightsOnly.nodes.map((n) => n.node_id), ["st_01_03"]);

  const empty = utils.selectTextbookRecommendationNodes({ weak: [], understandingNodes: [], nodeInsights: [] });
  assert.strictEqual(empty.source, null);
  assert.deepStrictEqual(empty.nodes, []);

  assert.strictEqual(utils.textbookRecommendationBadge(1, "weak"), "1 个薄弱点");
  assert.strictEqual(utils.textbookRecommendationBadge(2, "understanding"), "2 个待巩固点");
}
