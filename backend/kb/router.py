"""
知识库 API 路由
===============

提供知识库管理的 RESTful API 端点。

端点列表:
    POST   /kb/ingest          — 上传文档并自动处理（解析→分块→向量化→存储）
    GET    /kb/search           — 知识库检索
    GET    /kb/documents         — 已索引文档列表
    DELETE /kb/documents/{name} — 删除指定文档
    GET    /kb/stats            — 知识库统计信息
    GET    /kb/health           — 健康检查
"""

import os
import json
import logging
import tempfile
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from fastapi.responses import JSONResponse

from backend.kb.schemas import (
    KBSearchResponse,
    KBDocumentInfo,
    KBDocumentListResponse,
    KBStatsResponse,
    KBHealthResponse,
    KBIngestResponse,
)
from backend.kb.loader import DocumentLoader
from backend.kb.chunker import SmartChunker
from backend.kb.embedder import EmbeddingService
from backend.kb.vector_store import KnowledgeBaseStore
from backend.kb.retriever import KnowledgeBaseRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["知识库"])

# 全局单例（在 api.py 启动时初始化）
_embedding_service: Optional[EmbeddingService] = None
_vector_store: Optional[KnowledgeBaseStore] = None
_retriever: Optional[KnowledgeBaseRetriever] = None
_loader = DocumentLoader()
_chunker = SmartChunker()


def init_kb(embedding_service: Optional[EmbeddingService] = None,
            vector_store: Optional[KnowledgeBaseStore] = None):
    """初始化知识库模块（由 api.py 在启动时调用）"""
    global _embedding_service, _vector_store, _retriever

    _embedding_service = embedding_service or EmbeddingService()
    _vector_store = vector_store or KnowledgeBaseStore(
        embedding_service=_embedding_service,
    )
    _retriever = KnowledgeBaseRetriever(_vector_store, _embedding_service)

    logger.info("知识库模块初始化完成")


def get_retriever() -> KnowledgeBaseRetriever:
    if _retriever is None:
        init_kb()
    return _retriever  # type: ignore


def get_store() -> KnowledgeBaseStore:
    if _vector_store is None:
        init_kb()
    return _vector_store  # type: ignore


# ==================== 端点 ====================

@router.get("/search", response_model=KBSearchResponse)
async def search_knowledge_base(
    q: str = Query(..., min_length=1, max_length=1000, description="搜索查询"),
    top_k: int = Query(default=5, ge=1, le=50, description="返回结果数"),
    min_score: float = Query(default=0.5, ge=0.0, le=1.0, description="最小相似度阈值"),
    chapter: Optional[str] = Query(default=None, description="按章节过滤"),
    chunk_type: Optional[str] = Query(default=None, description="按块类型过滤"),
):
    """
    知识库语义检索。

    **队员3 调用此接口获取检索结果，用于 RAG 问答链路。**

    返回与查询最相关的内容块及其元数据（章节、页码、来源文档），
    队员3 将 content 拼接后发送给 LLM，并在回答中引用 metadata 中的来源信息。
    """
    retriever = get_retriever()
    result = retriever.retrieve(
        query=q,
        top_k=top_k,
        min_score=min_score,
        chapter=chapter,
        chunk_type=chunk_type,
    )
    return KBSearchResponse(**result)


@router.post("/ingest", response_model=KBIngestResponse)
async def ingest_document(file: UploadFile = File(...)):
    """
    上传文档并自动处理：解析 → 分块 → 向量化 → 存储。

    支持格式: PDF, Word (.docx/.doc), TXT, Markdown (.md)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # 保存上传文件到临时目录
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in DocumentLoader.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}。支持: {DocumentLoader.SUPPORTED_EXTENSIONS}"
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    errors = []
    try:
        # Step 1: 解析文档
        parsed = _loader.load(tmp_path)

        # Step 2: 分块
        chunks = _chunker.chunk(parsed)

        # Step 3: 向量化并存储
        store = get_store()
        chunk_count = store.index_chunks(chunks)

        chapters_found = [ch.title for ch in parsed.chapters if ch.level == 1]

        status = "success" if not parsed.errors else "partial"

        return KBIngestResponse(
            filename=file.filename,
            status=status,
            chunks_created=chunk_count,
            total_pages=parsed.total_pages,
            chapters_found=chapters_found,
            errors=parsed.errors + errors,
        )
    except Exception as e:
        logger.error(f"文档处理失败: {e}", exc_info=True)
        return KBIngestResponse(
            filename=file.filename,
            status="error",
            chunks_created=0,
            total_pages=0,
            chapters_found=[],
            errors=[str(e)],
        )
    finally:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.get("/documents", response_model=KBDocumentListResponse)
async def list_documents():
    """列出已索引的文档列表"""
    store = get_store()
    docs = store.get_documents()
    doc_infos = [KBDocumentInfo(**d) for d in docs]
    return KBDocumentListResponse(documents=doc_infos, total=len(doc_infos))


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    """删除指定文档的所有知识块"""
    store = get_store()
    deleted = store.delete_document(filename)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"文档 '{filename}' 未找到")
    return {"filename": filename, "deleted_chunks": deleted, "status": "success"}


@router.get("/stats", response_model=KBStatsResponse)
async def get_stats():
    """获取知识库统计信息"""
    store = get_store()
    stats = store.get_stats()
    return KBStatsResponse(**stats)


@router.get("/health", response_model=KBHealthResponse)
async def health_check():
    """知识库健康检查"""
    try:
        store = get_store()
        stats = store.get_stats()
        return KBHealthResponse(
            status="ok",
            chroma_connected=True,
            embedding_model=stats.get("embedding_model", "unknown"),
            total_chunks_indexed=stats.get("total_chunks", 0),
        )
    except Exception as e:
        return KBHealthResponse(
            status="error",
            chroma_connected=False,
            embedding_model="unknown",
            total_chunks_indexed=0,
        )


# ==================== 知识图谱端点 ====================

def _generate_mastery_levels(node_type: str, text: str) -> dict:
    """根据节点类型和内容自动生成五级掌握度描述"""
    topic = text[:30]
    levels = {
        "definition": {
            "0": f"从未接触过「{topic}」这个概念",
            "1": f"听说过「{topic}」，能说出名称",
            "2": f"理解「{topic}」的含义，能用自己的话解释",
            "3": f"能准确默写「{topic}」的定义，能举出正例和反例",
            "4": f"能灵活运用「{topic}」解决综合问题，能辨析易混淆概念",
        },
        "theorem": {
            "0": f"未学过「{topic}」",
            "1": f"知道「{topic}」这个定理的名称",
            "2": f"理解「{topic}」的内容和适用条件",
            "3": f"能独立证明「{topic}」，能举例说明应用场景",
            "4": f"能灵活运用「{topic}」证明其他结论，能分析证明思路",
        },
        "example": {
            "0": f"未接触过该例题所考察的知识点",
            "1": f"看过类似例题，能理解答案",
            "2": f"能独立完成该例题，但速度较慢",
            "3": f"能快速完成该例题，并能修改条件举一反三",
            "4": f"能自编类似例题，能给他人讲解解题思路",
        },
        "rule": {
            "0": f"未学过「{topic}」这条推理规则",
            "1": f"知道有「{topic}」这条规则",
            "2": f"理解「{topic}」的推理逻辑和适用条件",
            "3": f"能正确使用「{topic}」进行推理，能判断何时适用",
            "4": f"能综合运用多条规则进行复杂推理，能分析推理有效性",
        },
    }
    template = levels.get(node_type, levels["definition"])
    return {
        "0_未学": template["0"],
        "1_了解": template["1"],
        "2_理解": template["2"],
        "3_掌握": template["3"],
        "4_熟练": template["4"],
    }


# 知识图谱结构化数据（模块级常量，供图谱端点和强定义检索共用）
KG_DATA = {
        "modules": [
            {
                "id": "propositional_logic",
                "name": "命题逻辑",
                "description": "命题逻辑（命题演算、零阶逻辑）是数理逻辑的基础，研究命题（具有唯一真值的陈述句）之间的逻辑关系。它定义命题联结词（¬ ∧ ∨ → ↔）的真值规则，给出逻辑等价、重言式、范式等核心概念，并建立假言推理、拒取式等有效推理规则。命题逻辑是后续谓词逻辑、集合论、自动定理证明的推理语言基础。",
                "search_query": "命题逻辑 命题 联结词 基本概念",
                "children": [
                    {
                        "name": "命题与联结词",
                        "node_id": "pl_01",
                        "description": "命题逻辑的入门基础。介绍命题的定义（有唯一真值的陈述句）与判断方法，给出五种基本联结词（¬否定、∧合取、∨析取、→蕴含、↔等价）的符号、含义与真值规则，并通过例题展示命题与联结词在自然语言中的识别。",
                        "search_query": "什么是命题 联结词有哪些 命题的定义",
                        "items": [
                            {"type": "definition", "node_id": "pl_01_01", "text": "命题：具有确定真值的陈述句", "search_query": "命题的定义 什么是命题"},
                            {"type": "definition", "node_id": "pl_01_02", "text": "联结词：¬否定、∧合取、∨析取、→蕴含、↔等价", "search_query": "联结词有哪些 否定合取析取蕴含等价"},
                            {"type": "example", "node_id": "pl_01_03", "text": "'北京是首都'是真命题；'你好吗？'不是命题", "search_query": "命题的例子 真命题假命题"},
                        ],
                    },
                    {
                        "name": "真值表与逻辑等价",
                        "node_id": "pl_02",
                        "description": "用真值表刻画命题公式在所有赋值组合下的真值，定义逻辑等价关系（两个公式在所有赋值下真值相同则等价）。重点推导与应用：德摩根律、蕴含等价、等价转化、吸收律等。",
                        "search_query": "真值表 逻辑等价 德摩根律",
                        "items": [
                            {"type": "definition", "node_id": "pl_02_01", "text": "真值表：列出所有赋值下公式真值的表格", "search_query": "真值表怎么列 真值表定义"},
                            {"type": "theorem", "node_id": "pl_02_02", "text": "德摩根律：¬(P∧Q)≡¬P∨¬Q；¬(P∨Q)≡¬P∧¬Q", "search_query": "证明德摩根律 德摩根律是什么"},
                            {"type": "theorem", "node_id": "pl_02_03", "text": "蕴含等价：P→Q≡¬P∨Q", "search_query": "蕴含式的等价形式 P→Q≡¬P∨Q"},
                            {"type": "definition", "node_id": "pl_02_04", "text": "逻辑等价(P≡Q)：在所有赋值下真值相同", "search_query": "什么是逻辑等价"},
                        ],
                    },
                    {
                        "name": "范式与推理规则",
                        "node_id": "pl_03",
                        "description": "把任意命题公式化为标准形式：主析取范式（DNF）和主合取范式（CNF），并证明范式存在定理。形式化推理部分给出常用有效规则：假言推理（Modus Ponens）、拒取式（Modus Tollens）、假言三段论、归谬法，以及它们在数学证明中的应用。",
                        "search_query": "范式 重言式 推理规则",
                        "items": [
                            {"type": "definition", "node_id": "pl_03_01", "text": "重言式(永真式)：在所有赋值下恒为真", "search_query": "什么是重言式 永真式"},
                            {"type": "definition", "node_id": "pl_03_02", "text": "析取范式(DNF)：简单合取式的析取", "search_query": "析取范式DNF 主析取范式"},
                            {"type": "definition", "node_id": "pl_03_03", "text": "合取范式(CNF)：简单析取式的合取", "search_query": "合取范式CNF 主合取范式"},
                            {"type": "theorem", "node_id": "pl_03_04", "text": "范式存在定理：任一命题公式都存在等价DNF和CNF", "search_query": "范式存在定理 命题公式的范式"},
                            {"type": "rule", "node_id": "pl_03_05", "text": "假言推理：P→Q, P ⊢ Q", "search_query": "假言推理 推理规则"},
                            {"type": "rule", "node_id": "pl_03_06", "text": "拒取式：P→Q, ¬Q ⊢ ¬P", "search_query": "拒取式是什么"},
                            {"type": "rule", "node_id": "pl_03_07", "text": "假言三段论：P→Q, Q→R ⊢ P→R", "search_query": "假言三段论"},
                            {"type": "rule", "node_id": "pl_03_08", "text": "归谬法：(¬P→(Q∧¬Q)) ⊢ P", "search_query": "归谬法 反证法"},
                        ],
                    },
                ],
            },
            {
                "id": "predicate_logic",
                "name": "谓词逻辑",
                "description": "谓词逻辑（一阶逻辑）是对命题逻辑的扩展，引入谓词 P(x₁,...,xₙ)（表示个体性质或关系）和量词（全称量词 ∀、存在量词 ∃），能表达「所有 x 满足 P」「存在 x 满足 P」等量化命题。谓词逻辑是数学定理证明、程序验证、知识表示的形式化基础。",
                "search_query": "谓词逻辑 量词 谓词 基本概念",
                "children": [
                    {
                        "name": "谓词与量词",
                        "node_id": "fl_01",
                        "description": "谓词逻辑的基础概念。引入谓词 P(x)（表示个体性质或关系的语句）和量词（全称量词 ∀ 与存在量词 ∃），把命题逻辑扩展为可表达「所有」「存在」等量化关系的形式系统。区分约束变元（被量词约束）与自由变元（未被约束），明确公式的闭式与开式。",
                        "search_query": "谓词 量词 全称量词 存在量词",
                        "items": [
                            {"type": "definition", "node_id": "fl_01_01", "text": "谓词P(x)：表示个体性质或关系的语句", "search_query": "什么是谓词 谓词的定义"},
                            {"type": "definition", "node_id": "fl_01_02", "text": "全称量词∀xP(x)：所有x满足P", "search_query": "全称量词 任意符号"},
                            {"type": "definition", "node_id": "fl_01_03", "text": "存在量词∃xP(x)：存在某x满足P", "search_query": "存在量词 存在符号"},
                            {"type": "definition", "node_id": "fl_01_04", "text": "约束变元与自由变元", "search_query": "约束变元 自由变元 区别"},
                        ],
                    },
                    {
                        "name": "量词运算与推理",
                        "node_id": "fl_02",
                        "description": "处理量词与否定词的互换：量词否定律 ¬∀xP(x) ≡ ∃x¬P(x) 和 ¬∃xP(x) ≡ ∀x¬P(x)。给出四条核心推理规则：全称例示 UI（∀xP(x) ⊢ P(c)）、全称概括 UG（P(c) ⊢ ∀xP(x)，c 任意）、存在例示 EI（∃xP(x) ⊢ P(c)）、存在概括 EG（P(c) ⊢ ∃xP(x)），并用谓词逻辑证明数学命题。",
                        "search_query": "量词否定律 全称例示 存在概括",
                        "items": [
                            {"type": "theorem", "node_id": "fl_02_01", "text": "量词否定律：¬∀xP(x)≡∃x¬P(x)；¬∃xP(x)≡∀x¬P(x)", "search_query": "量词否定律"},
                            {"type": "rule", "node_id": "fl_02_02", "text": "全称例示(UI)：∀xP(x) ⊢ P(c)", "search_query": "全称例示 UI推理规则"},
                            {"type": "rule", "node_id": "fl_02_03", "text": "全称概括(UG)：对任意c有P(c) ⊢ ∀xP(x)", "search_query": "全称概括 UG"},
                            {"type": "rule", "node_id": "fl_02_04", "text": "存在例示(EI)：∃xP(x) ⊢ P(c)", "search_query": "存在例示 EI"},
                            {"type": "rule", "node_id": "fl_02_05", "text": "存在概括(EG)：P(c) ⊢ ∃xP(x)", "search_query": "存在概括 EG"},
                            {"type": "example", "node_id": "fl_02_06", "text": "证明奇数的平方也是奇数", "search_query": "证明奇数的平方是奇数 谓词逻辑证明"},
                        ],
                    },
                ],
            },
            {
                "id": "set_theory",
                "name": "集合论",
                "description": "集合论是研究集合（不同对象的无序聚集）的数学理论，是离散数学的底层基础。它定义集合、子集、幂集、集合运算（∪ ∩ - △ ^c）以及集合恒等式，并为后续的关系、函数、图论提供数学基础。康托 19 世纪创立的朴素集合论加上 ZFC 公理化体系构成了现代数学的共同语言。",
                "search_query": "集合论 集合的基本概念",
                "children": [
                    {
                        "name": "集合基本概念",
                        "node_id": "st_01",
                        "description": "集合论基础概念。集合的两种表示方法（列举法 {a,b,c} 与描述法 {x|P(x)}）、元素与集合的属于关系、子集 A⊆B 与真子集、幂集 P(A)（A 的所有子集构成的集合，|P(A)|=2^|A|）、集合相等的充要条件（A⊆B 且 B⊆A）。",
                        "search_query": "集合 子集 幂集 定义",
                        "items": [
                            {"type": "definition", "node_id": "st_01_01", "text": "集合：用列举法{x,y}或描述法{x|P(x)}表示", "search_query": "什么是集合 集合的表示方法"},
                            {"type": "definition", "node_id": "st_01_02", "text": "子集A⊆B：A中每个元素都属于B", "search_query": "什么是子集 子集的定义"},
                            {"type": "definition", "node_id": "st_01_03", "text": "幂集P(A)：|P(A)|=2ⁿ", "search_query": "幂集 幂集基数 2的n次方"},
                            {"type": "definition", "node_id": "st_01_04", "text": "集合相等A=B：A⊆B且B⊆A", "search_query": "集合相等 如何证明集合相等"},
                        ],
                    },
                    {
                        "name": "集合运算",
                        "node_id": "st_02",
                        "description": "集合的基本运算：并集 A∪B、交集 A∩B、差集 A-B、对称差 A△B、补集 A^c，以及这些运算的优先顺序。重点掌握运算律：交换律、结合律、分配律、德摩根律 (A∪B)^c = A^c∩B^c 与 (A∩B)^c = A^c∪B^c、吸收律、幂等律、补补律等。",
                        "search_query": "并集 交集 差集 补集 笛卡尔积",
                        "items": [
                            {"type": "definition", "node_id": "st_02_01", "text": "并集A∪B={x|x∈A或x∈B}", "search_query": "并集的定义 集合并运算"},
                            {"type": "definition", "node_id": "st_02_02", "text": "交集A∩B={x|x∈A且x∈B}", "search_query": "交集的定义 集合交运算"},
                            {"type": "definition", "node_id": "st_02_03", "text": "差集A-B={x|x∈A且x∉B}，补集~A=U-A", "search_query": "差集 补集 定义"},
                            {"type": "definition", "node_id": "st_02_04", "text": "对称差A⊕B=(A-B)∪(B-A)", "search_query": "对称差 集合对称差"},
                            {"type": "definition", "node_id": "st_02_05", "text": "笛卡尔积A×B={(a,b)|a∈A,b∈B}，|A×B|=mn", "search_query": "笛卡尔积的定义 笛卡尔积基数"},
                        ],
                    },
                    {
                        "name": "集合运算定律",
                        "node_id": "st_03",
                        "description": "用基本集合运算律证明更复杂的集合恒等式。常用方法：元素归属法（任取 x，证明 x∈左 ⇔ x∈右，最通用）、代数化简法（用运算律把一边化简到另一边）、Venn 图辅助法。覆盖典型题目如 (A∪B) - C = (A-C) ∪ (B-C) 等。",
                        "search_query": "分配律 德摩根律 吸收律 幂等律 集合",
                        "items": [
                            {"type": "theorem", "node_id": "st_03_01", "text": "分配律：A∩(B∪C)=(A∩B)∪(A∩C)", "search_query": "证明集合的分配律"},
                            {"type": "theorem", "node_id": "st_03_02", "text": "德摩根律(集合)：~(A∪B)=~A∩~B", "search_query": "集合的德摩根律"},
                            {"type": "theorem", "node_id": "st_03_03", "text": "幂等律与吸收律", "search_query": "幂等律 吸收律 集合运算定律"},
                        ],
                    },
                    {
                      "name": "有穷集的计数",
                      "node_id": "st_04",
                      "description": "教材 1.4 节：容斥原理（计数版）。",
                      "search_query": "容斥原理（计数版） 两集合容斥公式 三集合容斥公式 文氏图计数",
                      "items": [
                        {
                          "type": "definition",
                          "node_id": "st_04_01",
                          "text": "容斥原理（计数版）：两集合容斥公式、三集合容斥公式、文氏图计数",
                          "search_query": "容斥原理（计数版） 两集合容斥公式 三集合容斥公式 文氏图计数"
                        }
                      ]
                    },                    {
                      "name": "函数的定义与性质 / 函数的复合与反函数",
                      "node_id": "st_05",
                      "description": "教材 3.1 节、3.2 节：函数作为特殊关系、单射、满射与双射、复合函数、反函数。",
                      "search_query": "函数作为特殊关系 函数的定义（单值约束） 函数相等 函数集合 $B^A$ 单射、满射与双射 单射 满射 双射 复合函数 复合函数的定义 复合运算的结合律 反函数 反函数的定义 双射是反函数存在的充要条",
                      "items": [
                        {
                          "type": "definition",
                          "node_id": "st_05_01",
                          "text": "函数作为特殊关系：函数的定义（单值约束）、函数相等、函数集合 $B^A$",
                          "search_query": "函数作为特殊关系 函数的定义（单值约束） 函数相等 函数集合 $B^A$"
                        },
                        {
                          "type": "definition",
                          "node_id": "st_05_02",
                          "text": "单射、满射与双射：单射、满射、双射",
                          "search_query": "单射、满射与双射 单射 满射 双射"
                        },
                        {
                          "type": "definition",
                          "node_id": "st_05_03",
                          "text": "复合函数：复合函数的定义、复合运算的结合律",
                          "search_query": "复合函数 复合函数的定义 复合运算的结合律"
                        },
                        {
                          "type": "definition",
                          "node_id": "st_05_04",
                          "text": "反函数：反函数的定义、双射是反函数存在的充要条件",
                          "search_query": "反函数 反函数的定义 双射是反函数存在的充要条件"
                        }
                      ]
                    },                    {
                      "name": "双射函数与集合的基数",
                      "node_id": "st_06",
                      "description": "教材 3.3 节：集合的等势与基数、基数的比较与康托尔定理。",
                      "search_query": "集合的等势与基数 等势的定义 可数集 不可数集与康托尔对角线法 基数的比较与康托尔定理 基数的大小比较 |P(A)| > |A|（康托尔定理）",
                      "items": [
                        {
                          "type": "definition",
                          "node_id": "st_06_01",
                          "text": "集合的等势与基数：等势的定义、可数集、不可数集与康托尔对角线法",
                          "search_query": "集合的等势与基数 等势的定义 可数集 不可数集与康托尔对角线法"
                        },
                        {
                          "type": "theorem",
                          "node_id": "st_06_02",
                          "text": "基数的比较与康托尔定理：基数的大小比较、|P(A)| > |A|（康托尔定理）",
                          "search_query": "基数的比较与康托尔定理 基数的大小比较 |P(A)| > |A|（康托尔定理）"
                        }
                      ]
                    },
                ],
            },
            {
                "id": "induction",
                "name": "数学归纳法",
                "description": "数学归纳法是证明关于自然数命题的强有力工具，分为普通归纳法（假设 P(k) 证 P(k+1)）和强归纳法（假设前 k 个成立证第 k+1）。它与递归、递推密切相关，是算法分析、组合数学、数论证明的核心方法。",
                "search_query": "数学归纳法 归纳法证明",
                "children": [
                    {
                        "name": "普通归纳法",
                        "node_id": "mi_01",
                        "description": "数学归纳法的基本原理。证明关于自然数 n 的命题 P(n) 对所有 n 成立，需三步：(1) 归纳基础：验证 P(1) 成立；(2) 归纳假设：假设 P(k) 成立（k ≥ 1）；(3) 归纳步骤：证明 P(k) → P(k+1)。解释为什么这三步等价于「对所有自然数 n 成立」。",
                        "search_query": "数学归纳法 基础步 归纳步",
                        "items": [
                            {"type": "definition", "node_id": "mi_01_01", "text": "基础步：验证P(1)成立", "search_query": "数学归纳法基础步"},
                            {"type": "definition", "node_id": "mi_01_02", "text": "归纳步：假设P(k)成立证P(k+1)", "search_query": "数学归纳法归纳步 归纳假设"},
                        ],
                    },
                    {
                        "name": "强归纳法",
                        "node_id": "mi_02",
                        "description": "强归纳法（也称第二归纳法）。与普通归纳法相比，强归纳法的归纳假设更宽松：假设 P(1), P(2), ..., P(k) 都成立，证明 P(k+1)。强归纳法对证明递推关系、整除性等问题更方便，特别是归纳步骤中可能用到前面多个 k 值的情况。",
                        "search_query": "强归纳法 第二数学归纳法",
                        "items": [
                            {"type": "definition", "node_id": "mi_02_01", "text": "强归纳：假设对所有i<k有P(i)成立来证P(k)", "search_query": "强归纳法 强归纳假设"},
                        ],
                    },
                    {
                        "name": "经典归纳证明",
                        "node_id": "mi_03",
                        "description": "数学归纳法的典型应用：用归纳法证明求和公式（如 1+2+...+n = n(n+1)/2）、整除性（如 n³-n 被 6 整除）、不等式（如 2^n > n² 对 n≥5 成立）、组合恒等式（如二项式定理）、几何级数求和等。展示如何把具体问题转化为归纳形式。",
                        "search_query": "归纳法证明题 求和公式 整除",
                        "items": [
                            {"type": "example", "node_id": "mi_03_01", "text": "证明1+2+...+n=n(n+1)/2", "search_query": "用数学归纳法证明前n个自然数的和"},
                            {"type": "example", "node_id": "mi_03_02", "text": "证明1+3+...+(2n-1)=n²", "search_query": "用归纳法证明前n个奇数和"},
                            {"type": "example", "node_id": "mi_03_03", "text": "证明n³-n能被3整除", "search_query": "证明n的立方减n能被3整除"},
                            {"type": "example", "node_id": "mi_03_04", "text": "证明n<2ⁿ对所有正整数成立", "search_query": "证明n小于2的n次方"},
                            {"type": "example", "node_id": "mi_03_05", "text": "证明|P(A)|=2ⁿ（幂集基数）", "search_query": "证明幂集基数为2的n次方"},
                        ],
                    },
                ],
            },
            {
                "id": "relations",
                "name": "关系",
                "description": "关系是集合论的重要推广，研究元素之间的联系。二元关系 R ⊆ A×B 描述 A 和 B 元素之间的对应关系，关系的性质（自反、对称、传递）刻画了不同类型的关系，等价关系和偏序关系是其中最重要的两类。本模块为图论、数据库理论、形式语言打下基础。",
                "search_query": "关系 二元关系 基本概念",
                "children": [
                    {
                        "name": "关系基本概念",
                        "node_id": "rel_01",
                        "description": "二元关系的基础。定义有序对 <a,b> 与笛卡尔积 A×B，二元关系 R ⊆ A×B。关系的两种表示：关系矩阵 M_R（m×n 矩阵，M[i][j]=1 当 (aᵢ,bⱼ)∈R）和关系图（顶点为元素，有向边表示关系）。给出 A={1,2,3}, B={a,b,c} 上的具体关系例子。",
                        "search_query": "二元关系 关系矩阵 定义域 值域",
                        "items": [
                            {"type": "definition", "node_id": "rel_01_01", "text": "二元关系R⊆A×B：从A到B的有序对集合", "search_query": "什么是二元关系"},
                            {"type": "definition", "node_id": "rel_01_02", "text": "关系矩阵：M[i][j]=1表示aiRaj", "search_query": "关系矩阵怎么计算"},
                            {"type": "definition", "node_id": "rel_01_03", "text": "定义域dom(R)与值域ran(R)", "search_query": "关系的定义域与值域"},
                        ],
                    },
                    {
                        "name": "关系五大性质",
                        "node_id": "rel_02",
                        "description": "关系的基本性质：自反性 (∀x, xRx)、反自反性 (∀x, ¬xRx)、对称性 (xRy ⇒ yRx)、反对称性 (xRy ∧ yRx ⇒ x=y)、传递性 (xRy ∧ yRz ⇒ xRz)。给出判定方法（看关系矩阵/关系图的特征）和反例，掌握如何构造满足特定性质的关系。",
                        "search_query": "自反性 对称性 传递性 反自反 反对称",
                        "items": [
                            {"type": "definition", "node_id": "rel_02_01", "text": "自反性：∀a∈A, aRa（矩阵主对角线全1）", "search_query": "什么是自反性 自反关系"},
                            {"type": "definition", "node_id": "rel_02_02", "text": "对称性：aRb⇒bRa（矩阵对称）", "search_query": "什么是对称性 对称关系"},
                            {"type": "definition", "node_id": "rel_02_03", "text": "传递性：aRb∧bRc⇒aRc", "search_query": "什么是传递性 传递关系"},
                            {"type": "definition", "node_id": "rel_02_04", "text": "反自反性：∀a, ¬(aRa)（主对角线全0）", "search_query": "反自反性 反自反关系"},
                            {"type": "definition", "node_id": "rel_02_05", "text": "反对称性：aRb∧bRa⇒a=b", "search_query": "反对称性 反对称关系"},
                        ],
                    },
                    {
                        "name": "等价关系与等价类",
                        "node_id": "rel_03",
                        "description": "关系的运算。复合关系 R∘S = {<x,z> | ∃y, xSy ∧ yRz}（先 S 后 R），逆关系 R⁻¹ = {<y,x> | <x,y>∈R}，以及三种闭包：自反闭包 r(R)（加上所有 xRx）、对称闭包 s(R)（加上所有反向序对）、传递闭包 t(R)（加上传递性推出的新序对）。重点是 Warshall 算法求传递闭包。",
                        "search_query": "等价关系 等价类 划分",
                        "items": [
                            {"type": "definition", "node_id": "rel_03_01", "text": "等价关系：自反+对称+传递", "search_query": "等价关系需要满足哪些性质"},
                            {"type": "definition", "node_id": "rel_03_02", "text": "等价类[a]={x|xRa}", "search_query": "什么是等价类"},
                            {"type": "theorem", "node_id": "rel_03_03", "text": "等价关系决定集合的一个划分", "search_query": "证明等价类构成集合的一个划分"},
                            {"type": "example", "node_id": "rel_03_04", "text": "模n同余关系是等价关系", "search_query": "模n同余 等价关系例子"},
                        ],
                    },
                    {
                        "name": "偏序关系",
                        "node_id": "rel_04",
                        "description": "两类最重要的特殊关系。等价关系：满足自反、对称、传递的关系，它把集合划分成等价类，商集 A/R 是这些等价类的集合。偏序关系：满足自反、反对称、传递的关系，对应哈斯图（去掉自环和传递边）。两个概念对比：等价关系对应「分类」，偏序关系对应「层次」。",
                        "search_query": "偏序关系 哈斯图 极大元 极小元",
                        "items": [
                            {"type": "definition", "node_id": "rel_04_01", "text": "偏序关系：自反+反对称+传递", "search_query": "什么是偏序关系"},
                            {"type": "definition", "node_id": "rel_04_02", "text": "哈斯图：偏序集的可视化表示", "search_query": "哈斯图怎么画"},
                            {"type": "definition", "node_id": "rel_04_03", "text": "等价关系与偏序关系的区别", "search_query": "等价关系和偏序关系的区别"},
                            {"type": "definition", "node_id": "rel_04_04", "text": "极大元/极小元、最大元/最小元", "search_query": "极大元极小元 最大元最小元"},
                            {"type": "definition", "node_id": "rel_04_05", "text": "上界/下界、上确界/下确界", "search_query": "上界下界 上确界下确界"},
                        ],
                    },
                ],
            },
            {
                "id": "graph_theory",
                "name": "图论",
                "description": "图论研究图（顶点和边的集合）的结构与性质，是离散数学的核心分支。它在计算机网络、社交网络分析、地图导航、调度优化、编译器设计、电路设计等领域有广泛应用。核心内容包括：图的表示与遍历、树与生成树、连通性、欧拉/哈密顿路径、图的着色、平面图、网络流等。",
                "search_query": "图论 图的基本概念",
                "children": [
                    {
                        "name": "图的基本概念",
                        "node_id": "gt_01",
                        "description": "图论基础概念。无向图 G=(V,E)（V 顶点集，E 边集）、有向图 D=(V,A)、多重图（允许重边）、完全图 K_n（n 顶点的简单无向图，n(n-1)/2 条边）、二部图（顶点可分两组使所有边跨组）、邻接（两顶点相连）与关联（顶点与边）。",
                        "search_query": "图 顶点 边 完全图 二部图 度",
                        "items": [
                            {"type": "definition", "node_id": "gt_01_01", "text": "图G=(V,E)：V为顶点集，E为边集", "search_query": "图的定义 什么是图"},
                            {"type": "definition", "node_id": "gt_01_02", "text": "完全图Kₙ：边数=n(n-1)/2", "search_query": "完全图 完全图的边数"},
                            {"type": "definition", "node_id": "gt_01_03", "text": "二部图Kₘ,ₙ：边数=mn", "search_query": "二部图 完全二部图"},
                            {"type": "definition", "node_id": "gt_01_04", "text": "度deg(v)：顶点关联的边数", "search_query": "顶点的度 度数"},
                        ],
                    },
                    {
                        "name": "路径与连通性",
                        "node_id": "gt_02",
                        "description": "图的两种主要表示方法：邻接矩阵（n×n 矩阵 A[i][j]=边数/权重）和邻接表（每个顶点维护邻接顶点列表）。两种遍历算法：深度优先搜索 DFS（沿一条路径走到底再回溯）和广度优先搜索 BFS（按层扩展，先访问近邻）。两种遍历都能生成生成树/森林，复杂度 O(|V|+|E|)。",
                        "search_query": "路径 回路 连通图 连通分量",
                        "items": [
                            {"type": "definition", "node_id": "gt_02_01", "text": "路径v₀e₁v₁...vₙ，简单路径不重复", "search_query": "什么是路径 简单路径"},
                            {"type": "definition", "node_id": "gt_02_02", "text": "回路/圈：起点终点相同的路径", "search_query": "回路 圈 图论"},
                            {"type": "definition", "node_id": "gt_02_03", "text": "连通图：任意两点间存在路径", "search_query": "连通图 连通性"},
                            {"type": "definition", "node_id": "gt_02_04", "text": "连通分量：极大连通子图", "search_query": "连通分量 什么是连通分量"},
                        ],
                    },
                    {
                        "name": "重要定理",
                        "node_id": "gt_03",
                        "description": "树的定义：连通无环的无向图，n 顶点的树恰有 n-1 条边。森林（不连通的树集合）。生成树：包含图所有顶点的极小连通子图。最小生成树 MST：边权之和最小的生成树。两种经典算法：Prim 算法（从一个点扩展，类似 Dijkstra）和 Kruskal 算法（按边权排序，用并查集避免环）。",
                        "search_query": "握手定理 树 欧拉定理 邻接矩阵幂",
                        "items": [
                            {"type": "theorem", "node_id": "gt_03_01", "text": "握手定理：Σdeg(v)=2|E|", "search_query": "证明握手定理"},
                            {"type": "theorem", "node_id": "gt_03_02", "text": "奇度顶点个数必为偶数", "search_query": "奇度顶点个数为偶数 握手定理推论"},
                            {"type": "theorem", "node_id": "gt_03_03", "text": "树：n顶点连通无回路，有n-1条边", "search_query": "证明n个顶点的树有n-1条边"},
                            {"type": "theorem", "node_id": "gt_03_04", "text": "欧拉定理：欧拉回路⇔所有偶度", "search_query": "欧拉定理 欧拉回路条件"},
                            {"type": "theorem", "node_id": "gt_03_05", "text": "Aᵏ[i][j]=从i到j长度为k的路径数", "search_query": "邻接矩阵的幂 路径计数"},
                        ],
                    },
                    {
                        "name": "特殊图",
                        "node_id": "gt_04",
                        "description": "两类走遍性定理。欧拉回路/路径：经过图每条边恰好一次的回路/路径，欧拉回路存在的充要条件是图连通且所有顶点度为偶数。哈密顿回路/路径：经过每个顶点恰好一次。哈密顿问题没有简单的充要条件，判定 NP 完全。中国邮路问题（每条边至少走一次的最短路径）和 TSP 问题（每个顶点恰好一次的最短回路）都是经典应用。",
                        "search_query": "欧拉图 哈密顿图 树 生成树",
                        "items": [
                            {"type": "definition", "node_id": "gt_04_01", "text": "欧拉图：存在经过每条边恰好一次的回路", "search_query": "什么是欧拉图"},
                            {"type": "definition", "node_id": "gt_04_02", "text": "哈密顿图：存在经过每个顶点恰好一次的回路", "search_query": "什么是哈密顿图"},
                            {"type": "definition", "node_id": "gt_04_03", "text": "树：n顶点连通无回路的图", "search_query": "树的定义 树的性质"},
                            {"type": "definition", "node_id": "gt_04_04", "text": "生成树：包含所有顶点的树子图", "search_query": "生成树 最小生成树"},
                        ],
                    },
                    {
                      "name": "平面图的基本概念等",
                      "node_id": "gt_05",
                      "description": "教材 8.1 节、8.2 节、8.3 节、8.4 节：平面图与平面嵌入、欧拉公式、欧拉公式的应用、库拉托夫斯基定理。",
                      "search_query": "平面图与平面嵌入 平面图与平面嵌入 面与边界 面的次数 欧拉公式 v - e + r = 2 边数上限推论 欧拉公式的应用 判断图非平面 K5 与 K3,3 的非平面性 库拉托夫斯基定理 图的细分与同",
                      "items": [
                        {
                          "type": "definition",
                          "node_id": "gt_05_01",
                          "text": "平面图与平面嵌入：平面图与平面嵌入、面与边界、面的次数",
                          "search_query": "平面图与平面嵌入 平面图与平面嵌入 面与边界 面的次数"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_05_02",
                          "text": "欧拉公式：v - e + r = 2、边数上限推论",
                          "search_query": "欧拉公式 v - e + r = 2 边数上限推论"
                        },
                        {
                          "type": "example",
                          "node_id": "gt_05_03",
                          "text": "欧拉公式的应用：判断图非平面、K5 与 K3,3 的非平面性",
                          "search_query": "欧拉公式的应用 判断图非平面 K5 与 K3,3 的非平面性"
                        },
                        {
                          "type": "theorem",
                          "node_id": "gt_05_04",
                          "text": "库拉托夫斯基定理：图的细分与同胚、库拉托夫斯基定理内容",
                          "search_query": "库拉托夫斯基定理 图的细分与同胚 库拉托夫斯基定理内容"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_05_05",
                          "text": "极大平面图：极大平面图的定义、每个面均为三角形",
                          "search_query": "极大平面图 极大平面图的定义 每个面均为三角形"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_05_06",
                          "text": "对偶图：对偶图的构造、对偶图的性质",
                          "search_query": "对偶图 对偶图的构造 对偶图的性质"
                        },
                        {
                          "type": "example",
                          "node_id": "gt_05_07",
                          "text": "对偶图的应用：地图着色与四色定理、对偶图与欧拉公式",
                          "search_query": "对偶图的应用 地图着色与四色定理 对偶图与欧拉公式"
                        }
                      ]
                    },                    {
                      "name": "支配集、点独立集与点覆盖集等",
                      "node_id": "gt_06",
                      "description": "教材 9.1 节、9.2 节、9.3 节、9.4 节：支配集、点独立集、点覆盖集、匹配。",
                      "search_query": "支配集 支配集的定义 极小支配集 点独立集 点独立集的定义 最大独立集 点覆盖集 点覆盖集的定义 独立集与覆盖集的互补关系 匹配 匹配的定义 最大匹配与完美匹配 边覆盖集 边覆盖集的定义 匹配与边覆盖",
                      "items": [
                        {
                          "type": "definition",
                          "node_id": "gt_06_01",
                          "text": "支配集：支配集的定义、极小支配集",
                          "search_query": "支配集 支配集的定义 极小支配集"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_06_02",
                          "text": "点独立集：点独立集的定义、最大独立集",
                          "search_query": "点独立集 点独立集的定义 最大独立集"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_06_03",
                          "text": "点覆盖集：点覆盖集的定义、独立集与覆盖集的互补关系",
                          "search_query": "点覆盖集 点覆盖集的定义 独立集与覆盖集的互补关系"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_06_04",
                          "text": "匹配：匹配的定义、最大匹配与完美匹配",
                          "search_query": "匹配 匹配的定义 最大匹配与完美匹配"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_06_05",
                          "text": "边覆盖集：边覆盖集的定义、匹配与边覆盖的关系",
                          "search_query": "边覆盖集 边覆盖集的定义 匹配与边覆盖的关系"
                        },
                        {
                          "type": "theorem",
                          "node_id": "gt_06_06",
                          "text": "霍尔定理：二部图匹配的充要条件、任务分配应用",
                          "search_query": "霍尔定理 二部图匹配的充要条件 任务分配应用"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_06_07",
                          "text": "二部图与匹配判定：二部图的定义、二部图判定（奇圈检测）",
                          "search_query": "二部图与匹配判定 二部图的定义 二部图判定（奇圈检测）"
                        },
                        {
                          "type": "rule",
                          "node_id": "gt_06_08",
                          "text": "匈牙利算法：增广路径、匈牙利算法的步骤",
                          "search_query": "匈牙利算法 增广路径 匈牙利算法的步骤"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_06_09",
                          "text": "点着色：正常着色、色数、常见图的色数",
                          "search_query": "点着色 正常着色 色数 常见图的色数"
                        },
                        {
                          "type": "definition",
                          "node_id": "gt_06_10",
                          "text": "边着色：边色数、Vizing 定理",
                          "search_query": "边着色 边色数 Vizing 定理"
                        },
                        {
                          "type": "example",
                          "node_id": "gt_06_11",
                          "text": "着色的应用：排课表问题、寄存器分配",
                          "search_query": "着色的应用 排课表问题 寄存器分配"
                        }
                      ]
                    },
                ],
            },
            {
              "id": "number_theory",
              "name": "初等数论",
              "description": "面向离散数学《数学基础》教材的初等数论模块，覆盖：素数、最大公因数与最小公倍数、同余等。",
              "search_query": "初等数论 整除 素数 同余 最大公因数 欧几里得算法 RSA",
              "children": [
                {
                  "name": "素数",
                  "node_id": "nt_01",
                  "description": "教材 4.1 节：整除与带余除法、素数与合数、算术基本定理。",
                  "search_query": "整除与带余除法 整除的定义 带余除法 整除的性质 素数与合数 素数与合数的定义 素数的无穷性 试除法素性测试 算术基本定理 标准分解式 正因子个数公式",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "nt_01_01",
                      "text": "整除与带余除法：整除的定义、带余除法、整除的性质",
                      "search_query": "整除与带余除法 整除的定义 带余除法 整除的性质"
                    },
                    {
                      "type": "definition",
                      "node_id": "nt_01_02",
                      "text": "素数与合数：素数与合数的定义、素数的无穷性、试除法素性测试",
                      "search_query": "素数与合数 素数与合数的定义 素数的无穷性 试除法素性测试"
                    },
                    {
                      "type": "theorem",
                      "node_id": "nt_01_03",
                      "text": "算术基本定理：标准分解式、正因子个数公式",
                      "search_query": "算术基本定理 标准分解式 正因子个数公式"
                    }
                  ]
                },
                {
                  "name": "最大公因数与最小公倍数",
                  "node_id": "nt_02",
                  "description": "教材 4.2 节：最大公因数与欧几里得算法、互素、最小公倍数。",
                  "search_query": "最大公因数与欧几里得算法 最大公因数的定义 欧几里得算法（辗转相除法） gcd(a,b) 的线性组合表示 互素 互素的定义 互素的性质 最小公倍数 最小公倍数的定义 gcd(a,b)·lcm(a,b)",
                  "items": [
                    {
                      "type": "rule",
                      "node_id": "nt_02_01",
                      "text": "最大公因数与欧几里得算法：最大公因数的定义、欧几里得算法（辗转相除法）、gcd(a,b) 的线性组合表示",
                      "search_query": "最大公因数与欧几里得算法 最大公因数的定义 欧几里得算法（辗转相除法） gcd(a,b) 的线性组合表示"
                    },
                    {
                      "type": "definition",
                      "node_id": "nt_02_02",
                      "text": "互素：互素的定义、互素的性质",
                      "search_query": "互素 互素的定义 互素的性质"
                    },
                    {
                      "type": "definition",
                      "node_id": "nt_02_03",
                      "text": "最小公倍数：最小公倍数的定义、gcd(a,b)·lcm(a,b)=a·b",
                      "search_query": "最小公倍数 最小公倍数的定义 gcd(a,b)·lcm(a,b)=a·b"
                    }
                  ]
                },
                {
                  "name": "同余",
                  "node_id": "nt_03",
                  "description": "教材 4.3 节：同余的定义与性质、剩余类与剩余系、同余的应用。",
                  "search_query": "同余的定义与性质 同余的定义 同余的性质 模运算在计算机中的实现 剩余类与剩余系 剩余类 完全剩余系 简化剩余系 同余的应用 快速模幂运算 校验码（身份证/ISBN）",
                  "items": [
                    {
                      "type": "theorem",
                      "node_id": "nt_03_01",
                      "text": "同余的定义与性质：同余的定义、同余的性质、模运算在计算机中的实现",
                      "search_query": "同余的定义与性质 同余的定义 同余的性质 模运算在计算机中的实现"
                    },
                    {
                      "type": "definition",
                      "node_id": "nt_03_02",
                      "text": "剩余类与剩余系：剩余类、完全剩余系、简化剩余系",
                      "search_query": "剩余类与剩余系 剩余类 完全剩余系 简化剩余系"
                    },
                    {
                      "type": "example",
                      "node_id": "nt_03_03",
                      "text": "同余的应用：快速模幂运算、校验码（身份证/ISBN）",
                      "search_query": "同余的应用 快速模幂运算 校验码（身份证/ISBN）"
                    }
                  ]
                },
                {
                  "name": "一次同余方程",
                  "node_id": "nt_04",
                  "description": "教材 4.4 节：一次同余方程 ax≡b(mod m)、中国剩余定理。",
                  "search_query": "一次同余方程 ax≡b(mod m) 解存在的充要条件 求解方法 解的个数 中国剩余定理 定理内容 韩信点兵与物不知数",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "nt_04_01",
                      "text": "一次同余方程 ax≡b(mod m)：解存在的充要条件、求解方法、解的个数",
                      "search_query": "一次同余方程 ax≡b(mod m) 解存在的充要条件 求解方法 解的个数"
                    },
                    {
                      "type": "theorem",
                      "node_id": "nt_04_02",
                      "text": "中国剩余定理：定理内容、韩信点兵与物不知数",
                      "search_query": "中国剩余定理 定理内容 韩信点兵与物不知数"
                    }
                  ]
                },
                {
                  "name": "欧拉定理和费马小定理",
                  "node_id": "nt_05",
                  "description": "教材 4.5 节：欧拉函数、欧拉定理与费马小定理、数论定理的应用。",
                  "search_query": "欧拉函数 φ(n) 的定义 φ(n) 的计算公式 欧拉定理与费马小定理 欧拉定理 费马小定理 数论定理的应用 模逆元的计算 大整数模幂加速",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "nt_05_01",
                      "text": "欧拉函数：φ(n) 的定义、φ(n) 的计算公式",
                      "search_query": "欧拉函数 φ(n) 的定义 φ(n) 的计算公式"
                    },
                    {
                      "type": "theorem",
                      "node_id": "nt_05_02",
                      "text": "欧拉定理与费马小定理：欧拉定理、费马小定理",
                      "search_query": "欧拉定理与费马小定理 欧拉定理 费马小定理"
                    },
                    {
                      "type": "theorem",
                      "node_id": "nt_05_03",
                      "text": "数论定理的应用：模逆元的计算、大整数模幂加速",
                      "search_query": "数论定理的应用 模逆元的计算 大整数模幂加速"
                    }
                  ]
                },
                {
                  "name": "均匀伪随机数的产生方法",
                  "node_id": "nt_06",
                  "description": "教材 4.6 节：伪随机数的产生。",
                  "search_query": "伪随机数的产生 线性同余发生器 均匀性与周期",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "nt_06_01",
                      "text": "伪随机数的产生：线性同余发生器、均匀性与周期",
                      "search_query": "伪随机数的产生 线性同余发生器 均匀性与周期"
                    }
                  ]
                },
                {
                  "name": "RSA 公钥密码",
                  "node_id": "nt_07",
                  "description": "教材 4.7 节：RSA 密钥体制、RSA 的安全性。",
                  "search_query": "RSA 密钥体制 密钥生成算法 加密与解密运算 正确性证明（欧拉定理） RSA 的安全性 安全性依赖（大整数分解） 参数选择原则",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "nt_07_01",
                      "text": "RSA 密钥体制：密钥生成算法、加密与解密运算、正确性证明（欧拉定理）",
                      "search_query": "RSA 密钥体制 密钥生成算法 加密与解密运算 正确性证明（欧拉定理）"
                    },
                    {
                      "type": "definition",
                      "node_id": "nt_07_02",
                      "text": "RSA 的安全性：安全性依赖（大整数分解）、参数选择原则",
                      "search_query": "RSA 的安全性 安全性依赖（大整数分解） 参数选择原则"
                    }
                  ]
                }
              ]
            },            {
              "id": "combinatorics",
              "name": "组合数学",
              "description": "面向离散数学《数学基础》教材的组合数学模块，覆盖：加法法则与乘法法则、排列与组合、二项式定理与组合恒等式等。",
              "search_query": "组合数学 排列 组合 二项式定理 递推方程 生成函数 卡特兰数",
              "children": [
                {
                  "name": "加法法则与乘法法则",
                  "node_id": "cm_01",
                  "description": "教材 10.1 节：加法法则、乘法法则。",
                  "search_query": "加法法则 加法法则的内容 分类计数的适用条件 乘法法则 乘法法则的内容 分步计数的适用条件",
                  "items": [
                    {
                      "type": "rule",
                      "node_id": "cm_01_01",
                      "text": "加法法则：加法法则的内容、分类计数的适用条件",
                      "search_query": "加法法则 加法法则的内容 分类计数的适用条件"
                    },
                    {
                      "type": "rule",
                      "node_id": "cm_01_02",
                      "text": "乘法法则：乘法法则的内容、分步计数的适用条件",
                      "search_query": "乘法法则 乘法法则的内容 分步计数的适用条件"
                    }
                  ]
                },
                {
                  "name": "排列与组合",
                  "node_id": "cm_02",
                  "description": "教材 10.2 节：排列、组合。",
                  "search_query": "排列 全排列与选排列 圆排列 多重集排列 组合 组合数的定义 组合数的基本性质 多重集组合",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "cm_02_01",
                      "text": "排列：全排列与选排列、圆排列、多重集排列",
                      "search_query": "排列 全排列与选排列 圆排列 多重集排列"
                    },
                    {
                      "type": "definition",
                      "node_id": "cm_02_02",
                      "text": "组合：组合数的定义、组合数的基本性质、多重集组合",
                      "search_query": "组合 组合数的定义 组合数的基本性质 多重集组合"
                    }
                  ]
                },
                {
                  "name": "二项式定理与组合恒等式",
                  "node_id": "cm_03",
                  "description": "教材 10.3 节：二项式定理、组合恒等式。",
                  "search_query": "二项式定理 二项式定理的内容 通项与二项式系数 组合恒等式 常用组合恒等式 组合证明与归纳证明",
                  "items": [
                    {
                      "type": "theorem",
                      "node_id": "cm_03_01",
                      "text": "二项式定理：二项式定理的内容、通项与二项式系数",
                      "search_query": "二项式定理 二项式定理的内容 通项与二项式系数"
                    },
                    {
                      "type": "theorem",
                      "node_id": "cm_03_02",
                      "text": "组合恒等式：常用组合恒等式、组合证明与归纳证明",
                      "search_query": "组合恒等式 常用组合恒等式 组合证明与归纳证明"
                    }
                  ]
                },
                {
                  "name": "多项式定理",
                  "node_id": "cm_04",
                  "description": "教材 10.4 节：多项式定理。",
                  "search_query": "多项式定理 多项式定理的展开 多项式系数与多重集排列 计数应用",
                  "items": [
                    {
                      "type": "theorem",
                      "node_id": "cm_04_01",
                      "text": "多项式定理：多项式定理的展开、多项式系数与多重集排列、计数应用",
                      "search_query": "多项式定理 多项式定理的展开 多项式系数与多重集排列 计数应用"
                    }
                  ]
                },
                {
                  "name": "递推方程的定义及实例等",
                  "node_id": "cm_05",
                  "description": "教材 11.1 节、11.2 节、11.3 节：递推方程、常系数线性齐次递推方程、常系数线性非齐次递推方程、迭代解法。",
                  "search_query": "递推方程 递推关系的定义 初值条件 经典实例（汉诺塔/斐波那契） 常系数线性齐次递推方程 特征方程 相异实根的解 重根的解 常系数线性非齐次递推方程 特解的求法 通解 = 齐次通解 + 特解 迭代解法",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "cm_05_01",
                      "text": "递推方程：递推关系的定义、初值条件、经典实例（汉诺塔/斐波那契）",
                      "search_query": "递推方程 递推关系的定义 初值条件 经典实例（汉诺塔/斐波那契）"
                    },
                    {
                      "type": "definition",
                      "node_id": "cm_05_02",
                      "text": "常系数线性齐次递推方程：特征方程、相异实根的解、重根的解",
                      "search_query": "常系数线性齐次递推方程 特征方程 相异实根的解 重根的解"
                    },
                    {
                      "type": "definition",
                      "node_id": "cm_05_03",
                      "text": "常系数线性非齐次递推方程：特解的求法、通解 = 齐次通解 + 特解",
                      "search_query": "常系数线性非齐次递推方程 特解的求法 通解 = 齐次通解 + 特解"
                    },
                    {
                      "type": "rule",
                      "node_id": "cm_05_04",
                      "text": "迭代解法：递推展开法、差消法",
                      "search_query": "迭代解法 递推展开法 差消法"
                    },
                    {
                      "type": "theorem",
                      "node_id": "cm_05_05",
                      "text": "主定理与分治递推：分治算法的递推方程、主定理的三种情形、算法复杂度分析",
                      "search_query": "主定理与分治递推 分治算法的递推方程 主定理的三种情形 算法复杂度分析"
                    }
                  ]
                },
                {
                  "name": "生成函数及其应用 / 指数生成函数及其应用",
                  "node_id": "cm_06",
                  "description": "教材 11.4 节、11.5 节：生成函数、用生成函数求解递推方程、指数生成函数。",
                  "search_query": "生成函数 生成函数的定义 常见数列的生成函数 用生成函数求解递推方程 求解步骤 组合计数应用 指数生成函数 指数生成函数的定义 排列计数的应用",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "cm_06_01",
                      "text": "生成函数：生成函数的定义、常见数列的生成函数",
                      "search_query": "生成函数 生成函数的定义 常见数列的生成函数"
                    },
                    {
                      "type": "definition",
                      "node_id": "cm_06_02",
                      "text": "用生成函数求解递推方程：求解步骤、组合计数应用",
                      "search_query": "用生成函数求解递推方程 求解步骤 组合计数应用"
                    },
                    {
                      "type": "definition",
                      "node_id": "cm_06_03",
                      "text": "指数生成函数：指数生成函数的定义、排列计数的应用",
                      "search_query": "指数生成函数 指数生成函数的定义 排列计数的应用"
                    }
                  ]
                },
                {
                  "name": "卡塔兰数与斯特林数",
                  "node_id": "cm_07",
                  "description": "教材 11.6 节：卡塔兰数、斯特林数。",
                  "search_query": "卡塔兰数 卡塔兰数的递推式 应用（括号化/出栈序列） 斯特林数 第二类斯特林数 第一类斯特林数 集合划分与信筒问题",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "cm_07_01",
                      "text": "卡塔兰数：卡塔兰数的递推式、应用（括号化/出栈序列）",
                      "search_query": "卡塔兰数 卡塔兰数的递推式 应用（括号化/出栈序列）"
                    },
                    {
                      "type": "definition",
                      "node_id": "cm_07_02",
                      "text": "斯特林数：第二类斯特林数、第一类斯特林数、集合划分与信筒问题",
                      "search_query": "斯特林数 第二类斯特林数 第一类斯特林数 集合划分与信筒问题"
                    }
                  ]
                }
              ]
            },            {
              "id": "algebraic_structure",
              "name": "代数结构",
              "description": "面向离散数学《数学基础》教材的代数结构模块，覆盖：二元运算及其性质、代数系统、同态与同构等。",
              "search_query": "代数系统 群 环 域 格 布尔代数 半群 同态 同构 置换群",
              "children": [
                {
                  "name": "二元运算及其性质",
                  "node_id": "ag_01",
                  "description": "教材 12.1 节：二元运算、运算的性质、特殊元素。",
                  "search_query": "二元运算 二元运算的定义 运算表 运算的封闭性 运算的性质 结合律 交换律 分配律与吸收律 幂等律 特殊元素 单位元 零元 逆元 消去律",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_01_01",
                      "text": "二元运算：二元运算的定义、运算表、运算的封闭性",
                      "search_query": "二元运算 二元运算的定义 运算表 运算的封闭性"
                    },
                    {
                      "type": "theorem",
                      "node_id": "ag_01_02",
                      "text": "运算的性质：结合律、交换律、分配律与吸收律、幂等律",
                      "search_query": "运算的性质 结合律 交换律 分配律与吸收律 幂等律"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_01_03",
                      "text": "特殊元素：单位元、零元、逆元、消去律",
                      "search_query": "特殊元素 单位元 零元 逆元 消去律"
                    }
                  ]
                },
                {
                  "name": "代数系统",
                  "node_id": "ag_02",
                  "description": "教材 12.2 节：代数系统与子代数。",
                  "search_query": "代数系统与子代数 代数系统的定义 子代数",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_02_01",
                      "text": "代数系统与子代数：代数系统的定义、子代数",
                      "search_query": "代数系统与子代数 代数系统的定义 子代数"
                    }
                  ]
                },
                {
                  "name": "同态与同构",
                  "node_id": "ag_03",
                  "description": "教材 12.3 节：同态映射、同构。",
                  "search_query": "同态映射 同态的定义 满同态与单同态 同构 同构的定义 同构保持运算性质",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_03_01",
                      "text": "同态映射：同态的定义、满同态与单同态",
                      "search_query": "同态映射 同态的定义 满同态与单同态"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_03_02",
                      "text": "同构：同构的定义、同构保持运算性质",
                      "search_query": "同构 同构的定义 同构保持运算性质"
                    }
                  ]
                },
                {
                  "name": "群的定义及性质",
                  "node_id": "ag_04",
                  "description": "教材 13.1 节：半群与独异点、群、群的特例。",
                  "search_query": "半群与独异点 半群的定义 独异点的定义 元素的幂 群 群的定义 群的基本性质 群中的消去律 群的特例 阿贝尔群 有限群与群的阶",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_04_01",
                      "text": "半群与独异点：半群的定义、独异点的定义、元素的幂",
                      "search_query": "半群与独异点 半群的定义 独异点的定义 元素的幂"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_04_02",
                      "text": "群：群的定义、群的基本性质、群中的消去律",
                      "search_query": "群 群的定义 群的基本性质 群中的消去律"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_04_03",
                      "text": "群的特例：阿贝尔群、有限群与群的阶",
                      "search_query": "群的特例 阿贝尔群 有限群与群的阶"
                    }
                  ]
                },
                {
                  "name": "子群与群的陪集分解",
                  "node_id": "ag_05",
                  "description": "教材 13.2 节：子群、陪集与拉格朗日定理。",
                  "search_query": "子群 子群的定义 子群判定定理 陪集与拉格朗日定理 左陪集与右陪集 拉格朗日定理 元素的阶整除群的阶",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_05_01",
                      "text": "子群：子群的定义、子群判定定理",
                      "search_query": "子群 子群的定义 子群判定定理"
                    },
                    {
                      "type": "theorem",
                      "node_id": "ag_05_02",
                      "text": "陪集与拉格朗日定理：左陪集与右陪集、拉格朗日定理、元素的阶整除群的阶",
                      "search_query": "陪集与拉格朗日定理 左陪集与右陪集 拉格朗日定理 元素的阶整除群的阶"
                    }
                  ]
                },
                {
                  "name": "循环群与置换群",
                  "node_id": "ag_06",
                  "description": "教材 13.3 节：循环群、置换群。",
                  "search_query": "循环群 循环群的定义 生成元 循环群的分类 置换群 置换与置换群 轮换分解 Cayley 定理",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_06_01",
                      "text": "循环群：循环群的定义、生成元、循环群的分类",
                      "search_query": "循环群 循环群的定义 生成元 循环群的分类"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_06_02",
                      "text": "置换群：置换与置换群、轮换分解、Cayley 定理",
                      "search_query": "置换群 置换与置换群 轮换分解 Cayley 定理"
                    }
                  ]
                },
                {
                  "name": "环与域",
                  "node_id": "ag_07",
                  "description": "教材 13.4 节：环、域。",
                  "search_query": "环 环的定义 环的性质 整环 域 域的定义 有限域 GF(p) 有限域在密码学中的应用",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_07_01",
                      "text": "环：环的定义、环的性质、整环",
                      "search_query": "环 环的定义 环的性质 整环"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_07_02",
                      "text": "域：域的定义、有限域 GF(p)、有限域在密码学中的应用",
                      "search_query": "域 域的定义 有限域 GF(p) 有限域在密码学中的应用"
                    }
                  ]
                },
                {
                  "name": "格的定义及性质 / 分配格、有补格与布尔代数",
                  "node_id": "ag_08",
                  "description": "教材 14.1 节、14.2 节：格、格的实例与性质、分配格与有补格、布尔代数。",
                  "search_query": "格 格的定义（偏序定义） 格的定义（代数定义） 两种定义的等价性 格的实例与性质 子集格 P(A) 分配格 有界格与补元 分配格与有补格 分配格的判定 有补格 布尔格 布尔代数 布尔代数的定义 布尔表",
                  "items": [
                    {
                      "type": "definition",
                      "node_id": "ag_08_01",
                      "text": "格：格的定义（偏序定义）、格的定义（代数定义）、两种定义的等价性",
                      "search_query": "格 格的定义（偏序定义） 格的定义（代数定义） 两种定义的等价性"
                    },
                    {
                      "type": "theorem",
                      "node_id": "ag_08_02",
                      "text": "格的实例与性质：子集格 P(A)、分配格、有界格与补元",
                      "search_query": "格的实例与性质 子集格 P(A) 分配格 有界格与补元"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_08_03",
                      "text": "分配格与有补格：分配格的判定、有补格、布尔格",
                      "search_query": "分配格与有补格 分配格的判定 有补格 布尔格"
                    },
                    {
                      "type": "definition",
                      "node_id": "ag_08_04",
                      "text": "布尔代数：布尔代数的定义、布尔表达式、布尔函数与开关电路",
                      "search_query": "布尔代数 布尔代数的定义 布尔表达式 布尔函数与开关电路"
                    }
                  ]
                }
              ]
            },
        ],
        "edges": [
            {"from": "propositional_logic", "to": "predicate_logic", "label": "逻辑扩展"},
            {"from": "propositional_logic", "to": "set_theory", "label": "集合=命题函项"},
            {"from": "propositional_logic", "to": "induction", "label": "归纳法是逻辑推理"},
            {"from": "predicate_logic", "to": "set_theory", "label": "集合={x|P(x)}"},
            {"from": "predicate_logic", "to": "relations", "label": "关系用谓词表达"},
            {"from": "predicate_logic", "to": "induction", "label": "∀nP(n)用归纳法证"},
            {"from": "set_theory", "to": "relations", "label": "关系⊆A×B"},
            {"from": "set_theory", "to": "graph_theory", "label": "边集=顶点对集合"},
            {"from": "relations", "to": "graph_theory", "label": "有向图=二元关系"},
            {"from": "induction", "to": "set_theory", "label": "幂集基数证明"},
            {"from": "induction", "to": "relations", "label": "关系性质证明"},
            {"from": "induction", "to": "graph_theory", "label": "树边数证明"},
            {"from": "set_theory", "to": "number_theory", "label": "整除是整数集合的性质"},
            {"from": "set_theory", "to": "combinatorics", "label": "排列组合=计数集合"},
            {"from": "number_theory", "to": "combinatorics", "label": "模运算服务于递推计数"},
            {"from": "set_theory", "to": "algebraic_structure", "label": "代数系统基于集合与运算"},
            {"from": "number_theory", "to": "algebraic_structure", "label": "模n同余构成循环群"},
            {"from": "graph_theory", "to": "combinatorics", "label": "卡特兰数=树形结构计数"},
            {"from": "relations", "to": "set_theory", "label": "函数=特殊关系"},
        ],
        "learning_path": [
            "① 命题逻辑（基础语言）→",
            "② 谓词逻辑（扩展推理）→",
            "③ 数学归纳法（证明工具）→",
            "④ 集合论（数学对象）→",
            "⑤ 关系（元素间结构）→",
            "⑥ 图论（可视化网络）→",
            "⑦ 初等数论（整数结构）→",
            "⑧ 组合数学（计数方法）→",
            "⑨ 代数结构（运算体系）",
        ],
    }


@router.get("/knowledge-graph")
async def get_knowledge_graph():
    """返回离散数学知识图谱结构化数据，供前端可视化渲染。

    每个节点含 search_query、node_id 和 mastery_levels：
    - 前端点节点 → 调用 /kb/search?q=search_query → 展示对应内容
    - node_id 供学情分析追踪每个知识点的掌握度
    - mastery_levels 定义该知识点的五级掌握标准（0未学→4熟练）
    """
    import copy
    kg = copy.deepcopy(KG_DATA)

    edges = kg.get("edges", [])
    dependencies_by_target: dict[str, list[str]] = {}
    for edge in edges:
        source = edge.get("source") or edge.get("from")
        target = edge.get("target") or edge.get("to")
        if source and target:
            dependencies_by_target.setdefault(target, []).append(source)

    # 后处理：补齐章节层级、依赖和节点统计，并生成 mastery_levels。
    total_chapters = 0
    total_items = 0
    for module_index, module in enumerate(kg["modules"], 1):
        module_id = module.get("node_id") or module.get("id")
        module["node_id"] = module_id
        module["type"] = "module"
        module["chapter"] = f"第{module_index}章"
        module["depends_on"] = dependencies_by_target.get(module_id, [])
        module_item_count = 0
        for child_index, child in enumerate(module.get("children", []), 1):
            total_chapters += 1
            child["type"] = "chapter"
            child["chapter"] = f"{module_index}.{child_index}"
            child["chapter_title"] = f"{module_index}.{child_index} {child.get('name', '')}".strip()
            child["parent_node_id"] = module_id
            child["item_count"] = len(child.get("items", []))
            module_item_count += child["item_count"]
            for item in child.get("items", []):
                item["chapter"] = child["chapter"]
                item["parent_node_id"] = child.get("node_id")
                item.setdefault("name", item.get("text", "").split("：", 1)[0])
                item.setdefault("mastery_levels", _generate_mastery_levels(
                    item.get("type", "definition"),
                    item.get("text", "")
                ))
        module["chapter_count"] = len(module.get("children", []))
        module["item_count"] = module_item_count
        total_items += module_item_count

    kg["dependencies"] = [
        {
            "source": edge.get("source") or edge.get("from"),
            "target": edge.get("target") or edge.get("to"),
            "label": edge.get("label", "前置依赖"),
            "type": "prerequisite",
        }
        for edge in edges
        if (edge.get("source") or edge.get("from"))
        and (edge.get("target") or edge.get("to"))
    ]
    kg["stats"] = {
        "module_count": len(kg["modules"]),
        "chapter_count": total_chapters,
        "knowledge_point_count": total_items,
        "dependency_count": len(kg["dependencies"]),
    }

    return kg


# ==================== 个性化推荐端点 ====================

from pydantic import BaseModel, Field
from typing import List as PyList, Optional as PyOptional, Dict as PyDict


class RecommendRequest(BaseModel):
    node_id: str = Field(..., description="薄弱知识点node_id")
    level: int = Field(default=2, ge=0, le=4, description="当前掌握等级(0-4)")
    count: int = Field(default=5, ge=1, le=20, description="推荐题目数量")


class RecommendResponse(BaseModel):
    node_id: str
    questions: PyList[PyDict]


class LearningPathRequest(BaseModel):
    weak_nodes: PyList[str] = Field(..., description="薄弱知识点node_id列表")
    levels: PyOptional[PyDict[str, int]] = Field(default=None, description="各node_id的掌握等级")


class LearningPathResponse(BaseModel):
    path: PyList[PyDict]


@router.post("/recommend", response_model=RecommendResponse)
async def recommend_questions(req: RecommendRequest):
    """
    个性化题目推荐。

    根据薄弱知识点和当前掌握等级，按"挑战→巩固→基础"梯度出题。
    """
    from backend.kb.recommender import get_recommender
    rec = get_recommender()
    questions = rec.recommend(
        node_id=req.node_id,
        level=req.level,
        count=req.count,
    )
    return RecommendResponse(node_id=req.node_id, questions=questions)


@router.post("/learning-path", response_model=LearningPathResponse)
async def recommend_learning_path(req: LearningPathRequest):
    """
    个性化学习路径推荐。

    根据薄弱节点列表和知识图谱依赖关系，拓扑排序后给出分步学习路径，
    每步包含推荐题目。
    """
    from backend.kb.recommender import get_recommender
    rec = get_recommender()
    path = rec.recommend_learning_path(
        weak_nodes=req.weak_nodes,
        user_levels=req.levels or {},
    )
    return LearningPathResponse(path=path)


# ==================== 教师教材图谱（队友提供资源 · 四层结构） ====================

_WEB_RESOURCE_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@router.get("/teacher-graph", summary="教师教材四层知识图谱（章→节→知识点→要点 + 平台映射）")
def get_teacher_graph():
    """读取教师课件资源解析出的四层结构（19 章/73 节/150 知识点/376 要点），
    并合并 data/mapping_v1.json 的节点映射：
    每个 K 节点带 platform_node_id（学情染色/推荐题/路径联动用），未校准节点回退到模块。"""
    try:
        kg = json.load(open(_WEB_RESOURCE_DIR / "teacher_kg.json", encoding="utf-8"))
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": f"teacher_kg.json 未就绪: {exc}"}, status_code=503)
    mapping = {}
    try:
        mapping = json.load(open(_WEB_RESOURCE_DIR / "mapping_v1.json", encoding="utf-8")).get("mapping", {})
    except Exception:
        pass
    for ch in kg.get("chapters", []):
        for sec in ch.get("sections", []):
            for k in sec.get("kps", []):
                entry = mapping.get(k.get("id"))
                k["platform_node_id"] = entry["platform_node_id"] if entry else ""
                k["mapping_kind"] = entry.get("kind", "") if entry else ""
    return kg


# ==================== 教师教材图谱 · 动态追加/删除 ====================

async def _read_teacher_kg() -> dict:
    try:
        return json.load(open(_WEB_RESOURCE_DIR / "teacher_kg.json", encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"teacher_kg.json 未就绪: {exc}")


def _find_kg_container(kg: dict, parent_id: str):
    """返回 (list 容器, 父级 dict 或 None)：parent_id 为空→chapters；否则按层级查找。"""
    if not parent_id:
        return kg.setdefault("chapters", []), None
    for ch in kg.get("chapters", []):
        if ch.get("id") == parent_id:
            return ch.setdefault("sections", []), ch
        for sec in ch.get("sections", []):
            if sec.get("id") == parent_id:
                return sec.setdefault("kps", []), sec
            for k in sec.get("kps", []):
                if k.get("id") == parent_id:
                    return k.setdefault("points", []), k
    raise HTTPException(status_code=404, detail=f"父节点 {parent_id} 不存在")


@router.post("/teacher-graph/node", summary="动态追加：章节/节/知识点/要点")
async def add_teacher_node(
    node_type: str = Query(..., pattern="^(chapter|section|kp|point)$"),
    parent_id: str = Query(None),
    title: str = Query(..., min_length=1, max_length=100),
    node_id: str = Query(None, max_length=20),
):
    import os as _os
    kg = await _read_teacher_kg()
    container, parent = _find_kg_container(kg, parent_id)
    prefix = {"chapter": "C", "section": "S", "kp": "K", "point": "P"}[node_type]
    if not node_id:
        n = len(container) + 1
        node_id = f"{prefix}9{int(_os.times()[4]) % 10000:02d}{n:02d}"
    # 去重
    if any(x.get("id") == node_id for x in container):
        raise HTTPException(status_code=409, detail=f"节点 {node_id} 已存在")
    node = {"id": node_id, "title": title}
    if node_type in ("chapter", "section"):
        node["no"] = len(container) + 1
        node["page"] = [0, 0]
    if node_type == "chapter":
        node["part"] = "动态追加"
        node["sections"] = []
        node["points"] = []
    if node_type == "section":
        node["kps"] = []
    container.append(node)
    tmp = _WEB_RESOURCE_DIR / "teacher_kg.json.tmp"
    tmp.write_text(json.dumps(kg, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_WEB_RESOURCE_DIR / "teacher_kg.json")
    return {"ok": True, "id": node_id, "node_type": node_type, "parent_id": parent_id or "root"}


@router.delete("/teacher-graph/node/{node_id}", summary="删除节点（含子级）")
async def delete_teacher_node(node_id: str):
    kg = await _read_teacher_kg()
    deleted = False

    def drop(container):
        nonlocal deleted
        for i, item in enumerate(container):
            if item.get("id") == node_id:
                container.pop(i)
                return True
            for sub in ("sections", "kps", "points"):
                if sub in item and drop(item[sub]):
                    return True
        return False

    deleted = drop(kg.setdefault("chapters", []))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")
    tmp = _WEB_RESOURCE_DIR / "teacher_kg.json.tmp"
    tmp.write_text(json.dumps(kg, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_WEB_RESOURCE_DIR / "teacher_kg.json")
    return {"ok": True, "deleted": node_id}
