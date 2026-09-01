"""
练习题目 API
============

从知识库题库文档动态生成自测练习选择题。

数据源:
    1. data/documents/选择题题库.md     — 24 道现成选择题（题干/选项/答案/解析）
    2. data/documents/老师训练题库.json  — 老师提供的 112 题中的填空题，转换为选择题
                                             （正确答案 + 从答案池抽取的干扰项）

设计动机:
    自测练习前端原本只有硬编码的几道题。这里把知识库文档变成“活的题库”：
    后续往这些文档里补充题目，自测练习即可自动变丰富，无需改前端代码。

端点:
    GET /api/practice/questions?module=xxx — 返回练习题目列表
"""

import json
import logging
import os
import random
import re
import time
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.practice.ocr import OCRInputError, OCRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/practice", tags=["Practice"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS_DIR = os.path.join(BASE_DIR, "data", "documents")
QUIZ_BANK_FILE = os.path.join(DOCS_DIR, "选择题题库.md")
TEACHER_QUIZ_FILE = os.path.join(DOCS_DIR, "老师训练题库.json")

# 选择题题库.md 章节 → 前端模块值（与 index.html 的 practice-filter 一致）
CHAPTER_MODULE = {
    "命题逻辑": ("propositional_logic", "命题逻辑", "pl_01_01"),
    "谓词逻辑": ("predicate_logic", "谓词逻辑", "fl_01_01"),
    "集合论": ("set_theory", "集合论", "st_01_01"),
    "关系": ("relations", "关系", "rel_01_01"),
    "图论": ("graph_theory", "图论", "gt_01_01"),
    "初等数论": ("number_theory", "初等数论", "nt_01_01"),
    "代数结构": ("algebraic_structure", "代数结构", "ag_01_01"),
    "数学归纳法": ("induction", "数学归纳法", "mi_01_01"),
}

# 老师训练题库 kp → (module, moduleName, node_id)
KP_NODE = {
    # 命题逻辑
    "prop-logic": ("propositional_logic", "命题逻辑", "pl_01_02"),
    "normal-form": ("propositional_logic", "命题逻辑", "pl_03_01"),
    "inference": ("propositional_logic", "命题逻辑", "pl_03_05"),
    # 谓词逻辑
    "pred-logic": ("predicate_logic", "谓词逻辑", "fl_01_02"),
    # 集合论
    "set-ops": ("set_theory", "集合论", "st_02_01"),
    "function": ("set_theory", "集合论", "st_01_01"),
    "cardinality": ("set_theory", "集合论", "st_01_03"),
    "ie-set": ("set_theory", "集合论", "st_02_05"),
    # 关系
    "relation": ("relations", "关系", "rel_02_01"),
    # 图论
    "graph-basic": ("graph_theory", "图论", "gt_01_01"),
    "connectivity": ("graph_theory", "图论", "gt_02_04"),
    "planar": ("graph_theory", "图论", "gt_01_01"),
    "hamilton": ("graph_theory", "图论", "gt_04_02"),
    "spanning-tree": ("graph_theory", "图论", "gt_04_04"),
    "coloring": ("graph_theory", "图论", "gt_04_03"),
    "digraph": ("graph_theory", "图论", "gt_01_01"),
    # 扩展专题（数论/组合/代数）— 独立类别，与知识图谱 6 大模块并列
    "gcd": ("number_theory", "初等数论", "nt_01_01"),
    "congruence": ("number_theory", "初等数论", "nt_02_01"),
    "combinatorics": ("combinatorics", "组合数学", "cm_01_01"),
    "inclusion-exclusion": ("combinatorics", "组合数学", "cm_02_01"),
    "gen-func": ("combinatorics", "组合数学", "cm_03_01"),
    "recurrence": ("combinatorics", "组合数学", "cm_04_01"),
    "polya": ("combinatorics", "组合数学", "cm_05_01"),
    "algebra": ("algebraic_structure", "代数结构", "ag_01_01"),
    "group": ("algebraic_structure", "代数结构", "ag_02_01"),
    "semigroup": ("algebraic_structure", "代数结构", "ag_03_01"),
    "homomorphism": ("algebraic_structure", "代数结构", "ag_04_01"),
}


def _clean_math(s: str) -> str:
    """清理 LaTeX 中的换行/多余空白，保持可读。"""
    s = s.replace("<br>", " ").replace("<br/>", " ").replace("\\", "\\")
    return re.sub(r"\s+", " ", s).strip()


def parse_quiz_bank_md() -> List[Dict]:
    """解析 选择题题库.md，返回选择题列表。"""
    if not os.path.exists(QUIZ_BANK_FILE):
        logger.warning(f"选择题题库文件不存在: {QUIZ_BANK_FILE}")
        return []
    with open(QUIZ_BANK_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    questions: List[Dict] = []
    section = None
    # 按章节切分
    blocks = re.split(r"^##\s+(.+)$", content, flags=re.M)
    # blocks = [前导, 章节名, 内容, 章节名, 内容, ...]
    for i in range(1, len(blocks) - 1, 2):
        section = blocks[i].strip()
        body = blocks[i + 1]
        mod, mod_name, node_id = CHAPTER_MODULE.get(section, ("other", section, "ot_01_01"))
        # 逐个题块
        for m in re.finditer(r"\*\*(Q\d+)\*\*\s*(.*?)(?=\n\*\*Q\d+\*\*|\Z)", body, re.S):
            qid, block = m.group(1), m.group(2)
            lines = block.strip().split("\n")
            if not lines:
                continue
            question = lines[0].strip()
            rest = "\n".join(lines[1:])

            ans_match = re.search(r"答案[:：]\s*([A-D])", rest)
            exp_match = re.search(r"解析[:：]\s*(.+?)(?=\n\s*\n|\Z)", rest, re.S)
            if not ans_match:
                continue
            answer_letter = ans_match.group(1)

            # 选项区 = rest 去掉 答案/解析 行
            opts_text = re.sub(r"答案[:：].*", "", rest)
            opts_text = re.sub(r"解析[:：].*", "", opts_text, flags=re.S)
            options = parse_mc_options(opts_text)
            if not options or answer_letter not in options:
                continue

            # 统一为选项数组 + 答案索引
            letters = sorted(options.keys())
            option_list = [options[ch] for ch in letters]
            answer_idx = letters.index(answer_letter)
            explanation = exp_match.group(1).strip() if exp_match else ""

            questions.append({
                "id": f"q_bank_{section}_{qid}",
                "module": mod,
                "moduleName": mod_name,
                "nodeId": node_id,
                "nodeName": section,
                "type": "single",
                "question": question,
                "options": option_list,
                "answer": answer_idx,
                "explanation": explanation,
            })
    return questions


def parse_mc_options(text: str) -> Dict[str, str]:
    """把 'A. xxx  B. yyy  C. zzz  D. wwww'（可多行）拆成 {A: xxx, ...}。"""
    text = text.replace("\n", " ")
    parts = re.split(r"(?=[A-D][\.．、]\s)", text.strip())
    opts: Dict[str, str] = {}
    for p in parts:
        m = re.match(r"([A-D])[\.．、]\s*(.*)", p.strip())
        if m and m.group(2).strip():
            opts[m.group(1)] = m.group(2).strip()
    return opts


def load_teacher_fill_questions() -> List[Dict]:
    """从老师训练题库.json 提取填空题，转换为选择题。"""
    if not os.path.exists(TEACHER_QUIZ_FILE):
        logger.warning(f"老师训练题库文件不存在: {TEACHER_QUIZ_FILE}")
        return []
    with open(TEACHER_QUIZ_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 答案池（干扰项来源）
    answer_pool = []
    for exam in data.get("exams", []):
        for item in exam.get("fill", []):
            clean = _clean_math(item.get("a", ""))
            if clean:
                answer_pool.append(clean)
    answer_pool = list(dict.fromkeys(answer_pool))  # 去重保序

    questions: List[Dict] = []
    for exam in data.get("exams", []):
        for idx, item in enumerate(exam.get("fill", []), 1):
            q_text = _clean_math(item.get("q", ""))
            correct = _clean_math(item.get("a", ""))
            kp = item.get("kp", "")
            if not q_text or not correct:
                continue
            mod, mod_name, node_id = KP_NODE.get(kp, ("other", "其他", "ot_01_01"))

            # 干扰项：从答案池抽 3 个不同项
            distractors = random.sample(
                [a for a in answer_pool if a != correct],
                k=min(3, len([a for a in answer_pool if a != correct])),
            )
            while len(distractors) < 3:
                distractors.append("以上都不对")
            options = [correct] + distractors
            random.shuffle(options)
            answer_idx = options.index(correct)

            questions.append({
                "id": f"q_teacher_{exam.get('id', '?')}_{idx}",
                "module": mod,
                "moduleName": mod_name,
                "nodeId": node_id,
                "nodeName": mod_name,
                "type": "single",
                "question": q_text,
                "options": options,
                "answer": answer_idx,
                "explanation": f"参考答案：{correct}",
            })
    return questions


@router.get("/questions")
def get_practice_questions(
    module: Optional[str] = Query(default=None, description="按模块过滤"),
) -> Dict:
    """返回自测练习题目（选择题格式，前端可直接渲染）。"""
    questions = parse_quiz_bank_md() + load_teacher_fill_questions()
    if module and module != "all":
        questions = [q for q in questions if q["module"] == module]

    # 稳定排序：先按模块（与知识图谱 6 模块 + 3 扩展专题对齐），再按原顺序
    mod_order = {
        "propositional_logic": 0, "predicate_logic": 1, "set_theory": 2,
        "induction": 3, "relations": 4, "graph_theory": 5,
        "number_theory": 6, "combinatorics": 7, "algebraic_structure": 8,
    }
    questions.sort(key=lambda q: (mod_order.get(q["module"], 9), q["id"]))
    return {"total": len(questions), "questions": questions}


@router.get("/coverage")
def get_practice_coverage() -> Dict:
    """自测练习覆盖的知识点统计（学情面板：总知识点数 = 练习覆盖数）。

    返回:
        total_nodes: 覆盖的 node_id 总数（去重）
        total_questions: 题目总数
        by_module: {模块: {name, nodes, questions}}
        node_ids: 全部 node_id 列表
    """
    questions = parse_quiz_bank_md() + load_teacher_fill_questions()
    by_module: Dict[str, Dict] = {}
    node_ids: List[str] = []
    for q in questions:
        mod = q["module"]
        bucket = by_module.setdefault(mod, {"name": q["moduleName"], "nodes": set(), "questions": 0})
        bucket["nodes"].add(q["nodeId"])
        bucket["questions"] += 1
        node_ids.append(q["nodeId"])
    modules = [
        {"module": mod, "name": b["name"], "nodes": len(b["nodes"]), "questions": b["questions"]}
        for mod, b in by_module.items()
    ]
    unique_nodes = list(dict.fromkeys(node_ids))
    return {
        "total_nodes": len(unique_nodes),
        "total_questions": len(questions),
        "by_module": modules,
        "node_ids": unique_nodes,
    }


# ==================== 证明题 / 填空题 / OCR 拍照识别 ====================

OCR_MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"  # OCR 专用视觉模型（约 1-3s/张）


class OCRRequest(BaseModel):
    image_base64: str = Field(..., description="图片 base64（不含 data: 前缀）")
    filename: str = Field(default="photo.png", description="文件名（用于推断图片类型）")


class GradeFillRequest(BaseModel):
    question_id: str = Field(..., description="题目 id（如 e1_fill_3）")
    student_answer: str = Field(..., description="学生填写的答案")


def _load_teacher_exams() -> List[Dict]:
    if not os.path.exists(TEACHER_QUIZ_FILE):
        return []
    with open(TEACHER_QUIZ_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("exams", [])


def _find_teacher_item(question_id: str) -> Optional[Dict]:
    """按 id（e{exam}_{type}_{idx}）从老师题库定位题目。"""
    parts = question_id.split("_")
    if len(parts) != 3 or not parts[0].startswith("e"):
        return None
    exam_no, qtype, idx = int(parts[0][1:]), parts[1], int(parts[2])
    for exam in _load_teacher_exams():
        if exam.get("id") == exam_no:
            items = exam.get(qtype, [])
            if 1 <= idx <= len(items):
                return items[idx - 1]
    return None


@router.post("/ocr")
def ocr_image(req: OCRRequest) -> Dict:
    """对手写证明或计算过程做图像增强、公式 OCR 和低质量重试。"""
    try:
        return OCRService(model=OCR_MODEL).recognize(req.image_base64)
    except OCRInputError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("OCR 失败: %s", exc)
        return {"ok": False, "error": f"OCR 识别失败: {str(exc)[:120]}"}


@router.get("/proof-questions")
def get_proof_questions(limit: int = 16) -> Dict:
    """返回证明题（老师训练题库），供「证明题拍照作答」区使用。

    每题含标准答案（前端在学生提交后展示对照）。
    """
    questions = []
    for exam in _load_teacher_exams():
        for idx, item in enumerate(exam.get("proof", []), 1):
            kp = item.get("kp", "")
            mod, mod_name, node_id = KP_NODE.get(kp, ("other", "其他", "ot_01_01"))
            questions.append({
                "id": f"e{exam['id']}_proof_{idx}",
                "question": item["q"],
                "answer": item["a"],
                "kp": kp,
                "module": mod,
                "moduleName": mod_name,
                "nodeId": node_id,
                "fig": item.get("fig"),
            })
    questions = questions[:limit]
    return {"total": len(questions), "questions": questions}


@router.get("/calc-questions")
def get_calc_questions(limit: int = 16) -> Dict:
    """返回计算题，供自测中的拍照作答和自动批阅使用。"""
    questions = []
    for exam in _load_teacher_exams():
        for idx, item in enumerate(exam.get("calc", []), 1):
            kp = item.get("kp", "")
            mod, mod_name, node_id = KP_NODE.get(kp, ("other", "其他", "ot_01_01"))
            questions.append({
                "id": f"e{exam['id']}_calc_{idx}",
                "question": item["q"],
                "answer": item["a"],
                "kp": kp,
                "module": mod,
                "moduleName": mod_name,
                "nodeId": node_id,
                "fig": item.get("fig"),
            })
    questions = questions[:limit]
    return {"total": len(questions), "questions": questions}


@router.get("/fill-questions")
def get_fill_questions(limit: int = 28) -> Dict:
    """返回填空题（老师训练题库原题，学生输入答案）。"""
    questions = []
    for exam in _load_teacher_exams():
        for idx, item in enumerate(exam.get("fill", []), 1):
            kp = item.get("kp", "")
            mod, mod_name, node_id = KP_NODE.get(kp, ("other", "其他", "ot_01_01"))
            questions.append({
                "id": f"e{exam['id']}_fill_{idx}",
                "question": item["q"],
                "answer": item["a"],
                "kp": kp,
                "module": mod,
                "moduleName": mod_name,
                "nodeId": node_id,
            })
    questions = questions[:limit]
    return {"total": len(questions), "questions": questions}


@router.post("/grade-fill")
def grade_fill(req: GradeFillRequest) -> Dict:
    """填空题判定：大模型对照标准答案判断学生答案是否正确。"""
    item = _find_teacher_item(req.question_id)
    if not item:
        return {"ok": False, "error": "题目不存在"}
    student = req.student_answer.strip()
    if not student:
        return {"ok": False, "error": "答案为空"}

    try:
        from backend.chat.llm import OpenAICompatibleLLM
        llm = OpenAICompatibleLLM()
        prompt = (
            "你是一名离散数学阅卷教师。请判断学生答案与标准答案是否数学上等价（允许不同写法/等价变换）。\n\n"
            f"【题目】\n{item['q']}\n\n"
            f"【标准答案】\n{item['a']}\n\n"
            f"【学生答案】\n{student}\n\n"
            '请只输出 JSON：{"correct": true或false, "comment": "一两句评语"}'
        )
        t0 = time.time()
        judge = llm.generate([{"role": "user", "content": prompt}])
        start = judge.find("{")
        end = judge.rfind("}")
        parsed = {}
        if start != -1 and end != -1:
            try:
                parsed = json.loads(judge[start:end + 1])
            except json.JSONDecodeError:
                parsed = {}
        return {
            "ok": True,
            "correct": bool(parsed.get("correct", False)),
            "comment": parsed.get("comment", ""),
            "reference": item["a"],
            "seconds": round(time.time() - t0, 1),
        }
    except Exception as exc:
        return {"ok": False, "error": f"判定失败: {str(exc)[:120]}"}
