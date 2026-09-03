# -*- coding: utf-8 -*-
"""队员2 · 知识库微调数据：由四层库 + 平台图谱 + 题库语料生成微调指令集。

语料来源（全部为教材/教师权威内容，模板只改写问法、不改内容）：
  A. data/teacher_kg.json            四层库结构（19章/73节/150K/376P + pre/next）
  B. backend/kb/router.py KG_DATA    平台图谱 157 节点卡片（教材提炼的定义/定理/规则短文）
  C. data/documents/概念题库.md       32 条 Q/A
  D. data/documents/选择题题库.md     34 条选择题（答案+解析）
  E. data/documents/老师训练题库.json 112 题（q/kp/a）+ 节点映射 json
  F. data/documents/证明题库_*.md     27 道证明题（题目+完整证明）
  G. 符号表/推理规则（标准数学符号含义，逐条教材口径）
  H. data/documents/北大教材/第1部分chap1-3.md 等课件 OCR（短句教材事实，仅作"教材一致"正例）

输出（data/finetune/）：
  知数明析_指令集.jsonl          每行 {"messages":[{role:system|user|assistant}…]}
  知数明析_指令集_triplet.jsonl  每行 {"system":…,"user":…,"assistant":…}
  知数明析_星辰知识库.md         星辰 Agent 知识库导入用（按 9 模块组织）
  数据审计.md                    来源行数/符号统一统计/去重统计/未收录符号清单
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "documents"
OUT = ROOT / "data" / "finetune"
OUT.mkdir(parents=True, exist_ok=True)

from backend.kb.router import KG_DATA  # noqa: E402

SYS = ("你是“知数明析”离散数学课程的助教小微。回答要求：1) 数学符号尽量使用标准 Unicode 写法"
       "（∀ ∃ ∧ ∨ ¬ → ↔ ≡ ⊨ ⊢ ⊆ ∈ ∪ ∩ × ∅ ℕ ℤ ℝ ℚ）；若题目本身以 LaTeX 给出，"
       "公式可保留 LaTeX 原样；2) 先给结论，再给必要步骤；3) 针对学生的具体问题回答，"
       "不要长篇铺陈；4) 教材未涉及的内容明确说明“教材未涉及”，不要编造。")

# ---------------------------------------------------------------- 符号规范化
# 支持一层嵌套的花括号体（如 \frac{(2k)!}{2^{k}·…}、\sqrt{\sqrt{x}+1}）
_BRA = r"((?:[^{}]|\{[^{}]*\})*)"
SYMB_MAP = [
    (r"\\underline\{\\quad\}", "____"),
    (r"\\underline\{" + _BRA + r"\}", r"\1"),
    (r"\\operatorname\{card\}", "card"),
    (r"\\operatorname\{" + _BRA + r"\}", r"\1"),
    (r"\\mathrm\{" + _BRA + r"\}", r"\1"),
    (r"\\text\{" + _BRA + r"\}", r"\1"),
    (r"\\displaystyle(?![A-Za-z])", ""), (r"\\left(?![A-Za-z])", ""),
    (r"\\right(?![A-Za-z])", ""),
    (r"\\subseteq", "⊆"),
    (r"\\subset", "⊂"),
    (r"\\emptyset", "∅"), (r"\\varnothing", "∅"),
    (r"\\mathbb\{N\}", "ℕ"), (r"\\mathbb\{Z\}", "ℤ"),
    (r"\\mathbb\{R\}", "ℝ"), (r"\\mathbb\{Q\}", "ℚ"),
    (r"\\mathbb\{" + _BRA + r"\}", r"\1"),
    (r"\\forall", "∀"), (r"\\exists", "∃"), (r"\\neg", "¬"),
    (r"\\land", "∧"), (r"\\lor", "∨"), (r"\\wedge", "∧"), (r"\\vee", "∨"),
    (r"\\to", "→"),
    (r"\\leftrightarrow", "↔"), (r"\\Leftrightarrow", "↔"), (r"\\Rightarrow", "⇒"),
    (r"\\equiv", "≡"), (r"\\models", "⊨"), (r"\\vdash", "⊢"),
    (r"\\in", "∈"), (r"\\notin", "∉"), (r"\\cup", "∪"), (r"\\cap", "∩"),
    (r"\\times", "×"), (r"\\leq", "≤"), (r"\\geq", "≥"), (r"\\neq", "≠"),
    (r"\\langle", "⟨"), (r"\\rangle", "⟩"), (r"\\restriction", "↾"),
    (r"\\Sigma", "Σ"), (r"\\Delta", "Δ"), (r"\\delta", "δ"), (r"\\chi", "χ"),
    (r"\\omega", "ω"), (r"\\alpha", "α"), (r"\\beta", "β"), (r"\\pi", "π"),
    (r"\\aleph", "ℵ"), (r"\\infty", "∞"), (r"\\pm", "±"), (r"\\sim", "~"),
    (r"\\kappa", "κ"), (r"\\lambda", "λ"), (r"\\Gamma", "Γ"), (r"\\gamma", "γ"),
    (r"\\preceq", "≼"), (r"\\prec", "≺"),
    (r"\\notin", "∉"), (r"\\not", "¬"),
    (r"\\dfrac\{" + _BRA + r"\}\{" + _BRA + r"\}", r"\1/\2"),
    (r"\\bar\{" + _BRA + r"\}", r"\1̄"),
    (r"\\max", "max"), (r"\\min", "min"),
    (r"\\cos", "cos"), (r"\\sin", "sin"), (r"\\log", "log"),
    (r"\\\{", "{"), (r"\\\}", "}"),
    (r"\\quad", " "),
    (r"<br\s*/?>", " "),
    (r"\\circ", "∘"), (r"\\grad", "∇"), (r"\\sum", "∑"), (r"\\prod", "∏"),
    (r"\\cdots", "…"), (r"\\dots", "…"),
    (r"\\gcd", "gcd"), (r"\\lcm", "lcm"), (r"\\pmod", "mod"),
    (r"\\frac\{" + _BRA + r"\}\{" + _BRA + r"\}", r"\1/\2"),
    (r"\\binom\{" + _BRA + r"\}\{" + _BRA + r"\}", r"C(\1,\2)"),
    (r"\\sqrt\{" + _BRA + r"\}", r"√\1"),
    (r"\\cdot", "·"), (r"\\ast", "·"), (r"\\star", "∗"),
    (r"\\mid", "|"), (r"\\bmod", "mod"), (r"\\mod", "mod"),
    (r"\\lfloor", "⌊"), (r"\\rfloor", "⌋"), (r"\\lceil", "⌈"), (r"\\rceil", "⌉"),
]
LATEX_CMD = re.compile(r"\\[a-zA-Z]+")
_UNCONVERTED = Counter()


def norm_symbols(text: str) -> str:
    """LaTeX/ASCII → 标准 Unicode；含表格环境或未收录命令则整体保留原样。"""
    if not text:
        return text
    if r"\begin" in text or r"\end" in text:
        _UNCONVERTED[text[:40]] += 1  # 表格/矩阵环境，不做机械转换
        return text
    t = re.sub(r"(?<!\\)\$", "", text)
    t = re.sub(r"\\underline\{\\quad\}", "____", t)  # 填空占位符优先于通用 underline
    # 长命令优先，避免 \in 吃掉 \infty、\mid 吃掉 \min 等前缀冲突；
    # 每模式迭代到不再匹配（处理嵌套 \sqrt{\sqrt{…}}、\frac{\frac{…}}）
    for pat, rep in sorted(SYMB_MAP, key=lambda p: -len(p[0])):
        while True:
            t2 = re.sub(pat, rep, t)
            if t2 == t:
                break
            t = t2
    t = re.sub(r"[？?]{2,}", "？", t)
    t = re.sub(r"[！!]{2,}", "！", t)
    if LATEX_CMD.search(t):
        _UNCONVERTED[text[:40]] += 1
        return text
    return t


def dedup_key(q: str, a: str) -> str:
    return re.sub(r"[\s，。！？、.?!:：;,；;（）()【】\[\]`'\"“”\"\\\$-]", "", q + "||" + a)


def safe_head(q: str, n: int = 160) -> str:
    """提取题目开头摘要（约 n 字）：不在 $...$ 公式中间、不残留半截 LaTeX 命令，优先在句读处断开。

    规则：1) 若第 n 字落在未闭合的 $…$ 内，延伸到该公式结束；
          2) 尾部若有半个命令（如 \fra）去掉；
          3) 再退到最近的中文句读（。；？，）。
    """
    if len(q) <= n + 10:
        return q
    i = n
    if q[:i].count("$") % 2 == 1:          # 截断点在数学区间内
        nxt = q.find("$", i)
        if nxt != -1:
            i = nxt + 1
    tail = re.search(r"\\[a-zA-Z]*$", q[:i])
    if tail:                                # 去掉半截命令
        i = tail.start()
    for ch in ("。", "；", "？", "，", "！"):   # 注意：不用 "!"，会撞上公式里的阶乘号
        idx = q.rfind(ch, 40, i)
        if idx != -1:
            return q[: idx + 1]
    return q[:i]


# ---------------------------------------------------------------- 语料加载
def load_concept_qa(docs: Path) -> list:
    txt = docs.joinpath("概念题库.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    pairs, cur, buf = [], None, []
    for line in txt.splitlines():
        m = re.match(r"\*\*Q(\d+)[：:]\s*(.+?)\*\*\s*$", line.strip())
        if m:
            if cur and buf:
                pairs.append((cur, "\n".join(buf).strip()))
            cur, buf = m.group(2).strip(), []
            continue
        if cur is not None:
            am = re.match(r"^A[：:]\s*(.*)$", line.strip())
            if am:
                buf.append(am.group(1).strip())
            elif buf:
                buf.append(line.strip())
    if cur and buf:
        pairs.append((cur, "\n".join(buf).strip()))
    return [(q, a) for q, a in pairs if q and a]


def load_mc(docs: Path) -> list:
    txt = docs.joinpath("选择题题库.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    items, cur = [], {}
    for line in txt.splitlines():
        s = line.strip()
        m = re.match(r"\*\*Q\d+\*\*\s*(.*)$", s)
        if m:
            if cur.get("q"):
                items.append(cur)
            cur = {"q": m.group(1).strip()}
            continue
        if not cur.get("q"):
            continue
        om = re.match(r"^([A-D])[．.、]\s*(.+)$", s)
        if om:
            cur.setdefault("opts", {})[om.group(1)] = om.group(2).strip()
            continue
        if re.match(r"^答案[:：]", s):
            cur["ans"] = s.split("答案")[-1].lstrip(":： ").strip()
            continue
        if re.match(r"^解析[:：]", s):
            cur["exp"] = s.split("解析")[-1].lstrip(":： ").strip()
            continue
    if cur.get("q"):
        items.append(cur)
    return items


def load_exams(docs: Path) -> list:
    data = json.load(open(docs / "老师训练题库.json", encoding="utf-8"))
    rows = []
    for ex in data["exams"]:
        for kind in ("fill", "calc", "proof", "app"):
            for i, item in enumerate(ex.get(kind) or [], 1):
                if item.get("q") and item.get("a"):
                    rows.append((f"{ex['id']}-{kind}-{i}", item["q"], item["a"], item.get("kp", "")))
    return rows


def load_proofs(docs: Path) -> list:
    rows = []
    for f in sorted(docs.glob("证明题库_*.md")):
        txt = f.read_text(encoding="utf-8").replace("\r\n", "\n")
        blocks = re.split(r"^##\s+证明题\d+[：:]\s*(.+?)\s*$", txt, flags=re.M)
        for i in range(1, len(blocks) - 1, 2):
            title, body = blocks[i].strip(), blocks[i + 1]
            qm = re.search(r"\*\*题目\*\*[：:]\s*(.+)", body)
            pm = re.search(r"\*\*证明\*\*：\s*(.+?)(?=\n\*\*技巧\*\*|\n##|\Z)", body, re.S)
            if not qm or not pm:
                continue
            proof = re.sub(r"\s+", " ", pm.group(1)).strip()
            rows.append((qm.group(1).strip(), proof, title))
    return rows


def load_ocr_facts(docs: Path, cap: int = 150) -> list:
    """课件 OCR 中的教材短句（≤45字、无乱码）→ 教材一致的正例事实。"""
    facts = []
    seen = set()
    for f in sorted(docs.joinpath("北大教材").glob("第*部分*.md")):
        txt = f.read_text(encoding="utf-8").replace("\r\n", "\n")
        for line in txt.splitlines():
            s = line.strip()
            if not (6 <= len(s) <= 45):
                continue
            if re.search(r"[#*|\\{}\[\]]", s) or re.search(r"[a-zA-Z]{4,}", s):
                continue
            if re.fullmatch(r"[\d\s.、：:（）()\[\]，,]+", s):
                continue
            if re.match(r"^(例|图|表|注|第|习题|解[:：]|答案[:：]|考点|重点)", s):
                continue
            # OCR 编号标签（定义：2.3.2 等）
            if re.match(r"^(定义|定理|命题|推论|引理|性质|注意)\s*[:：]\s*[\d.]+", s):
                continue
            # 句子型筛选：只留有谓语的陈述句，标题/术语（如“集合运算的性质”）跳过
            if not re.search(r"是|若|则|求|指|设|由|可|为|都|也|且|仅|称|相|等|不|定义|证明|属于|对于|按照", s):
                continue
            # 纯汉语标题兜底：如“1.3 集合运算的性质”“性质（续）”
            if re.fullmatch(r"[\d. ]*[一-鿿（）续]{2,16}", s):
                continue
            if s in seen:
                continue
            seen.add(s)
            facts.append(s)
            if len(facts) >= cap:
                return facts
    return facts


# ---------------------------------------------------------------- 图谱数据
def kg_items():
    out = {}
    for m in KG_DATA["modules"]:
        for c in m["children"]:
            for it in c["items"]:
                out[it["node_id"]] = (m["name"], c["name"], it["type"], it["text"])
    return out


def load_kg_struct():
    kg = json.load(open(ROOT / "data" / "teacher_kg.json", encoding="utf-8"))
    kp_by_id = {}
    chapters = []
    for ch in kg["chapters"]:
        sections = []
        for s in ch["sections"]:
            kps = []
            for k in s["kps"]:
                kp_by_id[k["id"]] = k["title"]
                kps.append({"id": k["id"], "title": k["title"],
                            "points": [p["title"] for p in k["points"]],
                            "pre": k.get("pre", []), "next": k.get("next", [])})
            sections.append({"id": s["id"], "title": s["title"], "kps": kps})
        chapters.append({"id": ch["id"], "title": ch["title"], "sections": sections})
    return chapters, kp_by_id


# ---------------------------------------------------------------- 模板生成
# 每条 = (kind, source_id, [user 变体…], answer)：同一答句搭配多种问法（内容不变）
def main():
    chapters, kp_by_id = load_kg_struct()
    items = kg_items()
    qa_c = load_concept_qa(DOCS)
    mc = load_mc(DOCS)
    exams = load_exams(DOCS)
    proofs = load_proofs(DOCS)
    facts = load_ocr_facts(DOCS)
    node_map = json.load(open(DOCS / "老师训练题库_node_id.json", encoding="utf-8"))["questions"]
    print(f"概念QA {len(qa_c)} | 选择 {len(mc)} | 题库 {len(exams)} | 证明 {len(proofs)} | "
          f"OCR短句 {len(facts)} | 图谱节点 {len(items)}")

    rows = []
    stats = Counter()

    def emit(kind, sid, us, answer):
        for u in us:
            rows.append((kind, sid, u, answer))
        stats[kind] += len(us)

    # 1. 概念问答（32×4）
    for i, (q, a) in enumerate(qa_c):
        emit("concept_qa", f"concept-{i}", [
            f"问题：{q}", f"请解释：{q}", f"{q}（简答）", f"学生提问：{q}，请回答。"], a)
    # 2. 选择题讲解（34×4）
    for i, m in enumerate(mc):
        opts = "；".join(f"{k}、{v}" for k, v in m.get("opts", {}).items())
        exp = m.get("exp") or "详见选项解析。"
        ans = m.get("ans", "")
        full = f"正确答案：{ans}。{exp}"
        emit("mc", f"mc-{i}", [
            f"选择题：{m['q']}\n选项：{opts}\n请给出正确答案并说明理由。",
            f"单选题：{m['q']}？",
            f"解析这道选择题：{m['q']}（选项：{opts}）",
            f"下列正确的是？{m['q']}\n选项：{opts}"], full)
    # 3. 老师题库（112×4）
    for qid, q, a, kp in exams:
        node = node_map.get(qid, {}).get("node_id", "")
        tag = f"知识点：{kp}（图谱节点 {node}）" if kp else ""
        answer = f"{a}\n{tag}".strip()
        emit("teacher", qid, [
            f"题目：{q}\n请解答。", f"请完成：{q}", f"{q}\n\n请给出答案与依据。",
            f"讲解本题：{q}"], answer)
    # 4. 证明题（27×4）
    for i, (stmt, proof, title) in enumerate(proofs):
        s = stmt[2:] if stmt.startswith("证明") else stmt  # 标题自带"证明"时不重复
        answer = f"{proof}\n（{title}）"
        emit("proof", f"proof-{i}", [
            f"证明：{s}", f"请证明：{s}", f"{s}\n\n请写出完整证明过程。",
            f"用教材方法证明：{s}"], answer)
    # 5. 图谱卡片（157×4）
    for nid, (mod, conc, typ, text) in items.items():
        name = text.split("：")[0]
        emit("kg_card", nid, [
            f"什么是“{name}”？请按教材给出定义/要点。",
            f"请讲解“{name}”。", f"知识点卡：{name}",
            f"考试前快速复习：“{name}”。"], text)
    # 6. 知识点结构（150×3）
    for ch in chapters:
        for s in ch["sections"]:
            for k in s["kps"]:
                pts = "；".join(f"「{p}」" for p in k["points"])
                locate = f"「{k['title']}」属于 {ch['title']} 的“{s['title']}”，教材要点：{pts}。"
                emit("kp_struct", k["id"], [
                    f"请讲解知识点：{k['title']}", f"教材中“{k['title']}”讲什么？",
                    f"帮我梳理“{k['title']}”的要点。"], locate)
    # 7. 前置/后继（150×2）
    for ch in chapters:
        for s in ch["sections"]:
            for k in s["kps"]:
                pre = "、".join(f"「{kp_by_id[p]}」" for p in k["pre"] if p in kp_by_id) or "无专门前置"
                nxt = "、".join(f"「{kp_by_id[n]}」" for n in k["next"] if n in kp_by_id) or "无后继要求"
                emit("pre_next", k["id"], [
                    f"学习「{k['title']}」之前需要先掌握什么？", f"前置知识提示：{k['title']}"],
                    f"前置知识：{pre}。")
                emit("pre_next", k["id"], [
                    f"学完「{k['title']}」之后应当接着学什么？", f"后续学习建议：{k['title']}"],
                    f"后续知识：{nxt}。")
    # 8. 节级概述（73×2）
    for ch in chapters:
        for s in ch["sections"]:
            kps = "、".join(k["title"] for k in s["kps"])
            answer = f"「{s['title']}」属于{ch['title']}，涵盖：{kps}。"
            emit("section", s["id"], [
                f"请概述「{s['title']}」的主要内容。", f"「{s['title']}」一节有哪些知识点？"], answer)
    # 9. 符号表（27×4）
    SYMBOLS = [
        ("∀", "全称量词，表示“对所有……成立”。"),
        ("∃", "存在量词，表示“存在……使得……”。"),
        ("∧", "合取（逻辑与），P∧Q 当且仅当 P、Q 都真时为真。"),
        ("∨", "析取（逻辑或），P∨Q 当且仅当 P、Q 至少一个为真时为真。"),
        ("¬", "否定，¬P 与 P 真值相反。"),
        ("→", "蕴含，P→Q 仅在 P 真 Q 假时为假。"),
        ("↔", "等价（双条件），P↔Q 在 P、Q 真值相同时为真。"),
        ("≡", "逻辑等价：两个公式在所有赋值下真值相同。"),
        ("⊨", "逻辑蕴含：前件为真时后件必真。"),
        ("⊢", "推出/可证：从前提可推出结论。"),
        ("⊆", "包含于：A 的所有元素都属于 B。"),
        ("⊂", "真包含于：A 是 B 的子集且 A≠B。"),
        ("∈", "属于：元素与集合的归属关系。"),
        ("∉", "不属于。"),
        ("∪", "并集：属于 A 或属于 B 的元素集合。"),
        ("∩", "交集：同时属于 A 和 B 的元素集合。"),
        ("×", "笛卡尔积：A×B={(a,b) | a∈A, b∈B}。"),
        ("∅", "空集：不含任何元素的集合。"),
        ("ℕ", "自然数集。"),
        ("ℤ", "整数集。"),
        ("ℝ", "实数集。"),
        ("ℚ", "有理数集。"),
        ("Δ", "（图论）最大度：图中顶点度数的最大值。"),
        ("δ", "（图论）最小度：图中顶点度数的最小值。"),
        ("card A", "集合 A 的基数（元素个数）。"),
        ("Kₙ", "完全图：每两个顶点之间都有一条边的简单图。"),
        ("deg(v)", "顶点 v 的度：与 v 关联的边数。"),
    ]
    for i, (sym, mean) in enumerate(SYMBOLS):
        emit("symbol", f"sym-{i}", [
            f"符号「{sym}」在离散数学中表示什么？", f"「{sym}」是什么意思？",
            f"解释符号 {sym}。", f"离散数学中 {sym} 的读法与含义？"],
            f"{sym}：{mean}")
    # 10. LaTeX→Unicode 规范化练习（真实转换差值；×2 问法）
    for qid, q, a, kp in exams:
        cq = norm_symbols(q)
        if cq != q:
            emit("canon", qid, [
                f"请把下面题目中的数学符号改写为规范写法：\n{q}",
                f"符号规范化：{q}"], cq)
    # 11. 图谱节点溯源（112×2）
    for qid, q, a, kp in exams:
        node = node_map.get(qid, {}).get("node_id", "")
        if node:
            answer = f"对应知识点：{kp}，图谱节点 {node}。"
            hq = safe_head(q, 160)
            emit("trace", qid, [
                f"这道题对应教材哪个知识点？\n{hq}",
                f"请标注下面题目的知识点：{hq}"], answer)
    # 12. 模块导览（9×4）
    for m in KG_DATA["modules"]:
        names = "、".join(c["name"] for c in m["children"][:6])
        answer = f"「{m['name']}」模块覆盖：{names} 等。"
        emit("module", m["id"], [
            f"「{m['name']}」模块学什么？", f"“{m['name']}”涉及哪些内容？",
            f"复习「{m['name']}」。", f"请介绍「{m['name']}」模块的结构。"], answer)
    # 13. 概念卡（44×3）：每概念包含哪些子节点
    for m in KG_DATA["modules"]:
        for c in m["children"]:
            cards = "；".join(i["text"].split("：")[0] for i in c["items"])
            answer = f"「{c['name']}」（{m['name']}模块）包含：{cards}。"
            emit("conc_card", c["node_id"], [
                f"「{c['name']}」包括哪些知识点？", f"展开“{c['name']}”。",
                f"概念梳理：{c['name']}"], answer)
    # 14. 章节学习顺序（19×2）
    for ch in chapters:
        seq = " → ".join(s["title"] for s in ch["sections"])
        emit("chapter_plan", ch["id"], [
            f"按什么顺序学习{ch['title']}？",
            f"请给出{ch['title']}各节的学习顺序。"], f"{ch['title']}学习顺序：{seq}。")
    # 15. 课件教材短句正例（≤150）
    for i, s in enumerate(facts):
        emit("fact_check", f"fact-{i}", [
            f"下面的说法与教材一致吗？{s}",
            f"判断：{s}"], f"一致。教材表述：{s}。")

    # ------------------------------------------------------------ 规范化与去重
    deduped, seen, dup = [], set(), 0
    conv_stats = Counter()
    for kind, sid, user, answer in rows:
        u = norm_symbols(user)
        a = norm_symbols(answer)
        if u != user:
            conv_stats["user"] += 1
        if a != answer:
            conv_stats["answer"] += 1
        key = dedup_key(u, a)
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        deduped.append((kind, sid, u, a))
    print(f"生成 {len(rows)} 条 → 去重后 {len(deduped)} 条（去重 {dup}），"
          f"符号规范化 user {conv_stats['user']}/answer {conv_stats['answer']}，"
          f"未转换原文 {sum(_UNCONVERTED.values())} 条")

    # ------------------------------------------------------------ 输出
    def dump_jsonl(path, make_line):
        with open(path, "w", encoding="utf-8") as f:
            for kind, sid, u, a in deduped:
                f.write(json.dumps(make_line(u, a), ensure_ascii=False) + "\n")

    dump_jsonl(OUT / "知数明析_指令集.jsonl",
               lambda u, a: {"messages": [
                   {"role": "system", "content": SYS},
                   {"role": "user", "content": u},
                   {"role": "assistant", "content": a}]})
    dump_jsonl(OUT / "知数明析_指令集_triplet.jsonl",
               lambda u, a: {"system": SYS, "user": u, "assistant": a})

    # 星辰知识库（③：按模块整理的 Markdown 语料）
    md = ["# 知数明析 · 离散数学知识库（星辰 Agent 知识库导入用）\n",
          "> 源自教材《数学基础》四层结构（19章/73节/150知识点/376要点）与教师题库。\n",
          "## 0. 符号说明\n"]
    for sym, mean in SYMBOLS:
        md.append(f"- {sym}：{mean}")
    md.append("\n## 1. 模块知识\n")
    for m in KG_DATA["modules"]:
        md.append(f"\n### {m['name']}\n")
        for c in m["children"]:
            md.append(f"\n#### {c['name']}\n")
            for it in c["items"]:
                md.append(f"- {it['text']}")
    md.append("\n## 2. 例题与解答\n")
    for qid, q, a, kp in exams:
        md.append(f"\n**{qid}**（{kp}）{q}\n\n答案：{a}")
    for i, (stmt, proof, title) in enumerate(proofs):
        md.append(f"\n**证明题{i+1}**：{stmt}\n\n证明：{proof}")
    (OUT / "知数明析_星辰知识库.md").write_text("\n".join(md), encoding="utf-8")

    # 审计报告
    audit = ["# 微调数据审计报告\n",
             f"- 生成 {len(rows)} 条，去重后 **{len(deduped)}** 条，去除重复 {dup} 条",
             f"- 符号规范化：user {conv_stats['user']} 条 / answer {conv_stats['answer']} 条；"
             f"含未收录 LaTeX 命令整体保持原样 {sum(_UNCONVERTED.values())} 条",
             f"- 各来源类型分布：{ {k: v for k, v in sorted(stats.items())} }\n",
             "## 未收录符号（保留原文，供人工扩充映射表）\n"]
    for s, n in _UNCONVERTED.most_common(20):
        audit.append(f"- {n}× {s!r}")
    (OUT / "数据审计.md").write_text("\n".join(audit), encoding="utf-8")
    print("[OK] 输出目录", OUT)
    print("类型分布:", dict(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
