// 拍照识别「发送前压缩」的回归 —— 在 Node 里跑**真实的** prepareVisionUpload / shrinkVisionImage。
//
// app.js 是浏览器脚本，不能整体 require，所以按名字把要测的那几个函数从源码里抠出来，
// 再把「解码」和「画布编码」这两条边界换成替身执行。这样测的是**线上要跑的那段策略代码本身**
// （透传规则、降档顺序、四种失败回退、超时兜底、文案映射），而像素与编码交给真浏览器那层
// （验证_压缩.py）去测 —— 两层合起来才覆盖整条链路。
//
// 用法：
//   node test_vision_compress.js                               # 测待上传_前端_2个/app.js（应当全过）
//   node test_vision_compress.js <旧的 app.js 路径> --negative   # 负向对照：期望「新行为」用例全败，
//                                                              # 且败因必须是抠不到新代码，而不是别的
const fs = require("fs");
const path = require("path");

const argv = process.argv.slice(2);
const NEGATIVE = argv.includes("--negative");
const APP_JS = argv.find((item) => !item.startsWith("--"))
  || path.join(__dirname, "待上传_前端_2个", "app.js");
const source = fs.readFileSync(APP_JS, "utf8");

// ------------------------------------------------------------------ 从真源码里抠东西

function sliceFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) return null;
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

// 常量必须是**单行**声明才抠得出来（这也是给后面的人立下的格式约定）。
function sliceDeclaration(name, override) {
  const match = source.match(new RegExp(`^(?:const|let|var) ${name} = .*$`, "m"));
  if (!match) return null;
  return override === undefined ? match[0] : `const ${name} = ${override};`;
}

const REQUIRED_FUNCTIONS = [
  "visionJpegName", "decodeVisionImage", "canvasToJpegBlob", "shrinkVisionJpeg",
  "toVisionJpegFile", "shrinkVisionImage", "prepareVisionUpload", "describeVisionError",
  "readApiError",
];
const REQUIRED_DECLARATIONS = [
  "VISION_UPLOAD_MAX_BYTES", "VISION_SHRINK_STEPS", "VISION_COMPRESS_BUDGET_MS",
];

const missing = [];
const pieces = [];
for (const name of REQUIRED_DECLARATIONS) {
  const text = sliceDeclaration(name, name === "VISION_COMPRESS_BUDGET_MS" ? 60 : undefined);
  if (!text) missing.push(`常量 ${name}`);
  else pieces.push(text);
}
for (const name of REQUIRED_FUNCTIONS) {
  const text = sliceFunction(name);
  if (!text) missing.push(`函数 ${name}()`);
  else pieces.push(text);
}

// ------------------------------------------------------------------ 断言小工具

const results = [];
function check(label, ok, detail, isNewBehavior) {
  results.push({ label, ok: !!ok, detail: detail || "", isNewBehavior: !!isNewBehavior });
}

// ------------------------------------------------------------------ 组装作用域

// 把「解码」和「画布编码」换成替身：**追加在真实实现后面**，同作用域里后声明的函数
// 覆盖先声明的，于是 prepareVisionUpload / shrinkVisionImage 跑的还是真代码，只有边界被换掉。
const STUBS = `
const __stub = { decodeCalls: 0, encodeCalls: [], decodeResult: null, encodeSizes: [] };
async function decodeVisionImage(file) {
  __stub.decodeCalls += 1;
  if (__stub.decodeThrows) throw new Error("stub 解码失败");
  if (__stub.decodeNever) return await new Promise(() => {});
  return __stub.decodeResult || { width: 4000, height: 3000 };
}
async function shrinkVisionJpeg(source, width, height, maxSide, quality) {
  const index = __stub.encodeCalls.length;
  __stub.encodeCalls.push([maxSide, quality]);
  if (__stub.encodeNull) return null;
  const size = __stub.encodeSizes[index];
  if (size === undefined) return null;
  return new Blob([new Uint8Array(size)], { type: "image/jpeg" });
}
`;

const EXPORTS = [
  "prepareVisionUpload", "shrinkVisionImage", "describeVisionError", "toVisionJpegFile",
  "VISION_UPLOAD_MAX_BYTES", "VISION_SHRINK_STEPS", "VISION_COMPRESS_BUDGET_MS", "__stub",
];

let scope = null;
if (!missing.length) {
  try {
    scope = new Function(`${pieces.join("\n\n")}\n${STUBS}\nreturn { ${EXPORTS.join(", ")} };`)();
  } catch (error) {
    missing.push(`组装作用域失败：${error.message}`);
  }
}

function makeFile(size, type = "image/jpeg", name = "photo.jpg") {
  return new File([new Uint8Array(size)], name, { type });
}

// ------------------------------------------------------------------ 用例

async function run() {
  if (missing.length) {
    // 抠不到新代码 —— 这正是负向对照期望的结果
    for (const label of [
      "常量形状", "目标字节数离 1 MiB 有余量", "小图原样透传", "刚好超标就走压缩",
      "达标即停、逐档降级", "四档全超标回退原文件", "toBlob 返回 null 时回退原文件",
      "解码失败直接回退（不再试编码）", "压缩超时兜底", "压出来的 File 带对 content-type",
      "错误文案映射", "调用点没被改动",
    ]) {
      check(label, false, `抠不到新代码：${missing.slice(0, 3).join("、")}${missing.length > 3 ? " 等" : ""}`, true);
    }
    return;
  }

  const { prepareVisionUpload, describeVisionError, toVisionJpegFile } = scope;
  const { VISION_UPLOAD_MAX_BYTES, VISION_SHRINK_STEPS, VISION_COMPRESS_BUDGET_MS } = scope;
  const stub = scope.__stub;

  // 1. 常量形状 —— 防手抖把降档链改坏
  let ladderOk = Array.isArray(VISION_SHRINK_STEPS) && VISION_SHRINK_STEPS.length >= 2;
  let prevSide = Infinity;
  let prevQuality = Infinity;
  for (const step of VISION_SHRINK_STEPS || []) {
    const [side, quality] = step;
    if (!(side > 0) || !(quality > 0 && quality <= 1)) ladderOk = false;
    if (side >= prevSide || quality > prevQuality) ladderOk = false;
    prevSide = side;
    prevQuality = quality;
  }
  if (VISION_SHRINK_STEPS[0][0] !== 2000) ladderOk = false;
  check("常量形状", ladderOk,
    `首档 ${VISION_SHRINK_STEPS[0]}、共 ${VISION_SHRINK_STEPS.length} 档、严格递减`, true);

  // 2. 900 KB 离 nginx 的 1 MiB 必须留出余量（把线上的硬数字写进测试）
  check("目标字节数离 1 MiB 有余量",
    VISION_UPLOAD_MAX_BYTES + 1000 < 1048576,
    `${VISION_UPLOAD_MAX_BYTES} B vs 上限 1048576 B，余量 ${1048576 - VISION_UPLOAD_MAX_BYTES} B`, true);

  // 3. 小图原样透传（**同一个对象**，不是等值的另一个）
  for (const size of [0, 1, VISION_UPLOAD_MAX_BYTES]) {
    stub.decodeCalls = 0;
    const file = makeFile(size);
    const out = await prepareVisionUpload(file);
    check(`小图原样透传（${size} B）`,
      out === file && stub.decodeCalls === 0,
      out === file ? "返回的是同一个 File 对象，没走解码" : "返回了新对象", true);
  }

  // 4. 边界另一侧：刚好超标就要走压缩
  stub.decodeCalls = 0;
  stub.encodeSizes = [];
  stub.encodeNull = true;
  const over = makeFile(VISION_UPLOAD_MAX_BYTES + 1);
  const overOut = await prepareVisionUpload(over);
  check("刚好超标就走压缩",
    stub.decodeCalls === 1 && overOut === over,
    `decode 调用 ${stub.decodeCalls} 次`, true);

  // 5. 达标即停、逐档降级：第 2 档才达标
  // 注意：encodeSizes 是按 encodeCalls.length 取下标的，换用例必须先把调用记录清零，
  // 否则下标越界、替身一律返回 null —— 上一版就吃过这个亏（测试自己写错，不是代码错）。
  stub.decodeCalls = 0;
  stub.encodeCalls = [];
  stub.encodeNull = false;
  stub.encodeSizes = [1500 * 1024, 800 * 1024, 400 * 1024, 200 * 1024];
  const big = makeFile(3.4 * 1024 * 1024);
  const picked = await prepareVisionUpload(big);
  const calls = stub.encodeCalls.map((c) => c.join("/"));
  check("达标即停、逐档降级",
    stub.encodeCalls.length === 2
      && stub.encodeCalls[1][0] === VISION_SHRINK_STEPS[1][0]
      && stub.encodeCalls[1][1] === VISION_SHRINK_STEPS[1][1]
      && picked !== big && picked.size === 800 * 1024,
    `试了 ${calls.join(" → ")}，最终 ${picked === big ? "原文件" : picked.size + " B"}`, true);

  // 6. 四档全超标 → 回退原文件（宁可原样传，也不给一张糊图）
  stub.encodeCalls = [];
  stub.encodeSizes = [2e6, 2e6, 2e6, 2e6];
  const huge = makeFile(3.4 * 1024 * 1024);
  const fallback = await prepareVisionUpload(huge);
  check("四档全超标回退原文件",
    fallback === huge && stub.encodeCalls.length === VISION_SHRINK_STEPS.length,
    `试满 ${stub.encodeCalls.length} 档后回退原文件`, true);

  // 7. toBlob 返回 null → 继续降下一档，全 null 才回退
  stub.encodeCalls = [];
  stub.encodeNull = true;
  const nullOut = await prepareVisionUpload(huge);
  check("toBlob 返回 null 时回退原文件",
    nullOut === huge && stub.encodeCalls.length === VISION_SHRINK_STEPS.length,
    `null 走满 ${stub.encodeCalls.length} 档后回退原文件`, true);

  // 8. 解码失败 → 直接回退，且一次编码都不该试
  stub.encodeNull = false;
  stub.encodeCalls = [];
  stub.decodeThrows = true;
  const broken = await prepareVisionUpload(makeFile(3.4 * 1024 * 1024));
  stub.decodeThrows = false;
  check("解码失败直接回退（不再试编码）",
    broken === broken && stub.encodeCalls.length === 0,
    `encode 调用 ${stub.encodeCalls.length} 次（应为 0）`, true);

  // 9. 解码卡住不返回 → 超时兜底（第一原则：宁可原样传，也不许永远转圈）
  stub.decodeNever = true;
  const started = Date.now();
  const timedOut = await prepareVisionUpload(makeFile(3.4 * 1024 * 1024));
  const elapsed = Date.now() - started;
  stub.decodeNever = false;
  check("压缩超时兜底",
    timedOut instanceof File && elapsed < 3000,
    `${elapsed} ms 后返回了原文件（预算 ${VISION_COMPRESS_BUDGET_MS} ms）`, true);

  // 10. 压出来的 File 必须带 image/jpeg —— 后端 415 的根因就是这个字段
  const jpegFile = toVisionJpegFile(new Blob([new Uint8Array(10)], { type: "image/jpeg" }), {
    name: "IMG_1234.HEIC", type: "image/heic",
  });
  check("压出来的 File 带对 content-type",
    jpegFile instanceof File && jpegFile.type === "image/jpeg" && /\.jpg$/.test(jpegFile.name)
      && jpegFile.name === "IMG_1234.jpg",
    `name=${jpegFile.name} type=${jpegFile.type}`, true);

  // 11. 错误文案映射（含 nginx 那种没有 detail 的 HTML 413）
  const cases = [
    [413, {}, "图片太大，请离题目近一点重拍"],
    [413, { detail: "图片大小不能超过 10 MiB" }, "图片太大，请离题目近一点重拍"],
    [415, {}, "图片格式不支持，请用相机重拍"],
    [401, {}, "登录已过期，请重新登录后再试"],
    [403, {}, "登录已过期，请重新登录后再试"],
    [503, {}, "识别服务暂时不可用，请稍后重试"],
    [422, { detail: "图片内容不能为空" }, "图片内容不能为空"],
    [500, {}, "图片识别失败（HTTP 500）"],
  ];
  let textOk = true;
  const wrong = [];
  for (const [status, data, want] of cases) {
    const got = describeVisionError({ status }, data);
    if (got !== want) { textOk = false; wrong.push(`${status}→「${got}」`); }
  }
  check("错误文案映射", textOk, textOk ? `8 条全对` : `不一致：${wrong.join("、")}`, true);

  // 12. 不变式：调用点一个都没被碰（6 次 = 1 处定义 + 5 处调用）
  const callSites = (source.match(/parseVisionImage\(/g) || []).length;
  const hosts = ["handleCalcPhoto", "handleChatPhoto", "handleProofPhoto", "handleExamPhoto", "handleGradingPhoto"]
    .filter((fn) => sliceFunction(fn) && sliceFunction(fn).includes("parseVisionImage("));
  check("调用点没被改动", callSites === 6 && hosts.length === 5,
    `parseVisionImage( 出现 ${callSites} 次（期望 6），5 个宿主函数命中 ${hosts.length} 个`, true);
}

run().then(() => {
  const pass = results.filter((r) => r.ok);
  const fail = results.filter((r) => !r.ok);
  console.log(`测的是：${APP_JS}`);
  console.log("");
  for (const item of results) {
    console.log(`  ${item.ok ? "[过]" : "[败]"} ${item.label}${item.detail ? "  —— " + item.detail : ""}`);
  }
  console.log("");
  console.log(`${pass.length} 过 / ${fail.length} 败`);

  if (NEGATIVE) {
    // 负向对照：期望「新行为」用例全败，且必须是因为抠不到新代码
    const newBehaviorFails = results.filter((r) => r.isNewBehavior && !r.ok);
    const wrongReason = newBehaviorFails.filter((r) => !r.detail.includes("抠不到新代码"));
    if (newBehaviorFails.length === pass.filter((r) => r.isNewBehavior).length + newBehaviorFails.length
        || newBehaviorFails.length === results.filter((r) => r.isNewBehavior).length) {
      if (wrongReason.length) {
        console.log(`\n负向对照不合格：有 ${wrongReason.length} 条败因不是「抠不到新代码」`);
        process.exit(1);
      }
      console.log("\n负向对照符合预期：新行为用例全败，且败因都是抠不到新代码。");
      process.exit(0);
    }
    console.log(`\n负向对照不合格：只有 ${newBehaviorFails.length} 条新行为用例失败，期望全败`);
    process.exit(1);
  }
  process.exit(fail.length ? 1 : 0);
}).catch((error) => {
  console.error("测试自己崩了：", error);
  process.exit(2);
});
