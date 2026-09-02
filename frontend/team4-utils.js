(function attachTeam4Utils(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.Team4Utils = api;
})(typeof window !== "undefined" ? window : globalThis, function createTeam4Utils() {
  function splitProofSteps(reference) {
    const text = String(reference || "")
      .replace(/\r/g, "")
      .replace(/\n{2,}/g, "\n")
      .trim();
    if (!text) return [];

    const numbered = text
      .replace(/(^|\n)\s*(?:步骤\s*)?[一二三四五六七八九十]+[、.．：:]\s*/g, "$1@@STEP@@")
      .replace(/(^|\n)\s*\d+[、.．）):：]\s*/g, "$1@@STEP@@")
      .split("@@STEP@@")
      .map((item) => item.trim())
      .filter(Boolean);
    if (numbered.length > 1) return numbered;

    const lines = text.split("\n").map((item) => item.trim()).filter(Boolean);
    if (lines.length > 1) return lines;

    return text
      .split(/(?<=[。；])\s*/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function buildCompanionPrompt(kind, context) {
    const labels = {
      today: "安排今天的学习任务",
      mistakes: "分析近期薄弱点并安排错题巩固",
      duration: "根据当前状态建议学习时长和节奏",
    };
    const weak = (context.weakNodes || []).slice(0, 5).join("、") || "暂无明确薄弱点";
    return [
      "你是离散数学学习陪伴助手，请给出简短、可执行的建议。",
      `任务：${labels[kind] || labels.today}。`,
      `当前知识点：${context.currentNode || "尚未选择"}。`,
      `薄弱知识点：${weak}。`,
      `今日已学习：${Number(context.todayMinutes || 0)} 分钟；本周完成：${Number(context.weeklyQuestions || 0)} 题。`,
      "请按“现在做什么、练几题、完成标准”三项回答，不超过180字。",
    ].join("\n");
  }

  function buildLessonPrompt(context) {
    const points = (context.points || []).slice(0, 8).join("、") || "按章节核心知识点组织";
    return [
      "你是离散数学课程教师的备课助手。",
      `章节：${context.chapter || "未选择"}；小节：${context.section || "未选择"}。`,
      `授课对象：${context.audience || "本科生"}；课时：${Number(context.duration || 45)} 分钟。`,
      `重点知识：${points}。`,
      `请生成${context.outputType || "教学设计"}，包括教学目标、时间分配、关键推导、课堂活动、检查理解的问题和课后练习。`,
      "内容要可直接用于课堂，公式使用规范数学符号。",
    ].join("\n");
  }

  return { splitProofSteps, buildCompanionPrompt, buildLessonPrompt };
});
