"""
知识库模块 — 集成测试

测试文档解析、分块、向量化、存储、检索的完整流程。
"""

import sys
import os
import tempfile
import io

# UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==================== 测试数据 ====================

SAMPLE_DISCRETE_MATH = """
第1章 命题逻辑

1.1 命题与联结词

定义1.1（命题）：一个具有确定真值的陈述句称为命题。

例如：
（1）北京是中国的首都。——真命题
（2）2+3=6。——假命题
（3）你好吗？——不是命题（疑问句）

命题通常用大写字母 P, Q, R 等表示。命题的真值只有两个：真（T）和 假（F）。

定义1.2（联结词）：将命题组合成复合命题的逻辑运算符称为联结词。

常用的联结词有：
（1）否定联结词 ┐：┐P 表示"非P"
（2）合取联结词 ∧：P∧Q 表示"P且Q"
（3）析取联结词 ∨：P∨Q 表示"P或Q"
（4）蕴含联结词 →：P→Q 表示"若P则Q"
（5）等价联结词 ↔：P↔Q 表示"P当且仅当Q"

1.2 真值表与逻辑等价

定义1.3（真值表）：将命题公式在所有可能赋值下的真值列成的表称为真值表。

定理1.1（德摩根律）：
    ┐(P ∧ Q) ≡ ┐P ∨ ┐Q
    ┐(P ∨ Q) ≡ ┐P ∧ ┐Q

证明：
    根据真值表，列出P、Q的所有可能取值（共4种），
    分别计算┐(P ∧ Q)和┐P ∨ ┐Q的值，发现两列完全相同。
    因此等式成立。

定义1.4（逻辑等价）：如果两个命题公式 P 和 Q 在所有赋值下都有相同的真值，
则称 P 和 Q 逻辑等价，记作 P ≡ Q。

1.3 范式

定理1.2（范式存在定理）：任一命题公式都存在与之等价的析取范式和合取范式。
（证明略）

第2章 谓词逻辑

2.1 谓词与量词

在命题逻辑中，我们无法处理"所有x满足P(x)"这样的内部结构。
谓词逻辑将命题分解为个体词和谓词，从而具有更强的表达能力。

定义2.1（谓词）：表示个体性质或个体之间关系的词称为谓词。

定义2.2（量词）：
（1）全称量词 ∀x P(x)：对所有x，P(x)成立
（2）存在量词 ∃x P(x)：存在x使得P(x)成立

2.2 集合论基础

定义2.3（集合的并）：设A、B为两个集合，A与B的并集定义为：
A ∪ B = {x | x ∈ A 或 x ∈ B}

定义2.4（集合的交）：设A、B为两个集合，A与B的交集定义为：
A ∩ B = {x | x ∈ A 且 x ∈ B}

定理2.1（分配律）：对任意集合 A、B、C，有：
    A ∩ (B ∪ C) = (A ∩ B) ∪ (A ∩ C)
    A ∪ (B ∩ C) = (A ∪ B) ∩ (A ∪ C)

定理2.2（De Morgan律—集合形式）：设全集为 U，则：
    (A ∪ B)^c = A^c ∩ B^c
    (A ∩ B)^c = A^c ∪ B^c

证明：
    利用谓词逻辑中的德摩根律和集合运算的定义即可证明。
"""


# ==================== 测试函数 ====================

def test_loader_text():
    """测试纯文本加载器"""
    from backend.kb.loader import DocumentLoader

    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(SAMPLE_DISCRETE_MATH)
        tmp_path = f.name

    try:
        loader = DocumentLoader()
        doc = loader.load(tmp_path)
        assert doc.source_filename.endswith('.txt'), "文件名应为 .txt"
        assert len(doc.chapters) > 0, "应检测到章节"
        print(f"[PASS] loader_text: {len(doc.chapters)} 个章节")
        for ch in doc.chapters:
            if ch.level == 1:
                print(f"  - {ch.title} ({len(ch.elements)} 元素)")
        return True
    finally:
        os.unlink(tmp_path)


def test_chunker_theorem_proof_binding():
    """测试定理-证明绑定：定理和证明不应被分开"""
    from backend.kb.chunker import SmartChunker
    from backend.kb.loader import DocumentLoader

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(SAMPLE_DISCRETE_MATH)
        tmp_path = f.name

    try:
        loader = DocumentLoader()
        doc = loader.load(tmp_path)
        chunker = SmartChunker()
        chunks = chunker.chunk(doc)

        # 统计定理块
        theorem_blocks = [c for c in chunks if c.metadata.chunk_type == 'theorem_block']
        print(f"[INFO] chunker: {len(chunks)} 个块, {len(theorem_blocks)} 个定理块")

        for tb in theorem_blocks:
            content = tb.content
            # 检查是否有定理+证明绑定在一起
            if '定理' in content and '证明' in content:
                print(f"  [OK] 定理块包含完整证明: {tb.chunk_id}")
            elif '定理' in content and '证明略' in content:
                print(f"  [OK] 定理块（证明略）: {tb.chunk_id}")

        # 验证德摩根律定理和证明在一起
        demorgan_found = False
        for c in chunks:
            if '德摩根律' in c.content and '证明' in c.content:
                demorgan_found = True
                print(f"  [OK] 德摩根律定理块绑定成功: {c.metadata.chunk_type}")
                break

        assert len(chunks) > 5, f"分块数应 > 5，实际: {len(chunks)}"
        assert demorgan_found, "德摩根律定理和证明应在同一块中"

        print(f"[PASS] chunker_theorem_binding")
        return True
    finally:
        os.unlink(tmp_path)


def test_has_formula():
    """测试公式检测"""
    from backend.kb.chunker import has_formula

    assert has_formula("集合 $A \\cup B$ 的并"), "应检测到 $...$ 公式"
    assert has_formula("$$A \\cup B = \\{x\\}$$"), "应检测到 $$...$$ 公式"
    assert not has_formula("这是一段普通文本"), "不应误检普通文本"
    print(f"[PASS] has_formula")


def test_detect_element_type():
    """测试元素类型检测"""
    from backend.kb.loader import detect_element_type

    assert detect_element_type("定理1.1（德摩根律）") == 'theorem'
    assert detect_element_type("定理 1.1 德摩根律：") == 'theorem'
    assert detect_element_type("定义1.2（联结词）") == 'definition'
    assert detect_element_type("证明：根据定义...") == 'proof'
    assert detect_element_type("例1：判断命题") == 'example'
    assert detect_element_type("普通的段落内容") == 'paragraph'
    print(f"[PASS] detect_element_type")


def test_embedder_integration():
    """测试嵌入服务（使用 chroma_default 以避免下载大模型）"""
    import os
    os.environ["EMBEDDING_BACKEND"] = "chroma_default"

    from backend.kb.embedder import EmbeddingService

    service = EmbeddingService(backend="chroma_default")
    assert service.dimension == 384, f"默认维度应为384，实际: {service.dimension}"

    # 单文本嵌入
    vec = service.embed_query("什么是命题逻辑？")
    assert len(vec) == 384
    assert any(v != 0 for v in vec), "向量不应全为零"

    # 批量嵌入
    texts = ["集合的并运算", "命题逻辑的联结词", "谓词逻辑的量词"]
    vecs = service.embed_documents(texts)
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)

    # 缓存测试
    vec2 = service.embed_query("什么是命题逻辑？")
    assert vec == vec2, "缓存应返回相同向量"

    print(f"[PASS] embedder (chroma_default, {service.dimension}d)")


def test_vector_store_search():
    """测试向量存储和检索"""
    import os
    os.environ["EMBEDDING_BACKEND"] = "chroma_default"

    from backend.kb.embedder import EmbeddingService
    from backend.kb.vector_store import KnowledgeBaseStore
    from backend.kb.chunker import Chunk, ChunkMetadata

    # 创建临时持久化目录
    persist_dir = tempfile.mkdtemp(prefix="chroma_test_")

    try:
        embedding = EmbeddingService(backend="chroma_default")
        store = KnowledgeBaseStore(
            persist_dir=persist_dir,
            embedding_service=embedding,
            collection_name="test_kb",
        )

        # 写入测试块
        test_chunks = [
            Chunk(
                chunk_id="test_chunk_001",
                content="命题是一个具有确定真值的陈述句。真值只有真和假两种。",
                metadata=ChunkMetadata(
                    source_document="test.pdf",
                    chapter="第1章 命题逻辑",
                    section="1.1 命题与联结词",
                    chunk_type="definition",
                    has_formulas=False,
                ),
            ),
            Chunk(
                chunk_id="test_chunk_002",
                content="德摩根律：┐(P ∧ Q) ≡ ┐P ∨ ┐Q，这是命题逻辑中的重要等价关系。",
                metadata=ChunkMetadata(
                    source_document="test.pdf",
                    chapter="第1章 命题逻辑",
                    section="1.2 真值表",
                    chunk_type="theorem_block",
                    has_formulas=True,
                    is_complete_proof=True,
                ),
            ),
            Chunk(
                chunk_id="test_chunk_003",
                content="集合的并运算 A ∪ B = {x | x ∈ A 或 x ∈ B}，是集合论的基本运算。",
                metadata=ChunkMetadata(
                    source_document="test.pdf",
                    chapter="第2章 集合论",
                    section="2.1 集合运算",
                    chunk_type="definition",
                    has_formulas=True,
                ),
            ),
        ]

        count = store.index_chunks(test_chunks)
        assert count == 3, f"应索引 3 个块，实际: {count}"

        # 搜索测试
        results = store.search("德摩根律是什么？", top_k=3)
        assert len(results) >= 1, "应至少返回1个结果"
        assert "德摩根律" in results[0]["content"]

        # 验证元数据
        meta = results[0]["metadata"]
        assert meta["chapter"] == "第1章 命题逻辑"
        print(f"  [OK] 搜索命中，分数: {results[0]['score']}")

        # 文档列表
        docs = store.get_documents()
        assert len(docs) == 1
        assert docs[0]["filename"] == "test.pdf"
        print(f"  [OK] 文档列表: {len(docs)} 个文档, {docs[0]['chunks_count']} 个块")

        # 统计
        stats = store.get_stats()
        assert stats["total_chunks"] == 3
        print(f"  [OK] 统计: {stats}")

        # 删除
        deleted = store.delete_document("test.pdf")
        assert deleted == 3
        print(f"  [OK] 删除成功: {deleted} 个块")

        # 验证删除后
        results_after = store.search("集合")
        assert len(results_after) == 0, "删除后不应有结果"

        print(f"[PASS] vector_store_search")
    finally:
        # 清理
        import shutil
        shutil.rmtree(persist_dir, ignore_errors=True)


def test_retriever():
    """测试检索器"""
    import os
    os.environ["EMBEDDING_BACKEND"] = "chroma_default"

    from backend.kb.embedder import EmbeddingService
    from backend.kb.vector_store import KnowledgeBaseStore
    from backend.kb.retriever import KnowledgeBaseRetriever
    from backend.kb.chunker import Chunk, ChunkMetadata

    persist_dir = tempfile.mkdtemp(prefix="chroma_retriever_")

    try:
        embedding = EmbeddingService(backend="chroma_default")
        store = KnowledgeBaseStore(persist_dir=persist_dir, embedding_service=embedding)
        retriever = KnowledgeBaseRetriever(store, embedding)

        # 索引测试数据
        chunks = [
            Chunk(chunk_id="r001", content="命题逻辑研究命题之间的逻辑关系。",
                  metadata=ChunkMetadata(source_document="dm.pdf", chapter="第1章")),
            Chunk(chunk_id="r002", content="集合论是离散数学的基础，研究集合的性质与运算。",
                  metadata=ChunkMetadata(source_document="dm.pdf", chapter="第2章")),
            Chunk(chunk_id="r003", content="图论研究图的性质，包括路径、连通性等问题。",
                  metadata=ChunkMetadata(source_document="dm.pdf", chapter="第3章")),
        ]
        store.index_chunks(chunks)

        # 检索
        result = retriever.retrieve("什么是集合论？", top_k=3)
        assert result["total_hits"] >= 1
        assert result["search_time_ms"] is not None
        assert len(result["results"]) >= 1

        # 验证返回格式
        first = result["results"][0]
        assert "chunk_id" in first
        assert "content" in first
        assert "metadata" in first
        assert "score" in first
        print(f"  [OK] 检索 '{result['query']}', {result['total_hits']} 条结果, "
              f"{result['search_time_ms']:.1f}ms")

        print(f"[PASS] retriever")
    finally:
        import shutil
        shutil.rmtree(persist_dir, ignore_errors=True)


def test_full_pipeline():
    """端到端测试：文档 → 解析 → 分块 → 向量化 → 存储 → 检索"""
    import os
    os.environ["EMBEDDING_BACKEND"] = "chroma_default"

    from backend.kb.loader import DocumentLoader
    from backend.kb.chunker import SmartChunker
    from backend.kb.embedder import EmbeddingService
    from backend.kb.vector_store import KnowledgeBaseStore
    from backend.kb.retriever import KnowledgeBaseRetriever

    persist_dir = tempfile.mkdtemp(prefix="chroma_e2e_")

    try:
        # Step 1: 创建测试文档
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(SAMPLE_DISCRETE_MATH)
            doc_path = f.name

        # Step 2: 解析
        loader = DocumentLoader()
        parsed = loader.load(doc_path)
        assert parsed.total_pages > 0
        assert len(parsed.chapters) >= 3
        print(f"  [OK] Step 1-解析: {len(parsed.chapters)} 个章节")

        # Step 3: 分块
        chunker = SmartChunker()
        chunks = chunker.chunk(parsed)
        assert len(chunks) >= 8
        print(f"  [OK] Step 2-分块: {len(chunks)} 个块")

        # 检查分块质量
        theorem_blocks = [c for c in chunks if '定理' in c.content]
        assert len(theorem_blocks) >= 3, f"应至少3个定理块，实际: {len(theorem_blocks)}"
        print(f"  [OK] Step 2-质量: 定理块={len(theorem_blocks)}")

        # Step 4: 向量化 + 存储
        embedding = EmbeddingService(backend="chroma_default")
        store = KnowledgeBaseStore(persist_dir=persist_dir, embedding_service=embedding)
        count = store.index_chunks(chunks)
        assert count == len(chunks)
        print(f"  [OK] Step 3-索引: {count} 个块")

        # Step 5: 检索
        retriever = KnowledgeBaseRetriever(store, embedding)
        queries = [
            ("什么是命题？", "第1章"),
            ("德摩根律", "第1章"),
            ("集合的交与并", "第2章"),
            ("谓词逻辑", "第2章"),
        ]
        for q, expected_chapter in queries:
            result = retriever.retrieve(q, top_k=3, min_score=0.2)
            assert result["total_hits"] >= 1, f"查询 '{q}' 应返回结果"
            top_result_chapter = result["results"][0]["metadata"].get("chapter", "")
            print(f"  [OK] 查询'{q}' → {result['total_hits']}条, "
                  f"分数={result['results'][0]['score']}, "
                  f"章节={top_result_chapter}")

        print(f"[PASS] full_pipeline (端到端)")
    finally:
        import shutil
        os.unlink(doc_path)
        shutil.rmtree(persist_dir, ignore_errors=True)


# ==================== 运行测试 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("知数·明析 — 知识库模块测试")
    print("=" * 60)

    tests = [
        ("loader_text", test_loader_text),
        ("detect_element_type", test_detect_element_type),
        ("has_formula", test_has_formula),
        ("chunker_theorem_binding", test_chunker_theorem_proof_binding),
        ("embedder", test_embedder_integration),
        ("vector_store_search", test_vector_store_search),
        ("retriever", test_retriever),
        ("full_pipeline (E2E)", test_full_pipeline),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")
    print("=" * 60)
