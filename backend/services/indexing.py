"""检索索引构建：分块 -> 嵌入 -> Chroma + SQLite 映射。

SQLite 保存每个检索块的元数据与到 EvidenceSpan 的映射，Chroma 保存
向量并用于召回。两者使用同一个稳定 chunk_id 关联，因此检索结果可以
返回真实原文片段、版本、空间与精确字符范围。

索引失败不会把解析结果判为失败：parse_status 仍为 success，但
index_status 为 failed，检索会明确返回 INDEX_NOT_READY。
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.database import SessionLocal
from db.models import (
    Document,
    DocumentVersion,
    EvidenceSpan,
    RetrievalChunk,
    RetrievalIndex,
    Workspace,
    utcnow,
)
from services import vector_store
from services.chunking import ChunkDraft, chunk_spans
from services.embedding import embed_texts
from services.index_config import IndexConfig, get_index_config

logger = logging.getLogger(__name__)

# 启动补齐、上传解析与手动重建可能并发，串行化索引写入
_index_lock = threading.RLock()

INDEX_ERROR_EMBEDDING = "EMBEDDING_FAILED"
INDEX_ERROR_VECTOR_STORE = "VECTOR_STORE_FAILED"
INDEX_ERROR_INTERNAL = "INDEX_INTERNAL_ERROR"


class IndexingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def effective_index_status(
    version: DocumentVersion, config: Optional[IndexConfig] = None
) -> str:
    """返回对当前配置有效的索引状态。

    ready 但 index_version 不是当前配置时视为 stale，需要重建。
    """
    config = config or get_index_config()
    status = version.index_status or "pending"
    if status == "ready" and version.index_version != config.index_version:
        return "stale"
    return status


def index_status_reason(status: str) -> Optional[str]:
    return {
        "pending": "INDEX_PENDING",
        "indexing": "INDEXING",
        "failed": "INDEX_FAILED",
        "stale": "INDEX_CONFIG_STALE",
        "deleted": "SOURCE_DELETED",
    }.get(status)


def _ensure_manifest(db: Session, config: IndexConfig, *, status: str = "ready") -> RetrievalIndex:
    manifest = db.scalars(
        select(RetrievalIndex).where(
            RetrievalIndex.index_version == config.index_version
        )
    ).first()
    if manifest is None:
        manifest = RetrievalIndex(
            id=f"idx_{config.index_version.replace('-', '_')}",
            index_version=config.index_version,
            status=status,
            embedding_provider=config.embedding_provider,
            embedding_model=config.embedding_model,
            embedding_dimension=config.embedding_dimension,
            chunk_strategy=config.chunk_strategy,
            chunk_max_chars=config.chunk_max_chars,
            chunk_overlap_chars=config.chunk_overlap_chars,
            tokenizer_version=config.tokenizer_version,
            fusion_strategy=config.fusion_strategy,
            chunk_count=0,
            version_count=0,
            config=config.to_dict(),
        )
        db.add(manifest)
        db.flush()
    else:
        manifest.status = status
        manifest.embedding_provider = config.embedding_provider
        manifest.embedding_model = config.embedding_model
        manifest.embedding_dimension = config.embedding_dimension
        manifest.chunk_strategy = config.chunk_strategy
        manifest.chunk_max_chars = config.chunk_max_chars
        manifest.chunk_overlap_chars = config.chunk_overlap_chars
        manifest.tokenizer_version = config.tokenizer_version
        manifest.fusion_strategy = config.fusion_strategy
        manifest.config = config.to_dict()

    chunk_count = db.scalar(
        select(func.count())
        .select_from(RetrievalChunk)
        .where(
            RetrievalChunk.index_version == config.index_version,
            RetrievalChunk.status == "active",
        )
    )
    version_count = db.scalar(
        select(func.count(func.distinct(RetrievalChunk.document_version_id))).where(
            RetrievalChunk.index_version == config.index_version,
            RetrievalChunk.status == "active",
        )
    )
    manifest.chunk_count = int(chunk_count or 0)
    manifest.version_count = int(version_count or 0)
    return manifest


def _chunk_row(
    draft: ChunkDraft,
    *,
    version: DocumentVersion,
    document: Document,
    workspace: Workspace,
    config: IndexConfig,
) -> RetrievalChunk:
    return RetrievalChunk(
        id=draft.stable_id(version.id),
        index_version=config.index_version,
        workspace_id=version.workspace_id,
        document_id=version.document_id,
        document_version_id=version.id,
        evidence_span_id=draft.evidence_span_id,
        workspace_name=workspace.name,
        document_name=document.display_name or version.file_name,
        file_name=version.file_name,
        file_suffix=version.file_suffix,
        file_version=version.version,
        applicable_scope=version.applicable_scope,
        upload_source=version.upload_source,
        chunk_index=draft.chunk_index,
        chunk_type=draft.chunk_type,
        section_title=draft.section_title,
        page=draft.page,
        block_index=draft.block_index,
        text=draft.text,
        char_start=draft.char_start,
        char_end=draft.char_end,
        span_char_start=draft.span_char_start,
        span_char_end=draft.span_char_end,
        content_hash=draft.content_hash,
        status="active",
        embedding_model=config.embedding_model,
    )


def chunk_index_text(row: RetrievalChunk) -> str:
    """用于嵌入与 BM25 的文本：片段正文 + 最近一级标题。"""
    if row.section_title and row.section_title.strip() not in row.text:
        return f"{row.section_title}\n{row.text}"
    return row.text


def _vector_metadata(row: RetrievalChunk) -> Dict[str, object]:
    return {
        "workspace_id": row.workspace_id,
        "document_id": row.document_id,
        "document_version_id": row.document_version_id,
        "evidence_span_id": row.evidence_span_id,
        "chunk_index": int(row.chunk_index),
        "page": int(row.page),
        "block_index": int(row.block_index),
        "chunk_type": row.chunk_type,
        "section_title": row.section_title or "",
        "file_suffix": row.file_suffix,
        "file_version": int(row.file_version),
        "applicable_scope": row.applicable_scope or "",
        "upload_source": row.upload_source or "",
        "index_version": row.index_version,
        "content_hash": row.content_hash,
    }


def _mark_index_failed(
    db: Session, version_id: str, code: str, message: str
) -> None:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        return
    version.index_status = "failed"
    version.index_error_code = code
    version.index_error = message[:2000]
    version.chunk_count = 0
    db.commit()


def build_version_index(
    db: Session,
    version: DocumentVersion,
    *,
    config: Optional[IndexConfig] = None,
    commit: bool = True,
) -> Dict[str, object]:
    with _index_lock:
        return _build_version_index(
            db, version, config=config, commit=commit
        )


def _build_version_index(
    db: Session,
    version: DocumentVersion,
    *,
    config: Optional[IndexConfig] = None,
    commit: bool = True,
) -> Dict[str, object]:
    """为一个文档版本建立可检索索引。失败时写入 index_status=failed。"""
    config = config or get_index_config()
    document = db.get(Document, version.document_id)
    workspace = db.get(Workspace, version.workspace_id)
    if document is None or workspace is None:
        raise IndexingError(INDEX_ERROR_INTERNAL, "文档或资料空间不存在，无法建索引")

    version.index_status = "indexing"
    version.index_error_code = None
    version.index_error = None
    db.flush()

    spans = list(
        db.scalars(
            select(EvidenceSpan)
            .where(EvidenceSpan.document_version_id == version.id)
            .order_by(EvidenceSpan.page, EvidenceSpan.block_index, EvidenceSpan.id)
        ).all()
    )
    settings = get_settings()
    drafts = chunk_spans(
        spans,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )

    try:
        rows: List[RetrievalChunk] = [
            _chunk_row(
                draft,
                version=version,
                document=document,
                workspace=workspace,
                config=config,
            )
            for draft in drafts
        ]

        embeddings: List[List[float]] = []
        if rows:
            try:
                embeddings = embed_texts([chunk_index_text(row) for row in rows])
            except Exception as exc:  # noqa: BLE001
                raise IndexingError(
                    INDEX_ERROR_EMBEDDING, f"文本向量化失败：{exc}"
                ) from exc
            if len(embeddings) != len(rows):
                raise IndexingError(
                    INDEX_ERROR_EMBEDDING,
                    f"向量数量与文本块数量不一致：{len(embeddings)} != {len(rows)}",
                )

        # 同一版本重建时，先清理旧块与旧向量，避免重复或旧模型向量混用
        db.execute(
            delete(RetrievalChunk).where(
                RetrievalChunk.document_version_id == version.id
            )
        )
        try:
            vector_store.delete_version(
                version.id, index_version=config.index_version
            )
        except Exception as exc:  # noqa: BLE001
            raise IndexingError(
                INDEX_ERROR_VECTOR_STORE, f"清理旧向量失败：{exc}"
            ) from exc

        for row in rows:
            db.add(row)
        db.flush()

        if rows:
            try:
                vector_store.upsert_chunks(
                    index_version=config.index_version,
                    entries=[
                        {
                            "id": row.id,
                            "text": row.text,
                            "metadata": _vector_metadata(row),
                        }
                        for row in rows
                    ],
                    embeddings=embeddings,
                )
            except Exception as exc:  # noqa: BLE001
                raise IndexingError(
                    INDEX_ERROR_VECTOR_STORE, f"写入向量失败：{exc}"
                ) from exc

        version.index_status = "ready"
        version.index_error_code = None
        version.index_error = None
        version.index_version = config.index_version
        version.embedding_model = config.embedding_model
        version.chunk_count = len(rows)
        version.indexed_at = utcnow()
        _ensure_manifest(db, config)
        if commit:
            db.commit()

        return {
            "version_id": version.id,
            "index_version": config.index_version,
            "chunk_count": len(rows),
            "status": "ready",
        }
    except IndexingError as exc:
        try:
            vector_store.delete_version(
                version.id, index_version=config.index_version
            )
        except Exception:  # noqa: BLE001 — 清理失败不掩盖原始错误
            pass
        db.rollback()
        _mark_index_failed(db, version.id, exc.code, exc.message)
        raise
    except Exception as exc:  # noqa: BLE001 — 未知异常统一落为索引失败
        try:
            vector_store.delete_version(
                version.id, index_version=config.index_version
            )
        except Exception:  # noqa: BLE001
            pass
        db.rollback()
        _mark_index_failed(
            db, version.id, INDEX_ERROR_INTERNAL, f"建索引失败：{exc}"
        )
        raise IndexingError(INDEX_ERROR_INTERNAL, f"建索引失败：{exc}") from exc


def run_index_job(version_id: str) -> str:
    """后台重建单个版本的索引，返回最终状态。"""
    with SessionLocal() as db:
        version = db.get(DocumentVersion, version_id)
        if version is None:
            return "missing"
        try:
            build_version_index(db, version)
            return "ready"
        except IndexingError:
            return "failed"
        except Exception:  # noqa: BLE001
            logger.exception("重建索引失败：%s", version_id)
            return "failed"


def backfill_pending_indexes(limit: int = 30) -> int:
    """启动时补齐尚未索引/索引配置过期的已解析版本。

    只在启动阶段抓取一次候选，避免长时间运行的后台线程与用户操作竞争。
    失败会写入 index_status=failed，不影响服务启动。
    """
    config = get_index_config()
    with SessionLocal() as db:
        versions = list(
            db.scalars(
                select(DocumentVersion)
                .join(Document, Document.id == DocumentVersion.document_id)
                .join(Workspace, Workspace.id == DocumentVersion.workspace_id)
                .where(
                    Document.deleted_at.is_(None),
                    Workspace.deleted_at.is_(None),
                    DocumentVersion.parse_status == "success",
                    DocumentVersion.index_status.in_(["pending", "failed", "indexing"]),
                )
                .order_by(DocumentVersion.uploaded_at)
                .limit(limit)
            ).all()
        )
        stale_versions = list(
            db.scalars(
                select(DocumentVersion)
                .join(Document, Document.id == DocumentVersion.document_id)
                .join(Workspace, Workspace.id == DocumentVersion.workspace_id)
                .where(
                    Document.deleted_at.is_(None),
                    Workspace.deleted_at.is_(None),
                    DocumentVersion.parse_status == "success",
                    DocumentVersion.index_status == "ready",
                    DocumentVersion.index_version != config.index_version,
                )
                .order_by(DocumentVersion.uploaded_at)
                .limit(limit)
            ).all()
        )
        targets = {version.id: version for version in versions + stale_versions}

    count = 0
    for version_id in targets:
        status = run_index_job(version_id)
        if status == "ready":
            count += 1
    return count


def remove_version_index(
    db: Session,
    version: DocumentVersion,
    *,
    reason: str = "DOCUMENT_DELETED",
    commit: bool = True,
) -> None:
    """文档删除时移除候选：清理向量并标记文本块与版本索引不可用。"""
    try:
        vector_store.delete_version(
            version.id, index_version=version.index_version
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("删除向量索引失败（继续标记不可用）：%s", exc)

    chunks = db.scalars(
        select(RetrievalChunk).where(
            RetrievalChunk.document_version_id == version.id
        )
    ).all()
    for chunk in chunks:
        chunk.status = "deleted"

    version.index_status = "deleted"
    version.index_error_code = reason
    version.index_error = "来源已删除，索引不再参与检索"
    version.chunk_count = 0
    if commit:
        db.commit()


def reset_version_index(
    db: Session,
    version: DocumentVersion,
    *,
    commit: bool = True,
) -> None:
    """重新解析或恢复前清除旧索引。"""
    try:
        vector_store.delete_version(
            version.id, index_version=version.index_version
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("重置向量索引失败：%s", exc)
    db.execute(
        delete(RetrievalChunk).where(
            RetrievalChunk.document_version_id == version.id
        )
    )
    version.index_status = "pending"
    version.index_error_code = None
    version.index_error = None
    version.index_version = None
    version.embedding_model = None
    version.chunk_count = None
    version.indexed_at = None
    if commit:
        db.commit()
