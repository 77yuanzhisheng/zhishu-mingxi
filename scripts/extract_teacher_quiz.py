# -*- coding: utf-8 -*-
"""
extract_teacher_quiz.py — 从老师提供的训练题库.html 提取全部题目为 JSON
=======================================================================
用法:
    python scripts/extract_teacher_quiz.py
输出:
    data/documents/老师训练题库.json   (全部题目结构化数据)
    data/documents/老师训练题库.md     (供知识库索引的 Markdown)
"""

import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(BASE_DIR)  # D:\挑战杯
SRC_CANDIDATES = [
    os.path.join(BASE_DIR, "output_teacher", "训练题库.html"),
    os.path.join(WORKSPACE, "output_teacher", "训练题库.html"),
]
OUT_JSON = os.path.join(BASE_DIR, "data", "documents", "老师训练题库.json")
OUT_MD = os.path.join(BASE_DIR, "data", "documents", "老师训练题库.md")

NODE_EXTRACT = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const m = html.match(/const EXAMS=\[(.*?)\n\];/s);
if (!m) { console.error('EXAMS not found'); process.exit(1); }
const EXAMS = Function('return [' + m[1] + ']')();
process.stdout.write(JSON.stringify(EXAMS));
"""

KP_NAMES = {
    "set-ops": "集合运算", "relation": "关系性质", "function": "函数",
    "cardinality": "基数", "ie-set": "包含排斥原理", "graph-basic": "图的基本概念",
    "connectivity": "连通度", "planar": "平面图", "hamilton": "哈密顿图",
    "spanning-tree": "生成树", "coloring": "图着色", "digraph": "有向图",
    "gcd": "最大公因数", "congruence": "同余", "combinatorics": "排列组合",
    "inclusion-exclusion": "容斥原理", "gen-func": "生成函数", "recurrence": "递推方程",
    "polya": "Polya计数", "algebra": "代数系统", "group": "群", "semigroup": "半群",
    "prop-logic": "命题逻辑", "pred-logic": "谓词逻辑", "normal-form": "范式",
    "inference": "推理理论",
}

CAT_NAMES = {"fill": "填空题", "calc": "计算与简答题", "proof": "证明题", "app": "应用题"}


def extract_exams(html_path: str) -> list:
    proc = subprocess.run(
        ["node", "-e", NODE_EXTRACT, html_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node 提取失败: {proc.stderr}")
    return json.loads(proc.stdout)


def clean(s: str) -> str:
    """HTML <br>/<p> 等转成换行，方便 Markdown 展示。"""
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</?p\s*/?>", "\n", s)
    s = s.replace("\\u201c", "“").replace("\\u201d", "”")
    return s.strip()


def main() -> None:
    src = next((p for p in SRC_CANDIDATES if os.path.exists(p)), None)
    if not src:
        print("未找到训练题库.html，请先解压 output.rar 到 output_teacher/")
        sys.exit(1)

    exams = extract_exams(src)
    total = 0
    md_lines = [
        "# 老师训练题库（4 套模拟试题 · 含详细解答）",
        "",
        "> 来源：指导老师提供的离散数学交互式数字化教材（output.rar）训练题库。",
        "> 共 4 套模拟试卷，含填空题、计算与简答题、证明题、应用题，覆盖集合论、图论、数论、组合数学、代数结构、数理逻辑。",
        "",
    ]
    for exam in exams:
        md_lines.append(f"## {exam['title']}")
        md_lines.append("")
        for cat_key, cat_name in CAT_NAMES.items():
            items = exam.get(cat_key, [])
            if not items:
                continue
            md_lines.append(f"### {cat_name}（{len(items)} 题）")
            md_lines.append("")
            for i, item in enumerate(items, 1):
                kp = KP_NAMES.get(item.get("kp", ""), item.get("kp", ""))
                md_lines.append(f"**{i}. {clean(item['q'])}**")
                md_lines.append("")
                md_lines.append(f"- 知识点：{kp}")
                if item.get("fig"):
                    md_lines.append(f"- 配图：`{item['fig']}`")
                md_lines.append("")
                md_lines.append(f"**解答：** {clean(item['a'])}")
                md_lines.append("")
            total += len(items)

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"total": total, "exams": exams}, f, ensure_ascii=False, indent=1)

    print(f"题目总数: {total}")
    print(f"JSON: {OUT_JSON}")
    print(f"MD:   {OUT_MD}")


if __name__ == "__main__":
    main()
