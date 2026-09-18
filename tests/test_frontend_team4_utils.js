const assert = require("assert");
const utils = require("../frontend/team4-utils.js");

assert.deepStrictEqual(
  utils.splitProofSteps("1. 已知 P。\n2. 由蕴含规则得 Q。\n3. 因此命题成立。"),
  ["已知 P。", "由蕴含规则得 Q。", "因此命题成立。"],
);
assert.deepStrictEqual(utils.splitProofSteps("先设 n=k。于是结论成立；证毕。"), ["先设 n=k。", "于是结论成立；", "证毕。"]);

const emptyCompanion = {
  today_plan: {
    node_id: "pl_01_01",
    title: "命题与真值",
    reason: "当前学情数据较少",
    exercise_count: 3,
    available_question_count: 13,
    target_accuracy: 0.8,
    available: true,
    status: "未评估",
    path_position: 1,
    path_total_nodes: 6,
    path_stage_title: "补基础",
  },
  wrong_review: {
    count: 0,
    total_wrong_answers: 0,
    items: [],
    empty_message: "最近练习中没有需要立即巩固的错题，可以继续完成今日计划。",
  },
  duration_advice: {
    total_minutes: 20,
    review_minutes: 0,
    practice_minutes: 15,
    summary_minutes: 5,
  },
};
const todayHtml = utils.renderCompanionAdvice("today", emptyCompanion);
const emptyWrongHtml = utils.renderCompanionAdvice("mistakes", emptyCompanion);
const durationHtml = utils.renderCompanionAdvice("duration", emptyCompanion);
assert(todayHtml.includes("今日重点"));
assert(todayHtml.includes("命题与真值"));
assert(!todayHtml.includes("暂无待复习错题"));
assert(emptyWrongHtml.includes("暂无待复习错题"));
assert(!emptyWrongHtml.includes("3 道"));
assert(durationHtml.includes("20"));
assert(durationHtml.includes("错题复盘"));

const wrongCompanion = {
  ...emptyCompanion,
  wrong_review: {
    count: 1,
    total_wrong_answers: 2,
    items: [{
      node_id: "rel_02_03",
      title: "关系的反对称性",
      wrong_count: 2,
      recent_error_at: "2026-09-18T08:00:00+00:00",
      recent_practice_count: 3,
      accuracy: 1 / 3,
    }],
    empty_message: "",
  },
};
const wrongHtml = utils.renderCompanionAdvice("mistakes", wrongCompanion);
assert(wrongHtml.includes("关系的反对称性"));
assert(wrongHtml.includes("2 次"));
assert(wrongHtml.includes("2026-09-18"));
assert.strictEqual(utils.normalizeCompanionData(wrongCompanion).wrong_review.count, 1);
assert.notStrictEqual(todayHtml, wrongHtml);
assert.strictEqual(utils.practiceModuleForNode("rel_02_03"), "relations");

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
  { kind: "fallback", label: "Qwen3-32B 通道", detail: "智能体接口尚未接通" },
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
