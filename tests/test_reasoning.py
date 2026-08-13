from backend.reasoning.service import (
    QuestionType,
    build_reasoning_prompt,
    detect_question_type,
    evaluate_reasoning_answer,
    merge_reasoning_prompt,
    verify_symbolic_statement,
)

from scripts.test_rag import answer_token_limit, compact_context, filter_reasoning_contexts, request_timeout, symbolic_check_note


def test_detects_proof_derivation_and_calculation_questions():
    assert detect_question_type("证明德摩根律：非(A并B)=非A交非B") == QuestionType.PROOF
    assert detect_question_type("推导 (P -> Q) 的等价形式") == QuestionType.DERIVATION
    assert detect_question_type("判断关系R是否传递，并说明理由") == QuestionType.DERIVATION
    assert detect_question_type("计算 1+1 等于几") == QuestionType.CALCULATION


def test_detects_general_question_without_enhancement():
    assert detect_question_type("什么是集合？") == QuestionType.GENERAL


def test_builds_textbook_style_prompt_for_proof_question():
    prompt = build_reasoning_prompt("证明握手定理")

    for label in ["已知", "分析", "推导", "结论", "证毕"]:
        assert label in prompt.system_prompt
    for rule in ["步骤编号", "符号式", "依据", "自检"]:
        assert rule in prompt.system_prompt
    assert prompt.enabled is True
    assert prompt.question_type == QuestionType.PROOF


def test_general_question_bypasses_reasoning_prompt():
    prompt = build_reasoning_prompt("什么是命题？")

    assert prompt.enabled is False
    assert prompt.system_prompt == ""


def test_merge_reasoning_prompt_only_for_reasoning_questions():
    base = "你是离散数学智能助教。"

    enhanced = merge_reasoning_prompt(base, "证明德摩根律")
    unchanged = merge_reasoning_prompt(base, "什么是集合？")

    assert "已知" in enhanced
    assert "证毕" in enhanced
    assert unchanged == base


def test_symbolic_check_handles_simple_arithmetic_and_demorgan():
    arithmetic = verify_symbolic_statement("1+1=2")
    demorgan = verify_symbolic_statement("非(A并B)=非A交非B")

    assert arithmetic.checked is True
    assert arithmetic.valid is True
    assert demorgan.checked is True
    assert demorgan.valid is True


def test_symbolic_check_verifies_propositional_equivalence():
    implication = verify_symbolic_statement("P->Q = ¬P∨Q")
    invalid = verify_symbolic_statement("P∧Q = P∨Q")

    assert implication.checked is True
    assert implication.valid is True
    assert "P | Q | P->Q | ¬P∨Q" in implication.evidence
    assert "T | F | F | F" in implication.evidence
    assert invalid.checked is True
    assert invalid.valid is False
    assert "T | F | F | T" in invalid.evidence


def test_symbolic_check_extracts_formula_from_question_text():
    result = verify_symbolic_statement("证明命题逻辑等价式：P->Q = ¬P∨Q")

    assert result.checked is True
    assert result.valid is True


def test_symbolic_check_verifies_set_identities():
    demorgan = verify_symbolic_statement("证明集合恒等式：(A∪B)^c = A^c∩B^c")
    distributive = verify_symbolic_statement("A∩(B∪C) = (A∩B)∪(A∩C)")
    invalid = verify_symbolic_statement("A∪B = A∩B")

    assert demorgan.checked is True
    assert demorgan.valid is True
    assert "set identity" in demorgan.detail
    assert distributive.checked is True
    assert distributive.valid is True
    assert invalid.checked is True
    assert invalid.valid is False
    assert "counterexample" in invalid.evidence


def test_symbolic_check_verifies_relation_properties():
    reflexive = verify_symbolic_statement("判断关系R={(1,1),(1,2),(2,2)}是否自反")
    symmetric = verify_symbolic_statement("判断关系R={(1,1),(1,2),(2,1),(2,2)}是否对称")
    not_transitive = verify_symbolic_statement("判断关系R={(1,2),(2,3)}是否传递")

    assert reflexive.checked is True
    assert reflexive.valid is True
    assert "relation property" in reflexive.detail
    assert symmetric.checked is True
    assert symmetric.valid is True
    assert not_transitive.checked is True
    assert not_transitive.valid is False
    assert "counterexample" in not_transitive.evidence


def test_symbolic_check_verifies_relation_matrix_properties():
    symmetric = verify_symbolic_statement("判断关系矩阵M=[[1,1],[1,1]]是否对称")
    not_transitive = verify_symbolic_statement("判断关系矩阵M=[[0,1,0],[0,0,1],[0,0,0]]是否传递")
    antisymmetric = verify_symbolic_statement("判断关系矩阵M=[[1,1],[0,1]]是否反对称")

    assert symmetric.checked is True
    assert symmetric.valid is True
    assert "relation matrix" in symmetric.detail
    assert not_transitive.checked is True
    assert not_transitive.valid is False
    assert "counterexample" in not_transitive.evidence
    assert "(1,3) missing" in not_transitive.evidence
    assert antisymmetric.checked is True
    assert antisymmetric.valid is True


def test_symbolic_check_verifies_graph_formulas():
    complete_graph = verify_symbolic_statement("完全图K5的边数是否为10")
    handshake = verify_symbolic_statement("验证握手定理：度数和=2*边数，边数=3，度数和=6")

    assert complete_graph.checked is True
    assert complete_graph.valid is True
    assert "graph formula" in complete_graph.detail
    assert handshake.checked is True
    assert handshake.valid is True


def test_evaluate_reasoning_answer_scores_structure_and_evidence():
    answer = """
    已知：P,Q为命题。
    分析：使用真值表法。
    推导：步骤1：P->Q 与 ¬P∨Q 真值一致。依据：蕴含定义。
    自检：结论与目标一致。
    结论：P->Q = ¬P∨Q。
    证毕。
    """

    report = evaluate_reasoning_answer(answer)

    assert report.score == 100
    assert report.passed is True
    assert report.checks["has_reason"] is True
    assert report.symbolic_expression_count >= 2


def test_induction_answers_require_induction_structure():
    complete = """
    已知：n为正整数。分析：使用数学归纳法。
    推导：基础步：n=1成立。依据：代入计算。
    归纳假设：假设n=k时成立。
    归纳步：证明n=k+1时成立。
    自检：归纳法三部分完整。结论：命题成立。证毕。
    """
    incomplete = "已知：n为正整数。推导：直接可得。结论：成立。证毕。"

    assert evaluate_reasoning_answer(complete, question="用数学归纳法证明求和公式").passed is True
    assert evaluate_reasoning_answer(incomplete, question="用数学归纳法证明求和公式").passed is False


def test_reasoning_questions_use_larger_answer_budget():
    assert answer_token_limit("证明德摩根律") == 1400
    assert answer_token_limit("什么是集合？") == 800


def test_longer_answers_use_larger_request_timeout():
    assert request_timeout(1400) > request_timeout(800)


def test_compact_context_limits_reference_size():
    compacted = compact_context("a" * 900, limit=100)

    assert len(compacted) <= 103
    assert compacted.endswith("...")


def test_filter_reasoning_contexts_prefers_domain_sources_over_mapping_noise():
    results = [
        {"score": 0.70, "metadata": {"source_document": "题库节点映射.md"}, "content": "节点映射表"},
        {"score": 0.62, "metadata": {"source_document": "命题逻辑.md"}, "content": "德摩根律定义与证明"},
        {"score": 0.60, "metadata": {"source_document": "选择题题库.md"}, "content": "选择题"},
        {"score": 0.58, "metadata": {"source_document": "证明题库_命题逻辑.md"}, "content": "证明题示例"},
    ]

    filtered = filter_reasoning_contexts("证明命题逻辑中的德摩根律", results, limit=3)

    assert [item["metadata"]["source_document"] for item in filtered] == [
        "命题逻辑.md",
        "证明题库_命题逻辑.md",
        "题库节点映射.md",
    ]


def test_symbolic_check_note_reports_verified_result():
    note = symbolic_check_note("证明命题逻辑等价式：P->Q = ¬P∨Q")

    assert "程序侧符号校验结果：通过" in note
    assert "truth table" in note



def test_build_proof_plan_for_set_identity_uses_element_method():
    from backend.reasoning.service import build_proof_plan

    plan = build_proof_plan("\u8bc1\u660e\u96c6\u5408\u6052\u7b49\u5f0f\uff1a(A\u222aB)^c = A^c\u2229B^c")

    assert plan.enabled is True
    assert plan.method == "element_chasing"
    assert any("\u4efb\u53d6\u5143\u7d20" in step for step in plan.steps)
    assert any("\u53cd\u5411" in step for step in plan.steps)
    assert plan.symbolic_check.checked is True


def test_build_proof_plan_for_relation_transitivity_includes_counterexample():
    from backend.reasoning.service import build_proof_plan

    plan = build_proof_plan("\u5224\u65ad\u5173\u7cfb R={(1,2),(2,3)} \u662f\u5426\u4f20\u9012\uff0c\u5e76\u8bf4\u660e\u7406\u7531")

    assert plan.enabled is True
    assert plan.method == "relation_property_check"
    assert any("(a,b),(b,c)" in step for step in plan.steps)
    assert "missing" in plan.symbolic_check.evidence
    assert plan.symbolic_check.valid is False


def test_build_proof_plan_for_general_question_is_disabled():
    from backend.reasoning.service import build_proof_plan

    plan = build_proof_plan("\u4ec0\u4e48\u662f\u96c6\u5408\uff1f")

    assert plan.enabled is False
    assert plan.method == "none"
    assert plan.steps == []

def test_quantifier_negation_is_symbolically_checked():
    from backend.reasoning.service import verify_symbolic_statement

    result = verify_symbolic_statement("证明量词否定律：¬∀xP(x) ⇔ ∃x¬P(x)")

    assert result.checked is True
    assert result.valid is True
    assert "quantifier negation" in result.detail
    assert "not all" in result.evidence


def test_build_proof_plan_for_quantifier_negation_uses_quantifier_transform():
    from backend.reasoning.service import build_proof_plan

    plan = build_proof_plan("证明量词否定律：¬∃xP(x) ⇔ ∀x¬P(x)")

    assert plan.enabled is True
    assert plan.method == "quantifier_transformation"
    assert any("量词" in step for step in plan.steps)
    assert any("否定" in step for step in plan.steps)
    assert plan.symbolic_check.checked is True

def test_warshall_transitive_closure_for_relation_matrix():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "求关系矩阵 [[0,1,0],[0,0,1],[0,0,0]] 的传递闭包"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "Warshall" in result.detail
    assert "[[0, 1, 1], [0, 0, 1], [0, 0, 0]]" in result.evidence
    assert plan.method == "transitive_closure"


def test_partial_order_checker_reports_all_required_properties():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "判断 A={1,2,3} 上关系 R={(1,1),(2,2),(3,3),(1,2),(1,3),(2,3)} 是否为偏序关系"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "partial order" in result.detail
    assert "reflexive=True" in result.evidence
    assert "antisymmetric=True" in result.evidence
    assert "transitive=True" in result.evidence
    assert plan.method == "partial_order_check"


def test_equivalence_relation_checker_returns_partition():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "判断 A={1,2,3} 上关系 R={(1,1),(2,2),(3,3),(1,2),(2,1)} 是否为等价关系并给出划分"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "equivalence relation" in result.detail
    assert "partition={{1,2},{3}}" in result.evidence
    assert plan.method == "equivalence_partition"


def test_boolean_simplification_checker_uses_symbolic_normal_form():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "化简布尔表达式：P∧(P∨Q) = P"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "boolean normal form" in result.detail
    assert "equivalent=True" in result.evidence
    assert plan.method == "boolean_simplification"


def test_combination_identity_checker_verifies_pascal_rule():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "证明组合恒等式 C(5,2)+C(5,3)=C(6,3)"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "combination identity" in result.detail
    assert "10 + 10 = 20" in result.evidence
    assert plan.method == "combination_identity"


def test_tree_edge_count_checker_verifies_basic_tree_property():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "判断树有 8 个顶点，边数为 7 是否正确"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "tree edge count" in result.detail
    assert "n-1=7" in result.evidence
    assert plan.method == "tree_edge_count"


def test_euler_graph_checker_verifies_all_degrees_even():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "判断无向图度数序列 [2,4,2,6] 是否存在欧拉回路"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "Euler circuit" in result.detail
    assert "all_even=True" in result.evidence
    assert plan.method == "euler_graph_check"


def test_propositional_satisfiability_checker_finds_model():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "判断命题公式 P∧¬Q 是否可满足"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "satisfiability" in result.detail
    assert "model=" in result.evidence
    assert "P=True" in result.evidence
    assert "Q=False" in result.evidence
    assert plan.method == "sat_check"


def test_propositional_entailment_checker_finds_countermodel():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "判断 P 是否蕴含 Q"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is False
    assert "entailment" in result.detail
    assert "countermodel=" in result.evidence
    assert "P=True" in result.evidence
    assert "Q=False" in result.evidence
    assert plan.method == "entailment_check"


def test_relation_pair_transitive_closure_returns_new_pairs():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "求 A={1,2,3} 上关系 R={(1,2),(2,3)} 的传递闭包"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "transitive closure" in result.detail
    assert "closure={(1,2),(1,3),(2,3)}" in result.evidence
    assert "added={(1,3)}" in result.evidence
    assert plan.method == "transitive_closure"


def test_boolean_matrix_square_checker_computes_relation_composition():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "计算关系矩阵 [[0,1,0],[0,0,1],[0,0,0]] 的布尔平方"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "boolean matrix square" in result.detail
    assert "[[0, 0, 1], [0, 0, 0], [0, 0, 0]]" in result.evidence
    assert plan.method == "boolean_matrix_power"



def test_relation_reflexive_closure_returns_missing_diagonal_pairs():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "\u6c42 A={1,2,3} \u4e0a\u5173\u7cfb R={(1,2),(2,2)} \u7684\u81ea\u53cd\u95ed\u5305"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "reflexive closure" in result.detail
    assert "closure={(1,1),(1,2),(2,2),(3,3)}" in result.evidence
    assert "added={(1,1),(3,3)}" in result.evidence
    assert plan.method == "reflexive_closure"


def test_relation_symmetric_closure_returns_reverse_pairs():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "\u6c42 A={1,2,3} \u4e0a\u5173\u7cfb R={(1,2),(2,3)} \u7684\u5bf9\u79f0\u95ed\u5305"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "symmetric closure" in result.detail
    assert "closure={(1,2),(2,1),(2,3),(3,2)}" in result.evidence
    assert "added={(2,1),(3,2)}" in result.evidence
    assert plan.method == "symmetric_closure"


def test_propositional_dnf_checker_generates_canonical_terms():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "\u6c42\u547d\u9898\u516c\u5f0f P\u2227\u00acQ \u7684\u4e3b\u6790\u53d6\u8303\u5f0f"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "canonical DNF" in result.detail
    assert "dnf=(P&!Q)" in result.evidence
    assert "true_rows=1" in result.evidence
    assert plan.method == "normal_form_conversion"


def test_propositional_cnf_checker_generates_canonical_clauses():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "\u6c42\u547d\u9898\u516c\u5f0f P\u2228Q \u7684\u4e3b\u5408\u53d6\u8303\u5f0f"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "canonical CNF" in result.detail
    assert "cnf=(P|Q)" in result.evidence
    assert "false_rows=1" in result.evidence
    assert plan.method == "normal_form_conversion"



def test_relation_composition_checker_composes_two_relations():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "\u6c42 A={1,2,3} \u4e0a R={(1,2),(2,3)} \u548c S={(2,3),(3,1)} \u7684\u5173\u7cfb\u590d\u5408 S\u2218R"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "relation composition" in result.detail
    assert "composition={(1,3),(2,1)}" in result.evidence
    assert "witnesses=(1,2,3),(2,3,1)" in result.evidence
    assert plan.method == "relation_composition"



def test_inverse_relation_checker_reverses_ordered_pairs():
    from backend.reasoning.service import build_proof_plan, verify_symbolic_statement

    question = "\u6c42 A={1,2,3} \u4e0a\u5173\u7cfb R={(1,2),(2,3),(3,3)} \u7684\u9006\u5173\u7cfb R^{-1}"
    result = verify_symbolic_statement(question)
    plan = build_proof_plan(question)

    assert result.checked is True
    assert result.valid is True
    assert "inverse relation" in result.detail
    assert "inverse={(2,1),(3,2),(3,3)}" in result.evidence
    assert plan.method == "inverse_relation"


def test_boolean_simplification_uses_sympy_when_available():
    import importlib.util
    from backend.reasoning.service import verify_symbolic_statement

    if importlib.util.find_spec("sympy") is None:
        return

    result = verify_symbolic_statement("\u5316\u7b80\u5e03\u5c14\u516c\u5f0f P\u2227Q \u2228 P\u2227\u00acQ = P")

    assert result.checked is True
    assert result.valid is True
    assert "SymPy" in result.detail
    assert "simplified_left=P" in result.evidence


def test_propositional_normal_form_uses_sympy_when_available():
    import importlib.util
    from backend.reasoning.service import verify_symbolic_statement

    if importlib.util.find_spec("sympy") is None:
        return

    result = verify_symbolic_statement("\u6c42\u547d\u9898\u516c\u5f0f \u00ac(P\u2227Q) \u7684\u4e3b\u5408\u53d6\u8303\u5f0f")

    assert result.checked is True
    assert result.valid is True
    assert "SymPy" in result.detail
    assert "cnf=!P|!Q" in result.evidence


def test_sat_checker_marks_truth_table_fallback_without_z3():
    import sys
    from backend.reasoning.service import verify_symbolic_statement

    if "z3" in sys.modules:
        return

    result = verify_symbolic_statement("\u5224\u65ad\u547d\u9898\u516c\u5f0f P\u2227\u00acQ \u662f\u5426\u53ef\u6ee1\u8db3")

    assert result.checked is True
    assert result.valid is True
    assert "backend=truth_table" in result.evidence


def test_sat_checker_detail_names_z3_backend_when_available():
    import importlib.util
    from backend.reasoning.service import verify_symbolic_statement

    if importlib.util.find_spec("z3") is None:
        return

    result = verify_symbolic_statement("\u5224\u65ad\u547d\u9898\u516c\u5f0f P\u2227\u00acQ \u662f\u5426\u53ef\u6ee1\u8db3")

    assert result.checked is True
    assert result.valid is True
    assert "backend=z3" in result.evidence
    assert "z3" in result.detail
