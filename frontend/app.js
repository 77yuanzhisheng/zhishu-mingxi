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
  const localApiPattern = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i;
  let selected = "";
  if (requested && localApiPattern.test(requested)) {
    selected = requested.replace(/\/$/, "");
    localStorage.setItem("dm_api_base_url", selected);
  }
  const stored = localStorage.getItem("dm_api_base_url")?.trim() || "";
  const savedLocalOverride = localApiPattern.test(stored) ? stored : "";
  const isHttpPage = window.location.protocol === "http:" || window.location.protocol === "https:";
  const sameOriginApi = isHttpPage && window.location.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://127.0.0.1:8000";
  return (selected || savedLocalOverride || sameOriginApi).replace(/\/$/, "");
}

const tabRoutes = {
  dashboard: "/",
  chat: "/qa",
  graph: "/knowledge-graph",
  practice: "/practice",
  learning: "/learning",
  companion: "/companion",
  classes: "/classes",
  exam: "/exam",
  lessonPrep: "/lesson-prep",
  tools: "/tool-center",
  textbook: "/textbook-center",
  // ⚠️ 单段路径：见《部署说明》「路由为什么不能用两段」。
  // 两段路径会让浏览器去要 /admin/app.js，nginx 兜底回 HTML → 拒执行 → 白屏。
  teacherApproval: "/teacher-approval",
};

const titles = {
  dashboard: "个人学习仪表盘",
  chat: "推理大拿 · 课程知识问答",
  tools: "离散数学工具中心",
  graph: "离散数学知识图谱",
  practice: "自测练习",
  learning: "学情分析",
  companion: "学习陪伴",
  classes: "班级管理",
  exam: "在线考试",
  lessonPrep: "教师智能备课",
  textbook: "Web 交互式教材 5.0",
  teacherApproval: "教师审批",
};

// 角色专属页：教师端不提供学生向页面，学生端不提供教师向页面。
// 值 = 该角色访问时会被拦下的 tab。仅靠 data-role-only 隐藏导航是不够的——
// 直链、popstate 与页面内按钮仍能触发 switchTab，所以准入判断必须写在 switchTab 里。
const ROLE_BLOCKED_TABS = {
  teacher: new Set(["practice", "companion"]),
  student: new Set(["lessonPrep"]),
};

// 教师端这两个 tab 的标题与学生端不同（侧栏导航文案与顶栏标题都会跟着变）
const TEACHER_TITLES = {
  dashboard: "班级学情总览",
  learning: "班级学情分析",
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
  // ⑤ 图谱布局重构：点节点聚焦 + 浏览历史栈（上一步/下一步）
  nodeHistory: [],
  historyIndex: -1,
  fusionChapterIndex: 0,
  fusionSectionIndex: 0,
  fusionHistory: [],
  // 融合导航数据缓存（仅数据，教师四层树视图不回退恢复）
  teacherGraph: null,
};

const learningState = {
  currentNodeId: DEFAULT_NODE_ID,
  currentNodeName: "关系性质",
  chart: null,
  report: null,
};

const dashboardState = { chart: null };
const gradingState = {
  questions: [], selectedQuestion: null, startedAt: Date.now(), loaded: false,
  ocrFile: null, submitting: false, proofSteps: [], explanationSteps: [], explanationIndex: 0,
};
const chatState = { sessionId: null };
const agentState = { channel: "pending", fallbackReason: "" };
const authState = { token: localStorage.getItem(AUTH_TOKEN_KEY) || "", user: null };
const classState = { role: null, studentClass: null, teacherClasses: [], selectedClassId: null };
// 教师端班级学情总览的状态（与学生端的 learningState 平行，互不影响）
const teacherState = { report: null, classId: null, chart: null };
// 教师端组卷的知识点选择器状态。必须声明在这里、而不是挨着 EXAM_NODE_QUESTION_COUNTS
// 放在文件后半段：下方 DOM 绑定处（约 665 行）会同步读取 onlyWithQuestions 给复选框打勾，
// 而 const 在声明执行前处于 TDZ，放在后面会让整页脚本在加载时抛错白屏。
const examNodeState = {
  catalog: [],
  selected: new Set(),
  query: "",
  onlyWithQuestions: true,   // 默认只列有题的知识点；取消勾选可看到全部模块及"暂无题目"标注
  loading: false,
};
const examState = { examId: null, available: [], questions: [], answers: new Map(), secondsLeft: 900, timer: null, latestTeacherExamId: null, teacherExams: [], latestResult: null, latestExamClassId: null };
const extendedToolState = { current: "formula-simplify", hasseChart: null };
const unifiedToolState = { current: "truth" };
const companionState = { kind: "today", loading: false };
const lessonPrepState = { loading: false, resultText: "" };

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
// 来源：与后端 /kb/knowledge-graph 同源（KG_DATA 生成，模块/概念/条目全覆盖）。
// 来源：knowledge-graph 端点硬编码的概念名称（队员4 整理）。
const NODE_NAME_FALLBACKS = {
  // 模块
  combinatorics: "组合数学",
  induction: "数学归纳法",
  relation: "关系",
  relations: "关系",
  // 概念
  ag_01: "二元运算及其性质",
  ag_02: "代数系统",
  ag_03: "同态与同构",
  ag_04: "群的定义及性质",
  ag_05: "子群与群的陪集分解",
  ag_06: "循环群与置换群",
  ag_07: "环与域",
  ag_08: "格的定义及性质 / 分配格、有补格与布尔代数",
  algebraic_structure: "代数结构",
  cm_01: "加法法则与乘法法则",
  cm_02: "排列与组合",
  cm_03: "二项式定理与组合恒等式",
  cm_04: "多项式定理",
  cm_05: "递推方程的定义及实例等",
  cm_06: "生成函数及其应用 / 指数生成函数及其应用",
  cm_07: "卡塔兰数与斯特林数",
  fl_01: "谓词与量词",
  fl_02: "量词运算与推理",
  graph_theory: "图论",
  gt_01: "图的基本概念",
  gt_02: "路径与连通性",
  gt_03: "重要定理",
  gt_04: "特殊图",
  gt_05: "平面图的基本概念等",
  gt_06: "支配集、点独立集与点覆盖集等",
  mi_01: "普通归纳法",
  mi_02: "强归纳法",
  mi_03: "经典归纳证明",
  nt_01: "素数",
  nt_02: "最大公因数与最小公倍数",
  nt_03: "同余",
  nt_04: "一次同余方程",
  nt_05: "欧拉定理和费马小定理",
  nt_06: "均匀伪随机数的产生方法",
  nt_07: "RSA 公钥密码",
  number_theory: "初等数论",
  pl_01: "命题与联结词",
  pl_02: "真值表与逻辑等价",
  pl_03: "范式与推理规则",
  predicate_logic: "谓词逻辑",
  propositional_logic: "命题逻辑",
  rel_01: "关系基本概念",
  rel_02: "关系五大性质",
  rel_03: "等价关系与等价类",
  rel_04: "偏序关系",
  set_theory: "集合论",
  st_01: "集合基本概念",
  st_02: "集合运算",
  st_03: "集合运算定律",
  st_04: "有穷集的计数",
  st_05: "函数的定义与性质 / 函数的复合与反函数",
  st_06: "双射函数与集合的基数",
  // 条目
  ag_01_01: "二元运算",
  ag_01_02: "运算的性质",
  ag_01_03: "特殊元素",
  ag_02_01: "代数系统与子代数",
  ag_03_01: "同态映射",
  ag_03_02: "同构",
  ag_04_01: "半群与独异点",
  ag_04_02: "群",
  ag_04_03: "群的特例",
  ag_05_01: "子群",
  ag_05_02: "陪集与拉格朗日定理",
  ag_06_01: "循环群",
  ag_06_02: "置换群",
  ag_07_01: "环",
  ag_07_02: "域",
  ag_08_01: "格",
  ag_08_02: "格的实例与性质",
  ag_08_03: "分配格与有补格",
  ag_08_04: "布尔代数",
  cm_01_01: "加法法则",
  cm_01_02: "乘法法则",
  cm_02_01: "排列",
  cm_02_02: "组合",
  cm_03_01: "二项式定理",
  cm_03_02: "组合恒等式",
  cm_04_01: "多项式定理",
  cm_05_01: "递推方程",
  cm_05_02: "常系数线性齐次递推方程",
  cm_05_03: "常系数线性非齐次递推方程",
  cm_05_04: "迭代解法",
  cm_05_05: "主定理与分治递推",
  cm_06_01: "生成函数",
  cm_06_02: "用生成函数求解递推方程",
  cm_06_03: "指数生成函数",
  cm_07_01: "卡塔兰数",
  cm_07_02: "斯特林数",
  fl_01_01: "谓词P(x)",
  fl_01_02: "全称量词∀xP(x)",
  fl_01_03: "存在量词∃xP(x)",
  fl_01_04: "约束变元与自由变元",
  fl_02_01: "量词否定律",
  fl_02_02: "全称例示(UI)",
  fl_02_03: "全称概括(UG)",
  fl_02_04: "存在例示(EI)",
  fl_02_05: "存在概括(EG)",
  fl_02_06: "奇数的平方也是奇数",
  gt_01_01: "图G=(V,E)",
  gt_01_02: "完全图Kₙ",
  gt_01_03: "二部图Kₘ,ₙ",
  gt_01_04: "度deg(v)",
  gt_02_01: "路径v₀e₁v₁...vₙ",
  gt_02_02: "回路/圈",
  gt_02_03: "连通图",
  gt_02_04: "连通分量",
  gt_03_01: "握手定理",
  gt_03_02: "奇度顶点个数必为偶数",
  gt_03_03: "树",
  gt_03_04: "欧拉定理",
  gt_03_05: "Aᵏ[i][j]",
  gt_04_01: "欧拉图",
  gt_04_02: "哈密顿图",
  gt_04_03: "树",
  gt_04_04: "生成树",
  gt_05_01: "平面图与平面嵌入",
  gt_05_02: "欧拉公式",
  gt_05_03: "欧拉公式的应用",
  gt_05_04: "库拉托夫斯基定理",
  gt_05_05: "极大平面图",
  gt_05_06: "对偶图",
  gt_05_07: "对偶图的应用",
  gt_06_01: "支配集",
  gt_06_02: "点独立集",
  gt_06_03: "点覆盖集",
  gt_06_04: "匹配",
  gt_06_05: "边覆盖集",
  gt_06_06: "霍尔定理",
  gt_06_07: "二部图与匹配判定",
  gt_06_08: "匈牙利算法",
  gt_06_09: "点着色",
  gt_06_10: "边着色",
  gt_06_11: "着色的应用",
  mi_01_01: "基础步",
  mi_01_02: "归纳步",
  mi_02_01: "强归纳",
  mi_03_01: "1+2+...+n=n(n+1)/2",
  mi_03_02: "1+3+...+(2n-1)=n²",
  mi_03_03: "n³-n能被3整除",
  mi_03_04: "n<2ⁿ对所有正整数成立",
  mi_03_05: "|P(A)|=2ⁿ（幂集基数）",
  nt_01_01: "整除与带余除法",
  nt_01_02: "素数与合数",
  nt_01_03: "算术基本定理",
  nt_02_01: "最大公因数与欧几里得算法",
  nt_02_02: "互素",
  nt_02_03: "最小公倍数",
  nt_03_01: "同余的定义与性质",
  nt_03_02: "剩余类与剩余系",
  nt_03_03: "同余的应用",
  nt_04_01: "一次同余方程 ax≡b(mod m)",
  nt_04_02: "中国剩余定理",
  nt_05_01: "欧拉函数",
  nt_05_02: "欧拉定理与费马小定理",
  nt_05_03: "数论定理的应用",
  nt_06_01: "伪随机数的产生",
  nt_07_01: "RSA 密钥体制",
  nt_07_02: "RSA 的安全性",
  pl_01_01: "命题",
  pl_01_02: "联结词",
  pl_01_03: "北京是首都",
  pl_02_01: "真值表",
  pl_02_02: "德摩根律",
  pl_02_03: "蕴含等价",
  pl_02_04: "逻辑等价(P≡Q)",
  pl_03_01: "重言式(永真式)",
  pl_03_02: "析取范式(DNF)",
  pl_03_03: "合取范式(CNF)",
  pl_03_04: "范式存在定理",
  pl_03_05: "假言推理",
  pl_03_06: "拒取式",
  pl_03_07: "假言三段论",
  pl_03_08: "归谬法",
  rel_01_01: "二元关系R⊆A×B",
  rel_01_02: "关系矩阵",
  rel_01_03: "定义域dom(R)与值域ran(R)",
  rel_02_01: "自反性",
  rel_02_02: "对称性",
  rel_02_03: "传递性",
  rel_02_04: "反自反性",
  rel_02_05: "反对称性",
  rel_03_01: "等价关系",
  rel_03_02: "等价类[a]",
  rel_03_03: "等价关系决定集合的一个划分",
  rel_03_04: "模n同余关系是等价关系",
  rel_04_01: "偏序关系",
  rel_04_02: "哈斯图",
  rel_04_03: "等价关系与偏序关系的区别",
  rel_04_04: "极大元/极小元、最大元/最小元",
  rel_04_05: "上界/下界、上确界/下确界",
  st_01_01: "集合",
  st_01_02: "子集A⊆B",
  st_01_03: "幂集P(A)",
  st_01_04: "集合相等A=B",
  st_02_01: "并集A∪B",
  st_02_02: "交集A∩B",
  st_02_03: "差集A-B",
  st_02_04: "对称差A⊕B",
  st_02_05: "笛卡尔积A×B",
  st_03_01: "分配律",
  st_03_02: "德摩根律(集合)",
  st_03_03: "幂等律与吸收律",
  st_04_01: "容斥原理（计数版）",
  st_05_01: "函数作为特殊关系",
  st_05_02: "单射、满射与双射",
  st_05_03: "复合函数",
  st_05_04: "反函数",
  st_06_01: "集合的等势与基数",
  st_06_02: "基数的比较与康托尔定理",
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
      { name: "elements", label: "元素集合", type: "json", value: "[1, 2, 4]", hint: "子集关系支持 [a] 或 [\"a\"]；空集支持 []、[Ø] 或 [∅]。" },
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
      { name: "use_llm", label: "使用星火 Qwen3-32B 按完整题意生成", type: "checkbox", value: true },
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
document.getElementById("chatPhotoInput")?.addEventListener("change", (event) => {
  handleChatPhoto(event.target.files[0]);
});
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
// 图谱浏览历史（队员2 任务⑤：上一步/下一步）
document.getElementById("graphHistoryBackButton")?.addEventListener("click", () => gotoGraphHistoryStep(-1));
document.getElementById("graphHistoryForwardButton")?.addEventListener("click", () => gotoGraphHistoryStep(1));
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
document.getElementById("addProofStepButton").addEventListener("click", addProofStep);
document.getElementById("undoProofStepButton").addEventListener("click", undoProofStep);
document.getElementById("finishProofButton").addEventListener("click", finishProof);
document.getElementById("nextProofExplanationButton").addEventListener("click", revealNextProofExplanation);
document.getElementById("continueLearningButton").addEventListener("click", continueLearning);
document.getElementById("generateCompanionButton").addEventListener("click", generateCompanionAdvice);
document.getElementById("companionPracticeButton").addEventListener("click", () => switchTab("practice"));
document.getElementById("companionPathButton").addEventListener("click", () => switchTab("learning"));
document.querySelectorAll(".companion-kind").forEach((button) => {
  button.addEventListener("click", () => setCompanionKind(button.dataset.companionKind));
});
document.getElementById("prepChapterSelect").addEventListener("change", syncPrepSections);
document.getElementById("prepSectionSelect").addEventListener("change", updatePrepDocumentMeta);
document.getElementById("generateLessonPrepButton").addEventListener("click", generateLessonPrep);
document.getElementById("copyLessonPrepButton").addEventListener("click", copyLessonPrep);
document.getElementById("joinClassForm").addEventListener("submit", joinClass);
document.getElementById("createClassForm").addEventListener("submit", createClass);
document.getElementById("shareRequestForm").addEventListener("submit", requestLearningShare);
document.getElementById("loginForm").addEventListener("submit", loginAccount);
document.getElementById("registerForm").addEventListener("submit", registerAccount);
document.getElementById("showLoginButton").addEventListener("click", () => setAuthMode("login"));
document.getElementById("showRegisterButton").addEventListener("click", () => setAuthMode("register"));
document.getElementById("logoutButton").addEventListener("click", logoutAccount);
document.getElementById("generateExamForm").addEventListener("submit", generateTeacherExam);
// 教师端班级学情总览：手动刷新
const teacherDashboardRefreshButton = document.getElementById("teacherDashboardRefresh");
if (teacherDashboardRefreshButton) {
  teacherDashboardRefreshButton.addEventListener("click", () => loadTeacherClassOverview());
}
// 教师审批页：手动刷新（管理员可能开着页面等人注册）
const teacherApprovalRefreshButton = document.getElementById("teacherApprovalRefresh");
if (teacherApprovalRefreshButton) {
  teacherApprovalRefreshButton.addEventListener("click", () => loadPendingTeachers());
}
document.getElementById("loadExamResultsButton").addEventListener("click", loadTeacherExamResults);
// 同 refreshTeacherExamListButton：新按钮必须判空 —— 若浏览器还缓存着旧 index.html，
// 这里会拿到 null，直接 .addEventListener 会让整个 app.js 顶层抛错（白屏）。
const exportExamResultsButton = document.getElementById("exportExamResultsButton");
if (exportExamResultsButton) {
  exportExamResultsButton.addEventListener("click", exportExamResultsCsv);
}
// 同 teacherApprovalRefreshButton：新按钮必须判空 —— 若浏览器还缓存着旧 index.html，
// 这里会拿到 null，直接 .addEventListener 会让整个 app.js 顶层抛错（白屏）。
const refreshTeacherExamListButton = document.getElementById("refreshTeacherExamListButton");
if (refreshTeacherExamListButton) {
  refreshTeacherExamListButton.addEventListener("click", loadTeacherExamList);
}
// 知识点选择器（教师端组卷）：搜索 / 只看有题 / 清空 / 载入示例 / 题量变化时重算预检
const examNodeSearchInput = document.getElementById("teacherExamNodeSearch");
if (examNodeSearchInput) {
  examNodeSearchInput.addEventListener("input", () => {
    examNodeState.query = examNodeSearchInput.value;
    renderExamNodePicker();
  });
}
const examNodeOnlyCheckbox = document.getElementById("teacherExamNodeOnlyWithQuestions");
if (examNodeOnlyCheckbox) {
  examNodeOnlyCheckbox.checked = examNodeState.onlyWithQuestions;
  examNodeOnlyCheckbox.addEventListener("change", () => {
    examNodeState.onlyWithQuestions = examNodeOnlyCheckbox.checked;
    renderExamNodePicker();
  });
}
const examNodeClearButton = document.getElementById("teacherExamNodeClear");
if (examNodeClearButton) {
  examNodeClearButton.addEventListener("click", () => {
    examNodeState.selected.clear();
    renderExamNodePicker();
  });
}
const examNodeExampleButton = document.getElementById("teacherExamNodeExample");
if (examNodeExampleButton) {
  examNodeExampleButton.addEventListener("click", loadExamNodeExample);
}
const examCountInput = document.getElementById("teacherExamCount");
if (examCountInput) {
  // 题目数量一变，可用题量是否够也要跟着变
  examCountInput.addEventListener("input", () => {
    if (examNodeState.selected.size) renderExamNodeSelection();
  });
}
// 「清空」必须判空：浏览器若还缓存着旧 index.html，这里会拿到 null，
// 直接 .addEventListener 会让整个 app.js 顶层抛错（白屏）。同 refreshTeacherExamListButton。
const examTypeClearButton = document.getElementById("teacherExamTypeClear");
if (examTypeClearButton) {
  examTypeClearButton.addEventListener("click", () => {
    document.querySelectorAll('input[name="teacherExamType"]').forEach((input) => {
      input.checked = false;
    });
    if (examNodeState.selected.size) renderExamNodeSelection();
  });
}
// 题型一变，「限定之后可用的只会更少」这句提示要跟着出现/消失。
// 旧 index.html 里没有这些复选框 —— querySelectorAll 返回空 NodeList，这里是空操作。
document.querySelectorAll('input[name="teacherExamType"]').forEach((input) => {
  input.addEventListener("change", () => {
    if (examNodeState.selected.size) renderExamNodeSelection();
  });
});
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

// ⚠️ 演示账号口令写在静态文件里 = 等于公开。这三个账号只用于评委演示：
//    都是普通 student / teacher（**没有任何管理员权限**），也不要往里放真实教学数据。
//    数据库那一侧由《演示账号初始化.py》按本表写入，两边必须一致。
const DEMO_ACCOUNTS = {
  1: { username: "demo1", password: "ZhishuDemo-2026" },
  2: { username: "demo2", password: "ZhishuDemo-2026" },
  1003: { username: "demo1003", password: "ZhishuDemo-2026" },
};

async function loginDemoAccount(demoUserId) {
  const account = DEMO_ACCOUNTS[demoUserId];
  if (!account) throw new Error("这个 ID 没有配置演示账号（可用 1 / 2 / 1003）");
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: account.username, password: account.password }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(readApiError(data, `登录被拒绝（HTTP ${response.status}）`));
  // token 只放内存、**不写 localStorage**：?demo= 的双窗口演示（一个教师窗口、一个学生窗口）
  // 靠的就是每个窗口各自持有一份登录态；写进 localStorage 会互相覆盖，两个窗口会变成同一个人。
  authState.token = data.token;
  authState.user = data.user;
  return data.user;
}

bootstrapApp();

async function bootstrapApp() {
  // 演示/截图模式：?demo=<用户ID> 以演示账户**真实登录**进应用（评委演示也方便）。
  // 后端要求教师接口认 token 之后，原来只伪造 authState.user、不带 token 的写法
  // 会让演示的班级/考试页整片 401 —— 改成走 POST /api/auth/login 拿真 token。
  // 角色不再由 ?demoRole= 决定，一律以数据库里该账号的 role 为准（demoRole 后门已关）。
  const demoParams = new URLSearchParams(location.search);
  const demoParam = demoParams.get("demo");
  if (demoParam !== null) {
    const demoUserId = Number(demoParam) || DEFAULT_USER_ID;
    try {
      await loginDemoAccount(demoUserId);
    } catch (error) {
      showAuthGate(`演示账户 ${demoUserId} 登录失败：${error.message}`);
      return;
    }
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
  // 取元素后判空：万一只换了 app.js 没同步换 index.html（部署失误），
  // 只是提示条不出现，不会因为 getElementById 返回 null 而整页脚本抛错白屏
  // （与 4325 行 setTextById 那段注释同一个约定）。
  const accountNotice = document.getElementById("accountNotice");
  if (accountNotice) {
    if (user.role === "teacher" && user.teacher_status === "pending") {
      accountNotice.textContent = "教师账号正在等待管理员审批，通过后即可使用教师功能。";
      accountNotice.hidden = false;
    } else if (user.role === "teacher" && user.teacher_status === "rejected") {
      accountNotice.textContent = "教师账号申请未通过审批，暂时无法使用教师功能。";
      accountNotice.hidden = false;
    } else {
      accountNotice.textContent = "";
      accountNotice.hidden = true;
    }
  }
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

  // 角色准入：classState.role 在登录态就绪前为 null（模块加载期那次 switchTab），
  // 此时不拦截；applyAuthenticatedUser() 设好角色后会再调一次，那时才真正生效。
  // 教师审批页仅超级管理员可见。直链、popstate 与页面内按钮都能走到这里，
  // 所以准入判断必须写在 switchTab 里，光靠导航项 hidden 不够。
  // authState.user 判空是必需的：登录态恢复前的那次 switchTab 读不到 role，
  // 不判空就会把深链 rewrite 成首页（详见 patch_frontend.py 第 11 条注释）。
  if (tabName === "teacherApproval" && authState.user && authState.user.role !== "admin") {
    window.history.replaceState({ tab: "dashboard" }, "", tabRoutes.dashboard);
    tabName = "dashboard";
    updateHistory = false;
  }

  const blockedTabs = classState.role ? ROLE_BLOCKED_TABS[classState.role] : null;
  if (blockedTabs && blockedTabs.has(tabName)) {
    // 必须 replaceState：否则地址栏停在 /practice 而页面是首页，一刷新又走一遍重定向
    window.history.replaceState({ tab: "dashboard" }, "", tabRoutes.dashboard);
    tabName = "dashboard";
    updateHistory = false;
  }

  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));

  const navItem = document.querySelector(`[data-tab="${tabName}"]`);
  if (navItem) navItem.classList.add("active");
  const panel = document.getElementById(tabName);
  if (panel) panel.classList.add("active");
  const pageTitle = document.getElementById("pageTitle");
  if (pageTitle) {
    pageTitle.textContent = classState.role === "teacher" && TEACHER_TITLES[tabName]
      ? TEACHER_TITLES[tabName]
      : titles[tabName];
  }
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
    setTimeout(() => teacherState.chart?.resize(), 0);   // 教师端雷达图：切回首页时重算尺寸
  }
  if (tabName === "learning") {
    loadLearningReport();
    loadAiSummary();
    setTimeout(() => learningState.chart?.resize(), 0);
  }
  if (tabName === "companion") loadCompanionWorkspace();
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
  if (tabName === "teacherApproval") loadPendingTeachers();
  if (tabName === "exam") loadExamWorkspace();
  if (tabName === "lessonPrep") loadLessonPrepWorkspace();
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

  const loading = addMessage("正在生成回答...", "assistant");
  try {
    const data = await requestPreferredAssistant({
      message: question,
      user_id: getCurrentUserId(),
      session_id: chatState.sessionId,
      node_id: learningState.currentNodeId,
    }, loading);
    chatState.sessionId = data.session_id || chatState.sessionId;

    updateMessage(loading, data.answer, data.assistantChannel);
  } catch (error) {
    updateMessage(loading, `${error.message}。当前后端：${API_BASE_URL}；请检查后端状态和模型网络连接。`);
  }
}

async function requestPreferredAssistant(payload, message = null) {
  // /chat is the only supported entry point. The backend calls Xingchen Agent
  // first and returns the actual provider/fallback_reason for the UI.
  const data = await requestBasicAssistant(payload);
  if (message) {
    const writer = createTypewriter(message);
    writer.enqueue(data.answer);
    await writer.drain();
  }
  const channel = window.Team4Utils.resolveAssistantChannel(data);
  updateAssistantChannelUI(channel);
  return { ...data, assistantChannel: channel };
}

async function requestBasicAssistant(payload) {
  // /chat 已要求登录（后端 ensure_self）：未登录时给出明确提示，而不是把 401 原文弹给用户。
  if (!authState.token) throw new Error("请先登录后再使用智能问答");
  const response = await postJson("/chat", payload);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(readApiError(data, "基础模型暂时无法响应"));
  const answer = window.Team4Utils.normalizeAgentAnswer(data);
  if (!answer) throw new Error("基础模型没有返回有效回答");
  chatState.sessionId = data.session_id || chatState.sessionId;
  return { ...data, answer };
}

function updateAssistantChannelUI(channel) {
  agentState.channel = channel.kind;
  agentState.fallbackReason = channel.detail;
  document.querySelectorAll("[data-assistant-channel-wrap]").forEach((element) => {
    element.className = `assistant-channel ${channel.kind}`;
  });
  document.querySelectorAll("[data-assistant-channel]").forEach((element) => {
    element.textContent = channel.label;
  });
  document.querySelectorAll("[data-assistant-channel-detail]").forEach((element) => {
    element.textContent = channel.detail;
  });
}

async function requestStreamingChat(payload, message) {
  // 演示/截图模式：?nostream=1 走非流式（一次拿完整回答再打字机输出），规避流式偶发挂起
  if (new URLSearchParams(location.search).get("nostream") === "1") {
    let resp = await authenticatedFetch("/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || "问答请求失败");
    if (data.session_id) chatState.sessionId = data.session_id;
    const fallbackWriter = createTypewriter(message);
    fallbackWriter.enqueue(data.answer || "");
    await fallbackWriter.drain();
    fallbackWriter.finalize(data.answer || "");
    return data;
  }
  let response = await authenticatedFetch("/chat/stream", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (response.status === 404) {
    response = await authenticatedFetch("/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "问答请求失败");
    const fallbackWriter = createTypewriter(message);
    fallbackWriter.enqueue(data.answer || "");
    await fallbackWriter.drain();
    fallbackWriter.finalize(data.answer || "");
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
    } else if (event.type === "replace") {
      streamedAnswer = event.content || "";
      writer.replace(streamedAnswer);
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
  writer.finalize(result.answer);
  return result;
}

function createTypewriter(message) {
  return window.ChatStreamUtils.createTypewriter({
    render: (text) => updateStreamingMessage(message, text),
  });
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
  const hint = field.hint ? `<small class="tool-field-hint">${escapeHtml(field.hint)}</small>` : "";
  if (field.type === "select") {
    return `<label ${wrapper}>${escapeHtml(field.label)}<select name="${escapeHtml(field.name)}">${field.options.map(([optionValue, label]) => `<option value="${escapeHtml(optionValue)}" ${optionValue === field.value ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label>`;
  }
  if (field.type === "checkbox") {
    return `<label class="tool-checkbox" ${wrapper}><input type="checkbox" name="${escapeHtml(field.name)}" ${field.value ? "checked" : ""}><span>${escapeHtml(field.label)}</span></label>`;
  }
  if (field.type === "json" || field.type === "textarea") {
    return `<label ${wrapper}>${escapeHtml(field.label)}<textarea name="${escapeHtml(field.name)}" rows="${Number(field.rows || 3)}">${value}</textarea>${hint}</label>`;
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
        if (raw) {
          const isSubsetElements = toolName === "hasse-diagram"
            && field.name === "elements"
            && form.querySelector('[name="relation_type"]')?.value === "subset";
          params[field.name] = isSubsetElements
            ? parseHasseSubsetElements(raw, field.label)
            : parseToolJson(raw, field.label);
        }
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

function parseHasseSubsetElements(value, label) {
  const normalized = value.replace(/[，]/g, ",").replace(/[：]/g, ":");
  let parsed;
  try {
    parsed = JSON.parse(normalized);
  } catch (error) {
    parsed = parseRelaxedArraySyntax(normalized, label);
  }
  if (!Array.isArray(parsed)) {
    throw new Error(`${label} 必须使用方括号表示`);
  }
  if (!parsed.length) return [[]];
  return parsed.map((subset, index) => {
    if (!Array.isArray(subset)) {
      if (isEmptySetToken(subset)) return [];
      return [subset];
    }
    if (subset.length === 1 && isEmptySetToken(subset[0])) return [];
    if (subset.some(isEmptySetToken)) {
      throw new Error(`第 ${index + 1} 个子集中，空集符号不能与其他元素同时出现`);
    }
    return subset;
  });
}

function parseRelaxedArraySyntax(value, label) {
  let cursor = 0;
  const skipWhitespace = () => {
    while (/\s/.test(value[cursor] || "")) cursor += 1;
  };
  const fail = () => {
    throw new Error(`${label} 格式不正确，请检查方括号和逗号`);
  };
  const parseQuotedString = () => {
    const start = cursor;
    cursor += 1;
    let escaped = false;
    while (cursor < value.length) {
      const character = value[cursor];
      cursor += 1;
      if (character === '"' && !escaped) {
        try {
          return JSON.parse(value.slice(start, cursor));
        } catch (error) {
          fail();
        }
      }
      escaped = character === "\\" && !escaped;
      if (character !== "\\") escaped = false;
    }
    fail();
  };
  const parseValue = () => {
    skipWhitespace();
    if (value[cursor] === "[") return parseArray();
    if (value[cursor] === '"') return parseQuotedString();
    const start = cursor;
    while (cursor < value.length && ![",", "]"].includes(value[cursor])) cursor += 1;
    const token = value.slice(start, cursor).trim();
    if (!token) fail();
    if (/^-?\d+(?:\.\d+)?$/.test(token)) return Number(token);
    if (token === "true") return true;
    if (token === "false") return false;
    if (token === "null") return null;
    return token;
  };
  const parseArray = () => {
    if (value[cursor] !== "[") fail();
    cursor += 1;
    const items = [];
    skipWhitespace();
    if (value[cursor] === "]") {
      cursor += 1;
      return items;
    }
    while (cursor < value.length) {
      items.push(parseValue());
      skipWhitespace();
      if (value[cursor] === "]") {
        cursor += 1;
        return items;
      }
      if (value[cursor] !== ",") fail();
      cursor += 1;
      skipWhitespace();
    }
    fail();
  };
  skipWhitespace();
  const result = parseArray();
  skipWhitespace();
  if (cursor !== value.length) fail();
  return result;
}

function isEmptySetToken(value) {
  return typeof value === "string" && ["Ø", "∅"].includes(value.trim());
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
    <p class="hasse-chart-hint">节点按层级静态排布；元素较多时可横向滚动，或使用滚轮缩放、拖动画布查看。</p>
    <div class="hasse-chart-viewport"><div id="hasseResultChart" class="hasse-result-chart" role="img" aria-label="哈斯图计算结果"></div></div>
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
  const orderedLevels = [...grouped.keys()].sort((left, right) => left - right);
  const maxNodesInLevel = Math.max(1, ...[...grouped.values()].map((items) => items.length));
  const horizontalGap = nodes.length > 48 ? 145 : nodes.length > 24 ? 165 : 190;
  const verticalGap = nodes.length > 48 ? 95 : 115;
  const chartWidth = Math.max(760, maxNodesInLevel * horizontalGap + 180);
  const chartHeight = Math.max(420, orderedLevels.length * verticalGap + 150);
  container.style.width = `${chartWidth}px`;
  container.style.height = `${chartHeight}px`;
  const chartNodes = [];
  orderedLevels.forEach((level) => {
    const levelNodes = grouped.get(level).slice().sort((left, right) => {
      const leftLabel = formatHasseNodeLabel(left);
      const rightLabel = formatHasseNodeLabel(right);
      return leftLabel.localeCompare(rightLabel, "zh-CN", { numeric: true });
    });
    levelNodes.forEach((node, index) => {
      const label = formatHasseNodeLabel(node);
      const labelLength = Array.from(label).length;
      const nodeWidth = Math.max(54, Math.min(horizontalGap - 22, 30 + labelLength * 13));
      chartNodes.push({
        id: String(node.id),
        name: label,
        x: chartWidth / 2 + (index - (levelNodes.length - 1) / 2) * horizontalGap,
        y: 75 + (maxLevel - level) * verticalGap,
        symbol: "roundRect",
        symbolSize: [nodeWidth, nodes.length > 48 ? 40 : 46],
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
      label: { show: true, fontSize: nodes.length > 48 ? 11 : nodes.length > 24 ? 12 : 14, fontWeight: 700, overflow: "truncate" },
      emphasis: { focus: "adjacency", lineStyle: { width: 4 } },
    }],
  });
}

function formatHasseNodeLabel(node) {
  if (Array.isArray(node?.value)) {
    return node.value.length ? `{${node.value.map((item) => String(item)).join(", ")}}` : "∅";
  }
  return String(node?.label ?? node?.value ?? node?.id ?? "");
}

function bindGeneratedCodeCopy(code) {
  const button = document.getElementById("copyGeneratedCodeButton");
  if (!button) return;
  const done = () => {
    button.textContent = "已复制";
    setTimeout(() => { button.textContent = "复制代码"; }, 1600);
  };
  button.addEventListener("click", () => {
    // 同一根因：线上是纯 HTTP（非安全上下文），navigator.clipboard 是 undefined，
    // 原来 await navigator.clipboard.writeText 每次必抛，按钮永远停在「复制失败」。
    if (copyPlainTextViaSelection(code)) { done(); return; }
    // 只有安全上下文才碰 clipboard API（HTTP 下访问该属性本身就会抛 TypeError）。
    // 线上一律走不到这里，是「以后上了 HTTPS 自动变好」的保险。
    if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(code).then(done, () => { button.textContent = "复制失败"; });
      return;
    }
    button.textContent = "复制失败";
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
  return mode === "qwen" ? "星火 Qwen3-32B 按题生成" : "离线模板回退";
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

function updateMessage(message, text, channel = null) {
  message.innerHTML = "";

  if (channel) {
    const meta = document.createElement("div");
    meta.className = `message-channel ${channel.kind}`;
    meta.innerHTML = `<span></span><strong>${escapeHtml(channel.label)}</strong>`;
    meta.title = channel.detail;
    message.appendChild(meta);
  }

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
  let timeoutId;

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
    timeoutId = setTimeout(() => controller.abort(), 15000);
    const response = await fetch(`${KB_API_BASE_URL}/kb/knowledge-graph`, {
      signal: controller.signal,
    });
    const data = await response.json();
    if (timeoutId) clearTimeout(timeoutId);
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
  // 融合导航视图：教材章节/知识点与平台学情融合浏览（队员4）
  if (graphState.view === "fusion") {
    renderFusionGraph();
    return;
  }

  const container = document.getElementById("knowledgeGraphChart");
  if (container.dataset.renderer) {
    container.innerHTML = "";
    delete container.dataset.renderer;
    if (graphState.chart) {
      graphState.chart.dispose();
      graphState.chart = null;
    }
  }
  if (graphState.chart?.isDisposed?.()) graphState.chart = null;
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

// ============ 图谱浏览历史（上一步/下一步 · 节点聚焦） ============
function pickNodeForHistory(node) {
  if (!node) return null;
  // 只保留展示所需字段（避免整棵 children 树进入历史）
  return {
    id: node.id,
    nodeId: node.nodeId,
    name: node.name,
    type: node.type,
    level: node.level,
    text: node.text,
    description: node.description,
    chapter: node.chapter,
    mappingKind: node.mappingKind,
  };
}

function sameHistoryNode(a, b) {
  if (!a || !b) return false;
  const keyA = a.nodeId || a.id || "";
  const keyB = b.nodeId || b.id || "";
  return keyA === keyB && a.name === b.name;
}

function pushNodeHistory(node, dataIndex) {
  if (!node || node.level === "overview") return;
  const record = pickNodeForHistory(node);
  record.__dataIndex = Number.isFinite(dataIndex) ? dataIndex : NaN;
  node.__dataIndex = record.__dataIndex; // 同步回当前节点，供聚焦使用
  if (sameHistoryNode(graphState.nodeHistory[graphState.historyIndex], record)) {
    // 重复点击当前节点：只刷新焦点，不入栈
    graphState.nodeHistory[graphState.historyIndex].__dataIndex = record.__dataIndex;
    return;
  }
  graphState.nodeHistory.splice(graphState.historyIndex + 1);
  graphState.nodeHistory.push(record);
  if (graphState.nodeHistory.length > 100) {
    graphState.nodeHistory.shift();
  }
  graphState.historyIndex = graphState.nodeHistory.length - 1;
  updateGraphHistoryButtons();
}

function updateGraphHistoryButtons() {
  const back = document.getElementById("graphHistoryBackButton");
  const forward = document.getElementById("graphHistoryForwardButton");
  if (!back) return;
  back.disabled = graphState.historyIndex <= 0;
  forward.disabled = !graphState.nodeHistory.length || graphState.historyIndex >= graphState.nodeHistory.length - 1;
}

function gotoGraphHistoryStep(step) {
  const next = graphState.historyIndex + step;
  if (next < 0 || next >= graphState.nodeHistory.length) return;
  graphState.historyIndex = next;
  updateGraphHistoryButtons();
  displayNodeInGraph(graphState.nodeHistory[next], { record: false });
}

function displayNodeInGraph(node, options = {}) {
  if (!node) return;
  graphState.selectedNode = node;
  setCurrentLearningNode(node);
  showGraphNodeDetail(node);
  loadGraphNodeKnowledge(node);
  // 推荐题仅在用于平台映射节点时触发（伪节点不触发）
  if (node.nodeId && node.mappingKind !== "module_fallback") {
    loadRecommendedQuestions(node);
  }
  if (options.focus !== false) {
    focusGraphNode(node, node.__dataIndex);
  }
  scrollGraphDetailIntoView();
}

function focusGraphNode(node, dataIndex) {
  const chart = graphState.chart;
  if (!chart || !node) return;
  dataIndex = typeof dataIndex === "number" ? dataIndex : NaN;
  try {
    if (Number.isFinite(dataIndex)) {
      chart.dispatchAction({
        type: "treeUnfoldAndScrollTo",
        seriesIndex: 0,
        dataIndex,
      });
      chart.dispatchAction({ type: "highlight", seriesIndex: 0, dataIndex });
      return;
    }
  } catch (error) {
    // 视图重渲染后 dataIndex 可能失效，退化为高亮 + 滚动详情
  }
  try {
    chart.dispatchAction({ type: "highlight", seriesIndex: 0 });
  } catch (error) {
    // 关系图视图无 highlight：忽略
  }
}

function scrollGraphDetailIntoView() {
  const panel = document.getElementById("graphDetailPanel");
  if (!panel) return;
  const rect = panel.getBoundingClientRect();
  if (rect.top > window.innerHeight * 0.85 || rect.top < -rect.height) {
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  panel.classList.remove("detail-flash");
  void panel.offsetWidth; // 重新触发动画
  panel.classList.add("detail-flash");
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
  // ⑤ 浏览历史：入栈 + 节点聚焦 + 详情面板跟随
  pushNodeHistory(node, params.dataIndex);
  focusGraphNode(node, params.dataIndex);
  scrollGraphDetailIntoView();
  recordLearningEvent(node);
}

function setGraphView(view) {
  if (!['tree', 'force', 'fusion'].includes(view) || graphState.view === view) {
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
    : view === "fusion"
      ? "按章节逐级聚焦教材知识点，并同步显示平台掌握状态；选择知识点后可查看内容与推荐练习。"
      : "关系图采用固定分层布局；填充色表示内容类型，边框色表示掌握状态，橙色虚线表示前置知识流向。";
  document.querySelector(".graph-legend .dependency").hidden = view !== "force";
  renderKnowledgeGraph();
}


async function loadTeacherGraph() {
  // 融合导航数据源：/kb/teacher-graph 教材图谱数据（仅数据接口，不渲染教师四层树视图）
  if (graphState.teacherGraph) return graphState.teacherGraph;
  const response = await fetch(`${KB_API_BASE_URL}/kb/teacher-graph`).catch(() => null);
  if (!response || !response.ok) {
    throw new Error("教材图谱接口暂不可用");
  }
  graphState.teacherGraph = await response.json();
  return graphState.teacherGraph;
}

function handleTeacherGraphClick(data) {
  // 融合导航：教材知识点点击 → 映射到平台节点详情与推荐题（不渲染教师四层树）
  if (!data || data.kpId) {
    const platformNodeId = data.platform || "";
    const kind = data.mappingKind || "";
    const nodeId = platformNodeId || "";
    const name = nodeId ? findNodeName(nodeId) : data.name;

    // 构建description: 优先使用知识点内容,否则显示章节来源
    let description = "";
    if (data.knowledgeContent) {
      description = `${data.knowledgeContent}\n\n来源：${data.chapter || "教材图谱"}`;
    } else {
      description = `（来自教材图谱）${data.name}\n章节：${data.chapter || ""}`;
    }

    const pseudo = {
      id: `teacher-kp-${data.kpId || data.name}`,
      nodeId,
      name,
      type: nodeId ? "item" : "module",
      description: description,
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
  }
}

async function renderFusionGraph() {
  const container = document.getElementById("knowledgeGraphChart");
  let teacher;
  try {
    teacher = await loadTeacherGraph();
  } catch (error) {
    container.innerHTML = `<p class="error-state">${escapeHtml(error.message)}</p>`;
    return;
  }
  if (graphState.chart) {
    graphState.chart.dispose();
    graphState.chart = null;
  }
  container.dataset.renderer = "fusion";
  container.style.height = "auto";
  const chapters = teacher.chapters || [];
  graphState.fusionChapterIndex = Math.min(graphState.fusionChapterIndex, Math.max(0, chapters.length - 1));
  const chapter = chapters[graphState.fusionChapterIndex] || { sections: [] };
  const sections = chapter.sections || [];
  graphState.fusionSectionIndex = Math.min(graphState.fusionSectionIndex, Math.max(0, sections.length - 1));
  const section = sections[graphState.fusionSectionIndex] || { kps: [] };

  const chapterButtons = chapters.map((item, index) => `
    <button type="button" class="fusion-list-button ${index === graphState.fusionChapterIndex ? "active" : ""}" data-fusion-chapter="${index}">
      <span>${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(item.title || item.id)}</strong>
    </button>`).join("");
  const sectionButtons = sections.map((item, index) => `
    <button type="button" class="fusion-list-button ${index === graphState.fusionSectionIndex ? "active" : ""}" data-fusion-section="${index}">
      <strong>${escapeHtml(item.title || item.id)}</strong><span>${(item.kps || []).length} 个知识点</span>
    </button>`).join("");
  const knowledgeButtons = (section.kps || []).map((item) => {
    const platformNode = item.platform_node_id
      ? { nodeId: item.platform_node_id, type: "concept", children: [], items: [] }
      : null;
    const mastery = platformNode ? getNodeMastery(platformNode) : null;
    const status = platformNode ? getMasteryStatus(mastery) : "unlearned";
    const level = Number(mastery?.level ?? mastery?.mastery_level ?? 0);
    const points = (item.points || []).map((point) => point.title).filter(Boolean);
    return `
      <button type="button" class="fusion-kp-card ${status}" data-fusion-kp="${escapeHtml(item.id)}">
        <span class="fusion-status-dot"></span>
        <span class="fusion-kp-copy"><strong>${escapeHtml(item.title || item.id)}</strong><small>${escapeHtml(points.slice(0, 3).join(" · ") || "教材知识点")}</small></span>
        <span class="mastery-badge ${status}">${escapeHtml(getMasteryLabel(status, level))}</span>
      </button>`;
  }).join("");

  container.innerHTML = `
    <div class="fusion-focus-bar">
      <span>当前定位</span><strong>${escapeHtml(chapter.title || "请选择章节")}</strong><span>›</span><strong>${escapeHtml(section.title || "请选择小节")}</strong>
    </div>
    <div class="fusion-browser">
      <section class="fusion-column fusion-chapters"><header><strong>章节</strong><span>${chapters.length}</span></header><div>${chapterButtons}</div></section>
      <section class="fusion-column fusion-sections"><header><strong>小节</strong><span>${sections.length}</span></header><div>${sectionButtons || '<p class="empty-state">本章暂无小节</p>'}</div></section>
      <section class="fusion-column fusion-kps"><header><strong>教材知识点与平台学情</strong><span>${(section.kps || []).length}</span></header><div>${knowledgeButtons || '<p class="empty-state">本节暂无知识点</p>'}</div></section>
    </div>`;

  container.querySelectorAll("[data-fusion-chapter]").forEach((button) => {
    button.addEventListener("click", () => {
      const chapterIndex = Number(button.dataset.fusionChapter);
      graphState.fusionChapterIndex = chapterIndex;
      graphState.fusionSectionIndex = 0;
      renderFusionGraph();

      // 跳转到该章第一节
      const chapter = chapters[chapterIndex];
      if (chapter && chapter.sections && chapter.sections[0]) {
        openTextbookSection(chapter.sections[0].id);
      }
    });
  });
  container.querySelectorAll("[data-fusion-section]").forEach((button) => {
    button.addEventListener("click", () => {
      const sectionIndex = Number(button.dataset.fusionSection);
      graphState.fusionSectionIndex = sectionIndex;
      renderFusionGraph();

      // 跳转到该小节
      const section = sections[sectionIndex];
      if (section && section.id) {
        openTextbookSection(section.id);
      }
    });
  });
  container.querySelectorAll("[data-fusion-kp]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = (section.kps || []).find((kp) => kp.id === button.dataset.fusionKp);
      if (!item) return;
      container.querySelectorAll(".fusion-kp-card").forEach((node) => node.classList.remove("selected"));
      button.classList.add("selected");

      // 格式化知识点的要点列表
      const pointsList = (item.points || []).map(pt => `• ${pt.title}`).join('\n');
      const knowledgeContent = pointsList || item.title || "暂无详细内容";

      handleTeacherGraphClick({
        name: item.title || item.id,
        kpId: item.id,
        platform: item.platform_node_id || "",
        mappingKind: item.mapping_kind || "",
        chapter: `${chapter.title || ""} · ${section.title || ""}`,
        knowledgeContent: knowledgeContent, // 传递知识点内容
      });
      document.querySelector("#graph .graph-detail-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
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

  // 教材融合：显示教材跳转按钮
  // 场景1: 融合导航点击教材知识点 → node.id 包含 "teacher-kp-" 且有真实 kpId
  // 场景2: 平台知识图谱点击 → 通过 node.nodeId 反查教材映射
  const teacherKpMatch = node.id?.match(/^teacher-kp-(.+)$/);
  if (teacherKpMatch) {
    // 融合导航来源：直接从 node.id 提取 kpId
    const kpId = teacherKpMatch[1];
    if (kpId && kpId.match(/^[KCS]\d+$/)) {
      // 有效的教材ID格式（K010101/C01/S0101）
      renderTextbookButton(tasksEl, kpId, node.description || "");
    } else {
      tasksEl.hidden = true;
      tasksEl.innerHTML = "";
    }
  } else if (node.nodeId) {
    // 平台图谱来源：查询映射
    loadTextbookMappingForNode(node.nodeId, tasksEl);
  } else {
    tasksEl.hidden = true;
    tasksEl.innerHTML = "";
  }
}

function renderTextbookButton(container, kpId, description) {
  // 从描述中提取章节信息（融合导航格式："章节：第X章 xxx > X.X xxx"）
  const chapterMatch = description.match(/章节：(.+?)(?:\n|$)/);
  const chapterInfo = chapterMatch ? chapterMatch[1] : "教材详细讲解";

  const buttonHtml = `
    <button class="textbook-link-button" onclick="openTextbookKP('${kpId}')">
      📖 打开教材详细讲解: ${escapeHtml(chapterInfo)}
    </button>
  `;
  container.innerHTML = buttonHtml;
  container.hidden = false;
}

async function loadTextbookMappingForNode(nodeId, container) {
  try {
    const response = await fetch(`${KB_API_BASE_URL}/kb/node-textbook-mapping?node_id=${encodeURIComponent(nodeId)}`);
    const mapping = await response.json();

    if (mapping.found) {
      const buttonHtml = `
        <button class="textbook-link-button" onclick="openTextbookKP('${mapping.kpId}')">
          📖 查看教材: ${escapeHtml(mapping.chapterTitle)}(第${escapeHtml(mapping.section)}节)
        </button>
      `;
      container.innerHTML = buttonHtml;
      container.hidden = false;
    } else {
      container.hidden = true;
      container.innerHTML = "";
    }
  } catch (error) {
    console.warn("查询教材映射失败:", error);
    container.hidden = true;
    container.innerHTML = "";
  }
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
    if (!authState.token) {
      target.innerHTML = '<p class="muted-line">请先登录后查看学情数据。</p>';
      return;
    }
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const response = await authenticatedFetch(`/api/learning/report?user_id=${encodeURIComponent(userId)}`, {
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

  const localEvents = readAllLocalLearningEvents();
  localEvents.push({
    ...payload,
    node_name: node.name,
    search_query: node.searchQuery || node.name,
    timestamp: new Date().toISOString(),
  });
  localStorage.setItem("learning_events", JSON.stringify(localEvents.slice(-100)));

  // 当前学情接口只定义答题掌握度更新，浏览行为先保存在本地活动记录中。
}

// 原始读取：返回全部账号的事件。仅供写入路径使用（读出来 → push → 整体写回），
// 这里绝不能按用户过滤，否则写回时会把其他账号的事件整批抹掉。
function readAllLocalLearningEvents() {
  try {
    const events = JSON.parse(localStorage.getItem("learning_events") || "[]");
    return Array.isArray(events) ? events : [];
  } catch (error) {
    return [];
  }
}

// 展示用读取：learning_events 是浏览器全局键，同一浏览器切换账号会串数据
// （「今日学习 / 本周完成题目 / 近 7 天折线图」三处都读它）。事件写入时已带 user_id，
// 这里按当前用户过滤即可隔离，其余账号的数据仍原样保留在 localStorage 中。
function parseLocalLearningEvents() {
  const userId = Number(getCurrentUserId());
  return readAllLocalLearningEvents().filter(
    (event) => Number(event && event.user_id) === userId
  );
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
        <strong>${escapeHtml(q.kp || findNodeName(q.nodeId))}</strong>
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
    const data = await parseVisionImage(file);
    textarea.value = selectVisionText(data, "student_answer");
    practiceState.calcTexts.set(questionId, textarea.value);
    practiceState.calcStartedAt.set(questionId, Date.now());
    box.hidden = false;
    status.textContent = `识别完成：${describeVisionResult(data) || "已提取文本"}`;
  } catch (error) {
    status.textContent = `识别失败：${error.message}`;
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

// ==================== 拍照识别：发送前压缩 ====================
// 为什么要有这一段（2026-09-16 对线上实测，不是推测）：
//   · nginx 1.27.5 用的是**默认**的 client_max_body_size = 1 MiB；
//   · 对不存在的路径 POST：body 1,048,576 B → 404（请求进了 FastAPI），
//     body 1,048,577 B → 413，并且响应体是 nginx 自己的 HTML（text/html、183 B、
//     Connection: close）—— 请求根本没到 uvicorn；
//   · 拍照走的是 capture="environment" 的相机原图（模拟 12 MP 原图 = 3,448 KB），必然超标；
//   · 后端自己的 10 MiB 上限（backend/vision/router.py:18）因此从没被触发过 ——
//     学生看到的「图片识别失败（413）」是 readApiError 拿不到 detail 时露出来的裸状态码。
// parseVisionImage 是 5 个拍照入口（计算题 :3443 / 教材答疑 :3592 / 证明题 :3619 /
// 考试答题纸 :5994 / 智能批改 :6191）**唯一**的汇聚点，压在这里改一处就全部修好。

// 原图不超过这个字节数就**原样上传**：不动画质、不冒解码失败的风险、不白花手机 CPU。
// 900 KB 距 nginx 的 1,048,576 B 留 12% 余量（multipart 的边界加两个头部实测约 200 B）；
// 600 KB 的请求已实测能进应用（返回 422 而不是 413）。
const VISION_UPLOAD_MAX_BYTES = 900 * 1024;

// 逐级降档 [最长边, JPEG 质量]，从好到差，**一旦达标就停**。
// 第一档为什么是 2000 px：A4 纸竖拍占满画面时一行手写推导约等于照片长边的 1/40，
// 缩到 2000 px 后字高还有 45 px 上下，上下标、分数线、根号都分得开；再往下（<1200 px）
// 分式与根号开始糊，x 和 ×、1 和 l 会认混。2000 px 也基本等于视觉大模型自己的输入上限
// （超出的像素模型自己会丢），再大只是白花上传时间。
// 实测：模拟 12 MP 手机原图（3,448 KB）走第一档出 676 KB，正常情况只用得到第一档，
// 后面三档是保险。
const VISION_SHRINK_STEPS = [[2000, 0.85], [1600, 0.8], [1280, 0.72], [1024, 0.62]];

// 压缩整体限时。解码/编码都在浏览器内部，正常 0.5–2.5 秒，但**没有上限** ——
// 万一卡住学生就永远停在「正在识别…」，考试页还有 15 分钟倒计时，那比报错更难堪。
// 到点就放弃压缩、用原图（原图至少还有一次机会，后端给的话也比这里具体）。
const VISION_COMPRESS_BUDGET_MS = 8000;

function visionJpegName(name) {
  const text = String(name || "photo");
  const dot = text.lastIndexOf(".");
  const base = dot > 0 ? text.slice(0, dot) : text;
  return `${base || "photo"}.jpg`;
}

// 解码成「已经按 EXIF 摆正」的位图。imageOrientation:"from-image" 是**必须**的：
// 手机竖拍时像素其实是横躺着的，方向只写在 EXIF 里；若按像素原样解码，送给模型的就是
// 一张躺倒的卷子，整页读成乱码 —— 这种故障比 413 难查得多，而且不会报任何错。
// 三层回退：老浏览器认不出 "from-image" 这个枚举值时 WebIDL 会直接抛错。
async function decodeVisionImage(file) {
  if (typeof createImageBitmap === "function") {
    for (const options of [{ imageOrientation: "from-image" }, undefined]) {
      try {
        return await createImageBitmap(file, options);
      } catch (error) {
        // 换下一种解码方式（不认这个选项 / 解不开这个格式，例如 iPhone 的 HEIC）
      }
    }
  }
  return await new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error("图片解码失败")); };
    image.src = url;
  });
}

function canvasToJpegBlob(canvas, quality) {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob || null), "image/jpeg", quality);
  });
}

// 把位图缩到「最长边 ≤ maxSide」再编码成 JPEG；失败返回 null（调用方继续降下一档）。
async function shrinkVisionJpeg(source, width, height, maxSide, quality) {
  try {
    const scale = Math.min(1, maxSide / Math.max(width, height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d");
    if (!context) return null;
    // 缩小取样默认是低质量档，打开高质量重采样能让手写细笔画少一些锯齿
    // （Safari 不支持这个属性，赋值会被忽略，不影响后面的回退）
    context.imageSmoothingQuality = "high";
    // JPEG 没有透明通道：不先铺白底，带透明的 PNG 会被合成成**黑底黑字**，
    // 模型一个符号都读不出来。改这一处之前这类图是原样透传的，所以这行是必须的。
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    return await canvasToJpegBlob(canvas, quality);
  } catch (error) {
    return null;
  }
}

// 压出来的 Blob 要包成 File 再进 FormData：后端的白名单（backend/vision/router.py:17）
// 查的是 multipart part 里的 Content-Type，而它来自 File 的 type —— 少了这一步，
// 浏览器会按 application/octet-stream 发，后端直接 415。
function toVisionJpegFile(blob, original) {
  const name = visionJpegName(original.name);
  try {
    return new File([blob], name, { type: "image/jpeg" });
  } catch (error) {
    return blob;   // 老到没有 File 构造器的浏览器：退回 Blob（它的 type 也是 image/jpeg）
  }
}

// 逐档试，返回第一张达标（≤ VISION_UPLOAD_MAX_BYTES）的 JPEG；全不达标返回 null。
async function shrinkVisionImage(file) {
  let source = null;
  try {
    source = await decodeVisionImage(file);
    const width = source.width || source.naturalWidth || 0;
    const height = source.height || source.naturalHeight || 0;
    if (!width || !height) return null;
    for (const [maxSide, quality] of VISION_SHRINK_STEPS) {
      const blob = await shrinkVisionJpeg(source, width, height, maxSide, quality);
      if (blob && blob.size <= VISION_UPLOAD_MAX_BYTES) return toVisionJpegFile(blob, file);
    }
    // 四档都还超标：只可能是高熵噪声图，再往下压字就真糊了。
    // 这时宁可原样上传、让上层如实报错，也别给学生一张认不出的图。
    return null;
  } catch (error) {
    return null;
  } finally {
    // ImageBitmap 里是解码后的原始像素（12 MP 约 48 MB），手机上必须主动放掉
    if (source && typeof source.close === "function") source.close();
  }
}

// 把入参换成「可以安全发出去的那一份」。契约三条，缺一不可：
//   ① **任何一步失败都原样返回入参对象本身** —— 绝不能因为「压缩失败」把学生挡在门外；
//   ② 本来就 ≤ 900 KB 的原图原样透传，不重新编码（不引入无谓的质量损失）；
//   ③ 一定在 VISION_COMPRESS_BUDGET_MS 内返回，绝不永远挂起。
async function prepareVisionUpload(file) {
  if (!file || file.size <= VISION_UPLOAD_MAX_BYTES) return file;
  let timer = 0;
  try {
    const giveUp = new Promise((resolve) => { timer = setTimeout(() => resolve(null), VISION_COMPRESS_BUDGET_MS); });
    return (await Promise.race([shrinkVisionImage(file), giveUp])) || file;
  } catch (error) {
    return file;
  } finally {
    clearTimeout(timer);
  }
}

// 把 HTTP 状态码翻成学生看得懂的话。413 有两个来源 —— nginx（HTML 响应体，没有 detail）
// 和后端（10 MiB 那条，有 detail）—— 两种都给学生同一句可执行的指令：
// 客户端的压缩已经让 > 900 KB 的上传几乎不可能发生，真出现 413 就说明该重拍了。
// 同理 415 也不再暴露后端那句给开发看的「仅支持 PNG、JPEG、WebP 图片」。
// 其余状态码仍然优先用后端给的 detail（那是人话，而且更具体）。
function describeVisionError(response, data) {
  if (response.status === 413) return "图片太大，请离题目近一点重拍";
  if (response.status === 415) return "图片格式不支持，请用相机重拍";
  if (response.status === 401 || response.status === 403) return "登录已过期，请重新登录后再试";
  if (response.status === 502 || response.status === 503 || response.status === 504) {
    return "识别服务暂时不可用，请稍后重试";
  }
  return readApiError(data, `图片识别失败（HTTP ${response.status}）`);
}

async function parseVisionImage(file) {
  // 线上 nginx 的 client_max_body_size 是 1 MiB，相机原图必然超标 —— 先压再发（见上方说明）
  const upload = await prepareVisionUpload(file);
  const form = new FormData();
  form.append("file", upload, upload.name || "image.png");
  const response = await authenticatedFetch("/api/vision/parse", {
    method: "POST",
    body: form,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(describeVisionError(response, data));
  return data;
}

function selectVisionText(data, preferredField) {
  const preferred = String(data?.[preferredField] || "").trim();
  const fallbackField = preferredField === "student_answer" ? "question_text" : "student_answer";
  return preferred || String(data?.[fallbackField] || "").trim();
}

function describeVisionResult(data) {
  const parts = [];
  const confidence = Number(data?.confidence);
  const elapsed = Number(data?.elapsed_ms);
  if (Number.isFinite(confidence)) parts.push(`置信度 ${Math.round(confidence * 100)}%`);
  if (Number.isFinite(elapsed) && elapsed > 0) parts.push(`耗时 ${(elapsed / 1000).toFixed(1)} 秒`);
  if (Array.isArray(data?.warnings) && data.warnings.length) parts.push(`提示：${data.warnings.join("；")}`);
  return parts.join(" · ");
}

async function handleChatPhoto(file) {
  if (!file) return;

  const status = document.getElementById("chatPhotoStatus");
  const input = document.getElementById("questionInput");
  if (!status || !input) return;

  if (!file.type.startsWith("image/")) {
    status.textContent = "请选择图片文件。";
    return;
  }

  status.textContent = "正在识别图片中的文字...";
  try {
    const data = await parseVisionImage(file);
    const text = selectVisionText(data, "question_text");
    if (!text) throw new Error("图片中未识别到可用文字");

    input.value = text;
    input.focus();

    const details = describeVisionResult(data);
    status.textContent = details
      ? `识别完成：${details}`
      : "识别完成，请检查文字后发送";
  } catch (error) {
    status.textContent = `图片识别失败：${error.message}`;
  } finally {
    const picker = document.getElementById("chatPhotoInput");
    if (picker) picker.value = "";
  }
}

async function handleProofPhoto(questionId, file) {
  if (!file) return;
  const status = document.querySelector(`.proof-status[data-proof-status="${CSS.escape(questionId)}"]`);
  const box = document.querySelector(`.proof-ocr-box[data-proof-ocr="${CSS.escape(questionId)}"]`);
  const textarea = document.querySelector(`.proof-ocr-text[data-proof-text="${CSS.escape(questionId)}"]`);
  if (!status || !box || !textarea) return;
  status.textContent = "识别中…";
  try {
    const data = await parseVisionImage(file);
    textarea.value = selectVisionText(data, "student_answer");
    practiceState.proofTexts.set(questionId, textarea.value);
    box.hidden = false;
    status.textContent = `识别完成：${describeVisionResult(data) || "已提取文本"}`;
  } catch (error) {
    status.textContent = `识别失败：${error.message}`;
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
    const localEvents = readAllLocalLearningEvents();
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
  // 教师端不取"本人学情"——教师没有答题记录，取回来只会是一份全 0 的学生结构报告。
  // 这一处早退收口了所有学生向调用路径（刷新按钮、bootstrap、两个 tab、交卷后、路径刷新）。
  if (classState.role === "teacher") {
    await loadTeacherClassOverview({ silent: options.silent });
    return;
  }
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
    const response = await authenticatedFetch(path);
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
  // 这段 AI 学情洞察是学生向的（取本人问答+答题记录），教师在学情面板看到的是班级视图，
  // 该元素在教师视图下是 hidden 的，没必要为它发一次请求。
  if (classState.role === "teacher") return;
  const userId = getCurrentUserId();
  // 未登录时 getCurrentUserId() 会回落到 DEFAULT_USER_ID（=1），
  // 所以判定登录必须看 token，不能看 userId。
  if (!authState.token || !userId) {
    target.textContent = "请先登录后再生成学情分析。";
    return;
  }

  target.textContent = "正在综合问答与答题数据生成学情分析...";
  try {
    const response = await authenticatedFetch(`/api/learning/ai-summary?user_id=${encodeURIComponent(userId)}`);
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
  // 教师端首页渲染的是班级学情总览，学生仪表盘整套逻辑不参与（见 renderTeacherClassView）
  if (classState.role === "teacher") return;
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

  // 教材融合：薄弱点优先，其次推荐理解中节点对应的教材章节
  const textbookSelection = window.Team4Utils?.selectTextbookRecommendationNodes({
    weak: report?.weak,
    understandingNodes: report?.understanding_nodes,
    nodeInsights: report?.node_insights,
  }) || { source: null, nodes: [] };
  if (textbookSelection.nodes.length > 0) {
    renderDashboardTextbookRecommendations(textbookSelection.nodes, textbookSelection.source);
  } else {
    document.getElementById("dashboardTextbookCard").hidden = true;
  }
}

async function renderDashboardTextbookRecommendations(recommendationNodes, source = "weak") {
  const container = document.getElementById("dashboardTextbookRecommendations");
  const card = document.getElementById("dashboardTextbookCard");

  if (!recommendationNodes || recommendationNodes.length === 0) {
    card.hidden = true;
    return;
  }

  // 查询推荐节点的教材映射（父节点可能命中多个教材知识点）
  const mappingPromises = recommendationNodes.slice(0, 10).map(async (nodeItem) => {
    const nodeId = typeof nodeItem === "string" ? nodeItem : nodeItem.node_id;
    if (!nodeId) return [];

    try {
      const response = await fetch(`${KB_API_BASE_URL}/kb/node-textbook-mapping?node_id=${encodeURIComponent(nodeId)}`);
      const mapping = await response.json();
      if (!mapping.found) return [];

      const nodeName = typeof nodeItem === "string" ? findNodeName(nodeId) : nodeItem.node_name || nodeItem.name || findNodeName(nodeId);
      const candidates = Array.isArray(mapping.candidates) && mapping.candidates.length > 0 ? mapping.candidates : [mapping];
      return candidates
        .filter((candidate) => candidate && candidate.kpId)
        .map((candidate) => ({
          nodeId,
          nodeName,
          kpId: candidate.kpId,
          kpTitle: candidate.kpTitle,
          chapterId: candidate.chapterId,
          chapterTitle: candidate.chapterTitle,
          section: candidate.section,
          sectionTitle: candidate.sectionTitle,
        }));
    } catch (error) {
      console.warn(`查询 ${nodeId} 教材映射失败:`, error);
      return [];
    }
  });

  const mappings = (await Promise.all(mappingPromises)).flat();

  if (mappings.length === 0) {
    card.hidden = true;
    return;
  }

  // 按「章节 → 小节」聚合，同一知识点只统计一次
  const chapterMap = new Map();
  mappings.forEach((mapping) => {
    if (!chapterMap.has(mapping.chapterId)) {
      chapterMap.set(mapping.chapterId, {
        chapterId: mapping.chapterId,
        chapterTitle: mapping.chapterTitle,
        nodeIds: new Set(),
        sections: new Map(),
      });
    }
    const chapter = chapterMap.get(mapping.chapterId);
    chapter.nodeIds.add(mapping.nodeId);
    const sectionKey = `${mapping.sectionId || ""}-${mapping.section || ""}`;
    if (!chapter.sections.has(sectionKey)) {
      chapter.sections.set(sectionKey, {
        section: mapping.section,
        sectionTitle: mapping.sectionTitle,
        kpId: mapping.kpId,
        nodes: new Set(),
      });
    }
    chapter.sections.get(sectionKey).nodes.add(mapping.nodeId);
  });

  const topChapters = Array.from(chapterMap.values())
    .sort((a, b) => b.nodeIds.size - a.nodeIds.size)
    .slice(0, 3);

  const recommendationsHtml = topChapters.map((chapter) => {
    const sections = Array.from(chapter.sections.values()).slice(0, 3);
    const sectionButtons = sections.map((section) => `
      <button class="textbook-section-button" onclick="openTextbookKP('${section.kpId}')">
        <span>第${escapeHtml(section.section)}节 · ${escapeHtml(section.sectionTitle)}</span>
        <em>${window.Team4Utils?.textbookRecommendationBadge(section.nodes.size, source) || `${section.nodes.size} 个待巩固点`}</em>
      </button>
    `).join("");

    return `
    <div class="textbook-recommendation-item">
      <div class="textbook-rec-header">
        <strong>${escapeHtml(chapter.chapterTitle)}</strong>
        <span class="textbook-rec-badge">${window.Team4Utils?.textbookRecommendationBadge(chapter.nodeIds.size, source) || `${chapter.nodeIds.size} 个待巩固点`}</span>
      </div>
      ${sectionButtons}
    </div>
  `;
  }).join("");

  container.innerHTML = recommendationsHtml;
  card.hidden = false;
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

function getLearningSnapshot() {
  const events = parseLocalLearningEvents();
  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - 6);
  weekStart.setHours(0, 0, 0, 0);
  const recent = events.filter((event) => new Date(event.timestamp || 0) >= weekStart);
  const todayKey = formatDateKey(now);
  const today = recent.filter((event) => formatDateKey(new Date(event.timestamp)) === todayKey);
  return {
    todayMinutes: Math.min(120, new Set(today.map((event) => String(event.timestamp).slice(0, 13))).size * 8),
    weeklyQuestions: recent.filter((event) => event.event_type === "answer").length,
    weakNodes: (learningState.report?.weak || []).map((item) => shortenNodeName(item.name || item.node_name || findNodeName(item.node_id))),
    currentNode: learningState.currentNodeName,
  };
}

function loadCompanionWorkspace() {
  const snapshot = getLearningSnapshot();
  document.getElementById("companionTodayMinutes").textContent = `${snapshot.todayMinutes} 分钟`;
  document.getElementById("companionWeeklyQuestions").textContent = `${snapshot.weeklyQuestions} 题`;
  document.getElementById("companionWeakCount").textContent = `${snapshot.weakNodes.length} 项`;
  document.getElementById("companionCurrentNode").textContent = snapshot.currentNode || "尚未选择知识点";
  const weakTarget = document.getElementById("companionWeakNodes");
  weakTarget.innerHTML = snapshot.weakNodes.length
    ? snapshot.weakNodes.slice(0, 6).map((name) => `<span>${escapeHtml(name)}</span>`).join("")
    : '<p class="muted-line">当前没有待巩固知识点。</p>';
}

function setCompanionKind(kind) {
  companionState.kind = ["today", "mistakes", "duration"].includes(kind) ? kind : "today";
  document.querySelectorAll(".companion-kind").forEach((button) => {
    button.classList.toggle("active", button.dataset.companionKind === companionState.kind);
  });
}

async function requestAssistantText(prompt) {
  const data = await requestPreferredAssistant({
    message: prompt,
    user_id: getCurrentUserId(),
    session_id: chatState.sessionId,
    node_id: learningState.currentNodeId,
  });
  chatState.sessionId = data.session_id || chatState.sessionId;
  return data.answer;
}

async function generateCompanionAdvice() {
  if (companionState.loading) return;
  const target = document.getElementById("companionAdvice");
  const button = document.getElementById("generateCompanionButton");
  companionState.loading = true;
  button.disabled = true;
  button.textContent = "正在生成";
  target.className = "assistant-document loading-state";
  target.textContent = "正在结合学情和练习记录安排本次学习...";
  try {
    const prompt = window.Team4Utils.buildCompanionPrompt(companionState.kind, getLearningSnapshot());
    const answer = await requestAssistantText(prompt);
    target.className = "assistant-document";
    target.innerHTML = formatAnswerHtml(answer);
    typesetMath(target);
  } catch (error) {
    target.className = "assistant-document error-state";
    target.textContent = `学习建议生成失败：${error.message}`;
  } finally {
    companionState.loading = false;
    button.disabled = false;
    button.textContent = "重新生成";
  }
}

async function loadLessonPrepWorkspace() {
  const chapterSelect = document.getElementById("prepChapterSelect");
  if (chapterSelect.options.length) return;
  chapterSelect.innerHTML = '<option value="">正在读取教材章节...</option>';
  try {
    const teacher = await loadTeacherGraph();
    chapterSelect.innerHTML = (teacher.chapters || []).map((chapter, index) =>
      `<option value="${index}">${escapeHtml(chapter.title || chapter.id)}</option>`).join("");
    syncPrepSections();
  } catch (error) {
    chapterSelect.innerHTML = `<option value="">${escapeHtml(error.message)}</option>`;
  }
}

function getSelectedPrepContext() {
  const chapters = graphState.teacherGraph?.chapters || [];
  const chapter = chapters[Number(document.getElementById("prepChapterSelect").value)] || null;
  const section = chapter?.sections?.[Number(document.getElementById("prepSectionSelect").value)] || null;
  return { chapter, section };
}

function syncPrepSections() {
  const sectionSelect = document.getElementById("prepSectionSelect");
  const chapters = graphState.teacherGraph?.chapters || [];
  const chapter = chapters[Number(document.getElementById("prepChapterSelect").value)];
  sectionSelect.innerHTML = (chapter?.sections || []).map((section, index) =>
    `<option value="${index}">${escapeHtml(section.title || section.id)}</option>`).join("");
  updatePrepDocumentMeta();
}

function updatePrepDocumentMeta() {
  const { chapter, section } = getSelectedPrepContext();
  document.getElementById("prepDocumentMeta").textContent = chapter && section
    ? `${chapter.title} · ${section.title} · ${(section.kps || []).length} 个知识点`
    : "选择章节和小节后生成。";
}

async function generateLessonPrep() {
  if (lessonPrepState.loading) return;
  const { chapter, section } = getSelectedPrepContext();
  if (!chapter || !section) return;
  const target = document.getElementById("lessonPrepResult");
  const button = document.getElementById("generateLessonPrepButton");
  const outputType = document.getElementById("prepOutputSelect").value;
  lessonPrepState.loading = true;
  button.disabled = true;
  button.textContent = "正在生成";
  target.className = "assistant-document prep-document loading-state";
  target.textContent = "正在整理教材知识点和课堂节奏...";
  const prompt = window.Team4Utils.buildLessonPrompt({
    chapter: chapter.title,
    section: section.title,
    audience: document.getElementById("prepAudienceSelect").value,
    duration: document.getElementById("prepDurationInput").value,
    outputType,
    points: (section.kps || []).map((item) => item.title),
  });
  try {
    lessonPrepState.resultText = await requestAssistantText(prompt);
    document.getElementById("prepDocumentTitle").textContent = `${section.title} · ${outputType}`;
    target.className = "assistant-document prep-document";
    target.innerHTML = formatAnswerHtml(lessonPrepState.resultText);
    document.getElementById("copyLessonPrepButton").disabled = false;
    typesetMath(target);
  } catch (error) {
    target.className = "assistant-document prep-document error-state";
    target.textContent = `备课内容生成失败：${error.message}`;
  } finally {
    lessonPrepState.loading = false;
    button.disabled = false;
    button.textContent = "生成备课内容";
  }
}

// ==================== 复制到剪贴板（HTTP 下的正确写法） ====================
// 线上是纯 HTTP → 非安全上下文 → navigator.clipboard 是 undefined。
// 原来 `await navigator.clipboard.writeText(...)` 每次都抛未捕获异常，按钮永远停在
// 「复制内容」；而且复制的是**原始 markdown**，粘进 Word/WPS 得到的是 \(x\) 源码。
// 唯一能把 text/html 写进剪贴板的办法是「离屏选区 + document.execCommand('copy')」，
// 且该调用必须在**用户手势的同一次任务**里同步完成 —— 所以这条链路一行 await 都不能有。

const LESSON_PREP_COPY_LABEL = { idle: "复制内容", done: "已复制", fail: "复制失败" };
let lessonPrepCopyTimer = null;

// Word / WPS 认得 <math xmlns=...>MathML</math>，不认得 MathJax 的 <mjx-container>。
// 渲染后的 DOM 里每个 <mjx-container> 内都有一个带 xmlns 的 assistive <math>
// （MathJax 3.2.2 tex-chtml 默认 enableAssistiveMml），换出来公式就能带格式粘进 Word/WPS。
function buildLessonPrepClipboardHtml(renderedHtml) {
  if (!renderedHtml) return "";
  if (!/mjx-container|mjx-assistive-mml|<math[\s>]/i.test(renderedHtml)) return renderedHtml;
  const host = document.createElement("template");   // template 不触发其中的资源加载
  host.innerHTML = renderedHtml;
  host.content.querySelectorAll("mjx-container").forEach((node) => {
    const math = node.querySelector("math");
    // 找不到 <math> 就原样留着：宁可留一点 MathJax 残留，也不能把公式删掉。
    if (math) node.replaceWith(math);
  });
  return host.innerHTML;   // 只回片段，不包 <html>/<body> —— Word 粘 HTML 片段更干净
}

// 离屏选区 + execCommand，返回是否成功。
// ⚠️ 不能用 display:none / visibility:hidden / opacity:0 —— Chrome 会因此复制出空内容，
//    必须真的在布局里（挪到 -9999px 之外即可）。
function copyHtmlViaSelection(html) {
  if (!html) return false;
  const stage = document.createElement("div");
  stage.style.cssText = "position:fixed;left:-9999px;top:0;width:1px;height:1px;overflow:hidden;";
  stage.setAttribute("aria-hidden", "true");
  stage.innerHTML = html;
  document.body.appendChild(stage);
  const selection = window.getSelection();
  let ok = false;
  try {
    const range = document.createRange();
    range.selectNodeContents(stage);
    selection.removeAllRanges();
    selection.addRange(range);
    ok = document.execCommand("copy");
  } catch (error) {
    ok = false;
  }
  if (selection) selection.removeAllRanges();
  stage.remove();
  return ok;
}

// 纯文本兜底：HTML 那条路失败时，至少把原始文本复制走。
function copyPlainTextViaSelection(text) {
  if (!text) return false;
  const stage = document.createElement("textarea");
  stage.value = text;
  stage.setAttribute("readonly", "readonly");
  stage.setAttribute("aria-hidden", "true");
  stage.style.cssText = "position:fixed;left:-9999px;top:0;width:1px;height:1px;overflow:hidden;";
  document.body.appendChild(stage);
  let ok = false;
  try {
    stage.select();
    stage.setSelectionRange(0, stage.value.length);
    ok = document.execCommand("copy");
  } catch (error) {
    ok = false;
  }
  stage.remove();
  return ok;
}

// 定时器挂在模块级：连点两下时，后一次不能把前一次的文案提前收回去。
function setLessonPrepCopyLabel(button, state) {
  if (!button) return;
  if (lessonPrepCopyTimer) clearTimeout(lessonPrepCopyTimer);
  button.textContent = LESSON_PREP_COPY_LABEL[state] || LESSON_PREP_COPY_LABEL.idle;
  lessonPrepCopyTimer = setTimeout(() => {
    lessonPrepCopyTimer = null;
    button.textContent = LESSON_PREP_COPY_LABEL.idle;
  }, 1600);
}

function copyLessonPrep() {   // 注意：**不是** async，整条链路必须同步走完
  const button = document.getElementById("copyLessonPrepButton");
  const target = document.getElementById("lessonPrepResult");
  const renderedHtml = target ? target.innerHTML : "";
  if (!lessonPrepState.resultText && !renderedHtml) return;
  // 优先复制「渲染后的 HTML」——公式是 MathML、标题是 <h4>，粘进 Word/WPS 就是排版好的样子。
  let ok = false;
  if (renderedHtml) ok = copyHtmlViaSelection(buildLessonPrepClipboardHtml(renderedHtml));
  if (!ok && lessonPrepState.resultText) ok = copyPlainTextViaSelection(lessonPrepState.resultText);
  if (ok) { setLessonPrepCopyLabel(button, "done"); return; }
  // 只有安全上下文才碰 clipboard API（HTTP 下该属性是 undefined，直接访问就抛 TypeError）。
  if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText && lessonPrepState.resultText) {
    navigator.clipboard.writeText(lessonPrepState.resultText).then(
      () => setLessonPrepCopyLabel(button, "done"),
      () => setLessonPrepCopyLabel(button, "fail"),
    );
    return;
  }
  setLessonPrepCopyLabel(button, "fail");
}

// 统一用 null-safe 的取元素工具：万一只换了 app.js 没同步换 index.html（部署失误），
// 也只是新功能不出现，不会因整页脚本抛错而白屏。
function setTextById(id, text) {
  const element = document.getElementById(id);
  if (element) element.textContent = text;
}

function showRoleView(id, visible) {
  const element = document.getElementById(id);
  if (element) element.hidden = !visible;
}

function updateRoleInterface() {
  // 待审批 / 被拒的教师按**学生界面**显示 —— 后端也会拒掉他们的教师端点，两边口径一致。
  // ⚠️ 先判 role === "teacher" 再看审批状态：超管的 role 是 "admin"，
  // 不能因为它 teacher_status 恰好是 pending 就被降成学生界面。
  const currentUser = authState.user;
  const teacherUsable =
    currentUser?.role !== "teacher" || currentUser?.teacher_status === "approved";
  classState.role =
    ["teacher", "admin"].includes(currentUser?.role) && teacherUsable ? "teacher" : "student";
  const roleName = formatRole(classState.role);
  document.querySelectorAll("[data-role-only]").forEach((element) => {
    element.hidden = element.dataset.roleOnly !== classState.role;
  });
  document.getElementById("classRoleName").textContent = `${roleName} · ${authState.user?.name || "--"}`;
  document.getElementById("studentClassView").hidden = classState.role !== "student";
  document.getElementById("teacherClassView").hidden = classState.role !== "teacher";
  document.getElementById("studentExamView").hidden = classState.role !== "student";
  document.getElementById("teacherExamView").hidden = classState.role !== "teacher";

  // 首页 / 学情面板：学生看到学生视图，教师看到班级学情视图
  const isTeacher = classState.role === "teacher";
  showRoleView("studentDashboardView", !isTeacher);
  showRoleView("teacherDashboardView", isTeacher);
  showRoleView("studentLearningView", !isTeacher);
  showRoleView("teacherLearningView", isTeacher);

  // 导航文案随角色变，避免出现「导航写个人仪表盘、面板写班级学情总览」的现场穿帮
  setTextById("navTitleDashboard", isTeacher ? "班级学情总览" : "个人仪表盘");
  setTextById("navTitleLearning", isTeacher ? "班级学情分析" : "学情面板");

  // 教师审批页只对超级管理员出现（**不要**用 data-role-only：那套按 classState.role 比较，
  // 而 admin 在那个字段里是 "teacher"，会把这一页永久隐藏）
  showRoleView("navTeacherApproval", authState.user?.role === "admin");
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

// ==================== 教师端：班级学情总览 ====================
// 教师没有"本人学情"（没有答题记录），所以首页与学情面板改渲染班级维度数据。
// 数据全部来自既有的 GET /api/class/{id}/report（后端已做 require_class_manager 权限校验），
// 不新增任何后端接口。

async function loadTeacherClassOverview(options = {}) {
  if (!authState.user || classState.role !== "teacher") return;
  if (!options.silent) {
    setTextById("teacherDashboardSummary", "正在读取班级学情…");
    setTextById("teacherLearningSummary", "正在读取班级学情…");
  }
  if (!(classState.teacherClasses || []).length) {
    await loadClassWorkspace();   // 复用班级面板的加载逻辑，其教师分支会填充 teacherClasses
  }
  const classes = classState.teacherClasses || [];
  if (!classes.length) {
    teacherState.report = null;
    teacherState.classId = null;
    renderTeacherEmptyState();
    return;
  }
  const classId = Number(classState.selectedClassId) || Number(classes[0].class_id || classes[0].id);
  classState.selectedClassId = classId;
  try {
    teacherState.report = await fetchApiJson(`/api/class/${classId}/report?requester_id=${getCurrentUserId()}`);
    teacherState.classId = classId;
  } catch (error) {
    teacherState.report = null;
    renderTeacherEmptyState(`班级学情读取失败：${error.message}`);
    return;
  }
  renderTeacherClassView();
}

function disposeTeacherRadar() {
  if (teacherState.chart) {
    teacherState.chart.dispose();
    teacherState.chart = null;
  }
}

function setTeacherListState(id, className, text) {
  const target = document.getElementById(id);
  if (!target) return;
  target.className = `${className} empty-state`;
  target.textContent = text;
}

function renderTeacherEmptyState(message) {
  const emptyBox = document.getElementById("teacherDashboardEmpty");
  const bodyBox = document.getElementById("teacherDashboardBody");
  if (bodyBox) bodyBox.hidden = true;
  if (emptyBox) {
    emptyBox.hidden = false;
    emptyBox.className = "data-list empty-state";
    // 无班级与"读取失败"是两种不同处境：前者给指路话术，后者只如实报错，都不填任何推测数字
    emptyBox.innerHTML = message
      ? `<p>${escapeHtml(message)}</p>`
      : '<p>你还没有创建班级，暂时没有可分析的班级学情。</p>'
        + '<p>请在「班级管理」创建班级，学生用邀请码加入并完成练习后，这里会显示班级平均正确率、模块掌握度雷达与全班薄弱知识点排行。</p>'
        + '<button id="teacherGoCreateClassButton" type="button">去创建班级</button>';
  }
  const button = document.getElementById("teacherGoCreateClassButton");
  if (button) button.addEventListener("click", () => switchTab("classes"));

  setTextById("teacherDashboardSummary", message ? "班级学情暂不可用。" : "尚未创建班级。");
  setTextById("teacherLearningSummary", message ? "班级学情暂不可用。" : "尚未创建班级。");
  setTeacherListState("teacherWeakNodeRankingFull", "learning-node-list", "请先创建班级。");
  setTeacherListState("teacherStudentDetailList", "student-report-list", "请先创建班级。");
  setTeacherListState("teacherModuleTable", "student-report-list", "请先创建班级。");
  disposeTeacherRadar();
  const radarBox = document.getElementById("teacherClassRadarChart");
  if (radarBox) {
    radarBox.innerHTML = "";
    radarBox.textContent = "尚未创建班级。";
  }
}

function normalizeClassRadar(radarData) {
  if (!Array.isArray(radarData)) return [];
  return radarData.map((item) => ({
    moduleName: item.module || item.name || "未命名模块",
    score: Number(item.value ?? 0),          // 后端已给 0-100（average_level / 4 * 100）
    level: Number(item.average_level ?? 0),  // 0-4
    practiced: Number(item.practiced_nodes ?? 0),
  }));
}

function renderTeacherClassView() {
  const report = teacherState.report;
  if (!report) {
    renderTeacherEmptyState();
    return;
  }
  const classes = classState.teacherClasses || [];
  const selected = classes.find((item) => Number(item.class_id || item.id) === Number(teacherState.classId));
  const className = selected?.name || report.class_name || "当前班级";

  const emptyBox = document.getElementById("teacherDashboardEmpty");
  const bodyBox = document.getElementById("teacherDashboardBody");
  if (emptyBox) emptyBox.hidden = true;
  if (bodyBox) bodyBox.hidden = false;

  const students = Array.isArray(report.students) ? report.students : [];
  const weakNodes = Array.isArray(report.weak_nodes) ? report.weak_nodes : [];
  const answered = students.some((item) => Number(item.learning_summary?.total_answers || 0) > 0);
  const attention = students.filter((item) => Number(item.learning_summary?.weak_nodes || 0) > 0).length;
  const studentCount = Number(report.student_count ?? students.length);

  setTextById("teacherDashboardSummary", `${className} · 共 ${studentCount} 名学生。`
    + (answered ? "以下数据来自全班真实答题记录。" : "班级尚无答题记录，各项指标暂为空。"));
  setTextById("teacherLearningSummary", `${className} · 共 ${studentCount} 名学生。`
    + (answered ? "以下为全班汇总与逐生明细。" : "班级尚无答题记录。"));
  setTextById("teacherClassStudentCount", String(studentCount));
  // 无答题记录时显示 -- 而不是 0%：0% 会被读成"全班一道题都没做对"
  setTextById("teacherClassAccuracy", answered ? `${Math.round(Number(report.overall_accuracy || 0) * 100)}%` : "--");
  setTextById("teacherClassAttention", String(attention));
  setTextById("teacherWeakNodeCount", String(weakNodes.length));

  renderTeacherClassRadar(report.radar_data, answered);
  renderTeacherWeakRanking("teacherWeakNodeRanking", weakNodes, 5);
  renderTeacherWeakRanking("teacherWeakNodeRankingFull", weakNodes, Infinity);
  renderTeacherStudentList(students);
  renderTeacherModuleTable(report.radar_data);
  syncTeacherDashboardClassSelect(classes, teacherState.classId);
}

function renderTeacherClassRadar(radarData, hasAnswers) {
  const box = document.getElementById("teacherClassRadarChart");
  if (!box) return;
  const stats = normalizeClassRadar(radarData);
  disposeTeacherRadar();
  // 不画全 0 的雷达：那会让人误读成"班级掌握度为 0"。
  // practiced_nodes 全为 0 即代表全班还没在这些模块上产生练习记录。
  if (!stats.length || !stats.some((item) => item.practiced > 0)) {
    box.innerHTML = "";
    box.textContent = hasAnswers
      ? "本班学生尚未在课程模块上产生练习记录，暂无法计算模块掌握度。"
      : "班级尚无答题记录，暂无法计算模块掌握度。";
    return;
  }
  if (!window.echarts) {
    box.textContent = "ECharts 加载失败，无法绘制班级雷达图。";
    return;
  }
  box.innerHTML = "";
  teacherState.chart = echarts.init(box);
  teacherState.chart.setOption({
    tooltip: {
      formatter: (params) => {
        const item = stats[params.dataIndex];
        return `${item.moduleName}<br>班级平均掌握度：${item.score}%<br>平均等级：${item.level}/4<br>已练知识点：${item.practiced}`;
      },
    },
    radar: { indicator: stats.map((item) => ({ name: item.moduleName, max: 100 })), radius: "66%", splitNumber: 4 },
    series: [
      {
        type: "radar",
        data: [{ value: stats.map((item) => item.score), name: "班级模块掌握度", areaStyle: { color: "rgba(47,143,131,.2)" }, lineStyle: { color: "#2f8f83", width: 3 }, itemStyle: { color: "#1f5f8b" } }],
      },
    ],
  }, true);
}

function renderTeacherWeakRanking(targetId, weakNodes, limit) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!weakNodes.length) {
    target.className = "learning-node-list empty-state";
    target.textContent = "全班暂无薄弱知识点。学生产生答题记录后，这里会按薄弱人数从多到少展示。";
    return;
  }
  target.className = "learning-node-list";
  // 只读统计：不加 data-node-id、不用 button —— 复用学生端的点击跳问答行为在这里语义不对
  target.innerHTML = weakNodes.slice(0, limit).map((item) => {
    const nodeId = item.node_id || item.nodeId || "";
    const name = NODE_NAME_FALLBACKS[nodeId] || findNodeName(nodeId) || nodeId;
    return `<div class="learning-node-button weak-node"><strong>${escapeHtml(name)}</strong><span>${Number(item.student_count || 0)} 名学生薄弱 · ${escapeHtml(nodeId)}</span></div>`;
  }).join("");
}

function renderTeacherStudentList(students) {
  const target = document.getElementById("teacherStudentDetailList");
  if (!target) return;
  if (!students.length) {
    target.className = "student-report-list empty-state";
    target.textContent = "该班级暂无学生。学生凭邀请码加入后，这里会显示每人的答题次数与掌握情况。";
    return;
  }
  target.className = "student-report-list";
  target.innerHTML = students.map((item) => {
    const summary = item.learning_summary || {};
    const total = Number(summary.total_answers || 0);
    const weakCount = Number(summary.weak_nodes || 0);
    const accuracy = total ? `${Math.round(Number(summary.overall_accuracy || 0) * 100)}%` : "--";
    const badge = weakCount ? `薄弱 ${weakCount}` : total ? "状态良好" : "暂无答题";
    const badgeClass = weakCount ? "weak" : total ? "mastered" : "unlearned";
    return `<article><div><strong>${escapeHtml(item.name || `用户 ${item.user_id}`)}</strong><span>答题 ${total} 次 · 正确率 ${accuracy} · 已练 ${Number(summary.practiced_nodes || 0)} 个 · 已掌握 ${Number(summary.mastered_nodes || 0)} 个知识点</span></div><span class="mastery-badge ${badgeClass}">${badge}</span></article>`;
  }).join("");
}

function renderTeacherModuleTable(radarData) {
  const target = document.getElementById("teacherModuleTable");
  if (!target) return;
  const stats = normalizeClassRadar(radarData);
  if (!stats.length) {
    target.className = "student-report-list empty-state";
    target.textContent = "暂无模块掌握度数据。";
    return;
  }
  target.className = "student-report-list";
  // 只展示后端给出的三个数值（百分比 / 等级 / 已练节点数）。后端没有模块级达标线，
  // 前端不自造"达标/未达标"阈值。
  target.innerHTML = stats.map((item) => {
    const badge = item.practiced ? `已练 ${item.practiced} 个知识点` : "暂无数据";
    return `<article><div><strong>${escapeHtml(item.moduleName)}</strong><span>平均掌握度 ${item.score}% · 等级 ${item.level}/4</span></div><span class="mastery-badge ${item.practiced ? "learning" : "unlearned"}">${badge}</span></article>`;
  }).join("");
}

function syncTeacherDashboardClassSelect(classes, classId) {
  const select = document.getElementById("teacherDashboardClassSelect");
  if (!select) return;
  select.innerHTML = classes.map((item) => {
    const id = Number(item.class_id || item.id);
    return `<option value="${id}"${id === Number(classId) ? " selected" : ""}>${escapeHtml(item.name || "未命名班级")}</option>`;
  }).join("");
  select.hidden = classes.length <= 1;   // 只有一个班级时不必给选择器
  if (!select.dataset.bound) {
    select.dataset.bound = "1";
    select.addEventListener("change", () => {
      classState.selectedClassId = Number(select.value);
      loadTeacherClassOverview();
    });
  }
}

// 在途请求标记：连点「查看学情」不再叠加请求（后端每个学生要算一份报告，
// 叠加几次就慢几倍），也保证只有最后一次点击的结果会覆盖界面。
let teacherClassDetailsInFlight = null;

// 上一次**成功**渲染出来的那一屏（连同它属于哪个班）。
// 读得慢或者读不到的时候，把这个原样放回去，一个数字都不清零 —— 老师看到的是
// 「还是刚才那些数」而不是「面板坏了」。按班级记，所以换班时不会把上一个班的数字留住。
let teacherClassDetailsShown = null;

// 第一原则是这一屏**一定要加载得出来**，而不是到点弹一个错误出来把演示搞砸。
// 所以 90 秒只是一道最后的保险闸，正常路径（1-3 秒）永远碰不到它；
// 两次尝试共用这一个预算，等久了就不再重试（重试只救「秒断」那种，比如后端刚重启完）。
const CLASS_DETAILS_BUDGET_MS = 90000;
const CLASS_DETAILS_RETRY_DELAY_MS = 800;
const CLASS_DETAILS_RETRY_MIN_LEFT_MS = 15000;
const CLASS_DETAILS_SLOW_FAILURE_MS = 10000;

// 读不到时只在列表底下加一句可点击的软提示。
// ★ 这里不出现「失败」「超时」这类字眼，也不去动上面那三个数字：老师该看到的是
// 「还没读到」，不是「坏了」——一句话就能让整场演示显得是系统出错了。
function showClassDetailsSoftHint(message, classId) {
  const studentList = document.getElementById("classStudentList");
  if (!studentList) return;
  const hint = document.createElement("p");
  hint.className = "muted-line";
  hint.textContent = message;
  hint.style.cursor = "pointer";
  hint.style.textDecoration = "underline";
  hint.addEventListener("click", () => loadTeacherClassDetails(classId));
  studentList.appendChild(hint);
}

function renderClassDetails(classId, overview, studentList, reportData) {
  const students = reportData.students || [];
  const average = Math.round(Number(reportData.overall_accuracy || 0) * 100);
  const attention = students.filter((item) => Number(item.learning_summary?.weak_nodes || 0) > 0).length;
  overview.innerHTML = `<div><span>学生人数</span><strong>${students.length}</strong></div><div><span>平均正确率</span><strong>${average}%</strong></div><div><span>待关注学生</span><strong>${attention}</strong></div>`;
  renderStudentReports(students);
  teacherClassDetailsShown = {
    classId,
    overviewHtml: overview.innerHTML,
    studentListHtml: studentList.innerHTML,
    studentListClassName: studentList.className,
  };
}

// 两次都没读到时走这里。两条分支都不写「失败」「超时」，也不写假的 0：
//   同一个班 → 把上次读出来的原样放回去（数字还在，只是没刷新）
//   没读出来过的班 → 只给一句中性的状态，绝不摆一排 0 / -- / 0
function restoreClassDetailsOnFailure(classId, overview, studentList) {
  const shown = teacherClassDetailsShown;
  if (shown && shown.classId === classId) {
    overview.innerHTML = shown.overviewHtml;
    studentList.className = shown.studentListClassName;
    studentList.innerHTML = shown.studentListHtml;
  } else {
    overview.innerHTML = '<div><span>状态</span><strong>读取较慢</strong></div>';
    studentList.className = "student-report-list empty-state";
    studentList.textContent = "";
  }
  showClassDetailsSoftHint("学情读取较慢，点这里再读一次。", classId);
}

async function loadTeacherClassDetails(classId) {
  classState.selectedClassId = classId;
  // 连点同一个班：直接忽略，连面板都不重置（否则会把已经读出来的数字擦成「读取中」）。
  const previousRequest = teacherClassDetailsInFlight;
  if (previousRequest?.classId === classId) return;
  if (previousRequest) previousRequest.controller?.abort();

  const overview = document.getElementById("classOverview");
  const studentList = document.getElementById("classStudentList");
  overview.innerHTML = '<div><span>状态</span><strong>读取中</strong></div>';
  studentList.className = "student-report-list empty-state";
  studentList.textContent = "正在读取学生学情...";

  const token = Symbol("classDetails");
  const guard = { token, controller: null, classId };
  teacherClassDetailsInFlight = guard;

  // 「读取中」不再是死寂的空白：超过 3 秒就把已用时摆出来，演示时一眼看得出还活着。
  const startedAt = Date.now();
  const tickerId = setInterval(() => {
    if (teacherClassDetailsInFlight?.token !== token) return;
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    if (seconds < 3) return;
    studentList.textContent = `正在读取学生学情...（已用时 ${seconds} 秒）`;
  }, 1000);

  try {
    // 只打 /report 一次。原先并发的那条 /students 是纯重复：后端要再按学生逐个算一遍
    // 报告，而下面的 students 本来就优先取 reportData.students，那份数据没人用。
    const url = `/api/class/${classId}/report?requester_id=${getCurrentUserId()}`;
    let reportData = null;
    for (let attempt = 1; attempt <= 2 && reportData === null; attempt += 1) {
      const left = CLASS_DETAILS_BUDGET_MS - (Date.now() - startedAt);
      if (left <= 0) break;
      const controller = new AbortController();
      guard.controller = controller;   // 下一次点击要 abort 的是**这一轮**的请求
      const timeoutId = setTimeout(() => controller.abort(), left);
      try {
        reportData = await fetchApiJson(url, { signal: controller.signal });
      } catch (error) {
        // 读不到不是「错误」，是「还没读到」：吞掉，由下面的兜底统一说话。
      } finally {
        clearTimeout(timeoutId);
      }
      // 已经被后一次点击取代（换班了）：立刻收手，连重试都不必 —— 别为一个已经离开的班
      // 再打一次后端。
      if (teacherClassDetailsInFlight?.token !== token) break;
      const elapsed = Date.now() - startedAt;
      if (
        reportData === null
        && attempt < 2
        && elapsed < CLASS_DETAILS_SLOW_FAILURE_MS
        && CLASS_DETAILS_BUDGET_MS - elapsed > CLASS_DETAILS_RETRY_MIN_LEFT_MS
      ) {
        await new Promise((resolve) => setTimeout(resolve, CLASS_DETAILS_RETRY_DELAY_MS));
      }
    }
    if (teacherClassDetailsInFlight?.token !== token) return;   // 已经被后一次点击取代
    if (reportData === null) {
      restoreClassDetailsOnFailure(classId, overview, studentList);
    } else {
      renderClassDetails(classId, overview, studentList, reportData);
    }
  } finally {
    clearInterval(tickerId);
    if (teacherClassDetailsInFlight?.token === token) teacherClassDetailsInFlight = null;
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

// ==================== 教师审批（超级管理员） ====================

async function loadPendingTeachers() {
  const target = document.getElementById("teacherApprovalList");
  if (!target) return;
  target.className = "data-list empty-state";
  target.textContent = "正在加载待审批教师…";
  try {
    const data = await fetchApiJson("/api/admin/teachers?status=pending");
    renderTeacherApproval(data.teachers || []);
  } catch (error) {
    // 非超管走不到这里（switchTab 已挡），但 token 过期时会 —— 文案直接来自后端 detail。
    showClassError("teacherApprovalList", `加载失败：${error.message}`);
  }
}

function renderTeacherApproval(teachers) {
  const target = document.getElementById("teacherApprovalList");
  if (!target) return;
  if (!teachers.length) {
    target.className = "data-list empty-state";
    target.textContent = "当前没有待审批的教师账号。";
    return;
  }
  target.className = "data-list";
  target.textContent = "";
  teachers.forEach((teacher) => {
    const row = document.createElement("div");
    row.className = "class-row";

    const info = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = `${teacher.name} · ${teacher.username || "（无用户名）"}`;
    const detail = document.createElement("span");
    // 带上已建班级数：审批**不回收**已有班级关系，所以这个数决定"点了拒绝会留下什么"
    detail.textContent = `ID ${teacher.user_id} · 已建班级 ${teacher.class_count} 个`;
    info.append(name, detail);

    const actions = document.createElement("div");
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "ghost-button";
    approve.textContent = "通过";
    approve.addEventListener("click", () => decideTeacherApproval(teacher.user_id, true));
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "ghost-button";
    reject.textContent = "拒绝";
    reject.addEventListener("click", () => decideTeacherApproval(teacher.user_id, false));
    actions.append(approve, reject);

    row.append(info, actions);
    target.append(row);
  });
}

async function decideTeacherApproval(userId, approved) {
  const status = document.getElementById("teacherApprovalStatus");
  try {
    // ⚠️ postJson 返回的是 Response 不是 JSON，必须自己 await response.json() 并查 ok
    //    （照 decideShareRequest 的写法）。
    const action = approved ? "approve" : "reject";
    const response = await postJson(`/api/admin/teachers/${userId}/${action}`, {});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(readApiError(data, "审批失败"));
    if (status) status.textContent = approved ? "已通过该教师账号。" : "已拒绝该教师账号。";
    await loadPendingTeachers();
  } catch (error) {
    if (status) status.textContent = `审批失败：${error.message}`;
  }
}

function showClassError(targetId, message) {
  const target = document.getElementById(targetId);
  if (!target) return;
  target.className = `${targetId === "incomingShareRequests" ? "approval-list" : "data-list"} error-state`;
  target.textContent = message;
}

async function fetchApiJson(path, options = {}) {
  const response = await authenticatedFetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(readApiError(data, `请求失败（${response.status}）`));
  return data;
}

async function postJson(path, payload) {
  return authenticatedFetch(path, { method: "POST", body: JSON.stringify(payload) });
}

function authenticatedFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  if (authState.token) headers.set("Authorization", `Bearer ${authState.token}`);
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers });
}

async function loadExamWorkspace() {
  if (!authState.user) return;
  updateRoleInterface();
  if (classState.role === "teacher") {
    await loadClassWorkspace();
    syncTeacherExamClasses();
    ensureExamNodeCatalog();   // 不 await：自管加载态与错误态，不阻塞考试页其余部分
    loadTeacherExamList();     // 同上：回看入口要能自己刷出来，不拖住表单渲染
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
  target.innerHTML = examState.available.map((exam) => {
    const closed = exam.status === "closed";
    const submitted = Boolean(exam.submitted);
    let badge;
    let button;
    if (submitted) {
      // 已交卷的，关闭与否都能点开看自己那一份（学生只该看到自己的答案与得分）。
      badge = `<span class="source-badge ${closed ? "closed" : "synced"}">${closed ? "已结束" : "已提交"}</span>`;
      button = `<button type="button" class="ghost-button" data-result-exam-id="${Number(exam.exam_id)}">查看成绩</button>`;
    } else if (closed) {
      badge = `<span class="source-badge closed">已结束</span>`;
      button = `<button type="button" disabled>已结束</button>`;
    } else {
      badge = `<span class="source-badge local">待作答</span>`;
      button = `<button type="button" data-exam-id="${Number(exam.exam_id)}">进入考试</button>`;
    }
    return `
    <article>
      <div><strong>${escapeHtml(exam.title)}</strong><span>${formatDateTime(exam.created_at)} · 满分 ${Number(exam.total_score)}</span></div>
      ${badge}
      ${button}
    </article>`;
  }).join("");
  target.querySelectorAll("[data-exam-id]:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => openStudentExam(Number(button.dataset.examId)));
  });
  target.querySelectorAll("[data-result-exam-id]").forEach((button) => {
    button.addEventListener("click", () => openStudentExamResult(Number(button.dataset.resultExamId)));
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
      <small>${escapeHtml(question.type)} · ${question.score} 分 · ${escapeHtml(findNodeName(question.nodeId))}</small>
      <label class="exam-answer-label" for="exam-answer-${question.id}">你的答案</label>
      <textarea id="exam-answer-${question.id}" data-question-id="${question.id}" rows="3" placeholder="${String(question.type).includes("选择") ? "输入选项字母，例如 A" : "输入完整作答过程"}"></textarea>
      <div class="grading-photo-row">
        <label class="grading-photo-button" for="exam-photo-${question.id}">拍照识别</label>
        <input id="exam-photo-${question.id}" class="proof-file-input" type="file" accept="image/*" capture="environment" data-exam-photo="${question.id}">
        <span id="exam-ocr-status-${question.id}" class="grading-ocr-status"></span>
      </div>
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
  // 拍照输入用 data-exam-photo 而不是 data-question-id，上面那个选择器不会重复绑到它。
  form.querySelectorAll("[data-exam-photo]").forEach((input) => {
    input.addEventListener("change", () => handleExamPhoto(input.dataset.examPhoto, input.files[0]));
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

function renderExamSubmission(data, mode) {
  const target = document.getElementById("examResult");
  target.hidden = false;
  target.className = "exam-result";
  const pending = data.status === "pending_review";
  // mode === "recall"：学生点「查看成绩」回看自己已交的那一份（不是刚交完）。
  const recall = mode === "recall";
  target.innerHTML = `
    <div class="exam-score"><span>${recall ? "我的得分" : pending ? "自动判分得分" : "本次得分"}</span><strong>${Number(data.total_score || 0)}</strong><small>${recall ? (pending ? "主观题等待教师复核" : "这是你交卷时的判分结果") : pending ? "主观题等待教师复核" : "判分完成并已更新学情"}</small></div>
    <div class="exam-review">${(data.answers || []).map((answer, index) => `<article class="${answer.is_correct === false ? "wrong" : "correct"}"><strong>${index + 1}. ${answer.review_status === "pending_review" ? "待复核" : answer.is_correct ? "正确" : "错误"}</strong><p>本题得分 ${Number(answer.score || 0)}</p></article>`).join("")}</div>
    <button id="backToExamListButton" type="button">返回考试列表</button>`;
  document.getElementById("examForm").hidden = true;
  document.getElementById("backToExamListButton").addEventListener("click", resetExam);
  document.getElementById("examSubmitStatus").textContent = recall ? "已查看成绩" : pending ? "待复核" : "已提交";
  updateExamStatus();
  if (!recall) renderDashboard();   // 回看历史成绩没有新的学情变化，不必再拉一次
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
  // 按钮被禁用时要说明原因，否则教师只会看到"点了没反应"
  if (!classes.length) {
    const target = document.getElementById("teacherExamResult");
    if (target) {
      target.className = "exam-result empty-state";
      target.textContent = "尚未创建班级，无法发布考试。请先到「班级管理」创建班级，学生凭邀请码加入后再发布。";
    }
  }
}

// ==================== 在线考试：知识点选择器 ====================
// 组卷的知识点唯一数据源是 data/documents/题库节点映射.md（后端 recommender 按 node_id 精确查找）。
// 下面这张表是该文件的真实快照（78 个知识点 / 88 道题），用于前端预检提示；
// 最终能否组卷仍以后端 POST /api/exam/generate 的返回为准。
// 题库文件变更后需按《部署说明.md》给出的命令重新生成。
// 注意：初等数论(nt_)/组合数学(cm_)/代数结构(ag_) 在该文件中一道题都没有，故不在此表内。
// 读取方是 examNodeState 相关的选择器函数；examNodeState 本身声明在文件开头（TDZ 原因）。
const EXAM_NODE_QUESTION_COUNTS = {
  pl_01_01: 2, pl_01_02: 3, pl_02_01: 2, pl_02_02: 3, pl_02_03: 1, pl_02_04: 2,
  pl_03_01: 2, pl_03_02: 1, pl_03_03: 1, pl_03_04: 1, pl_03_05: 2, pl_03_06: 1, pl_03_07: 1, pl_03_08: 1,
  fl_01_01: 1, fl_01_02: 1, fl_01_03: 1, fl_01_04: 1, fl_02_01: 1, fl_02_02: 1, fl_02_03: 1, fl_02_04: 1, fl_02_05: 1, fl_02_06: 1,
  st_01_01: 1, st_01_02: 1, st_01_03: 1, st_01_04: 1, st_02_01: 1, st_02_02: 1, st_02_03: 1, st_02_04: 1, st_02_05: 1, st_03_01: 1, st_03_02: 1, st_03_03: 1,
  mi_01_01: 1, mi_01_02: 2, mi_02_01: 1, mi_03_01: 1, mi_03_02: 1, mi_03_03: 1, mi_03_04: 1, mi_03_05: 1,
  rel_01_01: 1, rel_01_02: 1, rel_01_03: 1, rel_02_01: 1, rel_02_02: 1, rel_02_03: 1, rel_02_04: 1, rel_02_05: 1,
  rel_03_01: 1, rel_03_02: 1, rel_03_03: 1, rel_03_04: 1, rel_04_01: 1, rel_04_02: 1, rel_04_03: 1, rel_04_04: 1, rel_04_05: 1,
  gt_01_01: 1, gt_01_02: 1, gt_01_03: 1, gt_01_04: 1, gt_02_01: 1, gt_02_02: 1, gt_02_03: 1, gt_02_04: 1,
  gt_03_01: 1, gt_03_02: 1, gt_03_03: 1, gt_03_04: 1, gt_03_05: 1, gt_04_01: 1, gt_04_02: 1, gt_04_03: 1, gt_04_04: 1,
};

async function ensureExamNodeCatalog() {
  const list = document.getElementById("teacherExamNodeList");
  if (!list || examNodeState.catalog.length || examNodeState.loading) return;
  examNodeState.loading = true;
  list.className = "node-picker-list empty-state";
  list.textContent = "正在加载知识点目录…";
  try {
    let modules = graphState.modules;
    if (!modules || !modules.length) {
      // 不调用 loadKnowledgeGraph()：那会往隐藏的图谱容器里 init echarts 并改 graphState.loaded。
      // 这里只取数据，归一化后也不写回 graphState，避免干扰图谱页自己的加载判定。
      const response = await fetch(`${KB_API_BASE_URL}/kb/knowledge-graph`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `知识图谱接口返回 ${response.status}`);
      modules = normalizeKnowledgeGraph(data);
    }
    examNodeState.catalog = buildExamNodeCatalog(modules);
    examNodeState.loading = false;
    renderExamNodePicker();
  } catch (error) {
    examNodeState.loading = false;
    list.className = "node-picker-list error-state";
    list.textContent = `知识点目录加载失败：${error.message}。可刷新页面重试。`;
  }
}

function buildExamNodeCatalog(modules) {
  const catalog = [];
  (modules || []).forEach((module) => {
    (module.children || []).forEach((concept) => {
      (concept.items || []).forEach((item) => {
        const nodeId = item.nodeId;
        if (!nodeId) return;
        catalog.push({
          nodeId,
          name: NODE_NAME_FALLBACKS[nodeId] || item.name || nodeId,   // 短中文名，不用 findNodeName 的长路径
          conceptName: concept.name || "未分组",
          moduleId: module.nodeId || module.id,
          moduleName: module.name || "未命名模块",
          questionCount: Number(EXAM_NODE_QUESTION_COUNTS[nodeId] || 0),
        });
      });
    });
  });
  return catalog;
}

function examNodeName(nodeId) {
  // 目录未加载完就被选中的情况兜底为 node_id 本身 —— 绝不猜名字
  return NODE_NAME_FALLBACKS[nodeId]
    || examNodeState.catalog.find((node) => node.nodeId === nodeId)?.name
    || nodeId;
}

function renderExamNodePicker() {
  const list = document.getElementById("teacherExamNodeList");
  if (!list) return;
  const query = examNodeState.query.trim().toLowerCase();
  const pool = examNodeState.catalog.filter((node) => !examNodeState.onlyWithQuestions || node.questionCount);
  const hit = (node, fields) => fields.some((value) => String(value || "").toLowerCase().includes(query));
  // 两段式匹配：先只按知识点名 / node_id 精确找。若一个都没命中，再放宽到模块名与所属概念名。
  // 不能一上来就匹配概念名 —— 概念名往往包含知识点名（如"等价与德摩根律"含"德摩根"），
  // 搜"德摩根"会把同概念下的兄弟知识点一并带出来，教师看到的结果比想要的宽。
  let visible = query ? pool.filter((node) => hit(node, [node.name, node.nodeId])) : pool;
  if (query && !visible.length) {
    visible = pool.filter((node) => hit(node, [node.moduleName, node.conceptName]));
  }

  if (!visible.length) {
    list.className = "node-picker-list empty-state";
    list.textContent = examNodeState.onlyWithQuestions
      ? "没有匹配的知识点。可取消「只看有题知识点」查看全部模块。"
      : "没有匹配的知识点，请更换关键词。";
    renderExamNodeSelection();
    return;
  }

  const byModule = new Map();
  visible.forEach((node) => {
    if (!byModule.has(node.moduleId)) byModule.set(node.moduleId, { name: node.moduleName, concepts: new Map() });
    const bucket = byModule.get(node.moduleId);
    if (!bucket.concepts.has(node.conceptName)) bucket.concepts.set(node.conceptName, []);
    bucket.concepts.get(node.conceptName).push(node);
  });

  list.className = "node-picker-list";
  list.innerHTML = Array.from(byModule.entries()).map(([moduleId, module]) => {
    const nodes = Array.from(module.concepts.values()).flat();
    const usable = nodes.filter((node) => node.questionCount);
    const usableTotal = usable.reduce((sum, node) => sum + node.questionCount, 0);
    const header = usable.length
      ? `<span>可出题 ${usable.length} 个知识点 / ${usableTotal} 道题</span><button type="button" class="ghost-button" data-select-module="${escapeHtml(moduleId)}">选中有题项</button>`
      : '<span class="node-picker-none">题库暂无题目</span>';
    const groups = Array.from(module.concepts.entries()).map(([conceptName, conceptNodes]) => `
      <div class="node-picker-group">
        <h5>${escapeHtml(conceptName)}</h5>
        ${conceptNodes.map((node) => `
          <label class="node-option${node.questionCount ? "" : " node-option-empty"}" title="${node.questionCount ? `题库现有 ${node.questionCount} 道题` : "题库中该知识点暂无题目，选中后无法用于组卷"}">
            <input type="checkbox" data-node-checkbox="${escapeHtml(node.nodeId)}"${node.questionCount ? "" : " disabled"}${examNodeState.selected.has(node.nodeId) ? " checked" : ""}>
            <span>${escapeHtml(node.name)}</span>
            <small>${node.questionCount ? `${node.questionCount} 道题` : "暂无题目"}</small>
          </label>`).join("")}
      </div>`).join("");
    return `<section class="node-picker-module" data-module="${escapeHtml(moduleId)}"><header><strong>${escapeHtml(module.name)}</strong>${header}</header>${groups}</section>`;
  }).join("");

  list.querySelectorAll("[data-node-checkbox]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const nodeId = checkbox.dataset.nodeCheckbox;
      if (checkbox.checked) examNodeState.selected.add(nodeId);
      else examNodeState.selected.delete(nodeId);
      renderExamNodeSelection();
    });
  });
  list.querySelectorAll("[data-select-module]").forEach((button) => {
    button.addEventListener("click", () => {
      examNodeState.catalog
        .filter((node) => node.questionCount && String(node.moduleId) === button.dataset.selectModule)
        .forEach((node) => examNodeState.selected.add(node.nodeId));
      renderExamNodePicker();
    });
  });
  renderExamNodeSelection();
}

function renderExamNodeSelection() {
  const box = document.getElementById("teacherExamNodeSelected");
  const budget = document.getElementById("teacherExamNodeBudget");
  const selectedIds = Array.from(examNodeState.selected);

  if (box) {
    if (!selectedIds.length) {
      box.className = "node-picker-selected empty-state";
      box.textContent = "尚未选择知识点。可按模块分组勾选，或点「载入示例」。";
    } else {
      box.className = "node-picker-selected";
      box.innerHTML = selectedIds.map((nodeId) => `<span class="node-chip">${escapeHtml(examNodeName(nodeId))}<small>${escapeHtml(nodeId)}</small><button type="button" data-remove-node="${escapeHtml(nodeId)}" aria-label="移除">×</button></span>`).join("");
      box.querySelectorAll("[data-remove-node]").forEach((button) => {
        button.addEventListener("click", () => {
          examNodeState.selected.delete(button.dataset.removeNode);
          renderExamNodePicker();
        });
      });
    }
  }

  if (!budget) return;
  if (!selectedIds.length) {
    budget.className = "node-picker-budget";
    budget.textContent = "";
    return;
  }
  const available = selectedIds.reduce((sum, nodeId) => sum + Number(EXAM_NODE_QUESTION_COUNTS[nodeId] || 0), 0);
  const need = Number(document.getElementById("teacherExamCount")?.value || 0);
  const enough = !need || available >= need;
  budget.className = `node-picker-budget${enough ? "" : " warn"}`;
  const summary = enough
    ? `已选 ${selectedIds.length} 个知识点，题库可用题目合计 ${available} 道（题目数量 ${need || "-"} 道）。`
    : `已选 ${selectedIds.length} 个知识点，题库可用题目合计仅 ${available} 道，少于题目数量 ${need} 道，生成会失败：请调小题目数量或再选几个知识点。`;
  // EXAM_NODE_QUESTION_COUNTS 是**只有知识点维度、没有题型维度**的快照，
  // 所以这里算不出「限定题型后可用的到底有几道」—— 那就如实说明它是全部题型的合计，
  // 绝不编一个看着准确、其实是猜的数字出来。
  const types = examTypeFilter();
  budget.textContent = types
    ? `${summary}已限定题型（${types.join("、")}）：上面的合计是全部题型的题量，限定后实际可用的只会更少，不够时请调小题目数量、再勾几个知识点，或放宽题型。`
    : summary;
}

// 示例 = 按题量从多到少累加，直到累计题量 ≥ 当前题目数量。
// 纯由 EXAM_NODE_QUESTION_COUNTS 推导，不硬编码任何 node_id，也不代表"推荐教学重点"。
function loadExamNodeExample() {
  const need = Math.max(1, Number(document.getElementById("teacherExamCount")?.value || 5));
  const sorted = examNodeState.catalog
    .filter((node) => node.questionCount)
    .sort((a, b) => b.questionCount - a.questionCount || a.nodeId.localeCompare(b.nodeId));
  examNodeState.selected.clear();
  let total = 0;
  for (const node of sorted) {
    if (total >= need) break;
    examNodeState.selected.add(node.nodeId);
    total += node.questionCount;
  }
  renderExamNodePicker();
}

// 后端 409 的原始文案是"现有题库仅找到 N 道匹配题目，少于请求的 M 道"（面向开发者）。
// 这里只把文案翻译成教师能懂的话并给出可执行建议，不改任何组卷/判分逻辑，也不编造题量。
function explainExamGenerateError(message) {
  const match = String(message || "").match(/仅找到\s*(\d+)\s*道匹配题目，少于请求的\s*(\d+)\s*道/);
  if (!match) return `发布失败：${message}`;
  const found = Number(match[1]);
  const need = Number(match[2]);
  const types = examTypeFilter();
  // 限定了题型时 found 是**筛完之后**的题量。不点明的话老师会以为题库真没题，
  // 转头来报「题型选择是坏的」。
  const scope = types ? `在限定的题型（${types.join("、")}）里只有 ${found} 道题` : `在题库中共有 ${found} 道题`;
  return `生成失败：所选知识点${scope}，少于需要生成的 ${need} 道。`
    + `处理办法：把「题目数量」改为 ${found > 0 ? found : 1}，或再勾选几个标着「N 道题」的知识点`
    + (types ? `，或放宽上面的题型限制。` : `。`);
}

async function generateTeacherExam(event) {
  event.preventDefault();
  const classId = Number(document.getElementById("examClassSelect").value);
  const title = document.getElementById("teacherExamTitle").value.trim();
  const nodeIds = Array.from(examNodeState.selected);
  const questionCount = Number(document.getElementById("teacherExamCount").value);
  const target = document.getElementById("teacherExamResult");
  // 原来是 `if (!classId || !title || !nodeIds.length) return;` —— 静默返回，
  // 教师点了「生成并发布」界面毫无反应。改为逐项可读提示。
  const problems = [];
  if (!classId) problems.push("请先选择班级（还没有班级请先到「班级管理」创建）");
  if (!title) problems.push("请填写考试标题");
  if (!nodeIds.length) problems.push("请至少选择 1 个知识点");
  if (!Number.isFinite(questionCount) || questionCount < 1) problems.push("题目数量需为不小于 1 的整数");
  if (problems.length) {
    target.className = "exam-result error-state";
    target.textContent = `无法生成试卷：${problems.join("；")}。`;
    return;
  }
  if (nodeIds.length > 20) {
    target.className = "exam-result error-state";
    target.textContent = `知识点最多选择 20 个（后端限制），当前已选 ${nodeIds.length} 个。`;
    return;
  }
  target.className = "exam-result empty-state";
  target.textContent = "正在从题库生成试卷...";
  try {
    const response = await postJson("/api/exam/generate", {
      teacher_id: getCurrentUserId(),
      class_id: classId,
      title,
      node_ids: nodeIds,
      question_count: questionCount,
      // 不限题型时是 undefined —— JSON.stringify 会整个丢掉这个键，
      // 请求体与加「题型选择」之前逐字节相同（后端那个字段默认也是 None）。
      question_types: examTypeFilter(),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(readApiError(data, "考试生成失败"));
    examState.latestTeacherExamId = data.exam_id;
    target.className = "exam-result";
    target.innerHTML = `<div class="tool-status-banner success"><div><span>试卷已发布</span><strong>${escapeHtml(data.title)}</strong></div><span>${data.questions.length} 道题 · 满分 ${Number(data.total_score)}</span></div><div class="teacher-question-list">${data.questions.map((question, index) => `<article><strong>${index + 1}. ${escapeHtml(question.content)}</strong><span>${escapeHtml(question.question_type)} · ${Number(question.score)} 分 · 答案 ${escapeHtml(question.answer || "人工复核")}</span></article>`).join("")}</div>`;
    document.getElementById("teacherLatestExam").textContent = `#${data.exam_id}`;
    document.getElementById("teacherLatestExamCount").textContent = data.questions.length;
    document.getElementById("loadExamResultsButton").disabled = false;
    loadTeacherExamList();   // 刚发布的这一份立刻出现在下面的列表里
  } catch (error) {
    target.className = "exam-result error-state";
    target.textContent = explainExamGenerateError(error.message);
  }
}

async function loadTeacherExamResults() {
  if (!examState.latestTeacherExamId) return;
  const target = document.getElementById("teacherExamAnalytics");
  target.className = "student-report-list empty-state";
  target.textContent = "正在读取成绩...";
  try {
    const data = await fetchApiJson(`/api/exam/${examState.latestTeacherExamId}/results?requester_id=${getCurrentUserId()}`);
    examState.latestResult = data;
    renderTeacherExamAnalytics();
  } catch (error) {
    target.className = "student-report-list error-state";
    target.textContent = `成绩读取失败：${error.message}`;
  }
}

// 汇总层作答情况：谁交了 / 每人得分与交卷时间 / 每知识点正确率 / 薄弱知识点。
// 后端一直有 node_statistics 与 weak_nodes，原先前端拿到就丢，这里补上。
// 差集「谁没交」要另取一次班级名单 —— /results 里的 students 是**内连接**，只含交了卷的人。
function renderTeacherExamAnalytics() {
  const data = examState.latestResult;
  const target = document.getElementById("teacherExamAnalytics");
  if (!data || !target) return;
  const students = data.students || [];
  const nodes = (data.node_statistics || []).filter((item) => item.accuracy !== null && item.accuracy !== undefined);
  const weakNodes = data.weak_nodes || [];
  const nodeLine = nodes.length
    ? nodes.map((item) => `<article><div><strong>${escapeHtml(findNodeName(item.node_id))}</strong><span>${Number(item.correct_answers)}/${Number(item.graded_answers)} 人答对${Number(item.pending_review) ? ` · ${Number(item.pending_review)} 份待复核` : ""}</span></div><span class="mastery-badge ${Number(item.accuracy) >= 0.6 ? "mastered" : "weak"}">${Math.round(Number(item.accuracy) * 100)}%</span></article>`).join("")
    : `<article><div><strong>暂无可用正确率</strong><span>这一份卷子的主观题可能都还在等待复核。</span></div></article>`;
  target.className = "student-report-list";
  target.innerHTML = `
    <article><div><strong>提交 ${Number(data.submitted_count)} 人</strong><span>平均 ${Number(data.average_score)} · 最高 ${Number(data.highest_score)} · 最低 ${Number(data.lowest_score)}</span></div></article>
    <article><div><strong>薄弱知识点 ${weakNodes.length} 个</strong><span>${weakNodes.length ? escapeHtml(weakNodes.map((node) => findNodeName(node)).join("、")) : "暂无明显薄弱知识点。"}</span></div></article>
    ${students.map((student) => `<article><div><strong>${escapeHtml(student.name)}</strong><span>${formatDateTime(student.submitted_at)}</span></div><span class="mastery-badge ${Number(student.total_score) >= 60 ? "mastered" : "weak"}">${Number(student.total_score)} 分</span></article>`).join("")}
    ${nodeLine}`;
  // 名单是后到的，到了再补一行「未交卷」，不阻塞上面的汇总。
  fillMissingSubmitters(data);
}

async function fillMissingSubmitters(data) {
  const target = document.getElementById("teacherExamAnalytics");
  const classId = Number(data.exam?.class_id || examState.latestExamClassId);
  if (!target || !classId) return;
  try {
    const roster = await fetchApiJson(`/api/class/${classId}/students?requester_id=${getCurrentUserId()}`);
    const submitted = new Set((data.students || []).map((student) => String(student.user_id)));
    const missing = (roster.students || []).filter((student) => !submitted.has(String(student.user_id)));
    if (!missing.length) return;
    const line = document.createElement("article");
    line.innerHTML = `<div><strong>未交卷 ${missing.length} 人</strong><span>${escapeHtml(missing.map((student) => student.name).join("、"))}</span></div>`;
    target.appendChild(line);
  } catch (error) {
    // 补不到就算了：这只是锦上添花，不该把已经渲染好的汇总整块变成错误态。
  }
}

// ==================== 在线考试：回看已发布的试卷 ====================
// 原先「生成并发布」把题目渲染进 #teacherExamResult 之后就再无入口：
// loadExamWorkspace 不恢复、examState 是纯内存，刷新即丢，教师找不到自己发过的卷子。
// 现在走 GET /api/exam/teacher/{id} 拿列表（教师名下所有班级），
// 点某份再走既有的 GET /api/exam/{id} 渲染只读题目。

async function loadTeacherExamList() {
  const target = document.getElementById("teacherExamHistory");
  if (!target) return;   // 旧缓存 index.html 没有这个节点
  target.className = "student-report-list empty-state";
  target.textContent = "正在读取已发布试卷...";
  try {
    examState.teacherExams = await fetchApiJson(`/api/exam/teacher/${getCurrentUserId()}`);
    renderTeacherExamList();
  } catch (error) {
    target.className = "student-report-list error-state";
    target.textContent = `试卷列表读取失败：${error.message}`;
  }
}

function renderTeacherExamList() {
  const target = document.getElementById("teacherExamHistory");
  if (!target) return;
  const exams = Array.isArray(examState.teacherExams) ? examState.teacherExams : [];
  if (!exams.length) {
    target.className = "student-report-list empty-state";
    target.textContent = "还没有发布过试卷。用上面的表单生成第一份后，这里会一直留着，随时可以回看、校对答案、结束考试。";
    return;
  }
  target.className = "student-report-list";
  target.innerHTML = exams.map((exam) => {
    const closed = exam.status === "closed";
    return `
    <article>
      <div><strong>${escapeHtml(exam.title)}</strong><span>${escapeHtml(exam.class_name)} · ${formatDateTime(exam.created_at)} · ${Number(exam.question_count)} 题 · 满分 ${Number(exam.total_score)}</span></div>
      <div class="exam-history-actions">
        <span class="source-badge ${closed ? "closed" : Number(exam.submitted_count) ? "synced" : "local"}">${closed ? "已结束" : `${Number(exam.submitted_count)} 人已交`}</span>
        <button type="button" class="ghost-button" data-preview-exam-id="${Number(exam.exam_id)}">查看题目</button>
        <button type="button" class="ghost-button" data-paper-exam-id="${Number(exam.exam_id)}">查看答案</button>
        <button type="button" class="ghost-button" data-status-exam-id="${Number(exam.exam_id)}" data-status-target="${closed ? "published" : "closed"}">${closed ? "重新开放" : "结束考试"}</button>
      </div>
    </article>`;
  }).join("");
  target.querySelectorAll("[data-preview-exam-id]").forEach((button) => {
    button.addEventListener("click", () => previewTeacherExam(Number(button.dataset.previewExamId)));
  });
  target.querySelectorAll("[data-paper-exam-id]").forEach((button) => {
    button.addEventListener("click", () => loadTeacherExamPaper(Number(button.dataset.paperExamId)));
  });
  target.querySelectorAll("[data-status-exam-id]").forEach((button) => {
    button.addEventListener("click", () => toggleTeacherExamStatus(button));
  });
}

async function previewTeacherExam(examId) {
  const target = document.getElementById("teacherExamResult");
  target.className = "exam-result empty-state";
  target.textContent = "正在加载试卷...";
  try {
    const exam = await fetchApiJson(`/api/exam/${examId}`);
    const questions = exam.questions || [];
    // 学生端的 GET /api/exam/{id} 刻意不返回 answer 列（它只要求登录，
    // 回了答案就等于任何登录者都能偷到任意试卷的答案），所以这里只回看题干/题型/分值。
    // 顺手把它记成「最近试卷」，右侧「查看最近试卷成绩」便能直接查到这一份。
    examState.latestTeacherExamId = exam.exam_id;
    document.getElementById("teacherLatestExam").textContent = `#${exam.exam_id}`;
    document.getElementById("teacherLatestExamCount").textContent = questions.length;
    document.getElementById("loadExamResultsButton").disabled = false;
    target.className = "exam-result";
    target.innerHTML = `<div class="tool-status-banner success"><div><span>历史试卷（只读回看，不含答案）</span><strong>${escapeHtml(exam.title)}</strong></div><span>${questions.length} 道题 · 满分 ${Number(exam.total_score)}</span></div><div class="teacher-question-list">${questions.map((question, index) => `<article><strong>${index + 1}. ${escapeHtml(question.content)}</strong><span>${escapeHtml(question.question_type)} · ${Number(question.score)} 分 · ${escapeHtml(findNodeName(question.node_id))}</span></article>`).join("")}</div>`;
  } catch (error) {
    target.className = "exam-result error-state";
    target.textContent = `试卷加载失败：${error.message}`;
  }
}

// ==================== 考试：校对答案 / 结束考试 / 导出成绩 / 学生回看 ====================

function examStatusLabel(status) {
  return ({ published: "进行中", closed: "已结束", draft: "草稿" })[status] || String(status || "未知");
}

// 校对答案：走 GET /api/exam/{id}/paper（require_teacher + 班级归属校验，所以**含答案**）。
// 与「查看题目」刻意分成两条路：那条走学生端端点，任何登录者都能读，因此永远不含 answer。
async function loadTeacherExamPaper(examId) {
  const target = document.getElementById("teacherExamResult");
  target.className = "exam-result empty-state";
  target.textContent = "正在加载参考答案...";
  try {
    const paper = await fetchApiJson(`/api/exam/${examId}/paper?requester_id=${getCurrentUserId()}`);
    const questions = paper.questions || [];
    examState.latestTeacherExamId = paper.exam_id;
    examState.latestExamClassId = paper.class_id;
    document.getElementById("teacherLatestExam").textContent = `#${paper.exam_id}`;
    document.getElementById("teacherLatestExamCount").textContent = questions.length;
    document.getElementById("loadExamResultsButton").disabled = false;
    target.className = "exam-result";
    target.innerHTML = `<div class="tool-status-banner success"><div><span>教师校对视图 · 含参考答案</span><strong>${escapeHtml(paper.title)}</strong></div><span>${escapeHtml(paper.class_name)} · ${questions.length} 道题 · ${examStatusLabel(paper.status)}</span></div><div class="teacher-question-list">${questions.map((question, index) => `<article><strong>${index + 1}. ${escapeHtml(question.content)}</strong><span>${escapeHtml(question.question_type)} · ${Number(question.score)} 分 · ${escapeHtml(findNodeName(question.node_id))}</span><p class="exam-answer-key">参考答案：${question.answer ? escapeHtml(question.answer) : "（无标准答案，需人工复核）"}</p></article>`).join("")}</div>`;
  } catch (error) {
    target.className = "exam-result error-state";
    target.textContent = `参考答案加载失败：${error.message}`;
  }
}

// 结束 / 重新开放。全站没有 confirm() 先例（浏览器弹窗在演示里很突兀），
// 改成**行内二次确认**：第一次点只是把按钮变成「确认结束？」，再点才真的发请求。
function toggleTeacherExamStatus(button) {
  const examId = Number(button.dataset.statusExamId);
  const target = button.dataset.statusTarget;
  if (!examId || !target) return;
  if (button.dataset.confirming !== "1") {
    button.dataset.confirming = "1";
    button.dataset.originalLabel = button.textContent;
    button.textContent = target === "closed" ? "确认结束？" : "确认重开？";
    // 3 秒内没再点就退回原样，避免「点了一次忘了、过一会儿手滑点到」。
    setTimeout(() => {
      if (button.dataset.confirming === "1") {
        button.dataset.confirming = "";
        button.textContent = button.dataset.originalLabel || "";
      }
    }, 3000);
    return;
  }
  button.dataset.confirming = "";
  button.disabled = true;
  button.textContent = "正在提交...";
  // 这不是 async 函数，用 Promise 链而不是 await —— 与文件里其它按钮处理器同一风格。
  postJson(`/api/exam/${examId}/status?requester_id=${getCurrentUserId()}`, { status: target }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(readApiError(data, "状态更新失败"));
    button.disabled = false;
    loadTeacherExamList();     // 重新拉列表，按钮文案与徽标由服务端状态决定
    const banner = document.getElementById("teacherExamResult");
    if (banner) {
      banner.className = "exam-result";
      banner.textContent = data.message || `已更新为「${examStatusLabel(data.status)}」。`;
    }
  }).catch((error) => {
    button.disabled = false;
    button.textContent = button.dataset.originalLabel || "重试";
    const banner = document.getElementById("teacherExamResult");
    if (banner) {
      banner.className = "exam-result error-state";
      banner.textContent = `操作失败：${error.message}`;
    }
  });
}

// CSV 字段转义：RFC 4180 —— 含逗号/引号/换行的整体加双引号，内部双引号翻倍。
function csvCell(value) {
  let text = value === null || value === undefined ? "" : String(value);
  // Excel / WPS 会把 = + - @ 开头的单元格当公式执行，前面加个单引号关掉这条路径。
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function buildExamResultsCsv(data) {
  const rows = [[
    "姓名",
    "得分",
    "判分状态",
    "交卷时间",
  ]];
  (data.students || []).forEach((student) => {
    rows.push([
      student.name,
      Number(student.total_score),
      student.status === "pending_review" ? "待复核" : "已判分",
      formatDateTime(student.submitted_at),
    ]);
  });
  rows.push([]);
  rows.push(["知识点", "答对人数", "已判分人数", "正确率", "待复核份数"]);
  (data.node_statistics || []).forEach((item) => {
    rows.push([
      findNodeName(item.node_id),
      Number(item.correct_answers),
      Number(item.graded_answers),
      item.accuracy === null || item.accuracy === undefined ? "暂无" : `${Math.round(Number(item.accuracy) * 100)}%`,
      Number(item.pending_review),
    ]);
  });
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
}

function exportExamResultsCsv() {
  const data = examState.latestResult;
  const note = document.getElementById("teacherExamResult");
  if (!data) {
    if (note) {
      note.className = "exam-result error-state";
      note.textContent = "请先在上面点某一份试卷的「查看题目」或「查看答案」，再来导出它的成绩。";
    }
    return;
  }
  const examTitle = (data.exam && data.exam.title) || `exam-${examState.latestTeacherExamId}`;
  // 必须带 UTF-8 BOM，否则 Excel / WPS 打开中文全是乱码。
  const blob = new Blob(["\ufeff", buildExamResultsCsv(data)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${examTitle}-成绩清单.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // 立刻 revoke 在部分浏览器上会截断下载，延后一拍更稳。
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

// 学生点「查看成绩」：走 /my-submission，身份只来自 token，接口上根本没有 user_id 参数。
async function openStudentExamResult(examId) {
  const target = document.getElementById("examResult");
  target.hidden = false;
  target.className = "exam-result empty-state";
  target.textContent = "正在读取你的成绩...";
  try {
    const data = await fetchApiJson(`/api/exam/${examId}/my-submission`);
    renderExamSubmission(data, "recall");
  } catch (error) {
    target.className = "exam-result error-state";
    target.textContent = `成绩读取失败：${error.message}`;
  }
}

// ==================== 组卷：题型多选 ====================

// 题库里仅有的三种题型（data/documents/题库节点分布：证明题 41 / 概念题 28 / 选择题 19）。
// 顺序就是界面上复选框的书写顺序，只用于「全勾 == 不限」的判断。
const EXAM_QUESTION_TYPES = ["概念题", "选择题", "证明题"];

// 勾中的题型 → 送给后端的 question_types。
// 一个都没勾 或 三个全勾 都返回 undefined（= 不限题型）：
// JSON.stringify 会把 undefined 的键整个丢掉，所以这两种情况下请求体与
// 加「题型选择」之前**逐字节相同**，老师不会因为顺手全勾而拿到一份奇怪的卷子。
function examTypeFilter() {
  const checked = Array.from(document.querySelectorAll('input[name="teacherExamType"]:checked'))
    .map((input) => input.value)
    .filter((value) => EXAM_QUESTION_TYPES.includes(value));
  if (!checked.length || checked.length === EXAM_QUESTION_TYPES.length) return undefined;
  return checked;
}

// ==================== 考试答题纸：拍照识别 ====================

// 自测练习那边的 handleCalcPhoto / handleProofPhoto / handleGradingPhoto
// 全都写死了各自的 DOM 选择器与 practiceState / gradingState，一个都不能直接调，
// 所以这里单独写一个 —— 但复用同一条后端链路（POST /api/vision/parse）与同一组纯函数。
async function handleExamPhoto(questionId, file) {
  if (!file) return;
  const status = document.getElementById(`exam-ocr-status-${questionId}`);
  const textarea = document.getElementById(`exam-answer-${questionId}`);
  if (!status || !textarea) return;
  if (!String(file.type || "").startsWith("image/")) {
    status.className = "grading-ocr-status error";
    status.textContent = "请选择图片文件。";
    return;
  }
  // 识别最长可能要几十秒（后端超时上限 60 秒），而考试有 15 分钟倒计时且到点**自动交卷**。
  // 识别在飞的时候学生可能已经交卷、点了「返回列表」、或换开了另一份卷子 ——
  // 那这时的结果必须丢弃，否则会写进一张已经交上去的答题纸里。
  const examId = examState.examId;
  status.className = "grading-ocr-status";
  status.textContent = "正在识别…";
  try {
    const data = await parseVisionImage(file);
    if (examState.examId !== examId || document.getElementById("examForm").hidden) return;
    const text = selectVisionText(data, "student_answer");
    if (!text) throw new Error("图片中未识别到可用文字");
    // ⚠️ 必须同时写两个地方：交卷走的是 examState.answers.get(question.id)，
    // 只改 textarea.value 的话学生一交卷答案就没了。
    // 反过来也**绝不能重渲染答题纸**（textarea 没有 value 回填），那会冲掉已经写好的其它答案。
    textarea.value = text;
    examState.answers.set(Number(questionId), text);
    updateExamStatus();
    status.textContent = `识别完成：${describeVisionResult(data) || "已提取文本"}，可修改后提交`;
  } catch (error) {
    status.className = "grading-ocr-status error";
    status.textContent = `识别失败：${error.message}`;
  }
}

function formatDateTime(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

function syncProofStepMode() {
  const isProof = document.getElementById("gradingQuestionType").value === "proof";
  document.getElementById("proofStepWorkspace").hidden = !isProof;
  document.getElementById("gradingStudentAnswer").hidden = isProof;
  document.querySelector('label[for="gradingStudentAnswer"]').hidden = isProof;
  document.getElementById("submitGradingButton").hidden = isProof;
  renderProofSteps();
}

function resetProofCoach() {
  gradingState.proofSteps = [];
  gradingState.explanationSteps = [];
  gradingState.explanationIndex = 0;
  const draft = document.getElementById("proofStepInput");
  if (draft) draft.value = "";
  const panel = document.getElementById("proofExplanationPanel");
  if (panel) panel.hidden = true;
  renderProofSteps();
}

function addProofStep() {
  const input = document.getElementById("proofStepInput");
  const step = input.value.trim();
  if (!step) {
    input.focus();
    return false;
  }
  gradingState.proofSteps.push(step);
  input.value = "";
  renderProofSteps();
  input.focus();
  return true;
}

function undoProofStep() {
  const previous = gradingState.proofSteps.pop();
  if (previous) document.getElementById("proofStepInput").value = previous;
  renderProofSteps();
}

function renderProofSteps() {
  const list = document.getElementById("proofStepList");
  if (!list) return;
  list.innerHTML = gradingState.proofSteps.length
    ? gradingState.proofSteps.map((step, index) => `<li><span>${index + 1}</span><p>${escapeHtml(step)}</p></li>`).join("")
    : '<li class="proof-step-empty">从“已知”或题设条件开始，逐步记录你的推导。</li>';
  document.getElementById("proofStepProgress").textContent = gradingState.proofSteps.length
    ? `已记录 ${gradingState.proofSteps.length} 步`
    : "尚未记录步骤";
  document.getElementById("undoProofStepButton").disabled = !gradingState.proofSteps.length;
  typesetMath(list);
}

function finishProof() {
  const draft = document.getElementById("proofStepInput").value.trim();
  if (draft) addProofStep();
  if (gradingState.proofSteps.length < 2) {
    document.getElementById("proofStepInput").focus();
    document.getElementById("gradingOcrStatus").textContent = "请至少记录两个推导步骤后再完成证明。";
    return;
  }
  document.getElementById("gradingStudentAnswer").value = gradingState.proofSteps
    .map((step, index) => `${index + 1}. ${step}`)
    .join("\n");
  document.getElementById("gradingForm").requestSubmit();
}

function prepareProofExplanation(reference) {
  gradingState.explanationSteps = window.Team4Utils.splitProofSteps(reference);
  gradingState.explanationIndex = 0;
  const panel = document.getElementById("proofExplanationPanel");
  panel.hidden = !gradingState.explanationSteps.length;
  renderProofExplanation();
}

function revealNextProofExplanation() {
  if (gradingState.explanationIndex < gradingState.explanationSteps.length) {
    gradingState.explanationIndex += 1;
    renderProofExplanation();
  } else {
    gradingState.explanationIndex = 0;
    renderProofExplanation();
  }
}

function renderProofExplanation() {
  const total = gradingState.explanationSteps.length;
  const shown = gradingState.explanationIndex;
  document.getElementById("proofExplanationProgress").textContent = `${shown}/${total}`;
  const target = document.getElementById("proofExplanationSteps");
  target.innerHTML = gradingState.explanationSteps.slice(0, shown)
    .map((step, index) => `<li><span>${index + 1}</span><div>${window.GradingUtils.formatGradingText(step)}</div></li>`)
    .join("");
  const button = document.getElementById("nextProofExplanationButton");
  button.textContent = shown === 0 ? "展示第一步" : shown < total ? "展示下一步" : "重新讲解";
  typesetMath(target);
}

async function loadGradingQuestions() {
  const type = document.getElementById("gradingQuestionType").value;
  syncProofStepMode();
  resetProofCoach();
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
  resetProofCoach();
  syncProofStepMode();
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
    const data = await parseVisionImage(file);
    const isProof = document.getElementById("gradingQuestionType").value === "proof";
    window.GradingUtils.applyGradingOcrText(data, {
      studentAnswer: document.getElementById("gradingStudentAnswer"),
      proofStepInput: document.getElementById("proofStepInput"),
      isProof,
    });
    if (status) {
      status.textContent = `识别完成：${describeVisionResult(data) || "已提取文本"}，可修改后提交`;
    }
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
  if (document.getElementById("gradingQuestionType").value === "proof") {
    prepareProofExplanation(document.getElementById("gradingReference").value);
  }
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
      ? nodeNameMap.get(nodeId) || findNodeName(nodeId)
      : pathItem.node_name || pathItem.name || nodeNameMap.get(nodeId) || findNodeName(nodeId);
    const action = typeof pathItem === "string" ? "学习" : pathItem.action || "练习";
    const questions = typeof pathItem === "string"
      ? []
      : pathItem.recommended_questions || pathItem.questions || [];
    return `
      <article class="path-step" data-action="${escapeHtml(action)}">
        <div class="path-step-head">
          <span class="path-step-number">${String(pathItem.step || index + 1).padStart(2, "0")}</span>
          <div><strong>${escapeHtml(shortenNodeName(name))}</strong></div>
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
  // 收起全部时同步清空浏览历史
  graphState.nodeHistory = [];
  graphState.historyIndex = -1;
  updateGraphHistoryButtons();
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
    // ⚠️ 每个命令后面都要 `\b`：没有它，`\int_0^1` 会被 `\in` 吃成 `∈t_0^1`、
    //    `\infty` 变成 `∈fty`、`\top` 变成 `→p`、`\leftarrow` 变成 `≤ftarrow`。
    //    模型漏掉 $ 时会吐裸 LaTeX，这条降级就是唯一接住它的地方，所以必错不可。
    .replace(/\\rightarrow\b|\\to\b/g, "→")
    .replace(/\\leftrightarrow\b/g, "↔")
    .replace(/\\wedge\b|\\land\b/g, "∧")
    .replace(/\\vee\b|\\lor\b/g, "∨")
    .replace(/\\neg\b|\\lnot\b/g, "¬")
    .replace(/\\notin\b/g, "∉")
    .replace(/\\in\b/g, "∈")
    .replace(/\\forall\b/g, "∀")
    .replace(/\\exists\b/g, "∃")
    .replace(/\\neq\b/g, "≠")
    .replace(/\\leq?\b/g, "≤")
    .replace(/\\geq?\b/g, "≥")
    .replace(/\\tag\{([^{}]+)\}/g, "（$1）")
    .replace(/\\notag\b/g, "");

  html = renderMarkdownBlocks(html);

  mathSegments.forEach((formula, index) => {
    html = html.replace(`MATHJAXTOKEN${index}ENDTOKEN`, escapeHtml(formula));
  });
  return html;
}

// `---` / `***` / `___` 单独成行是分隔线，必须在列表之前认出来：
// 下面 `^\s*[-*+]\s*\S` 会先把 `---` 看成「一个 - 加内容 --」的无序列表项，
// 渲染成 `• --` —— 就是老师截图里那个东西。
const THEMATIC_BREAK = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;

// 表格要「表头行 + |---| 分隔行」两行都在才算数 —— 光有竖线不算：
// 正文里的 `|x|`（绝对值、行列式）不该把整段切成块模式。
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_SEPARATOR = /^\s*\|[\s:|-]*-[\s:|-]*\|\s*$/;

function isTableStart(lines, index) {
  const head = lines[index];
  const separator = lines[index + 1];
  return Boolean(head && separator && TABLE_ROW.test(head) && TABLE_SEPARATOR.test(separator));
}

// 一行表格拆成单元格。此时 html 已经过 escapeHtml，拆竖线不会碰到 HTML 实体。
function splitTableRow(row) {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderMarkdownBlocks(html) {
  const lines = html.split("\n");
  // ⚠️ 这里**刻意不**把「·」「•」算作块级语法：纯文本里冒出一个「·」不该让整段
  //    从 <br> 模式切成块模式，那是扩散半径最大的一处，必须克制。
  //    （但已经在块模式里时，「·」会被下面当成无序列表项 —— 见 putItem 的调用点。）
  const hasBlockSyntax = lines.some((line, index) => (
    /^\s*$/.test(line)
    || /^\s{0,3}#{1,6}\s+/.test(line)
    || THEMATIC_BREAK.test(line)
    || isTableStart(lines, index)
    || /^\s*[-*+]\s+/.test(line)
    || /^\s*\d+[.)]\s+/.test(line)
    || /^\s*&gt;\s+/.test(line)
  ));
  if (!hasBlockSyntax) {
    return html.replace(/\n/g, "<br>");
  }

  const output = [];
  let paragraph = [];
  // 列表栈：一层 <ol>/<ul> 一帧，帧里记着「还没闭合的 <li>」。
  // <li> 不在原地关闭，而是延后到下一个出口 —— 只要它不提前关，
  // 子项就会被塞进上一个 <li> 里，嵌套就是自然结果，而不是另起一个列表。
  const stack = [];
  // 第一次出现列表行时的缩进量。比它还浅的缩进一律夹到这一层，
  // 免得整篇都缩进 2 格、末行没缩进时被拆成两个列表。
  let baseIndent = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      output.push(`<p class="answer-paragraph">${paragraph.join("<br>")}</p>`);
      paragraph = [];
    }
  };
  const frame = () => stack[stack.length - 1];
  const closeItem = () => {
    const top = frame();
    if (top && top.itemOpen) {
      output.push("</li>");
      top.itemOpen = false;
    }
  };
  const openFrame = (type, indent, startAttr) => {
    output.push(`<${type} class="answer-list"${startAttr}>`);
    stack.push({ type, indent, itemOpen: false });
  };
  const closeFrame = () => {
    closeItem();
    output.push(`</${stack.pop().type}>`);
  };
  const closeAllFrames = () => {
    while (stack.length) closeFrame();
  };
  const indentOf = (line) => line.replace(/\t/g, "    ").match(/^ */)[0].length;

  // 用**源里的编号**配 start="N"，不做顺序计数器重排。
  // 源编号本来就是 1 时一个字都不加 → 输出与改造前逐字节相同。
  // 这既忠实又能自愈：LLM 真的会吐 `1. 1. 1. 1.`，也会吐 `3.`。
  const orderedStartAttr = (number) => {
    const value = Number(number);
    // > 1e6 时忽略：浏览器对 start 有上限，加了反而被夹成错的。
    return value > 1 && value <= 1e6 ? ` start="${value}"` : "";
  };

  const putItem = (type, content, indent, startAttr) => {
    flushParagraph();
    // 先退栈到「比本行更浅」的那一层为止 —— 退掉的每一层都会补上自己的 </li></ul>。
    // ⚠️ 条件是 stack.length > 1：**绝不因为缩进变浅就把最外层列表也关掉**。
    //    否则一行缩进不一致的内容（LLM 偶尔混进一个制表符）会把它拆成两个列表，
    //    而改造前那种「不看缩进」的写法是会合成一个的 —— 那是纯粹的倒退。
    //    真正要换列表的情况（ul 里插 ol、被标题/空行/段落打断）各有各的出口，不靠这里。
    while (stack.length > 1 && frame().indent > indent) closeFrame();
    if (!stack.length || frame().indent < indent) {
      openFrame(type, indent, startAttr);          // 更深（或从无到有）→ 新开一层，嵌进上一层的 <li>
    } else if (frame().type !== type) {
      closeFrame();                                 // 同缩进但换了类型（ul 里插 ol）→ 关旧开新
      openFrame(type, indent, startAttr);
    }
    closeItem();                                    // 关掉同层的上一个 <li>（刚开的新层无副作用）
    output.push(`<li>${content}`);
    frame().itemOpen = true;
  };

  const listLine = (line) => {
    // 缩进比基准还浅的，一律夹到基准层 —— 保证「整篇缩进一致」的输入仍是一个列表。
    const raw = indentOf(line);
    const indent = baseIndent === null ? raw : Math.max(raw, baseIndent);
    const trimmed = line.trim();
    const ordered = trimmed.match(/^(\d+)[.)]\s+(.+)$/);
    if (ordered) {
      if (baseIndent === null) baseIndent = raw;
      putItem("ol", ordered[2], indent, orderedStartAttr(ordered[1]));
      return true;
    }
    // 「·」「•」只在块模式内部当列表项用（见函数开头的说明）。
    const bullet = trimmed.match(/^[-*+·•]\s*(.+)$/);
    if (bullet) {
      if (baseIndent === null) baseIndent = raw;
      putItem("ul", bullet[1], indent, "");
      return true;
    }
    return false;
  };

  const isListLine = (line) => /^\s*(?:\d+[.)]|[-*+·•])\s*\S/.test(line);

  // 一张表要一次吃掉好几行，所以这里用 for 而不是 forEach（forEach 里推不动 index）。
  const putTable = (start) => {
    const header = splitTableRow(lines[start]);
    let end = start + 2;                              // 跳过表头行与 |---| 分隔行
    while (end < lines.length && TABLE_ROW.test(lines[end])) end += 1;
    const cell = (tag, values) => values.map((value) => `<${tag}>${value}</${tag}>`).join("");
    const body = lines
      .slice(start + 2, end)
      .map((row) => `<tr>${cell("td", splitTableRow(row))}</tr>`)
      .join("");
    output.push(
      `<table class="answer-table"><thead><tr>${cell("th", header)}</tr></thead>`
      + `<tbody>${body}</tbody></table>`,
    );
    return end - start;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      const nextContentLine = lines.slice(index + 1).find((nextLine) => nextLine.trim());
      // 空行后面如果还是编号项，就先别关 —— 与改造前同一条判据，只是从
      // 「单个 listType」改成「栈顶那一层」。
      const continuesOrderedList =
        frame() && frame().type === "ol" && /^\s*\d+[.)]\s+/.test(nextContentLine || "");
      if (!continuesOrderedList) closeAllFrames();
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeAllFrames();
      const level = Math.min(heading[1].length + 3, 6);
      output.push(`<h${level} class="answer-heading">${heading[2]}</h${level}>`);
      continue;
    }

    // 分隔线要排在列表前面 —— `---` 长得就像列表项（见 THEMATIC_BREAK 的说明）。
    if (THEMATIC_BREAK.test(trimmed)) {
      flushParagraph();
      closeAllFrames();
      output.push('<hr class="answer-rule">');
      continue;
    }

    if (isTableStart(lines, index)) {
      flushParagraph();
      closeAllFrames();
      index += putTable(index) - 1;
      continue;
    }

    if (isListLine(line) && listLine(line)) continue;

    const quote = trimmed.match(/^&gt;\s+(.+)$/);
    if (quote) {
      flushParagraph();
      closeAllFrames();
      output.push(`<blockquote class="answer-quote">${quote[1]}</blockquote>`);
      continue;
    }

    // 列表之外的普通行：先把列表收干净再当段落 —— 编号由 start="N" 保住，
    // 结构不需要为了「不断号」而变形。
    closeAllFrames();
    paragraph.push(trimmed);
  }

  flushParagraph();
  closeAllFrames();
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

  return value.split("\n").map(convertInlineDollarMath).join("\n");
}

// 行内 $...$ → \(...\)。
//
// 原先是一条正则 `\$([^$\n]+?)\$` 从左往右配对。模型漏 $ 的时候（生成被截断时
// 尤其常见，尾部就是「…度数为奇数…$f(1) = a」这样半截的公式），它会把落单的那个 $
// 和**后面最近的一个 $** 硬凑成一对，把中间的中文整个当成公式体 —— 渲染出来就是
// 一片乱码，老师截图里的 `$f(1) = a` 就是这么来的。index.html 里 MathJax 自己也把
// $ 配成行内分隔符，所以漏网的那个 $ 到了它手上照样会乱配。
//
// 判据是**看两个 $ 之间装的是什么**：真公式不会夹着中文。夹了中文就说明是配错对，
// 把这个 $ 当字面量转义掉（\$），然后从它后面接着往下找 —— 这样既拆得开错配，
// 又不会像「整行有奇数个 $ 就全转义」那样把同在一行里的真公式一起牺牲掉。
const CJK = /[　-〿㐀-䶿一-鿿豈-﫿＀-￯]/;
const MAX_INLINE_MATH_CHARS = 200;

function looksLikeMath(body) {
  return Boolean(body) && body.length <= MAX_INLINE_MATH_CHARS && !CJK.test(body);
}

function convertInlineDollarMath(line) {
  let result = "";
  let cursor = 0;
  while (cursor < line.length) {
    const open = line.indexOf("$", cursor);
    if (open < 0) {
      result += line.slice(cursor);
      break;
    }
    // 前面带反斜杠的 $ 已经是要显示的字面量了，别再当分隔符。
    if (open > 0 && line[open - 1] === "\\") {
      result += line.slice(cursor, open + 1);
      cursor = open + 1;
      continue;
    }
    const close = line.indexOf("$", open + 1);
    const body = close < 0 ? "" : line.slice(open + 1, close);
    if (!looksLikeMath(body)) {
      result += `${line.slice(cursor, open)}\\$`;   // 落单或配错 → 当字面量
      cursor = open + 1;
      continue;
    }
    result += `${line.slice(cursor, open)}\\(${cleanInlineMath(body)}\\)`;
    cursor = close + 1;
  }
  return result;
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

// 图谱浏览历史 · 调试钩子（浏览器控制台/自动化测试也可用）
window.__graphDebug = {
  state: graphState,
  clickNode: (id, dataIndex) => {
    const node = graphState.nodeIndex.get(id);
    if (node) handleGraphClick({ dataType: "node", data: node, dataIndex: dataIndex ?? 0 });
    else throw new Error(`node not found: ${id}`);
  },
  history: () => graphState.nodeHistory.map((n) => ({ id: n.id, name: n.name })),
};

// 教材融合：全局函数，从知识图谱跳转教材指定知识点
function navigateTextbookFrame({ sectionId, kpId } = {}) {
  const textbookFrame = document.getElementById("textbookFrame");
  const contentWindow = textbookFrame?.contentWindow;
  if (!contentWindow) return false;
  const directNavigated = window.Team4Utils?.navigateTextbookWindow(contentWindow, { sectionId, kpId }) || false;
  if (directNavigated) return true;
  contentWindow.postMessage(
    { type: "navigate", ...(sectionId ? { sectionId } : {}), ...(kpId ? { kpId } : {}) },
    window.location.origin,
  );
  return false;
}

function navigateTextbookWithRetry(target) {
  const textbookTab = document.querySelector('[data-tab="textbook"]');
  if (textbookTab) textbookTab.click();
  let navigated = false;
  const attempt = () => {
    if (navigated) return;
    navigated = navigateTextbookFrame(target);
  };
  attempt();
  setTimeout(attempt, 300);
  setTimeout(attempt, 800);
  setTimeout(attempt, 1500);
}

window.openTextbookKP = function (kpId) {
  navigateTextbookWithRetry({ kpId });
};

window.openTextbookSection = function (secId) {
  navigateTextbookWithRetry({ sectionId: secId });
};
