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

console.log("team4-utils tests passed");
