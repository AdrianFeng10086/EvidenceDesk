"""文档上传、版本、解析状态与原文读取接口。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api.serializers import (
    document_detail,
    document_summary,
    latest_job,
    page_content,
    parse_job_out,
    version_out,
    workspace_out,
)
from core.config import get_settings
from core.database import get_db
from db.models import (
    Case,
    Document,
    DocumentPage,
    DocumentVersion,
    EvidenceSpan,
    ParseJob,
    RetrievalScopeItem,
    Run,
    SourceTombstone,
    new_id,
    utcnow,
)
from schemas.document import (
    DocumentDeleteImpactOut,
    DocumentDetailOut,
    DocumentListOut,
    DocumentSummaryOut,
    EvidenceSearchOut,
    EvidenceSpanRefOut,
    PageContentOut,
    RetryParseResponseOut,
    UploadResponseOut,
)
from services.access import (
    Principal,
    get_principal,
    require_version_access,
    require_workspace_access,
)
from services.errors import ConflictError, NotFoundError
from services.evidence_search import search_workspace_evidence
from services.indexing import (
    remove_version_index,
    reset_version_index,
    run_index_job,
)
from services.parser import run_parse_job
from services.storage import (
    assert_managed_path,
    finalize_upload,
    normalize_name,
    original_file_exists,
    remove_staged,
    sanitize_filename,
    stage_upload,
    validate_suffix,
)

router = APIRouter()


@router.get(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentListOut,
    tags=["文档"],
)
def list_documents(
    workspace_id: str,
    include_deleted: bool = Query(False, description="是否包含已软删除的文档"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentListOut:
    workspace = require_workspace_access(db, workspace_id, principal)
    query = select(Document).where(Document.workspace_id == workspace.id)
    if not include_deleted:
        query = query.where(Document.deleted_at.is_(None))
    documents = db.scalars(query.order_by(Document.updated_at.desc())).all()
    return DocumentListOut(
        workspace=workspace_out(db, workspace),
        documents=[document_summary(db, doc) for doc in documents],
    )


@router.get(
    "/workspaces/{workspace_id}/evidence/search",
    response_model=EvidenceSearchOut,
    tags=["证据"],
)
def search_evidence(
    workspace_id: str,
    q: str = Query(..., min_length=1, max_length=200, description="检索问题或关键词"),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> EvidenceSearchOut:
    """返回资料空间内真实存在的 EvidenceSpan，供证据卡定位使用。"""
    workspace = require_workspace_access(db, workspace_id, principal)
    spans = search_workspace_evidence(db, workspace.id, q, limit=limit)
    return EvidenceSearchOut(
        query=q,
        is_sample=False,
        note=None if spans else "资料空间中没有匹配的已解析证据片段",
        evidence_spans=[EvidenceSpanRefOut(**span) for span in spans],
    )


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=UploadResponseOut,
    status_code=201,
    tags=["文档"],
)
async def upload_document(
    workspace_id: str,
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF（带文字层）、TXT 或 Markdown"),
    upload_source: Optional[str] = Form(None),
    applicable_scope: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> UploadResponseOut:
    settings = get_settings()
    workspace = require_workspace_access(db, workspace_id, principal)

    file_name = sanitize_filename(file.filename)
    suffix = validate_suffix(file_name)
    normalized = normalize_name(file_name)

    document = db.scalars(
        select(Document).where(
            Document.workspace_id == workspace.id,
            Document.normalized_name == normalized,
        )
    ).first()

    if document is None or document.deleted_at is not None:
        _assert_document_capacity(db, workspace.id, settings.max_documents_per_workspace)

    staging_dir = settings.upload_dir / ".staging" / uuid.uuid4().hex
    saved = await stage_upload(
        file,
        staging_root=staging_dir,
        file_name=file_name,
        suffix=suffix,
    )
    committed = False

    try:
        duplicate = db.scalars(
            select(DocumentVersion).where(
                DocumentVersion.workspace_id == workspace.id,
                DocumentVersion.file_hash == saved.sha256,
            )
        ).first()

        if duplicate is not None:
            duplicate_document = db.get(Document, duplicate.document_id)
            if duplicate_document is None:  # pragma: no cover — 数据一致性兜底
                raise NotFoundError("重复文件对应的文档不存在")
            if duplicate_document.deleted_at is not None:
                _assert_document_capacity(
                    db, workspace.id, settings.max_documents_per_workspace
                )
                # 已删除文档的原始文件可能已被清理；上传的同一份文件可以补回该版本文件
                if not original_file_exists(duplicate.file_path):
                    saved = finalize_upload(
                        saved,
                        workspace_id=duplicate.workspace_id,
                        document_id=duplicate.document_id,
                        version_id=duplicate.id,
                    )
                    if Path(saved.path).resolve() != Path(duplicate.file_path).resolve():
                        raise ConflictError(
                            "原始文件位置已变化，无法恢复该版本",
                            code="ORIGINAL_FILE_MISSING",
                        )
                else:
                    remove_staged(saved)
                _restore_document(db, duplicate_document)
                restore_versions = list(
                    db.scalars(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == duplicate_document.id
                        )
                    ).all()
                )
                for restore_version in restore_versions:
                    restore_version.index_status = "pending"
                    restore_version.index_error_code = None
                    restore_version.index_error = None
                db.commit()
                committed = True
                for restore_version in restore_versions:
                    background_tasks.add_task(run_index_job, restore_version.id)
            else:
                remove_staged(saved)
            response.status_code = 200
            return UploadResponseOut(
                duplicate=True,
                document=document_summary(db, duplicate_document),
                version=version_out(duplicate),
                parse_job=parse_job_out(latest_job(db, duplicate))
                or _queued_job_stub(duplicate, duplicate.parse_status),
            )

        if document is None:
            document = Document(
                workspace_id=workspace.id,
                name=file_name,
                normalized_name=normalized,
                display_name=file_name,
                version_count=0,
            )
            db.add(document)
            db.flush()
        elif document.deleted_at is not None:
            # 同名文档曾被软删除：重新上传时恢复该文档，避免命中旧的唯一约束
            _restore_document(db, document)

        next_version = document.version_count + 1
        version_id = new_id("ver")

        # 内容和存储路径在 INSERT 前确定；版本入库后这些字段不再允许修改
        saved = finalize_upload(
            saved,
            workspace_id=workspace.id,
            document_id=document.id,
            version_id=version_id,
        )

        version = DocumentVersion(
            id=version_id,
            document_id=document.id,
            workspace_id=workspace.id,
            file_name=file_name,
            file_suffix=suffix,
            media_type=saved.media_type,
            file_hash=saved.sha256,
            file_size=saved.size,
            file_path=str(saved.path),
            version=next_version,
            upload_source=(upload_source or "").strip() or None,
            applicable_scope=(applicable_scope or "").strip() or None,
            uploaded_by=principal.id,
            parse_status="uploaded",
            support_level="pending",
            warnings=[],
        )
        db.add(version)
        db.flush()

        document.version_count = next_version
        document.latest_version_id = version.id
        document.display_name = file_name
        document.updated_at = utcnow()

        job = ParseJob(
            document_version_id=version.id,
            status="queued",
            attempt=1,
        )
        db.add(job)
        db.commit()
        committed = True
        db.refresh(version)
        db.refresh(document)
        db.refresh(job)

        background_tasks.add_task(run_parse_job, version.id)
        response.status_code = 201

        return UploadResponseOut(
            duplicate=False,
            document=document_summary(db, document),
            version=version_out(version),
            parse_job=parse_job_out(job),
        )
    except Exception:
        db.rollback()
        if not committed:
            remove_staged(saved)
        raise


def _queued_job_stub(version: DocumentVersion, status: str):
    """重复文件没有新建解析任务时的占位响应。"""
    from schemas.document import ParseJobOut

    return ParseJobOut(
        id=f"duplicate_{version.id}",
        status=status,
        warnings=[],
        attempt=0,
        created_at=version.uploaded_at,
    )


def _assert_document_capacity(db: Session, workspace_id: str, limit: int) -> None:
    """新上传或恢复文档都会占用一个活跃文档名额。"""
    active_count = db.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
    )
    if int(active_count or 0) >= limit:
        raise ConflictError(
            f"资料空间最多允许 {limit} 个文档",
            code="WORKSPACE_DOCUMENT_LIMIT",
            details={"limit": limit},
        )


def _restore_document(db: Session, document: Document) -> None:
    """恢复软删除文档，并移除它的来源墓碑。"""
    document.deleted_at = None
    document.deleted_by = None
    document.updated_at = utcnow()
    db.execute(
        delete(SourceTombstone).where(SourceTombstone.document_id == document.id)
    )


def _get_workspace_document(
    db: Session,
    workspace_id: str,
    document_id: str,
    principal: Principal,
) -> tuple[Document, list[DocumentVersion]]:
    workspace = require_workspace_access(db, workspace_id, principal)
    document = db.get(Document, document_id)
    if document is None or document.workspace_id != workspace.id:
        raise NotFoundError(
            "文档不存在",
            details={"document_id": document_id},
        )
    versions = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version.desc())
        ).all()
    )
    return document, versions


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}/delete-impact",
    response_model=DocumentDeleteImpactOut,
    tags=["文档"],
)
def get_document_delete_impact(
    workspace_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentDeleteImpactOut:
    """删除前展示影响：版本、页面、证据片段、引用该文档的 Case 和最近 Run。"""
    document, versions = _get_workspace_document(
        db, workspace_id, document_id, principal
    )
    version_ids = [version.id for version in versions]

    page_count = 0
    span_count = 0
    cases: list[Any] = []
    runs: list[Any] = []
    if version_ids:
        page_count = int(
            db.scalar(
                select(func.count())
                .select_from(DocumentPage)
                .where(DocumentPage.document_version_id.in_(version_ids))
            )
            or 0
        )
        span_count = int(
            db.scalar(
                select(func.count())
                .select_from(EvidenceSpan)
                .where(EvidenceSpan.document_version_id.in_(version_ids))
            )
            or 0
        )
        cases = db.execute(
            select(Case.id, Case.title)
            .join(RetrievalScopeItem, RetrievalScopeItem.case_id == Case.id)
            .where(
                RetrievalScopeItem.document_version_id.in_(version_ids),
                Case.owner_id == principal.id,
            )
            .distinct()
            .order_by(Case.updated_at.desc())
        ).all()
        runs = db.execute(
            select(Run.id, Run.case_id, Run.status, Run.created_at)
            .join(Case, Case.id == Run.case_id)
            .join(RetrievalScopeItem, RetrievalScopeItem.case_id == Run.case_id)
            .where(
                RetrievalScopeItem.document_version_id.in_(version_ids),
                Case.owner_id == principal.id,
            )
            .distinct()
            .order_by(Run.created_at.desc())
            .limit(5)
        ).all()

    from schemas.document import CaseRefOut, RunRefOut

    return DocumentDeleteImpactOut(
        document=document_summary(db, document),
        version_count=len(versions),
        page_count=page_count,
        span_count=span_count,
        referencing_cases=[
            CaseRefOut(id=row[0], title=row[1]) for row in cases
        ],
        recent_runs=[
            RunRefOut(
                id=row[0],
                case_id=row[1],
                status=row[2],
                created_at=row[3],
            )
            for row in runs
        ],
    )


@router.delete(
    "/workspaces/{workspace_id}/documents/{document_id}",
    response_model=DocumentSummaryOut,
    tags=["文档"],
)
def delete_document(
    workspace_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentSummaryOut:
    """软删除文档；文件与解析产物保留，供保留期内恢复。"""
    document, versions = _get_workspace_document(
        db, workspace_id, document_id, principal
    )
    if document.deleted_at is not None:
        raise ConflictError("文档已删除", code="DOCUMENT_ALREADY_DELETED")

    document.deleted_at = utcnow()
    document.deleted_by = principal.id
    document.updated_at = utcnow()

    for version in versions:
        # 删除后立即从向量索引与候选块中移除；历史日志由 Tombstone 标注
        remove_version_index(db, version, commit=False)
        existing = db.scalars(
            select(SourceTombstone).where(
                SourceTombstone.document_version_id == version.id
            )
        ).first()
        if existing is None:
            db.add(
                SourceTombstone(
                    workspace_id=version.workspace_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    display_name=document.display_name,
                    file_name=version.file_name,
                    file_hash=version.file_hash,
                    version=version.version,
                    deleted_by=principal.id,
                    reason="document_deleted",
                )
            )

    db.commit()
    db.refresh(document)
    return document_summary(db, document)


@router.post(
    "/workspaces/{workspace_id}/documents/{document_id}/restore",
    response_model=DocumentSummaryOut,
    tags=["文档"],
)
def restore_document(
    workspace_id: str,
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentSummaryOut:
    """恢复保留期内的软删除文档。"""
    document, versions = _get_workspace_document(
        db, workspace_id, document_id, principal
    )
    if document.deleted_at is None:
        raise ConflictError("文档未删除，无需恢复", code="DOCUMENT_NOT_DELETED")

    latest = next(
        (version for version in versions if version.id == document.latest_version_id),
        versions[0] if versions else None,
    )
    if latest is None:
        raise ConflictError("文档没有可恢复的版本", code="DOCUMENT_EMPTY")
    if not original_file_exists(latest.file_path):
        raise ConflictError(
            "原始文件已丢失，无法恢复该文档",
            code="ORIGINAL_FILE_MISSING",
        )

    _restore_document(db, document)
    for version in versions:
        reset_version_index(db, version, commit=False)
    db.commit()
    db.refresh(document)
    for version in versions:
        background_tasks.add_task(run_index_job, version.id)
    return document_summary(db, document)


@router.get("/documents/{version_id}", response_model=DocumentDetailOut, tags=["文档"])
def get_document(
    version_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentDetailOut:
    version, document, workspace = require_version_access(db, version_id, principal)
    return document_detail(db, workspace, document, version)


@router.get("/documents/{version_id}/status", tags=["文档"])
def get_parse_status(
    version_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    version, document, _workspace = require_version_access(db, version_id, principal)
    job = latest_job(db, version)
    return {
        "version": version_out(version),
        "parse_job": parse_job_out(job),
    }


@router.get(
    "/documents/{version_id}/content",
    response_model=PageContentOut,
    tags=["文档"],
)
def get_page_content(
    version_id: str,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> PageContentOut:
    version, _document, _workspace = require_version_access(db, version_id, principal)

    if version.parse_status != "success":
        raise ConflictError(
            "文档尚未解析成功，暂无原文可读取",
            code="PARSE_NOT_READY",
            details={
                "parse_status": version.parse_status,
                "parse_error_code": version.parse_error_code,
            },
        )

    content = page_content(db, version, page)
    if content is None:
        raise NotFoundError(
            "该页不存在",
            code="PAGE_NOT_FOUND",
            details={"page": page, "page_count": version.page_count},
        )
    return content


@router.get("/documents/{version_id}/original", tags=["文档"])
def download_original(
    version_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    version, _document, _workspace = require_version_access(db, version_id, principal)
    path = Path(version.file_path)
    if not path.exists():
        raise NotFoundError("原始文件已丢失", code="ORIGINAL_FILE_MISSING")
    safe_path = assert_managed_path(path)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{_quote_filename(version.file_name)}",
        "X-Content-SHA256": version.file_hash,
    }
    return FileResponse(
        safe_path,
        media_type=version.media_type,
        headers=headers,
    )


def _quote_filename(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")


@router.post(
    "/documents/{version_id}/parse/retry",
    response_model=RetryParseResponseOut,
    status_code=202,
    tags=["文档"],
)
def retry_parse(
    version_id: str,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> RetryParseResponseOut:
    version, _document, _workspace = require_version_access(db, version_id, principal)

    if version.parse_status in {"parsing", "indexing"}:
        raise ConflictError("解析正在进行中", code="PARSE_IN_PROGRESS")
    if version.parse_status == "success":
        raise ConflictError("该版本已解析成功，无需重试", code="PARSE_ALREADY_SUCCESS")

    previous = latest_job(db, version)
    attempt = (previous.attempt + 1) if previous else 1

    reset_version_index(db, version, commit=False)
    version.parse_status = "uploaded"
    version.support_level = "pending"
    version.parse_error_code = None
    version.parse_error = None
    version.warnings = []
    version.page_count = None
    version.char_count = None
    version.parsed_at = None

    job = ParseJob(
        document_version_id=version.id,
        status="queued",
        attempt=attempt,
    )
    db.add(job)
    db.commit()
    db.refresh(version)
    db.refresh(job)

    background_tasks.add_task(run_parse_job, version.id)
    response.status_code = 202
    return RetryParseResponseOut(
        version=version_out(version),
        parse_job=parse_job_out(job),
    )
