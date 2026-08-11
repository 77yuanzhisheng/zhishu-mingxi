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
import logging
import tempfile
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


@router.get("/knowledge-graph")
async def get_knowledge_graph():
    """返回离散数学知识图谱结构化数据，供前端可视化渲染。

    每个节点含 search_query、node_id 和 mastery_levels：
    - 前端点节点 → 调用 /kb/search?q=search_query → 展示对应内容
    - node_id 供学情分析追踪每个知识点的掌握度
    - mastery_levels 定义该知识点的五级掌握标准（0未学→4熟练）
    """
    kg = {
        "modules": [
            {
                "id": "propositional_logic",
                "name": "命题逻辑",
                "description": "研究命题之间逻辑关系的基础数学工具，是离散数学的推理语言基础",
                "search_query": "命题逻辑 命题 联结词 基本概念",
                "children": [
                    {
                        "name": "命题与联结词",
                        "node_id": "pl_01",
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
                "description": "命题逻辑的扩展，引入谓词和量词，可表达'所有''存在'等量化关系",
                "search_query": "谓词逻辑 量词 谓词 基本概念",
                "children": [
                    {
                        "name": "谓词与量词",
                        "node_id": "fl_01",
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
                "description": "离散数学的数学基础，研究集合的性质与运算，为关系和图论提供底层结构",
                "search_query": "集合论 集合的基本概念",
                "children": [
                    {
                        "name": "集合基本概念",
                        "node_id": "st_01",
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
                        "search_query": "分配律 德摩根律 吸收律 幂等律 集合",
                        "items": [
                            {"type": "theorem", "node_id": "st_03_01", "text": "分配律：A∩(B∪C)=(A∩B)∪(A∩C)", "search_query": "证明集合的分配律"},
                            {"type": "theorem", "node_id": "st_03_02", "text": "德摩根律(集合)：~(A∪B)=~A∩~B", "search_query": "集合的德摩根律"},
                            {"type": "theorem", "node_id": "st_03_03", "text": "幂等律与吸收律", "search_query": "幂等律 吸收律 集合运算定律"},
                        ],
                    },
                ],
            },
            {
                "id": "induction",
                "name": "数学归纳法",
                "description": "证明∀nP(n)型命题的核心工具，贯穿集合论、关系、图论的证明",
                "search_query": "数学归纳法 归纳法证明",
                "children": [
                    {
                        "name": "普通归纳法",
                        "node_id": "mi_01",
                        "search_query": "数学归纳法 基础步 归纳步",
                        "items": [
                            {"type": "definition", "node_id": "mi_01_01", "text": "基础步：验证P(1)成立", "search_query": "数学归纳法基础步"},
                            {"type": "definition", "node_id": "mi_01_02", "text": "归纳步：假设P(k)成立证P(k+1)", "search_query": "数学归纳法归纳步 归纳假设"},
                        ],
                    },
                    {
                        "name": "强归纳法",
                        "node_id": "mi_02",
                        "search_query": "强归纳法 第二数学归纳法",
                        "items": [
                            {"type": "definition", "node_id": "mi_02_01", "text": "强归纳：假设对所有i<k有P(i)成立来证P(k)", "search_query": "强归纳法 强归纳假设"},
                        ],
                    },
                    {
                        "name": "经典归纳证明",
                        "node_id": "mi_03",
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
                "description": "研究集合元素间联系的结构，是图论的代数基础",
                "search_query": "关系 二元关系 基本概念",
                "children": [
                    {
                        "name": "关系基本概念",
                        "node_id": "rel_01",
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
                "description": "研究顶点和边构成的网络结构，是离散数学最直观的应用领域",
                "search_query": "图论 图的基本概念",
                "children": [
                    {
                        "name": "图的基本概念",
                        "node_id": "gt_01",
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
                        "search_query": "欧拉图 哈密顿图 树 生成树",
                        "items": [
                            {"type": "definition", "node_id": "gt_04_01", "text": "欧拉图：存在经过每条边恰好一次的回路", "search_query": "什么是欧拉图"},
                            {"type": "definition", "node_id": "gt_04_02", "text": "哈密顿图：存在经过每个顶点恰好一次的回路", "search_query": "什么是哈密顿图"},
                            {"type": "definition", "node_id": "gt_04_03", "text": "树：n顶点连通无回路的图", "search_query": "树的定义 树的性质"},
                            {"type": "definition", "node_id": "gt_04_04", "text": "生成树：包含所有顶点的树子图", "search_query": "生成树 最小生成树"},
                        ],
                    },
                ],
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
        ],
        "learning_path": [
            "① 命题逻辑（基础语言）→",
            "② 集合论（数学对象）→",
            "③ 谓词逻辑（扩展推理）→",
            "④ 数学归纳法（证明工具）→",
            "⑤ 关系（元素间结构）→",
            "⑥ 图论（可视化网络）",
        ],
    }

    # 后处理：给所有 items 节点自动生成 mastery_levels
    for module in kg["modules"]:
        for child in module.get("children", []):
            for item in child.get("items", []):
                item.setdefault("mastery_levels", _generate_mastery_levels(
                    item.get("type", "definition"),
                    item.get("text", "")
                ))

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
