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
