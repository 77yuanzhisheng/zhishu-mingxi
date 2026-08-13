from __future__ import annotations

import ast
import math
import itertools
import operator
import re
from typing import Any
from dataclasses import dataclass
from enum import Enum


class QuestionType(str, Enum):
    GENERAL = "general"
    PROOF = "proof"
    DERIVATION = "derivation"
    CALCULATION = "calculation"


@dataclass(frozen=True)
class ReasoningPrompt:
    enabled: bool
    question_type: QuestionType
    system_prompt: str


@dataclass(frozen=True)
class SymbolicCheckResult:
    checked: bool
    valid: bool | None
    detail: str = ""
    evidence: str = ""


@dataclass(frozen=True)
class ReasoningEvaluation:
    score: int
    passed: bool
    checks: dict[str, bool]
    symbolic_expression_count: int


@dataclass(frozen=True)
class ProofPlan:
    enabled: bool
    method: str
    goal: str
    steps: list[str]
    required_sections: list[str]
    symbolic_check: SymbolicCheckResult


def detect_question_type(question: str) -> QuestionType:
    text = question.strip()
    if re.search(r"证明|证毕|定理", text):
        return QuestionType.PROOF
    if re.search(r"推导|等价|化简|推出|蕴含|判断.*是否|说明理由", text):
        return QuestionType.DERIVATION
    if re.search(r"计算|求值|等于几|[0-9]+\s*[+\-*/]\s*[0-9]+", text):
        return QuestionType.CALCULATION
    return QuestionType.GENERAL


def build_reasoning_prompt(question: str) -> ReasoningPrompt:
    question_type = detect_question_type(question)
    if question_type == QuestionType.GENERAL:
        return ReasoningPrompt(False, question_type, "")
    return ReasoningPrompt(
        True,
        question_type,
        "你是离散数学教学助手。回答证明题、推导题和计算题时，必须采用教材式符号推理结构，"
        "不得只给结论或套用模板，不得跳过关键步骤。\n"
        "输出格式必须包含以下小节：\n"
        "1. 已知：列出题目给定条件、符号含义、全集或变量范围，以及需要证明或计算的目标。\n"
        "2. 分析：说明将使用的定义、定理、等价变换或计算规则，并说明证明路线。\n"
        "3. 推导：使用步骤编号逐步写出推理过程；每一步必须包含符号式和依据，格式为"
        "“步骤n：符号式/中间结论；依据：所用定义、定理或等价规则”。\n"
        "4. 自检：检查每一步是否由已知条件或已列规则推出，检查最终结论是否与题目目标一致。\n"
        "5. 结论：明确回答题目目标。\n"
        "6. 证毕：证明题和推导题以“证毕”结束。\n"
        "要求：证明必须完整但精炼，优先控制在4到8个关键步骤，不展开与题目目标无关的内容；"
        "如果提供了程序侧符号校验结果或符号证据，必须优先依据该证据组织证明，不要自行生成与证据冲突的公式或表格。",
    )


def merge_reasoning_prompt(base_system_prompt: str, question: str) -> str:
    reasoning_prompt = build_reasoning_prompt(question)
    if not reasoning_prompt.enabled:
        return base_system_prompt
    if not base_system_prompt.strip():
        return reasoning_prompt.system_prompt
    return f"{base_system_prompt.rstrip()}\n\n{reasoning_prompt.system_prompt}"


def build_proof_plan(question: str) -> ProofPlan:
    question_type = detect_question_type(question)
    symbolic_check = verify_symbolic_statement(question)
    method = _select_proof_method(question, question_type, symbolic_check)
    if method == "none":
        return ProofPlan(False, "none", "", [], [], symbolic_check)

    required_sections = ["已知", "分析", "推导", "自检", "结论"]
    if question_type in {QuestionType.PROOF, QuestionType.DERIVATION}:
        required_sections.append("证毕")

    return ProofPlan(
        enabled=True,
        method=method,
        goal=_extract_goal(question),
        steps=_proof_steps_for_method(method, symbolic_check),
        required_sections=required_sections,
        symbolic_check=symbolic_check,
    )


def format_proof_plan_for_prompt(plan: ProofPlan) -> str:
    if not plan.enabled:
        return "暂无专门的符号证明计划。"

    lines = [
        f"方法：{plan.method}",
        f"目标：{plan.goal}",
        "必须包含小节：" + "、".join(plan.required_sections),
        "推理步骤约束：",
    ]
    lines.extend(f"{index}. {step}" for index, step in enumerate(plan.steps, start=1))
    if plan.symbolic_check.checked:
        status = "通过" if plan.symbolic_check.valid else "未通过"
        lines.append(f"程序侧符号校验：{status}；{plan.symbolic_check.detail}")
        if plan.symbolic_check.evidence:
            lines.append("校验证据：")
            lines.append(plan.symbolic_check.evidence)
    return "\n".join(lines)


def _select_proof_method(question: str, question_type: QuestionType, symbolic_check: SymbolicCheckResult) -> str:
    text = question.strip()
    expression = _extract_symbolic_expression(text)
    normalized_logic = _normalize_logic(expression)
    normalized_set = _normalize_set_text(expression)

    if question_type == QuestionType.GENERAL and not symbolic_check.checked:
        return "none"
    if re.search(r"归纳法|数学归纳|对.*n.*证明|n\s*=\s*1", text):
        return "mathematical_induction"
    if _verify_reflexive_closure(text) is not None:
        return "reflexive_closure"
    if _verify_symmetric_closure(text) is not None:
        return "symmetric_closure"
    if _verify_transitive_closure(text) is not None:
        return "transitive_closure"
    if _verify_relation_composition(text) is not None:
        return "relation_composition"
    if _verify_inverse_relation(text) is not None:
        return "inverse_relation"
    if _verify_boolean_matrix_square(text) is not None:
        return "boolean_matrix_power"
    if _verify_propositional_satisfiability(text) is not None:
        return "sat_check"
    if _verify_propositional_entailment(text) is not None:
        return "entailment_check"
    if _verify_propositional_normal_form(text) is not None:
        return "normal_form_conversion"
    if _verify_partial_order(text) is not None:
        return "partial_order_check"
    if _verify_equivalence_partition(text) is not None:
        return "equivalence_partition"
    if _verify_boolean_simplification(text) is not None:
        return "boolean_simplification"
    if _verify_combination_identity(text) is not None:
        return "combination_identity"
    if _verify_tree_edge_count(text) is not None:
        return "tree_edge_count"
    if _verify_euler_graph(text) is not None:
        return "euler_graph_check"
    if _verify_quantifier_negation(text) is not None:
        return "quantifier_transformation"
    if _verify_relation_matrix_property(text) is not None or _verify_relation_property(text) is not None:
        return "relation_property_check"
    if _verify_graph_formula(text) is not None or re.search(r"握手定理|度数和|K\s*\d+|完全图|边数", text):
        return "graph_counting"
    if _verify_set_identity(expression) is not None or (re.search(r"集合|补集|并集|交集", text) and re.search(r"[∪∩]|\^c|[A-Z].*=[A-Z]", normalized_set)):
        return "element_chasing"
    if _verify_propositional_equivalence(expression) is not None or (re.search(r"命题|真值表|等价|德摩根|蕴含", text) and re.search(r"[!&|]|->|<->", normalized_logic)):
        return "truth_table_or_equivalence"
    if _verify_arithmetic_equal(expression) is not None or question_type == QuestionType.CALCULATION:
        return "calculation_verification"
    if question_type in {QuestionType.PROOF, QuestionType.DERIVATION}:
        return "definition_expansion"
    return "none"


def _extract_goal(question: str) -> str:
    goal = re.sub(r"^(请)?(证明|判断|推导|计算|求证)[:：]?", "", question.strip())
    goal = re.sub(r"\s+", " ", goal)
    return goal[:180]


def _proof_steps_for_method(method: str, symbolic_check: SymbolicCheckResult) -> list[str]:
    method_steps = {
        "truth_table_or_equivalence": [
            "列出命题变元及待证等价式，明确两侧公式。",
            "枚举所有真值赋值，分别计算左式和右式。",
            "逐行比较两侧真值；若每行一致，则推出等价成立。",
            "如果程序侧提供真值表证据，回答中的表格必须与证据一致。",
        ],
        "element_chasing": [
            "任取元素 x，并说明 x 属于题目涉及的全集。",
            "从左侧集合出发，逐步展开补集、并集、交集等定义，推出 x 属于右侧。",
            "反向证明：从右侧集合出发，用同一组定义推出 x 属于左侧。",
            "由双向包含得到两个集合相等。",
        ],
        "transitive_closure": [
            "写出原始关系矩阵 M，并说明矩阵中 1 表示对应有序对属于关系。",
            "使用 Warshall 算法逐个中间点更新可达关系。",
            "列出最终闭包矩阵，并解释新增的 1 对应哪些传递可达关系。",
            "检查闭包矩阵是否已经满足传递性。",
        ],
        "reflexive_closure": [
            "写出论域 A 和原关系 R。",
            "逐个检查每个 a∈A 的对角有序对 (a,a) 是否已经属于 R。",
            "只补入缺失的对角有序对，得到最小自反关系。",
            "列出自反闭包并检查每个元素都与自身相关。",
        ],
        "symmetric_closure": [
            "写出论域 A 和原关系 R。",
            "对每个 (a,b)∈R 检查反向有序对 (b,a) 是否已经属于 R。",
            "只补入缺失的反向有序对，得到最小对称关系。",
            "列出对称闭包并检查每个有序对都有对应反向有序对。",
        ],
        "relation_composition": [
            "写出两个关系 R 和 S，并明确复合方向。",
            "按 S∘R 的定义寻找中间元素 b，使 (a,b)∈R 且 (b,c)∈S。",
            "列出每个成功三元组 (a,b,c) 作为符号推导依据。",
            "把所有得到的 (a,c) 汇总为关系复合结果。",
        ],
        "inverse_relation": [
            "写出原关系 R 的所有有序对。",
            "按逆关系定义把每个 (a,b) 转换为 (b,a)。",
            "合并转换后的有序对并去重。",
            "列出 R^{-1}，并说明每个有序对都来自原关系中的反向有序对。",
        ],
        "boolean_matrix_power": [
            "写出原关系矩阵 M。",
            "按布尔矩阵乘法规则计算 M 与 M 的复合：加法用逻辑或，乘法用逻辑与。",
            "逐项说明矩阵中为 1 的位置对应哪些长度为 2 的关系路径。",
            "给出最终布尔平方矩阵。",
        ],
        "sat_check": [
            "写出命题公式和所有命题变元。",
            "枚举真值赋值并寻找使公式为真的模型。",
            "若找到模型，列出该赋值；若找不到，说明公式不可满足。",
            "结论明确回答是否可满足。",
        ],
        "entailment_check": [
            "写出前提公式和结论公式。",
            "把蕴含检查转为寻找反模型：前提为真且结论为假的赋值。",
            "若存在反模型，说明不蕴含；若不存在反模型，说明蕴含成立。",
            "结论明确回答蕴含关系是否成立。",
        ],
        "normal_form_conversion": [
            "列出命题变元并枚举所有真值赋值。",
            "逐行计算目标公式的真值。",
            "求主析取范式时取所有成真行生成极小项；求主合取范式时取所有成假行生成极大项。",
            "给出标准范式，并说明它与原公式具有相同真值表。",
        ],
        "partial_order_check": [
            "写出论域 A 和关系 R。",
            "分别验证自反性、反对称性和传递性。",
            "若某一性质失败，给出具体反例；若三者都成立，说明 R 是偏序关系。",
            "结论必须明确回答是否为偏序关系。",
        ],
        "equivalence_partition": [
            "写出论域 A 和关系 R。",
            "分别验证自反性、对称性和传递性。",
            "若三者都成立，根据 R 合并互相关联的元素并写出等价类。",
            "用等价类给出 A 的划分。",
        ],
        "boolean_simplification": [
            "写出原布尔表达式和目标化简式。",
            "使用吸收律、幂等律、分配律或真值等价规则逐步化简。",
            "将左右两式化为同一标准真值形式，或用反例说明不等价。",
            "结论明确说明化简结果是否正确。",
        ],
        "combination_identity": [
            "写出组合数恒等式两侧，并明确 C(n,k) 的含义。",
            "使用组合数公式 C(n,k)=n!/(k!(n-k)!) 分别计算左右两侧。",
            "逐项比较两侧数值；若相等，则恒等式在题目给定参数下成立。",
            "结论明确说明等式是否正确。",
        ],
        "tree_edge_count": [
            "写出树的顶点数 |V| 和边数 |E|。",
            "使用树的基本性质：含 n 个顶点的树有 n-1 条边。",
            "代入顶点数计算期望边数，并与题目给出的边数比较。",
            "结论明确说明该树边数表述是否正确。",
        ],
        "euler_graph_check": [
            "写出无向图的度数序列。",
            "使用欧拉回路判定的必要条件：所有顶点度数均为偶数。",
            "逐项检查度数序列是否全为偶数；若存在奇度顶点，应给出反例。",
            "结论明确说明是否满足欧拉回路的度数条件。",
        ],
        "quantifier_transformation": [
            "写出论域、谓词 P(x) 的含义，以及待证的量词等价式。",
            "从左式出发，先解释外层否定作用于哪个量词命题。",
            "使用量词否定律：否定全称量词变为存在量词加内部否定；否定存在量词变为全称量词加内部否定。",
            "说明两侧在任意论域解释下含义一致，因此等价成立。",
        ],
        "relation_property_check": [
            "写出关系 R、论域 A，以及要判断的性质定义。",
            "按性质定义检查所有必要的有序对，例如传递性需检查 (a,b),(b,c) 是否推出 (a,c)。",
            "若性质不成立，给出程序侧反例；若成立，说明所有必要条件均已验证。",
            "结论必须明确回答该关系是否具有该性质。",
        ],
        "graph_counting": [
            "明确图论对象、顶点数、边数或度数和等符号。",
            "使用握手定理或完全图边数公式写出等式来源。",
            "代入题目数据完成计算或证明，不跳过公式来源。",
            "检查结论与题目要求的边数、度数和或定理表述一致。",
        ],
        "mathematical_induction": [
            "写出待证命题 P(n) 和 n 的取值范围。",
            "基础步：验证最小 n 的情形成立。",
            "归纳假设：假设 P(k) 成立，并清楚写出可使用的等式或性质。",
            "归纳步：在归纳假设基础上推出 P(k+1) 成立。",
            "说明由数学归纳法可得命题对所有允许的 n 成立。",
        ],
        "calculation_verification": [
            "写出原始表达式和需要计算的目标。",
            "按运算优先级或离散数学定义逐步变形。",
            "每一步给出依据，避免直接跳到结果。",
            "用程序侧校验结果核对最终答案。",
        ],
        "definition_expansion": [
            "列出题目中的关键定义和待证目标。",
            "把目标拆成若干中间结论，每个中间结论只使用已列定义或定理。",
            "逐步连接中间结论，说明每一步的依据。",
            "回到原目标并给出明确结论。",
        ],
    }
    steps = list(method_steps[method])
    if symbolic_check.checked and symbolic_check.valid is False:
        steps.append("注意：程序侧校验显示命题不成立，应优先给出反例，而不是强行证明。")
    return steps


def evaluate_reasoning_answer(answer: str, question: str = "") -> ReasoningEvaluation:
    checks = {
        "has_given": bool(re.search(r"已知", answer)),
        "has_analysis": bool(re.search(r"分析", answer)),
        "has_derivation": bool(re.search(r"推导|步骤", answer)),
        "has_reason": bool(re.search(r"依据", answer)),
        "has_self_check": bool(re.search(r"自检", answer)),
        "has_conclusion": bool(re.search(r"结论", answer)),
        "ends_with_qed": bool(re.search(r"证毕\s*[。.]?\s*$", answer.strip())),
    }
    if re.search(r"归纳法|数学归纳|归纳证明", question + answer):
        checks.update(
            {
                "has_base_case": bool(re.search(r"基础步|奠基|n\s*=\s*1", answer)),
                "has_induction_hypothesis": bool(re.search(r"归纳假设|假设.*成立", answer)),
                "has_induction_step": bool(re.search(r"归纳步|k\s*\+\s*1", answer)),
            }
        )
    symbolic_expression_count = len(re.findall(r"[¬∧∨∪∩→↔⇔≡]|->|<->|\^c|\\(?:neg|land|lor|cup|cap|rightarrow|equiv)", answer))
    score = round(sum(checks.values()) / len(checks) * 100)
    return ReasoningEvaluation(score, score >= 85, checks, symbolic_expression_count)


def verify_symbolic_statement(statement: str) -> SymbolicCheckResult:
    reflexive_closure_check = _verify_reflexive_closure(statement)
    if reflexive_closure_check is not None:
        return SymbolicCheckResult(
            True,
            reflexive_closure_check.valid,
            "checked reflexive closure by adding missing diagonal pairs",
            reflexive_closure_check.evidence,
        )
    symmetric_closure_check = _verify_symmetric_closure(statement)
    if symmetric_closure_check is not None:
        return SymbolicCheckResult(
            True,
            symmetric_closure_check.valid,
            "checked symmetric closure by adding reverse pairs",
            symmetric_closure_check.evidence,
        )
    closure_check = _verify_transitive_closure(statement)
    if closure_check is not None:
        return SymbolicCheckResult(
            True,
            closure_check.valid,
            "checked transitive closure by Warshall algorithm",
            closure_check.evidence,
        )
    composition_check = _verify_relation_composition(statement)
    if composition_check is not None:
        return SymbolicCheckResult(
            True,
            composition_check.valid,
            "checked relation composition by intermediate element enumeration",
            composition_check.evidence,
        )
    inverse_check = _verify_inverse_relation(statement)
    if inverse_check is not None:
        return SymbolicCheckResult(
            True,
            inverse_check.valid,
            "checked inverse relation by reversing ordered pairs",
            inverse_check.evidence,
        )
    matrix_power_check = _verify_boolean_matrix_square(statement)
    if matrix_power_check is not None:
        return SymbolicCheckResult(
            True,
            matrix_power_check.valid,
            "checked boolean matrix square for relation composition",
            matrix_power_check.evidence,
        )
    satisfiability_check = _verify_propositional_satisfiability(statement)
    if satisfiability_check is not None:
        detail = "checked propositional satisfiability with z3 solver" if "backend=z3" in satisfiability_check.evidence else "checked propositional satisfiability by truth assignment enumeration"
        return SymbolicCheckResult(
            True,
            satisfiability_check.valid,
            detail,
            satisfiability_check.evidence,
        )
    entailment_check = _verify_propositional_entailment(statement)
    if entailment_check is not None:
        detail = "checked propositional entailment with z3 countermodel search" if "backend=z3" in entailment_check.evidence else "checked propositional entailment by countermodel search"
        return SymbolicCheckResult(
            True,
            entailment_check.valid,
            detail,
            entailment_check.evidence,
        )
    normal_form_check = _verify_propositional_normal_form(statement)
    if normal_form_check is not None:
        return SymbolicCheckResult(
            True,
            normal_form_check.valid,
            normal_form_check.detail,
            normal_form_check.evidence,
        )
    partial_order_check = _verify_partial_order(statement)
    if partial_order_check is not None:
        return SymbolicCheckResult(
            True,
            partial_order_check.valid,
            "checked partial order properties",
            partial_order_check.evidence,
        )
    equivalence_check = _verify_equivalence_partition(statement)
    if equivalence_check is not None:
        return SymbolicCheckResult(
            True,
            equivalence_check.valid,
            "checked equivalence relation and partition",
            equivalence_check.evidence,
        )
    boolean_check = _verify_boolean_simplification(statement)
    if boolean_check is not None:
        detail = "checked boolean normal form equivalence with SymPy" if "backend=SymPy" in boolean_check.evidence else "checked boolean normal form equivalence"
        return SymbolicCheckResult(
            True,
            boolean_check.valid,
            detail,
            boolean_check.evidence,
        )
    combination_check = _verify_combination_identity(statement)
    if combination_check is not None:
        return SymbolicCheckResult(
            True,
            combination_check.valid,
            "checked combination identity by exact integer arithmetic",
            combination_check.evidence,
        )
    tree_check = _verify_tree_edge_count(statement)
    if tree_check is not None:
        return SymbolicCheckResult(
            True,
            tree_check.valid,
            "checked tree edge count property",
            tree_check.evidence,
        )
    euler_check = _verify_euler_graph(statement)
    if euler_check is not None:
        return SymbolicCheckResult(
            True,
            euler_check.valid,
            "checked Euler circuit degree condition",
            euler_check.evidence,
        )
    quantifier_check = _verify_quantifier_negation(statement)
    if quantifier_check is not None:
        return SymbolicCheckResult(
            True,
            quantifier_check.valid,
            "checked quantifier negation equivalence",
            quantifier_check.evidence,
        )
    relation_matrix_check = _verify_relation_matrix_property(statement)
    if relation_matrix_check is not None:
        return SymbolicCheckResult(
            True,
            relation_matrix_check.valid,
            "checked relation matrix property",
            relation_matrix_check.evidence,
        )
    relation_check = _verify_relation_property(statement)
    if relation_check is not None:
        return SymbolicCheckResult(
            True,
            relation_check.valid,
            "checked relation property on finite relation",
            relation_check.evidence,
        )
    graph_check = _verify_graph_formula(statement)
    if graph_check is not None:
        return SymbolicCheckResult(
            True,
            graph_check.valid,
            "checked graph formula",
            graph_check.evidence,
        )
    expression = _extract_symbolic_expression(statement)
    normalized = _normalize_logic(expression)
    if normalized in {"!(A|B)=!A&!B", "!A&!B=!(A|B)", "!(A&B)=!A|!B", "!A|!B=!(A&B)"}:
        return SymbolicCheckResult(True, True, "matched De Morgan equivalence")
    set_identity = _verify_set_identity(expression)
    if set_identity is not None:
        return SymbolicCheckResult(
            True,
            set_identity.valid,
            "checked set identity by finite universe enumeration",
            set_identity.evidence,
        )
    propositional = _verify_propositional_equivalence(expression)
    if propositional is not None:
        return SymbolicCheckResult(
            True,
            propositional.valid,
            "checked propositional truth table",
            propositional.evidence,
        )
    arithmetic = _verify_arithmetic_equal(expression)
    if arithmetic is not None:
        return SymbolicCheckResult(True, arithmetic, "checked arithmetic equality")
    return SymbolicCheckResult(False, None, "no supported symbolic check")


@dataclass(frozen=True)
class _QuantifierCheck:
    valid: bool
    evidence: str


def _verify_quantifier_negation(statement: str) -> _QuantifierCheck | None:
    expression = _normalize_quantifier_text(_extract_quantifier_expression(statement))
    valid_patterns = {
        "!forallxP(x)<->existsx!P(x)": "not all x satisfy P(x) iff there exists x that does not satisfy P(x)",
        "existsx!P(x)<->!forallxP(x)": "there exists x that does not satisfy P(x) iff not all x satisfy P(x)",
        "!existsxP(x)<->forallx!P(x)": "there does not exist x satisfying P(x) iff every x does not satisfy P(x)",
        "forallx!P(x)<->!existsxP(x)": "every x does not satisfy P(x) iff there does not exist x satisfying P(x)",
        "!forallxP(x)=existsx!P(x)": "not all x satisfy P(x) iff there exists x that does not satisfy P(x)",
        "existsx!P(x)=!forallxP(x)": "there exists x that does not satisfy P(x) iff not all x satisfy P(x)",
        "!existsxP(x)=forallx!P(x)": "there does not exist x satisfying P(x) iff every x does not satisfy P(x)",
        "forallx!P(x)=!existsxP(x)": "every x does not satisfy P(x) iff there does not exist x satisfying P(x)",
    }
    if expression in valid_patterns:
        return _QuantifierCheck(True, f"quantifier negation: {valid_patterns[expression]}")
    if any(token in expression for token in ("forall", "exists")) and _find_equivalence_separator(expression):
        return _QuantifierCheck(False, "unsupported or non-standard quantifier transformation pattern")
    return None


def _extract_quantifier_expression(text: str) -> str:
    candidates = re.findall(r"[¬!∀∃A-Za-z0-9()\s↔⇔≡=<>-]+", text)
    candidates = [candidate.strip() for candidate in candidates if any(token in candidate for token in ("∀", "∃", "forall", "exists"))]
    candidates = [candidate for candidate in candidates if _find_equivalence_separator(_normalize_quantifier_text(candidate))]
    if not candidates:
        return text
    return max(candidates, key=len)


def _normalize_quantifier_text(text: str) -> str:
    replacements = {
        " ": "",
        "（": "(",
        "）": ")",
        "¬": "!",
        "非": "!",
        "∀": "forall",
        "全称": "forall",
        "任意": "forall",
        "∃": "exists",
        "存在": "exists",
        "⇔": "<->",
        "↔": "<->",
        "≡": "<->",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("FORALL", "forall").replace("EXISTS", "exists")
    text = re.sub(r"P\s*\(\s*[Xx]\s*\)", "P(x)", text)
    text = re.sub(r"PX", "P(x)", text, flags=re.IGNORECASE)
    return text

def _extract_symbolic_expression(text: str) -> str:
    candidates = re.findall(r"[A-Za-z0-9非并交¬!∧∨∪∩&|(),，\-<>↔⇔≡=+*/.^\s]+", text)
    candidates = [candidate.strip() for candidate in candidates]
    candidates = [candidate for candidate in candidates if _find_equivalence_separator(candidate)]
    if not candidates:
        return text
    return max(candidates, key=len)


def _normalize_logic(text: str) -> str:
    for old, new in {
        " ": "",
        "（": "(",
        "）": ")",
        "非": "!",
        "¬": "!",
        "并": "|",
        "∪": "|",
        "∨": "|",
        "交": "&",
        "∩": "&",
        "∧": "&",
    }.items():
        text = text.replace(old, new)
    return text.upper()


def _verify_arithmetic_equal(statement: str) -> bool | None:
    if "=" not in statement:
        return None
    left, right = statement.split("=", 1)
    if not re.fullmatch(r"[0-9+\-*/().\s]+", left + right):
        return None
    return _safe_eval_arithmetic(left) == _safe_eval_arithmetic(right)


@dataclass(frozen=True)
class _PropositionalCheck:
    valid: bool
    evidence: str


@dataclass(frozen=True)
class _NormalFormCheck:
    valid: bool
    detail: str
    evidence: str


def _verify_propositional_equivalence(statement: str) -> _PropositionalCheck | None:
    separator = _find_equivalence_separator(statement)
    if separator is None:
        return None
    left, right = statement[: separator[0]], statement[separator[1] :]
    variables = sorted(set(re.findall(r"[A-Z]", _normalize_logic(left + right))))
    if not variables or len(variables) > 6:
        return None
    if not _is_supported_logic_text(left + right):
        return None

    try:
        rows = []
        for values in itertools.product([False, True], repeat=len(variables)):
            env = dict(zip(variables, values))
            left_value = _eval_logic_expr(left, env)
            right_value = _eval_logic_expr(right, env)
            rows.append((env, left_value, right_value))
        valid = all(left_value == right_value for _, left_value, right_value in rows)
        return _PropositionalCheck(valid, _format_truth_table(variables, left, right, rows))
    except ValueError:
        return None


def _format_truth_table(
    variables: list[str],
    left: str,
    right: str,
    rows: list[tuple[dict[str, bool], bool, bool]],
) -> str:
    headers = variables + [left.strip(), right.strip()]
    lines = [" | ".join(headers)]
    lines.append(" | ".join(["---"] * len(headers)))
    for env, left_value, right_value in rows:
        values = [_truth_symbol(env[var]) for var in variables]
        values.extend([_truth_symbol(left_value), _truth_symbol(right_value)])
        lines.append(" | ".join(values))
    return "\n".join(lines)


def _truth_symbol(value: bool) -> str:
    return "T" if value else "F"


@dataclass(frozen=True)
class _SetIdentityCheck:
    valid: bool
    evidence: str


@dataclass(frozen=True)
class _RelationCheck:
    valid: bool
    evidence: str


@dataclass(frozen=True)
class _GraphCheck:
    valid: bool
    evidence: str


def _verify_set_identity(statement: str) -> _SetIdentityCheck | None:
    separator = _find_equivalence_separator(statement)
    if separator is None:
        return None
    left, right = statement[: separator[0]], statement[separator[1] :]
    if not _is_supported_set_text(left + right):
        return None
    variables = sorted(set(re.findall(r"[A-Z]", left + right)))
    if not variables or len(variables) > 4:
        return None

    universe = frozenset(range(1, len(variables) + 2))
    subsets = _all_subsets(universe)
    rows = 0
    for values in itertools.product(subsets, repeat=len(variables)):
        env = dict(zip(variables, values))
        try:
            left_value = _eval_set_expr(left, env, universe)
            right_value = _eval_set_expr(right, env, universe)
        except ValueError:
            return None
        rows += 1
        if left_value != right_value:
            return _SetIdentityCheck(
                False,
                "counterexample: "
                + ", ".join(f"{name}={_format_set(env[name])}" for name in variables)
                + f"; left={_format_set(left_value)}, right={_format_set(right_value)}",
            )
    return _SetIdentityCheck(True, f"verified on finite universe {_format_set(universe)} across {rows} assignments")


def _is_supported_set_text(text: str) -> bool:
    normalized = _normalize_set_text(text)
    return re.fullmatch(r"[A-ZUC&|()^\s]+", normalized) is not None


def _normalize_set_text(text: str) -> str:
    for old, new in {
        " ": "",
        "（": "(",
        "）": ")",
        "并": "|",
        "∪": "|",
        "交": "&",
        "∩": "&",
        "补": "^C",
    }.items():
        text = text.replace(old, new)
    return text.upper()


def _all_subsets(universe: frozenset[int]) -> list[frozenset[int]]:
    items = list(universe)
    return [frozenset(item for bit, item in enumerate(items) if mask & (1 << bit)) for mask in range(1 << len(items))]


def _eval_set_expr(expression: str, env: dict[str, frozenset[int]], universe: frozenset[int]) -> frozenset[int]:
    tokens = _set_tokens(_normalize_set_text(expression))
    parser = _SetParser(tokens, env, universe)
    result = parser.parse_union()
    if parser.current() is not None:
        raise ValueError("unexpected trailing token")
    return result


def _set_tokens(expression: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(expression):
        if expression.startswith("^C", i):
            tokens.append("^C")
            i += 2
        elif expression[i] in "|&()":
            tokens.append(expression[i])
            i += 1
        elif re.match(r"[A-Z]", expression[i]):
            tokens.append(expression[i])
            i += 1
        else:
            raise ValueError(f"unsupported token: {expression[i]}")
    return tokens


class _SetParser:
    def __init__(self, tokens: list[str], env: dict[str, frozenset[int]], universe: frozenset[int]):
        self.tokens = tokens
        self.env = env
        self.universe = universe
        self.index = 0

    def current(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def accept(self, token: str) -> bool:
        if self.current() == token:
            self.index += 1
            return True
        return False

    def parse_union(self) -> frozenset[int]:
        value = self.parse_intersection()
        while self.accept("|"):
            value = value | self.parse_intersection()
        return value

    def parse_intersection(self) -> frozenset[int]:
        value = self.parse_postfix()
        while self.accept("&"):
            value = value & self.parse_postfix()
        return value

    def parse_postfix(self) -> frozenset[int]:
        value = self.parse_atom()
        while self.accept("^C"):
            value = self.universe - value
        return value

    def parse_atom(self) -> frozenset[int]:
        token = self.current()
        if token is None:
            raise ValueError("unexpected end of expression")
        if self.accept("("):
            value = self.parse_union()
            if not self.accept(")"):
                raise ValueError("missing closing parenthesis")
            return value
        if re.fullmatch(r"[A-Z]", token):
            self.index += 1
            return env_value(self.env, token)
        raise ValueError(f"unexpected token: {token}")


def env_value(env: dict[str, frozenset[int]], token: str) -> frozenset[int]:
    if token not in env:
        raise ValueError(f"unknown set variable: {token}")
    return env[token]


def _format_set(values: frozenset[int]) -> str:
    if not values:
        return "{}"
    return "{" + ",".join(str(value) for value in sorted(values)) + "}"


def _verify_transitive_closure(statement: str) -> _RelationCheck | None:
    if not re.search(r"传递闭包|Warshall|warshall", statement):
        return None
    matrix = _extract_relation_matrix(statement)
    if matrix is not None:
        closure = _warshall_closure(matrix)
        return _RelationCheck(True, f"Warshall closure matrix={closure}")
    parsed = _extract_relation_problem(statement)
    if parsed is None:
        return None
    relation, universe = parsed
    matrix_from_relation = _relation_to_matrix(relation, universe)
    closure_matrix = _warshall_closure(matrix_from_relation)
    closure_relation = _matrix_to_relation(closure_matrix, universe)
    added = closure_relation - relation
    evidence = f"closure={_format_relation(closure_relation)}; added={_format_relation(added)}"
    return _RelationCheck(True, evidence)


def _verify_reflexive_closure(statement: str) -> _RelationCheck | None:
    if "自反闭包" not in statement and not re.search(r"reflexive closure", statement, re.IGNORECASE):
        return None
    parsed = _extract_relation_problem(statement)
    if parsed is None:
        return None
    relation, universe = parsed
    diagonal = {(item, item) for item in universe}
    closure = relation | diagonal
    added = closure - relation
    evidence = f"closure={_format_relation(closure)}; added={_format_relation(added)}"
    return _RelationCheck(True, evidence)


def _verify_symmetric_closure(statement: str) -> _RelationCheck | None:
    if "对称闭包" not in statement and not re.search(r"symmetric closure", statement, re.IGNORECASE):
        return None
    parsed = _extract_relation_problem(statement)
    if parsed is None:
        return None
    relation, _ = parsed
    reverse_pairs = {(b, a) for a, b in relation}
    closure = relation | reverse_pairs
    added = closure - relation
    evidence = f"closure={_format_relation(closure)}; added={_format_relation(added)}"
    return _RelationCheck(True, evidence)


def _verify_relation_composition(statement: str) -> _RelationCheck | None:
    if not re.search(r"复合|composition|[RS]\s*[∘○o]\s*[RS]", statement, re.IGNORECASE):
        return None
    relations = _extract_named_relations(statement)
    if len(relations) < 2:
        return None
    direction = _extract_composition_direction(statement)
    if direction is None:
        return None
    left_name, right_name = direction
    if left_name not in relations or right_name not in relations:
        return None
    # For S∘R, first apply R, then S.
    left_relation = relations[left_name]
    right_relation = relations[right_name]
    composition, witnesses = _compose_relations(right_relation, left_relation)
    evidence = f"composition={_format_relation(composition)}; witnesses={_format_witnesses(witnesses)}"
    return _RelationCheck(True, evidence)


def _verify_inverse_relation(statement: str) -> _RelationCheck | None:
    if "逆关系" not in statement and not re.search(r"inverse relation|R\s*\^\s*\{?\s*-\s*1\s*\}?", statement, re.IGNORECASE):
        return None
    parsed = _extract_relation_problem(statement)
    if parsed is None:
        return None
    relation, _ = parsed
    inverse = {(b, a) for a, b in relation}
    return _RelationCheck(True, f"inverse={_format_relation(inverse)}")


def _verify_boolean_matrix_square(statement: str) -> _RelationCheck | None:
    if not re.search(r"布尔平方|矩阵平方|M\s*\^\s*2|boolean matrix square", statement, re.IGNORECASE):
        return None
    matrix = _extract_relation_matrix(statement)
    if matrix is None:
        return None
    squared = _boolean_matrix_multiply(matrix, matrix)
    return _RelationCheck(True, f"boolean_square={squared}")


def _verify_propositional_satisfiability(statement: str) -> _PropositionalCheck | None:
    if not re.search(r"可满足|满足性|satisf", statement, re.IGNORECASE):
        return None
    expression = _extract_logic_formula_without_label(statement)
    variables = sorted(set(re.findall(r"[A-Z]", _normalize_logic(expression))))
    if not variables or len(variables) > 8 or not _is_supported_logic_text(expression):
        return None
    z3_check = _try_z3_satisfiability(expression, variables)
    if z3_check is not None:
        return z3_check
    try:
        for values in itertools.product([False, True], repeat=len(variables)):
            env = dict(zip(variables, values))
            if _eval_logic_expr(expression, env):
                return _PropositionalCheck(True, f"backend=truth_table; model={_format_bool_assignment(env)}")
    except ValueError:
        return None
    return _PropositionalCheck(False, f"backend=truth_table; no model over variables={variables}")


def _verify_propositional_entailment(statement: str) -> _PropositionalCheck | None:
    if "蕴含" not in statement and not re.search(r"entails?|implies", statement, re.IGNORECASE):
        return None
    parsed = _extract_entailment_parts(statement)
    if parsed is None:
        return None
    premise, conclusion = parsed
    variables = sorted(set(re.findall(r"[A-Z]", _normalize_logic(premise + conclusion))))
    if not variables or len(variables) > 8 or not _is_supported_logic_text(premise + conclusion):
        return None
    z3_check = _try_z3_entailment(premise, conclusion, variables)
    if z3_check is not None:
        return z3_check
    try:
        for values in itertools.product([False, True], repeat=len(variables)):
            env = dict(zip(variables, values))
            if _eval_logic_expr(premise, env) and not _eval_logic_expr(conclusion, env):
                return _PropositionalCheck(False, f"backend=truth_table; countermodel={_format_bool_assignment(env)}")
    except ValueError:
        return None
    return _PropositionalCheck(True, f"backend=truth_table; no countermodel over variables={variables}")




def _verify_propositional_normal_form(statement: str) -> _NormalFormCheck | None:
    wants_dnf = any(token in statement for token in ("\u4e3b\u6790\u53d6\u8303\u5f0f", "\u6790\u53d6\u8303\u5f0f")) or bool(re.search(r"DNF", statement, re.IGNORECASE))
    wants_cnf = any(token in statement for token in ("\u4e3b\u5408\u53d6\u8303\u5f0f", "\u5408\u53d6\u8303\u5f0f")) or bool(re.search(r"CNF", statement, re.IGNORECASE))
    if not wants_dnf and not wants_cnf:
        return None
    expression = _extract_logic_formula_without_label(statement)
    if not expression or not _is_supported_logic_text(expression):
        return None
    variables = sorted(set(re.findall(r"[A-Z]", _normalize_logic(expression))))
    if not variables or len(variables) > 8:
        return None
    sympy_check = _try_sympy_normal_form(expression, variables, wants_dnf)
    try:
        rows = []
        for values in itertools.product([False, True], repeat=len(variables)):
            env = dict(zip(variables, values))
            rows.append((env, _eval_logic_expr(expression, env)))
    except ValueError:
        return None

    if wants_dnf:
        canonical_dnf = _canonical_dnf(rows, variables)
        true_rows = sum(value for _, value in rows)
        if sympy_check is not None:
            evidence = f"{sympy_check.evidence}; true_rows={true_rows}; canonical_dnf={canonical_dnf}; bits={_truth_bits(expression, variables)}"
            return _NormalFormCheck(True, "checked canonical DNF by truth-table minterm enumeration; SymPy DNF also computed", evidence)
        evidence = f"backend=truth_table; variables={variables}; true_rows={true_rows}; dnf={canonical_dnf}; bits={_truth_bits(expression, variables)}"
        return _NormalFormCheck(True, "checked canonical DNF by truth-table minterm enumeration", evidence)

    canonical_cnf = _canonical_cnf(rows, variables)
    false_rows = sum(not value for _, value in rows)
    if sympy_check is not None:
        evidence = f"{sympy_check.evidence}; false_rows={false_rows}; canonical_cnf={canonical_cnf}; bits={_truth_bits(expression, variables)}"
        return _NormalFormCheck(True, "checked canonical CNF by truth-table maxterm enumeration; SymPy CNF also computed", evidence)
    evidence = f"backend=truth_table; variables={variables}; false_rows={false_rows}; cnf={canonical_cnf}; bits={_truth_bits(expression, variables)}"
    return _NormalFormCheck(True, "checked canonical CNF by truth-table maxterm enumeration", evidence)

def _verify_partial_order(statement: str) -> _RelationCheck | None:
    if "偏序" not in statement:
        return None
    parsed = _extract_relation_problem(statement)
    if parsed is None:
        return None
    relation, universe = parsed
    reflexive = _check_relation_property(relation, universe, "reflexive")
    antisymmetric = _check_relation_property(relation, universe, "antisymmetric")
    transitive = _check_relation_property(relation, universe, "transitive")
    checks = {"reflexive": reflexive, "antisymmetric": antisymmetric, "transitive": transitive}
    valid = all(check is not None and check.valid for check in checks.values())
    evidence_parts = [f"{name}={check.valid if check else None}" for name, check in checks.items()]
    evidence_parts.extend(f"{name}_evidence={check.evidence}" for name, check in checks.items() if check and not check.valid)
    return _RelationCheck(valid, "; ".join(evidence_parts))


def _verify_equivalence_partition(statement: str) -> _RelationCheck | None:
    if "等价关系" not in statement and "划分" not in statement:
        return None
    parsed = _extract_relation_problem(statement)
    if parsed is None:
        return None
    relation, universe = parsed
    reflexive = _check_relation_property(relation, universe, "reflexive")
    symmetric = _check_relation_property(relation, universe, "symmetric")
    transitive = _check_relation_property(relation, universe, "transitive")
    checks = {"reflexive": reflexive, "symmetric": symmetric, "transitive": transitive}
    valid = all(check is not None and check.valid for check in checks.values())
    evidence_parts = [f"{name}={check.valid if check else None}" for name, check in checks.items()]
    if valid:
        evidence_parts.append(f"partition={_format_partition(_equivalence_classes(relation, universe))}")
    else:
        evidence_parts.extend(f"{name}_evidence={check.evidence}" for name, check in checks.items() if check and not check.valid)
    return _RelationCheck(valid, "; ".join(evidence_parts))


def _verify_boolean_simplification(statement: str) -> _PropositionalCheck | None:
    if not re.search(r"化简|布尔|simplif|boolean", statement, re.IGNORECASE):
        return None
    expression = _extract_symbolic_expression(statement)
    separator = _find_equivalence_separator(expression)
    if separator is None:
        return None
    left, right = expression[: separator[0]], expression[separator[1] :]
    if "->" in _normalize_logic(left + right):
        return None
    if not re.search(r"[∧∨¬!&|]", left + right):
        return None
    if not _is_supported_logic_text(left + right):
        return None
    variables = sorted(set(re.findall(r"[A-Z]", _normalize_logic(left + right))))
    if not variables or len(variables) > 8:
        return None
    sympy_check = _try_sympy_boolean_equivalence(left, right, variables)
    if sympy_check is not None:
        return sympy_check
    try:
        left_bits = _truth_bits(left, variables)
        right_bits = _truth_bits(right, variables)
    except ValueError:
        return None
    valid = left_bits == right_bits
    evidence = f"backend=truth_table; variables={variables}; left_bits={left_bits}; right_bits={right_bits}; equivalent={valid}"
    return _PropositionalCheck(valid, evidence)


@dataclass(frozen=True)
class _NumericCheck:
    valid: bool
    evidence: str


def _verify_combination_identity(statement: str) -> _NumericCheck | None:
    if not re.search(r"组合|C\s*\(|C\s*[（]", statement):
        return None
    expression = _extract_symbolic_expression(statement)
    separator = _find_equivalence_separator(expression)
    if separator is None:
        return None
    left, right = expression[: separator[0]], expression[separator[1] :]
    try:
        left_value = _eval_combination_expr(left)
        right_value = _eval_combination_expr(right)
    except ValueError:
        return None
    valid = left_value == right_value
    evidence = f"left={left_value}; right={right_value}; equivalent={valid}"
    if "+" in left:
        parts = [_eval_combination_expr(part) for part in left.split("+")]
        evidence += f"; expanded_left={' + '.join(str(part) for part in parts)} = {left_value}"
    return _NumericCheck(valid, evidence)


def _verify_tree_edge_count(statement: str) -> _NumericCheck | None:
    if "树" not in statement:
        return None
    vertices = _extract_labeled_number(statement, ("顶点", "结点", "节点"))
    edges = _extract_labeled_number(statement, ("边数", "边"))
    if vertices is None or edges is None:
        return None
    if vertices < 1:
        return None
    expected = vertices - 1
    return _NumericCheck(edges == expected, f"vertices={vertices}; edges={edges}; n-1={expected}")


def _verify_euler_graph(statement: str) -> _NumericCheck | None:
    if not re.search(r"欧拉|Euler", statement, re.IGNORECASE):
        return None
    sequence_match = re.search(r"\[[\d\s,]+\]", statement)
    if not sequence_match:
        return None
    try:
        degrees = ast.literal_eval(sequence_match.group(0))
    except (SyntaxError, ValueError):
        return None
    if not isinstance(degrees, list) or not degrees or any(not isinstance(value, int) or value < 0 for value in degrees):
        return None
    odd_degrees = [value for value in degrees if value % 2 == 1]
    all_even = not odd_degrees
    return _NumericCheck(all_even, f"degrees={degrees}; all_even={all_even}; odd_degrees={odd_degrees}")


def _eval_combination_expr(expression: str) -> int:
    tokens = re.findall(r"C\s*[（(]\s*(\d+)\s*,\s*(\d+)\s*[）)]|\d+|[+-]", expression)
    if not tokens:
        raise ValueError("empty combination expression")
    converted = _replace_combination_terms(expression)
    if not re.fullmatch(r"[0-9+\-\s]+", converted):
        raise ValueError("unsupported combination expression")
    value = 0
    sign = 1
    expect_number = True
    for token in re.findall(r"\d+|[+-]", converted):
        if token == "+":
            if expect_number:
                raise ValueError("unexpected plus")
            sign = 1
            expect_number = True
        elif token == "-":
            if expect_number:
                sign *= -1
            else:
                sign = -1
                expect_number = True
        else:
            value += sign * int(token)
            sign = 1
            expect_number = False
    if expect_number:
        raise ValueError("expression ended with operator")
    return value


def _replace_combination_terms(expression: str) -> str:
    def repl(match: re.Match[str]) -> str:
        n = int(match.group(1))
        k = int(match.group(2))
        if k < 0 or k > n:
            raise ValueError("invalid combination indices")
        return str(math.comb(n, k))

    return re.sub(r"C\s*[（(]\s*(\d+)\s*,\s*(\d+)\s*[）)]", repl, expression)


def _extract_labeled_number(statement: str, labels: tuple[str, ...]) -> int | None:
    joined = "|".join(re.escape(label) for label in labels)
    patterns = [
        rf"(\d+)\s*(?:个|条)?\s*(?:{joined})",
        rf"(?:{joined})\s*(?:数)?\s*(?:为|是|=|有)?\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, statement)
        if match:
            return int(match.group(1))
    return None


def _extract_relation_problem(statement: str) -> tuple[set[tuple[int, int]], list[int]] | None:
    relation_match = re.search(r"R\s*=\s*\{([^}]*)\}", statement)
    if not relation_match:
        return None
    pairs = _parse_relation_pairs(relation_match.group(1))
    if not pairs:
        return None
    universe_match = re.search(r"A\s*=\s*\{([^}]*)\}", statement)
    if universe_match:
        universe = sorted({int(value) for value in re.findall(r"\d+", universe_match.group(1))})
    else:
        universe = sorted(set().union(*pairs))
    if not universe:
        return None
    return set(pairs), universe


def _extract_relation_matrix(statement: str) -> list[list[int]] | None:
    matrix_match = re.search(r"\[\s*\[[\s\S]*?\]\s*\]", statement)
    if not matrix_match:
        return None
    try:
        matrix = ast.literal_eval(matrix_match.group(0))
    except (SyntaxError, ValueError):
        return None
    if not _is_square_zero_one_matrix(matrix):
        return None
    return matrix


def _warshall_closure(matrix: list[list[int]]) -> list[list[int]]:
    closure = [row[:] for row in matrix]
    size = len(closure)
    for k in range(size):
        for i in range(size):
            for j in range(size):
                closure[i][j] = 1 if closure[i][j] or (closure[i][k] and closure[k][j]) else 0
    return closure


def _boolean_matrix_multiply(left: list[list[int]], right: list[list[int]]) -> list[list[int]]:
    size = len(left)
    result = [[0 for _ in range(size)] for _ in range(size)]
    for i in range(size):
        for j in range(size):
            result[i][j] = 1 if any(left[i][k] and right[k][j] for k in range(size)) else 0
    return result


def _relation_to_matrix(relation: set[tuple[int, int]], universe: list[int]) -> list[list[int]]:
    index = {value: position for position, value in enumerate(universe)}
    matrix = [[0 for _ in universe] for _ in universe]
    for a, b in relation:
        if a in index and b in index:
            matrix[index[a]][index[b]] = 1
    return matrix


def _matrix_to_relation(matrix: list[list[int]], universe: list[int]) -> set[tuple[int, int]]:
    return {
        (universe[row_index], universe[col_index])
        for row_index, row in enumerate(matrix)
        for col_index, value in enumerate(row)
        if value == 1
    }


def _format_relation(relation: set[tuple[int, int]]) -> str:
    if not relation:
        return "{}"
    return "{" + ",".join(f"({a},{b})" for a, b in sorted(relation)) + "}"


def _extract_named_relations(statement: str) -> dict[str, set[tuple[int, int]]]:
    relations: dict[str, set[tuple[int, int]]] = {}
    for name, content in re.findall(r"\b([A-Z])\s*=\s*\{([^}]*)\}", statement):
        pairs = _parse_relation_pairs(content)
        if pairs:
            relations[name] = set(pairs)
    return relations


def _extract_composition_direction(statement: str) -> tuple[str, str] | None:
    match = re.search(r"\b([A-Z])\s*[∘○o]\s*([A-Z])\b", statement)
    if match:
        return match.group(1), match.group(2)
    return None


def _compose_relations(
    first_relation: set[tuple[int, int]],
    second_relation: set[tuple[int, int]],
) -> tuple[set[tuple[int, int]], list[tuple[int, int, int]]]:
    result: set[tuple[int, int]] = set()
    witnesses: list[tuple[int, int, int]] = []
    for a, b in sorted(first_relation):
        for x, c in sorted(second_relation):
            if b != x:
                continue
            result.add((a, c))
            witnesses.append((a, b, c))
    return result, witnesses


def _format_witnesses(witnesses: list[tuple[int, int, int]]) -> str:
    if not witnesses:
        return "none"
    return ",".join(f"({a},{b},{c})" for a, b, c in witnesses)


def _equivalence_classes(relation: set[tuple[int, int]], universe: list[int]) -> list[frozenset[int]]:
    seen: set[int] = set()
    classes: list[frozenset[int]] = []
    for item in universe:
        if item in seen:
            continue
        related = frozenset(other for other in universe if (item, other) in relation and (other, item) in relation)
        if not related:
            related = frozenset({item})
        classes.append(related)
        seen.update(related)
    return classes


def _format_partition(classes: list[frozenset[int]]) -> str:
    return "{" + ",".join(_format_set(group) for group in classes) + "}"


def _truth_bits(expression: str, variables: list[str]) -> str:
    bits = []
    for values in itertools.product([False, True], repeat=len(variables)):
        env = dict(zip(variables, values))
        bits.append("1" if _eval_logic_expr(expression, env) else "0")
    return "".join(bits)


def _canonical_dnf(rows: list[tuple[dict[str, bool], bool]], variables: list[str]) -> str:
    terms = []
    for env, value in rows:
        if not value:
            continue
        literals = [variable if env[variable] else f"!{variable}" for variable in variables]
        terms.append("(" + "&".join(literals) + ")")
    if not terms:
        return "False"
    return "|".join(terms)


def _canonical_cnf(rows: list[tuple[dict[str, bool], bool]], variables: list[str]) -> str:
    clauses = []
    for env, value in rows:
        if value:
            continue
        literals = [f"!{variable}" if env[variable] else variable for variable in variables]
        clauses.append("(" + "|".join(literals) + ")")
    if not clauses:
        return "True"
    return "&".join(clauses)


def _format_bool_assignment(env: dict[str, bool]) -> str:
    return "{" + ", ".join(f"{key}={value}" for key, value in sorted(env.items())) + "}"


def _try_sympy_boolean_equivalence(left: str, right: str, variables: list[str]) -> _PropositionalCheck | None:
    try:
        import sympy as sp
    except ImportError:
        return None

    try:
        left_expr = _logic_to_external_expr(left, variables, sp.Symbol, sp.Not, sp.And, sp.Or, sp.Implies, sp.Equivalent)
        right_expr = _logic_to_external_expr(right, variables, sp.Symbol, sp.Not, sp.And, sp.Or, sp.Implies, sp.Equivalent)
        left_simple = sp.simplify_logic(left_expr, form="dnf")
        right_simple = sp.simplify_logic(right_expr, form="dnf")
        valid = sp.simplify_logic(sp.Equivalent(left_expr, right_expr)) == sp.true
    except Exception:
        return None
    evidence = (
        f"backend=SymPy; variables={variables}; "
        f"simplified_left={_format_external_logic_expr(left_simple)}; "
        f"simplified_right={_format_external_logic_expr(right_simple)}; equivalent={valid}"
    )
    return _PropositionalCheck(bool(valid), evidence)


def _try_sympy_normal_form(expression: str, variables: list[str], wants_dnf: bool) -> _NormalFormCheck | None:
    try:
        import sympy as sp
    except ImportError:
        return None

    try:
        sympy_expr = _logic_to_external_expr(expression, variables, sp.Symbol, sp.Not, sp.And, sp.Or, sp.Implies, sp.Equivalent)
        normal_form = sp.to_dnf(sympy_expr, simplify=True) if wants_dnf else sp.to_cnf(sympy_expr, simplify=True)
    except Exception:
        return None
    form_name = "dnf" if wants_dnf else "cnf"
    evidence = f"backend=SymPy; variables={variables}; {form_name}={_format_external_logic_expr(normal_form)}"
    return _NormalFormCheck(True, f"computed {form_name.upper()} with SymPy", evidence)


def _try_z3_satisfiability(expression: str, variables: list[str]) -> _PropositionalCheck | None:
    try:
        import z3  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        solver = z3.Solver()
        z3_expr = _logic_to_external_expr(expression, variables, z3.Bool, z3.Not, z3.And, z3.Or, z3.Implies, lambda a, b: a == b)
        solver.add(z3_expr)
        if solver.check() != z3.sat:
            return _PropositionalCheck(False, f"backend=z3; no model over variables={variables}")
        model = solver.model()
        assignment = {variable: bool(z3.is_true(model.eval(z3.Bool(variable), model_completion=True))) for variable in variables}
        return _PropositionalCheck(True, f"backend=z3; model={_format_bool_assignment(assignment)}")
    except Exception:
        return None


def _try_z3_entailment(premise: str, conclusion: str, variables: list[str]) -> _PropositionalCheck | None:
    try:
        import z3  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        solver = z3.Solver()
        premise_expr = _logic_to_external_expr(premise, variables, z3.Bool, z3.Not, z3.And, z3.Or, z3.Implies, lambda a, b: a == b)
        conclusion_expr = _logic_to_external_expr(conclusion, variables, z3.Bool, z3.Not, z3.And, z3.Or, z3.Implies, lambda a, b: a == b)
        solver.add(premise_expr, z3.Not(conclusion_expr))
        if solver.check() != z3.sat:
            return _PropositionalCheck(True, f"backend=z3; no countermodel over variables={variables}")
        model = solver.model()
        assignment = {variable: bool(z3.is_true(model.eval(z3.Bool(variable), model_completion=True))) for variable in variables}
        return _PropositionalCheck(False, f"backend=z3; countermodel={_format_bool_assignment(assignment)}")
    except Exception:
        return None


def _logic_to_external_expr(
    expression: str,
    variables: list[str],
    symbol_factory: Any,
    not_fn: Any,
    and_fn: Any,
    or_fn: Any,
    implies_fn: Any,
    equivalent_fn: Any,
) -> Any:
    env = {variable: symbol_factory(variable) for variable in variables}
    parser = _ExternalLogicParser(_logic_tokens(_normalize_logic(expression)), env, not_fn, and_fn, or_fn, implies_fn, equivalent_fn)
    result = parser.parse_equiv()
    if parser.current() is not None:
        raise ValueError("unexpected trailing token")
    return result


def _format_external_logic_expr(expression: Any) -> str:
    return (
        str(expression)
        .replace(" ", "")
        .replace("~", "!")
        .replace("&", "&")
        .replace("|", "|")
        .replace("True", "True")
        .replace("False", "False")
    )


def _extract_logic_formula_without_label(statement: str) -> str:
    text = re.sub(r"^(请)?(判断|证明|求证|说明)[:：]?", "", statement.strip())
    text = re.sub(r"命题公式|公式|是否可满足|可满足吗|是否满足|满足性", "", text)
    return _extract_logic_formula(text)


def _extract_entailment_parts(statement: str) -> tuple[str, str] | None:
    text = re.sub(r"^(请)?(判断|证明|求证|说明)[:：]?", "", statement.strip())
    patterns = [
        r"(.+?)是否蕴含(.+)",
        r"(.+?)蕴含(.+)",
        r"(.+?)entails?(.+)",
        r"(.+?)implies(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            premise = _extract_symbolic_expression(match.group(1)).strip(" ：:。？?")
            conclusion = _extract_symbolic_expression(match.group(2)).strip(" ：:。？?")
            premise = _extract_logic_formula(premise)
            conclusion = _extract_logic_formula(conclusion)
            if premise and conclusion:
                return premise, conclusion
    return None


def _extract_logic_formula(text: str) -> str:
    candidates = re.findall(r"[A-Za-z()¬!∧∨&|\-<>↔⇔≡\s]+", text)
    candidates = [candidate.strip(" ：:。？?") for candidate in candidates]
    candidates = [candidate for candidate in candidates if re.search(r"[A-Z]", _normalize_logic(candidate))]
    candidates = [candidate for candidate in candidates if _is_supported_logic_text(candidate)]
    if not candidates:
        return _extract_symbolic_expression(text).strip(" ：:。？?")
    return max(candidates, key=len)

def _verify_relation_property(statement: str) -> _RelationCheck | None:
    relation_match = re.search(r"R\s*=\s*\{([^}]*)\}", statement)
    if not relation_match:
        return None
    property_name = _extract_relation_property_name(statement)
    if property_name is None:
        return None

    pairs = _parse_relation_pairs(relation_match.group(1))
    if not pairs:
        return None
    universe = sorted(set().union(*pairs))
    if not universe:
        return None

    return _check_relation_property(set(pairs), universe, property_name)


def _verify_relation_matrix_property(statement: str) -> _RelationCheck | None:
    if "矩阵" not in statement and "matrix" not in statement.lower():
        return None
    property_name = _extract_relation_property_name(statement)
    if property_name is None:
        return None

    matrix_match = re.search(r"\[\s*\[[\s\S]*?\]\s*\]", statement)
    if not matrix_match:
        return None
    try:
        matrix = ast.literal_eval(matrix_match.group(0))
    except (SyntaxError, ValueError):
        return None
    if not _is_square_zero_one_matrix(matrix):
        return None

    relation = {
        (row_index + 1, col_index + 1)
        for row_index, row in enumerate(matrix)
        for col_index, value in enumerate(row)
        if value == 1
    }
    universe = list(range(1, len(matrix) + 1))
    return _check_relation_property(relation, universe, property_name)


def _extract_relation_property_name(statement: str) -> str | None:
    for key, label in (("反对称", "antisymmetric"), ("自反", "reflexive"), ("对称", "symmetric"), ("传递", "transitive")):
        if key in statement:
            return label
    return None


def _is_square_zero_one_matrix(matrix: object) -> bool:
    if not isinstance(matrix, list) or not matrix:
        return False
    size = len(matrix)
    for row in matrix:
        if not isinstance(row, list) or len(row) != size:
            return False
        if any(value not in (0, 1) for value in row):
            return False
    return True


def _check_relation_property(relation: set[tuple[int, int]], universe: list[int], property_name: str) -> _RelationCheck | None:
    if property_name == "reflexive":
        for x in universe:
            if (x, x) not in relation:
                return _RelationCheck(False, f"counterexample: missing ({x},{x})")
        return _RelationCheck(True, f"verified on universe {universe}")

    if property_name == "symmetric":
        for a, b in relation:
            if (b, a) not in relation:
                return _RelationCheck(False, f"counterexample: ({a},{b}) present but ({b},{a}) missing")
        return _RelationCheck(True, f"verified on universe {universe}")

    if property_name == "antisymmetric":
        for a, b in relation:
            if a != b and (b, a) in relation:
                return _RelationCheck(False, f"counterexample: ({a},{b}) and ({b},{a}) both present")
        return _RelationCheck(True, f"verified on universe {universe}")

    if property_name == "transitive":
        for a, b in relation:
            for c, d in relation:
                if b == c and (a, d) not in relation:
                    return _RelationCheck(False, f"counterexample: ({a},{b}) and ({c},{d}) present but ({a},{d}) missing")
        return _RelationCheck(True, f"verified on universe {universe}")

    return None


def _parse_relation_pairs(content: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for item in re.findall(r"\((\d+)\s*,\s*(\d+)\)", content):
        pairs.append((int(item[0]), int(item[1])))
    return pairs


def _verify_graph_formula(statement: str) -> _GraphCheck | None:
    complete_match = re.search(r"K\s*(\d+).*?(?:边数|edges?).*?(?:为|=)\s*(\d+)", statement, re.IGNORECASE)
    if complete_match:
        n = int(complete_match.group(1))
        expected = int(complete_match.group(2))
        actual = n * (n - 1) // 2
        return _GraphCheck(actual == expected, f"K{n} edge count = {n}*({n}-1)/2 = {actual}; claimed={expected}")

    if "握手定理" in statement or "度数和" in statement:
        edge_matches = re.findall(r"边数\s*=\s*(\d+)", statement)
        degree_matches = re.findall(r"度数和\s*=\s*(\d+)", statement)
        if edge_matches and degree_matches:
            edges = int(edge_matches[-1])
            degree_sum = int(degree_matches[-1])
            expected = 2 * edges
            return _GraphCheck(degree_sum == expected, f"2*|E| = 2*{edges} = {expected}; degree_sum={degree_sum}")
        return _GraphCheck(True, "handshake theorem structural check: each undirected edge contributes 2 to degree sum")
    return None


def _find_equivalence_separator(statement: str) -> tuple[int, int] | None:
    for token in ("<->", "↔", "⇔", "≡", "="):
        index = statement.find(token)
        if index > -1:
            return index, index + len(token)
    return None


def _is_supported_logic_text(text: str) -> bool:
    normalized = _normalize_logic(text)
    return re.fullmatch(r"[A-Z!&|()\-<>=>]+", normalized) is not None


def _eval_logic_expr(expression: str, env: dict[str, bool]) -> bool:
    tokens = _logic_tokens(_normalize_logic(expression))
    parser = _LogicParser(tokens, env)
    result = parser.parse_equiv()
    if parser.current() is not None:
        raise ValueError("unexpected trailing token")
    return result


def _logic_tokens(expression: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(expression):
        if expression.startswith("<->", i):
            tokens.append("<->")
            i += 3
        elif expression.startswith("->", i):
            tokens.append("->")
            i += 2
        elif expression[i] in "!&|()":
            tokens.append(expression[i])
            i += 1
        elif re.match(r"[A-Z]", expression[i]):
            tokens.append(expression[i])
            i += 1
        else:
            raise ValueError(f"unsupported token: {expression[i]}")
    return tokens


class _LogicParser:
    def __init__(self, tokens: list[str], env: dict[str, bool]):
        self.tokens = tokens
        self.env = env
        self.index = 0

    def current(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def accept(self, token: str) -> bool:
        if self.current() == token:
            self.index += 1
            return True
        return False

    def parse_equiv(self) -> bool:
        value = self.parse_implies()
        while self.accept("<->"):
            value = value == self.parse_implies()
        return value

    def parse_implies(self) -> bool:
        value = self.parse_or()
        if self.accept("->"):
            right = self.parse_implies()
            value = (not value) or right
        return value

    def parse_or(self) -> bool:
        value = self.parse_and()
        while self.accept("|"):
            right = self.parse_and()
            value = value or right
        return value

    def parse_and(self) -> bool:
        value = self.parse_not()
        while self.accept("&"):
            right = self.parse_not()
            value = value and right
        return value

    def parse_not(self) -> bool:
        if self.accept("!"):
            return not self.parse_not()
        return self.parse_atom()

    def parse_atom(self) -> bool:
        token = self.current()
        if token is None:
            raise ValueError("unexpected end of expression")
        if self.accept("("):
            value = self.parse_equiv()
            if not self.accept(")"):
                raise ValueError("missing closing parenthesis")
            return value
        if re.fullmatch(r"[A-Z]", token):
            self.index += 1
            return self.env[token]
        raise ValueError(f"unexpected token: {token}")


class _ExternalLogicParser:
    def __init__(self, tokens: list[str], env: dict[str, Any], not_fn: Any, and_fn: Any, or_fn: Any, implies_fn: Any, equivalent_fn: Any):
        self.tokens = tokens
        self.env = env
        self.not_fn = not_fn
        self.and_fn = and_fn
        self.or_fn = or_fn
        self.implies_fn = implies_fn
        self.equivalent_fn = equivalent_fn
        self.index = 0

    def current(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def accept(self, token: str) -> bool:
        if self.current() == token:
            self.index += 1
            return True
        return False

    def parse_equiv(self) -> Any:
        value = self.parse_implies()
        while self.accept("<->"):
            value = self.equivalent_fn(value, self.parse_implies())
        return value

    def parse_implies(self) -> Any:
        value = self.parse_or()
        if self.accept("->"):
            value = self.implies_fn(value, self.parse_implies())
        return value

    def parse_or(self) -> Any:
        value = self.parse_and()
        while self.accept("|"):
            value = self.or_fn(value, self.parse_and())
        return value

    def parse_and(self) -> Any:
        value = self.parse_not()
        while self.accept("&"):
            value = self.and_fn(value, self.parse_not())
        return value

    def parse_not(self) -> Any:
        if self.accept("!"):
            return self.not_fn(self.parse_not())
        return self.parse_atom()

    def parse_atom(self) -> Any:
        token = self.current()
        if token is None:
            raise ValueError("unexpected end of expression")
        if self.accept("("):
            value = self.parse_equiv()
            if not self.accept(")"):
                raise ValueError("missing closing parenthesis")
            return value
        if re.fullmatch(r"[A-Z]", token):
            self.index += 1
            return self.env[token]
        raise ValueError(f"unexpected token: {token}")


def _safe_eval_arithmetic(expression: str) -> float:
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](eval_node(node.operand))
        raise ValueError("unsupported arithmetic expression")

    return eval_node(ast.parse(expression, mode="eval"))
