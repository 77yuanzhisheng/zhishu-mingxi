"""
结构化题库服务（队员2：知识库/题库）
====================================

为「大题自动批阅引擎」（队员1）提供结构化题源：
把老师训练题库中的证明题/计算题整理为 {题面, 标准答案, 知识点, 评分要点} 结构。

数据来源:
    data/documents/老师训练题库.json （112 题全量，含 LaTeX 答案与知识点 kp 标签）

端点:
    GET /api/kb/structured-questions?type=proof|calc|fill|app&kp=&limit=
        — 返回结构化题目（供批阅引擎取题 / 前端展示）
    GET /api/kb/grading-guide?kp=semigroup
        — 返回该知识点的「评分要点映射」（5 维评分时检查什么、常见错误）
"""

import json
import logging
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kb", tags=["KB-Structured"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QUIZ_FILE = os.path.join(BASE_DIR, "data", "documents", "老师训练题库.json")

TYPE_NAMES = {"fill": "填空题", "calc": "计算与简答题", "proof": "证明题", "app": "应用题"}

# 知识点 → 评分要点映射（供批阅引擎的 5 维评分提示词使用）
# 每项: {name, focus(评分重点), checks(关键判定点), common_errors(常见错误)}
GRADING_GUIDE = {
    # ===== 命题逻辑 =====
    "prop-logic": {
        "name": "命题逻辑符号化", "focus": "自然语言命题的符号化与真值分析",
        "checks": ["联结词（¬∧∨→↔）使用是否准确", "复合命题的真值判定是否正确",
                   "符号化与题意是否一致"],
        "common_errors": ["蕴含方向写反（q→p 与 p→q 混淆）", "否定范围错误", "联结词优先级错误"],
    },
    "normal-form": {
        "name": "范式（主析取/合取范式）", "focus": "公式范式化过程与结果",
        "checks": ["化简步骤是否等价", "主范式项是否完整（所有极小/极大项）", "结果形式是否符合定义"],
        "common_errors": ["缺少极小项/极大项", "化简跳步导致不等价", "混淆 DNF 与 CNF"],
    },
    "inference": {
        "name": "推理理论（NL 自然推理）", "focus": "一阶/命题逻辑形式推理证明",
        "checks": ["推理规则（∀⁻/∃⁺/假言三段论等）使用是否合法", "每一步是否由前提可导出",
                   "结论是否严格推出"],
        "common_errors": ["∃xP(x) 随意指定具体个体（存在例示误用）", "量词消去/引入顺序错误",
                          "循环论证"],
    },
    # ===== 谓词逻辑 =====
    "pred-logic": {
        "name": "谓词逻辑符号化与真值", "focus": "量词公式的符号化、解释下的真值判定",
        "checks": ["量词（∀∃）使用是否准确", "在给定解释下真值计算是否正确",
                   "符号化是否忠实于原命题"],
        "common_errors": ["∀ 与 ∃ 混淆", "否定与量词交换错误（¬∀xP(x)≡∃x¬P(x) 用反）",
                          "个体域理解错误"],
    },
    # ===== 集合论 =====
    "set-ops": {
        "name": "集合运算与等式证明", "focus": "集合恒等式的推导与充要条件",
        "checks": ["运算定义使用是否准确（∪∩-⊕~）", "等式证明是否等价变形",
                   "充要条件是否双向说明"],
        "common_errors": ["只证充分性不证必要性", "用特例代替一般证明", "补集/差集概念混淆"],
    },
    "function": {
        "name": "函数与特征函数", "focus": "函数定义、单射满射双射、特征函数",
        "checks": ["函数性质判定是否正确", "特征函数与原集合对应是否准确",
                   "定义域/值域描述是否完整"],
        "common_errors": ["单射与满射混淆", "特征函数值域理解错误", "复合函数顺序错误"],
    },
    "cardinality": {
        "name": "基数与集合大小", "focus": "集合基数比较、可数性",
        "checks": ["基数概念使用是否准确", "双射/映射构造是否合法", "结论证明是否完备"],
        "common_errors": ["把基数与元素个数混为一谈", "构造双射不证明双射性"],
    },
    "ie-set": {
        "name": "包含排斥原理", "focus": "容斥原理公式的应用与计算",
        "checks": ["容斥公式使用是否正确（交叠项符号）", "计数是否遗漏或重复",
                   "结果计算是否正确"],
        "common_errors": ["交叠项符号写反", "遗漏多重交叠", "未考虑全集限制"],
    },
    # ===== 关系 =====
    "relation": {
        "name": "关系性质与运算", "focus": "关系五大性质判定、关系复合/逆/限制",
        "checks": ["性质判定（自反/反自反/对称/反对称/传递）是否逐一验证",
                   "dom/ran/复合/限制等运算是否正确", "反例构造是否有效"],
        "common_errors": ["用单个元素判断传递性", "自反与反自反同时成立的例外", "复合顺序颠倒"],
    },
    # ===== 图论 =====
    "graph-basic": {
        "name": "图的基本概念", "focus": "图的定义、度、完全图、特殊图",
        "checks": ["定义理解是否准确（无向/有向/多重边/环）", "度与边数计算是否正确"],
        "common_errors": ["忽略多重边/环的度贡献", "完全图边数公式用错"],
    },
    "connectivity": {
        "name": "连通性", "focus": "连通图判定、割点/割边、连通分量",
        "checks": ["连通性判定逻辑是否正确", "p(G-V') 计数与条件验证是否完整"],
        "common_errors": ["只验证部分顶点子集", "必要条件与充分条件混淆"],
    },
    "hamilton": {
        "name": "哈密顿图", "focus": "哈密顿通路/回路的存在性判定",
        "checks": ["判定定理（必要条件/充分条件）使用是否准确", "反例或构造是否有效"],
        "common_errors": ["用欧拉图条件判定哈密顿图", "忽略必要条件的逆否命题"],
    },
    "spanning-tree": {
        "name": "生成树", "focus": "生成树的存在性、边数、弦",
        "checks": ["生成树定义使用是否准确", "边数关系（n-1）与弦概念是否正确"],
        "common_errors": ["弦与树边混淆", "非连通图误判有生成树"],
    },
    "coloring": {
        "name": "图着色", "focus": "点/边色数、平面图四色、对偶图",
        "checks": ["色数判定是否正确", "对偶图构造与色数关系是否准确"],
        "common_errors": ["把对偶图顶点数当色数", "四色定理适用条件误用"],
    },
    "digraph": {
        "name": "有向图", "focus": "有向图概念、可达性、强连通",
        "checks": ["有向概念（入度/出度/强连通）使用是否准确"],
        "common_errors": ["忽略方向性", "强连通与弱连通混淆"],
    },
    # ===== 数论 =====
    "gcd": {
        "name": "最大公因数", "focus": "质因数分解求 gcd/lcm、欧几里得算法",
        "checks": ["质因数分解是否正确", "gcd/lcm 公式使用是否准确", "计算过程是否完整"],
        "common_errors": ["gcd 与 lcm 混淆", "指数取 min/max 错误"],
    },
    "congruence": {
        "name": "同余方程", "focus": "一次同余方程求解、解的存在性",
        "checks": ["解存在判定（gcd 整除性）是否正确", "模等价类列举是否完整",
                   "全部解是否给出"],
        "common_errors": ["漏解", "gcd 计算错误导致存在性误判", "同余类表述不规范"],
    },
    # ===== 组合数学 =====
    "combinatorics": {
        "name": "排列组合计数", "focus": "排列/组合/隔板法/整数解计数",
        "checks": ["计数模型选择是否正确（排列 vs 组合 vs 隔板）", "变换（变量代换）是否合法",
                   "组合数计算是否正确"],
        "common_errors": ["排列组合混用", "隔板法前提不满足仍使用", "组合数 C(n,k) 计算错误"],
    },
    "inclusion-exclusion": {
        "name": "容斥原理", "focus": "容斥公式在多集合计数中的应用",
        "checks": ["容斥公式使用是否正确", "各交叠项计数是否准确"],
        "common_errors": ["符号错误", "漏项", "重复计数"],
    },
    "gen-func": {
        "name": "生成函数", "focus": "指数/普通生成函数的展开与系数提取",
        "checks": ["生成函数乘法是否正确", "系数对应关系（组合意义）是否准确"],
        "common_errors": ["指数生成函数与普通生成函数混淆", "系数提取错误"],
    },
    "recurrence": {
        "name": "递推方程", "focus": "递推关系建立与求解",
        "checks": ["递推式建立是否忠实于问题", "求解方法（特征方程/迭代）是否正确"],
        "common_errors": ["初始条件遗漏", "特征方程解错", "通解与特解混淆"],
    },
    "polya": {
        "name": "Polya 计数", "focus": "置换群作用下染色计数",
        "checks": ["置换群与轨道数理解是否正确", "Burnside/Polya 公式应用是否准确"],
        "common_errors": ["固定置换下染色数算错", "对称性因子（如旋转/翻转等价）遗漏"],
    },
    # ===== 代数结构 =====
    "algebra": {
        "name": "代数系统", "focus": "二元运算性质、代数系统判定",
        "checks": ["运算封闭性/结合/交换/单位元/逆元验证是否完整"],
        "common_errors": ["漏验证封闭性", "单位元与零元混淆"],
    },
    "group": {
        "name": "群", "focus": "群公理验证、子群判定、同态同构",
        "checks": ["群四条公理是否逐一验证", "子群判定条件使用是否准确",
                   "同态/同构映射构造与验证是否完整"],
        "common_errors": ["漏验证结合律", "同态映射不验证保持运算", "单位元唯一性误用"],
    },
    "semigroup": {
        "name": "半群", "focus": "半群运算性质与交换性证明",
        "checks": ["结合律验证是否完整", "交换性推导链是否每一步合法"],
        "common_errors": ["跳过结合律直接交换", "推导链不完整（跳步）"],
    },
}


def _load_quiz() -> List[Dict]:
    if not os.path.exists(QUIZ_FILE):
        logger.warning(f"老师训练题库文件不存在: {QUIZ_FILE}")
        return []
    with open(QUIZ_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("exams", [])


@router.get("/structured-questions")
def get_structured_questions(
    type: Optional[str] = None,
    kp: Optional[str] = None,
    limit: int = 50,
) -> Dict:
    """返回结构化题目（题面/标准答案/知识点），供批阅引擎与前端使用。"""
    exams = _load_quiz()
    questions = []
    for exam in exams:
        for t, tname in TYPE_NAMES.items():
            for idx, item in enumerate(exam.get(t, []), 1):
                if type and t != type:
                    continue
                if kp and item.get("kp") != kp:
                    continue
                questions.append({
                    "id": f"e{exam['id']}_{t}_{idx}",
                    "exam_id": exam["id"],
                    "type": t,
                    "type_name": tname,
                    "question": item["q"],
                    "answer": item["a"],
                    "kp": item.get("kp", ""),
                    "fig": item.get("fig"),
                    "grading_guide": GRADING_GUIDE.get(item.get("kp", "")),
                })
    questions = questions[:limit]
    return {
        "total": len(questions),
        "questions": questions,
        "kp_count": len(GRADING_GUIDE),
    }


@router.get("/grading-guide")
def get_grading_guide(
    kp: Optional[str] = None,
) -> Dict:
    """返回知识点 → 评分要点映射（批阅引擎 5 维评分提示词的数据源）。"""
    if kp:
        guide = GRADING_GUIDE.get(kp)
        if not guide:
            return {"found": False, "kp": kp, "guide": None}
        return {"found": True, "kp": kp, "guide": guide}
    return {"found": True, "count": len(GRADING_GUIDE), "guides": GRADING_GUIDE}
