"""SQLAlchemy 数据模型。

实体关系：
    Workspace 1--n Document 1--n DocumentVersion 1--n DocumentPage
                                                1--n EvidenceSpan
                                                1--n ParseJob

DocumentVersion 一旦创建，其文件内容标识（file_hash / file_path / version）
不再修改。重新上传同名但内容不同的文件会产生新版本，旧版本的页面与证据
片段保持不变。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    documents: Mapped[List["Document"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class Document(Base):
    """逻辑文档。同名文件的不同内容版本挂在同一个 Document 下。"""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "normalized_name", name="uq_documents_workspace_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("doc"))
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    latest_version_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version",
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_versions_version"),
        UniqueConstraint("workspace_id", "file_hash", name="uq_document_versions_hash"),
        Index("idx_document_versions_workspace", "workspace_id"),
        Index("idx_document_versions_parse_status", "parse_status"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("ver")
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 内容标识：创建后不再改变
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_suffix: Mapped[str] = mapped_column(String(16), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    upload_source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    applicable_scope: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # 解析状态：uploaded -> parsing -> indexing -> success / failed
    parse_status: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False)
    parse_error_code: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    parse_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    support_level: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 检索索引状态：pending -> indexing -> ready / failed / deleted
    index_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
    index_error_code: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    index_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    index_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="versions")
    pages: Mapped[List["DocumentPage"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="DocumentPage.page_number"
    )
    spans: Mapped[List["EvidenceSpan"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    jobs: Mapped[List["ParseJob"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_version_id", "page_number", name="uq_pages_version_page"),
        Index("idx_document_pages_version", "document_version_id"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("page")
    )
    document_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_blank: Mapped[bool] = mapped_column(default=False, nullable=False)

    version: Mapped["DocumentVersion"] = relationship(back_populates="pages")


class EvidenceSpan(Base):
    """不可变证据片段。

    char_start / char_end 均是在对应 DocumentPage.text 中的字符偏移。
    bboxes 中每个矩形通过 char_start / char_end 映射到同一段页面文本，
    因此既可从字符定位到文字框，也可从文字框回溯到字符范围。
    """

    __tablename__ = "evidence_spans"
    __table_args__ = (
        Index("idx_evidence_spans_version", "document_version_id"),
        Index("idx_evidence_spans_page", "document_version_id", "page"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("span")
    )
    document_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="paragraph", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    bboxes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    context_before: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_after: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    version: Mapped["DocumentVersion"] = relationship(back_populates="spans")


class ParseJob(Base):
    __tablename__ = "parse_jobs"
    __table_args__ = (Index("idx_parse_jobs_version", "document_version_id", "created_at"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("job")
    )
    document_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    version: Mapped["DocumentVersion"] = relationship(back_populates="jobs")


class Case(Base):
    """一次决策或核对任务。

    Case 是检索范围的拥有者，可以固定引用多个资料空间中的文档版本。
    资料空间只负责所有权与存储，不限制 Case 的引用范围。
    """

    __tablename__ = "cases"
    __table_args__ = (Index("idx_cases_owner", "owner_id"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("case")
    )
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_workspace_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    scope_items: Mapped[List["RetrievalScopeItem"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    facts: Mapped[List["Fact"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    check_items: Mapped[List["CheckItem"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    runs: Mapped[List["Run"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class RetrievalScopeItem(Base):
    """Case 固定引用的文档版本；可来自任意一个所有者有权访问的空间。"""

    __tablename__ = "case_scope_items"
    __table_args__ = (
        UniqueConstraint("case_id", "document_version_id", name="uq_case_scope_version"),
        Index("idx_case_scope_case", "case_id"),
        Index("idx_case_scope_version", "document_version_id"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("scope")
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    case: Mapped["Case"] = relationship(back_populates="scope_items")


class Fact(Base):
    """用户提供或确认的事实，用于条件核对。"""

    __tablename__ = "facts"
    __table_args__ = (UniqueConstraint("case_id", "key", name="uq_facts_case_key"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("fact")
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="user_input", nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    case: Mapped["Case"] = relationship(back_populates="facts")


class CheckItem(Base):
    """条件核对清单项，证据与事实均可追溯。"""

    __tablename__ = "check_items"
    __table_args__ = (Index("idx_check_items_case", "case_id"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("check")
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    premise: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    required_facts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_span_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    human_confirmed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    case: Mapped["Case"] = relationship(back_populates="check_items")


class Run(Base):
    """Case 的一次执行，保存范围快照与状态，供删除影响和历史标注使用。"""

    __tablename__ = "runs"
    __table_args__ = (Index("idx_runs_case", "case_id", "created_at"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("run")
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # 范围快照指纹；Case 范围变化后旧 Run 标记为 stale
    scope_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    index_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    retrieval_log_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    stale_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    stale_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="runs")


class SourceTombstone(Base):
    """已删除来源的墓碑，供历史记录标注来源已删除或不可用。

    不设外键：文档或空间硬删除后墓碑仍需保留文件名、版本和哈希。
    """

    __tablename__ = "source_tombstones"
    __table_args__ = (
        Index("idx_source_tombstones_document", "document_id"),
        Index("idx_source_tombstones_version", "document_version_id"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("tombstone")
    )
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    deleted_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reason: Mapped[str] = mapped_column(String(48), default="document_deleted", nullable=False)


class RetrievalIndex(Base):
    """索引配置清单。

    index_version 由嵌入模型、维度、分块策略、分词器与融合策略共同决定。
    配置变化会产生新的 fingerprint，旧版本索引不会再被检索使用。
    """

    __tablename__ = "retrieval_indexes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    index_version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), default="ready", nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(48), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_strategy: Mapped[str] = mapped_column(String(48), nullable=False)
    chunk_max_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_overlap_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    tokenizer_version: Mapped[str] = mapped_column(String(48), nullable=False)
    fusion_strategy: Mapped[str] = mapped_column(String(48), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class RetrievalChunk(Base):
    """可检索文本块，稳定映射回不可变 EvidenceSpan。

    一个 EvidenceSpan 可能被切成多个检索块；每个块保留其在页面文本中的
    绝对字符范围，以及所属 span 的范围。chunk.id 在相同版本、span、序号
    与文本内容下保持稳定，重复建索引不会改变检索结果里的 ID。
    """

    __tablename__ = "retrieval_chunks"
    __table_args__ = (
        Index("idx_retrieval_chunks_version", "document_version_id", "status"),
        Index("idx_retrieval_chunks_workspace", "workspace_id", "status"),
        Index("idx_retrieval_chunks_span", "evidence_span_id"),
        Index("idx_retrieval_chunks_index", "index_version", "status"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    index_version: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_version_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    evidence_span_id: Mapped[str] = mapped_column(String(64), nullable=False)

    workspace_name: Mapped[str] = mapped_column(String(200), nullable=False)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_suffix: Mapped[str] = mapped_column(String(16), nullable=False)
    file_version: Mapped[int] = mapped_column(Integer, nullable=False)
    applicable_scope: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    upload_source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), default="paragraph", nullable=False)
    # 最近一级标题，用于检索时补足片段缺失的上下文
    section_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # 页面文本中的绝对字符范围
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    # 所属 EvidenceSpan 的范围
    span_char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class RetrievalLog(Base):
    """一次检索的完整记录：范围快照、过滤条件、结果与空结果原因。"""

    __tablename__ = "retrieval_logs"
    __table_args__ = (
        Index("idx_retrieval_logs_case", "case_id", "created_at"),
        Index("idx_retrieval_logs_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("rlog")
    )
    case_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    scope_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    scope_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ok", nullable=False)
    empty_reason: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    results: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    index_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# 版本内容不可变保护
# ---------------------------------------------------------------------------

IMMUTABLE_VERSION_FIELDS = (
    "document_id",
    "workspace_id",
    "file_name",
    "file_suffix",
    "media_type",
    "file_hash",
    "file_size",
    "file_path",
    "version",
    "uploaded_by",
    "uploaded_at",
)


@event.listens_for(DocumentVersion, "before_update")
def _prevent_version_content_change(mapper, connection, target) -> None:  # noqa: ANN001
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_VERSION_FIELDS
        if state.attrs[field].history.has_changes()
    ]
    if changed:
        raise ValueError(f"文档版本内容不可修改：{', '.join(changed)}")
