// 「查看学情」加载链路的回归 —— 在 Node 里跑**真实的** loadTeacherClassDetails。
//
// app.js 是浏览器脚本，不能整体 require，所以按名字把要测的那几个函数从源码里抠出来，
// 配上假 document + 假 fetchApiJson 执行。这样测的是线上要跑的那段代码本身，
// 不是它的复制品。
//
// 用法：
//   node test_class_details.js                        # 测待上传_前端_2个/app.js（应当全过）
//   node test_class_details.js <旧的 app.js 路径> --negative   # 负向对照：期望那几条
//                                                     # 「新行为」用例全败，且败因必须是
//                                                     # 真的行为差异（不能是抠不到源码）
//
// 第一条原则是「一定要加载得出来」：所以断言里最要紧的是**面板不出现「失败」「超时」**
// 和**上一轮的数字不被清零**，而不是加载快不快。
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const argv = process.argv.slice(2);
const NEGATIVE = argv.includes("--negative");
const APP_JS = argv.find((item) => !item.startsWith("--"))
  || path.join(__dirname, "待上传_前端_2个", "app.js");
const source = fs.readFileSync(APP_JS, "utf8");

function sliceFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) return null;                     // 修复前的版本没有这些函数
  // 前面挂着 `async ` 的要一起带上，否则抠出来的函数体里 `await` 直接变成语法错误。
  const prefix = source.slice(Math.max(0, start - "async ".length), start) === "async " ? "async " : "";
  let depth = 0;
  let index = source.indexOf("{", start);
  for (; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    else if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return prefix + source.slice(start, index + 1);
    }
  }
  throw new Error(`function ${name} 的花括号不闭合`);
}

function sliceDeclaration(name) {
  const match = source.match(new RegExp(`^(?:const|let|var) ${name} = .*$`, "m"));
  return match ? match[0] : null;
}

// 两个纯时间常数在测试里压小，好让「慢失败不重试」几秒内就能验完；行为一模一样。
const SHRINK = { CLASS_DETAILS_RETRY_DELAY_MS: 40, CLASS_DETAILS_SLOW_FAILURE_MS: 250 };
const declarationFor = (name) => {
  const line = sliceDeclaration(name);
  if (!line) return null;
  return SHRINK[name] === undefined ? line : line.replace(/=\s*[\d_]+/, `= ${SHRINK[name]}`);
};

const WANTED_CONSTS = [
  "CLASS_DETAILS_BUDGET_MS", "CLASS_DETAILS_RETRY_DELAY_MS",
  "CLASS_DETAILS_RETRY_MIN_LEFT_MS", "CLASS_DETAILS_SLOW_FAILURE_MS",
  "teacherClassDetailsInFlight", "teacherClassDetailsShown",
];
const WANTED_FUNCS = [
  "loadTeacherClassDetails", "renderClassDetails", "restoreClassDetailsOnFailure",
  "showClassDetailsSoftHint", "renderStudentReports", "escapeHtml",
  // 旧版失败时走的就是它（把面板清成 0 / -- / 0 再写一句红字）。一起抠进来，
  // 负向对照才会因为**真行为不同**而失败，而不是因为「函数不存在」这种假失败。
  "renderEmptyClassOverview",
];

// ── 假 DOM：只要够 loadTeacherClassDetails 这一条链路用就行 ──────────────────
class FakeElement {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.text = "";
    this.html = "";
    this.className = "";
    this.style = {};
    this.listeners = {};
  }
  set innerHTML(value) { this.html = String(value); this.text = ""; this.children = []; }
  get innerHTML() { return this.html; }
  set textContent(value) { this.text = String(value); this.html = ""; this.children = []; }
  get textContent() {
    return [this.text, ...this.children.map((child) => child.textContent)]
      .filter(Boolean)
      .join(" ");
  }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  click() { (this.listeners.click || []).slice().forEach((handler) => handler()); }
}

const nodes = { classOverview: new FakeElement(), classStudentList: new FakeElement() };
globalThis.document = {
  getElementById: (id) => nodes[id] || null,
  createElement: (tag) => new FakeElement(tag),
};
globalThis.classState = { selectedClassId: null };
globalThis.getCurrentUserId = () => 7;

const fetchStub = { calls: 0, impl: null };
globalThis.fetchApiJson = (...args) => {
  fetchStub.calls += 1;
  return fetchStub.impl(...args);
};

// 缺哪块就少拼哪块，这样同一个脚本也能拿去跑修复前的 app.js（缺函数时自然全败）。
const bundle = [
  ...WANTED_CONSTS.map(declarationFor).filter(Boolean),
  ...WANTED_FUNCS.map(sliceFunction).filter(Boolean),
  "module.exports = { loadTeacherClassDetails, reset: () => {"
  + " teacherClassDetailsInFlight = null; teacherClassDetailsShown = null; } };",
].join("\n\n");

const sandbox = { module: { exports: {} } };
new Function("module", bundle)(sandbox.module);
const { loadTeacherClassDetails } = sandbox.module.exports;
const reset = sandbox.module.exports.reset || (() => {});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ── 断言helper ──────────────────────────────────────────────────────────────
const ERROR_WORDS = ["失败", "超时", "错误", "异常"];

function panelText() {
  return [
    nodes.classOverview.innerHTML,
    nodes.classStudentList.innerHTML,
    nodes.classStudentList.textContent,
  ].join(" | ");
}

function assertNoErrorWords(context = "") {
  const text = panelText();
  for (const word of ERROR_WORDS) {
    assert(!text.includes(word), `面板里出现了「${word}」：${text} ${context}`);
  }
}

function assertOverviewCount(count) {
  assert(
    nodes.classOverview.innerHTML.includes(`学生人数</span><strong>${count}</strong>`),
    `概览里没有「学生人数 ${count}」：${nodes.classOverview.innerHTML}`,
  );
}

function studentsPayload(count) {
  return {
    overall_accuracy: 0.75,
    students: Array.from({ length: count }, (_, index) => ({
      user_id: index + 1,
      name: `学生${index + 1}`,
      learning_summary: { total_answers: 10 + index, overall_accuracy: 0.7, weak_nodes: index % 2 },
    })),
  };
}

// 只有被 abort 才结束的 promise —— 用来复现「换班时旧请求被掐掉」。
function pendingUntilAborted(signal) {
  return new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => {
      const error = new Error("The operation was aborted.");
      error.name = "AbortError";
      reject(error);
    });
  });
}

function softHint() {
  return nodes.classStudentList.children.find((child) => child.textContent.includes("读取较慢"));
}

// ── 用例 ────────────────────────────────────────────────────────────────────
let passed = 0;
const failures = [];
const failureMessages = [];
async function check(label, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`  ✓ ${label}`);
  } catch (error) {
    const message = String(error.message).split("\n")[0];
    failures.push(label);
    failureMessages.push(`${label} → ${message}`);
    console.log(`  ✗ ${label}`);
    console.log(`      ${message}`);
  }
}

async function main() {
  console.log(`「查看学情」加载链路 —— 被测文件 ${path.relative(process.cwd(), APP_JS)}`);
  console.log(NEGATIVE ? `（负向对照：期望这些用例**全部失败**）\n` : "\n");

  await check("读到了就正常出数：学生人数 / 正确率 / 待关注", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    fetchStub.impl = async () => studentsPayload(3);
    await loadTeacherClassDetails(101);
    assertOverviewCount(3);
    assert(nodes.classOverview.innerHTML.includes("<strong>75%</strong>"), nodes.classOverview.innerHTML);
    assert.strictEqual(fetchStub.calls, 1);
    assert(nodes.classStudentList.innerHTML.includes("学生1"), nodes.classStudentList.innerHTML);
    assertNoErrorWords();
  });

  await check("等超过 3 秒时面板里出现「已用时 N 秒」，不再是死寂的空白", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    let release = null;
    fetchStub.impl = () => new Promise((resolve) => { release = resolve; });
    const running = loadTeacherClassDetails(102);
    await sleep(3300);
    assert(/已用时 [0-9]+ 秒/.test(nodes.classStudentList.textContent),
      `3 秒后仍只显示：${nodes.classStudentList.textContent}`);
    release(studentsPayload(1));
    await running;
    assert(nodes.classStudentList.innerHTML.includes("学生1"));
  });

  await check("读不到时自动重试一次；两次都不行也只给软提示，不出现「失败」「超时」", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    fetchStub.impl = async () => { throw new Error("请求失败（500）：Internal Server Error"); };
    await loadTeacherClassDetails(103);
    assert.strictEqual(fetchStub.calls, 2, `应当自动重试一次，实际请求 ${fetchStub.calls} 次`);
    assert(softHint(), `没有软提示：${nodes.classStudentList.textContent}`);
    assertNoErrorWords();
  });

  await check("软提示可点击：点一下真的会再读一次", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    fetchStub.impl = async () => { throw new Error("boom"); };
    await loadTeacherClassDetails(104);
    const hint = softHint();
    assert(hint, "找不到软提示元素");
    fetchStub.impl = async () => studentsPayload(2);
    const before = fetchStub.calls;
    hint.click();
    await sleep(30);
    assert.strictEqual(fetchStub.calls, before + 1, "点击软提示没有发起新请求");
    assertOverviewCount(2);
  });

  await check("同一个班重读读不到时，上一轮的数字原样保留（不清零）", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    fetchStub.impl = async () => studentsPayload(4);
    await loadTeacherClassDetails(105);
    const goodOverview = nodes.classOverview.innerHTML;
    assertOverviewCount(4);

    fetchStub.impl = async () => { throw new Error("boom"); };
    await loadTeacherClassDetails(105);
    assert.strictEqual(nodes.classOverview.innerHTML, goodOverview, "上一轮的数字被改掉了");
    assert(nodes.classStudentList.innerHTML.includes("学生1"), "上一轮的学生列表被清掉了");
    assert(softHint(), "应当补一句软提示");
    assertNoErrorWords();
  });

  await check("换班读不到时不残留上一个班的数字", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    fetchStub.impl = async () => studentsPayload(4);
    await loadTeacherClassDetails(106);
    assertOverviewCount(4);

    fetchStub.impl = async () => { throw new Error("boom"); };
    await loadTeacherClassDetails(107);
    assert(!nodes.classOverview.innerHTML.includes("<strong>4</strong>"),
      `上一个班的数字还留在屏幕上：${nodes.classOverview.innerHTML}`);
    assertNoErrorWords();
  });

  await check("连点 5 次同一个班：只发 1 个请求（在途守卫还在）", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    let release = null;
    fetchStub.impl = () => new Promise((resolve) => { release = resolve; });
    const runs = [0, 1, 2, 3, 4].map(() => loadTeacherClassDetails(108));
    await sleep(20);
    assert.strictEqual(fetchStub.calls, 1, `连点 5 次实际发了 ${fetchStub.calls} 个请求`);
    release(studentsPayload(1));
    await Promise.all(runs);
  });

  await check("换到另一个班时旧请求被 abort，且不再为重读旧班补一次请求", async () => {
    reset();
    nodes.classOverview = new FakeElement();
    nodes.classStudentList = new FakeElement();
    fetchStub.calls = 0;
    let firstSignal = null;
    fetchStub.impl = (url, options) => {
      if (fetchStub.calls === 1) {
        firstSignal = options.signal;
        return pendingUntilAborted(options.signal);
      }
      return Promise.resolve(studentsPayload(1));
    };
    const stuck = loadTeacherClassDetails(109);
    await sleep(20);
    const switching = loadTeacherClassDetails(110);
    await Promise.all([stuck, switching]);
    assert(firstSignal, "第一次请求没有带上 signal");
    assert.strictEqual(firstSignal.aborted, true, "换班时旧请求没有被 abort");
    assert.strictEqual(fetchStub.calls, 2, `换班后不该再补请求，实际 ${fetchStub.calls} 次`);
    assertOverviewCount(1);
  });

  console.log("");
  if (NEGATIVE) {
    // 负向对照要的不是「全败」：有几条钉的是**新旧都该成立**的不变量（正常出数、
    // 连点不叠加、换班 abort），它们在旧版上本来就过。真正要看的是——
    // ① 至少有几条败（说明这些用例确实在测东西）；② 每条败的都是**行为差异**，
    //    不能是「函数不存在」这类抠源码失败，否则负向对照等于什么都没证明。
    const artifacts = failureMessages.filter((message) => message.includes("is not defined"));
    const ok = failures.length > 0 && artifacts.length === 0;
    console.log(`负向对照：${passed} 过 / ${failures.length} 败`);
    console.log(`  （过的 ${passed} 条是「新旧都该成立」的不变量：正常出数、连点不叠加、换班 abort）`);
    if (artifacts.length) console.log(`  ★ 有 ${artifacts.length} 条是抠源码失败，不算数证：${artifacts.join("；")}`);
    console.log(`  ${ok ? "符合预期：每条失败都是真实的行为差异" : "★ 不符合预期"}`);
    process.exit(ok ? 0 : 1);
  }
  console.log(`共 ${passed + failures.length} 条：${passed} 过 / ${failures.length} 败`);
  process.exit(failures.length ? 1 : 0);
}

main();
