"""Case 级混合证据检索：向量召回基线 + 中文 BM25 + RRF 融合。

检索范围只来自 Case 固定引用的 DocumentVersion；任何 workspace/version
过滤都必须在 Case 范围内，模型或调用方不能通过参数扩大范围。

空结果不是一句“没找到”，而是区分：
    NO_SCOPE              范围为空
    ALL_SOURCES_DELETED   范围内来源全部删除
    SOURCES_UNAVAILABLE   范围来源全部缺失/不可用
    INDEX_NOT_READY       来源存在但索引未就绪
    FILTERED_OUT          过滤条件排除了全部来源
    NO_SEARCHABLE_CONTENT 索引就绪但没有可检索文本块
    NO_MATCH              有可检索内容但没有匹配
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from rank_bm25 import BM25Plus
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from db.models import (
    Case,
    Document,
    DocumentVersion,
    EvidenceSpan,
    RetrievalChunk,
    RetrievalLog,
    Run,
    Workspace,
    utcnow,
)
from services import vector_store
from services.access import Principal, require_case_access
from services.cases import (
    ScopeEntry,
    build_scope_snapshot,
    compute_scope_hash,
    load_scope_entries,
)
from services.chunking import overlapping_bboxes
from services.embedding import embed_query
from services.errors import AppError, ForbiddenError
from services.index_config import IndexConfig, get_index_config
from services.indexing import (
    chunk_index_text,
    effective_index_status,
    index_status_reason,
)
from services.tokenizer import query_terms, tokenize

EMPTY_NO_SCOPE = "NO_SCOPE"
EMPTY_ALL_SOURCES_DELETED = "ALL_SOURCES_DELETED"
EMPTY_SOURCES_UNAVAILABLE = "SOURCES_UNAVAILABLE"
EMPTY_INDEX_NOT_READY = "INDEX_NOT_READY"
EMPTY_FILTERED_OUT = "FILTERED_OUT"
EMPTY_NO_SEARCHABLE_CONTENT = "NO_SEARCHABLE_CONTENT"
EMPTY_NO_MATCH = "NO_MATCH"

EMPTY_MESSAGES = {
    EMPTY_NO_SCOPE: "该事项还没有固定引用任何文档版本",
    EMPTY_ALL_SOURCES_DELETED: "范围内所有来源都已删除，无法检索",
    EMPTY_SOURCES_UNAVAILABLE: "范围内来源版本缺失或不可用，无法检索",
    EMPTY_INDEX_NOT_READY: "范围内的文档尚未完成索引，请等待索引完成或重建索引",
    EMPTY_FILTERED_OUT: "当前过滤条件下没有可检索的来源",
    EMPTY_NO_SEARCHABLE_CONTENT: "范围内没有可检索的文本块",
    EMPTY_NO_MATCH: "范围内没有匹配该问题的证据片段",
}

DELETED_STATES = {"document_deleted", "workspace_deleted"}
UNAVAILABLE_STATES = {
    "version_missing",
    "document_missing",
    "workspace_missing",
}


class _StopRetrieval(Exception):
    def __init__(self, reason: str, note: Optional[str] = None) -> None:
        self.reason = reason
        self.note = note or EMPTY_MESSAGES.get(reason)
        super().__init__(self.note)


@dataclass(frozen=True)
class RetrievalFilters:
    workspace_ids: Tuple[str, ...] = ()
    document_version_ids: Tuple[str, ...] = ()
    document_ids: Tuple[str, ...] = ()
    file_suffixes: Tuple[str, ...] = ()
    chunk_types: Tuple[str, ...] = ()
    applicable_scopes: Tuple[str, ...] = ()
    deletion_status: str = "active"

    @classmethod
    def from_input(cls, value: Any) -> "RetrievalFilters":
        if value is None:
            return cls()

        def items(name: str) -> Tuple[str, ...]:
            raw = getattr(value, name, None)
            if raw is None and isinstance(value, dict):
                raw = value.get(name)
            if raw is None:
                return ()
            if isinstance(raw, str):
                raw = [raw]
            return tuple(str(item).strip() for item in raw if str(item).strip())

        suffixes = []
        for suffix in items("file_suffixes"):
            suffix = suffix.lower()
            suffixes.append(suffix if suffix.startswith(".") else f".{suffix}")

        deletion_status = getattr(value, "deletion_status", None)
        if deletion_status is None and isinstance(value, dict):
            deletion_status = value.get("deletion_status")
        deletion_status = (deletion_status or "active").strip().lower()
        if deletion_status not in {"active", "deleted", "all"}:
            deletion_status = "active"

        return cls(
            workspace_ids=items("workspace_ids"),
            document_version_ids=items("document_version_ids"),
            document_ids=items("document_ids"),
            file_suffixes=tuple(suffixes),
            chunk_types=items("chunk_types"),
            applicable_scopes=items("applicable_scopes"),
            deletion_status=deletion_status,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "workspace_ids": list(self.workspace_ids),
            "document_version_ids": list(self.document_version_ids),
            "document_ids": list(self.document_ids),
            "file_suffixes": list(self.file_suffixes),
            "chunk_types": list(self.chunk_types),
            "applicable_scopes": list(self.applicable_scopes),
            "deletion_status": self.deletion_status,
        }


def _out_of_scope(code: str, message: str, **details: Any) -> AppError:
    return ForbiddenError(message, code=code, details=details)


def _validate_filters_against_scope(
    filters: RetrievalFilters, entries: Sequence[ScopeEntry]
) -> None:
    scope_workspaces = {entry.item.workspace_id for entry in entries}
    scope_versions = {entry.item.document_version_id for entry in entries}
    scope_documents = {
        entry.version.document_id for entry in entries if entry.version is not None
    }
    extra_workspaces = set(filters.workspace_ids) - scope_workspaces
    if extra_workspaces:
        raise _out_of_scope(
            "WORKSPACE_OUT_OF_SCOPE",
            "过滤条件包含不在该事项范围内的资料空间",
            workspace_ids=sorted(extra_workspaces),
        )
    extra_versions = set(filters.document_version_ids) - scope_versions
    if extra_versions:
        raise _out_of_scope(
            "VERSION_OUT_OF_SCOPE",
            "过滤条件包含不在该事项范围内的文档版本",
            document_version_ids=sorted(extra_versions),
        )
    extra_documents = set(filters.document_ids) - scope_documents
    if extra_documents:
        raise _out_of_scope(
            "DOCUMENT_OUT_OF_SCOPE",
            "过滤条件包含不在该事项范围内的文档",
            document_ids=sorted(extra_documents),
        )


def _matches_filters(entry: ScopeEntry, filters: RetrievalFilters) -> bool:
    if entry.source_state == "unauthorized":
        return False

    if filters.workspace_ids and entry.item.workspace_id not in filters.workspace_ids:
        return False
    if (
        filters.document_version_ids
        and entry.item.document_version_id not in filters.document_version_ids
    ):
        return False

    version = entry.version
    if filters.document_ids:
        if version is None or version.document_id not in filters.document_ids:
            return False
    if filters.file_suffixes:
        if version is None or version.file_suffix.lower() not in filters.file_suffixes:
            return False
    if filters.applicable_scopes:
        scope_value = (version.applicable_scope or "") if version else ""
        if scope_value not in filters.applicable_scopes:
            return False

    if filters.deletion_status == "active":
        return entry.source_state == "active"
    if filters.deletion_status == "deleted":
        return entry.source_state in DELETED_STATES
    return True


def _excluded_reason(entry: ScopeEntry, filters: RetrievalFilters) -> str:
    if entry.source_state == "unauthorized":
        return "UNAUTHORIZED"
    if filters.deletion_status == "active" and entry.source_state in DELETED_STATES:
        return "SOURCE_DELETED"
    if (
        filters.deletion_status == "active"
        and entry.source_state in UNAVAILABLE_STATES
    ):
        return "SOURCE_UNAVAILABLE"
    if filters.deletion_status == "deleted" and entry.source_state not in DELETED_STATES:
        return "NOT_DELETED"
    return "FILTERED_OUT"


def _query_candidate_chunks(
    db: Session,
    *,
    version_ids: Sequence[str],
    index_version: str,
    filters: RetrievalFilters,
    max_candidates: int,
) -> List[RetrievalChunk]:
    if not version_ids:
        return []
    statement = select(RetrievalChunk).where(
        RetrievalChunk.document_version_id.in_(list(version_ids)),
        RetrievalChunk.status == "active",
        RetrievalChunk.index_version == index_version,
    )
    if filters.chunk_types:
        statement = statement.where(
            RetrievalChunk.chunk_type.in_(list(filters.chunk_types))
        )
    statement = statement.order_by(
        RetrievalChunk.document_version_id,
        RetrievalChunk.page,
        RetrievalChunk.block_index,
        RetrievalChunk.chunk_index,
        RetrievalChunk.id,
    ).limit(max_candidates)
    return list(db.scalars(statement).all())


def _rrf(
    vector_rank: Dict[str, int],
    keyword_rank: Dict[str, int],
    *,
    rrf_k: int,
    vector_weight: float,
    keyword_weight: float,
) -> List[Tuple[str, float]]:
    identifiers = set(vector_rank) | set(keyword_rank)
    scored: List[Tuple[str, float]] = []
    for chunk_id in identifiers:
        score = 0.0
        if chunk_id in vector_rank:
            score += vector_weight / (rrf_k + vector_rank[chunk_id])
        if chunk_id in keyword_rank:
            score += keyword_weight / (rrf_k + keyword_rank[chunk_id])
        scored.append((chunk_id, score))
    scored.sort(
        key=lambda item: (
            -item[1],
            vector_rank.get(item[0], 10**9),
            keyword_rank.get(item[0], 10**9),
            item[0],
        )
    )
    return scored


def _result_payload(
    *,
    chunk: RetrievalChunk,
    span: Optional[EvidenceSpan],
    entry: Optional[ScopeEntry],
    vector_similarity: Optional[float],
    vector_rank: Optional[int],
    keyword_score: Optional[float],
    keyword_rank: Optional[int],
    fused_score: float,
    query_tokens: Sequence[str],
) -> Dict[str, Any]:
    version = entry.version if entry else None
    workspace = entry.workspace if entry else None
    bboxes = (
        overlapping_bboxes(span.bboxes or [], chunk.char_start, chunk.char_end)
        if span is not None
        else []
    )
    chunk_token_set = set(tokenize(chunk_index_text(chunk)))
    matched_terms = [token for token in query_tokens if token in chunk_token_set][:20]

    workspace_name = workspace.name if workspace else chunk.workspace_name
    document_name = chunk.document_name
    return {
        # id 保持为 EvidenceSpan ID，前端证据卡与原文高亮直接可用
        "id": chunk.evidence_span_id,
        "stable_id": chunk.id,
        "chunk_id": chunk.id,
        "evidence_span_id": chunk.evidence_span_id,
        "document_version_id": chunk.document_version_id,
        "document_id": chunk.document_id,
        "workspace_id": chunk.workspace_id,
        "workspace_name": workspace_name,
        "source_label": f"{workspace_name} / {document_name}",
        "document_name": document_name,
        "file_name": chunk.file_name,
        "file_suffix": chunk.file_suffix,
        "file_version": chunk.file_version,
        "applicable_scope": (
            version.applicable_scope if version is not None else chunk.applicable_scope
        ),
        "upload_source": (
            version.upload_source if version is not None else chunk.upload_source
        ),
        "page": chunk.page,
        "page_count": version.page_count if version and version.page_count else 1,
        "support_level": version.support_level if version else "pending",
        "block_index": chunk.block_index,
        "chunk_index": chunk.chunk_index,
        "kind": chunk.chunk_type,
        "chunk_type": chunk.chunk_type,
        "section_title": chunk.section_title,
        "text": chunk.text,
        "span_text": span.text if span is not None else chunk.text,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "span_char_start": chunk.span_char_start,
        "span_char_end": chunk.span_char_end,
        "bboxes": bboxes,
        "context_before": span.context_before if span is not None else None,
        "context_after": span.context_after if span is not None else None,
        "matched_terms": matched_terms,
        "scores": {
            "fused": round(fused_score, 8),
            "vector_similarity": (
                round(vector_similarity, 6) if vector_similarity is not None else None
            ),
            "vector_rank": vector_rank,
            "keyword": round(keyword_score, 6) if keyword_score is not None else None,
            "keyword_rank": keyword_rank,
        },
        "source_status": "active",
        "source_available": True,
        "is_sample": False,
    }


def _log_result(result: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "id",
        "stable_id",
        "chunk_id",
        "evidence_span_id",
        "document_version_id",
        "document_id",
        "workspace_id",
        "workspace_name",
        "source_label",
        "document_name",
        "file_name",
        "file_suffix",
        "file_version",
        "applicable_scope",
        "upload_source",
        "page",
        "page_count",
        "support_level",
        "block_index",
        "chunk_index",
        "kind",
        "chunk_type",
        "section_title",
        "text",
        "span_text",
        "char_start",
        "char_end",
        "span_char_start",
        "span_char_end",
        "matched_terms",
        "scores",
        "source_status",
        "source_available",
    )
    return {key: result.get(key) for key in keys}


def _source_state_for_result(
    db: Session, result: Dict[str, Any]
) -> Tuple[str, bool]:
    workspace_id = result.get("workspace_id")
    version_id = result.get("document_version_id")
    chunk_id = result.get("chunk_id")

    workspace = db.get(Workspace, workspace_id) if workspace_id else None
    if workspace is None:
        return "workspace_missing", False
    if workspace.deleted_at is not None:
        return "workspace_deleted", False

    version = db.get(DocumentVersion, version_id) if version_id else None
    if version is None:
        return "version_missing", False

    document = db.get(Document, version.document_id)
    if document is None:
        return "document_missing", False
    if document.deleted_at is not None:
        return "document_deleted", False

    chunk = db.get(RetrievalChunk, chunk_id) if chunk_id else None
    if chunk is None:
        return "chunk_missing", False
    if chunk.status != "active":
        return f"chunk_{chunk.status}", False
    return "active", True


def annotate_log_sources(
    db: Session, results: Iterable[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for result in results:
        item = dict(result)
        state, available = _source_state_for_result(db, item)
        item["source_status"] = state
        item["source_available"] = available
        annotated.append(item)
    return annotated


def _persist_outcome(
    db: Session,
    *,
    case: Case,
    principal: Principal,
    query: str,
    filters: RetrievalFilters,
    scope_snapshot: Dict[str, Any],
    config: IndexConfig,
    status: str,
    empty_reason: Optional[str],
    note: Optional[str],
    results: List[Dict[str, Any]],
    counts: Dict[str, Any],
    diagnostics: Dict[str, Any],
    latency_ms: int,
    record_run: bool,
) -> Tuple[Optional[Run], RetrievalLog]:
    scope_hash = scope_snapshot.get("scope_hash") or compute_scope_hash(
        load_scope_entries(db, case.id)
    )
    log = RetrievalLog(
        case_id=case.id,
        owner_id=principal.id,
        query=query,
        filters=filters.as_dict(),
        scope_snapshot=scope_snapshot,
        scope_hash=scope_hash,
        status=status,
        empty_reason=empty_reason,
        note=note,
        result_count=len(results),
        counts=counts,
        results=[_log_result(result) for result in results],
        diagnostics=diagnostics,
        config_snapshot=config.to_dict(),
        index_version=config.index_version,
        latency_ms=latency_ms,
    )
    db.add(log)
    db.flush()

    run: Optional[Run] = None
    if record_run:
        run = Run(
            case_id=case.id,
            status="succeeded",
            query=query,
            scope_snapshot=scope_snapshot,
            scope_hash=scope_hash,
            index_version=config.index_version,
            retrieval_log_id=log.id,
            finished_at=utcnow(),
        )
        db.add(run)
        db.flush()
        log.run_id = run.id

    db.commit()
    db.refresh(log)
    if run is not None:
        db.refresh(run)
    return run, log


def retrieve_evidence(
    db: Session,
    *,
    case_id: str,
    principal: Principal,
    query: str,
    filters: Any = None,
    top_k: Optional[int] = None,
    record_run: bool = True,
) -> Dict[str, Any]:
    """Case 级证据检索入口。返回结果、范围快照、诊断与检索日志 ID。"""
    started_at = time.perf_counter()
    settings = get_settings()
    config = get_index_config()
    case = require_case_access(db, case_id, principal)
    retrieval_filters = RetrievalFilters.from_input(filters)
    limit = int(top_k or settings.retrieval_default_top_k)
    limit = max(1, min(limit, 20))

    entries = load_scope_entries(db, case.id, principal_id=principal.id)
    scope_snapshot = build_scope_snapshot(case, entries, principal_id=principal.id)
    scope_hash = compute_scope_hash(entries)

    counts: Dict[str, Any] = {
        "scope_items": len(entries),
        "unauthorized_sources": sum(
            1 for entry in entries if entry.source_state == "unauthorized"
        ),
        "deleted_sources": sum(
            1 for entry in entries if entry.source_state in DELETED_STATES
        ),
        "unavailable_sources": sum(
            1 for entry in entries if entry.source_state in UNAVAILABLE_STATES
        ),
        "matched_sources": 0,
        "searchable_sources": 0,
        "indexed_sources": 0,
        "not_ready_sources": 0,
        "candidate_chunks": 0,
        "vector_hits": 0,
        "keyword_hits": 0,
        "fused_candidates": 0,
        "returned": 0,
    }
    index_status_counts: Dict[str, int] = {}
    excluded_sources: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []
    not_ready: List[Dict[str, Any]] = []
    query_tokens: List[str] = []
    diagnostics: Dict[str, Any] = {
        "fusion": "rrf",
        "rrf_k": settings.retrieval_rrf_k,
        "vector_weight": settings.retrieval_vector_weight,
        "keyword_weight": settings.retrieval_keyword_weight,
        "index_version": config.index_version,
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "embedding_dimension": config.embedding_dimension,
        "chunk_strategy": config.chunk_strategy,
        "tokenizer_version": config.tokenizer_version,
        "vector_baseline": [],
        "keyword_ranking": [],
    }
    results: List[Dict[str, Any]] = []

    try:
        if not entries:
            raise _StopRetrieval(EMPTY_NO_SCOPE)

        unauthorized = [
            entry for entry in entries if entry.source_state == "unauthorized"
        ]
        if unauthorized:
            # 失败关闭：范围中只要出现非当前主体的空间，就拒绝整次检索，
            # 而不是悄悄少查一部分来源。
            raise ForbiddenError(
                "该事项范围中的资料空间不属于当前访问主体",
                code="SCOPE_FORBIDDEN",
                details={
                    "case_id": case.id,
                    "workspace_ids": sorted(
                        {entry.item.workspace_id for entry in unauthorized}
                    ),
                },
            )

        _validate_filters_against_scope(retrieval_filters, entries)

        matched_entries: List[ScopeEntry] = []
        for entry in entries:
            if _matches_filters(entry, retrieval_filters):
                matched_entries.append(entry)
            else:
                excluded_sources.append(
                    {
                        "workspace_id": entry.item.workspace_id,
                        "workspace_name": (
                            entry.workspace.name if entry.workspace else None
                        ),
                        "document_version_id": entry.item.document_version_id,
                        "document_name": (
                            entry.document.display_name if entry.document else None
                        ),
                        "source_state": entry.source_state,
                        "reason": _excluded_reason(entry, retrieval_filters),
                    }
                )
        counts["matched_sources"] = len(matched_entries)

        if not matched_entries:
            if entries and all(
                entry.source_state in DELETED_STATES | UNAVAILABLE_STATES
                for entry in entries
            ):
                if any(entry.source_state in DELETED_STATES for entry in entries):
                    raise _StopRetrieval(EMPTY_ALL_SOURCES_DELETED)
                raise _StopRetrieval(EMPTY_SOURCES_UNAVAILABLE)
            if (
                retrieval_filters.deletion_status == "deleted"
                and any(
                    entry.source_state in DELETED_STATES for entry in entries
                )
            ):
                raise _StopRetrieval(
                    EMPTY_ALL_SOURCES_DELETED,
                    "已删除来源不会进入检索候选集",
                )
            raise _StopRetrieval(EMPTY_FILTERED_OUT)

        if retrieval_filters.deletion_status == "deleted":
            # 已删除来源已从索引移除；这里明确返回空，而不是伪装成“没匹配”
            raise _StopRetrieval(
                EMPTY_ALL_SOURCES_DELETED,
                "已删除来源不会进入检索候选集",
            )

        searchable_entries = [
            entry for entry in matched_entries if entry.source_state == "active"
        ]
        counts["searchable_sources"] = len(searchable_entries)
        if not searchable_entries:
            if any(entry.source_state in DELETED_STATES for entry in matched_entries):
                raise _StopRetrieval(EMPTY_ALL_SOURCES_DELETED)
            raise _StopRetrieval(EMPTY_SOURCES_UNAVAILABLE)

        ready_entries: List[ScopeEntry] = []
        for entry in searchable_entries:
            version = entry.version
            effective = effective_index_status(version, config) if version else "pending"
            index_status_counts[effective] = index_status_counts.get(effective, 0) + 1
            is_ready = (
                version is not None
                and version.parse_status == "success"
                and effective == "ready"
            )
            if is_ready:
                ready_entries.append(entry)
            else:
                not_ready.append(
                    {
                        "workspace_id": entry.item.workspace_id,
                        "workspace_name": (
                            entry.workspace.name if entry.workspace else None
                        ),
                        "document_version_id": entry.item.document_version_id,
                        "document_name": (
                            entry.document.display_name if entry.document else None
                        ),
                        "parse_status": version.parse_status if version else None,
                        "index_status": effective,
                        "index_reason": index_status_reason(effective),
                        "index_error_code": (
                            version.index_error_code if version else None
                        ),
                    }
                )
        counts["indexed_sources"] = len(ready_entries)
        counts["not_ready_sources"] = len(not_ready)

        if not ready_entries:
            diagnostics["not_ready_sources"] = not_ready
            raise _StopRetrieval(
                EMPTY_INDEX_NOT_READY,
                "范围内文档索引未就绪："
                + "、".join(
                    sorted(
                        {
                            item["index_status"] or "pending"
                            for item in not_ready
                        }
                    )
                ),
            )

        version_ids = [
            entry.item.document_version_id for entry in ready_entries
        ]
        chunks = _query_candidate_chunks(
            db,
            version_ids=version_ids,
            index_version=config.index_version,
            filters=retrieval_filters,
            max_candidates=settings.retrieval_max_candidates,
        )
        counts["candidate_chunks"] = len(chunks)
        if not chunks:
            raise _StopRetrieval(EMPTY_NO_SEARCHABLE_CONTENT)

        entry_by_version = {
            entry.item.document_version_id: entry for entry in ready_entries
        }
        chunks_by_id = {chunk.id: chunk for chunk in chunks}

        query_tokens = query_terms(query)
        vector_rank: Dict[str, int] = {}
        vector_similarity: Dict[str, float] = {}
        try:
            query_vector = embed_query(query)
            vector_hits = vector_store.query(
                index_version=config.index_version,
                document_version_ids=version_ids,
                embedding=query_vector,
                n_results=max(
                    limit * 4,
                    settings.retrieval_candidate_k,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — 向量不可用时降级到关键词
            vector_hits = []
            warnings.append({"code": "VECTOR_UNAVAILABLE", "message": str(exc)})
            diagnostics["vector_available"] = False
        else:
            diagnostics["vector_available"] = True

        baseline: List[Dict[str, Any]] = []
        for hit in vector_hits:
            chunk_id = hit["chunk_id"]
            if chunk_id not in chunks_by_id:
                continue
            rank = len(vector_rank) + 1
            vector_rank[chunk_id] = rank
            vector_similarity[chunk_id] = float(hit["similarity"])
            baseline.append(
                {
                    "chunk_id": chunk_id,
                    "rank": rank,
                    "similarity": round(float(hit["similarity"]), 6),
                }
            )
        diagnostics["vector_baseline"] = baseline
        counts["vector_hits"] = len(vector_rank)

        keyword_rank: Dict[str, int] = {}
        keyword_scores: Dict[str, float] = {}
        tokenized: List[List[str]] = []
        if query_tokens:
            tokenized = [tokenize(chunk_index_text(chunk)) for chunk in chunks]
        if query_tokens and any(tokenized):
            bm25 = BM25Plus(tokenized)
            scores = bm25.get_scores(query_tokens)
            ranked = sorted(
                (
                    (float(score), chunk.id)
                    for score, chunk in zip(scores, chunks)
                    if float(score) > 0
                ),
                key=lambda item: (-item[0], item[1]),
            )
            for rank, (score, chunk_id) in enumerate(ranked, start=1):
                keyword_rank[chunk_id] = rank
                keyword_scores[chunk_id] = score
        diagnostics["keyword_ranking"] = [
            {
                "chunk_id": chunk_id,
                "rank": rank,
                "score": round(keyword_scores[chunk_id], 6),
            }
            for chunk_id, rank in list(keyword_rank.items())[:100]
        ]
        counts["keyword_hits"] = len(keyword_rank)

        # 单字命中（如“的”“年”）不足以证明匹配；至少需要一个多字词项，
        # 或一个达到相似度阈值的向量命中，否则视为无匹配。
        keyword_content_hit = False
        for chunk_id in list(keyword_rank)[:100]:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue
            chunk_tokens = set(tokenize(chunk_index_text(chunk)))
            if any(len(token) >= 2 and token in chunk_tokens for token in query_tokens):
                keyword_content_hit = True
                break
        max_vector_similarity = max(vector_similarity.values(), default=0.0)
        diagnostics["keyword_content_hit"] = keyword_content_hit
        diagnostics["max_vector_similarity"] = round(max_vector_similarity, 6)
        if (
            not keyword_content_hit
            and max_vector_similarity < settings.retrieval_min_vector_similarity
        ):
            raise _StopRetrieval(
                EMPTY_NO_MATCH,
                "没有相似度或关键词匹配达到阈值的证据片段",
            )

        fused = _rrf(
            vector_rank,
            keyword_rank,
            rrf_k=settings.retrieval_rrf_k,
            vector_weight=settings.retrieval_vector_weight,
            keyword_weight=settings.retrieval_keyword_weight,
        )
        counts["fused_candidates"] = len(fused)
        if not fused:
            raise _StopRetrieval(EMPTY_NO_MATCH)

        selected = fused[:limit]
        span_ids = {
            chunks_by_id[chunk_id].evidence_span_id
            for chunk_id, _score in selected
            if chunk_id in chunks_by_id
        }
        spans = {
            span.id: span
            for span in db.scalars(
                select(EvidenceSpan).where(EvidenceSpan.id.in_(list(span_ids)))
            ).all()
        } if span_ids else {}

        for chunk_id, fused_score in selected:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue
            results.append(
                _result_payload(
                    chunk=chunk,
                    span=spans.get(chunk.evidence_span_id),
                    entry=entry_by_version.get(chunk.document_version_id),
                    vector_similarity=vector_similarity.get(chunk_id),
                    vector_rank=vector_rank.get(chunk_id),
                    keyword_score=keyword_scores.get(chunk_id),
                    keyword_rank=keyword_rank.get(chunk_id),
                    fused_score=fused_score,
                    query_tokens=query_tokens,
                )
            )
        counts["returned"] = len(results)

        if not results:
            raise _StopRetrieval(EMPTY_NO_MATCH)

        min_similarity = settings.retrieval_min_vector_similarity
        strong = any(
            any(len(term) >= 2 for term in result["matched_terms"])
            or (
                result["scores"]["vector_similarity"] is not None
                and result["scores"]["vector_similarity"] >= min_similarity
            )
            for result in results
        )
        status = "ok" if strong else "insufficient"
        empty_reason = None
        note = (
            None
            if status == "ok"
            else "已返回部分候选，但匹配信号较弱，建议补充关键词或核对原文"
        )
    except _StopRetrieval as stop:
        status = "empty"
        empty_reason = stop.reason
        note = stop.note
    except ForbiddenError:
        raise
    except Exception as exc:  # noqa: BLE001 — 先记录失败日志，再向上抛出
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        log = RetrievalLog(
            case_id=case.id,
            owner_id=principal.id,
            query=query,
            filters=retrieval_filters.as_dict(),
            scope_snapshot=scope_snapshot,
            scope_hash=scope_hash,
            status="error",
            empty_reason=None,
            note="检索执行失败",
            result_count=0,
            counts=counts,
            results=[],
            diagnostics=diagnostics,
            config_snapshot=config.to_dict(),
            index_version=config.index_version,
            latency_ms=latency_ms,
            error_code=type(exc).__name__,
            error_message=str(exc),
        )
        db.add(log)
        if record_run:
            db.add(
                Run(
                    case_id=case.id,
                    status="failed",
                    query=query,
                    scope_snapshot=scope_snapshot,
                    scope_hash=scope_hash,
                    index_version=config.index_version,
                    retrieval_log_id=log.id,
                    finished_at=utcnow(),
                )
            )
        db.commit()
        raise

    latency_ms = int((time.perf_counter() - started_at) * 1000)

    diagnostics.update(
        {
            "query_tokens": query_tokens,
            "returned": counts["returned"],
            "vector_hits": counts["vector_hits"],
            "keyword_hits": counts["keyword_hits"],
            "warnings": warnings,
            "index_status_counts": index_status_counts,
        }
    )
    counts["filtered_out_sources"] = len(excluded_sources)
    counts["warnings"] = len(warnings)

    run, log = _persist_outcome(
        db,
        case=case,
        principal=principal,
        query=query,
        filters=retrieval_filters,
        scope_snapshot=scope_snapshot,
        config=config,
        status=status,
        empty_reason=empty_reason,
        note=note,
        results=results,
        counts=counts,
        diagnostics=diagnostics,
        latency_ms=latency_ms,
        record_run=record_run,
    )

    return {
        "case_id": case.id,
        "run_id": run.id if run is not None else None,
        "retrieval_log_id": log.id,
        "query": query,
        "status": status,
        "empty_reason": empty_reason,
        "note": note,
        "filters": retrieval_filters.as_dict(),
        "scope_snapshot": scope_snapshot,
        "scope_hash": scope_hash,
        "index_status": {
            "index_version": config.index_version,
            "embedding_provider": config.embedding_provider,
            "embedding_model": config.embedding_model,
            "embedding_dimension": config.embedding_dimension,
            "status_counts": index_status_counts,
            "not_ready_sources": not_ready,
        },
        "counts": counts,
        "excluded_sources": excluded_sources[:50],
        "warnings": warnings,
        "diagnostics": diagnostics,
        "results": results,
        "latency_ms": latency_ms,
    }
