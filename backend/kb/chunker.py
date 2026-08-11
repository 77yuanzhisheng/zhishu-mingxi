"""
智能分块器
=========

针对离散数学内容优化的分块策略：
1. 公式不截断 — LaTeX $...$ / $$...$$ 块不被分割
2. 定理+证明绑定 — "定理 → 证明" 保持在同一 chunk
3. 语义边界优先 — 优先在章节/段落边界分块
4. 重叠缓冲 — chunk 间重叠防止上下文断裂

分块流程:
    结构解析 → 公式保护 → 定理-证明绑定 → 递归分块 → 元数据注入
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

from backend.kb.loader import ParsedDocument, Chapter, ContentElement

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class ChunkMetadata:
    """块的元数据"""
    source_document: str = ""
    chapter: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_type: str = "general"
    is_complete_proof: bool = False
    has_formulas: bool = False
    token_count: Optional[int] = None


@dataclass
class Chunk:
    """知识块"""
    chunk_id: str
    content: str            # 纯文本（含行内 LaTeX 标记）
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)


# ==================== LaTeX 公式保护 ====================

# 匹配行内公式 $...$（不匹配 $$）
INLINE_FORMULA = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)')

# 匹配块级公式 $$...$$
BLOCK_FORMULA = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)

# 匹配 \begin{...}...\end{...} 环境
BEGIN_END_ENV = re.compile(r'\\begin\{(\w+)\}(.+?)\\end\{\1\}', re.DOTALL)

# 匹配 \(...\) 和 \[...\] 环境
PAREN_FORMULA = re.compile(r'\\[\(\[](.+?)\\[\)\]]', re.DOTALL)


def has_formula(text: str) -> bool:
    """检查文本是否包含 LaTeX 公式"""
    if INLINE_FORMULA.search(text):
        return True
    if BLOCK_FORMULA.search(text):
        return True
    if BEGIN_END_ENV.search(text):
        return True
    if PAREN_FORMULA.search(text):
        return True
    return False


def find_safe_split_point(text: str, max_pos: int) -> int:
    """
    在不超过 max_pos 的位置找到安全的分割点。

    安全 = 不在公式内部。
    优先级：段落结尾 > 句子结尾 > 行尾 > 逗号 > 空格
    """
    if len(text) <= max_pos:
        return len(text)

    # 搜索区域：从 max_pos 往前找
    search_start = max(0, max_pos - 200)
    search_region = text[search_start:max_pos + 1]

    # 公式边界标记
    formula_ranges: List[Tuple[int, int]] = []
    for pattern in [BLOCK_FORMULA, BEGIN_END_ENV, PAREN_FORMULA]:
        for m in pattern.finditer(search_region):
            formula_ranges.append((m.start(), m.end()))

    def is_safe(pos: int) -> bool:
        """检查位置是否在公式外"""
        for start, end in formula_ranges:
            if start < pos < end:
                return False
        return True

    # 按优先级寻找安全分割点（从后往前找）
    separators = [
        (r'\n\s*\n', 0.9),    # 段落边界（最高优先级）
        (r'[。！？；]', 0.8),   # 中文句子结尾
        (r'\n', 0.6),          # 行尾
        (r'[，、]', 0.4),      # 中文逗号
        (r'\s{2,}', 0.3),      # 多个空格
    ]

    best_pos = max_pos
    best_priority = 0

    for sep_pattern, priority in separators:
        for m in re.finditer(sep_pattern, search_region):
            pos = search_start + m.end()
            if max_pos - 100 <= pos <= max_pos and is_safe(pos):
                if priority > best_priority:
                    best_pos = pos
                    best_priority = priority

    # 如果找不到合适的分割点，在 max_pos 处硬切（但要确保不在公式内）
    if best_priority == 0:
        best_pos = max_pos
        # 调整到最近的公式外位置
        while best_pos > 0 and not is_safe(best_pos):
            best_pos -= 1

    return min(best_pos, len(text))


# ==================== 章节结构解析 ====================

def extract_chapter_context(chapters: List[Chapter]) -> Dict[int, Dict[str, str]]:
    """
    从章节列表构建层级上下文映射。
    返回: {element_index: {"chapter": "...", "section": "...", "subsection": "..."}}
    """
    context = {}
    current_context = {"chapter": None, "section": None, "subsection": None}

    for chapter in chapters:
        if chapter.level == 1:
            current_context["chapter"] = chapter.title
            current_context["section"] = None
            current_context["subsection"] = None
        elif chapter.level == 2:
            current_context["section"] = chapter.title
            current_context["subsection"] = None
        elif chapter.level == 3:
            current_context["subsection"] = chapter.title

        for elem in chapter.elements:
            context[id(elem)] = dict(current_context)

    return context


# ==================== 主分块器 ====================

class SmartChunker:
    """
    智能分块器：针对离散数学内容优化的分块策略。

    参数:
        chunk_size: 目标块大小（字符数），默认 800
        chunk_overlap: 块间重叠字符数，默认 200
        max_chunk_size: 最大块大小（字符数），默认 1200
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 200,
                 max_chunk_size: int = 1200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_chunk_size = max_chunk_size

    def chunk(self, parsed_doc: ParsedDocument) -> List[Chunk]:
        """
        将 ParsedDocument 分块。

        分块策略:
        1. 定理+证明绑定为一个完整块
        2. 定义、例题保持完整（如果尺寸允许）
        3. 普通段落按 chunk_size 分割
        4. 所有块携带章节/页码元数据
        """
        chunks = []
        chunk_counter = 0

        # 将章节和未分配元素合并处理
        source = parsed_doc.source_filename

        # 处理每个章节
        for chapter in parsed_doc.chapters:
            # 获取当前层级上下文
            chapter_name = chapter.title if chapter.level == 1 else None
            section_name = chapter.title if chapter.level == 2 else None
            subsection_name = chapter.title if chapter.level == 3 else None

            # 遍历当前层级下所有元素的章节上下文
            parent_chapter = None
            parent_section = None
            parent_subsection = None

            # 回溯查找父级章节标题
            for ch in parsed_doc.chapters:
                if ch is chapter:
                    break
                if ch.level == 1:
                    parent_chapter = ch.title
                    parent_section = None
                    parent_subsection = None
                elif ch.level == 2:
                    parent_section = ch.title
                    parent_subsection = None
                elif ch.level == 3:
                    parent_subsection = ch.title

            # 如果当前元素是章级别
            if chapter.level == 1:
                chapter_name = chapter.title
                parent_section = None
                parent_subsection = None
            elif chapter.level == 2:
                section_name = chapter.title
                chapter_name = parent_chapter
                parent_subsection = None
            elif chapter.level == 3:
                subsection_name = chapter.title
                section_name = parent_section
                chapter_name = parent_chapter

            chapter_chunks = self._chunk_elements(
                chapter.elements, source, chunk_counter,
                chapter_name, section_name, subsection_name
            )
            chunks.extend(chapter_chunks)
            chunk_counter += len(chapter_chunks)

        # 处理未分配元素
        if parsed_doc.unassigned_elements:
            unassigned_chunks = self._chunk_elements(
                parsed_doc.unassigned_elements, source, chunk_counter,
                None, None, None
            )
            chunks.extend(unassigned_chunks)

        logger.info(f"分块完成: {len(chunks)}个块, 来自 {source}")
        return chunks

    def _chunk_elements(self, elements: List[ContentElement], source: str,
                        start_counter: int, chapter: Optional[str],
                        section: Optional[str],
                        subsection: Optional[str]) -> List[Chunk]:
        """对元素列表进行分块"""
        chunks = []
        buffer = []
        buffer_type = "general"
        buffer_pages = []
        counter = start_counter

        def flush_buffer():
            """将缓冲区内容写入一个 Chunk"""
            nonlocal counter
            if not buffer:
                return
            content = ' '.join(buffer)
            chunk_id = f"chunk_{Path(source).stem}_{counter:04d}"
            metadata = ChunkMetadata(
                source_document=source,
                chapter=chapter,
                section=section,
                subsection=subsection,
                page_start=buffer_pages[0] if buffer_pages else None,
                page_end=buffer_pages[-1] if buffer_pages else None,
                chunk_type=buffer_type,
                is_complete_proof=(buffer_type == "theorem_block"),
                has_formulas=has_formula(content),
                token_count=len(content),
            )
            chunks.append(Chunk(
                chunk_id=chunk_id,
                content=content,
                metadata=metadata,
            ))
            counter += 1

        from pathlib import Path

        i = 0
        while i < len(elements):
            elem = elements[i]

            # 定理开始 → 开始收集定理块
            if elem.type in ('theorem', 'definition', 'axiom', 'corollary', 'lemma'):
                flush_buffer()
                buffer = [elem.text]
                buffer_type = 'theorem_block' if elem.type == 'theorem' else elem.type
                buffer_pages = [elem.page_number]

                # 向后收集证明
                j = i + 1
                while j < len(elements):
                    next_elem = elements[j]
                    # 证明跟在定理后面 → 绑定
                    if next_elem.type == 'proof':
                        buffer.append(next_elem.text)
                        buffer_pages.append(next_elem.page_number)
                        # 如果文本不太长，继续往后收集一点
                        combined = ' '.join(buffer)
                        if len(combined) < self.max_chunk_size:
                            j += 1
                            # 再往后看一个元素
                            if j < len(elements):
                                nxt = elements[j]
                                if nxt.type == 'paragraph' and len(combined + ' ' + nxt.text) < self.max_chunk_size:
                                    buffer.append(nxt.text)
                                    buffer_pages.append(nxt.page_number)
                                    j += 1
                        buffer_type = 'theorem_block'  # 标记包含完整证明
                        break
                    # 下一个也是定理 → 不绑定
                    elif next_elem.type in ('theorem', 'definition', 'axiom', 'corollary', 'lemma'):
                        break
                    # 普通段落，可能还没到证明
                    elif next_elem.type == 'paragraph':
                        combined = ' '.join(buffer + [next_elem.text])
                        if len(combined) < self.max_chunk_size:
                            buffer.append(next_elem.text)
                            buffer_pages.append(next_elem.page_number)
                            j += 1
                        else:
                            break
                    else:
                        break

                flush_buffer()
                i = j
                continue

            # 例题 → 尽量保持完整
            if elem.type == 'example':
                flush_buffer()
                buffer = [elem.text]
                buffer_type = 'example'
                buffer_pages = [elem.page_number]

                # 向后收集解答
                j = i + 1
                while j < len(elements):
                    nxt = elements[j]
                    if nxt.type in ('theorem', 'definition', 'proof', 'example'):
                        break
                    combined = ' '.join(buffer + [nxt.text])
                    if len(combined) < self.max_chunk_size:
                        buffer.append(nxt.text)
                        buffer_pages.append(nxt.page_number)
                        j += 1
                    else:
                        break

                flush_buffer()
                i = j
                continue

            # 普通段落 → 添加到缓冲区
            if elem.type in ('paragraph', 'proof'):
                buffer.append(elem.text)
                buffer_pages.append(elem.page_number)
                buffer_type = 'general'

                # 检查是否需要刷新
                combined = ' '.join(buffer)
                if len(combined) >= self.chunk_size:
                    # 找到安全分割点
                    flush_buffer()
                i += 1
            else:
                buffer.append(elem.text)
                buffer_pages.append(elem.page_number)
                i += 1

        # 刷新最后的缓冲区
        flush_buffer()

        # 添加 chunk 间重叠
        self._add_overlap(chunks)

        return chunks

    def _add_overlap(self, chunks: List[Chunk]):
        """在相邻 chunk 之间添加内容重叠"""
        if self.chunk_overlap <= 0:
            return

        for i in range(1, len(chunks)):
            prev_content = chunks[i - 1].content
            if len(prev_content) > self.chunk_overlap:
                overlap_text = prev_content[-self.chunk_overlap:]
                # 确保不从公式中间截断
                safe_pos = find_safe_split_point(prev_content, len(prev_content) - self.chunk_overlap)
                if safe_pos > 0 and safe_pos < len(prev_content):
                    overlap_text = prev_content[safe_pos:]
                chunks[i].content = overlap_text + '\n\n' + chunks[i].content


# ==================== 辅助函数 ====================

import os
from pathlib import Path as _Path  # noqa: F811
