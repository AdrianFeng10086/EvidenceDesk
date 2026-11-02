"""数据库对象 -> API 响应模型。"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import get_settings
from db.models import (
    Document,
    DocumentPage,
    DocumentVersion,
    EvidenceSpan,
    ParseJob,
    Workspace,
)
from schemas.document import (
    BBoxOut,
    DocumentDetailOut,
    DocumentSummaryOut,
    DocumentVersionOut,
    EvidenceSpanOut,
    PageContentOut,
    PageSummaryOut,
    ParseJobOut,
    WorkspaceOut,
)


def workspace_out(db: Session, workspace: Workspace) -> WorkspaceOut:
    count = db.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.workspace_id == workspace.id,
            Document.deleted_at.is_(None),
        )
    )
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        owner_id=workspace.owner_id,
        document_count=int(count or 0),
        document_limit=get_settings().max_documents_per_workspace,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def version_out(version: DocumentVersion) -> DocumentVersionOut:
    return DocumentVersionOut(
        id=version.id,
        document_id=version.document_id,
        workspace_id=version.workspace_id,
        file_name=version.file_name,
        file_suffix=version.file_suffix,
        media_type=version.media_type,
        file_hash=version.file_hash,
        file_size=version.file_size,
        version=version.version,
        upload_source=version.upload_source,
        applicable_scope=version.applicable_scope,
        uploaded_by=version.uploaded_by,
        uploaded_at=version.uploaded_at,
        parse_status=version.parse_status,
        parse_error_code=version.parse_error_code,
        parse_error=version.parse_error,
        support_level=version.support_level,
        warnings=version.warnings or [],
        page_count=version.page_count,
        char_count=version.char_count,
        parsed_at=version.parsed_at,
    )


def parse_job_out(job: Optional[ParseJob]) -> Optional[ParseJobOut]:
    if job is None:
        return None
    return ParseJobOut(
        id=job.id,
        status=job.status,
        error_code=job.error_code,
        error_message=job.error_message,
        warnings=job.warnings or [],
        attempt=job.attempt,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


def document_summary(
    db: Session,
    document: Document,
    *,
    include_versions: bool = True,
) -> DocumentSummaryOut:
    versions = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version.desc())
    ).all()

    latest: Optional[DocumentVersion] = None
    if document.latest_version_id:
        latest = next((v for v in versions if v.id == document.latest_version_id), None)
    if latest is None and versions:
        latest = versions[0]

    return DocumentSummaryOut(
        id=document.id,
        name=document.name,
        display_name=document.display_name,
        version_count=document.version_count,
        latest_version=version_out(latest) if latest else None,
        versions=[version_out(v) for v in versions] if include_versions else [],
        deleted_at=document.deleted_at,
        deleted_by=document.deleted_by,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def latest_job(db: Session, version: DocumentVersion) -> Optional[ParseJob]:
    return db.scalars(
        select(ParseJob)
        .where(ParseJob.document_version_id == version.id)
        .order_by(ParseJob.created_at.desc())
    ).first()


def document_detail(
    db: Session,
    workspace: Workspace,
    document: Document,
    version: DocumentVersion,
) -> DocumentDetailOut:
    rows = db.execute(
        select(
            DocumentPage.page_number,
            DocumentPage.char_count,
            DocumentPage.line_count,
            DocumentPage.width,
            DocumentPage.height,
            DocumentPage.is_blank,
            func.count(EvidenceSpan.id),
        )
        .outerjoin(
            EvidenceSpan,
            (EvidenceSpan.document_version_id == DocumentPage.document_version_id)
            & (EvidenceSpan.page == DocumentPage.page_number),
        )
        .where(DocumentPage.document_version_id == version.id)
        .group_by(
            DocumentPage.page_number,
            DocumentPage.char_count,
            DocumentPage.line_count,
            DocumentPage.width,
            DocumentPage.height,
            DocumentPage.is_blank,
        )
        .order_by(DocumentPage.page_number)
    ).all()

    pages = [
        PageSummaryOut(
            page_number=row[0],
            char_count=row[1],
            line_count=row[2],
            width=row[3],
            height=row[4],
            is_blank=bool(row[5]),
            span_count=int(row[6] or 0),
        )
        for row in rows
    ]

    return DocumentDetailOut(
        workspace=workspace_out(db, workspace),
        document=document_summary(db, document, include_versions=True),
        version=version_out(version),
        pages=pages,
        parse_job=parse_job_out(latest_job(db, version)),
    )


def span_out(span: EvidenceSpan) -> EvidenceSpanOut:
    return EvidenceSpanOut(
        id=span.id,
        document_version_id=span.document_version_id,
        page=span.page,
        block_index=span.block_index,
        kind=span.kind,
        text=span.text,
        char_start=span.char_start,
        char_end=span.char_end,
        bboxes=[BBoxOut(**box) for box in (span.bboxes or [])],
        context_before=span.context_before,
        context_after=span.context_after,
        created_at=span.created_at,
    )


def page_content(db: Session, version: DocumentVersion, page_number: int) -> Optional[PageContentOut]:
    page = db.scalars(
        select(DocumentPage).where(
            DocumentPage.document_version_id == version.id,
            DocumentPage.page_number == page_number,
        )
    ).first()
    if page is None:
        return None

    spans = db.scalars(
        select(EvidenceSpan)
        .where(
            EvidenceSpan.document_version_id == version.id,
            EvidenceSpan.page == page_number,
        )
        .order_by(EvidenceSpan.block_index)
    ).all()

    return PageContentOut(
        version_id=version.id,
        page_number=page.page_number,
        text=page.text,
        char_count=page.char_count,
        line_count=page.line_count,
        width=page.width,
        height=page.height,
        is_blank=page.is_blank,
        spans=[span_out(span) for span in spans],
    )


def versions_for_document(db: Session, document_id: str) -> List[DocumentVersion]:
    return list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
        ).all()
    )
