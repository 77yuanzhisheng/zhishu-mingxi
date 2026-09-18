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

  function escapeCompanionHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeCompanionData(payload) {
    const source = payload && typeof payload === "object" ? payload : {};
    const today = source.today_plan && typeof source.today_plan === "object" ? source.today_plan : {};
    const review = source.wrong_review && typeof source.wrong_review === "object" ? source.wrong_review : {};
    const duration = source.duration_advice && typeof source.duration_advice === "object" ? source.duration_advice : {};
    const items = Array.isArray(review.items) ? review.items.filter((item) => item && item.node_id) : [];
    return {
      ...source,
      today_plan: {
        node_id: String(today.node_id || ""),
        title: String(today.title || today.node_id || "等待学习路径"),
        reason: String(today.reason || "当前学情数据较少，先从基础知识点开始学习。"),
        exercise_count: Math.max(0, Number(today.exercise_count || 0)),
        available_question_count: Math.max(0, Number(today.available_question_count || 0)),
        target_accuracy: Math.min(1, Math.max(0, Number(today.target_accuracy ?? 0.8))),
        available: Boolean(today.available),
        accuracy: today.accuracy == null ? null : Number(today.accuracy),
        recent_practice_count: Math.max(0, Number(today.recent_practice_count || 0)),
        status: String(today.status || "未评估"),
        path_position: today.path_position == null ? null : Number(today.path_position),
        path_total_nodes: Math.max(0, Number(today.path_total_nodes || 0)),
        path_stage_title: String(today.path_stage_title || ""),
      },
      wrong_review: {
        count: items.length,
        total_wrong_answers: items.reduce((sum, item) => sum + Math.max(0, Number(item.wrong_count || 0)), 0),
        items,
        empty_message: String(review.empty_message || "最近练习中没有需要立即巩固的错题，可以继续完成今日计划。"),
      },
      duration_advice: {
        total_minutes: Math.max(0, Number(duration.total_minutes || 0)),
        review_minutes: Math.max(0, Number(duration.review_minutes || 0)),
        practice_minutes: Math.max(0, Number(duration.practice_minutes || 0)),
        summary_minutes: Math.max(0, Number(duration.summary_minutes || 0)),
      },
    };
  }

  function renderCompanionAdvice(kind, payload) {
    const data = normalizeCompanionData(payload);
    if (kind === "mistakes") return renderWrongReview(data.wrong_review);
    if (kind === "duration") return renderDurationAdvice(data.duration_advice);
    return renderTodayPlan(data.today_plan);
  }

  function renderTodayPlan(plan) {
    const pathText = plan.path_position
      ? `${plan.path_stage_title || "当前路径"} · 第 ${plan.path_position}/${plan.path_total_nodes} 个任务`
      : "等待更多学情后更新路径位置";
    const taskText = plan.available
      ? `完成 ${plan.exercise_count} 道相关练习题`
      : "当前题库暂无对应练习题，先复习概念与例题";
    const targetText = plan.available
      ? `正确率达到 ${Math.round(plan.target_accuracy * 100)}%`
      : "完成概念复习后更新计划";
    return `
      <section class="companion-tab-content" data-companion-view="today">
        <article class="companion-primary-card">
          <span>今日重点</span>
          <strong>${escapeCompanionHtml(plan.title)}</strong>
          <small>${escapeCompanionHtml(plan.node_id)} · ${escapeCompanionHtml(plan.status)}</small>
        </article>
        <div class="companion-fact-grid">
          <article><span>推荐原因</span><p>${escapeCompanionHtml(plan.reason)}</p></article>
          <article><span>建议任务</span><p>${escapeCompanionHtml(taskText)}</p></article>
          <article><span>完成目标</span><p>${escapeCompanionHtml(targetText)}</p></article>
          <article><span>路径位置</span><p>${escapeCompanionHtml(pathText)}</p></article>
        </div>
      </section>`;
  }

  function renderWrongReview(review) {
    if (!review.items.length) {
      return `
        <section class="companion-tab-content companion-empty" data-companion-view="mistakes">
          <strong>暂无待复习错题</strong>
          <p>${escapeCompanionHtml(review.empty_message)}</p>
        </section>`;
    }
    const visibleItems = review.items.slice(0, 6);
    const itemsHtml = visibleItems.map((item) => {
      const date = String(item.recent_error_at || "").split("T")[0] || "时间未知";
      const accuracy = Math.round(Math.min(1, Math.max(0, Number(item.accuracy || 0))) * 100);
      const reminder = Number(item.wrong_count || 0) > 1
        ? "该知识点近期出现多次错误"
        : "该知识点近期出现错误";
      return `
        <article class="companion-wrong-item">
          <div><span>知识点</span><strong>${escapeCompanionHtml(item.title || item.node_id)}</strong><small>${escapeCompanionHtml(item.node_id)}</small></div>
          <div class="companion-wrong-stats"><span>最近错误 ${escapeCompanionHtml(date)}</span><strong>${Number(item.wrong_count || 0)} 次</strong><span>近期正确率 ${accuracy}%</span></div>
          <p>${escapeCompanionHtml(reminder)}</p>
        </article>`;
    }).join("");
    const remaining = review.count - visibleItems.length;
    return `
      <section class="companion-tab-content" data-companion-view="mistakes">
        <div class="companion-list-heading"><strong>待复习 ${review.count} 个知识点</strong><span>共 ${review.total_wrong_answers} 次真实错误记录</span></div>
        <div class="companion-wrong-list">${itemsHtml}</div>
        ${remaining > 0 ? `<p class="companion-more">另有 ${remaining} 个待巩固知识点，可更新计划后继续查看。</p>` : ""}
      </section>`;
  }

  function renderDurationAdvice(duration) {
    return `
      <section class="companion-tab-content" data-companion-view="duration">
        <article class="companion-duration-total"><span>今日建议</span><strong>${duration.total_minutes}<small> 分钟</small></strong><p>按当前计划题量和真实错题数量计算</p></article>
        <div class="companion-duration-grid">
          <article><span>错题复盘</span><strong>${duration.review_minutes} min</strong></article>
          <article><span>当前知识点练习</span><strong>${duration.practice_minutes} min</strong></article>
          <article><span>总结检查</span><strong>${duration.summary_minutes} min</strong></article>
        </div>
      </section>`;
  }

  function practiceModuleForNode(nodeId) {
    const modules = {
      pl: "propositional_logic",
      fl: "predicate_logic",
      st: "set_theory",
      mi: "induction",
      rel: "relations",
      gt: "graph_theory",
      nt: "number_theory",
      cm: "combinatorics",
      ag: "algebraic_structure",
    };
    return modules[String(nodeId || "").split("_")[0]] || "all";
  }

  // 格式契约是补出来的，不是想出来的：模型原先会吐 `---` 分隔线（渲染器只认列表，
  // `---` 会被当成「一个 - 加内容 --」的无序列表项，显示成 `• --`），公式也会写成
  // `$f(1) = a` 这样漏掉收尾 `$`。线上同章节实测：
  //   原样 prompt → 1513 字 / 9 处 `---` / 21 个表格竖线；
  //   加上下面这份契约 → 602 字 / 0 处 `---` / 0 个竖线，
  //   六个小节一个不缺，六个 `$` 全成对，生成还快了约 10 秒。
  // 「每个 $ 必须成对」和「控制在 700 字以内」是一起在管的：输出被生成上限截断时，
  // 断在半句上最容易留下孤立的 `$`。
  function buildLessonPrompt(context) {
    const points = (context.points || []).slice(0, 8).join("、") || "按章节核心知识点组织";
    return [
      "你是离散数学课程教师的备课助手。",
      `章节：${context.chapter || "未选择"}；小节：${context.section || "未选择"}。`,
      `授课对象：${context.audience || "本科生"}；课时：${Number(context.duration || 45)} 分钟。`,
      `重点知识：${points}。`,
      `请生成${context.outputType || "教学设计"}，按下面的顺序写完整六个部分，每个部分都要出现，缺一不可：`,
      "一、教学目标；二、时间分配；三、关键推导；四、课堂活动；五、检查理解的问题；六、课后练习。",
      "排版要求：",
      "1. 用 Markdown 的 ### 标题加短列表组织，六个部分各不超过 5 行，全文控制在 700 字以内，务必在最后一行写完。",
      "2. 数学符号一律用 $...$ 包裹（例如 $G=(V,E)$、$f(1)=a$），每个 $ 必须成对出现，不要留下落单的 $。",
      "3. 不要用 --- 当分隔线。",
      "内容要可直接用于课堂。",
    ].join("\n");
  }

  function normalizeAgentAnswer(payload) {
    if (!payload || typeof payload !== "object") return "";
    const candidates = [
      payload.answer,
      payload.content,
      payload.output,
      payload.result?.answer,
      payload.data?.answer,
      payload.data?.content,
    ];
    return String(candidates.find((value) => typeof value === "string" && value.trim()) || "").trim();
  }

  function resolveAssistantChannel(payload, fallbackReason = "") {
    const marker = [
      payload?.channel,
      payload?.provider,
      payload?.source,
      payload?.agent_status,
      payload?.route,
    ].filter(Boolean).join(" ").toLowerCase();
    const reason = String(fallbackReason || payload?.fallback_reason || "").trim();
    const isAgent = /agent|星辰|xfyun/.test(marker) && !/fallback|degraded|降级/.test(marker);
    if (isAgent && !reason) {
      return { kind: "agent", label: "星辰 Agent", detail: "智能体通道正常" };
    }
    return {
      kind: "fallback",
      label: "Qwen3-32B 通道",
      detail: reason || "当前回答由基础模型生成",
    };
  }

  function navigateTextbookWindow(contentWindow, { sectionId, kpId } = {}) {
    if (!contentWindow || typeof contentWindow.renderSection !== "function") return false;
    let targetSection = String(sectionId || "").trim();
    if (!targetSection && kpId && typeof contentWindow.kpMeta === "function") {
      const meta = contentWindow.kpMeta(kpId);
      targetSection = String(meta?.sec?.id || "").trim();
    }
    if (!targetSection) return false;
    contentWindow.renderSection(targetSection, kpId || undefined);
    return true;
  }

  function normalizeRecommendationNode(item) {
    if (!item) return null;
    if (typeof item === "string") return { node_id: item, node_name: "" };
    const nodeId = item.node_id || item.nodeId || item.id;
    if (!nodeId) return null;
    return {
      node_id: nodeId,
      node_name: item.node_name || item.nodeName || item.name || "",
    };
  }

  function selectTextbookRecommendationNodes({ weak, understandingNodes, nodeInsights } = {}) {
    const weakNodes = (Array.isArray(weak) ? weak : []).map(normalizeRecommendationNode).filter(Boolean);
    if (weakNodes.length > 0) {
      return { source: "weak", nodes: weakNodes };
    }

    const insights = (Array.isArray(nodeInsights) ? nodeInsights : []).filter(
      (item) => item && item.status === "理解中",
    );
    const insightById = new Map(
      insights.map((item) => [item.node_id || item.nodeId || item.id, item]),
    );
    const rawIds = Array.isArray(understandingNodes) ? understandingNodes : [];
    const ids = rawIds.length > 0 ? rawIds : insights.map((item) => item.node_id || item.nodeId || item.id);
    const nodes = ids
      .map((id) => {
        const insight = insightById.get(id);
        return normalizeRecommendationNode(insight ? { ...insight, node_id: id } : id);
      })
      .filter(Boolean);

    if (nodes.length > 0) {
      return { source: "understanding", nodes };
    }
    return { source: null, nodes: [] };
  }

  function textbookRecommendationBadge(count, source) {
    const safeCount = Number(count) || 0;
    if (source === "weak") return `${safeCount} 个薄弱点`;
    return `${safeCount} 个待巩固点`;
  }

  function countReadyMaterials(evidence, recordings) {
    const screenshotCount = Object.values(evidence || {}).filter(Boolean).length;
    const recordingCount = Object.values(recordings || {}).filter(Boolean).length;
    return { ready: screenshotCount + recordingCount, total: 6 };
  }

  return {
    splitProofSteps,
    normalizeCompanionData,
    renderCompanionAdvice,
    practiceModuleForNode,
    buildLessonPrompt,
    normalizeAgentAnswer,
    resolveAssistantChannel,
    countReadyMaterials,
    navigateTextbookWindow,
    selectTextbookRecommendationNodes,
    textbookRecommendationBadge,
  };
});
