"""按关键词从已解析文档中召回真实 EvidenceSpan。

首版不引入向量检索：这里只做确定性的关键词/中文二元组匹配，
返回数据库里真实存在、且带文档版本与文字框的证据片段。
Day 5 的向量 + BM25 检索会替换本模块的打分部分，但返回结构保持不变。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Document, DocumentVersion, EvidenceSpan, Workspace

MAX_CANDIDATES = 5000
DEFAULT_LIMIT = 5

_ASCII_TERM_RE = re.compile(r"[a-z0-9]{2,}")
_CJK_RUN_RE = re.compile(r"[㐀-鿿]+")


def query_terms(query: str) -> List[str]:
    """把问题拆成可用于子串匹配的词。

    中文没有空格，使用 2 字窗口召回；1 字词噪声太大，不参与打分。
    """
    normalized = (query or "").lower()
    terms = set(_ASCII_TERM_RE.findall(normalized))

    for run in _CJK_RUN_RE.findall(query or ""):
        if len(run) <= 4:
            terms.add(run)
        for index in range(len(run) - 1):
            terms.add(run[index : index + 2])

    return sorted(term for term in terms if len(term) >= 2)


def _score(text: str, terms: Sequence[str]) -> int:
    lowered = text.lower()
    total = 0
    for term in terms:
        occurrences = lowered.count(term)
        if occurrences:
            total += occurrences * min(len(term), 4)
    return total


def _payload(
    span: EvidenceSpan,
    version: DocumentVersion,
    document: Document,
) -> Dict[str, Any]:
    return {
        "id": span.id,
        "document_version_id": version.id,
        "document_name": document.display_name or version.file_name,
        "file_name": version.file_name,
        "file_suffix": version.file_suffix,
        "page": span.page,
        "page_count": version.page_count or 1,
        "support_level": version.support_level,
        "block_index": span.block_index,
        "kind": span.kind,
        "text": span.text,
        "char_start": span.char_start,
        "char_end": span.char_end,
        "bboxes": span.bboxes or [],
        "context_before": span.context_before,
        "context_after": span.context_after,
        "is_sample": False,
    }


def search_workspace_evidence(
    db: Session,
    workspace_id: str,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """在资料空间内召回真实证据片段，按关键词命中数排序。"""
    terms = query_terms(query)
    if not terms or limit <= 0:
        return []

    rows = db.execute(
        select(EvidenceSpan, DocumentVersion, Document)
        .join(DocumentVersion, DocumentVersion.id == EvidenceSpan.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(Workspace, Workspace.id == DocumentVersion.workspace_id)
        .where(
            DocumentVersion.workspace_id == workspace_id,
            DocumentVersion.parse_status == "success",
            Document.deleted_at.is_(None),
            Workspace.deleted_at.is_(None),
        )
        .order_by(DocumentVersion.id, EvidenceSpan.page, EvidenceSpan.block_index)
        .limit(MAX_CANDIDATES)
    ).all()

    scored = []
    for span, version, document in rows:
        score = _score(span.text, terms)
        if score > 0:
            scored.append((score, span, version, document))

    scored.sort(key=lambda item: (-item[0], item[1].page, item[1].block_index))

    return [
        _payload(span, version, document)
        for _score_value, span, version, document in scored[:limit]
    ]
