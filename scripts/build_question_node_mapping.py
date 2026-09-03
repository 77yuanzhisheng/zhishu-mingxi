# -*- coding: utf-8 -*-
"""队员2 · 任务⑥：老师训练题库 112 题 全量挂 node_id（平台节点级）

匹配策略（由强到弱，候选池一律先按 kp 的模块家族过滤，杜绝跨模块语义污染）：
  1. contain_match —— 家族内平台节点名/章节名整词出现在题面
  2. semantic      —— 家族内本机 bge-small-zh-v1.5 语义相似度 >= SEM_THRESHOLD
                      （题面 vs 映射.md 88 条手工题面 + 平台家族节点 name+text）
  3. md_dice       —— 家族内映射.md 题面 bigram Dice >= 0.42
  4. kp_fallback   —— kp → KP_NODE（与 backend/practice/router.py 同步兜底）

输出：data/documents/老师训练题库_node_id.json
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows GBK 控制台兜底

BASE = Path("D:/挑战杯/zhishu-mingxi/data/documents")
KB_API = "http://127.0.0.1:8000/kb/knowledge-graph"
SEM_THRESHOLD = 0.55

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.kb.embedder import EmbeddingService

# 与 backend/practice/router.py 的 KP_NODE 保持同步（kp -> (module, moduleName, node_id)）
KP_NODE = {
    "prop-logic": ("propositional_logic", "命题逻辑", "pl_01_02"),
    "normal-form": ("propositional_logic", "命题逻辑", "pl_03_02"),
    "inference": ("propositional_logic", "命题逻辑", "pl_03_05"),
    "pred-logic": ("predicate_logic", "谓词逻辑", "fl_01_02"),
    "set-ops": ("set_theory", "集合论", "st_02_01"),
    "function": ("set_theory", "集合论", "st_05_01"),
    "cardinality": ("set_theory", "集合论", "st_06_01"),
    "ie-set": ("set_theory", "集合论", "st_04_01"),
    "relation": ("relations", "关系", "rel_01_01"),
    "graph-basic": ("graph_theory", "图论", "gt_01_01"),
    "connectivity": ("graph_theory", "图论", "gt_02_03"),
    "planar": ("graph_theory", "图论", "gt_05_01"),
    "hamilton": ("graph_theory", "图论", "gt_04_02"),
    "spanning-tree": ("graph_theory", "图论", "gt_04_04"),
    "coloring": ("graph_theory", "图论", "gt_06_09"),
    "digraph": ("graph_theory", "图论", "gt_01_01"),
    "gcd": ("number_theory", "初等数论", "nt_02_01"),
    "congruence": ("number_theory", "初等数论", "nt_03_01"),
    "combinatorics": ("combinatorics", "组合数学", "cm_01_01"),
    "inclusion-exclusion": ("set_theory", "集合论", "st_04_01"),
    "gen-func": ("combinatorics", "组合数学", "cm_06_01"),
    "recurrence": ("combinatorics", "组合数学", "cm_05_01"),
    "polya": ("algebraic_structure", "代数结构", "ag_06_02"),
    "algebra": ("algebraic_structure", "代数结构", "ag_02_01"),
    "group": ("algebraic_structure", "代数结构", "ag_04_02"),
    "semigroup": ("algebraic_structure", "代数结构", "ag_04_01"),
    "homomorphism": ("algebraic_structure", "代数结构", "ag_03_01"),
}

# module_id → node_id 前缀（与 KG_DATA 9 模块对齐）
MODULE_PREFIX = {
    "propositional_logic": "pl", "predicate_logic": "fl", "set_theory": "st",
    "induction": "mi", "relations": "rel", "graph_theory": "gt",
    "number_theory": "nt", "combinatorics": "cm", "algebraic_structure": "ag",
}


# 人工校准（human_calibrated，2026-09-03）：逐题核对后修正的挂载
OVERRIDES = {
    "1-fill-3": ("st_05_01", "特征函数=函数作为特殊关系"),
    "1-fill-4": ("gt_01_02", "Δ=δ=n-1 → 完全图"),
    "1-fill-5": ("gt_04_02", "哈密顿通路判定"),
    "1-fill-7": ("gt_05_06", "轮图对偶图"),
    "1-fill-8": ("cm_02_02", "方程整数解=隔板法组合计数"),
    "1-fill-14": ("fl_01_02", "∀x(F→G) 在解释I下的真值=全称量词"),
    "1-calc-4": ("nt_04_01", "一次同余方程的判定"),
    "1-calc-5": ("gt_03_01", "握手定理"),
    "1-calc-6": ("st_04_01", "容斥原理"),
    "1-calc-7": ("cm_05_02", "常系数线性齐次递推方程"),
    "2-fill-8": ("cm_01_02", "乘法法则"),
    "2-calc-5": ("gt_03_05", "邻接矩阵幂=路径计数"),
    "2-calc-6": ("cm_05_01", "递推方程建模"),
    "2-calc-7": ("ag_01_02", "运算的性质"),
    "3-fill-8": ("cm_02_01", "排列"),
    "4-calc-4": ("nt_05_02", "费马小定理"),
    "4-calc-6": ("cm_03_02", "组合恒等式"),
    # 第二轮核对（语义误挂修正）
    "1-fill-10": ("cm_02_01", "5颗全异色手镯=圆排列"),
    "1-app-1": ("gt_04_02", "游完4点回A最短路线=哈密顿回路"),
    "2-fill-3": ("st_06_01", "card B^A=|B|^|A| 基数乘方"),
    "2-fill-9": ("st_04_01", "错位置换D4=容斥原理"),
    "2-fill-10": ("st_05_02", "满射函数计数"),
    "2-app-1": ("gt_04_03", "哈夫曼编码=最优二叉树(树)"),
    "2-calc-4": ("nt_05_02", "123^1000个位数=欧拉定理"),
    "3-fill-1": ("st_06_01", "card{a,b}^N=2^ℵ0=连续统"),
    "3-fill-2": ("rel_01_01", "描述法枚举元素=二元关系定义"),
    "3-fill-7": ("gt_01_02", "补图边数=完全图边数−m"),
    "3-fill-14": ("pl_03_01", "蕴含式类型=重言式"),
    "3-calc-3": ("nt_04_01", "模逆元=一次同余方程"),
    "3-calc-7": ("cm_06_01", "生成函数求解分书问题"),
    "4-fill-1": ("st_06_02", "card P(N×N)=c 康托尔定理"),
    "4-fill-2": ("rel_01_01", "R(x)邻域=二元关系定义"),
    "4-fill-9": ("st_04_01", "重复排列约束=容斥"),
}

# 关键词锚定（教学锚点，家族内命中即挂载；顺序=特异性优先，越靠前越具体）
KW_RULES = {
    "pl": [
        ("主析取", "pl_03_02"), ("主合取", "pl_03_03"), ("析取范", "pl_03_02"), ("合取范", "pl_03_03"),
        ("重言式", "pl_03_01"), ("永真", "pl_03_01"), ("矛盾式", "pl_03_01"),
        ("假言三段论", "pl_03_07"), ("假言推理", "pl_03_05"), ("拒取", "pl_03_06"),
        ("归谬", "pl_03_08"), ("蕴含等价", "pl_02_03"), ("德摩根", "pl_02_02"),
        ("等值演算", "pl_02_03"), ("逻辑等价", "pl_02_04"), ("真值表", "pl_02_01"),
        ("联结词", "pl_01_02"),
    ],
    "fl": [
        ("量词否定", "fl_02_01"), ("否定律", "fl_02_01"), ("全称例示", "fl_02_02"),
        ("全称概括", "fl_02_03"), ("存在例示", "fl_02_04"),
        ("全称量词", "fl_01_02"), ("存在量词", "fl_01_03"), ("约束变元", "fl_01_04"),
        ("自由变元", "fl_01_04"), ("个体域", "fl_01_01"), ("谓词", "fl_01_01"),
    ],
    "st": [
        ("容斥", "st_04_01"), ("特征函数", "st_05_01"),
        ("单射", "st_05_02"), ("满射", "st_05_02"), ("双射", "st_05_02"),
        ("复合函数", "st_05_03"), ("反函数", "st_05_04"),
        ("基数", "st_06_01"), ("等势", "st_06_01"), ("康托尔", "st_06_02"),
        ("对称差", "st_02_04"), ("笛卡尔积", "st_02_05"), ("幂集", "st_01_03"),
        ("子集", "st_01_02"), ("并集", "st_02_01"), ("交集", "st_02_02"),
        ("差集", "st_02_03"), ("补集", "st_02_03"), ("分配律", "st_03_01"),
        ("吸收律", "st_03_03"), ("幂等律", "st_03_03"),
    ],
    "mi": [
        ("强归纳", "mi_02_01"), ("归纳步", "mi_01_02"), ("基础步", "mi_01_01"),
        ("整除", "mi_03_03"), ("归纳", "mi_01_01"),
    ],
    "rel": [
        ("反对称", "rel_02_05"), ("反自反", "rel_02_04"), ("自反", "rel_02_01"),
        ("等价类", "rel_03_02"), ("等价关系", "rel_03_01"), ("划分", "rel_03_03"),
        ("哈斯", "rel_04_02"), ("偏序", "rel_04_01"),
        ("上确界", "rel_04_05"), ("下确界", "rel_04_05"), ("上界", "rel_04_05"), ("下界", "rel_04_05"),
        ("极大元", "rel_04_04"), ("极小元", "rel_04_04"),
        ("对称", "rel_02_02"), ("传递", "rel_02_03"),
        ("关系矩阵", "rel_01_02"), ("定义域", "rel_01_03"), ("值域", "rel_01_03"),
        ("二元关系", "rel_01_01"),
    ],
    "gt": [
        ("握手", "gt_03_01"), ("奇度", "gt_03_02"), ("欧拉公式", "gt_05_02"),
        ("对偶", "gt_05_06"), ("库拉托夫斯基", "gt_05_04"), ("极大平面", "gt_05_05"),
        ("平面图", "gt_05_01"), ("哈密顿", "gt_04_02"), ("欧拉图", "gt_04_01"),
        ("着色", "gt_06_09"), ("色数", "gt_06_09"), ("匈牙利", "gt_06_08"),
        ("支配", "gt_06_01"), ("独立集", "gt_06_02"), ("覆盖", "gt_06_03"),
        ("匹配", "gt_06_04"), ("最小生成树", "gt_04_04"), ("生成树", "gt_04_04"),
        ("完全图", "gt_01_02"), ("二部图", "gt_01_03"), ("度", "gt_01_04"),
        ("邻接矩阵", "gt_03_05"), ("连通分量", "gt_02_04"), ("连通图", "gt_02_03"),
        ("欧拉回路", "gt_03_04"), ("欧拉路径", "gt_03_04"), ("相异结点", "gt_02_01"),
        ("回路", "gt_02_02"), ("通路", "gt_02_01"), ("路径", "gt_02_01"),
        ("树", "gt_04_03"),
    ],
    "nt": [
        ("一次同余", "nt_04_01"), ("中国剩余", "nt_04_02"), ("剩余类", "nt_03_02"),
        ("费马", "nt_05_02"), ("欧拉函数", "nt_05_01"), ("欧拉定理", "nt_05_02"),
        ("同余", "nt_03_01"), ("最大公因数", "nt_02_01"), ("最大公约数", "nt_02_01"),
        ("欧几里得", "nt_02_01"), ("辗转相除", "nt_02_01"),
        ("最小公倍", "nt_02_03"), ("互素", "nt_02_02"), ("整除", "nt_01_01"),
        ("试除", "nt_01_02"), ("素数", "nt_01_02"), ("质数", "nt_01_02"),
        ("算术基本", "nt_01_03"), ("标准分解", "nt_01_03"), ("正因子", "nt_01_03"),
        ("伪随机", "nt_06_01"), ("公钥", "nt_07_01"),
    ],
    "cm": [
        ("指数生成函数", "cm_06_03"), ("生成函数", "cm_06_01"),
        ("常系数线性齐次", "cm_05_02"), ("常系数线性非齐次", "cm_05_03"),
        ("主定理", "cm_05_05"), ("递推方程", "cm_05_01"), ("卡塔兰数", "cm_07_01"),
        ("卡特兰", "cm_07_01"), ("斯特林数", "cm_07_02"), ("多项式定理", "cm_04_01"),
        ("二项式定理", "cm_03_01"), ("组合恒等式", "cm_03_02"),
        ("乘法法则", "cm_01_02"), ("加法法则", "cm_01_01"),
        ("排列", "cm_02_01"), ("组合数", "cm_02_02"),
    ],
    "ag": [
        ("半群", "ag_04_01"), ("独异点", "ag_04_01"), ("循环群", "ag_06_01"),
        ("置换群", "ag_06_02"), ("拉格朗日", "ag_05_02"), ("陪集", "ag_05_02"),
        ("子群", "ag_05_01"), ("布尔代数", "ag_08_02"), ("群同构", "ag_03_02"),
        ("同构", "ag_03_02"), ("同态", "ag_03_01"), ("代数系统", "ag_02_01"),
        ("单位元", "ag_01_03"), ("零元", "ag_01_03"), ("逆元", "ag_01_03"),
        ("交换律", "ag_01_02"), ("结合律", "ag_01_02"), ("幂等律", "ag_01_02"),
        ("分配律", "ag_01_02"), ("群", "ag_04_02"), ("环", "ag_07_01"),
        ("域", "ag_07_02"), ("格", "ag_08_01"),
    ],
}


def normalize(text: str) -> str:
    """粗规范化：去 LaTeX 符号/命令/标点/空白，仅保留中英文与数字。"""
    text = re.sub(r"\$[^$]*\$", " ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"[\{\}\[\]\(\),.;:，。；：、？！?'!—\-_|=+*/<>^&%]", " ", text)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def sem_text(text: str) -> str:
    """语义向量用文本：去掉 $ 定界符与 LaTeX 命令，保留中文叙述与数学字母。"""
    text = re.sub(r"\$([^$]*)\$", r" \1 ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"[{}_^]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def bigrams(s: str):
    return {s[i:i + 2] for i in range(len(s) - 1)}


def dice(a: str, b: str) -> float:
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return 0.0
    return 2 * len(ga & gb) / (len(ga) + len(gb))


def dot(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b))


def load_platform_nodes() -> list[dict]:
    """平台 9 模块/44 概念/157 条目，每节点带匹配候选文本。"""
    with urllib.request.urlopen(KB_API, timeout=30) as resp:
        kg = json.loads(resp.read().decode("utf-8"))
    nodes = []
    for mod in kg.get("modules", []):
        nodes.append({"node_id": mod["node_id"], "name": mod["name"], "level": "module", "text": mod.get("description") or ""})
        for concept in mod.get("children", []):
            nodes.append({
                "node_id": concept["node_id"],
                "name": concept.get("name") or concept.get("chapter_title") or "",
                "level": "concept",
                "text": concept.get("description") or "",
            })
            for item in concept.get("items", []):
                nodes.append({
                    "node_id": item["node_id"],
                    "name": item.get("name") or "",
                    "level": "item",
                    "text": item.get("text") or "",
                })
    return nodes


def main():
    # 1) 112 题全量
    bank = json.load(open(BASE / "老师训练题库.json", encoding="utf-8"))
    questions = []
    for exam in bank["exams"]:
        for kind in ("fill", "calc", "proof", "app"):
            for i, item in enumerate(exam.get(kind, [])):
                questions.append({
                    "qid": f"{exam['id']}-{kind}-{i + 1}",
                    "exam": exam["id"],
                    "kind": kind,
                    "stem": item.get("q") or item.get("stem") or "",
                    "kp": item.get("kp") or "",
                })
    assert len(questions) == 112, f"题目数应为 112，实际 {len(questions)}"

    # 2) 候选池：映射.md 手工题面(88) + 平台节点(9模块/44概念/157条目)
    nodes = load_platform_nodes()
    print(f"平台节点候选: {len(nodes)}")
    md_text = open(BASE / "题库节点映射.md", encoding="utf-8").read()
    md_pairs = []
    for line in md_text.splitlines():
        m = re.match(r"node_id:\s*(\S+)\s*\|\s*类型:\s*(\S+)\s*\|\s*题目:\s*(.+?)\s*\|\s*难度", line)
        if m:
            md_pairs.append((m.group(3).strip(), m.group(1)))
    print(f"映射.md 条目: {len(md_pairs)}")

    # 3) 批量嵌入（一次全部，带去重）
    print("加载嵌入模型…")
    svc = EmbeddingService(device="cpu")

    # 按家族分组候选
    families: dict[str, list[dict]] = {}
    for md_stem, node_id in md_pairs:
        pre = node_id.split("_")[0]
        families.setdefault(pre, []).append({
            "node_id": node_id, "level": "item", "pool": "md",
            "raw": md_stem, "sem": sem_text(md_stem), "norm": normalize(md_stem),
        })
    for node in nodes:
        pre = node["node_id"].split("_")[0]
        families.setdefault(pre, []).append({
            "node_id": node["node_id"], "level": node["level"], "pool": "kb",
            "raw": node["name"], "sem": sem_text(f'{node["name"]} {node["text"]}'),
            "norm": normalize(node["name"]),
        })

    # 4) 逐题匹配
    result = {}
    stats = {"human_calibrated": 0, "contain_match": 0, "keyword": 0,
             "semantic": 0, "md_dice": 0, "kp_fallback": 0, "unmapped": 0}
    sem_scores = []
    for qi, q in enumerate(questions):
        kp = q["kp"]
        isok = kp in KP_NODE and KP_NODE[kp][0] in MODULE_PREFIX
        pre = MODULE_PREFIX[KP_NODE[kp][0]] if isok else None
        cands = families.get(pre, []) if pre else [c for v in families.values() for c in v]
        nstem = normalize(q["stem"])

        # 词面层：家族内平台节点名/章节名整词出现在题面
        lex_best, lex_node = 0.0, None
        for node in nodes:
            if pre and not node["node_id"].startswith(pre + "_"):
                continue
            nname = normalize(node["name"])
            if nname and nname in nstem:
                score = 1.0
            else:
                score = max(dice(nstem, nname), dice(nstem, normalize(node["text"][:120])) * 1.15)
            if score > lex_best:
                lex_best, lex_node = score, node

        # 语义层：家族内全量 cosine
        qv = svc.embed_query(sem_text(q["stem"]))
        sem_best, sem_i = -1.0, 0
        level_rank = {"item": 0, "concept": 1, "module": 2}
        for j, c in enumerate(cands):
            s = dot(qv, svc.embed_query(c["sem"]))
            if s > sem_best + 1e-6 or (abs(s - sem_best) <= 1e-6
                                       and level_rank[c["level"]] < level_rank[cands[sem_i]["level"]]):
                sem_best, sem_i = s, j
        sem_scores.append(sem_best)
        cand = cands[sem_i]
        alts = sorted(((dot(qv, svc.embed_query(c["sem"])), c) for c in cands), key=lambda t: t[0], reverse=True)[:3]

        if q["qid"] in OVERRIDES:
            method, node_id, conf = "human_calibrated", OVERRIDES[q["qid"]][0], 1.0
        elif lex_best >= 1.0:
            method, node_id, conf = "contain_match", lex_node["node_id"], lex_best
        elif pre:
            kw_hit = next((nid for kw, nid in KW_RULES.get(pre, []) if kw in q["stem"]), None)
            if kw_hit:
                method, node_id, conf = "keyword", kw_hit, 0.95
            elif sem_best >= SEM_THRESHOLD:
                method, node_id, conf = "semantic", cand["node_id"], sem_best
            elif lex_best >= 0.42:
                method, node_id, conf = "md_dice", lex_node["node_id"], lex_best
            elif isok:
                method, node_id, conf = "kp_fallback", KP_NODE[kp][2], 0.5
            else:
                method, node_id, conf = "unmapped", "ot_01_01", 0.0
        elif isok:
            method, node_id, conf = "kp_fallback", KP_NODE[kp][2], 0.5
        else:
            method, node_id, conf = "unmapped", "ot_01_01", 0.0
        stats[method] += 1
        result[q["qid"]] = {
            "node_id": node_id,
            "kp": kp,
            "kind": q["kind"],
            "method": method,
            "conf": round(conf, 3),
            "exam": q["exam"],
            "stem": q["stem"][:90],
            "alts": [(c["node_id"], round(s, 3), c["raw"][:26]) for s, c in alts],
        }

    out = {
        "generated": "2026-09-03",
        "total": len(result),
        "distinct_node_ids": len({v["node_id"] for v in result.values()}),
        "stats": stats,
        "questions": result,
    }
    path = BASE / "老师训练题库_node_id.json"
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[OK] 已写 {path}")
    print(f"统计: {stats}, 覆盖 node_id 数: {out['distinct_node_ids']}")

    # 5) 阈值校准 + 抽查
    ss = sorted(sem_scores)
    print(f"语义 top-1 分布: n={len(ss)}, min={ss[0]:.3f}, 中位={ss[len(ss)//2]:.3f}, max={ss[-1]:.3f}")
    shown = 0
    for q in questions:
        if shown >= 14:
            break
        r = result[q["qid"]]
        if r["method"] == "semantic":
            print(f"  [{r['kind']}] {q['qid']} {r['kp']} → {r['node_id']} ({r['conf']:.3f}) {r['stem'][:34]}")
            for nid, s, raw in r["alts"][:2]:
                print(f"      top: {nid} {s:.3f} {raw}")
            shown += 1


if __name__ == "__main__":
    main()
