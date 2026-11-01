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
