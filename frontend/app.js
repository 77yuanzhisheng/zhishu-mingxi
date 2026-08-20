const API_BASE_URL = "http://127.0.0.1:8000";
const RAG_API_BASE_URL = API_BASE_URL;
const TOOLS_API_BASE_URL = API_BASE_URL;
const KB_API_BASE_URL = API_BASE_URL;
const DEFAULT_USER_ID = 1;
const DEFAULT_NODE_ID = "rel_02";

const tabRoutes = {
  dashboard: "/",
  chat: "/chat",
  truth: "/truth-table",
  relation: "/relation",
  graph: "/knowledge-graph",
  practice: "/practice",
  learning: "/learning",
  classes: "/classes",
  exam: "/exam",
  tools: "/tools",
};

const titles = {
  dashboard: "个人学习仪表盘",
  chat: "知识库 RAG 问答",
  truth: "真值表生成",
  relation: "关系矩阵性质判断",
  tools: "离散数学算法工具箱",
  graph: "离散数学知识图谱",
  practice: "自测练习",
  learning: "学情分析",
  classes: "班级管理",
  exam: "在线考试",
};

const graphState = {
  chart: null,
  modules: [],
  dependencies: [],
  nodeIndex: new Map(),
  expandedModules: new Set(),
  expandedConcepts: new Set(),
  view: "tree",
  loaded: false,
  masteryByNode: new Map(),
  recommendedPath: [],
  selectedNode: null,
  weakPulse: false,
  pulseTimer: null,
};

const learningState = {
  currentNodeId: DEFAULT_NODE_ID,
  currentNodeName: "关系性质",
  chart: null,
  report: null,
};

const dashboardState = { chart: null };
const chatState = { sessionId: null };
const classState = { role: "student", studentClass: null, teacherClasses: [], selectedClassId: null };
const examState = { examId: null, questions: [], answers: new Map(), secondsLeft: 900, timer: null };
const extendedToolState = { current: "formula-simplify", hasseChart: null };

const practiceState = {
  filter: "all",
  answered: new Map(),
};

const practiceQuestions = [
  {
    id: "q_pl_01",
    module: "propositional_logic",
    moduleName: "命题逻辑",
    nodeId: "pl_01",
    nodeName: "命题与联结词",
    type: "single",
    question: "下列哪一个语句是命题？",
    options: ["请关门。", "x + 1 = 3", "北京是中国的首都。", "你喜欢离散数学吗？"],
    answer: 2,
    explanation: "命题必须是具有确定真值的陈述句。“北京是中国的首都”可以判断真假，因此是命题。",
  },
  {
    id: "q_pl_02",
    module: "propositional_logic",
    moduleName: "命题逻辑",
    nodeId: "pl_02_02",
    nodeName: "德摩根律",
    type: "single",
    question: "命题逻辑中，¬(P ∧ Q) 等价于哪一个公式？",
    options: ["¬P ∧ ¬Q", "¬P ∨ ¬Q", "P ∨ Q", "P ∧ ¬Q"],
    answer: 1,
    explanation: "德摩根律：¬(P∧Q) ≡ ¬P∨¬Q，¬(P∨Q) ≡ ¬P∧¬Q。",
  },
  {
    id: "q_fl_01",
    module: "predicate_logic",
    moduleName: "谓词逻辑",
    nodeId: "fl_01_02",
    nodeName: "全称量词",
    type: "single",
    question: "∀xP(x) 的含义是？",
    options: ["存在某个 x 满足 P", "所有 x 都满足 P", "没有 x 满足 P", "只有一个 x 满足 P"],
    answer: 1,
    explanation: "∀ 是全称量词，表示论域中所有对象都满足谓词 P。",
  },
  {
    id: "q_set_01",
    module: "set_theory",
    moduleName: "集合论",
    nodeId: "st_01_03",
    nodeName: "幂集",
    type: "single",
    question: "若集合 A 有 n 个元素，则幂集 P(A) 的元素个数是？",
    options: ["n", "n²", "2n", "2^n"],
    answer: 3,
    explanation: "每个元素都有“选入子集/不选入子集”两种状态，因此共有 2^n 个子集。",
  },
  {
    id: "q_rel_01",
    module: "relations",
    moduleName: "关系",
    nodeId: "rel_02_01",
    nodeName: "自反性",
    type: "single",
    question: "关系矩阵满足自反性时，矩阵需要满足什么条件？",
    options: ["主对角线全为 1", "矩阵关于主对角线对称", "所有元素全为 0", "每一行恰好一个 1"],
    answer: 0,
    explanation: "自反性要求对每个 a∈A 都有 aRa，因此关系矩阵主对角线必须全为 1。",
  },
  {
    id: "q_rel_02",
    module: "relations",
    moduleName: "关系",
    nodeId: "rel_03_01",
    nodeName: "等价关系",
    type: "single",
    question: "等价关系必须同时满足哪三种性质？",
    options: ["自反、对称、传递", "自反、反对称、传递", "反自反、对称、传递", "自反、对称、反传递"],
    answer: 0,
    explanation: "等价关系的判定条件是自反性、对称性和传递性。",
  },
  {
    id: "q_ind_01",
    module: "induction",
    moduleName: "数学归纳法",
    nodeId: "mi_01",
    nodeName: "数学归纳法",
    type: "single",
    question: "数学归纳法的归纳步通常要证明什么？",
    options: ["P(1) 成立", "若 P(k) 成立，则 P(k+1) 成立", "P(k) 一定不成立", "只证明 P(2) 成立"],
    answer: 1,
    explanation: "归纳步是在归纳假设 P(k) 成立的基础上，推出 P(k+1) 成立。",
  },
  {
    id: "q_graph_01",
    module: "graph_theory",
    moduleName: "图论",
    nodeId: "gt_03_01",
    nodeName: "握手定理",
    type: "single",
    question: "无向图的握手定理说明什么？",
    options: ["所有顶点度数之和等于边数", "所有顶点度数之和等于 2 倍边数", "边数等于顶点数", "所有顶点度数都相等"],
    answer: 1,
    explanation: "每条边会给两个端点各贡献 1 个度数，所以所有顶点度数之和为 2|E|。",
  },
];

const defaultModuleDependencies = [
  { source: "propositional_logic", target: "predicate_logic", label: "逻辑基础" },
  { source: "set_theory", target: "relations", label: "集合上的关系" },
  { source: "relations", target: "graph_theory", label: "关系结构" },
  { source: "induction", target: "graph_theory", label: "归纳证明" },
];

const relationSamples = {
  order: [
    [1, 1, 1],
    [0, 1, 1],
    [0, 0, 1],
  ],
  equivalence: [
    [1, 0, 1],
    [0, 1, 0],
    [1, 0, 1],
  ],
};

const extendedToolConfigs = {
  "formula-simplify": {
    title: "命题公式化简",
    fields: [{ name: "expression", label: "命题公式", type: "text", value: "(p and q) or (p and not q)" }],
  },
  "normal-forms": {
    title: "主范式转换",
    fields: [{ name: "expression", label: "命题公式", type: "text", value: "p -> q" }],
  },
  "set-operation": {
    title: "集合运算计算器",
    fields: [
      { name: "set_a", label: "集合 A", type: "json", value: "[1, 2, 3]" },
      { name: "set_b", label: "集合 B", type: "json", value: "[2, 3, 4]" },
      { name: "operation", label: "运算", type: "select", value: "union", options: [["union", "并集"], ["intersection", "交集"], ["difference", "差集 A-B"], ["symmetric_difference", "对称差"], ["cartesian_product", "笛卡尔积"], ["power_set", "幂集 P(A)"], ["complement", "补集"]] },
      { name: "universal_set", label: "全集 U", type: "json", value: "[1, 2, 3, 4, 5]" },
    ],
  },
  "hasse-diagram": {
    title: "哈斯图生成",
    fields: [
      { name: "elements", label: "元素集合", type: "json", value: "[1, 2, 4]" },
      { name: "relation", label: "偏序关系", type: "json", rows: 5, value: "[[1,1],[2,2],[4,4],[1,2],[2,4],[1,4]]" },
    ],
  },
  dijkstra: {
    title: "Dijkstra 最短路径",
    fields: [
      { name: "edges", label: "带权边", type: "json", rows: 5, value: '[["A","B",2],["A","C",7],["B","C",1]]' },
      { name: "start", label: "起点", type: "text", value: "A" },
      { name: "end", label: "终点", type: "text", value: "C" },
      { name: "directed", label: "有向图", type: "checkbox", value: false },
    ],
  },
  bipartite: {
    title: "二分图判定",
    fields: [{ name: "matrix", label: "邻接矩阵", type: "json", rows: 6, value: "[[0,1,0,1],[1,0,1,0],[0,1,0,1],[1,0,1,0]]" }],
  },
  "code-generate": {
    title: "Python/C 代码生成",
    fields: [
      { name: "problem", label: "离散数学问题", type: "textarea", rows: 4, value: "求带权图中从起点到终点的最短路径" },
      { name: "language", label: "编程语言", type: "select", value: "python", options: [["python", "Python"], ["c", "C"]] },
      { name: "problem_type", label: "问题类型", type: "select", value: "dijkstra", options: [["truth_table", "真值表"], ["relation_properties", "关系性质"], ["set_operation", "集合运算"], ["dijkstra", "最短路径"], ["bipartite", "二分图"], ["hasse", "哈斯图"]] },
    ],
  },
};

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => switchTab(item.dataset.tab));
});
window.addEventListener("popstate", () => switchTab(getTabFromLocation(), false));
window.addEventListener("resize", () => extendedToolState.hasseChart?.resize());

document.querySelectorAll(".sample-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById("expressionInput").value = button.dataset.expression;
  });
});

document.querySelectorAll(".prompt-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById("questionInput").value = button.dataset.question;
    handleAsk();
  });
});

document.getElementById("askButton").addEventListener("click", handleAsk);
document.getElementById("questionInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    handleAsk();
  }
});

document.getElementById("truthButton").addEventListener("click", generateTruthTable);
document.getElementById("relationButton").addEventListener("click", analyzeRelation);
document.getElementById("checkStatusButton").addEventListener("click", checkStatus);
document.getElementById("matrixInput").addEventListener("input", updateMatrixPreview);

document.getElementById("loadOrderSample").addEventListener("click", () => loadMatrixSample("order"));
document.getElementById("loadEquivalenceSample").addEventListener("click", () => loadMatrixSample("equivalence"));
document.getElementById("refreshGraphButton").addEventListener("click", () => loadKnowledgeGraph(true));
document.getElementById("resetGraphButton").addEventListener("click", resetKnowledgeGraph);
document.getElementById("loadGraphRecommendationsButton").addEventListener("click", loadSelectedGraphRecommendations);
document.getElementById("refreshLearningButton").addEventListener("click", loadLearningReport);
document.getElementById("continueLearningButton").addEventListener("click", continueLearning);
document.getElementById("joinClassForm").addEventListener("submit", joinClass);
document.getElementById("createClassForm").addEventListener("submit", createClass);
document.getElementById("shareRequestForm").addEventListener("submit", requestLearningShare);
document.getElementById("startExamButton").addEventListener("click", startExam);
document.querySelectorAll(".role-button").forEach((button) => {
  button.addEventListener("click", () => setClassRole(button.dataset.classRole));
});
document.querySelectorAll(".practice-filter").forEach((button) => {
  button.addEventListener("click", () => setPracticeFilter(button.dataset.practiceFilter));
});
document.querySelectorAll(".graph-view-button").forEach((button) => {
  button.addEventListener("click", () => setGraphView(button.dataset.graphView));
});
document.querySelectorAll(".extended-tool-button").forEach((button) => {
  button.addEventListener("click", () => selectExtendedTool(button.dataset.toolName));
});
document.getElementById("runExtendedToolButton").addEventListener("click", runExtendedTool);

updateMatrixPreview();
renderPracticeList();
renderDashboard();
selectExtendedTool(extendedToolState.current);
switchTab(getTabFromLocation(), false);
bootstrapApp();

async function bootstrapApp() {
  await ensureCurrentUser();
  await Promise.allSettled([
    checkStatus(),
    loadLearningReport({ silent: true }),
  ]);
  switchTab(getTabFromLocation(), false);
}

async function ensureCurrentUser() {
  try {
    await postJson("/api/user/ensure", {
      user_id: getCurrentUserId(),
      name: "演示学生",
      role: "student",
    });
  } catch (error) {
    console.warn("用户初始化失败：", error);
  }
}

function switchTab(tabName, updateHistory = true) {
  if (!titles[tabName]) tabName = "dashboard";
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));

  document.querySelector(`[data-tab="${tabName}"]`).classList.add("active");
  document.getElementById(tabName).classList.add("active");
  document.getElementById("pageTitle").textContent = titles[tabName];
  if (updateHistory && window.location.pathname !== tabRoutes[tabName]) {
    window.history.pushState({ tab: tabName }, "", tabRoutes[tabName]);
  }

  if (tabName === "graph") {
    loadKnowledgeGraph();
    setTimeout(() => graphState.chart?.resize(), 0);
  }
  if (tabName === "dashboard") {
    renderDashboard();
    loadLearningReport({ silent: true });
    setTimeout(() => dashboardState.chart?.resize(), 0);
  }
  if (tabName === "learning") {
    loadLearningReport();
    setTimeout(() => learningState.chart?.resize(), 0);
  }
  if (tabName === "practice") {
    renderPracticeList();
  }
  if (tabName === "classes") loadClassWorkspace();
  if (tabName === "exam") updateExamStatus();
}

function getTabFromLocation() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  return Object.entries(tabRoutes).find(([, route]) => route === path)?.[0] || "dashboard";
}

async function checkStatus() {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  dot.className = "status-dot";
  text.textContent = "检测中";

  try {
    const apiResponse = await fetch(`${API_BASE_URL}/api/health`);
    if (!apiResponse.ok) {
      throw new Error("服务异常");
    }
    dot.className = "status-dot ok";
    text.textContent = "统一后端与工具已连接";
  } catch (error) {
    dot.className = "status-dot error";
    text.textContent = "服务未全部连接";
  }
}

async function handleAsk() {
  const input = document.getElementById("questionInput");
  const question = input.value.trim();
  if (!question) {
    return;
  }

  addMessage(question, "user");
  input.value = "";

  const loading = addMessage("正在检索知识库并生成回答...", "assistant");
  try {
    const data = await requestStreamingChat({
      message: question,
      user_id: getCurrentUserId(),
      session_id: chatState.sessionId,
      node_id: learningState.currentNodeId,
    }, loading);
    chatState.sessionId = data.session_id || chatState.sessionId;

    updateMessage(
      loading,
      data.answer,
    );
  } catch (error) {
    updateMessage(loading, `${error.message}。请确认主后端 8000 与模型接口都已启动。`);
  }
}

async function requestStreamingChat(payload, message) {
  const response = await fetch(`${RAG_API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "问答请求失败");
  }
  if (!response.body) {
    throw new Error("浏览器不支持流式回答");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let answer = "";
  let result = null;

  const consumeLine = (line) => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "meta") {
      chatState.sessionId = event.session_id || chatState.sessionId;
    } else if (event.type === "delta") {
      answer += event.content || "";
      updateStreamingMessage(message, answer);
    } else if (event.type === "done") {
      result = event;
    } else if (event.type === "error") {
      throw new Error(event.detail || "模型流式调用失败");
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    lines.forEach(consumeLine);
    if (done) break;
  }
  if (buffer.trim()) consumeLine(buffer);
  if (!result) {
    throw new Error("流式回答提前结束");
  }
  result.answer = result.answer || answer;
  return result;
}

function updateStreamingMessage(message, text) {
  let content = message.querySelector(".message-content");
  if (!content) {
    content = document.createElement("div");
    content.className = "message-content";
    message.replaceChildren(content);
  }
  content.textContent = text;
  const messages = document.getElementById("chatMessages");
  messages.scrollTop = messages.scrollHeight;
}

async function generateTruthTable() {
  const expression = document.getElementById("expressionInput").value.trim();
  const resultBox = document.getElementById("truthResult");

  if (!expression) {
    showError(resultBox, "请输入逻辑表达式。");
    return;
  }

  resultBox.textContent = "正在生成真值表...";

  try {
    const response = await fetch(`${TOOLS_API_BASE_URL}/tools/truth-table`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expression }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "生成真值表失败");
    }

    renderTruthTable(data);
  } catch (error) {
    showError(resultBox, `${error.message}。请确认统一后端 8000 正在运行。`);
  }
}

async function analyzeRelation() {
  const resultBox = document.getElementById("relationResult");

  try {
    const matrix = readMatrixInput();
    resultBox.textContent = "正在判断关系性质...";

    const response = await fetch(`${TOOLS_API_BASE_URL}/tools/relation-properties`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ matrix }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "判断关系性质失败");
    }

    renderRelationProperties(data, matrix.length);
  } catch (error) {
    showError(resultBox, error.message);
  }
}

function selectExtendedTool(toolName) {
  const config = extendedToolConfigs[toolName];
  if (!config) return;
  if (extendedToolState.current === "hasse-diagram" && toolName !== "hasse-diagram" && extendedToolState.hasseChart) {
    extendedToolState.hasseChart.dispose();
    extendedToolState.hasseChart = null;
  }
  extendedToolState.current = toolName;
  document.querySelectorAll(".extended-tool-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.toolName === toolName);
  });
  document.getElementById("extendedToolTitle").textContent = config.title;
  document.getElementById("extendedToolEndpoint").textContent = `POST /tools/${toolName}`;
  document.getElementById("extendedToolForm").innerHTML = config.fields.map(renderExtendedToolField).join("");
  const result = document.getElementById("extendedToolResult");
  result.className = "tool-response empty-state";
  result.textContent = "填写参数后运行工具。";
}

function renderExtendedToolField(field) {
  const value = escapeHtml(String(field.value ?? ""));
  if (field.type === "select") {
    return `<label>${escapeHtml(field.label)}<select name="${escapeHtml(field.name)}">${field.options.map(([optionValue, label]) => `<option value="${escapeHtml(optionValue)}" ${optionValue === field.value ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label>`;
  }
  if (field.type === "checkbox") {
    return `<label class="tool-checkbox"><input type="checkbox" name="${escapeHtml(field.name)}" ${field.value ? "checked" : ""}><span>${escapeHtml(field.label)}</span></label>`;
  }
  if (field.type === "json" || field.type === "textarea") {
    return `<label>${escapeHtml(field.label)}<textarea name="${escapeHtml(field.name)}" rows="${Number(field.rows || 3)}">${value}</textarea></label>`;
  }
  return `<label>${escapeHtml(field.label)}<input name="${escapeHtml(field.name)}" value="${value}"></label>`;
}

async function runExtendedTool() {
  const toolName = extendedToolState.current;
  const config = extendedToolConfigs[toolName];
  const form = document.getElementById("extendedToolForm");
  const resultBox = document.getElementById("extendedToolResult");
  const runButton = document.getElementById("runExtendedToolButton");
  resultBox.className = "tool-response";
  resultBox.textContent = "正在计算...";
  runButton.disabled = true;
  try {
    const params = {};
    config.fields.forEach((field) => {
      const control = form.querySelector(`[name="${field.name}"]`);
      if (!control) {
        throw new Error(`未找到“${field.label}”输入框，请刷新页面后重试`);
      }
      if (field.type === "checkbox") {
        params[field.name] = control.checked;
      } else if (field.type === "json") {
        const raw = control.value.trim();
        if (raw) params[field.name] = parseToolJson(raw, field.label);
      } else if (["start", "end"].includes(field.name)) {
        params[field.name] = parseToolScalar(control.value.trim());
      } else {
        params[field.name] = control.value.trim();
      }
    });
    const response = await fetch(`${TOOLS_API_BASE_URL}/tools/${toolName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `工具执行失败（${response.status}）`);
    renderExtendedToolResult(data);
  } catch (error) {
    resultBox.className = "tool-response error-state";
    resultBox.textContent = error.message;
  } finally {
    runButton.disabled = false;
  }
}

function parseToolJson(value, label) {
  const normalized = value.replace(/[，]/g, ",").replace(/[：]/g, ":");
  try {
    return JSON.parse(normalized);
  } catch (error) {
    throw new Error(`${label} 必须是有效 JSON`);
  }
}

function parseToolScalar(value) {
  if (/^-?\d+(?:\.\d+)?$/.test(value)) return Number(value);
  return value;
}

function renderExtendedToolResult(data) {
  const resultBox = document.getElementById("extendedToolResult");
  const result = data.result || {};
  const renderers = {
    "formula-simplify": renderFormulaSimplificationResult,
    "normal-forms": renderNormalFormsResult,
    "set-operation": renderSetOperationResult,
    "hasse-diagram": renderHasseDiagramResult,
    dijkstra: renderDijkstraResult,
    bipartite: renderBipartiteResult,
    "code-generate": renderCodeGenerationResult,
  };
  const renderResult = renderers[extendedToolState.current] || renderGenericToolResult;
  const steps = Array.isArray(data.steps) ? data.steps : [];

  resultBox.className = "tool-response";
  resultBox.innerHTML = `${renderResult(result)}
    <div class="tool-result-details">
      <section class="tool-result-steps">
        <h4>计算步骤</h4>
        ${steps.length ? `<ol>${steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>` : "<p>本次计算无需额外步骤。</p>"}
      </section>
      <section class="tool-result-explanation">
        <h4>结果说明</h4>
        <p>${escapeHtml(data.explanation || "暂无补充说明。")}</p>
      </section>
    </div>`;

  if (extendedToolState.current === "hasse-diagram") renderHasseResultChart(result);
  if (extendedToolState.current === "code-generate") bindGeneratedCodeCopy(result.code || "");
  typesetMath(resultBox);
}

function renderFormulaSimplificationResult(result) {
  const variables = Array.isArray(result.variables) ? result.variables : [];
  return `<section class="tool-result-visual">
    <div class="result-kicker">等价化简结果</div>
    <div class="formula-comparison">
      <div class="formula-block"><span>原公式</span><strong>${escapeHtml(formatLogicExpression(result.original))}</strong></div>
      <span class="formula-arrow" aria-hidden="true">→</span>
      <div class="formula-block answer"><span>最简等价形式</span><strong>${escapeHtml(formatLogicExpression(result.simplified))}</strong></div>
    </div>
    <div class="result-meta-row">
      <span><b>表达形式</b> ${escapeHtml(formatNormalFormName(result.form))}</span>
      <span><b>命题变量</b> ${variables.length ? variables.map((item) => escapeHtml(item)).join("、") : "无"}</span>
    </div>
  </section>`;
}

function renderNormalFormsResult(result) {
  return `<section class="tool-result-visual">
    <div class="result-kicker">主范式转换结果</div>
    <div class="source-formula"><span>原公式</span><strong>${escapeHtml(formatLogicExpression(result.expression))}</strong></div>
    <div class="normal-form-grid">
      <div class="normal-form-result"><span>主析取范式（PDNF）</span><strong>${escapeHtml(formatLogicExpression(result.principal_dnf))}</strong></div>
      <div class="normal-form-result"><span>主合取范式（PCNF）</span><strong>${escapeHtml(formatLogicExpression(result.principal_cnf))}</strong></div>
    </div>
    <div class="result-meta-row">
      <span><b>极小项编号</b> ${formatIndexList(result.minterm_indices)}</span>
      <span><b>极大项编号</b> ${formatIndexList(result.maxterm_indices)}</span>
    </div>
  </section>`;
}

function renderSetOperationResult(result) {
  const operation = getSetOperationInfo(result.operation);
  return `<section class="tool-result-visual set-result-visual">
    <div class="result-kicker">${escapeHtml(operation.name)}结果</div>
    <div class="set-result-display">
      <span class="set-operation-symbol">${escapeHtml(operation.symbol)}</span>
      <strong>${escapeHtml(formatSetValue(result.value, result.operation))}</strong>
    </div>
    <p class="result-caption">结果中共有 ${Array.isArray(result.value) ? result.value.length : 0} 个元素</p>
  </section>`;
}

function renderHasseDiagramResult(result) {
  const nodes = Array.isArray(result.nodes) ? result.nodes : [];
  const edges = Array.isArray(result.edges) ? result.edges : [];
  return `<section class="tool-result-visual">
    <div class="result-heading-row">
      <div><div class="result-kicker">偏序关系可视化</div><h4>哈斯图</h4></div>
      <div class="result-counts"><span>${nodes.length} 个元素</span><span>${edges.length} 条覆盖关系</span></div>
    </div>
    <div id="hasseResultChart" class="hasse-result-chart" role="img" aria-label="哈斯图计算结果"></div>
  </section>`;
}

function renderDijkstraResult(result) {
  const reachable = Boolean(result.reachable);
  const path = Array.isArray(result.path) ? result.path : [];
  const visited = Array.isArray(result.visited_order) ? result.visited_order : [];
  return `<section class="tool-result-visual">
    <div class="tool-status-banner ${reachable ? "success" : "failure"}">
      <span>${reachable ? "已找到最短路径" : "起点与终点不可达"}</span>
      <strong>${reachable ? `最短距离：${escapeHtml(formatNumber(result.distance))}` : "无可用路径"}</strong>
    </div>
    ${reachable ? `<div class="path-result"><span>最短路径</span><div class="path-nodes">${path.map((node, index) => `${index ? '<i aria-hidden="true">→</i>' : ""}<b>${escapeHtml(formatVertex(node))}</b>`).join("")}</div></div>` : ""}
    <div class="result-meta-row"><span><b>访问顺序</b> ${visited.length ? visited.map((node) => escapeHtml(formatVertex(node))).join(" → ") : "无"}</span></div>
  </section>`;
}

function renderBipartiteResult(result) {
  const isBipartite = Boolean(result.is_bipartite);
  const partitions = result.partitions || {};
  const left = Array.isArray(partitions.left) ? partitions.left : [];
  const right = Array.isArray(partitions.right) ? partitions.right : [];
  const conflict = Array.isArray(result.conflict_edge) ? result.conflict_edge : [];
  return `<section class="tool-result-visual">
    <div class="tool-status-banner ${isBipartite ? "success" : "failure"}">
      <span>判定结果</span><strong>${isBipartite ? "该图是二分图" : "该图不是二分图"}</strong>
    </div>
    ${isBipartite ? `<div class="partition-grid">
      <div class="partition-result left"><span>左侧顶点集 U</span><div class="result-chip-list">${renderValueChips(left)}</div></div>
      <div class="partition-divider" aria-hidden="true">↔</div>
      <div class="partition-result right"><span>右侧顶点集 V</span><div class="result-chip-list">${renderValueChips(right)}</div></div>
    </div>` : `<p class="conflict-result">发现同色相邻顶点：${conflict.length ? conflict.map((node) => escapeHtml(formatVertex(node))).join(" 与 ") : "请检查输入图"}</p>`}
  </section>`;
}

function renderCodeGenerationResult(result) {
  const language = String(result.language || "text").toLowerCase();
  const languageName = language === "c" ? "C" : language === "python" ? "Python" : language.toUpperCase();
  return `<section class="tool-result-visual generated-code-result">
    <div class="generated-code-header">
      <div><div class="result-kicker">生成结果</div><h4>${escapeHtml(languageName)} 实现</h4></div>
      <button id="copyGeneratedCodeButton" class="copy-code-button" type="button">复制代码</button>
    </div>
    <div class="result-meta-row">
      <span><b>问题类型</b> ${escapeHtml(formatProblemType(result.problem_type))}</span>
      <span><b>任务</b> ${escapeHtml(result.problem || "未说明")}</span>
    </div>
    <pre class="generated-code"><code>${escapeHtml(result.code || "未生成代码")}</code></pre>
  </section>`;
}

function renderGenericToolResult(result) {
  return `<section class="tool-result-visual"><div class="result-kicker">计算结果</div><pre class="generated-code"><code>${escapeHtml(JSON.stringify(result, null, 2))}</code></pre></section>`;
}

function renderHasseResultChart(result) {
  const container = document.getElementById("hasseResultChart");
  if (!container || typeof echarts === "undefined") return;
  if (extendedToolState.hasseChart) extendedToolState.hasseChart.dispose();
  const nodes = Array.isArray(result.nodes) ? result.nodes : [];
  const edges = Array.isArray(result.edges) ? result.edges : [];
  const grouped = new Map();
  nodes.forEach((node) => {
    const level = Number(node.level || 0);
    if (!grouped.has(level)) grouped.set(level, []);
    grouped.get(level).push(node);
  });
  const maxLevel = Math.max(0, ...grouped.keys());
  const chartNodes = [];
  grouped.forEach((levelNodes, level) => {
    levelNodes.forEach((node, index) => {
      chartNodes.push({
        id: String(node.id),
        name: String(node.label ?? node.value ?? node.id),
        x: (index - (levelNodes.length - 1) / 2) * 190,
        y: (maxLevel - level) * 115,
        symbolSize: 58,
        itemStyle: { color: level === maxLevel ? "#246a96" : "#ffffff", borderColor: "#246a96", borderWidth: 2 },
        label: { color: level === maxLevel ? "#ffffff" : "#17212f" },
      });
    });
  });
  extendedToolState.hasseChart = echarts.init(container);
  extendedToolState.hasseChart.setOption({
    animationDuration: 450,
    tooltip: { formatter: (params) => params.dataType === "edge" ? "覆盖关系" : `元素 ${params.name}` },
    series: [{
      type: "graph", layout: "none", roam: true, data: chartNodes,
      links: edges.map((edge) => ({ source: String(edge.source), target: String(edge.target) })),
      lineStyle: { color: "#86a9be", width: 2 },
      label: { show: true, fontSize: 15, fontWeight: 700 },
      emphasis: { focus: "adjacency", lineStyle: { width: 4 } },
    }],
  });
}

function bindGeneratedCodeCopy(code) {
  const button = document.getElementById("copyGeneratedCodeButton");
  if (!button) return;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code);
      button.textContent = "已复制";
      setTimeout(() => { button.textContent = "复制代码"; }, 1600);
    } catch (error) {
      button.textContent = "复制失败";
    }
  });
}

function formatLogicExpression(expression) {
  return String(expression ?? "无")
    .replace(/<->/g, "↔").replace(/->/g, "→")
    .replace(/\bnot\b/gi, "¬").replace(/\band\b/gi, "∧")
    .replace(/\bor\b/gi, "∨").replace(/\bxor\b/gi, "⊕");
}

function formatNormalFormName(form) {
  const names = { minimal_dnf: "最小析取范式", dnf: "析取范式", cnf: "合取范式" };
  return names[form] || form || "等价公式";
}

function formatIndexList(values) {
  return Array.isArray(values) && values.length ? values.map((value) => escapeHtml(String(value))).join("、") : "无";
}

function getSetOperationInfo(operation) {
  return ({
    union: { name: "并集", symbol: "A ∪ B =" }, intersection: { name: "交集", symbol: "A ∩ B =" },
    difference: { name: "差集", symbol: "A − B =" }, symmetric_difference: { name: "对称差", symbol: "A △ B =" },
    cartesian_product: { name: "笛卡尔积", symbol: "A × B =" }, power_set: { name: "幂集", symbol: "P(A) =" },
    complement: { name: "补集", symbol: "Aᶜ =" },
  })[operation] || { name: "集合运算", symbol: "结果 =" };
}

function formatSetValue(value, operation) {
  if (!Array.isArray(value)) return String(value ?? "∅");
  if (!value.length) return "∅";
  const items = value.map((item) => {
    if (!Array.isArray(item)) return formatVertex(item);
    const content = item.map(formatVertex).join(", ");
    return operation === "cartesian_product" ? `(${content})` : `{${content}}`;
  });
  return `{${items.join(", ")}}`;
}

function renderValueChips(values) {
  if (!values.length) return '<span class="result-chip empty">空集</span>';
  return values.map((value) => `<span class="result-chip">${escapeHtml(formatVertex(value))}</span>`).join("");
}

function formatVertex(value) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function formatNumber(value) {
  return Number.isFinite(Number(value)) ? String(Number(value)) : String(value ?? "未知");
}

function formatProblemType(type) {
  return ({ truth_table: "真值表", relation_properties: "关系性质", set_operation: "集合运算",
    dijkstra: "最短路径", bipartite: "二分图判定", hasse: "哈斯图" })[type] || type || "通用算法";
}

function addMessage(text, type, citations = []) {
  const messages = document.getElementById("chatMessages");
  const message = document.createElement("article");
  message.className = `message ${type}`;

  const content = document.createElement("div");
  content.className = "message-content";
  content.innerHTML = formatAnswerHtml(text);
  message.appendChild(content);

  if (citations.length > 0) {
    const list = document.createElement("div");
    list.className = "citation-list";
    citations.forEach((citation) => {
      const item = document.createElement("span");
      item.textContent = citation;
      list.appendChild(item);
    });
    message.appendChild(list);
  }

  messages.appendChild(message);
  typesetMath(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

function updateMessage(message, text, citations = []) {
  message.innerHTML = "";

  const content = document.createElement("div");
  content.className = "message-content";
  content.innerHTML = formatAnswerHtml(text);
  message.appendChild(content);

  if (citations.length > 0) {
    const list = document.createElement("div");
    list.className = "citation-list";
    citations.forEach((citation) => {
      const item = document.createElement("span");
      item.textContent = citation;
      list.appendChild(item);
    });
    message.appendChild(list);
  }

  typesetMath(message);
}

function renderTruthTable(data) {
  const resultBox = document.getElementById("truthResult");
  const trueCount = data.rows.filter((row) => row.result).length;
  const falseCount = data.rows.length - trueCount;
  const formulaType = getFormulaType(trueCount, falseCount);
  const headers = [...data.variables, "结果"];
  const rows = data.rows
    .map((row) => {
      const values = data.variables.map((variable) => `<td>${formatBool(row.values[variable])}</td>`).join("");
      return `<tr>${values}<td>${formatBool(row.result)}</td></tr>`;
    })
    .join("");

  resultBox.classList.remove("empty-state");
  resultBox.innerHTML = `
    <div class="result-summary">
      <div class="summary-card"><span>变量数</span><strong>${data.variables.length}</strong></div>
      <div class="summary-card"><span>行数</span><strong>${data.rows.length}</strong></div>
      <div class="summary-card"><span>公式类型</span><strong>${formulaType}</strong></div>
    </div>
    <p class="result-note">结果统计：真 ${trueCount} 行，假 ${falseCount} 行。可结合教材中的永真式、矛盾式、可满足式概念进行判断。</p>
    <table>
      <thead>
        <tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderRelationProperties(data, size) {
  const resultBox = document.getElementById("relationResult");
  const labels = {
    reflexive: "自反",
    irreflexive: "反自反",
    symmetric: "对称",
    antisymmetric: "反对称",
    transitive: "传递",
  };
  const trueCount = Object.values(data).filter(Boolean).length;

  resultBox.classList.remove("empty-state");
  resultBox.innerHTML = `
    <div class="result-summary">
      <div class="summary-card"><span>矩阵阶数</span><strong>${size} × ${size}</strong></div>
      <div class="summary-card"><span>满足性质</span><strong>${trueCount} / 5</strong></div>
      <div class="summary-card"><span>结果类型</span><strong>${guessRelationType(data)}</strong></div>
    </div>
    <p class="result-note">${buildRelationExplanation(data)}</p>
    <div class="property-list">
      ${Object.entries(labels)
        .map(([key, label]) => `
          <div class="property-item ${data[key] ? "true" : "false"}">
            ${label}
            <strong>${data[key] ? "是" : "否"}</strong>
          </div>
        `)
        .join("")}
    </div>
  `;
}

function updateMatrixPreview() {
  const preview = document.getElementById("matrixPreview");

  try {
    const matrix = readMatrixInput();
    preview.innerHTML = matrix
      .map((row) => `
        <div class="matrix-row">
          ${row.map((cell) => `<span class="matrix-cell ${cell ? "on" : ""}">${Number(cell)}</span>`).join("")}
        </div>
      `)
      .join("");
  } catch (error) {
    preview.innerHTML = '<p class="error">矩阵格式待修正</p>';
  }
}

function loadMatrixSample(type) {
  document.getElementById("matrixInput").value = JSON.stringify(relationSamples[type], null, 2);
  updateMatrixPreview();
}

function readMatrixInput() {
  const normalizedText = normalizeJsonText(document.getElementById("matrixInput").value);
  const matrix = JSON.parse(normalizedText);
  if (!Array.isArray(matrix)) {
    throw new Error("矩阵必须是二维数组。");
  }
  return matrix;
}

function normalizeJsonText(text) {
  return text
    .replaceAll("，", ",")
    .replaceAll("［", "[")
    .replaceAll("］", "]")
    .replaceAll("（", "(")
    .replaceAll("）", ")")
    .replaceAll("：", ":")
    .replaceAll("；", ";");
}

function guessRelationType(data) {
  if (data.reflexive && data.symmetric && data.transitive) {
    return "等价关系";
  }
  if (data.reflexive && data.antisymmetric && data.transitive) {
    return "偏序关系";
  }
  return "一般关系";
}

function getFormulaType(trueCount, falseCount) {
  if (falseCount === 0) {
    return "永真式";
  }
  if (trueCount === 0) {
    return "矛盾式";
  }
  return "可满足式";
}

function buildRelationExplanation(data) {
  if (data.reflexive && data.symmetric && data.transitive) {
    return "该关系同时满足自反、对称和传递，因此可以归类为等价关系。";
  }
  if (data.reflexive && data.antisymmetric && data.transitive) {
    return "该关系同时满足自反、反对称和传递，因此可以归类为偏序关系。";
  }
  return "该关系未同时满足等价关系或偏序关系的全部条件，可继续观察具体缺失的性质。";
}

async function loadKnowledgeGraph(forceReload = false) {
  const container = document.getElementById("knowledgeGraphChart");

  if (graphState.loaded && !forceReload) {
    renderKnowledgeGraph();
    return;
  }

  if (!window.echarts) {
    container.textContent = "ECharts 加载失败，请确认网络可访问 CDN，或将 echarts.min.js 放到本地。";
    return;
  }

  container.textContent = "正在从知识库加载知识图谱...";

  try {
    const response = await fetch(`${KB_API_BASE_URL}/kb/knowledge-graph`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "知识图谱接口请求失败");
    }

    graphState.modules = normalizeKnowledgeGraph(data);
    graphState.dependencies = normalizeKnowledgeDependencies(data, graphState.modules);
    graphState.expandedModules.clear();
    graphState.expandedConcepts.clear();
    graphState.loaded = true;
    renderKnowledgeGraph();
    showGraphNodeDetail({
      name: "知识图谱",
      level: "overview",
      description: `已加载 ${graphState.modules.length} 个课程模块。点击模块展开子概念，再点击子概念展开定义、定理、例题和规则。`,
    });
  } catch (error) {
    container.textContent = `${error.message}。请确认主后端 8000 已启动，并且接口 /kb/knowledge-graph 可用。`;
  }
}

function normalizeKnowledgeGraph(raw) {
  const modules = Array.isArray(raw)
    ? raw
    : raw.modules || raw.children || raw.data || raw.knowledge_graph || [];

  return modules.map((module, moduleIndex) => {
    const moduleNodeId = module.node_id || module.id || module.key || `module_${moduleIndex + 1}`;
    const moduleId = `module-${moduleNodeId}`;
    const children = module.children || module.concepts || module.nodes || [];
    const moduleName = module.name || module.title || module.label || `模块${moduleIndex + 1}`;

    return {
      id: moduleId,
      nodeId: moduleNodeId,
      name: moduleName,
      type: "module",
      description: module.description || module.summary || module.content || "",
      searchQuery: module.search_query || module.query || moduleName,
      children: children.map((child, childIndex) => {
        const childNodeId = child.node_id || child.id || child.key || `${moduleNodeId}_${childIndex + 1}`;
        const childId = `${moduleId}-concept-${childNodeId}`;
        const items = child.items || child.children || [];
        const childName = child.name || child.title || child.label || `子概念${childIndex + 1}`;

        return {
          id: childId,
          nodeId: childNodeId,
          parentId: moduleId,
          parentNodeId: moduleNodeId,
          name: childName,
          type: "concept",
          description: child.description || child.summary || child.content || "",
          searchQuery: child.search_query || child.query || `${moduleName} ${childName}`,
          masteryLevels: child.mastery_levels || {},
          items: items.map((item, itemIndex) => ({
            ...normalizeKnowledgeItem(item, itemIndex, childId, childNodeId, childName),
          })),
        };
      }),
    };
  });
}

function normalizeKnowledgeDependencies(raw, modules) {
  const moduleIds = new Set(modules.map((module) => module.nodeId));
  const moduleNameToId = new Map(modules.map((module) => [module.name, module.nodeId]));
  const rawModules = Array.isArray(raw)
    ? raw
    : raw.modules || raw.children || raw.data || raw.knowledge_graph || [];
  const declaredDependencies = Array.isArray(raw?.dependencies)
    ? raw.dependencies
    : Array.isArray(raw?.edges)
      ? raw.edges
      : Array.isArray(raw?.links)
        ? raw.links
        : [];

  const candidates = declaredDependencies.map((dependency) => ({
    source: dependency.source || dependency.from || dependency.prerequisite,
    target: dependency.target || dependency.to || dependency.module,
    label: dependency.label || dependency.name || dependency.type || "前置依赖",
  }));

  rawModules.forEach((module) => {
    const target = module.node_id || module.id || module.key || module.name;
    const prerequisites = module.depends_on || module.prerequisites || module.dependencies || [];
    const values = Array.isArray(prerequisites) ? prerequisites : [prerequisites];
    values.filter(Boolean).forEach((source) => {
      candidates.push({ source, target, label: "前置依赖" });
    });
  });

  const sourceData = candidates.length ? candidates : defaultModuleDependencies;
  const seen = new Set();
  return sourceData.reduce((dependencies, dependency) => {
    const source = resolveModuleNodeId(dependency.source, moduleIds, moduleNameToId);
    const target = resolveModuleNodeId(dependency.target, moduleIds, moduleNameToId);
    const key = `${source}->${target}`;
    if (!source || !target || source === target || seen.has(key)) {
      return dependencies;
    }
    seen.add(key);
    dependencies.push({ source, target, label: dependency.label || "前置依赖" });
    return dependencies;
  }, []);
}

function resolveModuleNodeId(value, moduleIds, moduleNameToId) {
  const normalized = String(value || "").replace(/^module-/, "");
  if (moduleIds.has(normalized)) {
    return `module-${normalized}`;
  }
  const idByName = moduleNameToId.get(String(value || ""));
  return idByName ? `module-${idByName}` : "";
}

function normalizeKnowledgeItem(item, itemIndex, parentId, parentNodeId, parentName) {
  const type = item.type || "item";
  const itemNodeId = item.node_id || item.id || item.key || `${parentNodeId}_${itemIndex + 1}`;
  const name = item.name || item.title || item.label || item.text || item.content || `条目${itemIndex + 1}`;
  const description = item.description || item.summary || item.content || item.text || "";

  return {
    id: `${parentId}-item-${itemNodeId}`,
    nodeId: itemNodeId,
    parentId,
    parentNodeId,
    name,
    type,
    description,
    searchQuery: item.search_query || item.query || `${parentName} ${name}`,
    masteryLevels: item.mastery_levels || {},
  };
}

function renderKnowledgeGraph() {
  const container = document.getElementById("knowledgeGraphChart");
  if (!graphState.chart) {
    container.innerHTML = "";
    graphState.chart = echarts.init(container);
    graphState.chart.on("click", handleGraphClick);
    window.addEventListener("resize", () => graphState.chart?.resize());
    graphState.pulseTimer = window.setInterval(() => {
      if (!graphState.masteryByNode.size || !document.getElementById("graph").classList.contains("active")) return;
      graphState.weakPulse = !graphState.weakPulse;
      renderKnowledgeGraph();
    }, 1200);
  }

  const option = graphState.view === "force"
    ? buildForceGraphOption()
    : buildMindMapOption();
  graphState.chart.setOption(option, true);
}

function buildForceGraphOption() {
  const { nodes, links } = buildGraphSeriesData(true);
  return {
    tooltip: {
      formatter: (params) => {
        const data = params.data || {};
        if (params.dataType === "edge") {
          return data.relationLabel || data.label?.formatter || "";
        }
        return `${data.name}<br>${getTypeLabel(data.rawType || data.type)}`;
      },
    },
    legend: {
      top: 8,
      data: ["模块", "子概念", "定义", "定理", "例题", "规则"],
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        animationDurationUpdate: 350,
        categories: [
          { name: "模块" },
          { name: "子概念" },
          { name: "定义" },
          { name: "定理" },
          { name: "例题" },
          { name: "规则" },
        ],
        force: {
          repulsion: 260,
          edgeLength: [80, 170],
          gravity: 0.08,
        },
        label: {
          show: true,
          position: "inside",
          color: "#ffffff",
          fontWeight: 700,
          formatter: (params) => truncateText(params.data.name, 10),
        },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: 8,
        lineStyle: {
          color: "#9eb7cc",
          width: 1.5,
          curveness: 0.08,
        },
        data: nodes,
        links,
      },
    ],
  };
}

function buildMindMapOption() {
  graphState.nodeIndex = new Map();
  const treeData = {
    id: "course-root",
    name: "离散数学",
    rawType: "root",
    symbol: "roundRect",
    symbolSize: [96, 42],
    itemStyle: { color: "#16476d", borderColor: "#ffffff", borderWidth: 2 },
    label: { color: "#ffffff", fontWeight: 700 },
    children: graphState.modules.map((module, index) => buildMindMapNode(module, index)),
  };

  return {
    tooltip: {
      formatter: (params) => {
        const data = params.data || {};
        if (data.id === "course-root") {
          return "离散数学课程知识体系";
        }
        const node = graphState.nodeIndex.get(data.id);
        return node ? `${node.name}<br>${getTypeLabel(node.type)}` : data.name || "";
      },
    },
    series: [
      {
        type: "tree",
        data: [treeData],
        orient: "LR",
        top: 30,
        left: 55,
        bottom: 30,
        right: 165,
        roam: true,
        expandAndCollapse: true,
        initialTreeDepth: -1,
        edgeShape: "polyline",
        edgeForkPosition: "58%",
        symbol: "roundRect",
        lineStyle: {
          color: "#b8c9d8",
          width: 1.5,
        },
        label: {
          position: "inside",
          align: "center",
          verticalAlign: "middle",
          color: "#ffffff",
          fontSize: 11,
          fontWeight: 700,
          formatter: (params) => truncateText(params.data.name, 14),
        },
        leaves: {
          label: {
            position: "inside",
            align: "center",
          },
        },
        animationDuration: 350,
        animationDurationUpdate: 350,
      },
    ],
  };
}

function buildMindMapNode(module, moduleIndex) {
  graphState.nodeIndex.set(module.id, module);
  return {
    id: module.id,
    name: `${moduleIndex + 1}. ${module.name}`,
    rawType: module.type,
    symbolSize: [112, 38],
    itemStyle: getGraphNodeStyle(module),
    collapsed: !graphState.expandedModules.has(module.id),
    children: module.children.map((concept) => buildMindMapConceptNode(concept)),
  };
}

function buildMindMapConceptNode(concept) {
  graphState.nodeIndex.set(concept.id, concept);
  return {
    id: concept.id,
    name: concept.name,
    rawType: concept.type,
    symbolSize: [116, 34],
    itemStyle: getGraphNodeStyle(concept),
    collapsed: !graphState.expandedConcepts.has(concept.id),
    children: concept.items.map((item) => {
      const category = getItemCategory(item.type);
      graphState.nodeIndex.set(item.id, item);
      return {
        id: item.id,
        name: item.name,
        rawType: item.type,
        symbolSize: [138, 30],
        itemStyle: getGraphNodeStyle(item),
      };
    }),
  };
}

function buildGraphSeriesData(includeDependencies = false) {
  const nodes = [];
  const links = [];
  graphState.nodeIndex = new Map();

  graphState.modules.forEach((module) => {
    pushGraphNode(nodes, module, 0, 62);

    if (!graphState.expandedModules.has(module.id)) {
      return;
    }

    module.children.forEach((concept) => {
      pushGraphNode(nodes, concept, 1, 48);
      links.push(buildGraphLink(module.id, concept.id, "包含"));

      if (!graphState.expandedConcepts.has(concept.id)) {
        return;
      }

      concept.items.forEach((item) => {
        pushGraphNode(nodes, item, getItemCategory(item.type), 34);
        links.push(buildGraphLink(concept.id, item.id, getTypeLabel(item.type)));
      });
    });
  });

  if (includeDependencies) {
    graphState.dependencies.forEach((dependency) => {
      links.push(buildDependencyLink(dependency));
    });
  }

  return { nodes, links };
}

function pushGraphNode(nodes, rawNode, category, symbolSize) {
  const node = {
    id: rawNode.id,
    nodeId: rawNode.nodeId,
    name: rawNode.name,
    rawType: rawNode.type,
    searchQuery: rawNode.searchQuery,
    category,
    symbolSize,
    value: rawNode.description || "",
    itemStyle: getGraphNodeStyle(rawNode),
  };
  graphState.nodeIndex.set(rawNode.id, rawNode);
  nodes.push(node);
}

function buildGraphLink(source, target, label) {
  const sourceNode = graphState.nodeIndex.get(source);
  const targetNode = graphState.nodeIndex.get(target);
  const highlighted = isRecommendedNode(sourceNode) && isRecommendedNode(targetNode);
  return {
    source,
    target,
    lineStyle: highlighted ? { color: "#157f6f", width: 4, opacity: 1 } : undefined,
    symbolSize: highlighted ? 12 : 8,
    label: {
      show: false,
      formatter: label,
    },
  };
}

function buildDependencyLink(dependency) {
  return {
    source: dependency.source,
    target: dependency.target,
    relationLabel: dependency.label,
    symbol: ["none", "arrow"],
    symbolSize: 10,
    lineStyle: {
      color: "#d97706",
      width: 2.4,
      type: "dashed",
      curveness: 0.2,
      opacity: 0.9,
    },
    label: {
      show: false,
      formatter: dependency.label,
      color: "#9a4d08",
      fontSize: 10,
      backgroundColor: "rgba(255,255,255,0.9)",
      borderRadius: 3,
      padding: [2, 4],
    },
    emphasis: {
      lineStyle: { width: 3.2, opacity: 1 },
      label: { show: true },
    },
  };
}

function handleGraphClick(params) {
  if (params.dataType === "edge") {
    return;
  }

  if (params.data?.id === "course-root") {
    showGraphNodeDetail({
      name: "离散数学",
      level: "overview",
      description: "课程知识按命题逻辑、谓词逻辑、集合论、数学归纳法、关系和图论的顺序组织。",
    });
    return;
  }

  const node = graphState.nodeIndex.get(params.data.id);
  if (!node) {
    return;
  }

  if (node.type === "module" && node.children?.length) {
    toggleSetValue(graphState.expandedModules, node.id);
    if (graphState.view === "force") {
      renderKnowledgeGraph();
    }
  } else if (node.type === "concept" && node.items?.length) {
    toggleSetValue(graphState.expandedConcepts, node.id);
    if (graphState.view === "force") {
      renderKnowledgeGraph();
    }
  }

  graphState.selectedNode = node;
  setCurrentLearningNode(node);
  showGraphNodeDetail(node);
  loadGraphNodeKnowledge(node);
  loadRecommendedQuestions(node);
  recordLearningEvent(node);
}

function setGraphView(view) {
  if (!['tree', 'force'].includes(view) || graphState.view === view) {
    return;
  }
  graphState.view = view;
  document.querySelectorAll(".graph-view-button").forEach((button) => {
    const active = button.dataset.graphView === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });

  const hint = document.getElementById("graphViewHint");
  hint.textContent = view === "tree"
    ? "思维导图按课程顺序展示层级；点击模块或子概念可继续展开。"
    : "关系图展示层级连线和跨模块依赖；橙色虚线表示前置知识流向。";
  document.querySelector(".graph-legend .dependency").hidden = view !== "force";
  renderKnowledgeGraph();
}

function showGraphNodeDetail(node) {
  document.getElementById("graphDetailTitle").textContent = node.name || "知识图谱";
  if (node.level === "overview") {
    document.getElementById("graphDetailPrereq").textContent = "默认展示 6 大模块。点击模块展开子概念，再点击子概念展开定义、定理、例题和规则。";
    document.getElementById("graphDetailConcepts").innerHTML = `<p>${formatAnswerHtml(node.description || "请选择一个节点查看详情。")}</p>`;
    document.getElementById("graphDetailLinks").textContent = "点击节点后，前端会使用该节点的 search_query 调用 /kb/search 获取教材内容。";
    document.getElementById("graphDetailTasks").textContent = "点击节点后，前端会把 node_id 作为 view 事件传给学情分析接口。";
    typesetMath(document.getElementById("graphDetailConcepts"));
    return;
  }

  const nodeId = node.nodeId || node.id || "无";
  const searchQuery = node.searchQuery || node.name || "无";
  document.getElementById("graphDetailPrereq").textContent = `类型：${getTypeLabel(node.type || node.level)} · node_id：${nodeId}`;
  document.getElementById("graphDetailConcepts").innerHTML = buildNodeSummaryHtml(node, searchQuery);

  if (node.type === "module") {
    document.getElementById("graphDetailLinks").innerHTML = `<p class="muted-line">正在用 search_query 检索：${escapeHtml(searchQuery)}</p>`;
    document.getElementById("graphDetailTasks").innerHTML = buildTrackingHtml(node, "已记录模块访问，可传给学情分析服务。");
  } else if (node.type === "concept") {
    document.getElementById("graphDetailLinks").innerHTML = `<p class="muted-line">正在用 search_query 检索：${escapeHtml(searchQuery)}</p>`;
    document.getElementById("graphDetailTasks").innerHTML = buildTrackingHtml(node, "已记录子概念访问，后续可计算掌握度。");
  } else {
    document.getElementById("graphDetailLinks").innerHTML = `<p class="muted-line">正在用 search_query 检索：${escapeHtml(searchQuery)}</p>`;
    document.getElementById("graphDetailTasks").innerHTML = buildTrackingHtml(node, "已记录知识条目访问，适合用于薄弱点定位。");
  }

  typesetMath(document.getElementById("graphDetailConcepts"));
}

async function loadGraphNodeKnowledge(node) {
  const target = document.getElementById("graphDetailLinks");
  const query = node.searchQuery || node.name;
  if (!query || node.level === "overview") {
    return;
  }

  try {
    const response = await fetch(`${KB_API_BASE_URL}/kb/search?q=${encodeURIComponent(query)}&top_k=3`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "知识库检索失败");
    }

    const results = Array.isArray(data.results) ? data.results : [];
    target.innerHTML = renderKnowledgeSearchResults(results);
    typesetMath(target);
  } catch (error) {
    target.innerHTML = `<p class="error">${escapeHtml(error.message)}。请确认主后端 8000 的 /kb/search 可用。</p>`;
  }
}

function renderKnowledgeSearchResults(results) {
  if (!results.length) {
    return `<p class="muted-line">未检索到对应资料。可以让队员二检查该节点的 search_query 或知识库索引。</p>`;
  }

  return `
    <div class="knowledge-results">
      ${results.map((result, index) => {
        const metadata = result.metadata || {};
        const source = formatKnowledgeSource(metadata);
        const score = typeof result.score === "number" ? ` · 相似度 ${result.score.toFixed(3)}` : "";
        return `
          <article class="knowledge-result-item">
            <div class="node-meta">资料 ${index + 1}${score}</div>
            <div class="knowledge-result-content">${formatAnswerHtml(result.content || result.text || "暂无内容")}</div>
            <div class="source-line">${escapeHtml(source)}</div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function formatKnowledgeSource(metadata) {
  // 只显示来源文档名，不显示章节/页码。
  return metadata.source || metadata.file_name || metadata.filename || "";
}

function buildNodeSummaryHtml(node, searchQuery) {
  const countText = node.type === "module"
    ? `包含 ${node.children?.length || 0} 个子概念`
    : node.type === "concept"
      ? `包含 ${node.items?.length || 0} 条知识条目`
      : `父节点：${node.parentNodeId || node.parentId || "无"}`;
  const description = node.description || "暂无节点简介，右侧将从知识库检索对应教材内容。";

  return `
    <div class="node-summary">
      <p>${formatAnswerHtml(description)}</p>
      <div class="node-meta">search_query：${escapeHtml(searchQuery)}</div>
      <div class="node-meta">${escapeHtml(countText)}</div>
    </div>
  `;
}

function buildTrackingHtml(node, message) {
  return `
    <div class="tracking-box">
      <strong>${escapeHtml(message)}</strong>
      <span>payload：node_id=${escapeHtml(node.nodeId || node.id || "")}，event_type=view，user_id=${escapeHtml(getCurrentUserId())}</span>
    </div>
  `;
}

function recordLearningEvent(node) {
  if (!node || node.level === "overview") {
    return;
  }

  const payload = {
    user_id: getCurrentUserId(),
    node_id: node.nodeId || node.id,
    event_type: "view",
  };

  const localEvents = parseLocalLearningEvents();
  localEvents.push({
    ...payload,
    node_name: node.name,
    search_query: node.searchQuery || node.name,
    timestamp: new Date().toISOString(),
  });
  localStorage.setItem("learning_events", JSON.stringify(localEvents.slice(-100)));

  // 当前学情接口只定义答题掌握度更新，浏览行为先保存在本地活动记录中。
}

function parseLocalLearningEvents() {
  try {
    const events = JSON.parse(localStorage.getItem("learning_events") || "[]");
    return Array.isArray(events) ? events : [];
  } catch (error) {
    return [];
  }
}

function setCurrentLearningNode(node) {
  if (!node || node.level === "overview") {
    return;
  }
  learningState.currentNodeId = node.nodeId || node.id || DEFAULT_NODE_ID;
  learningState.currentNodeName = node.name || "当前知识点";
  updateCurrentLearningNodeText();
}

function updateCurrentLearningNodeText() {
  const target = document.getElementById("currentLearningNode");
  if (!target) {
    return;
  }
  target.textContent = `${learningState.currentNodeId} · ${learningState.currentNodeName}`;
}

function getCurrentUserId() {
  const input = document.getElementById("learningUserInput");
  const value = Number(input?.value || DEFAULT_USER_ID);
  return Number.isInteger(value) && value > 0 ? value : DEFAULT_USER_ID;
}

function setPracticeFilter(filter) {
  practiceState.filter = filter || "all";
  document.querySelectorAll(".practice-filter").forEach((button) => {
    button.classList.toggle("active", button.dataset.practiceFilter === practiceState.filter);
  });
  renderPracticeList();
}

function renderPracticeList() {
  const target = document.getElementById("practiceList");
  if (!target) {
    return;
  }

  const questions = practiceQuestions.filter((question) => (
    practiceState.filter === "all" || question.module === practiceState.filter
  ));

  target.innerHTML = questions.map((question) => renderPracticeQuestion(question)).join("");
  target.querySelectorAll(".practice-option").forEach((button) => {
    button.addEventListener("click", () => submitPracticeAnswer(
      button.dataset.questionId,
      Number(button.dataset.optionIndex),
    ));
  });
  updatePracticeScore();
}

function renderPracticeQuestion(question) {
  const answered = practiceState.answered.get(question.id);
  const resultClass = answered
    ? answered.isCorrect ? "correct" : "wrong"
    : "";
  const resultHtml = answered
    ? `
      <div class="practice-explanation ${resultClass}">
        <strong>${answered.isCorrect ? "回答正确" : "回答错误"}</strong>
        <p>${escapeHtml(question.explanation)}</p>
      </div>
    `
    : "";

  return `
    <article class="practice-card ${resultClass}">
      <div class="practice-card-header">
        <span>${escapeHtml(question.moduleName)}</span>
        <strong>${escapeHtml(question.nodeId)} · ${escapeHtml(question.nodeName)}</strong>
      </div>
      <h4>${escapeHtml(question.question)}</h4>
      <div class="practice-options">
        ${question.options.map((option, index) => {
          const selected = answered?.selectedIndex === index;
          const correct = answered && question.answer === index;
          const optionClass = [
            selected ? "selected" : "",
            correct ? "correct-option" : "",
          ].filter(Boolean).join(" ");
          return `
            <button class="practice-option ${optionClass}" type="button" data-question-id="${escapeHtml(question.id)}" data-option-index="${index}">
              <span>${String.fromCharCode(65 + index)}</span>
              <strong>${escapeHtml(option)}</strong>
            </button>
          `;
        }).join("")}
      </div>
      ${resultHtml}
    </article>
  `;
}

async function submitPracticeAnswer(questionId, selectedIndex) {
  const question = practiceQuestions.find((item) => item.id === questionId);
  if (!question) {
    return;
  }

  const isCorrect = selectedIndex === question.answer;
  practiceState.answered.set(question.id, {
    selectedIndex,
    isCorrect,
  });
  learningState.currentNodeId = question.nodeId;
  learningState.currentNodeName = question.nodeName;
  updateCurrentLearningNodeText();
  renderPracticeList();

  try {
    const response = await postJson("/api/learning/update-mastery", {
      user_id: getCurrentUserId(),
      node_id: question.nodeId,
      correct: isCorrect,
    });
    if (!response.ok) {
      throw new Error("答题事件记录失败");
    }
  } catch (error) {
    const localEvents = parseLocalLearningEvents();
    localEvents.push({
      user_id: getCurrentUserId(),
      node_id: question.nodeId,
      node_name: question.nodeName,
      event_type: "answer",
      is_correct: isCorrect,
      timestamp: new Date().toISOString(),
    });
    localStorage.setItem("learning_events", JSON.stringify(localEvents.slice(-100)));
  }
}

function updatePracticeScore() {
  const totalAnswered = practiceState.answered.size;
  const correctCount = Array.from(practiceState.answered.values())
    .filter((item) => item.isCorrect).length;
  const accuracy = totalAnswered
    ? Math.round((correctCount / totalAnswered) * 100)
    : 0;

  document.getElementById("practiceAccuracy").textContent = `${accuracy}%`;
  document.getElementById("practiceProgress").textContent = totalAnswered
    ? `已完成 ${totalAnswered}/${practiceQuestions.length} 题，正确 ${correctCount} 题。`
    : "尚未答题。";
}

async function loadLearningReport(options = {}) {
  updateCurrentLearningNodeText();
  const chartBox = document.getElementById("learningChart");
  const weakBox = document.getElementById("weakNodes");
  const pathBox = document.getElementById("recommendedPath");
  const userId = getCurrentUserId();

  if (!options.silent) {
    chartBox.textContent = "正在读取学情报告...";
    weakBox.textContent = "正在分析薄弱知识点...";
    pathBox.textContent = "正在生成推荐路径...";
  }

  try {
    const response = await fetchLearningReport(userId);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "学情报告请求失败");
    }

    const report = normalizeLearningReport(data);
    renderLearningReport(report);
    await loadRecommendedLearningPath(report);
  } catch (error) {
    const report = buildLocalLearningReport();
    renderLearningReport(report);
    await loadRecommendedLearningPath(report);
    if (!options.silent) {
      chartBox.insertAdjacentHTML("beforeend", `<p class="data-source-note">学情 API 尚未接入，当前使用本地练习记录。</p>`);
    }
  }
}

async function fetchLearningReport(userId) {
  const paths = [
    `/api/learning/report?user_id=${encodeURIComponent(userId)}`,
    `/api/learning-report?user_id=${encodeURIComponent(userId)}`,
  ];
  let lastResponse;
  for (const path of paths) {
    const response = await fetch(`${API_BASE_URL}${path}`);
    if (response.ok || response.status !== 404) return response;
    lastResponse = response;
  }
  return lastResponse;
}

function normalizeLearningReport(raw) {
  const mastered = normalizeLearningNodes(raw.mastered || raw.mastered_nodes || [], "mastered", 4);
  const weak = normalizeLearningNodes(raw.weak || raw.weak_nodes || [], "weak", 1);
  const unlearned = normalizeLearningNodes(raw.unlearned || raw.unlearned_nodes || [], "unlearned", 0);
  const records = raw.node_mastery || raw.nodes || raw.mastery || [];
  if (Array.isArray(records)) {
    records.forEach((record) => {
      const level = Number(record.level ?? record.mastery_level ?? 0);
      const status = level >= 3 ? "mastered" : level === 0 ? "unlearned" : level === 1 ? "weak" : "learning";
      const target = status === "mastered" ? mastered : status === "unlearned" ? unlearned : weak;
      if (!target.some((node) => node.node_id === record.node_id)) {
        target.push(normalizeLearningNode(record, status, level));
      }
    });
  }
  return {
    ...raw,
    mastered,
    weak,
    unlearned,
    recommended_path: raw.recommended_path || raw.path || [],
    module_scores: raw.module_scores || raw.radar || raw.radar_data || null,
    local: Boolean(raw.local),
  };
}

function normalizeLearningNodes(nodes, status, fallbackLevel) {
  if (!Array.isArray(nodes)) return [];
  return nodes.map((node) => normalizeLearningNode(
    typeof node === "string" ? { node_id: node, name: findNodeName(node) } : node,
    status,
    fallbackLevel,
  ));
}

function normalizeLearningNode(node, status, fallbackLevel) {
  return {
    ...node,
    node_id: node.node_id || node.id || "",
    name: node.name || node.node_name || findNodeName(node.node_id || node.id) || node.node_id || node.id,
    level: Number(node.level ?? node.mastery_level ?? fallbackLevel),
    status,
  };
}

function buildLocalLearningReport() {
  const events = parseLocalLearningEvents();
  const stats = new Map();
  events.forEach((event) => {
    if (!event.node_id) return;
    if (!stats.has(event.node_id)) stats.set(event.node_id, { total: 0, correct: 0, name: event.node_name });
    if (event.event_type === "answer") {
      const stat = stats.get(event.node_id);
      stat.total += 1;
      if (event.is_correct) stat.correct += 1;
    }
  });
  const mastered = [];
  const weak = [];
  stats.forEach((stat, nodeId) => {
    const accuracy = stat.total ? stat.correct / stat.total : 0;
    const node = { node_id: nodeId, name: stat.name || findNodeName(nodeId), answer_count: stat.total, accuracy };
    if (stat.total && accuracy >= 0.85) mastered.push({ ...node, level: 4, status: "mastered" });
    else weak.push({ ...node, level: accuracy >= 0.6 ? 3 : accuracy >= 0.3 ? 2 : 1, status: "weak" });
  });
  return { mastered, weak, unlearned: [], recommended_path: [], local: true };
}

function renderLearningReport(report) {
  const mastered = Array.isArray(report.mastered) ? report.mastered : [];
  const weak = Array.isArray(report.weak) ? report.weak : [];
  const unlearned = Array.isArray(report.unlearned) ? report.unlearned : [];
  const allNodes = [...mastered, ...weak, ...unlearned];
  const nodeNameMap = new Map(allNodes.map((node) => [node.node_id, node.name]));
  learningState.report = report;
  graphState.masteryByNode = new Map(allNodes.map((node) => [node.node_id, node]));

  document.getElementById("masteredCount").textContent = mastered.length;
  document.getElementById("weakCount").textContent = weak.length;
  document.getElementById("unlearnedCount").textContent = unlearned.length;
  const total = mastered.length + weak.length + unlearned.length;
  const percent = total ? Math.round((mastered.length / total) * 100) : 0;
  document.getElementById("learningProgressPercent").textContent = `${percent}%`;
  document.getElementById("learningProgressLabel").textContent = `总知识点 ${total} · 已掌握 ${mastered.length}`;
  document.getElementById("learningProgressBar").style.width = `${percent}%`;

  renderLearningChart(mastered, weak, unlearned, report.module_scores);
  renderWeakNodes(weak);
  renderRecommendedPath(report.recommended_path || [], nodeNameMap);
  renderDashboard(report);
  if (graphState.loaded) renderKnowledgeGraph();
}

function renderLearningChart(mastered, weak, unlearned, moduleScores) {
  const chartBox = document.getElementById("learningChart");
  if (!window.echarts) {
    chartBox.textContent = "ECharts 加载失败，无法绘制学情图。";
    return;
  }

  chartBox.innerHTML = "";
  if (learningState.chart) {
    learningState.chart.dispose();
  }
  learningState.chart = echarts.init(chartBox);

  const moduleStats = normalizeModuleScores(moduleScores) || buildModuleLearningStats(mastered, weak, unlearned);
  const modules = moduleStats.map((item) => item.moduleName);
  const scores = moduleStats.map((item) => item.score);

  learningState.chart.setOption({
    tooltip: {
      formatter: (params) => {
        const item = moduleStats[params.dataIndex];
        return `${item.moduleName}<br>掌握度：${item.score}%<br>已掌握：${item.mastered}<br>薄弱：${item.weak}<br>未学：${item.unlearned}`;
      },
    },
    radar: { indicator: modules.map((name) => ({ name, max: 100 })), radius: "66%", splitNumber: 4 },
    series: [
      {
        type: "radar",
        data: [{ value: scores, name: "模块掌握度", areaStyle: { color: "rgba(47,143,131,.2)" }, lineStyle: { color: "#2f8f83", width: 3 }, itemStyle: { color: "#1f5f8b" } }],
      },
    ],
  }, true);
}

function normalizeModuleScores(moduleScores) {
  if (!moduleScores) return null;
  if (Array.isArray(moduleScores)) {
    return moduleScores.map((item) => ({ moduleName: item.module || item.name, score: Number(item.score ?? item.value ?? 0), mastered: item.mastered || 0, weak: item.weak || 0, unlearned: item.unlearned || 0 }));
  }
  if (typeof moduleScores === "object") {
    return Object.entries(moduleScores).map(([moduleName, score]) => ({ moduleName, score: Number(score?.score ?? score?.value ?? score ?? 0), mastered: 0, weak: 0, unlearned: 0 }));
  }
  return null;
}

function buildModuleLearningStats(mastered, weak, unlearned) {
  const defaultModules = graphState.modules.length
    ? graphState.modules.map((module) => module.name)
    : ["命题逻辑", "谓词逻辑", "集合论", "数学归纳法", "关系", "图论"];
  const stats = new Map(defaultModules.map((moduleName) => [moduleName, { moduleName, mastered: 0, weak: 0, unlearned: 0 }]));
  [
    ["mastered", mastered],
    ["weak", weak],
    ["unlearned", unlearned],
  ].forEach(([status, nodes]) => {
    nodes.forEach((node) => {
      const moduleName = getModuleNameFromStatus(node);
      if (!stats.has(moduleName)) {
        stats.set(moduleName, { moduleName, mastered: 0, weak: 0, unlearned: 0 });
      }
      stats.get(moduleName)[status] += 1;
    });
  });

  return Array.from(stats.values()).map((item) => {
    const total = item.mastered + item.weak + item.unlearned || 1;
    const score = Math.round(((item.mastered + item.weak * 0.35) / total) * 100);
    return { ...item, score };
  });
}

function renderDashboard(report = learningState.report) {
  const events = parseLocalLearningEvents();
  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - 6);
  weekStart.setHours(0, 0, 0, 0);
  const recentEvents = events.filter((event) => new Date(event.timestamp || 0) >= weekStart);
  const todayKey = formatDateKey(now);
  const todayEvents = recentEvents.filter((event) => formatDateKey(new Date(event.timestamp)) === todayKey);
  const weeklyAnswers = recentEvents.filter((event) => event.event_type === "answer").length;
  const todayMinutes = Math.min(120, new Set(todayEvents.map((event) => String(event.timestamp).slice(0, 13))).size * 8);

  document.getElementById("todayMinutes").textContent = `${todayMinutes} 分钟`;
  document.getElementById("weeklyQuestions").textContent = weeklyAnswers;
  document.getElementById("dashboardCurrentNode").textContent = `${learningState.currentNodeId} · ${learningState.currentNodeName}`;

  const mastered = report?.mastered?.length || 0;
  const weak = report?.weak?.length || 0;
  const unlearned = report?.unlearned?.length || 0;
  const total = mastered + weak + unlearned;
  const progress = total ? Math.round((mastered / total) * 100) : 0;
  document.getElementById("dashboardProgress").textContent = `${progress}%`;
  document.getElementById("dashboardProgressText").textContent = total ? `${mastered}/${total} 个知识点已掌握` : "等待学情数据";
  document.getElementById("dashboardWeakCount").textContent = weak;
  document.getElementById("dashboardSummary").textContent = report?.local
    ? "学情接口待接入，当前概览来自本地练习记录。"
    : "学习数据已同步，建议从薄弱知识点和推荐路径继续。";

  const path = report?.recommended_path || [];
  const first = path[0];
  const nextNodeId = typeof first === "string" ? first : first?.node_id;
  const nextName = typeof first === "string" ? findNodeName(first) : first?.node_name || first?.name;
  document.getElementById("dashboardNextStep").innerHTML = nextNodeId
    ? `<span>推荐知识点</span><strong>${escapeHtml(nextName || nextNodeId)}</strong><small>${escapeHtml(nextNodeId)}</small>`
    : `<span>继续上次学习</span><strong>${escapeHtml(learningState.currentNodeName)}</strong><small>${escapeHtml(learningState.currentNodeId)}</small>`;
  renderActivityChart(recentEvents);
}

function renderActivityChart(events) {
  const target = document.getElementById("activityChart");
  if (!target || !window.echarts) return;
  if (!dashboardState.chart) {
    dashboardState.chart = echarts.init(target);
    window.addEventListener("resize", () => dashboardState.chart?.resize());
  }
  const days = Array.from({ length: 7 }, (_, offset) => {
    const date = new Date();
    date.setDate(date.getDate() - 6 + offset);
    return { key: formatDateKey(date), label: `${date.getMonth() + 1}/${date.getDate()}` };
  });
  const values = days.map((day) => events.filter((event) => formatDateKey(new Date(event.timestamp)) === day.key).length);
  dashboardState.chart.setOption({
    tooltip: { trigger: "axis", formatter: (items) => `${items[0].axisValue}<br>学习事件 ${items[0].value} 次` },
    grid: { top: 24, right: 20, bottom: 34, left: 42 },
    xAxis: { type: "category", data: days.map((day) => day.label), boundaryGap: false },
    yAxis: { type: "value", minInterval: 1 },
    series: [{ type: "line", data: values, smooth: true, symbolSize: 8, lineStyle: { color: "#1f5f8b", width: 3 }, itemStyle: { color: "#2f8f83" }, areaStyle: { color: "rgba(31,95,139,.12)" } }],
  }, true);
}

function formatDateKey(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function continueLearning() {
  const first = learningState.report?.recommended_path?.[0];
  const nodeId = typeof first === "string" ? first : first?.node_id;
  const nodeName = typeof first === "string" ? findNodeName(first) : first?.node_name || first?.name;
  if (nodeId) {
    learningState.currentNodeId = nodeId;
    learningState.currentNodeName = nodeName || findNodeName(nodeId);
  }
  switchTab("chat");
  document.getElementById("questionInput").value = `请继续讲解 ${learningState.currentNodeName}`;
  document.getElementById("questionInput").focus();
}

function setClassRole(role) {
  classState.role = role === "teacher" ? "teacher" : "student";
  document.querySelectorAll(".role-button").forEach((button) => button.classList.toggle("active", button.dataset.classRole === classState.role));
  document.getElementById("studentClassView").hidden = classState.role !== "student";
  document.getElementById("teacherClassView").hidden = classState.role !== "teacher";
  loadClassWorkspace();
}

async function joinClass(event) {
  event.preventDefault();
  const inviteCode = document.getElementById("inviteCodeInput").value.trim();
  if (!inviteCode) return;
  const payload = { user_id: getCurrentUserId(), invite_code: inviteCode };
  try {
    const response = await postJson("/api/class/join", payload);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "加入班级失败");
    classState.studentClass = data;
    document.getElementById("inviteCodeInput").value = "";
    await loadClassWorkspace();
  } catch (error) {
    showClassError("studentClassList", `加入失败：${error.message}`);
  }
}

async function createClass(event) {
  event.preventDefault();
  const name = document.getElementById("classNameInput").value.trim();
  if (!name) return;
  const payload = { name, teacher_id: getCurrentUserId() };
  try {
    const response = await postJson("/api/class/create", payload);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "创建班级失败");
    classState.selectedClassId = data.id;
    document.getElementById("classNameInput").value = "";
    await loadClassWorkspace();
    await loadTeacherClassDetails(data.id);
  } catch (error) {
    showClassError("teacherClassList", `创建失败：${error.message}`);
  }
}

async function requestLearningShare(event) {
  event.preventDefault();
  const targetUserId = Number(document.getElementById("shareTargetInput").value.trim());
  if (!targetUserId) return;
  const status = document.getElementById("shareRequestStatus");
  try {
    const response = await postJson("/api/share/request", { requester_id: getCurrentUserId(), target_user_id: targetUserId });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "申请发送失败");
    status.textContent = `已向用户 ${targetUserId} 发送授权申请，申请编号 ${data.request_id}。`;
  } catch (error) {
    status.textContent = `申请失败：${error.message}`;
  }
  document.getElementById("shareTargetInput").value = "";
}

async function loadClassWorkspace() {
  const userId = getCurrentUserId();
  const [studentResult, teacherResult, shareResult] = await Promise.allSettled([
    fetchApiJson(`/api/class/student/${userId}`),
    fetchApiJson(`/api/class/teacher/${userId}`),
    fetchApiJson(`/api/share/requests?target_user_id=${userId}`),
  ]);

  if (studentResult.status === "fulfilled") {
    classState.studentClass = studentResult.value.class;
    renderClassList("studentClassList", classState.studentClass ? [classState.studentClass] : [], "已加入");
  } else {
    showClassError("studentClassList", `班级读取失败：${studentResult.reason.message}`);
  }

  if (teacherResult.status === "fulfilled") {
    classState.teacherClasses = teacherResult.value.classes || [];
    renderClassList("teacherClassList", classState.teacherClasses, "教师", true);
    if (!classState.teacherClasses.length) renderEmptyClassOverview();
  } else {
    showClassError("teacherClassList", `班级读取失败：${teacherResult.reason.message}`);
    renderEmptyClassOverview("教师班级数据暂不可用。");
  }

  if (shareResult.status === "fulfilled") {
    renderIncomingShareRequests(shareResult.value.requests || []);
  } else {
    showClassError("incomingShareRequests", `申请读取失败：${shareResult.reason.message}`);
  }
}

function renderClassList(targetId, items, roleLabel, selectable = false) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!items.length) {
    target.className = "data-list empty-state";
    target.textContent = roleLabel === "教师" ? "尚未创建班级。" : "尚未加入班级。";
    return;
  }
  target.className = "data-list";
  target.innerHTML = items.map((item) => `<article class="class-row"><div><strong>${escapeHtml(item.name || "未命名班级")}</strong><span>${escapeHtml(roleLabel)} · 邀请码 ${escapeHtml(item.invite_code || "--")}</span></div>${selectable ? `<button type="button" class="class-detail-button" data-class-id="${Number(item.id)}">查看学情</button>` : '<span class="source-badge synced">已同步</span>'}</article>`).join("");
  target.querySelectorAll(".class-detail-button").forEach((button) => {
    button.addEventListener("click", () => loadTeacherClassDetails(Number(button.dataset.classId)));
  });
}

async function loadTeacherClassDetails(classId) {
  classState.selectedClassId = classId;
  const overview = document.getElementById("classOverview");
  const studentList = document.getElementById("classStudentList");
  overview.innerHTML = '<div><span>状态</span><strong>读取中</strong></div>';
  studentList.className = "student-report-list empty-state";
  studentList.textContent = "正在读取学生学情...";
  try {
    const [studentsData, reportData] = await Promise.all([
      fetchApiJson(`/api/class/${classId}/students`),
      fetchApiJson(`/api/class/${classId}/report`),
    ]);
    const reports = reportData.reports || [];
    const average = reports.length
      ? Math.round(reports.reduce((sum, item) => sum + Number(item.summary?.overall_accuracy || 0), 0) / reports.length * 100)
      : 0;
    const attention = reports.filter((item) => (item.weak_nodes || []).length > 0).length;
    overview.innerHTML = `<div><span>学生人数</span><strong>${studentsData.students?.length || 0}</strong></div><div><span>平均正确率</span><strong>${average}%</strong></div><div><span>待关注学生</span><strong>${attention}</strong></div>`;
    renderStudentReports(reports);
  } catch (error) {
    renderEmptyClassOverview(`班级报告读取失败：${error.message}`);
  }
}

function renderStudentReports(reports) {
  const target = document.getElementById("classStudentList");
  if (!reports.length) {
    target.className = "student-report-list empty-state";
    target.textContent = "该班级暂无学生。";
    return;
  }
  target.className = "student-report-list";
  target.innerHTML = reports.map((item) => `<article><div><strong>${escapeHtml(item.user?.name || `用户 ${item.user?.id}`)}</strong><span>答题 ${Number(item.summary?.total_answers || 0)} 次</span></div><span class="mastery-badge ${(item.weak_nodes || []).length ? "weak" : "mastered"}">${(item.weak_nodes || []).length ? `薄弱 ${(item.weak_nodes || []).length}` : "状态良好"}</span></article>`).join("");
}

function renderIncomingShareRequests(requests) {
  const target = document.getElementById("incomingShareRequests");
  if (!requests.length) {
    target.className = "approval-list empty-state";
    target.textContent = "暂无待处理申请。";
    return;
  }
  target.className = "approval-list";
  target.innerHTML = requests.map((item) => `<article><div><strong>${escapeHtml(item.requester_name || `用户 ${item.requester_id}`)}</strong><span>申请查看你的学情</span></div><div class="approval-actions"><button type="button" data-share-id="${Number(item.id)}" data-approved="true">同意</button><button type="button" class="ghost-button" data-share-id="${Number(item.id)}" data-approved="false">拒绝</button></div></article>`).join("");
  target.querySelectorAll("[data-share-id]").forEach((button) => {
    button.addEventListener("click", () => decideShareRequest(Number(button.dataset.shareId), button.dataset.approved === "true"));
  });
}

async function decideShareRequest(requestId, approved) {
  try {
    const response = await postJson("/api/share/approve", { request_id: requestId, target_user_id: getCurrentUserId(), approved });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "处理申请失败");
    document.getElementById("shareRequestStatus").textContent = approved ? "已同意学情查看申请。" : "已拒绝学情查看申请。";
    await loadClassWorkspace();
  } catch (error) {
    document.getElementById("shareRequestStatus").textContent = `处理失败：${error.message}`;
  }
}

function renderEmptyClassOverview(message = "请选择一个班级查看学生学情。") {
  document.getElementById("classOverview").innerHTML = '<div><span>学生人数</span><strong>0</strong></div><div><span>平均正确率</span><strong>--</strong></div><div><span>待关注学生</span><strong>0</strong></div>';
  const target = document.getElementById("classStudentList");
  target.className = "student-report-list empty-state";
  target.textContent = message;
}

function showClassError(targetId, message) {
  const target = document.getElementById(targetId);
  if (!target) return;
  target.className = `${targetId === "incomingShareRequests" ? "approval-list" : "data-list"} error-state`;
  target.textContent = message;
}

async function fetchApiJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `请求失败（${response.status}）`);
  return data;
}

async function postJson(path, payload) {
  return fetch(`${API_BASE_URL}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

async function startExam() {
  const modules = Array.from(document.querySelectorAll(".exam-module-grid input:checked")).map((input) => input.value);
  if (!modules.length) return;
  const localQuestions = practiceQuestions.filter((question) => modules.includes(question.module)).slice(0, 6);
  examState.questions = localQuestions;
  examState.answers.clear();
  try {
    const response = await postJson("/api/exam/generate", { user_id: getCurrentUserId(), node_ids: localQuestions.map((question) => question.nodeId), count: 6 });
    const data = await response.json();
    if (response.ok && Array.isArray(data.questions) && data.questions.length) {
      examState.examId = data.exam_id || null;
      examState.questions = data.questions.map((question, index) => normalizeExamQuestion(question, index));
    }
  } catch (error) {
    // 队员3接口尚未合并时使用经过验证的本地题库。
  }
  document.getElementById("examSetup").hidden = true;
  document.getElementById("examResult").hidden = true;
  document.getElementById("examForm").hidden = false;
  renderExamPaper();
  startExamTimer();
}

function normalizeExamQuestion(question, index) {
  return {
    id: question.id || `server_exam_${index}`,
    nodeId: question.node_id || question.nodeId || "",
    nodeName: question.node_name || question.nodeName || "知识点",
    moduleName: question.module || question.moduleName || "离散数学",
    question: question.content || question.question || "",
    options: question.options || [],
    answer: Number(question.answer ?? question.correct_index ?? 0),
    explanation: question.explanation || question.analysis || "提交后查看解析。",
  };
}

function renderExamPaper() {
  const form = document.getElementById("examForm");
  form.innerHTML = examState.questions.map((question, questionIndex) => `
    <fieldset class="exam-question">
      <legend><span>${questionIndex + 1}</span>${escapeHtml(question.question)}</legend>
      <div class="exam-options">
        ${question.options.map((option, optionIndex) => `<label><input type="radio" name="exam-${questionIndex}" value="${optionIndex}"><span>${String.fromCharCode(65 + optionIndex)}</span>${escapeHtml(option)}</label>`).join("")}
      </div>
    </fieldset>
  `).join("") + `<button type="submit" class="submit-exam-button">提交试卷</button>`;
  form.onchange = () => {
    examState.questions.forEach((question, index) => {
      const selected = form.querySelector(`input[name="exam-${index}"]:checked`);
      if (selected) examState.answers.set(question.id, Number(selected.value));
    });
    updateExamStatus();
  };
  form.onsubmit = submitExam;
  updateExamStatus();
}

function startExamTimer() {
  clearInterval(examState.timer);
  examState.secondsLeft = 15 * 60;
  renderExamTimer();
  examState.timer = setInterval(() => {
    examState.secondsLeft -= 1;
    renderExamTimer();
    if (examState.secondsLeft <= 0) submitExam(new Event("submit"));
  }, 1000);
}

function renderExamTimer() {
  const minutes = Math.floor(examState.secondsLeft / 60);
  const seconds = examState.secondsLeft % 60;
  const target = document.getElementById("examTimer");
  target.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  target.classList.toggle("urgent", examState.secondsLeft <= 120);
}

async function submitExam(event) {
  event.preventDefault();
  clearInterval(examState.timer);
  const results = examState.questions.map((question) => {
    const selected = examState.answers.get(question.id);
    return { question, selected, isCorrect: selected === question.answer };
  });
  const correct = results.filter((result) => result.isCorrect).length;
  const score = results.length ? Math.round((correct / results.length) * 100) : 0;
  const payload = { exam_id: examState.examId, user_id: getCurrentUserId(), answers: results.map((result) => ({ question_id: result.question.id, node_id: result.question.nodeId, answer: result.selected })) };
  let synced = false;
  let serverResult = null;
  try {
    const response = await postJson("/api/exam/submit", payload);
    synced = response.ok;
    if (response.ok) serverResult = await response.json();
  } catch (error) {
    synced = false;
  }
  if (!synced) results.forEach((result) => recordExamMastery(result));
  const displayScore = serverResult?.score ?? score;
  const displayCorrect = serverResult?.correct_count ?? correct;
  const target = document.getElementById("examResult");
  target.hidden = false;
  target.innerHTML = `
    <div class="exam-score"><span>本次得分</span><strong>${displayScore}</strong><small>${displayCorrect}/${results.length} 题正确 · ${synced ? "已同步服务器" : "本地判分"}</small></div>
    <div class="exam-review">${results.map((result, index) => `<article class="${result.isCorrect ? "correct" : "wrong"}"><strong>${index + 1}. ${result.isCorrect ? "正确" : "错误"}</strong><p>${escapeHtml(result.question.explanation)}</p></article>`).join("")}</div>
    <button id="restartExamButton" type="button">重新测评</button>`;
  document.getElementById("examForm").hidden = true;
  document.getElementById("restartExamButton").addEventListener("click", resetExam);
  updateExamStatus();
  renderDashboard();
}

async function recordExamMastery(result) {
  const event = { user_id: getCurrentUserId(), node_id: result.question.nodeId, node_name: result.question.nodeName, event_type: "answer", is_correct: result.isCorrect, timestamp: new Date().toISOString() };
  const localEvents = parseLocalLearningEvents();
  localEvents.push(event);
  localStorage.setItem("learning_events", JSON.stringify(localEvents.slice(-200)));
  try {
    await postJson("/api/learning/update-mastery", { user_id: event.user_id, node_id: event.node_id, correct: event.is_correct });
  } catch (error) {
    // 本地记录保留，后端接口就绪后新答题会自动同步。
  }
}

function resetExam() {
  clearInterval(examState.timer);
  examState.questions = [];
  examState.examId = null;
  examState.answers.clear();
  examState.secondsLeft = 900;
  renderExamTimer();
  document.getElementById("examSetup").hidden = false;
  document.getElementById("examForm").hidden = true;
  document.getElementById("examResult").hidden = true;
  updateExamStatus();
}

function updateExamStatus() {
  document.getElementById("examQuestionCount").textContent = examState.questions.length;
  document.getElementById("examAnsweredCount").textContent = examState.answers.size;
}

function getModuleNameFromStatus(node) {
  const name = String(node.name || "未分类");
  return name.split(">").map((part) => part.trim()).filter(Boolean)[0] || "未分类";
}

function renderWeakNodes(weak) {
  const target = document.getElementById("weakNodes");
  if (!weak.length) {
    target.innerHTML = `<p class="empty-state">当前没有薄弱知识点。继续在图谱中浏览或答题后会更新。</p>`;
    return;
  }

  target.innerHTML = weak.slice(0, 8).map((node) => `
    <button class="learning-node-button weak-node" type="button" data-node-id="${escapeHtml(node.node_id)}" data-node-name="${escapeHtml(node.name)}">
      <strong>${escapeHtml(shortenNodeName(node.name))}</strong>
      <span>${formatLearningStat(node)}</span>
    </button>
  `).join("");
  bindLearningNodeButtons(target);
}

function renderRecommendedPath(path, nodeNameMap) {
  const target = document.getElementById("recommendedPath");
  if (!path.length) {
    target.textContent = "暂无推荐路径。";
    return;
  }

  target.innerHTML = path.slice(0, 10).map((pathItem, index) => {
    const nodeId = typeof pathItem === "string" ? pathItem : pathItem.node_id || pathItem.id;
    const name = typeof pathItem === "string"
      ? nodeNameMap.get(nodeId) || nodeId
      : pathItem.node_name || pathItem.name || nodeNameMap.get(nodeId) || nodeId;
    return `
      <button class="path-node" type="button" data-node-id="${escapeHtml(nodeId)}" data-node-name="${escapeHtml(name)}">
        <span>${String(index + 1).padStart(2, "0")}</span>
        <strong>${escapeHtml(shortenNodeName(name))}</strong>
      </button>
    `;
  }).join("");
  bindLearningNodeButtons(target);
}

async function loadRecommendedLearningPath(report) {
  const weakNodes = report.weak.map((node) => node.node_id).filter(Boolean);
  const levels = Object.fromEntries(report.weak.map((node) => [node.node_id, node.level ?? 1]));
  if (!weakNodes.length) {
    graphState.recommendedPath = [];
    return;
  }
  try {
    const response = await fetch(`${KB_API_BASE_URL}/kb/learning-path`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weak_nodes: weakNodes, levels }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "学习路径推荐失败");
    const path = data.path || data.recommended_path || [];
    graphState.recommendedPath = path.map((item) => typeof item === "string" ? item : item.node_id).filter(Boolean);
    renderRecommendedPath(path, new Map(report.weak.map((node) => [node.node_id, node.name])));
    report.recommended_path = path;
    renderDashboard(report);
    if (graphState.loaded) renderKnowledgeGraph();
  } catch (error) {
    graphState.recommendedPath = weakNodes;
    renderRecommendedPath(weakNodes, new Map(report.weak.map((node) => [node.node_id, node.name])));
  }
}

async function loadRecommendedQuestions(node) {
  const target = document.getElementById("graphRecommendedQuestions");
  const badge = document.getElementById("graphMasteryBadge");
  const button = document.getElementById("loadGraphRecommendationsButton");
  const nodeId = node?.nodeId || node?.id;
  if (!target || !nodeId || node.level === "overview") return;
  graphState.selectedNode = node;
  const mastery = graphState.masteryByNode.get(nodeId);
  const level = Number(mastery?.level ?? 0);
  const status = getMasteryStatus(mastery);
  badge.className = `mastery-badge ${status}`;
  badge.textContent = getMasteryLabel(status, level);
  target.textContent = "正在按当前掌握度生成推荐题目...";
  button.disabled = true;
  button.textContent = "正在获取...";
  try {
    let questions = await fetchRecommendedQuestions(nodeId, level, 3);
    if (!questions.length) {
      const descendants = getQuestionCandidateNodes(node);
      const batches = await Promise.all(descendants.slice(0, 6).map((candidate) => {
        const candidateMastery = graphState.masteryByNode.get(candidate.nodeId);
        return fetchRecommendedQuestions(candidate.nodeId, Number(candidateMastery?.level ?? level), 3)
          .catch(() => []);
      }));
      questions = batches.flat();
    }
    renderGraphRecommendedQuestions(deduplicateQuestions(questions).slice(0, 6), node);
  } catch (error) {
    target.innerHTML = `<p class="muted-line">${escapeHtml(error.message)}。</p>`;
  } finally {
    button.disabled = false;
    button.textContent = "重新获取推荐题目";
  }
}

async function loadSelectedGraphRecommendations() {
  const target = document.getElementById("graphRecommendedQuestions");
  const node = graphState.selectedNode || findGraphNodeByNodeId(learningState.currentNodeId);
  if (!node) {
    target.innerHTML = '<p class="muted-line">请先点击左侧知识图谱中的知识点。</p>';
    return;
  }
  await loadRecommendedQuestions(node);
}

async function fetchRecommendedQuestions(nodeId, level, count) {
  const response = await fetch(`${KB_API_BASE_URL}/kb/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, level, count }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "题目推荐失败");
  return Array.isArray(data.questions) ? data.questions : [];
}

function getQuestionCandidateNodes(node) {
  if (node.type === "module") {
    const concepts = node.children || [];
    return [...concepts.flatMap((concept) => concept.items || []), ...concepts];
  }
  if (node.type === "concept") {
    return node.items || [];
  }
  return [];
}

function findGraphNodeByNodeId(nodeId) {
  return Array.from(graphState.nodeIndex.values()).find((node) => (node.nodeId || node.id) === nodeId) || null;
}

function deduplicateQuestions(questions) {
  const seen = new Set();
  return questions.filter((question) => {
    const content = question.content || question.question || "";
    const key = content.trim().replace(/\s+/g, " ");
    if (!content || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function renderGraphRecommendedQuestions(questions, node) {
  const target = document.getElementById("graphRecommendedQuestions");
  if (!questions.length) {
    target.innerHTML = `<p class="muted-line">该节点暂未映射题目，可先查看教材内容。</p>`;
    return;
  }
  target.innerHTML = questions.map((question, index) => `
    <button class="recommended-question" type="button" data-question-index="${index}">
      <span>难度 ${escapeHtml(String(question.difficulty ?? "--"))} · ${escapeHtml(question.type || "练习题")}</span>
      <strong>${escapeHtml(question.content || question.question || "题目内容待补充")}</strong>
    </button>
  `).join("");
  target.querySelectorAll(".recommended-question").forEach((button) => {
    button.addEventListener("click", () => {
      const question = questions[Number(button.dataset.questionIndex)];
      switchTab("chat");
      document.getElementById("questionInput").value = `请引导我完成这道题：${question.content || question.question}`;
      learningState.currentNodeId = question.node_id || node.nodeId || node.id;
      learningState.currentNodeName = findNodeName(learningState.currentNodeId);
      updateCurrentLearningNodeText();
    });
  });
}

function bindLearningNodeButtons(container) {
  container.querySelectorAll("[data-node-id]").forEach((button) => {
    button.addEventListener("click", () => {
      learningState.currentNodeId = button.dataset.nodeId || DEFAULT_NODE_ID;
      learningState.currentNodeName = button.dataset.nodeName || "推荐知识点";
      updateCurrentLearningNodeText();
      switchTab("chat");
      document.getElementById("questionInput").value = `请讲解 ${learningState.currentNodeName}`;
      document.getElementById("questionInput").focus();
    });
  });
}

function shortenNodeName(name) {
  const parts = String(name || "").split(">").map((part) => part.trim()).filter(Boolean);
  return parts.at(-1) || name || "未知知识点";
}

function formatLearningStat(node) {
  const viewCount = node.view_count || 0;
  const answerCount = node.answer_count || 0;
  if (typeof node.accuracy === "number") {
    return `浏览 ${viewCount} 次 · 答题 ${answerCount} 次 · 正确率 ${Math.round(node.accuracy * 100)}%`;
  }
  return `浏览 ${viewCount} 次 · 暂无答题记录`;
}

function resetKnowledgeGraph() {
  graphState.expandedModules.clear();
  graphState.expandedConcepts.clear();
  renderKnowledgeGraph();
  showGraphNodeDetail({
    name: "知识图谱",
    level: "overview",
    description: "已收起全部节点。点击模块展开子概念。",
  });
}

function toggleSetValue(set, value) {
  if (set.has(value)) {
    set.delete(value);
  } else {
    set.add(value);
  }
}

function getItemCategory(type) {
  const normalized = String(type || "").toLowerCase();
  if (normalized === "definition") return 2;
  if (normalized === "theorem") return 3;
  if (normalized === "example") return 4;
  if (normalized === "rule") return 5;
  return 2;
}

function getTypeLabel(type) {
  const labels = {
    overview: "总览",
    module: "模块",
    concept: "子概念",
    definition: "定义",
    theorem: "定理",
    example: "例题",
    rule: "规则",
    item: "知识条目",
  };
  return labels[String(type || "").toLowerCase()] || type || "未知类型";
}

function getNodeColor(type, category) {
  const colors = {
    module: "#1f5f8b",
    concept: "#2f8f83",
    definition: "#6b73d6",
    theorem: "#b54708",
    example: "#12a1a7",
    rule: "#7a5af8",
  };
  return colors[String(type || "").toLowerCase()] || ["#1f5f8b", "#2f8f83", "#6b73d6"][category] || "#6b73d6";
}

function getGraphNodeStyle(node) {
  const mastery = getNodeMastery(node);
  const status = getMasteryStatus(mastery);
  const colors = {
    mastered: "#20805f",
    learning: "#d39a16",
    weak: "#c43d35",
    unlearned: "#8291a2",
  };
  return {
    color: colors[status],
    borderColor: status === "weak" ? "#8e211c" : "#ffffff",
    borderWidth: status === "weak" ? (graphState.weakPulse ? 5 : 2) : 1,
    shadowBlur: status === "weak" ? (graphState.weakPulse ? 24 : 10) : 4,
    shadowColor: status === "weak" ? "rgba(196,61,53,.48)" : "rgba(24,50,76,.12)",
  };
}

function getNodeMastery(node) {
  if (!node) return null;
  const direct = graphState.masteryByNode.get(node.nodeId || node.id);
  if (direct) return direct;
  const descendants = node.type === "module"
    ? node.children.flatMap((child) => [child, ...(child.items || [])])
    : node.type === "concept" ? node.items || [] : [];
  const records = descendants.map((item) => graphState.masteryByNode.get(item.nodeId || item.id)).filter(Boolean);
  if (!records.length) return null;
  return { level: records.reduce((sum, record) => sum + Number(record.level || 0), 0) / records.length };
}

function getMasteryStatus(mastery) {
  if (!mastery) return "unlearned";
  if (mastery.status === "weak") return "weak";
  const level = Number(mastery.level ?? mastery.mastery_level ?? 0);
  if (level >= 3) return "mastered";
  if (level === 2) return "learning";
  if (level === 1) return "weak";
  return "unlearned";
}

function getMasteryLabel(status, level) {
  const labels = { mastered: level >= 4 ? "熟练" : "已掌握", learning: "理解中", weak: "薄弱", unlearned: "未学" };
  return labels[status];
}

function isRecommendedNode(node) {
  return Boolean(node && graphState.recommendedPath.includes(node.nodeId || node.id));
}

function findNodeName(nodeId) {
  for (const module of graphState.modules) {
    if (module.nodeId === nodeId) return module.name;
    for (const concept of module.children || []) {
      if (concept.nodeId === nodeId) return `${module.name} > ${concept.name}`;
      const item = (concept.items || []).find((entry) => entry.nodeId === nodeId);
      if (item) return `${module.name} > ${concept.name} > ${item.name}`;
    }
  }
  return nodeId || "未知知识点";
}

function truncateText(text, length) {
  const value = String(text || "");
  return value.length > length ? `${value.slice(0, length)}...` : value;
}

function formatAnswerHtml(text) {
  const mathSegments = [];
  // 学生作业中的图片引用指向已丢失的 Typora 本地截图，显示时直接忽略。
  const normalized = normalizeLatexText(text).replace(
    /!\[[^\]]*\]\(\s*(?:<[^>]+>|[^\r\n)]+)\s*\)/g,
    "",
  );
  const protectedText = normalized.replace(
    /\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)/g,
    (formula) => {
      const token = `MATHJAXTOKEN${mathSegments.length}ENDTOKEN`;
      mathSegments.push(formula);
      return token;
    },
  );

  let html = escapeHtml(protectedText)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    // 对没有数学分隔符的残缺 LaTeX 做可读降级。
    .replace(/\\rightarrow|\\to/g, "→")
    .replace(/\\leftrightarrow/g, "↔")
    .replace(/\\wedge|\\land/g, "∧")
    .replace(/\\vee|\\lor/g, "∨")
    .replace(/\\neg|\\lnot/g, "¬")
    .replace(/\\in/g, "∈")
    .replace(/\\notin/g, "∉")
    .replace(/\\forall/g, "∀")
    .replace(/\\exists/g, "∃")
    .replace(/\\neq/g, "≠")
    .replace(/\\leq?/g, "≤")
    .replace(/\\geq?/g, "≥")
    .replace(/\\tag\{([^{}]+)\}/g, "（$1）")
    .replace(/\\notag\b/g, "");

  html = renderMarkdownBlocks(html);

  mathSegments.forEach((formula, index) => {
    html = html.replace(`MATHJAXTOKEN${index}ENDTOKEN`, escapeHtml(formula));
  });
  return html;
}

function renderMarkdownBlocks(html) {
  const lines = html.split("\n");
  const hasBlockSyntax = lines.some((line) => (
    /^\s*$/.test(line)
    || /^\s{0,3}#{1,6}\s+/.test(line)
    || /^\s*[-*+]\s+/.test(line)
    || /^\s*\d+[.)]\s+/.test(line)
    || /^\s*&gt;\s+/.test(line)
  ));
  if (!hasBlockSyntax) {
    return html.replace(/\n/g, "<br>");
  }

  const output = [];
  let paragraph = [];
  let listType = "";

  const flushParagraph = () => {
    if (paragraph.length) {
      output.push(`<p class="answer-paragraph">${paragraph.join("<br>")}</p>`);
      paragraph = [];
    }
  };
  const closeList = () => {
    if (listType) {
      output.push(`</${listType}>`);
      listType = "";
    }
  };
  const addListItem = (type, content) => {
    flushParagraph();
    if (listType !== type) {
      closeList();
      output.push(`<${type} class="answer-list">`);
      listType = type;
    }
    output.push(`<li>${content}</li>`);
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      closeList();
      return;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(heading[1].length + 3, 6);
      output.push(`<h${level} class="answer-heading">${heading[2]}</h${level}>`);
      return;
    }

    const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
    if (unordered) {
      addListItem("ul", unordered[1]);
      return;
    }
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      addListItem("ol", ordered[1]);
      return;
    }
    const quote = trimmed.match(/^&gt;\s+(.+)$/);
    if (quote) {
      flushParagraph();
      closeList();
      output.push(`<blockquote class="answer-quote">${quote[1]}</blockquote>`);
      return;
    }

    closeList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  closeList();
  return output.join("");
}

function normalizeLatexText(text) {
  let value = String(text ?? "")
    .replace(/\r\n?/g, "\n")
    .replace(/\u00a0/g, " ");

  // PDF/Markdown 抽取结果中常见的块级环境不能直接嵌套在 HTML 段落里，
  // 统一转换为 MathJax 可稳定处理的 display math。
  value = value.replace(
    /\\begin\{align\*?\}([\s\S]*?)\\end\{align\*?\}/g,
    (_, body) => `\\[\\begin{aligned}${cleanDisplayMath(body)}\\end{aligned}\\]`,
  );
  value = value.replace(
    /\\begin\{(?:equation|gather|multline)\*?\}([\s\S]*?)\\end\{(?:equation|gather|multline)\*?\}/g,
    (_, body) => `\\[${cleanDisplayMath(body)}\\]`,
  );

  // 先把美元分隔符统一为 \(...\) / \[...\]，避免后续 HTML 处理丢失边界。
  value = value.replace(/\$\$([\s\S]*?)\$\$/g, (_, body) => `\\[${cleanDisplayMath(body)}\\]`);
  value = value.replace(/(^|[^\\])\$([^$\n]+?)\$/g, (_, prefix, body) => {
    return `${prefix}\\(${cleanInlineMath(body)}\\)`;
  });

  return value;
}

function cleanDisplayMath(math) {
  return String(math)
    .replace(/\\notag\b/g, "")
    .trim();
}

function cleanInlineMath(math) {
  return String(math)
    .replace(/\\notag\b/g, "")
    .replace(/\\tag\{([^{}]+)\}/g, "\\text{($1)}\\quad ")
    .trim();
}

let mathTypesetQueue = Promise.resolve();

function typesetMath(target) {
  if (!target || !window.MathJax) {
    return;
  }

  const startup = window.MathJax.startup?.promise || Promise.resolve();
  mathTypesetQueue = mathTypesetQueue
    .then(() => startup)
    .then(() => {
      if (!window.MathJax.typesetPromise || !target.isConnected) {
        return;
      }
      window.MathJax.typesetClear?.([target]);
      return window.MathJax.typesetPromise([target]);
    })
    .catch((error) => {
      console.warn("MathJax 公式渲染失败：", error);
    });
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showError(target, message) {
  target.classList.remove("empty-state");
  target.innerHTML = `<p class="error">${message}</p>`;
}

function formatBool(value) {
  return value ? "真" : "假";
}
