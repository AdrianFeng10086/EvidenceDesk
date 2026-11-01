"""文档解析：PDF（带文字层）、TXT、Markdown。

产出结构：
    ParsedPage.text         该页/该文件的完整原文（字符偏移的基准）
    ParsedSpan.char_start   在 ParsedPage.text 中的起始字符位置
    ParsedSpan.char_end     在 ParsedPage.text 中的结束字符位置（不含）
    ParsedSpan.bboxes       页面坐标系中的文字框；TXT/Markdown 为空
                            每个框带 char_start/char_end，用于字符 ↔ 坐标映射

PDF 布局可靠性：
    - 单栏、无表格、字符坐标覆盖充分 -> support_level = full
    - 检测到多栏、表格、旋转文本、坐标覆盖不足 -> support_level = restricted
    - 扫描件（只有图像没有文字层）明确失败为 NO_TEXT_LAYER，不做 OCR 伪装
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.database import SessionLocal
from db.models import (
    DocumentPage,
    DocumentVersion,
    EvidenceSpan,
    ParseJob,
    utcnow,
)
from services.errors import (
    ERROR_CORRUPTED,
    ERROR_EMPTY_DOCUMENT,
    ERROR_ENCRYPTED,
    ERROR_INTERNAL,
    ERROR_NO_TEXT_LAYER,
    ERROR_TOO_MANY_PAGES,
    ERROR_UNSUPPORTED_ENCODING,
    ERROR_UNSUPPORTED_FORMAT,
    ParseFailure,
)

MAX_SPAN_CHARS = 1500
CONTEXT_CHARS = 120

RESTRICTING_WARNINGS = {
    "LAYOUT_MULTI_COLUMN",
    "LAYOUT_TABLES",
    "ROTATED_TEXT",
    "LOW_TEXT_COVERAGE",
    "GARBLED_TEXT",
}

WARNING_MESSAGES = {
    "LAYOUT_MULTI_COLUMN": "检测到多栏排版，阅读顺序与段落边界可能不准确",
    "LAYOUT_TABLES": "检测到表格区域，表格内文字按行抽取，未还原单元格结构",
    "ROTATED_TEXT": "检测到旋转文字，坐标与文本顺序可能不可靠",
    "LOW_TEXT_COVERAGE": "部分字符没有坐标信息，文字框可能不完整",
    "GARBLED_TEXT": "文本中存在无法识别的字符，可能缺少字体映射",
    "LONG_BLOCK_SPLIT": "超长段落已按行拆分，以保证证据片段可定位",
    "ENCODING_FALLBACK": "文件不是 UTF-8 编码，已按备用编码读取",
    "EMPTY_PAGE": "页面没有可抽取的文字",
}

LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+•·]|\d{1,3}[.、)]|[一二三四五六七八九十]+[、.])\s*")
HEADING_RE = re.compile(r"^\s*(#{1,6})\s+")
MD_THEMATIC_RE = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class ParsedSpan:
    page: int
    block_index: int
    kind: str
    text: str
    char_start: int
    char_end: int
    bboxes: List[Dict[str, Any]] = field(default_factory=list)
    context_before: Optional[str] = None
    context_after: Optional[str] = None


@dataclass
class ParsedPage:
    page_number: int
    text: str
    char_count: int
    line_count: int
    width: Optional[float]
    height: Optional[float]
    is_blank: bool
    spans: List[ParsedSpan] = field(default_factory=list)


@dataclass
class ParseResult:
    pages: List[ParsedPage]
    support_level: str
    warnings: List[Dict[str, Any]]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(page.char_count for page in self.pages)


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------


def extract_document(path: Path, suffix: str) -> ParseResult:
    suffix = suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return _parse_text_file(path, suffix)
    raise ParseFailure(
        ERROR_UNSUPPORTED_FORMAT,
        f"不支持的文件格式：{suffix or '无扩展名'}",
        details={"suffix": suffix},
    )


def run_parse_job(version_id: str, *, force: bool = False) -> str:
    """执行一次解析任务，返回最终状态。

    该函数是同步的，由 FastAPI BackgroundTasks 在线程池中调用。
    解析失败不会抛给调用方，而是写入文档版本与解析任务记录。
    """
    with SessionLocal() as db:
        version = db.get(DocumentVersion, version_id)
        if version is None:
            return "missing"

        if not force and version.parse_status in {"parsing", "indexing"}:
            return version.parse_status

        job = db.scalars(
            select(ParseJob)
            .where(ParseJob.document_version_id == version.id)
            .order_by(ParseJob.created_at.desc())
        ).first()
        if job is None or job.finished_at is not None:
            job = ParseJob(
                document_version_id=version.id,
                status="queued",
                attempt=(job.attempt + 1 if job else 1),
            )
            db.add(job)
            db.flush()

        version.parse_status = "parsing"
        version.parse_error_code = None
        version.parse_error = None
        version.support_level = "pending"
        version.warnings = []
        job.status = "parsing"
        job.error_code = None
        job.error_message = None
        job.started_at = utcnow()
        job.finished_at = None
        db.commit()

        try:
            result = extract_document(Path(version.file_path), version.file_suffix)

            # 进入“索引准备中”。Day 5 会在这里调用向量化与 BM25 建索引；
            # 首版该阶段仅校验解析产物，因此很快进入 success。
            version.parse_status = "indexing"
            job.status = "indexing"
            db.commit()

            _replace_parsed_content(db, version, result)
            db.commit()

            version.parse_status = "success"
            version.support_level = result.support_level
            version.warnings = result.warnings
            version.page_count = result.page_count
            version.char_count = result.char_count
            version.parsed_at = utcnow()
            job.status = "success"
            job.warnings = result.warnings
            job.finished_at = utcnow()
            db.commit()
            return "success"

        except ParseFailure as exc:
            _mark_failed(db, version, job, exc.code, exc.message)
            return "failed"
        except Exception as exc:  # noqa: BLE001 — 未知异常也必须落到失败状态
            _mark_failed(db, version, job, ERROR_INTERNAL, f"解析失败：{exc}")
            return "failed"


def _mark_failed(
    db: Session,
    version: DocumentVersion,
    job: ParseJob,
    code: str,
    message: str,
) -> None:
    # 失败时不保留半成品页面/证据，避免被当成可用原文
    db.execute(delete(EvidenceSpan).where(EvidenceSpan.document_version_id == version.id))
    db.execute(delete(DocumentPage).where(DocumentPage.document_version_id == version.id))

    version.parse_status = "failed"
    version.support_level = "unsupported"
    version.parse_error_code = code
    version.parse_error = message
    version.warnings = []
    version.page_count = None
    version.char_count = None
    version.parsed_at = utcnow()

    job.status = "failed"
    job.error_code = code
    job.error_message = message
    job.finished_at = utcnow()
    db.commit()


def _replace_parsed_content(
    db: Session, version: DocumentVersion, result: ParseResult
) -> None:
    # 重新解析只清理当前版本自己的半成品，绝不触碰旧版本
    db.execute(delete(EvidenceSpan).where(EvidenceSpan.document_version_id == version.id))
    db.execute(delete(DocumentPage).where(DocumentPage.document_version_id == version.id))

    for page in result.pages:
        db.add(
            DocumentPage(
                document_version_id=version.id,
                page_number=page.page_number,
                text=page.text,
                char_count=page.char_count,
                line_count=page.line_count,
                width=page.width,
                height=page.height,
                is_blank=page.is_blank,
            )
        )
        for span in page.spans:
            db.add(
                EvidenceSpan(
                    document_version_id=version.id,
                    page=span.page,
                    block_index=span.block_index,
                    kind=span.kind,
                    text=span.text,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    bboxes=span.bboxes,
                    context_before=span.context_before,
                    context_after=span.context_after,
                )
            )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _parse_pdf(path: Path) -> ParseResult:
    settings = get_settings()
    page_count = _pdf_page_count(path)

    if page_count == 0:
        raise ParseFailure(ERROR_EMPTY_DOCUMENT, "PDF 没有任何页面")
    if page_count > settings.max_pdf_pages:
        raise ParseFailure(
            ERROR_TOO_MANY_PAGES,
            f"PDF 页数超过限制（最多 {settings.max_pdf_pages} 页，当前 {page_count} 页）",
            details={"page_count": page_count, "max_pages": settings.max_pdf_pages},
        )

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover — 依赖缺失
        raise ParseFailure(ERROR_INTERNAL, f"缺少 pdfplumber 依赖：{exc}")

    warnings: List[Dict[str, Any]] = []
    pages: List[ParsedPage] = []
    has_images = False

    try:
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                parsed, page_warnings, page_has_images = _extract_pdf_page(page, index)
                pages.append(parsed)
                warnings.extend(page_warnings)
                has_images = has_images or page_has_images
    except ParseFailure:
        raise
    except Exception as exc:  # noqa: BLE001 — pdfminer 的异常类型较杂
        raise ParseFailure(ERROR_CORRUPTED, f"PDF 文件损坏或无法解析：{exc}")

    if not any(page.text.strip() for page in pages):
        if has_images:
            raise ParseFailure(
                ERROR_NO_TEXT_LAYER,
                "PDF 只有图像、没有可抽取的文字层；首版不支持扫描件 OCR",
            )
        raise ParseFailure(ERROR_EMPTY_DOCUMENT, "PDF 没有可抽取的文字内容")

    support_level = "restricted" if _has_restricting_warning(warnings) else "full"
    return ParseResult(pages=pages, support_level=support_level, warnings=warnings)


def _pdf_page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ParseFailure(ERROR_ENCRYPTED, f"PDF 已加密，无法解析：{exc}")
            if decrypted == 0:
                raise ParseFailure(ERROR_ENCRYPTED, "PDF 已加密，无法解析")
        return len(reader.pages)
    except ParseFailure:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ParseFailure(ERROR_CORRUPTED, f"PDF 文件损坏或无法读取：{exc}")


def _extract_pdf_page(page: Any, page_number: int) -> Tuple[ParsedPage, List[Dict], bool]:
    warnings: List[Dict[str, Any]] = []
    raw_chars: List[Dict[str, Any]] = list(page.chars or [])
    raw_char_count = len(raw_chars)
    images = []
    try:
        images = list(page.images or [])
    except Exception:  # noqa: BLE001
        images = []

    try:
        raw_lines = page.extract_text_lines(return_chars=True, strip=True)
    except Exception:  # noqa: BLE001 — 个别损坏页可能无法按行抽取
        raw_lines = []

    line_infos: List[Dict[str, Any]] = []
    for raw_line in raw_lines:
        text = (raw_line.get("text") or "").strip()
        if not text:
            continue
        chars = [ch for ch in (raw_line.get("chars") or []) if ch.get("text")]
        sizes = [float(ch.get("size") or 0) for ch in chars if ch.get("size")]
        line_infos.append(
            {
                "text": text,
                "x0": float(raw_line.get("x0") or 0.0),
                "x1": float(raw_line.get("x1") or 0.0),
                "top": float(raw_line.get("top") or 0.0),
                "bottom": float(raw_line.get("bottom") or 0.0),
                "size": statistics.median(sizes) if sizes else 0.0,
                "chars": chars,
            }
        )

    page_text, char_starts = _build_page_text(line_infos)
    char_count = len(page_text)

    mapped_chars = sum(len(info["chars"]) for info in line_infos)
    if raw_char_count and mapped_chars / raw_char_count < 0.95:
        warnings.append(_warning("LOW_TEXT_COVERAGE", page_number))

    if _detect_multi_column(line_infos):
        warnings.append(_warning("LAYOUT_MULTI_COLUMN", page_number))

    if _detect_tables(page):
        warnings.append(_warning("LAYOUT_TABLES", page_number))

    rotated = sum(1 for ch in raw_chars if ch.get("upright") is False)
    if raw_char_count >= 20 and rotated / raw_char_count > 0.05:
        warnings.append(_warning("ROTATED_TEXT", page_number))

    if "�" in page_text:
        warnings.append(_warning("GARBLED_TEXT", page_number))

    spans = _build_pdf_spans(
        line_infos=line_infos,
        char_starts=char_starts,
        page_text=page_text,
        page_number=page_number,
        page_width=float(page.width or 0.0),
        page_height=float(page.height or 0.0),
        restricted=_has_restricting_warning(warnings),
    )

    parsed = ParsedPage(
        page_number=page_number,
        text=page_text,
        char_count=char_count,
        line_count=len(line_infos),
        width=float(page.width) if page.width else None,
        height=float(page.height) if page.height else None,
        is_blank=not page_text.strip(),
        spans=spans,
    )
    return parsed, warnings, bool(images)


def _build_page_text(line_infos: Sequence[Dict[str, Any]]) -> Tuple[str, List[int]]:
    parts: List[str] = []
    starts: List[int] = []
    offset = 0
    for info in line_infos:
        starts.append(offset)
        parts.append(info["text"])
        offset += len(info["text"]) + 1  # 行间换行
    return "\n".join(parts), starts


def _line_bbox(
    info: Dict[str, Any],
    page_width: float,
    page_height: float,
    char_start: int,
    char_end: int,
) -> Dict[str, Any]:
    return {
        "x0": round(info["x0"], 2),
        "y0": round(info["top"], 2),
        "x1": round(info["x1"], 2),
        "y1": round(info["bottom"], 2),
        "page_width": round(page_width, 2),
        "page_height": round(page_height, 2),
        # 该文字框覆盖的页面字符范围，用于字符 ↔ 坐标映射
        "char_start": char_start,
        "char_end": char_end,
    }


def _build_pdf_spans(
    *,
    line_infos: List[Dict[str, Any]],
    char_starts: List[int],
    page_text: str,
    page_number: int,
    page_width: float,
    page_height: float,
    restricted: bool,
) -> List[ParsedSpan]:
    if not line_infos:
        return []

    sizes = [info["size"] for info in line_infos if info["size"] > 0]
    body_size = statistics.median(sizes) if sizes else 0.0

    def is_heading(info: Dict[str, Any]) -> bool:
        return body_size > 0 and info["size"] >= body_size * 1.12

    spans: List[ParsedSpan] = []
    block_index = 0
    i = 0
    while i < len(line_infos):
        first = line_infos[i]
        if restricted:
            group = [i]
            i += 1
            kind = "line"
        elif is_heading(first):
            group = [i]
            i += 1
            kind = "heading"
        else:
            group = [i]
            j = i + 1
            while j < len(line_infos):
                current = line_infos[j]
                previous = line_infos[j - 1]
                if is_heading(current):
                    break
                gap = current["top"] - previous["bottom"]
                line_height = max(previous["bottom"] - previous["top"], 1.0)
                if gap > max(4.5, line_height * 0.85):
                    break
                if LIST_ITEM_RE.match(current["text"]) and previous["text"].endswith(
                    ("。", "！", "？", ".", "!", "?")
                ):
                    break
                group.append(j)
                j += 1
            i = j
            kind = "list_item" if LIST_ITEM_RE.match(first["text"]) else "paragraph"

        start_line = group[0]
        end_line = group[-1]
        char_start = char_starts[start_line]
        char_end = char_starts[end_line] + len(line_infos[end_line]["text"])
        text = page_text[char_start:char_end]

        bboxes = [
            _line_bbox(
                line_infos[index],
                page_width,
                page_height,
                char_starts[index],
                char_starts[index] + len(line_infos[index]["text"]),
            )
            for index in group
        ]

        spans.append(
            ParsedSpan(
                page=page_number,
                block_index=block_index,
                kind=kind,
                text=text,
                char_start=char_start,
                char_end=char_end,
                bboxes=bboxes,
                context_before=_context(page_text, max(0, char_start - CONTEXT_CHARS), char_start),
                context_after=_context(page_text, char_end, min(len(page_text), char_end + CONTEXT_CHARS)),
            )
        )
        block_index += 1

    return spans


def _detect_multi_column(line_infos: Sequence[Dict[str, Any]]) -> bool:
    """同一水平带上出现左右分离的两段文字，视为多栏/并排布局。

    注意：pdfplumber 的 extract_text_lines 会把同一基线上的左右两栏
    合并成“一行”，所以不能只比较行框；还要检查行内字符之间是否存在
    足以割裂阅读顺序的大间距。
    """
    for info in line_infos:
        chars = sorted(info["chars"], key=lambda ch: float(ch.get("x0") or 0.0))
        if len(chars) < 4:
            continue
        runs = 1
        previous = chars[0]
        for char in chars[1:]:
            gap = float(char.get("x0") or 0.0) - float(previous.get("x1") or 0.0)
            if gap > 24:
                runs += 1
            previous = char
        if runs >= 2:
            return True

    for i in range(len(line_infos)):
        a = line_infos[i]
        for j in range(i + 1, len(line_infos)):
            b = line_infos[j]
            overlap = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
            min_height = min(a["bottom"] - a["top"], b["bottom"] - b["top"])
            if min_height <= 0 or overlap / min_height < 0.5:
                continue
            if b["x0"] - a["x1"] > 24 or a["x0"] - b["x1"] > 24:
                return True
    return False


def _detect_tables(page: Any) -> bool:
    try:
        tables = page.find_tables()
    except Exception:  # noqa: BLE001 — 表格识别失败不应中断解析
        return False
    return bool(tables)


def _context(text: str, start: int, end: int) -> Optional[str]:
    snippet = text[start:end].strip()
    return snippet or None


# ---------------------------------------------------------------------------
# TXT / Markdown
# ---------------------------------------------------------------------------


def _decode_text(path: Path) -> Tuple[str, Optional[Dict[str, Any]]]:
    raw = path.read_bytes()
    if not raw:
        return "", None

    candidates: List[Tuple[str, str]] = []
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        candidates.append(("utf-16", "BOM"))
    candidates.extend([("utf-8-sig", "UTF-8"), ("gb18030", "GB18030")])

    for encoding, label in candidates:
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if "\x00" in text and encoding != "utf-16":
            continue
        warning = None
        if label == "GB18030":
            warning = _warning("ENCODING_FALLBACK")
        return text, warning

    raise ParseFailure(
        ERROR_UNSUPPORTED_ENCODING,
        "无法识别文件编码，请另存为 UTF-8 后重试",
    )


def _parse_text_file(path: Path, suffix: str) -> ParseResult:
    raw_text, encoding_warning = _decode_text(path)
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    if not text.strip():
        raise ParseFailure(ERROR_EMPTY_DOCUMENT, "文件为空或仅包含空白字符")

    is_markdown = suffix in {".md", ".markdown"}
    spans = _build_text_spans(text, is_markdown)
    warnings: List[Dict[str, Any]] = []
    if encoding_warning:
        warnings.append(encoding_warning)
    if any(span.kind == "block_split" for span in spans):
        warnings.append(_warning("LONG_BLOCK_SPLIT"))
        for span in spans:
            if span.kind == "block_split":
                span.kind = "paragraph"

    page = ParsedPage(
        page_number=1,
        text=text,
        char_count=len(text),
        line_count=text.count("\n") + 1,
        width=None,
        height=None,
        is_blank=False,
        spans=spans,
    )
    return ParseResult(pages=[page], support_level="full", warnings=warnings)


def _block_kind(block: str, is_markdown: bool) -> str:
    first_line = block.lstrip("\n").split("\n", 1)[0]
    if is_markdown:
        if first_line.strip().startswith("```"):
            return "code"
        if HEADING_RE.match(first_line):
            return "heading"
        if TABLE_ROW_RE.match(first_line):
            return "table"
    if first_line.lstrip().startswith(">"):
        return "quote"
    if LIST_ITEM_RE.match(first_line):
        return "list_item"
    return "paragraph"


def _build_text_spans(text: str, is_markdown: bool) -> List[ParsedSpan]:
    blocks = _split_text_blocks(text, is_markdown)
    spans: List[ParsedSpan] = []
    block_index = 0

    for start, end, raw_block in blocks:
        kind = _block_kind(raw_block, is_markdown)
        if len(raw_block) <= MAX_SPAN_CHARS:
            chunks = [(start, end)]
        else:
            chunks = _split_long_block(text, start, end)
            kind = "block_split"

        for chunk_start, chunk_end in chunks:
            chunk_text = text[chunk_start:chunk_end]
            if not chunk_text.strip():
                continue
            spans.append(
                ParsedSpan(
                    page=1,
                    block_index=block_index,
                    kind=kind,
                    text=chunk_text,
                    char_start=chunk_start,
                    char_end=chunk_end,
                    bboxes=[],
                    context_before=_context(
                        text, max(0, chunk_start - CONTEXT_CHARS), chunk_start
                    ),
                    context_after=_context(
                        text, chunk_end, min(len(text), chunk_end + CONTEXT_CHARS)
                    ),
                )
            )
            block_index += 1

    return spans


def _split_text_blocks(text: str, is_markdown: bool) -> List[Tuple[int, int, str]]:
    """按空行切分段落；Markdown 代码块内不切分，标题单独成块。"""
    blocks: List[Tuple[int, int, str]] = []
    offset = 0
    block_start: Optional[int] = None
    block_end = 0
    in_fence = False

    def flush() -> None:
        nonlocal block_start, block_end
        if block_start is not None and block_end > block_start:
            raw = text[block_start:block_end]
            left_trim = len(raw) - len(raw.lstrip())
            right_trim = len(raw) - len(raw.rstrip())
            start = block_start + left_trim
            end = block_end - right_trim
            if end > start:
                blocks.append((start, end, text[start:end]))
        block_start = None

    # splitlines(keepends=True) 保留原始偏移
    for line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        content = line.rstrip("\n")
        stripped = content.strip()
        fence = is_markdown and stripped.startswith("```")

        if fence:
            if block_start is None:
                block_start = line_start
            in_fence = not in_fence
            block_end = offset
            continue

        if in_fence:
            block_end = offset
            continue

        if not stripped:
            flush()
            continue

        if is_markdown and (HEADING_RE.match(content) or MD_THEMATIC_RE.match(content)):
            flush()
            block_start = line_start
            block_end = offset
            flush()
            continue

        if block_start is None:
            block_start = line_start
        block_end = offset

    flush()
    return blocks


def _split_long_block(text: str, start: int, end: int) -> List[Tuple[int, int]]:
    """超长段落按不超过 MAX_SPAN_CHARS 切开，优先在换行处断开。"""
    chunks: List[Tuple[int, int]] = []
    cursor = start
    while cursor < end:
        limit = min(cursor + MAX_SPAN_CHARS, end)
        if limit < end:
            newline = text.rfind("\n", cursor, limit)
            if newline > cursor:
                limit = newline + 1
        chunks.append((cursor, limit))
        cursor = limit
    return chunks


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _warning(code: str, page: Optional[int] = None) -> Dict[str, Any]:
    warning: Dict[str, Any] = {
        "code": code,
        "message": WARNING_MESSAGES.get(code, code),
    }
    if page is not None:
        warning["page"] = page
    return warning


def _has_restricting_warning(warnings: Sequence[Dict[str, Any]]) -> bool:
    return any(w.get("code") in RESTRICTING_WARNINGS for w in warnings)
