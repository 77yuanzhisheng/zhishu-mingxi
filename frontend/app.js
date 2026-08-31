const API_BASE_URL = resolveApiBaseUrl();
const RAG_API_BASE_URL = API_BASE_URL;
const TOOLS_API_BASE_URL = API_BASE_URL;
const KB_API_BASE_URL = API_BASE_URL;
const DEFAULT_USER_ID = 1;
const DEFAULT_NODE_ID = "rel_02";
const AUTH_TOKEN_KEY = "dm_auth_token";

function resolveApiBaseUrl() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("api")?.trim();
  let selected = "";
  if (requested && /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(requested)) {
    selected = requested.replace(/\/$/, "");
    localStorage.setItem("dm_api_base_url", selected);
  }
  return (selected || localStorage.getItem("dm_api_base_url") || "http://127.0.0.1:8000").replace(/\/$/, "");
}

const tabRoutes = {
  dashboard: "/",
  chat: "/chat",
  graph: "/knowledge-graph",
  practice: "/practice",
  learning: "/learning",
  classes: "/classes",
  exam: "/exam",
  tools: "/tools",
  textbook: "/textbook",
};

const titles = {
  dashboard: "个人学习仪表盘",
  chat: "推理大拿 · 课程知识问答",
  tools: "离散数学工具中心",
  graph: "离散数学知识图谱",
  practice: "自测练习",
  learning: "学情分析",
  classes: "班级管理",
  exam: "在线考试",
  textbook: "Web 交互式教材 2.0",
};

const graphState = {
  chart: null,
  modules: [],
  teacherGraph: null,
  teacherLoaded: false,
  dependencies: [],
  nodeIndex: new Map(),
  expandedModules: new Set(),
  expandedConcepts: new Set(),
  view: "tree",
  loaded: false,
  masteryByNode: new Map(),
  recommendedPath: [],
  selectedNode: null,
};

const learningState = {
  currentNodeId: DEFAULT_NODE_ID,
  currentNodeName: "关系性质",
  chart: null,
  report: null,
};

const dashboardState = { chart: null };
const gradingState = { questions: [], selectedQuestion: null, startedAt: Date.now(), loaded: false, ocrFile: null, submitting: false };
const chatState = { sessionId: null };
const authState = { token: localStorage.getItem(AUTH_TOKEN_KEY) || "", user: null };
const classState = { role: null, studentClass: null, teacherClasses: [], selectedClassId: null };
const examState = { examId: null, available: [], questions: [], answers: new Map(), secondsLeft: 900, timer: null, latestTeacherExamId: null };
const extendedToolState = { current: "formula-simplify", hasseChart: null };
const unifiedToolState = { current: "truth" };

const practiceState = {
  filter: "all",
  mode: "choice",
  questionIndex: {
    choice: 0,
    fill: 0,
    proof: 0,
    calc: 0,
    grading: 0,
  },
  answered: new Map(),
  fillQuestions: [],
  fillResults: new Map(),
  proofQuestions: [],
  proofResults: new Map(),
  proofErrors: new Map(),
  proofTexts: new Map(),
  proofStartedAt: new Map(),
  proofSubmitting: new Set(),
  calcQuestions: [],
  calcResults: new Map(),
  calcErrors: new Map(),
  calcTexts: new Map(),
  calcStartedAt: new Map(),
  calcSubmitting: new Set(),
};

let practiceQuestions = [];

// 节点名称兜底字典：当后端 /api/learning/* 报告里没返回 node_name 时，
// 用这里的静态映射补全显示。键是 node_id，值是中文名称。
// 来源：knowledge-graph 端点硬编码的概念名称（队员4 整理）。
const NODE_NAME_FALLBACKS = {
  // 命题逻辑
  pl_01_01: "命题",
  pl_01_02: "联结词",
  pl_02_01: "真值表",
  pl_02_02: "德摩根律",
  pl_03_01: "重言式（永真式）",
  pl_03_02: "主析取范式",
  pl_03_03: "推理规则",
  // 谓词逻辑
  fl_01_01: "谓词 P(x)",
  fl_01_02: "全称量词 ∀xP(x)",
  fl_02_01: "量词否定律",
  fl_02_02: "量词分配律",
  // 集合论
  st_01_01: "集合",
  st_01_02: "子集",
  st_01_03: "幂集",
  st_02_01: "并集",
  st_02_02: "交集",
  st_02_03: "补集",
  // 数学归纳法
  mi_01: "数学归纳法",
  mi_02: "强归纳法",
  // 关系
  relation: "关系",
  rel_01: "关系基本概念",
  rel_02_01: "自反性",
  rel_02_02: "对称性",
  rel_02_03: "传递性",
  rel_03_01: "等价关系",
  rel_04_01: "偏序关系",
  // 图论
  gt_01_01: "图",
  gt_02_01: "路径",
  gt_02_02: "连通性",
  gt_03_01: "握手定理",
  gt_04_01: "欧拉图",
  gt_04_02: "哈密顿图",
  gt_05_01: "树",
  gt_06_01: "图着色",
};

// 模块名兜底字典：按 node_id 前缀（pl/fl/st/...）给出模块中文名。
const NODE_MODULE_FALLBACKS = {
  pl: "命题逻辑知识点",
  fl: "谓词逻辑知识点",
  st: "集合论知识点",
  mi: "数学归纳法知识点",
  rel: "关系知识点",
  gt: "图论知识点",
  nt: "初等数论知识点",
  cm: "组合数学知识点",
  ag: "代数结构知识点",
};
const FALLBACK_PRACTICE_QUESTIONS = [
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

// 从后端 /api/practice/questions 加载自测练习题目（知识库即题库）。
// 后端会解析 选择题题库.md 与 老师训练题库.json，动态扩充题目。
// 请求失败时回退到内置 FALLBACK_PRACTICE_QUESTIONS。
async function loadPracticeQuestions() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/practice/questions`);
    if (!response.ok) {
      throw new Error(`practice api ${response.status}`);
    }
    const data = await response.json();
    if (Array.isArray(data.questions) && data.questions.length > 0) {
      practiceQuestions = data.questions;
    } else {
      practiceQuestions = FALLBACK_PRACTICE_QUESTIONS;
    }
  } catch (error) {
    console.warn("加载练习题目失败，使用内置题库:", error);
    practiceQuestions = FALLBACK_PRACTICE_QUESTIONS;
  }
  practiceState.answered.clear();
  renderPracticeList();
}

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
      { name: "relation_type", label: "偏序关系类型", type: "select", value: "divisibility", options: [["divisibility", "整除关系 a | b"], ["less_equal", "小于等于 a ≤ b"], ["subset", "子集关系 A ⊆ B"], ["explicit", "手动输入有序对"]] },
      { name: "elements", label: "元素集合", type: "json", value: "[1, 2, 4]" },
      { name: "relation", label: "偏序关系有序对", type: "json", rows: 5, value: "[[1,1],[2,2],[4,4],[1,2],[2,4],[1,4]]", showWhen: { name: "relation_type", value: "explicit" } },
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
      { name: "problem", label: "完整题目", type: "textarea", rows: 6, value: "给定带权图 A-B 权重为 2，A-C 权重为 7，B-C 权重为 1，请用 Dijkstra 算法求 A 到 C 的最短路径并输出路径和距离。" },
      { name: "language", label: "编程语言", type: "select", value: "python", options: [["python", "Python"], ["c", "C"]] },
      { name: "use_llm", label: "使用 Qwen 按完整题意生成", type: "checkbox", value: true },
    ],
  },
};

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => switchTab(item.dataset.tab));
});
window.addEventListener("popstate", () => switchTab(getTabFromLocation(), false));
window.addEventListener("resize", () => extendedToolState.hasseChart?.resize());
document.getElementById("reloadTextbookFrame")?.addEventListener("click", () => {
  const frame = document.getElementById("textbookFrame");
  if (frame) frame.src = frame.src;
});

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
document.getElementById("matrixInput").addEventListener("input", updateMatrixPreview);

document.getElementById("loadOrderSample").addEventListener("click", () => loadMatrixSample("order"));
document.getElementById("loadEquivalenceSample").addEventListener("click", () => loadMatrixSample("equivalence"));
document.getElementById("refreshGraphButton").addEventListener("click", () => loadKnowledgeGraph(true));
document.getElementById("resetGraphButton").addEventListener("click", resetKnowledgeGraph);
document.getElementById("loadGraphRecommendationsButton").addEventListener("click", loadSelectedGraphRecommendations);
document.getElementById("refreshLearningButton").addEventListener("click", loadLearningReport);
document.getElementById("reloadGradingQuestionsButton").addEventListener("click", loadGradingQuestions);
document.getElementById("gradingQuestionType").addEventListener("change", loadGradingQuestions);
document.getElementById("gradingQuestionSelect").addEventListener("change", selectGradingQuestion);
document.getElementById("gradingForm").addEventListener("submit", submitForGrading);
document.getElementById("gradingPhotoInput").addEventListener("change", (event) => {
  handleGradingPhoto(event.target.files?.[0]);
});
document.getElementById("gradingRecheckButton").addEventListener("click", () => {
  if (gradingState.ocrFile) handleGradingPhoto(gradingState.ocrFile);
});
document.getElementById("continueLearningButton").addEventListener("click", continueLearning);
document.getElementById("joinClassForm").addEventListener("submit", joinClass);
document.getElementById("createClassForm").addEventListener("submit", createClass);
document.getElementById("shareRequestForm").addEventListener("submit", requestLearningShare);
document.getElementById("loginForm").addEventListener("submit", loginAccount);
document.getElementById("registerForm").addEventListener("submit", registerAccount);
document.getElementById("showLoginButton").addEventListener("click", () => setAuthMode("login"));
document.getElementById("showRegisterButton").addEventListener("click", () => setAuthMode("register"));
document.getElementById("logoutButton").addEventListener("click", logoutAccount);
document.getElementById("generateExamForm").addEventListener("submit", generateTeacherExam);
document.getElementById("loadExamResultsButton").addEventListener("click", loadTeacherExamResults);
document.querySelectorAll(".practice-filter").forEach((button) => {
  button.addEventListener("click", () => setPracticeFilter(button.dataset.practiceFilter));
});
document.querySelectorAll(".practice-mode").forEach((button) => {
  button.addEventListener("click", () => setPracticeMode(button.dataset.practiceMode));
});
document.querySelectorAll(".graph-view-button").forEach((button) => {
  button.addEventListener("click", () => setGraphView(button.dataset.graphView));
});
document.querySelectorAll(".extended-tool-button").forEach((button) => {
  button.addEventListener("click", () => selectExtendedTool(button.dataset.toolName));
});
document.querySelectorAll(".unified-tool-tab").forEach((button) => {
  button.addEventListener("click", () => selectUnifiedTool(button.dataset.unifiedTool));
});
document.getElementById("runExtendedToolButton").addEventListener("click", runExtendedTool);

updateMatrixPreview();
loadPracticeQuestions();
renderDashboard();
selectExtendedTool(extendedToolState.current);
selectUnifiedTool(unifiedToolState.current);
switchTab(getTabFromLocation(), false);
bootstrapApp();

async function bootstrapApp() {
  // 演示/截图模式：?demo=1003 直接以演示账户进入（评委演示也方便）。
  const demoParams = new URLSearchParams(location.search);
  const demoParam = demoParams.get("demo");
  if (demoParam !== null) {
    const demoUserId = Number(demoParam) || DEFAULT_USER_ID;
    authState.user = {
      user_id: demoUserId,
      name: demoUserId === 1003 ? "张鹤轩" : `演示用户 ${demoUserId}`,
      role: "student",
    };
    await startAuthenticatedApp();
    // 演示/截图模式：?ask=问题 自动在 RAG 问答中发送（真实问答，用于截图）
    const askQuestion = demoParams.get("ask");
    if (askQuestion) {
      setTimeout(() => {
        const input = document.getElementById("questionInput");
        if (input) {
          input.value = askQuestion;
          handleAsk();
        }
      }, 1500);
    }
    return;
  }
  const restored = await restoreAuthSession();
  if (!restored) {
    showAuthGate();
    return;
  }
  await startAuthenticatedApp();
}

async function startAuthenticatedApp() {
  applyAuthenticatedUser();
  await Promise.allSettled([
    checkStatus(),
    loadLearningReport({ silent: true }),
  ]);
  switchTab(getTabFromLocation(), false);
}

async function restoreAuthSession() {
  if (!authState.token) return false;
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${authState.token}` },
    });
    if (!response.ok) throw new Error("登录状态已失效");
    authState.user = await response.json();
    return true;
  } catch (error) {
    clearAuthSession();
    return false;
  }
}

function showAuthGate(message = "") {
  document.getElementById("authGate").hidden = false;
  document.getElementById("appLayout").hidden = true;
  setAuthStatus(message);
}

function applyAuthenticatedUser() {
  const user = authState.user;
  if (!user) return;
  document.getElementById("authGate").hidden = true;
  document.getElementById("appLayout").hidden = false;
  document.getElementById("currentUserName").textContent = user.name;
  document.getElementById("currentUserRole").textContent = formatRole(user.role);
  document.getElementById("learningUserInput").value = `${user.name} · ID ${user.user_id}`;
  classState.role = ["teacher", "admin"].includes(user.role) ? "teacher" : "student";
  updateRoleInterface();
}

function setAuthMode(mode) {
  const isLogin = mode === "login";
  document.getElementById("loginForm").hidden = !isLogin;
  document.getElementById("registerForm").hidden = isLogin;
  document.getElementById("showLoginButton").classList.toggle("active", isLogin);
  document.getElementById("showRegisterButton").classList.toggle("active", !isLogin);
  document.getElementById("showLoginButton").setAttribute("aria-selected", String(isLogin));
  document.getElementById("showRegisterButton").setAttribute("aria-selected", String(!isLogin));
  document.getElementById("authTitle").textContent = isLogin ? "登录学习空间" : "创建学习账户";
  document.getElementById("authSubtitle").textContent = isLogin ? "使用你的账户继续上次学习。" : "选择真实身份，系统会准备对应工作空间。";
  setAuthStatus("");
}

async function loginAccount(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await submitAuth("/api/auth/login", {
    username: form.elements.username.value.trim(),
    password: form.elements.password.value,
  }, form);
}

async function registerAccount(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await submitAuth("/api/auth/register", {
    name: form.elements.name.value.trim(),
    username: form.elements.username.value.trim(),
    password: form.elements.password.value,
    role: form.elements.role.value,
  }, form);
}

async function submitAuth(path, payload, form) {
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  setAuthStatus("正在连接账户服务...", "loading");
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(readApiError(data, `请求失败（${response.status}）`));
    authState.token = data.token;
    authState.user = data.user;
    localStorage.setItem(AUTH_TOKEN_KEY, data.token);
    setAuthStatus("");
    await startAuthenticatedApp();
  } catch (error) {
    setAuthStatus(error.message, "error");
  } finally {
    submitButton.disabled = false;
  }
}

function logoutAccount() {
  clearInterval(examState.timer);
  clearAuthSession();
  classState.studentClass = null;
  classState.teacherClasses = [];
  examState.available = [];
  setAuthMode("login");
  showAuthGate("已安全退出当前账户。");
}

function clearAuthSession() {
  authState.token = "";
  authState.user = null;
  chatState.sessionId = null;
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

function setAuthStatus(message, state = "") {
  const target = document.getElementById("authStatus");
  target.textContent = message;
  target.className = `auth-status${state ? ` ${state}` : ""}`;
}

function formatRole(role) {
  return role === "teacher" ? "教师" : role === "admin" ? "管理员" : "学生";
}

function readApiError(data, fallback) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item.msg).filter(Boolean).join("；") || fallback;
  return fallback;
}

function selectUnifiedTool(toolName) {
  const selected = ["truth", "relation", "extended"].includes(toolName) ? toolName : "truth";
  unifiedToolState.current = selected;
  document.querySelectorAll(".unified-tool-tab").forEach((button) => {
    const active = button.dataset.unifiedTool === selected;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".unified-tool-view").forEach((view) => {
    const viewName = view.id === "extendedTools" ? "extended" : view.id;
    view.classList.toggle("active", viewName === selected);
  });
  if (selected === "relation") updateMatrixPreview();
  if (selected === "extended") setTimeout(() => extendedToolState.hasseChart?.resize(), 0);
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
    const graphParams = new URLSearchParams(location.search);
    // 演示/截图模式：?expand=all 自动展开全部模块与概念；?graphview=force 切关系图视图
    if (graphParams.get("expand") === "all" || graphParams.get("graphview")) {
      const timer = setInterval(() => {
        if (!graphState.modules.length) return;
        clearInterval(timer);
        if (graphParams.get("graphview") === "force") {
          // 关系图视图下也展开全部层级，让图更完整（关系图支持逐层展开）
          graphState.modules.forEach((module) => {
            graphState.expandedModules.add(module.id);
            (module.children || []).forEach((concept) => graphState.expandedConcepts.add(concept.id));
          });
          setGraphView("force");
          return;
        }
        if (graphParams.get("graphview") === "teacher") {
          setGraphView("teacher");
          return;
        }
        graphState.modules.forEach((module) => {
          graphState.expandedModules.add(module.id);
          (module.children || []).forEach((concept) => graphState.expandedConcepts.add(concept.id));
        });
        renderKnowledgeGraph();
      }, 300);
    }
  }
  if (tabName === "dashboard") {
    renderDashboard();
    loadLearningReport({ silent: true });
    setTimeout(() => dashboardState.chart?.resize(), 0);
  }
  if (tabName === "learning") {
    loadLearningReport();
    loadAiSummary();
    setTimeout(() => learningState.chart?.resize(), 0);
  }
  if (tabName === "practice") {
    syncPracticeModePanels();
    if (practiceState.mode === "grading") {
      loadGradingQuestions();
    } else {
      renderPracticeList();
    }
  }
  if (tabName === "tools") selectUnifiedTool(unifiedToolState.current);
  if (tabName === "classes") loadClassWorkspace();
  if (tabName === "exam") loadExamWorkspace();
}

function getTabFromLocation() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  if (path === "/grading") {
    practiceState.mode = "grading";
    return "practice";
  }
  if (path === "/truth-table") {
    selectUnifiedTool("truth");
    return "tools";
  }
  if (path === "/relation") {
    selectUnifiedTool("relation");
    return "tools";
  }
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

    updateMessage(loading, data.answer);
  } catch (error) {
    updateMessage(loading, `${error.message}。当前后端：${API_BASE_URL}；请检查后端状态和模型网络连接。`);
  }
}

async function requestStreamingChat(payload, message) {
  // 演示/截图模式：?nostream=1 走非流式（一次拿完整回答再打字机输出），规避流式偶发挂起
  if (new URLSearchParams(location.search).get("nostream") === "1") {
    let resp = await fetch(`${RAG_API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || "问答请求失败");
    if (data.session_id) chatState.sessionId = data.session_id;
    const fallbackWriter = createTypewriter(message);
    fallbackWriter.enqueue(data.answer || "");
    await fallbackWriter.drain();
    return data;
  }
  let response = await fetch(`${RAG_API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.status === 404) {
    response = await fetch(`${RAG_API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "问答请求失败");
    const fallbackWriter = createTypewriter(message);
    fallbackWriter.enqueue(data.answer || "");
    await fallbackWriter.drain();
    return data;
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "问答请求失败");
  }
  if (!response.body) throw new Error("当前浏览器不支持流式回答");

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const writer = createTypewriter(message);
  let buffer = "";
  let result = null;
  let streamedAnswer = "";

  const consumeLine = (line) => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "meta") {
      chatState.sessionId = event.session_id || chatState.sessionId;
    } else if (event.type === "delta") {
      const content = event.content || "";
      streamedAnswer += content;
      writer.enqueue(content);
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
  await writer.drain();
  if (!result) throw new Error("流式回答提前结束");
  result.answer = result.answer || streamedAnswer;
  return result;
}

function createTypewriter(message) {
  const pending = [];
  const waiters = [];
  let displayed = "";
  let timer = null;

  const resolveWaiters = () => {
    while (waiters.length) waiters.shift()();
  };
  const tick = () => {
    const character = pending.shift();
    if (character === undefined) {
      timer = null;
      resolveWaiters();
      return;
    }
    displayed += character;
    updateStreamingMessage(message, displayed);
    timer = setTimeout(tick, 12);
  };

  return {
    enqueue(text) {
      pending.push(...Array.from(String(text || "")));
      if (!timer && pending.length) tick();
    },
    drain() {
      if (!timer && !pending.length) return Promise.resolve();
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
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
    const response = await fetch(`${TOOLS_API_BASE_URL}/tools/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool: "truth-table", params: { expression } }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "生成真值表失败");
    }

    renderTruthTable(data.result);
  } catch (error) {
    showError(resultBox, `${error.message}。请确认当前后端 ${API_BASE_URL} 正在运行。`);
  }
}

async function analyzeRelation() {
  const resultBox = document.getElementById("relationResult");

  try {
    const matrix = readMatrixInput();
    resultBox.textContent = "正在判断关系性质...";

    const response = await fetch(`${TOOLS_API_BASE_URL}/tools/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool: "relation-properties", params: { matrix } }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "判断关系性质失败");
    }

    renderRelationProperties(data.result, matrix.length);
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
  const form = document.getElementById("extendedToolForm");
  form.innerHTML = config.fields.map(renderExtendedToolField).join("");
  bindExtendedToolFieldRules(config, form);
  const result = document.getElementById("extendedToolResult");
  result.className = "tool-response empty-state";
  result.textContent = "填写参数后运行工具。";
}

function renderExtendedToolField(field) {
  const value = escapeHtml(String(field.value ?? ""));
  const wrapper = `data-tool-field="${escapeHtml(field.name)}"`;
  if (field.type === "select") {
    return `<label ${wrapper}>${escapeHtml(field.label)}<select name="${escapeHtml(field.name)}">${field.options.map(([optionValue, label]) => `<option value="${escapeHtml(optionValue)}" ${optionValue === field.value ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label>`;
  }
  if (field.type === "checkbox") {
    return `<label class="tool-checkbox" ${wrapper}><input type="checkbox" name="${escapeHtml(field.name)}" ${field.value ? "checked" : ""}><span>${escapeHtml(field.label)}</span></label>`;
  }
  if (field.type === "json" || field.type === "textarea") {
    return `<label ${wrapper}>${escapeHtml(field.label)}<textarea name="${escapeHtml(field.name)}" rows="${Number(field.rows || 3)}">${value}</textarea></label>`;
  }
  return `<label ${wrapper}>${escapeHtml(field.label)}<input name="${escapeHtml(field.name)}" value="${value}"></label>`;
}

function bindExtendedToolFieldRules(config, form) {
  const updateVisibility = () => {
    config.fields.forEach((field) => {
      const wrapper = form.querySelector(`[data-tool-field="${field.name}"]`);
      if (!wrapper || !field.showWhen) return;
      const dependency = form.querySelector(`[name="${field.showWhen.name}"]`);
      wrapper.hidden = !dependency || dependency.value !== field.showWhen.value;
    });
  };
  const dependencies = new Set(
    config.fields.filter((field) => field.showWhen).map((field) => field.showWhen.name),
  );
  dependencies.forEach((name) => {
    form.querySelector(`[name="${name}"]`)?.addEventListener("change", updateVisibility);
  });
  updateVisibility();
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
      const wrapper = form.querySelector(`[data-tool-field="${field.name}"]`);
      if (wrapper?.hidden) return;
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
    const response = await fetch(`${TOOLS_API_BASE_URL}/tools/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool: toolName, params }),
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
      <div class="result-counts"><span>${escapeHtml(formatHasseRelationType(result.relation_type))}</span><span>${nodes.length} 个元素</span><span>${edges.length} 条覆盖关系</span></div>
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
      <span><b>生成方式</b> ${escapeHtml(formatGenerationMode(result.generation_mode))}</span>
    </div>
    <p class="result-caption">${escapeHtml(result.problem || "未说明任务")}</p>
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
    dijkstra: "最短路径", bipartite: "二分图判定", hasse: "哈斯图", general: "自定义离散数学问题" })[type] || type || "通用算法";
}

function formatHasseRelationType(type) {
  return ({ explicit: "手动偏序", divisibility: "整除关系", less_equal: "小于等于关系", subset: "子集关系" })[type] || "偏序关系";
}

function formatGenerationMode(mode) {
  return mode === "qwen" ? "Qwen 按题生成" : "离线模板回退";
}

function addMessage(text, type) {
  const messages = document.getElementById("chatMessages");
  const message = document.createElement("article");
  message.className = `message ${type}`;

  const content = document.createElement("div");
  content.className = "message-content";
  content.innerHTML = formatAnswerHtml(text);
  message.appendChild(content);

  messages.appendChild(message);
  typesetMath(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

function updateMessage(message, text) {
  message.innerHTML = "";

  const content = document.createElement("div");
  content.className = "message-content";
  content.innerHTML = formatAnswerHtml(text);
  message.appendChild(content);

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

  // 首次加载（无画布）时才显示占位文字；刷新时保留现有画布，避免 textContent 覆盖 echarts DOM。
  if (!graphState.chart) {
    container.textContent = "正在从知识库加载知识图谱...";
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);
    const response = await fetch(`${KB_API_BASE_URL}/kb/knowledge-graph`, {
      signal: controller.signal,
    });
    const data = await response.json();
    clearTimeout(timeoutId);
    if (!response.ok) {
      throw new Error(data.detail || "知识图谱接口请求失败");
    }

    graphState.modules = normalizeKnowledgeGraph(data);
    graphState.dependencies = normalizeKnowledgeDependencies(data, graphState.modules);
    renderGraphDependencies();
    graphState.expandedModules.clear();
    graphState.expandedConcepts.clear();
    graphState.loaded = true;

    // 强制刷新：销毁旧 echarts 实例，重新挂载画布（否则 setOption 画到被覆盖的 DOM 上）。
    if (forceReload && graphState.chart) {
      graphState.chart.dispose();
      graphState.chart = null;
    }
    // 节点颜色由 masteryByNode 决定（getNodeMastery）。先 await 拉一次学情，再渲染，
    // 否则图谱节点颜色永远 unlearned 灰。
    await refreshGraphMastery();
    renderKnowledgeGraph();
    showGraphNodeDetail({
      name: "知识图谱",
      level: "overview",
      description: `已加载 ${graphState.modules.length} 个课程模块。点击模块展开子概念，再点击子概念展开定义、定理、例题和规则。`,
    });
  } catch (error) {
    clearTimeout(timeoutId);
    const message = error.name === "AbortError"
      ? "知识图谱加载超时（15s）。"
      : error.message;
    container.textContent = `${message}。请确认当前后端 ${API_BASE_URL} 已启动，并且接口 /kb/knowledge-graph 可用。`;
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

    const normalizedChildren = children.map((child, childIndex) => {
      const childNodeId = child.node_id || child.id || child.key || `${moduleNodeId}_${childIndex + 1}`;
      const childId = `${moduleId}-concept-${childNodeId}`;
      const items = child.items || child.children || [];
      const childName = child.name || child.title || child.label || `子概念${childIndex + 1}`;
      const chapter = child.chapter || `${moduleIndex + 1}.${childIndex + 1}`;

      const normalizedItems = items.map((item, itemIndex) => ({
        ...normalizeKnowledgeItem(item, itemIndex, childId, childNodeId, childName),
      }));

      // concept 节点的"强定义"：优先用后端 description（已补全的权威文字），
      // 缺 description 时才回退到 items 聚合，确保每个节点都有强定义可显示。
      const childDescription = (child.description || "").trim();
      const childText = childDescription || normalizedItems
        .map((item) => `[${item.type || "条目"}] ${item.text || ""}`.trim())
        .filter((line) => line.replace(/\[[^\]]+\]\s*/, "").length > 0)
        .join("\n");

      return {
        id: childId,
        nodeId: childNodeId,
        parentId: moduleId,
        parentNodeId: moduleNodeId,
        name: childName,
        type: "concept",
        chapter,
        chapterTitle: child.chapter_title || `${chapter} ${childName}`,
        itemCount: Number(child.item_count || items.length),
        description: child.description || child.summary || child.content || "",
        text: childText,
        searchQuery: child.search_query || child.query || `${moduleName} ${childName}`,
        masteryLevels: child.mastery_levels || {},
        items: normalizedItems,
      };
    });

    // module 节点的"强定义"：优先用后端 description，缺时回退到子概念聚合。
    const moduleDescription = (module.description || "").trim();
    const moduleText = moduleDescription || normalizedChildren
      .map((concept) => {
        const conceptLines = [
          `【${concept.name}】`,
          ...concept.items.map((item) => `  · [${item.type || "条目"}] ${item.text || ""}`.trim()),
        ];
        return conceptLines.join("\n");
      })
      .filter((block) => block.length > 4)
      .join("\n\n");

    return {
      id: moduleId,
      nodeId: moduleNodeId,
      name: moduleName,
      type: "module",
      chapter: module.chapter || `第${moduleIndex + 1}章`,
      itemCount: Number(module.item_count || 0),
      description: module.description || module.summary || module.content || "",
      text: moduleText,
      searchQuery: module.search_query || module.query || moduleName,
      children: normalizedChildren,
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
  const text = item.text || "";
  const name = item.name || item.title || item.label || text || item.content || `条目${itemIndex + 1}`;
  const description = item.description || item.summary || item.content || text || "";

  return {
    id: `${parentId}-item-${itemNodeId}`,
    nodeId: itemNodeId,
    parentId,
    parentNodeId,
    name,
    type,
    text,
    description,
    chapter: item.chapter || "",
    searchQuery: item.search_query || item.query || `${parentName} ${name}`,
    masteryLevels: item.mastery_levels || {},
  };
}

function renderKnowledgeGraph() {
  // 教材图谱视图：单独渲染（四层结构 + 映射染色）
  if (graphState.view === "teacher") {
    renderTeacherGraph();
    return;
  }

  const container = document.getElementById("knowledgeGraphChart");
  if (!graphState.chart) {
    container.innerHTML = "";
    graphState.chart = echarts.init(container);
    graphState.chart.on("click", handleGraphClick);
    window.addEventListener("resize", () => graphState.chart?.resize());
  }

  const option = graphState.view === "force"
    ? buildStaticRelationGraphOption()
    : buildMindMapOption();
  graphState.chart.resize();
  graphState.chart.setOption(option, true);
}

function buildStaticRelationGraphOption() {
  const { nodes, links } = buildGraphSeriesData(true);
  const rowCount = applyStaticRelationLayout(nodes);
  const chart = document.getElementById("knowledgeGraphChart");
  chart.style.height = `${Math.min(1400, Math.max(620, rowCount * 82 + 150))}px`;
  return {
    tooltip: {
      formatter: (params) => {
        const data = params.data || {};
        if (params.dataType === "edge") {
          return data.relationLabel || data.label?.formatter || "";
        }
        const rawNode = graphState.nodeIndex.get(data.id);
        const mastery = getNodeMastery(rawNode);
        const status = getMasteryStatus(mastery);
        const level = Number(mastery?.level ?? mastery?.mastery_level ?? 0);
        return `${data.name}<br>${getTypeLabel(data.rawType || data.type)} · ${getMasteryLabel(status, level)}`;
      },
    },
    legend: {
      top: 8,
      data: ["模块", "子概念", "定义", "定理", "例题", "规则"],
    },
    series: [
      {
        type: "graph",
        layout: "none",
        roam: true,
        draggable: false,
        animation: false,
        categories: [
          { name: "模块", itemStyle: { color: getNodeColor("module", 0) } },
          { name: "子概念", itemStyle: { color: getNodeColor("concept", 1) } },
          { name: "定义", itemStyle: { color: getNodeColor("definition", 2) } },
          { name: "定理", itemStyle: { color: getNodeColor("theorem", 3) } },
          { name: "例题", itemStyle: { color: getNodeColor("example", 4) } },
          { name: "规则", itemStyle: { color: getNodeColor("rule", 5) } },
        ],
        label: {
          show: true,
          position: "inside",
          color: "#ffffff",
          fontWeight: 700,
          formatter: (params) => truncateText(params.data.name, Math.max(8, Math.floor(Number(params.data.symbolSize || 34) / 4))),
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
  document.getElementById("knowledgeGraphChart").style.height = "";
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
    symbolSize: calculateMindMapNodeSize(`${moduleIndex + 1}. ${module.name}`, 112, 38),
    itemStyle: getGraphNodeStyle(module),
    collapsed: !graphState.expandedModules.has(module.id),
    children: module.children.map((concept) => buildMindMapConceptNode(concept)),
  };
}

function buildMindMapConceptNode(concept) {
  graphState.nodeIndex.set(concept.id, concept);
  return {
    id: concept.id,
    name: concept.chapterTitle || concept.name,
    rawType: concept.type,
    symbolSize: calculateMindMapNodeSize(concept.chapterTitle || concept.name, 116, 34),
    itemStyle: getGraphNodeStyle(concept),
    collapsed: !graphState.expandedConcepts.has(concept.id),
    children: concept.items.map((item) => {
      const category = getItemCategory(item.type);
      graphState.nodeIndex.set(item.id, item);
      return {
        id: item.id,
        name: item.name,
        rawType: item.type,
        symbolSize: calculateMindMapNodeSize(item.name, 138, 30),
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

function applyStaticRelationLayout(nodes) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const rowStep = 100;
  const columns = { module: 100, concept: 500, item: 900 };
  let row = 0;

  const placeAtRow = (node, column, rowNumber) => {
    node.x = column;
    node.y = 60 + rowNumber * rowStep;
    node.fixed = true;
    return node.y;
  };

  graphState.modules.forEach((module) => {
    const moduleNode = nodeById.get(module.id);
    if (!moduleNode) return;

    const conceptYs = [];
    if (graphState.expandedModules.has(module.id)) {
      module.children.forEach((concept) => {
        const conceptNode = nodeById.get(concept.id);
        if (!conceptNode) return;

        const itemYs = [];
        if (graphState.expandedConcepts.has(concept.id)) {
          concept.items.forEach((item) => {
            const itemNode = nodeById.get(item.id);
            if (!itemNode) return;
            itemYs.push(placeAtRow(itemNode, columns.item, row));
            row += 1;
          });
        }

        if (itemYs.length) {
          conceptNode.x = columns.concept;
          conceptNode.y = (itemYs[0] + itemYs[itemYs.length - 1]) / 2;
          conceptNode.fixed = true;
        } else {
          conceptYs.push(placeAtRow(conceptNode, columns.concept, row));
          row += 1;
          return;
        }
        conceptYs.push(conceptNode.y);
      });
    }

    if (conceptYs.length) {
      moduleNode.x = columns.module;
      moduleNode.y = (conceptYs[0] + conceptYs[conceptYs.length - 1]) / 2;
      moduleNode.fixed = true;
    } else {
      placeAtRow(moduleNode, columns.module, row);
      row += 1;
    }
    row += 0.65;
  });

  nodes.forEach((node) => {
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) return;
    placeAtRow(node, columns.item, row);
    row += 1;
  });
  return Math.max(6, row);
}

function pushGraphNode(nodes, rawNode, category, symbolSize) {
  const node = {
    id: rawNode.id,
    nodeId: rawNode.nodeId,
    name: rawNode.name,
    rawType: rawNode.type,
    searchQuery: rawNode.searchQuery,
    category,
    symbolSize: calculateForceNodeSize(rawNode, symbolSize),
    value: rawNode.description || "",
    itemStyle: getForceGraphNodeStyle(rawNode, category),
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
    emphasis: {
      label: {
        show: true,
        formatter: label,
      },
    },
  };
}

function calculateForceNodeSize(node, baseSize) {
  const textLength = Array.from(String(node.name || "")).length;
  const childCount = node.type === "module"
    ? node.children?.length || 0
    : node.type === "concept" ? node.items?.length || 0 : 0;
  return Math.max(baseSize, Math.min(baseSize + 30, baseSize + textLength * 1.15 + childCount * 1.8));
}

function calculateMindMapNodeSize(name, baseWidth, height) {
  const textLength = Array.from(String(name || "")).length;
  return [Math.max(baseWidth, Math.min(210, 32 + textLength * 12)), height];
}

function renderGraphDependencies() {
  const target = document.getElementById("graphDependencies");
  if (!target) return;
  const moduleNames = new Map(graphState.modules.map((module) => [module.id, module.name]));
  if (!graphState.dependencies.length) {
    target.className = "dependency-list empty-state";
    target.textContent = "后端未返回模块依赖关系。";
    return;
  }
  target.className = "dependency-list";
  target.innerHTML = graphState.dependencies.map((dependency) => `
    <div>
      <strong>${escapeHtml(moduleNames.get(dependency.source) || dependency.source.replace(/^module-/, ""))}</strong>
      <span>→</span>
      <strong>${escapeHtml(moduleNames.get(dependency.target) || dependency.target.replace(/^module-/, ""))}</strong>
      <small>${escapeHtml(dependency.label)}</small>
    </div>
  `).join("");
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

  // 教材图谱（教师四层结构）视图：点击 K 知识点 → 走平台映射后的行为链
  if (graphState.view === "teacher") {
    handleTeacherGraphClick(params.data);
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
  if (!['tree', 'force', 'teacher'].includes(view) || graphState.view === view) {
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
    : view === "teacher"
      ? "教材图谱按 章→节→知识点→要点 四层展示；颜色表示对应知识点的掌握状态（映射到平台学情）。"
      : "关系图采用固定分层布局；填充色表示内容类型，边框色表示掌握状态，橙色虚线表示前置知识流向。";
  document.querySelector(".graph-legend .dependency").hidden = view !== "force";
  renderKnowledgeGraph();
}

// ============ 教材图谱（教师四层结构 · 映射联动学情） ============
async function loadTeacherGraph() {
  if (graphState.teacherLoaded) return graphState.teacherGraph;
  const response = await fetch(`${KB_API_BASE_URL}/kb/teacher-graph`).catch(() => null);
  if (!response || !response.ok) {
    throw new Error("教材图谱接口暂不可用");
  }
  graphState.teacherGraph = await response.json();
  graphState.teacherLoaded = true;
  return graphState.teacherGraph;
}

function handleTeacherGraphClick(data) {
  if (!data || data.kpId) {
    // K 知识点节点
    const platformNodeId = data.platform || "";
    const kind = data.mappingKind || "";
    const nodeId = platformNodeId || "";
    const name = nodeId ? findNodeName(nodeId) : data.name;
    const pseudo = {
      id: `teacher-kp-${data.kpId || data.name}`,
      nodeId,
      name,
      type: nodeId ? "item" : "module",
      description: `（来自教材图谱）${data.name}\n章节：${data.chapter || ""}`,
      text: "",
    };
    graphState.selectedNode = pseudo;
    setCurrentLearningNode(pseudo);
    showGraphNodeDetail(pseudo);
    loadGraphNodeKnowledge(pseudo);
    if (nodeId && kind !== "module_fallback") {
      loadRecommendedQuestions(pseudo);
    }
    recordLearningEvent(pseudo);
    return;
  }
  if (data.children) {
    graphState.expandedModules.add(data.id || data.name);
    renderKnowledgeGraph();
  }
}

async function renderTeacherGraph() {
  const container = document.getElementById("knowledgeGraphChart");
  if (container && container.dataset.renderer === "teacher") return;
  let teacher;
  try {
    teacher = await loadTeacherGraph();
  } catch (error) {
    container.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
    return;
  }
  container.dataset.renderer = "teacher";

  // 递归建树（章→节→K），K 节点带 platform 映射
  function chaptersToTree(chapters) {
    return chapters.map((ch) => {
      const sections = (ch.sections || []).map((sec) => ({
        name: sec.title || sec.id,
        children: (sec.kps || []).map((k) => ({
          name: k.title || k.id,
          kpId: k.id,
          platform: k.platform_node_id || "",
          mappingKind: k.mapping_kind || "",
          chapter: ch.title || "",
          value: k.id,
        })),
      }));
      return { name: ch.title || ch.id, children: sections };
    });
  }

  const treeData = { name: "离散数学教材 · 19 章", children: chaptersToTree(teacher.chapters || []) };

  // 四层染色：K 用 platform 映射的掌握度；其上层按均值
  function colorFor(node) {
    const leaf = !node.children || !node.children.length;
    if (leaf && node.kpId) {
      const pNode = node.platform
        ? { nodeId: node.platform, type: "concept", children: [], items: [] }
        : null;
      const mastery = pNode ? getNodeMastery(pNode) : null;
      return getMasteryColor(getMasteryStatus(mastery));
    }
    if (leaf) return "transparent";
    const colors = (node.children || []).map((c) => colorFor(c)).filter((c) => c && c !== "transparent");
    return colors.length ? colors[Math.floor(colors.length / 2)] : "transparent";
  }
  function attachColors(node) {
    node.itemStyle = { color: colorFor(node) === "transparent" ? "#d7e1ea" : colorFor(node), borderColor: "#ffffff", borderWidth: 1.2 };
    (node.children || []).forEach(attachColors);
  }
  attachColors(treeData);

  if (graphState.chart) {
    graphState.chart.dispose();
  }
  graphState.chart = echarts.init(container);
  graphState.chart.on("click", handleGraphClick);
  graphState.chart.setOption({
    tooltip: {
      formatter: (params) => {
        const d = params.data || {};
        return d.kpId
          ? `${d.name}<br/>K：${d.kpId}${d.platform ? `<br/>映射：${d.platform}（${d.chapter || ""}）` : "<br/>（暂未映射到平台节点）"}`
          : d.name;
      },
    },
    series: [{
      type: "tree",
      data: [treeData],
      top: "8%",
      left: "8%",
      bottom: "8%",
      right: "26%",
      symbolSize: 11,
      initialTreeDepth: 2,
      orient: "LR",
      expandAndCollapse: true,
      label: { position: "left", verticalAlign: "middle", fontSize: 12.5, color: "#314559" },
      leaves: { label: { position: "right", verticalAlign: "middle" } },
      emphasis: { focus: "descendant" },
      lineStyle: { color: "#7fa6cc", width: 1.2 },
    }],
  }, true);
}

function showGraphNodeDetail(node) {
  document.getElementById("graphDetailTitle").textContent = node.name || "知识图谱";
  const linksEl = document.getElementById("graphDetailLinks");
  const tasksEl = document.getElementById("graphDetailTasks");
  if (node.level === "overview") {
    // overview 模式只显示标题，不显示任何内部实现/调用细节的占位文字。
    linksEl.hidden = true;
    linksEl.innerHTML = "";
    tasksEl.hidden = true;
    tasksEl.innerHTML = "";
    return;
  }

  // 强定义 / 学情追踪 卡片：点击非根节点时展开。
  linksEl.hidden = false;
  linksEl.innerHTML = `<p class="muted-line">正在加载知识库内容…</p>`;
  renderGraphNodeLearning(node);
}

async function loadGraphNodeKnowledge(node) {
  const target = document.getElementById("graphDetailLinks");
  if (!node || node.level === "overview") {
    return;
  }

  // 节点的强定义：优先用 text（若后端有强定义内容），否则用 description（模块/概念简介）。
  const strongDefinition = (node.text || node.description || "").trim();
  if (strongDefinition) {
    target.innerHTML = renderStrongDefinition(node, strongDefinition);
  } else {
    target.innerHTML = `<p class="muted-line">该节点暂无强定义内容。</p>`;
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

function renderStrongDefinition(node, text) {
  return `
    <article class="knowledge-result-item strong-definition">
      <div class="knowledge-result-content">${formatAnswerHtml(text)}</div>
    </article>
  `;
}

function formatKnowledgeSource(metadata) {
  // 只显示来源文档名，不显示章节/页码。
  return metadata.source || metadata.file_name || metadata.filename || "";
}

function buildNodeSummaryHtml(node, searchQuery) {
  // 节点说明只显示 description，移除 search_query / 父节点 / 包含 N 条 等技术性元数据。
  const description = node.description || "暂无节点简介，右侧将从知识库检索对应教材内容。";

  return `
    <div class="node-summary">
      <p>${formatAnswerHtml(description)}</p>
    </div>
  `;
}

const LEARNING_LEVEL_NAMES = ["未学", "了解", "理解", "掌握", "熟练"];

// 加载前的占位提示（真实学情到达后替换）
function buildTrackingHtml(node) {
  return `<p class="muted-line">正在加载学情数据...</p>`;
}

// 先渲染本地浏览统计，再异步加载后端真实学情（答题掌握度）替换。
function renderGraphNodeLearning(node) {
  const target = document.getElementById("graphDetailTasks");
  if (!target) return;
  target.hidden = false;
  target.innerHTML = buildTrackingHtml(node);
  loadGraphNodeLearning(node);
}

async function loadGraphNodeLearning(node) {
  const target = document.getElementById("graphDetailTasks");
  const nodeId = node.nodeId || node.id || "";
  if (!nodeId || node.level === "overview") return;
  const userId = getCurrentUserId();

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const response = await fetch(`${API_BASE_URL}/api/learning/report?user_id=${encodeURIComponent(userId)}`, {
      signal: controller.signal,
    });
    const data = await response.json();
    clearTimeout(timeoutId);
    const current = graphState.selectedNode;
    if (!current || (current.nodeId || current.id || "") !== nodeId) return;
    if (!response.ok) throw new Error(data.detail || "学情获取失败");

    const mastery = (data.node_mastery || []).find((record) => record.node_id === nodeId) || null;
    target.innerHTML = renderNodeLearningHtml(node, mastery);
  } catch (error) {
    clearTimeout(timeoutId);
    const current = graphState.selectedNode;
    if (!current || (current.nodeId || current.id || "") !== nodeId) return;
    const message = error.name === "AbortError"
      ? "学情加载超时（10s）。"
      : "学情接口暂不可用，请确认后端服务已启动。";
    target.innerHTML = `<p class="muted-line">${message}</p>`;
  }
}

function renderNodeLearningHtml(node, mastery) {
  if (!mastery) {
    return `
      <div class="tracking-box">
        <p class="muted-line">该节点暂无练习记录。在「自测练习」完成答题后，这里会显示真实掌握度。</p>
      </div>
    `;
  }

  const level = Number(mastery.level ?? 0);
  const levelName = LEARNING_LEVEL_NAMES[level] || "未知";
  const correct = Number(mastery.correct_count ?? 0);
  const total = Number(mastery.total_count ?? 0);
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;
  const weak = level > 0 && level <= 2;
  const lastTime = mastery.last_practice_time
    ? new Date(mastery.last_practice_time).toLocaleString("zh-CN")
    : "暂无";

  return `
    <div class="tracking-box">
      <div class="mastery-badge ${weak ? "weak" : ""}">掌握等级 ${level} · ${levelName}${weak ? "（薄弱）" : ""}</div>
      <div class="progress-track"><span style="display:block;width:${level / 4 * 100}%;background:#22c55e;height:8px;border-radius:4px;"></span></div>
      <ul class="mastery-stats">
        <li>答题：${correct} / ${total}</li>
        <li>准确率：${accuracy}%</li>
        <li>最近练习：${lastTime}</li>
      </ul>
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
  target.textContent = learningState.currentNodeName || "尚未选择知识点";
}

function getCurrentUserId() {
  const value = Number(authState.user?.user_id || DEFAULT_USER_ID);
  return Number.isInteger(value) && value > 0 ? value : DEFAULT_USER_ID;
}

function setPracticeFilter(filter) {
  practiceState.filter = filter || "all";
  practiceState.questionIndex[practiceState.mode] = 0;
  document.querySelectorAll(".practice-filter").forEach((button) => {
    button.classList.toggle("active", button.dataset.practiceFilter === practiceState.filter);
  });
  renderPracticeList();
}

function setPracticeMode(mode) {
  const supportedModes = ["choice", "fill", "proof", "grading"];
  practiceState.mode = supportedModes.includes(mode) ? mode : "choice";
  practiceState.questionIndex[practiceState.mode] = 0;
  document.querySelectorAll(".practice-mode").forEach((button) => {
    button.classList.toggle("active", button.dataset.practiceMode === practiceState.mode);
  });
  syncPracticeModePanels();
  if (practiceState.mode === "grading") {
    loadGradingQuestions();
    return;
  }
  // 模式切换时同步加载对应题库
  if (practiceState.mode === "fill" && practiceState.fillQuestions.length === 0) {
    loadFillQuestions();
    return;
  }
  if (practiceState.mode === "calc" && practiceState.calcQuestions.length === 0) {
    loadCalcQuestions();
    return;
  }
  if (practiceState.mode === "proof" && practiceState.proofQuestions.length === 0) {
    loadProofQuestions();
    return;
  }
  renderPracticeList();
}

function syncPracticeModePanels() {
  const gradingMode = practiceState.mode === "grading";
  document.querySelectorAll(".practice-mode").forEach((button) => {
    const active = button.dataset.practiceMode === practiceState.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.getElementById("practiceFilterBar").hidden = gradingMode;
  document.getElementById("practiceList").hidden = gradingMode;
  document.getElementById("gradingPracticeWorkspace").hidden = !gradingMode;
  document.getElementById("practiceResultPanel").hidden = gradingMode;
  document.getElementById("gradingResultPanel").hidden = !gradingMode;
}

function renderPracticeList() {
  const target = document.getElementById("practiceList");
  if (!target) {
    return;
  }
  if (practiceState.mode === "grading") {
    return;
  }
  if (practiceState.mode === "fill") {
    renderFillList(target);
    return;
  }
  if (practiceState.mode === "calc") {
    renderCalcList(target);
    return;
  }
  if (practiceState.mode === "proof") {
    renderProofList(target);
    return;
  }

  const questions = practiceQuestions.filter((question) => (
    practiceState.filter === "all" || question.module === practiceState.filter
  ));

  if (!questions.length) {
    target.innerHTML = `<p class="empty-state">该类别暂无选择题。</p>`;
    updatePracticeScore();
    return;
  }
  const question = getCurrentPracticeQuestion(questions);
  renderPracticePage(target, questions, renderPracticeQuestion(question));
  target.querySelectorAll(".practice-option").forEach((button) => {
    button.addEventListener("click", () => submitPracticeAnswer(
      button.dataset.questionId,
      Number(button.dataset.optionIndex),
    ));
  });
  typesetMath(target);
  updatePracticeScore();
}

function getCurrentPracticeQuestion(questions) {
  const mode = practiceState.mode;
  const lastIndex = Math.max(0, questions.length - 1);
  const currentIndex = Math.min(Math.max(0, practiceState.questionIndex[mode] || 0), lastIndex);
  practiceState.questionIndex[mode] = currentIndex;
  return questions[currentIndex];
}

function renderPracticePage(target, questions, questionHtml) {
  const mode = practiceState.mode;
  const currentIndex = practiceState.questionIndex[mode] || 0;
  target.innerHTML = `
    <div class="practice-pager" aria-label="题目切换">
      <button type="button" data-practice-nav="-1" ${currentIndex === 0 ? "disabled" : ""}>上一题</button>
      <strong>第 ${currentIndex + 1} / ${questions.length} 题</strong>
      <button type="button" data-practice-nav="1" ${currentIndex >= questions.length - 1 ? "disabled" : ""}>下一题</button>
    </div>
    <div class="practice-viewport">${questionHtml}</div>
  `;
  target.querySelectorAll("[data-practice-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      practiceState.questionIndex[mode] = Math.min(
        questions.length - 1,
        Math.max(0, currentIndex + Number(button.dataset.practiceNav)),
      );
      renderPracticeList();
    });
  });
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

// ==================== 填空题（学生输入答案，大模型判定） ====================

async function loadFillQuestions() {
  const target = document.getElementById("practiceList");
  if (!target) return;
  target.innerHTML = `<p class="muted-line">正在加载填空题…</p>`;
  try {
    const response = await fetch(`${API_BASE_URL}/api/practice/fill-questions`);
    if (!response.ok) throw new Error(`fill api ${response.status}`);
    const data = await response.json();
    practiceState.fillQuestions = data.questions || [];
  } catch (error) {
    console.warn("填空题加载失败:", error);
    practiceState.fillQuestions = [];
  }
  renderPracticeList();
}

function renderFillList(target) {
  const questions = practiceState.fillQuestions.filter((q) => (
    practiceState.filter === "all" || q.module === practiceState.filter
  ));
  if (!questions.length) {
    target.innerHTML = `<p class="empty-state">该类别暂无填空题。</p>`;
    return;
  }
  const q = getCurrentPracticeQuestion(questions);
  const result = practiceState.fillResults.get(q.id);
  const resultHtml = result
    ? `<div class="practice-explanation ${result.correct ? "correct" : "wrong"}">
        <strong>${result.correct ? "回答正确" : "回答错误"}</strong>
        <p>${escapeHtml(result.comment || "")}</p>
        <p class="muted-line">标准答案：${escapeHtml(result.reference || "")}</p>
      </div>`
    : "";
  renderPracticePage(target, questions, `
    <article class="practice-card">
      <div class="practice-card-header">
        <span>${escapeHtml(q.moduleName)}</span>
      </div>
      <h4>${escapeHtml(q.question)}</h4>
      <div class="fill-answer-row">
        <input class="fill-input" type="text" placeholder="在此输入你的答案…" data-fill-id="${escapeHtml(q.id)}" />
        <button class="fill-submit" type="button" data-fill-submit="${escapeHtml(q.id)}">提交</button>
      </div>
      ${resultHtml}
    </article>
  `);
  target.querySelectorAll(".fill-submit").forEach((button) => {
    button.addEventListener("click", () => submitFillAnswer(button.dataset.fillSubmit));
  });
  target.querySelectorAll(".fill-input").forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        submitFillAnswer(input.dataset.fillId);
      }
    });
  });
  typesetMath(target);
}

async function submitFillAnswer(questionId) {
  const input = document.querySelector(`.fill-input[data-fill-id="${CSS.escape(questionId)}"]`);
  const studentAnswer = input?.value?.trim() || "";
  if (!studentAnswer) {
    input?.focus();
    return;
  }
  const question = practiceState.fillQuestions.find((q) => q.id === questionId);
  if (!question) return;
  const button = document.querySelector(`.fill-submit[data-fill-submit="${CSS.escape(questionId)}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = "判定中…";
  }
  try {
    const response = await postJson("/api/practice/grade-fill", {
      question_id: questionId,
      student_answer: studentAnswer,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || data.detail || "判定失败");
    }
    practiceState.fillResults.set(questionId, {
      correct: Boolean(data.correct),
      comment: data.comment || "",
      reference: data.reference || "",
    });
    reportPracticeEvent(question, Boolean(data.correct), studentAnswer, "fill");
  } catch (error) {
    window.alert(`判定失败：${error.message}`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "提交";
    }
  }
  renderPracticeList();
}

// ==================== 证明题（拍照上传 → OCR 识别） ====================

async function loadCalcQuestions() {
  const target = document.getElementById("practiceList");
  if (!target) return;
  target.innerHTML = `<p class="muted-line">正在加载计算题…</p>`;
  try {
    const response = await fetch(`${API_BASE_URL}/api/practice/calc-questions`);
    if (!response.ok) throw new Error(`calc api ${response.status}`);
    const data = await response.json();
    practiceState.calcQuestions = data.questions || [];
  } catch (error) {
    console.warn("计算题加载失败:", error);
    practiceState.calcQuestions = [];
  }
  renderPracticeList();
}

function renderCalcList(target) {
  const questions = practiceState.calcQuestions.filter((q) => (
    practiceState.filter === "all" || q.module === practiceState.filter
  ));
  if (!questions.length) {
    target.innerHTML = `<p class="empty-state">该类别暂无计算题。</p>`;
    return;
  }
  const q = getCurrentPracticeQuestion(questions);
  const result = practiceState.calcResults.get(q.id);
  const error = practiceState.calcErrors.get(q.id);
  const text = practiceState.calcTexts.get(q.id) || "";
  renderPracticePage(target, questions, `
    <article class="practice-card calc-card" data-calc-id="${escapeHtml(q.id)}">
      <div class="practice-card-header">
        <span>${escapeHtml(q.moduleName)}</span>
        <strong>${escapeHtml(q.nodeId)} · ${escapeHtml(q.kp || "")}</strong>
      </div>
      <h4>${escapeHtml(q.question)}</h4>
      ${q.fig ? `<img class="practice-figure" src="${escapeHtml(q.fig)}" alt="题目图示" />` : ""}
      <p class="muted-line">请在纸上完成计算过程，拍照上传后核对识别文本，也可直接修改文本再提交。</p>
      <div class="calc-action-row">
        <label class="calc-upload-btn" for="calc-file-${escapeHtml(q.id)}">拍照上传</label>
        <input id="calc-file-${escapeHtml(q.id)}" class="calc-file-input" type="file" accept="image/*" capture="environment" data-calc-upload="${escapeHtml(q.id)}" />
        <span class="calc-status" data-calc-status="${escapeHtml(q.id)}"></span>
      </div>
      <div class="calc-ocr-box" data-calc-ocr="${escapeHtml(q.id)}" ${result || text || error ? "" : "hidden"}>
        <strong>识别结果（可核对修正）：</strong>
        <textarea class="calc-ocr-text" rows="6" data-calc-text="${escapeHtml(q.id)}">${escapeHtml(text)}</textarea>
        <div class="calc-action-row">
          <button class="calc-recheck" type="button" data-calc-recheck="${escapeHtml(q.id)}">重新识别</button>
          <button class="calc-submit" type="button" data-calc-submit="${escapeHtml(q.id)}" ${practiceState.calcSubmitting.has(q.id) ? "disabled" : ""}>${practiceState.calcSubmitting.has(q.id) ? "正在智能批阅..." : "提交作答"}</button>
        </div>
        <div class="calc-answer" ${result || error ? "" : "hidden"}>${result ? renderProofGradingResultMarkup(result, q) : `<div class="proof-grading-error">${escapeHtml(error || "批阅失败")}<button type="button" class="calc-retry" data-calc-submit="${escapeHtml(q.id)}">重试批阅</button></div>`}</div>
      </div>
    </article>
  `);
  target.querySelectorAll(".calc-file-input").forEach((input) => input.addEventListener("change", () => handleCalcPhoto(input.dataset.calcUpload, input.files[0])));
  target.querySelectorAll(".calc-recheck").forEach((button) => button.addEventListener("click", () => document.getElementById(`calc-file-${CSS.escape(button.dataset.calcRecheck)}`)?.click()));
  target.querySelectorAll(".calc-submit, .calc-retry").forEach((button) => button.addEventListener("click", () => submitCalcAnswer(button.dataset.calcSubmit)));
  typesetMath(target);
}

async function handleCalcPhoto(questionId, file) {
  if (!file) return;
  const status = document.querySelector(`.calc-status[data-calc-status="${CSS.escape(questionId)}"]`);
  const box = document.querySelector(`.calc-ocr-box[data-calc-ocr="${CSS.escape(questionId)}"]`);
  const textarea = document.querySelector(`.calc-ocr-text[data-calc-text="${CSS.escape(questionId)}"]`);
  if (!status || !box || !textarea) return;
  status.textContent = "识别中…";
  try {
    const base64 = await readFileAsBase64(file);
    const response = await postJson("/api/practice/ocr", { image_base64: base64, filename: file.name || "photo.png" });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || data.detail || "OCR 失败");
    textarea.value = data.text || "";
    practiceState.calcTexts.set(questionId, textarea.value);
    practiceState.calcStartedAt.set(questionId, Date.now());
    box.hidden = false;
    status.textContent = `识别完成（${data.seconds || "?"}s）`;
  } catch (error) {
    status.textContent = "";
    window.alert(`识别失败：${error.message}`);
  }
}

async function submitCalcAnswer(questionId) {
  const question = practiceState.calcQuestions.find((q) => q.id === questionId);
  if (!question || practiceState.calcSubmitting.has(questionId)) return;
  const textarea = document.querySelector(`.calc-ocr-text[data-calc-text="${CSS.escape(questionId)}"]`);
  const answerText = textarea?.value?.trim() || "";
  if (!answerText) { window.alert("请先拍照上传作答内容"); return; }
  practiceState.calcTexts.set(questionId, answerText);
  const startedAt = practiceState.calcStartedAt.get(questionId) || Date.now();
  practiceState.calcStartedAt.set(questionId, startedAt);
  practiceState.calcSubmitting.add(questionId);
  practiceState.calcErrors.delete(questionId);
  try {
    const response = await postJson("/api/grading/grade", {
      question: question.question,
      student_answer: answerText,
      reference_answer: question.answer,
      kp: question.kp || null,
      knowledge_points: question.kp ? [question.kp] : [],
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.error || "批阅失败");
    practiceState.calcResults.set(questionId, result);
    await reportPracticeEvent(question, proofResultIsCorrect(result), answerText, "calc", Date.now() - startedAt);
  } catch (error) {
    practiceState.calcResults.delete(questionId);
    practiceState.calcErrors.set(questionId, error.message || "请稍后重试");
  } finally {
    practiceState.calcSubmitting.delete(questionId);
    renderPracticeList();
  }
}
async function loadProofQuestions() {
  const target = document.getElementById("practiceList");
  if (!target) return;
  target.innerHTML = `<p class="muted-line">正在加载证明题…</p>`;
  try {
    const response = await fetch(`${API_BASE_URL}/api/practice/proof-questions`);
    if (!response.ok) throw new Error(`proof api ${response.status}`);
    const data = await response.json();
    practiceState.proofQuestions = data.questions || [];
  } catch (error) {
    console.warn("证明题加载失败:", error);
    practiceState.proofQuestions = [];
  }
  renderPracticeList();
}

function renderProofList(target) {
  const questions = practiceState.proofQuestions.filter((q) => (
    practiceState.filter === "all" || q.module === practiceState.filter
  ));
  if (!questions.length) {
    target.innerHTML = `<p class="empty-state">该类别暂无证明题。</p>`;
    return;
  }
  const q = getCurrentPracticeQuestion(questions);
  renderPracticePage(target, questions, `
    <article class="practice-card proof-card" data-proof-id="${escapeHtml(q.id)}">
      <div class="practice-card-header">
        <span>${escapeHtml(q.moduleName)}</span>
      </div>
      <h4>${escapeHtml(q.question)}</h4>
      <p class="muted-line">请在纸上作答，然后拍照上传（不支持键盘输入）。</p>
      <div class="proof-action-row">
        <label class="proof-upload-btn" for="proof-file-${escapeHtml(q.id)}">拍照上传</label>
        <input id="proof-file-${escapeHtml(q.id)}" class="proof-file-input" type="file"
               accept="image/*" capture="environment"
               data-proof-upload="${escapeHtml(q.id)}" />
        <span class="proof-status" data-proof-status="${escapeHtml(q.id)}"></span>
      </div>
      <div class="proof-ocr-box" data-proof-ocr="${escapeHtml(q.id)}" ${practiceState.proofResults.has(q.id) || practiceState.proofTexts.has(q.id) ? "" : "hidden"}>
        <strong>识别结果（可核对修正）：</strong>
        <textarea class="proof-ocr-text" rows="6" data-proof-text="${escapeHtml(q.id)}">${escapeHtml(practiceState.proofTexts.get(q.id) || "")}</textarea>
        <div class="proof-action-row">
          <button class="proof-recheck" type="button" data-proof-recheck="${escapeHtml(q.id)}">重新识别</button>
          <button class="proof-submit" type="button" data-proof-submit="${escapeHtml(q.id)}" ${practiceState.proofSubmitting.has(q.id) ? "disabled" : ""}>${practiceState.proofSubmitting.has(q.id) ? "正在智能批阅..." : "提交作答"}</button>
        </div>
        <div class="proof-answer" data-proof-answer="${escapeHtml(q.id)}" ${practiceState.proofResults.has(q.id) || practiceState.proofErrors.has(q.id) ? "" : "hidden"}>${practiceState.proofResults.has(q.id) ? renderProofGradingResultMarkup(practiceState.proofResults.get(q.id), q) : practiceState.proofErrors.has(q.id) ? `<div class="proof-grading-error">${escapeHtml(practiceState.proofErrors.get(q.id))}<button type="button" class="proof-retry" data-proof-submit="${escapeHtml(q.id)}">重试批阅</button></div>` : ""}</div>
      </div>
    </article>
  `);
  target.querySelectorAll(".proof-file-input").forEach((input) => {
    input.addEventListener("change", () => handleProofPhoto(input.dataset.proofUpload, input.files[0]));
  });
  target.querySelectorAll(".proof-recheck").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(`proof-file-${CSS.escape(button.dataset.proofRecheck)}`)?.click();
    });
  });
  target.querySelectorAll(".proof-submit, .proof-retry").forEach((button) => {
    button.addEventListener("click", () => submitProofAnswer(button.dataset.proofSubmit));
  });
  typesetMath(target);
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function handleProofPhoto(questionId, file) {
  if (!file) return;
  const status = document.querySelector(`.proof-status[data-proof-status="${CSS.escape(questionId)}"]`);
  const box = document.querySelector(`.proof-ocr-box[data-proof-ocr="${CSS.escape(questionId)}"]`);
  const textarea = document.querySelector(`.proof-ocr-text[data-proof-text="${CSS.escape(questionId)}"]`);
  if (!status || !box || !textarea) return;
  status.textContent = "识别中…";
  try {
    const base64 = await readFileAsBase64(file);
    const response = await postJson("/api/practice/ocr", {
      image_base64: base64,
      filename: file.name || "photo.png",
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || data.detail || "OCR 失败");
    }
    textarea.value = data.text || "";
    practiceState.proofTexts.set(questionId, textarea.value);
    box.hidden = false;
    status.textContent = `识别完成（${data.seconds || "?"}s）`;
  } catch (error) {
    status.textContent = "";
    window.alert(`识别失败：${error.message}`);
  }
}

function proofResultIsCorrect(result) {
  return result && !result.needs_manual_review ? Number(result.total_score) >= 60 : null;
}

function renderProofGradingResultMarkup(result, question) {
  const dimensions = [
    ["conclusion_correctness", "结论正确性", 20],
    ["key_reasoning_steps", "关键推理步骤", 35],
    ["logical_rigor", "逻辑严密性", 25],
    ["definition_theorem_usage", "定义和定理使用", 10],
    ["expression_notation", "表达与符号规范", 10],
  ];
  const dimensionHtml = dimensions.map(([key, label, max]) => {
    const score = Number(result.dimension_scores?.[key] ?? 0);
    const percent = Math.max(0, Math.min(100, score / max * 100));
    return `<div class="proof-dimension"><div><span>${label}</span><strong>${score.toFixed(1)} / ${max}</strong></div><div class="proof-dimension-track"><span style="width:${percent}%"></span></div></div>`;
  }).join("");
  const errors = Array.isArray(result.error_types) && result.error_types.length
    ? result.error_types.map((item) => `<span class="proof-error-tag">${escapeHtml(item)}</span>`).join("")
    : '<span class="muted-line">未识别到结构性错误</span>';
  const evidence = Array.isArray(result.evidence) && result.evidence.length
    ? result.evidence.map((item) => `<div class="proof-evidence-item"><strong>${escapeHtml(item.dimension || "评分依据")}</strong><p>“${escapeHtml(item.student_excerpt || "") }”</p><span>${escapeHtml(item.reason || "")}</span></div>`).join("")
    : '<p class="muted-line">暂无详细评分依据。</p>';
  const review = result.needs_manual_review
    ? `<div class="proof-review-warning"><strong>建议人工复核</strong><ul>${(result.review_reasons || ["该答案需要进一步确认"]).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul></div>`
    : "";
  return `<div class="proof-grading-result"><div class="proof-score-head"><span>自动批阅结果</span><strong>${Number(result.total_score || 0).toFixed(1)}<small> / 100</small></strong></div><div class="proof-dimensions">${dimensionHtml}</div><div class="proof-feedback"><strong>批阅反馈</strong><p>${escapeHtml(result.feedback || "暂无反馈")}</p></div><div class="proof-errors"><strong>错误类型</strong><div>${errors}</div></div><div class="proof-evidence-list"><strong>评分依据</strong>${evidence}</div>${review}<details class="proof-reference"><summary>查看参考答案</summary><p>${escapeHtml(question.answer || "暂无参考答案")}</p></details></div>`;
}

async function submitProofAnswer(questionId) {
  const question = practiceState.proofQuestions.find((q) => q.id === questionId);
  if (!question || practiceState.proofSubmitting.has(questionId)) return;
  const textarea = document.querySelector(`.proof-ocr-text[data-proof-text="${CSS.escape(questionId)}"]`);
  const answerText = textarea?.value?.trim() || "";
  if (!answerText) { window.alert("请先拍照上传作答内容"); return; }
  practiceState.proofTexts.set(questionId, answerText);
  const startedAt = practiceState.proofStartedAt.get(questionId) || Date.now();
  practiceState.proofStartedAt.set(questionId, startedAt);
  practiceState.proofSubmitting.add(questionId);
  try {
    const response = await postJson("/api/grading/grade", {
      question: question.question,
      student_answer: answerText,
      reference_answer: question.answer,
      kp: question.kp || null,
      knowledge_points: question.kp ? [question.kp] : [],
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.error || "批阅失败");
    practiceState.proofResults.set(questionId, result);
    await reportPracticeEvent(question, proofResultIsCorrect(result), answerText, "proof", Date.now() - startedAt);
  } catch (error) {
    practiceState.proofResults.delete(questionId);
    practiceState.proofErrors.set(questionId, error.message || "请稍后重试");
  } finally {
    practiceState.proofSubmitting.delete(questionId);
    renderPracticeList();
  }
}
async function reportPracticeEvent(question, isCorrect, answerText, questionType, durationMs = null) {
  // 统一上报做题事件（供学情统计：搜索/问答/答题全维度评估掌握度）
  try {
    const response = await postJson("/api/learning/events", {
      user_id: getCurrentUserId(),
      question_id: question.id,
      question_type: questionType,
      module: question.module,
      node_id: question.nodeId,
      is_correct: isCorrect,
      duration_ms: durationMs,
      answer_text: answerText,
    });
    if (!response.ok) throw new Error("events failed");
  } catch (error) {
    console.warn("做题事件上报失败:", error);
  }
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
  // 同步写入学情事件（填空题/批阅题已上报，选择题补齐：供 path/report/时间线使用）
  reportPracticeEvent(question, isCorrect, "", "single");
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
    const [reportResponse, profileResponse] = await Promise.all([
      fetchLearningReport(userId),
      authenticatedFetch(`/api/learning/ability-profile?user_id=${encodeURIComponent(userId)}`),
    ]);
    const [data, profile] = await Promise.all([
      reportResponse.json().catch(() => ({})),
      profileResponse.json().catch(() => ({})),
    ]);
    if (!reportResponse.ok) throw new Error(readApiError(data, "学情报告请求失败"));
    if (!profileResponse.ok) throw new Error(readApiError(profile, "能力画像请求失败"));

    const report = normalizeLearningReport({
      ...data,
      ability_profile: profile,
      module_scores: profile.radar_data,
      weak_nodes: profile.weak_nodes,
    });
    renderLearningReport(report);
    await loadRecommendedLearningPath(report);
  } catch (error) {
    if (options.silent) return;
    learningState.report = null;
    chartBox.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
    weakBox.innerHTML = `<p class="error">无法读取真实能力画像。</p>`;
    pathBox.innerHTML = `<p class="error">路径接口暂不可用。</p>`;
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

// 轻量拉取当前用户 mastery 并写入 graphState.masteryByNode，不重渲染学情面板。
// 知识图谱节点颜色（getGraphNodeStyle -> getNodeMastery）依赖这个 Map。
// loadLearningReport 会在学情页调用，graph 页没有入口，所以单独抽一个。
async function refreshGraphMastery() {
  const userId = getCurrentUserId();
  if (!userId) return;
  try {
    const response = await fetchLearningReport(userId);
    if (!response || !response.ok) return;
    const data = await response.json();
    const records = Array.isArray(data.node_mastery) ? data.node_mastery : [];
    records.forEach((record) => {
      if (!record || !record.node_id) return;
      const level = Number(record.level ?? record.mastery_level ?? 0);
      const existing = graphState.masteryByNode.get(record.node_id) || {};
      graphState.masteryByNode.set(record.node_id, {
        ...existing,
        node_id: record.node_id,
        level,
        correct_count: Number(record.correct_count ?? existing.correct_count ?? 0),
        total_count: Number(record.total_count ?? existing.total_count ?? 0),
        module: record.module || existing.module || "",
      });
    });
  } catch (error) {
    // 静默失败：图谱照常渲染，只是颜色都按 unlearned
  }
}

async function loadAiSummary() {
  const target = document.getElementById("aiSummaryResult");
  if (!target) return;
  const userId = getCurrentUserId();
  if (!userId) {
    target.textContent = "请先登录后再生成学情分析。";
    return;
  }

  target.textContent = "正在综合问答与答题数据生成学情分析...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/learning/ai-summary?user_id=${encodeURIComponent(userId)}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "学情分析生成失败");
    }
    target.textContent = data.summary || "暂无足够学情数据。";
    target.classList.remove("muted-line");
  } catch (error) {
    target.textContent = `学情分析失败：${error.message}`;
  }
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
      const existing = target.find((node) => node.node_id === record.node_id);
      if (existing) {
        // 把 node_mastery 里的统计字段（正确数 / 总数 / 准确率）合并到已有的 weak 节点上，
        // 让"答对 X/Y"能跟 ability-profile 的"正确率"同时显示。
        Object.assign(existing, {
          correct_count: record.correct_count,
          total_count: record.total_count,
          accuracy: record.accuracy,
          module: existing.module || record.module,
        });
      } else {
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

  const overallScore = Number(report.ability_profile?.overall_score ?? 0);
  document.getElementById("abilityOverallScore").textContent = Number.isFinite(overallScore)
    ? overallScore.toFixed(1)
    : "0";
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
  document.getElementById("dashboardCurrentNode").textContent = learningState.currentNodeName || "尚未选择知识点";

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

function updateRoleInterface() {
  classState.role = ["teacher", "admin"].includes(authState.user?.role) ? "teacher" : "student";
  const roleName = formatRole(classState.role);
  document.getElementById("classRoleName").textContent = `${roleName} · ${authState.user?.name || "--"}`;
  document.getElementById("studentClassView").hidden = classState.role !== "student";
  document.getElementById("teacherClassView").hidden = classState.role !== "teacher";
  document.getElementById("studentExamView").hidden = classState.role !== "student";
  document.getElementById("teacherExamView").hidden = classState.role !== "teacher";
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
    classState.studentClass = data.class_info || data;
    authState.user.class_id = classState.studentClass.class_id || classState.studentClass.id;
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
    classState.selectedClassId = data.class_id || data.id;
    document.getElementById("classNameInput").value = "";
    await loadClassWorkspace();
    await loadTeacherClassDetails(classState.selectedClassId);
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
  if (!authState.user) return;
  const userId = getCurrentUserId();
  updateRoleInterface();
  if (classState.role === "teacher") {
    try {
      const data = await fetchApiJson(`/api/class/teacher/${userId}`);
      classState.teacherClasses = data.classes || [];
      renderClassList("teacherClassList", classState.teacherClasses, "教师", true);
      syncTeacherExamClasses();
      if (!classState.teacherClasses.length) renderEmptyClassOverview();
    } catch (error) {
      showClassError("teacherClassList", `班级读取失败：${error.message}`);
      renderEmptyClassOverview("教师班级数据暂不可用。");
    }
    return;
  }

  const [studentResult, shareResult] = await Promise.allSettled([
    fetchApiJson(`/api/class/student/${userId}`),
    fetchApiJson(`/api/share/requests?target_user_id=${userId}`),
  ]);
  if (studentResult.status === "fulfilled") {
    classState.studentClass = studentResult.value.class;
    renderClassList("studentClassList", classState.studentClass ? [classState.studentClass] : [], "已加入");
  } else {
    showClassError("studentClassList", `班级读取失败：${studentResult.reason.message}`);
  }
  if (shareResult.status === "fulfilled") {
    renderIncomingShareRequests((shareResult.value.requests || []).filter((item) => item.status === "pending"));
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
  target.innerHTML = items.map((item) => `<article class="class-row"><div><strong>${escapeHtml(item.name || "未命名班级")}</strong><span>${escapeHtml(roleLabel)} · 邀请码 ${escapeHtml(item.invite_code || "--")}</span></div>${selectable ? `<button type="button" class="class-detail-button" data-class-id="${Number(item.class_id || item.id)}">查看学情</button>` : '<span class="source-badge synced">已同步</span>'}</article>`).join("");
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
      fetchApiJson(`/api/class/${classId}/students?requester_id=${getCurrentUserId()}`),
      fetchApiJson(`/api/class/${classId}/report?requester_id=${getCurrentUserId()}`),
    ]);
    const students = reportData.students || studentsData.students || [];
    const average = Math.round(Number(reportData.overall_accuracy || 0) * 100);
    const attention = students.filter((item) => Number(item.learning_summary?.weak_nodes || 0) > 0).length;
    overview.innerHTML = `<div><span>学生人数</span><strong>${students.length}</strong></div><div><span>平均正确率</span><strong>${average}%</strong></div><div><span>待关注学生</span><strong>${attention}</strong></div>`;
    renderStudentReports(students);
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
  target.innerHTML = reports.map((item) => {
    const summary = item.learning_summary || item.summary || {};
    const weakCount = Number(summary.weak_nodes || 0);
    return `<article><div><strong>${escapeHtml(item.name || item.user?.name || `用户 ${item.user_id || item.user?.id}`)}</strong><span>答题 ${Number(summary.total_answers || 0)} 次 · 正确率 ${Math.round(Number(summary.overall_accuracy || 0) * 100)}%</span></div><span class="mastery-badge ${weakCount ? "weak" : "mastered"}">${weakCount ? `薄弱 ${weakCount}` : "状态良好"}</span></article>`;
  }).join("");
}

function renderIncomingShareRequests(requests) {
  const target = document.getElementById("incomingShareRequests");
  if (!requests.length) {
    target.className = "approval-list empty-state";
    target.textContent = "暂无待处理申请。";
    return;
  }
  target.className = "approval-list";
  target.innerHTML = requests.map((item) => `<article><div><strong>${escapeHtml(item.requester_name || `用户 ${item.requester_id}`)}</strong><span>申请查看你的学情</span></div><div class="approval-actions"><button type="button" data-share-id="${Number(item.request_id || item.id)}" data-approved="true">同意</button><button type="button" class="ghost-button" data-share-id="${Number(item.request_id || item.id)}" data-approved="false">拒绝</button></div></article>`).join("");
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
  const response = await authenticatedFetch(path);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(readApiError(data, `请求失败（${response.status}）`));
  return data;
}

async function postJson(path, payload) {
  return authenticatedFetch(path, { method: "POST", body: JSON.stringify(payload) });
}

function authenticatedFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (authState.token) headers.set("Authorization", `Bearer ${authState.token}`);
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers });
}

async function loadExamWorkspace() {
  if (!authState.user) return;
  updateRoleInterface();
  if (classState.role === "teacher") {
    await loadClassWorkspace();
    syncTeacherExamClasses();
    return;
  }
  await loadStudentExams();
}

async function loadStudentExams() {
  const target = document.getElementById("studentExamList");
  target.hidden = false;
  target.className = "exam-list empty-state";
  target.textContent = "正在读取已发布考试...";
  document.getElementById("examForm").hidden = true;
  document.getElementById("examResult").hidden = true;
  try {
    examState.available = await fetchApiJson(`/api/exam/student/${getCurrentUserId()}`);
    renderStudentExamList();
  } catch (error) {
    target.className = "exam-list error-state";
    target.textContent = `考试读取失败：${error.message}`;
  }
}

function renderStudentExamList() {
  const target = document.getElementById("studentExamList");
  if (!examState.available.length) {
    target.className = "exam-list empty-state";
    target.textContent = authState.user?.class_id ? "所在班级暂无已发布考试。" : "请先加入班级，之后可以在这里参加教师发布的考试。";
    return;
  }
  target.className = "exam-list";
  target.innerHTML = examState.available.map((exam) => `
    <article>
      <div><strong>${escapeHtml(exam.title)}</strong><span>${formatDateTime(exam.created_at)} · 满分 ${Number(exam.total_score)}</span></div>
      <span class="source-badge ${exam.submitted ? "synced" : "local"}">${exam.submitted ? "已提交" : "待作答"}</span>
      <button type="button" data-exam-id="${Number(exam.exam_id)}" ${exam.submitted ? "disabled" : ""}>${exam.submitted ? "已完成" : "进入考试"}</button>
    </article>`).join("");
  target.querySelectorAll("[data-exam-id]:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => openStudentExam(Number(button.dataset.examId)));
  });
}

async function openStudentExam(examId) {
  const target = document.getElementById("studentExamList");
  target.className = "exam-list empty-state";
  target.textContent = "正在加载试卷...";
  try {
    const exam = await fetchApiJson(`/api/exam/${examId}`);
    examState.examId = exam.exam_id;
    examState.questions = (exam.questions || []).map((question) => ({
      id: question.question_id,
      nodeId: question.node_id,
      type: question.question_type,
      question: question.content,
      score: Number(question.score || 0),
    }));
    examState.answers.clear();
    document.getElementById("examTitle").textContent = exam.title;
    target.hidden = true;
    document.getElementById("examResult").hidden = true;
    document.getElementById("examForm").hidden = false;
    renderExamPaper();
    startExamTimer();
  } catch (error) {
    target.className = "exam-list error-state";
    target.textContent = `试卷加载失败：${error.message}`;
  }
}

function renderExamPaper() {
  const form = document.getElementById("examForm");
  form.innerHTML = examState.questions.map((question, index) => `
    <fieldset class="exam-question">
      <legend><span>${index + 1}</span>${escapeHtml(question.question)}</legend>
      <small>${escapeHtml(question.type)} · ${question.score} 分 · ${escapeHtml(question.nodeId)}</small>
      <label class="exam-answer-label" for="exam-answer-${question.id}">你的答案</label>
      <textarea id="exam-answer-${question.id}" data-question-id="${question.id}" rows="3" placeholder="${String(question.type).includes("选择") ? "输入选项字母，例如 A" : "输入完整作答过程"}"></textarea>
    </fieldset>
  `).join("") + '<div class="button-row"><button id="leaveExamButton" class="ghost-button" type="button">返回列表</button><button type="submit" class="submit-exam-button">提交试卷</button></div>';
  form.querySelectorAll("[data-question-id]").forEach((input) => {
    input.addEventListener("input", () => {
      const answer = input.value.trim();
      if (answer) examState.answers.set(Number(input.dataset.questionId), answer);
      else examState.answers.delete(Number(input.dataset.questionId));
      updateExamStatus();
    });
  });
  document.getElementById("leaveExamButton").addEventListener("click", resetExam);
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
  if (!examState.examId) return;
  const submitButton = event.currentTarget?.querySelector('.submit-exam-button');
  if (submitButton) submitButton.disabled = true;
  document.getElementById("examSubmitStatus").textContent = "提交中";
  try {
    const response = await postJson("/api/exam/submit", {
      exam_id: examState.examId,
      user_id: getCurrentUserId(),
      answers: examState.questions.map((question) => ({
        question_id: question.id,
        answer: examState.answers.get(question.id) || "",
      })),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(readApiError(data, "试卷提交失败"));
    clearInterval(examState.timer);
    renderExamSubmission(data);
  } catch (error) {
    document.getElementById("examSubmitStatus").textContent = "提交失败";
    const target = document.getElementById("examResult");
    target.hidden = false;
    target.className = "exam-result error-state";
    target.textContent = `提交失败：${error.message}`;
    if (submitButton) submitButton.disabled = false;
  }
}

function renderExamSubmission(data) {
  const target = document.getElementById("examResult");
  target.hidden = false;
  target.className = "exam-result";
  const pending = data.status === "pending_review";
  target.innerHTML = `
    <div class="exam-score"><span>${pending ? "自动判分得分" : "本次得分"}</span><strong>${Number(data.total_score || 0)}</strong><small>${pending ? "主观题等待教师复核" : "判分完成并已更新学情"}</small></div>
    <div class="exam-review">${(data.answers || []).map((answer, index) => `<article class="${answer.is_correct === false ? "wrong" : "correct"}"><strong>${index + 1}. ${answer.review_status === "pending_review" ? "待复核" : answer.is_correct ? "正确" : "错误"}</strong><p>本题得分 ${Number(answer.score || 0)}</p></article>`).join("")}</div>
    <button id="backToExamListButton" type="button">返回考试列表</button>`;
  document.getElementById("examForm").hidden = true;
  document.getElementById("backToExamListButton").addEventListener("click", resetExam);
  document.getElementById("examSubmitStatus").textContent = pending ? "待复核" : "已提交";
  updateExamStatus();
  renderDashboard();
}

function resetExam() {
  clearInterval(examState.timer);
  examState.questions = [];
  examState.examId = null;
  examState.answers.clear();
  examState.secondsLeft = 900;
  renderExamTimer();
  document.getElementById("examForm").hidden = true;
  document.getElementById("examResult").hidden = true;
  document.getElementById("studentExamList").hidden = false;
  document.getElementById("examTitle").textContent = "我的班级考试";
  document.getElementById("examSubmitStatus").textContent = "待选择";
  updateExamStatus();
  loadStudentExams();
}

function updateExamStatus() {
  document.getElementById("examQuestionCount").textContent = examState.questions.length;
  document.getElementById("examAnsweredCount").textContent = examState.answers.size;
}

function syncTeacherExamClasses() {
  const select = document.getElementById("examClassSelect");
  const classes = classState.teacherClasses || [];
  select.innerHTML = classes.length
    ? classes.map((item) => `<option value="${Number(item.class_id || item.id)}">${escapeHtml(item.name)}</option>`).join("")
    : '<option value="">请先创建班级</option>';
  select.disabled = !classes.length;
  document.querySelector('#generateExamForm button[type="submit"]').disabled = !classes.length;
  document.getElementById("teacherExamClassCount").textContent = classes.length;
}

async function generateTeacherExam(event) {
  event.preventDefault();
  const classId = Number(document.getElementById("examClassSelect").value);
  const title = document.getElementById("teacherExamTitle").value.trim();
  const nodeIds = document.getElementById("teacherExamNodes").value.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean);
  const questionCount = Number(document.getElementById("teacherExamCount").value);
  const target = document.getElementById("teacherExamResult");
  if (!classId || !title || !nodeIds.length) return;
  target.className = "exam-result empty-state";
  target.textContent = "正在从题库生成试卷...";
  try {
    const response = await postJson("/api/exam/generate", {
      teacher_id: getCurrentUserId(),
      class_id: classId,
      title,
      node_ids: nodeIds,
      question_count: questionCount,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(readApiError(data, "考试生成失败"));
    examState.latestTeacherExamId = data.exam_id;
    target.className = "exam-result";
    target.innerHTML = `<div class="tool-status-banner success"><div><span>试卷已发布</span><strong>${escapeHtml(data.title)}</strong></div><span>${data.questions.length} 道题 · 满分 ${Number(data.total_score)}</span></div><div class="teacher-question-list">${data.questions.map((question, index) => `<article><strong>${index + 1}. ${escapeHtml(question.content)}</strong><span>${escapeHtml(question.question_type)} · ${Number(question.score)} 分 · 答案 ${escapeHtml(question.answer || "人工复核")}</span></article>`).join("")}</div>`;
    document.getElementById("teacherLatestExam").textContent = `#${data.exam_id}`;
    document.getElementById("teacherLatestExamCount").textContent = data.questions.length;
    document.getElementById("loadExamResultsButton").disabled = false;
  } catch (error) {
    target.className = "exam-result error-state";
    target.textContent = `发布失败：${error.message}`;
  }
}

async function loadTeacherExamResults() {
  if (!examState.latestTeacherExamId) return;
  const target = document.getElementById("teacherExamAnalytics");
  target.className = "student-report-list empty-state";
  target.textContent = "正在读取成绩...";
  try {
    const data = await fetchApiJson(`/api/exam/${examState.latestTeacherExamId}/results?requester_id=${getCurrentUserId()}`);
    target.className = "student-report-list";
    target.innerHTML = `<article><div><strong>提交 ${Number(data.submitted_count)} 人</strong><span>平均 ${Number(data.average_score)} · 最高 ${Number(data.highest_score)} · 最低 ${Number(data.lowest_score)}</span></div></article>${(data.students || []).map((student) => `<article><div><strong>${escapeHtml(student.name)}</strong><span>${formatDateTime(student.submitted_at)}</span></div><span class="mastery-badge ${Number(student.total_score) >= 60 ? "mastered" : "weak"}">${Number(student.total_score)} 分</span></article>`).join("")}`;
  } catch (error) {
    target.className = "student-report-list error-state";
    target.textContent = `成绩读取失败：${error.message}`;
  }
}

function formatDateTime(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

async function loadGradingQuestions() {
  const type = document.getElementById("gradingQuestionType").value;
  const select = document.getElementById("gradingQuestionSelect");
  select.innerHTML = '<option value="">正在读取结构化题库...</option>';
  try {
    const data = await fetchApiJson(`/api/kb/structured-questions?type=${encodeURIComponent(type)}&limit=50`);
    gradingState.questions = Array.isArray(data.questions) ? data.questions : [];
    select.innerHTML = gradingState.questions.length
      ? gradingState.questions.map((question, index) => `<option value="${index}">${escapeHtml(window.GradingUtils.gradingQuestionSummary(question.question))}</option>`).join("")
      : '<option value="">该类型暂无结构化题目</option>';
    gradingState.loaded = true;
    if (gradingState.questions.length) {
      select.value = "0";
      selectGradingQuestion();
    }
  } catch (error) {
    gradingState.questions = [];
    select.innerHTML = `<option value="">题库读取失败：${escapeHtml(error.message)}</option>`;
  }
}

function selectGradingQuestion() {
  const index = Number(document.getElementById("gradingQuestionSelect").value);
  const question = gradingState.questions[index];
  if (!question) return;
  gradingState.selectedQuestion = question;
  gradingState.startedAt = Date.now();
  document.getElementById("gradingQuestion").value = question.question || "";
  const questionInput = document.getElementById("gradingQuestion");
  const questionPreview = document.getElementById("gradingQuestionPreview");
  questionPreview.innerHTML = window.GradingUtils.formatGradingText(question.question || "");
  questionPreview.hidden = false;
  questionInput.hidden = true;
  typesetMath(questionPreview);
  document.getElementById("gradingReference").value = question.answer || "";
  document.getElementById("gradingKp").value = question.kp || "general";
  document.getElementById("gradingModule").value = getGradingModule(question.kp);
  document.getElementById("gradingStudentAnswer").value = "";
  resetGradingResult();
}

function getGradingModule(kp = "") {
  const value = String(kp);
  if (/graph|connect|hamilton|tree|color|digraph/.test(value)) return "图论";
  if (/set|function|cardinality|ie-/.test(value)) return "集合论";
  if (/relation/.test(value)) return "关系";
  if (/pred/.test(value)) return "谓词逻辑";
  if (/gcd|congruence/.test(value)) return "初等数论";
  if (/combin|inclusion|gen-func|recurrence|polya/.test(value)) return "组合数学";
  if (/algebra|group|semigroup/.test(value)) return "代数结构";
  return "命题逻辑";
}

function resetGradingResult() {
  document.getElementById("gradingScore").textContent = "--";
  const badge = document.getElementById("gradingStatusBadge");
  badge.className = "mastery-badge unlearned";
  badge.textContent = "待提交";
  document.getElementById("gradingDimensions").className = "grading-dimensions empty-state";
  document.getElementById("gradingDimensions").textContent = "提交后展示五维评分。";
  document.getElementById("gradingComment").textContent = "等待批阅。";
  document.getElementById("gradingErrorTypes").innerHTML = "<span>暂无</span>";
}

async function handleGradingPhoto(file) {
  if (!file || !gradingState.selectedQuestion) return;
  const status = document.getElementById("gradingOcrStatus");
  const recheck = document.getElementById("gradingRecheckButton");
  gradingState.ocrFile = file;
  if (status) status.textContent = "正在识别图片...";
  if (recheck) recheck.disabled = true;
  try {
    const base64 = await readFileAsBase64(file);
    const response = await postJson("/api/practice/ocr", {
      image_base64: base64,
      filename: file.name || "photo.png",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      throw new Error(data.error || data.detail || "OCR 识别失败");
    }
    document.getElementById("gradingStudentAnswer").value = data.text || "";
    if (status) status.textContent = `识别完成${data.seconds ? `（${data.seconds} 秒）` : ""}，可修改后提交`;
  } catch (error) {
    if (status) status.textContent = `识别失败：${error.message}`;
  } finally {
    if (recheck) recheck.disabled = false;
  }
}

async function submitForGrading(event) {
  event.preventDefault();
  const button = document.getElementById("submitGradingButton");
  const payload = {
    question: document.getElementById("gradingQuestion").value.trim(),
    student_answer: document.getElementById("gradingStudentAnswer").value.trim(),
    reference_answer: document.getElementById("gradingReference").value.trim(),
    kp: document.getElementById("gradingKp").value.trim(),
    knowledge_points: [document.getElementById("gradingKp").value.trim()].filter(Boolean),
    module: document.getElementById("gradingModule").value.trim(),
    max_score: Number(document.getElementById("gradingMaxScore").value),
  };
  if (!payload.question || !payload.student_answer) return;

  button.disabled = true;
  button.textContent = "正在按五个维度批阅...";
  const badge = document.getElementById("gradingStatusBadge");
  badge.className = "mastery-badge learning";
  badge.textContent = "批阅中";
  try {
    const response = await postJson("/api/grading/grade", payload);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error("批阅引擎尚未合入当前后端，请队员1提供 POST /api/grading/grade");
      }
      throw new Error(readApiError(data, `批阅请求失败（${response.status}）`));
    }
    renderGradingResult(data);
    await recordGradingEvent(data, payload);
  } catch (error) {
    badge.className = "mastery-badge weak";
    badge.textContent = "批阅失败";
    document.getElementById("gradingDimensions").className = "grading-dimensions error-state";
    document.getElementById("gradingDimensions").textContent = error.message;
    document.getElementById("gradingComment").textContent = "未生成评分结果，请确认批阅接口与模型服务状态。";
  } finally {
    button.disabled = false;
    button.textContent = "提交智能批阅";
  }
}

function renderGradingResult(data) {
  const normalized = window.GradingUtils.normalizeGradingResult(data);
  const score = normalized.score;
  const maxScore = normalized.maxScore;
  const ratio = window.GradingUtils.gradingResultRatio(data);
  document.getElementById("gradingScore").textContent = `${score}/${maxScore}`;
  const badge = document.getElementById("gradingStatusBadge");
  badge.className = `mastery-badge ${ratio >= 0.85 ? "mastered" : ratio >= 0.6 ? "learning" : "weak"}`;
  badge.textContent = ratio >= 0.85 ? "优秀" : ratio >= 0.6 ? "达标" : "需订正";

  const dimensions = normalized.dimensions;
  const target = document.getElementById("gradingDimensions");
  target.className = "grading-dimensions";
  target.innerHTML = dimensions.length ? dimensions.map((dimension) => {
    const dimensionScore = Number(dimension.score || 0);
    const dimensionMax = Number(dimension.maxScore || maxScore);
    const percent = Math.max(0, Math.min(100, Math.round((dimensionScore / dimensionMax) * 100)));
    return `<article><div><strong>${escapeHtml(dimension.name || "评分维度")}</strong><span>${dimensionScore}/${Number(dimensionMax.toFixed(2))}</span></div><div class="dimension-track"><span style="width:${percent}%"></span></div></article>`;
  }).join("") : '<p class="empty-state">接口未返回五维评分明细。</p>';
  document.getElementById("gradingComment").textContent = normalized.comment || "批阅完成，暂无补充评语。";
  const errors = normalized.errors;
  document.getElementById("gradingErrorTypes").innerHTML = errors.length
    ? errors.map((item) => `<span>${escapeHtml(window.GradingUtils.gradingErrorLabel(item))}</span>`).join("")
    : "<span>未发现典型错误</span>";
}

async function recordGradingEvent(result, payload) {
  const selected = gradingState.selectedQuestion;
  const questionType = document.getElementById("gradingQuestionType").value;
  const normalized = window.GradingUtils.normalizeGradingResult(result);
  const maxScore = normalized.maxScore;
  // node_id 必须用真实的 leaf 节点 ID（如 pl_02_02、fl_01_01），否则 mastery 计算找不到节点。
  // 旧实现用 `grading_${payload.kp}` 伪 ID，导致批阅/计算题做完不增长 mastery。
  const realNodeId = selected?.nodeId || selected?.node_id || payload.kp || payload.node_id || "unknown";
  const eventPayload = {
    user_id: getCurrentUserId(),
    question_id: selected?.id || `manual-${Date.now()}`,
    question_type: questionType === "calc" ? "calc" : "proof",
    module: payload.module,
    node_id: String(realNodeId).slice(0, 100),
    is_correct: maxScore ? normalized.score / maxScore >= 0.6 : null,
    duration_ms: Math.max(0, Date.now() - gradingState.startedAt),
    answer_text: payload.student_answer,
  };
  try {
    const response = await postJson("/api/learning/events", eventPayload);
    if (!response.ok) console.warn("批阅事件记录失败：", response.status);
  } catch (error) {
    console.warn("批阅事件记录失败：", error);
  }
}

async function loadLearningTimeline(userId) {
  const target = document.getElementById("learningTimeline");
  target.className = "learning-timeline empty-state";
  target.textContent = "正在读取做题历史...";
  try {
    const data = await fetchApiJson(`/api/learning/events?user_id=${encodeURIComponent(userId)}&limit=30`);
    renderLearningTimeline(data.events || []);
  } catch (error) {
    target.className = "learning-timeline error-state";
    target.textContent = `做题历史读取失败：${error.message}`;
  }
}

function renderLearningTimeline(events) {
  const target = document.getElementById("learningTimeline");
  if (!events.length) {
    target.className = "learning-timeline empty-state";
    target.textContent = "暂无做题记录。完成自测、考试或大题批阅后，这里会按时间展示真实事件。";
    return;
  }
  const typeNames = { single: "选择题", fill: "填空题", calc: "计算题", proof: "证明题", exam: "考试" };
  target.className = "learning-timeline";
  target.innerHTML = events.map((event) => {
    const resultClass = event.is_correct === true ? "correct" : event.is_correct === false ? "wrong" : "pending";
    const resultText = event.is_correct === true ? "正确" : event.is_correct === false ? "需巩固" : "待批阅";
    const duration = Number.isFinite(Number(event.duration_ms))
      ? `${Math.max(1, Math.round(Number(event.duration_ms) / 1000))} 秒`
      : "未记录耗时";
    return `
      <article class="timeline-event ${resultClass}">
        <time>${escapeHtml(formatDateTime(event.created_at))}</time>
        <div>
          <strong>${escapeHtml(typeNames[event.question_type] || event.question_type)} · ${escapeHtml(event.module)}</strong>
          <span>${escapeHtml(event.node_id)} · ${escapeHtml(duration)}</span>
        </div>
        <span class="timeline-result">${resultText}</span>
      </article>
    `;
  }).join("");
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
  // 新接口：嵌套 stages + ai_notes（来自 /api/learning/path）
  if (path && typeof path === "object" && !Array.isArray(path) && Array.isArray(path.stages)) {
    renderPathStages(target, path);
    return;
  }
  if (!path.length) {
    target.textContent = "暂无推荐路径。";
    return;
  }

  target.innerHTML = path.slice(0, 10).map((pathItem, index) => {
    const nodeId = typeof pathItem === "string" ? pathItem : pathItem.node_id || pathItem.id;
    const name = typeof pathItem === "string"
      ? nodeNameMap.get(nodeId) || nodeId
      : pathItem.node_name || pathItem.name || nodeNameMap.get(nodeId) || nodeId;
    const action = typeof pathItem === "string" ? "学习" : pathItem.action || "练习";
    const questions = typeof pathItem === "string"
      ? []
      : pathItem.recommended_questions || pathItem.questions || [];
    return `
      <article class="path-step" data-action="${escapeHtml(action)}">
        <div class="path-step-head">
          <span class="path-step-number">${String(pathItem.step || index + 1).padStart(2, "0")}</span>
          <div><strong>${escapeHtml(shortenNodeName(name))}</strong><small>${escapeHtml(nodeId)}</small></div>
          <span class="path-action">${escapeHtml(action)}</span>
        </div>
        ${pathItem.reason ? `<p>${escapeHtml(pathItem.reason)}</p>` : ""}
        <div class="path-question-list">
          ${questions.map((question, questionIndex) => `<button type="button" class="path-question" data-path-index="${index}" data-question-index="${questionIndex}"><span>${escapeHtml(question.stage || `难度 ${question.difficulty || "-"}`)}</span>${escapeHtml(question.content || question.question || "推荐练习")}</button>`).join("")}
        </div>
        <button class="path-learn-button" type="button" data-node-id="${escapeHtml(nodeId)}" data-node-name="${escapeHtml(name)}">进入学习</button>
      </article>
    `;
  }).join("");
  bindLearningNodeButtons(target);
  target.querySelectorAll(".path-question").forEach((button) => {
    button.addEventListener("click", () => {
      const item = path[Number(button.dataset.pathIndex)];
      const questions = item?.recommended_questions || item?.questions || [];
      const question = questions[Number(button.dataset.questionIndex)];
      if (!question) return;
      learningState.currentNodeId = question.node_id || item.node_id;
      learningState.currentNodeName = item.name || item.node_name || findNodeName(learningState.currentNodeId);
      switchTab("chat");
      document.getElementById("questionInput").value = `请引导我完成这道题：${question.content || question.question}`;
    });
  });
}

function renderPathStages(target, pathPayload) {
  const stages = pathPayload.stages || [];
  const aiNotes = pathPayload.ai_notes || {};
  const diagnosis = pathPayload.diagnosis || {};

  if (!stages.length) {
    target.textContent = "暂无推荐路径。";
    return;
  }

  const stageLabels = { foundation: "补基", reinforcement: "巩固", advancement: "提升" };
  const stageIcons = { foundation: "①", reinforcement: "②", advancement: "③" };

  // 顶部 AI 总结 / 诊断文字不在前端展示，直入三段式卡片。
  const headerHtml = "";

  const stagesHtml = stages.map((stage, stageIndex) => {
    const label = stageLabels[stage.stage] || stage.title || stage.stage;
    const icon = stageIcons[stage.stage] || String(stageIndex + 1);
    const nodes = stage.nodes || [];
    if (!nodes.length) return "";
    const nodesHtml = nodes.map((node) => {
      const nodeId = node.node_id;
      const name = node.title && !node.title.includes(":") && !node.title.includes("：")
        ? node.title
        : findNodeName(nodeId) || nodeId;
      const evidence = node.evidence || {};
      const tasks = node.tasks || [];
      const gate = node.mastery_gate || {};
      const conf = typeof node.confidence === "number" ? Math.round(node.confidence * 100) : null;
      const evidenceText = [
        evidence.mastery ? `掌握度 L${evidence.mastery.level ?? 0} · 正确率 ${Math.round((evidence.mastery.accuracy || 0) * 100)}% · ${evidence.mastery.total_count ?? 0} 题` : "",
        evidence.practice && evidence.practice.event_count ? `近 ${evidence.practice.event_count} 次练习 · 错题 ${evidence.practice.wrong_count ?? 0}` : "",
        evidence.qa && evidence.qa.count ? `问答困惑 ${evidence.qa.count} 次` : "",
      ].filter(Boolean).join(" · ");
      const tasksHtml = tasks.map((t) => `<li>${escapeHtml(t.title || t.type || "练习")}</li>`).join("");
      const gateParts = [];
      if (gate.required_questions) gateParts.push(`${gate.required_questions} 题`);
      if (typeof gate.accuracy_at_least === "number") gateParts.push(`正确率 ≥ ${Math.round(gate.accuracy_at_least * 100)}%`);
      return `
        <article class="path-stage-node">
          <div class="path-stage-node-head">
            <div>
              <strong>${escapeHtml(name)}</strong>
              <span class="path-priority">优先级 ${(node.priority || 0).toFixed(0)}</span>
            </div>
            ${conf !== null ? `<span class="path-confidence" title="置信度">${conf}%</span>` : ""}
          </div>
          ${node.reason ? `<p class="path-reason">${escapeHtml(node.reason)}</p>` : ""}
          ${evidenceText ? `<p class="path-evidence muted-line">${escapeHtml(evidenceText)}</p>` : ""}
          ${tasksHtml ? `<ul class="path-tasks">${tasksHtml}</ul>` : ""}
          ${gateParts.length ? `<p class="path-gate">过关条件：${gateParts.map(escapeHtml).join(" · ")}</p>` : ""}
          <button class="path-learn-button" type="button" data-node-id="${escapeHtml(nodeId)}" data-node-name="${escapeHtml(name)}">进入学习</button>
        </article>
      `;
    }).join("");

    return `
      <section class="path-stage">
        <header class="path-stage-header">
          <span class="path-stage-icon">${icon}</span>
          <div>
            <h4>${escapeHtml(label)}${stage.objective ? `<small>${escapeHtml(stage.objective)}</small>` : ""}</h4>
          </div>
        </header>
        <div class="path-stage-nodes">${nodesHtml}</div>
      </section>
    `;
  }).filter(Boolean).join("");

  target.innerHTML = `<div class="path-stages">${headerHtml}${stagesHtml}</div>`;
  bindLearningNodeButtons(target);
}

async function loadRecommendedLearningPath(report) {
  // 演示/截图模式：?no-path=1 跳过路径生成（用于展示"回答前：暂无推荐路径"状态）
  if (new URLSearchParams(location.search).get("no-path") === "1") {
    document.getElementById("recommendedPath").textContent = "暂无推荐路径。";
    return;
  }
  const weakNodes = report.weak.map((node) => node.node_id).filter(Boolean);
  const levels = Object.fromEntries(report.weak.map((node) => [node.node_id, node.level ?? 1]));
  try {
    let response = await authenticatedFetch(`/api/learning/path?user_id=${encodeURIComponent(getCurrentUserId())}`);
    if (response.status === 404 && weakNodes.length) {
      response = await fetch(`${KB_API_BASE_URL}/kb/learning-path`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weak_nodes: weakNodes, levels }),
      });
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(readApiError(data, "学习路径推荐失败"));
    // 后端返回 { stages, path, ai_notes, diagnosis, ... } — 直接把整个对象传给渲染器，
    // 渲染器根据是否含 stages 选择三段式或扁平视图。
    const pathPayload = data.stages ? data : (data.path || data.recommended_path || []);
    const flatPath = Array.isArray(pathPayload) ? pathPayload : (data.path || []);
    graphState.recommendedPath = flatPath.map((item) => typeof item === "string" ? item : item.node_id).filter(Boolean);
    renderRecommendedPath(pathPayload, new Map(report.weak.map((node) => [node.node_id, node.name])));
    report.recommended_path = flatPath;
    report.learning_path = data;
    renderDashboard(report);
    if (graphState.loaded) renderKnowledgeGraph();
  } catch (error) {
    graphState.recommendedPath = [];
    document.getElementById("recommendedPath").innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
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
    if (button.tagName !== "BUTTON") return; // 只响应按钮点击，忽略 article 等容器
    button.addEventListener("click", () => {
      const nodeId = button.dataset.nodeId || DEFAULT_NODE_ID;
      const nodeName = button.dataset.nodeName || findNodeName(nodeId) || "该知识点";
      learningState.currentNodeId = nodeId;
      learningState.currentNodeName = nodeName;
      updateCurrentLearningNodeText();
      switchTab("chat");
      document.getElementById("questionInput").value =
        `请系统讲解「${nodeName}」的定义、定理、典型例题与常见易错点，给出 1-2 道自测题。`;
      document.getElementById("questionInput").focus();
    });
  });
}

function shortenNodeName(name) {
  const parts = String(name || "").split(">").map((part) => part.trim()).filter(Boolean);
  return parts.at(-1) || name || "未知知识点";
}

function formatLearningStat(node) {
  const correct = Number(node.correct_count ?? 0);
  const total = Number(node.total_count ?? node.answer_count ?? 0);
  const accuracyPct = typeof node.accuracy === "number" ? Math.round(node.accuracy * 100) : null;
  if (total > 0) {
    return `答对 ${correct}/${total} · 正确率 ${accuracyPct ?? 0}%`;
  }
  if (accuracyPct !== null) {
    return `正确率 ${accuracyPct}%`;
  }
  return "暂无答题记录";
}

function resetKnowledgeGraph() {
  graphState.expandedModules.clear();
  graphState.expandedConcepts.clear();
  const container = document.getElementById("knowledgeGraphChart");
  container.dataset.renderer = "";
  graphState.teacherLoaded = false;
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
    concept: "章节",
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
    rule: "#20805f",
  };
  return colors[String(type || "").toLowerCase()] || ["#1f5f8b", "#2f8f83", "#6b73d6"][category] || "#6b73d6";
}

function getMasteryColor(status) {
  const colors = {
    mastered: "#20805f",
    learning: "#d39a16",
    weak: "#c43d35",
    unlearned: "#8291a2",
  };
  return colors[status] || colors.unlearned;
}

function getForceGraphNodeStyle(node, category) {
  const status = getMasteryStatus(getNodeMastery(node));
  return {
    color: getNodeColor(node?.type, category),
    borderColor: getMasteryColor(status),
    borderWidth: status === "weak" ? 6 : 4,
    shadowBlur: status === "weak" ? 14 : 5,
    shadowColor: status === "weak" ? "rgba(196,61,53,.48)" : "rgba(24,50,76,.16)",
  };
}

function getGraphNodeStyle(node) {
  const mastery = getNodeMastery(node);
  const status = getMasteryStatus(mastery);
  return {
    color: getMasteryColor(status),
    borderColor: status === "weak" ? "#8e211c" : "#ffffff",
    borderWidth: status === "weak" ? 3 : 1,
    shadowBlur: status === "weak" ? 12 : 4,
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
  const rawLevel = mastery.level ?? mastery.mastery_level;
  const level = Number(rawLevel);
  if (rawLevel !== undefined && rawLevel !== null && Number.isFinite(level)) {
    if (level >= 3) return "mastered";
    if (level >= 2) return "learning";
    if (level > 0) return "weak";
    return "unlearned";
  }
  return ["mastered", "learning", "weak"].includes(mastery.status)
    ? mastery.status
    : "unlearned";
}

function getMasteryLabel(status, level) {
  const labels = { mastered: level >= 4 ? "熟练" : "已掌握", learning: "理解中", weak: "薄弱", unlearned: "未学" };
  return labels[status];
}

function isRecommendedNode(node) {
  return Boolean(node && graphState.recommendedPath.includes(node.nodeId || node.id));
}

function findNodeName(nodeId) {
  if (!nodeId) return "未知知识点";
  if (NODE_NAME_FALLBACKS[nodeId]) return NODE_NAME_FALLBACKS[nodeId];
  for (const module of graphState.modules) {
    if (module.nodeId === nodeId) return module.name;
    for (const concept of module.children || []) {
      if (concept.nodeId === nodeId) return `${module.name} > ${concept.name}`;
      const item = (concept.items || []).find((entry) => entry.nodeId === nodeId);
      if (item) return `${module.name} > ${concept.name} > ${item.name}`;
    }
  }
  return nodeId;
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
