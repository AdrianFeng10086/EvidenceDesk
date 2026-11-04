"""把 EvidenceSpan 切分为可检索文本块，并保留回 span 的映射。

分块原则：
- 默认一个 EvidenceSpan（段落/列表项/标题）就是一个块；
- 超过上限的 span 按换行优先切分，并保留少量重叠；
- 每个块保存页面绝对字符范围与所属 span 范围；
- 块 ID 由版本、span、块序号和内容哈希决定，重复建索引保持稳定。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from db.models import EvidenceSpan

# 纯文本样例常保留 Markdown/中文序号标题，但解析器会按 .txt 当成段落；
# 这里按首行特征补充章节识别，不改变 EvidenceSpan 本身的 kind。
_HEADING_TEXT_RE = re.compile(
    r"^\s*(?:#{1,6}\s+\S|第[一二三四五六七八九十百\d]+[章节篇部分]|[一二三四五六七八九十]+、)"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def make_chunk_id(
    document_version_id: str,
    evidence_span_id: str,
    chunk_index: int,
    content_hash: str,
) -> str:
    raw = f"{document_version_id}|{evidence_span_id}|{chunk_index}|{content_hash}"
    return "chk_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


@dataclass(frozen=True)
class ChunkDraft:
    evidence_span_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    span_char_start: int
    span_char_end: int
    page: int
    block_index: int
    chunk_type: str
    section_title: Optional[str]
    content_hash: str

    def stable_id(self, document_version_id: str) -> str:
        return make_chunk_id(
            document_version_id,
            self.evidence_span_id,
            self.chunk_index,
            self.content_hash,
        )


def _windows(text: str, max_chars: int, overlap_chars: int) -> List[tuple[int, int]]:
    """返回相对于 span.text 的窗口范围。"""
    if not text:
        return []
    if max_chars <= 0 or len(text) <= max_chars:
        return [(0, len(text))]

    overlap = max(0, min(overlap_chars, max_chars // 2))
    windows: List[tuple[int, int]] = []
    cursor = 0
    length = len(text)
    while cursor < length:
        limit = min(cursor + max_chars, length)
        if limit < length:
            # 优先在换行处断开，避免把一句话切成两半
            newline = text.rfind("\n", cursor + max_chars // 2, limit)
            if newline > cursor:
                limit = newline + 1
        windows.append((cursor, limit))
        if limit >= length:
            break
        cursor = max(limit - overlap, cursor + 1)
    return windows


def chunk_span(
    span: EvidenceSpan,
    *,
    max_chars: int,
    overlap_chars: int,
    section_title: Optional[str] = None,
    kind_override: Optional[str] = None,
) -> List[ChunkDraft]:
    drafts: List[ChunkDraft] = []
    for index, (start, end) in enumerate(_windows(span.text, max_chars, overlap_chars)):
        snippet = span.text[start:end]
        if not snippet.strip():
            continue
        content_hash = sha256_text(snippet)
        drafts.append(
            ChunkDraft(
                evidence_span_id=span.id,
                chunk_index=index,
                text=snippet,
                char_start=span.char_start + start,
                char_end=span.char_start + end,
                span_char_start=span.char_start,
                span_char_end=span.char_end,
                page=span.page,
                block_index=span.block_index,
                chunk_type=kind_override or span.kind or "paragraph",
                section_title=section_title,
                content_hash=content_hash,
            )
        )
    return drafts


def _looks_like_heading(text: str) -> bool:
    first_line = (text or "").lstrip("\n").split("\n", 1)[0].strip()
    if not first_line or len(first_line) > 80:
        return False
    return bool(_HEADING_TEXT_RE.match(first_line))


def chunk_spans(
    spans: Sequence[EvidenceSpan],
    *,
    max_chars: int,
    overlap_chars: int,
) -> List[ChunkDraft]:
    """按阅读顺序分块，并把最近一级标题写入块上下文。

    TXT/Markdown 的列表项或段落本身常常不含“申报材料”“住宿费标准”等
    章节词，只靠片段文本会丢失上下文；保留 section_title 可以显著改善
    BM25 与向量召回，同时返回给用户的 text 仍是真实片段。
    """
    drafts: List[ChunkDraft] = []
    current_section: Optional[str] = None
    for span in spans:
        is_heading = (span.kind or "") == "heading" or _looks_like_heading(span.text)
        if is_heading:
            current_section = span.text.strip()
        drafts.extend(
            chunk_span(
                span,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                section_title=current_section,
                kind_override="heading" if is_heading else None,
            )
        )
    return drafts


def overlapping_bboxes(
    bboxes: Iterable[dict], char_start: int, char_end: int
) -> List[dict]:
    """只保留与检索块字符范围有交集的文字框。"""
    result: List[dict] = []
    for box in bboxes or []:
        try:
            box_start = int(box.get("char_start", 0))
            box_end = int(box.get("char_end", 0))
        except (TypeError, ValueError):
            result.append(box)
            continue
        if box_start < char_end and box_end > char_start:
            result.append(box)
    return result


__all__ = [
    "ChunkDraft",
    "chunk_span",
    "chunk_spans",
    "make_chunk_id",
    "overlapping_bboxes",
    "sha256_text",
]
