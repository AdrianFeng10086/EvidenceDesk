"""Case 范围、Case 级检索、索引状态与检索日志接口。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database import get_db
from db.models import (
    Case,
    DocumentVersion,
    RetrievalIndex,
    RetrievalLog,
    RetrievalScopeItem,
    Run,
    Workspace,
    new_id,
    utcnow,
)
from schemas.retrieval import (
    CaseCreate,
    CaseDetailOut,
    CaseOut,
    CaseUpdate,
    RetrieveRequest,
    ScopeItemCreate,
)
from services import vector_store
from services.access import (
    Principal,
    get_principal,
    require_case_access,
    require_scope_version_access,
    require_version_access,
    require_workspace_access,
)
from services.cases import (
    build_scope_snapshot,
    case_detail_out,
    case_out,
    load_scope_entries,
    refresh_stale_runs,
    scope_item_out,
)
from services.errors import ForbiddenError, NotFoundError
from services.index_config import get_index_config
from services.indexing import effective_index_status, index_status_reason, run_index_job
from services.retrieval import annotate_log_sources, retrieve_evidence

router = APIRouter()


# ---------------------------------------------------------------------------
# Case CRUD 与范围
# ---------------------------------------------------------------------------


@router.get("/cases", response_model=List[CaseOut], tags=["事项"])
def list_cases(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> List[CaseOut]:
    cases = db.scalars(
        select(Case)
        .where(Case.owner_id == principal.id)
        .order_by(Case.updated_at.desc())
    ).all()
    return [case_out(db, case) for case in cases]


@router.post("/cases", response_model=CaseDetailOut, status_code=201, tags=["事项"])
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> CaseDetailOut:
    if payload.primary_workspace_id:
        require_workspace_access(db, payload.primary_workspace_id, principal)

    # 先全部校验，避免创建出半成品 Case
    validated: List[tuple[ScopeItemCreate, Any, Any, Any]] = []
    seen_versions: set[str] = set()
    for item in payload.scope_items:
        version, document, workspace = require_scope_version_access(
            db, item.workspace_id, item.document_version_id, principal
        )
        if version.id in seen_versions:
            continue
        seen_versions.add(version.id)
        validated.append((item, version, document, workspace))

    case = Case(
        id=new_id("case"),
        owner_id=principal.id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        primary_workspace_id=payload.primary_workspace_id,
    )
    db.add(case)
    db.flush()

    for _item, version, _document, _workspace in validated:
        db.add(
            RetrievalScopeItem(
                case_id=case.id,
                workspace_id=version.workspace_id,
                document_version_id=version.id,
            )
        )
    db.flush()
    db.commit()
    db.refresh(case)
    return case_detail_out(
        db, case, principal_id=principal.id, entries=load_scope_entries(db, case.id)
    )


@router.get("/cases/{case_id}", response_model=CaseDetailOut, tags=["事项"])
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> CaseDetailOut:
    case = require_case_access(db, case_id, principal)
    return case_detail_out(db, case, principal_id=principal.id)


@router.patch("/cases/{case_id}", response_model=CaseDetailOut, tags=["事项"])
def update_case(
    case_id: str,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> CaseDetailOut:
    case = require_case_access(db, case_id, principal)
    if payload.title is not None:
        case.title = payload.title.strip()
    if payload.description is not None:
        case.description = payload.description.strip() or None
    case.updated_at = utcnow()
    db.commit()
    db.refresh(case)
    return case_detail_out(db, case, principal_id=principal.id)


@router.get("/cases/{case_id}/scope", tags=["事项"])
def get_case_scope(
    case_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    case = require_case_access(db, case_id, principal)
    entries = load_scope_entries(db, case.id, principal_id=principal.id)
    return {
        "case_id": case.id,
        "scope_hash": build_scope_snapshot(
            case, entries, principal_id=principal.id
        )["scope_hash"],
        "items": [scope_item_out(entry).model_dump() for entry in entries],
    }


def _attach_scope_item(
    db: Session,
    case: Case,
    item: ScopeItemCreate,
    principal: Principal,
) -> tuple[RetrievalScopeItem, bool]:
    version, _document, _workspace = require_scope_version_access(
        db, item.workspace_id, item.document_version_id, principal
    )
    existing = db.scalars(
        select(RetrievalScopeItem).where(
            RetrievalScopeItem.case_id == case.id,
            RetrievalScopeItem.document_version_id == version.id,
        )
    ).first()
    if existing is not None:
        return existing, False

    scope_item = RetrievalScopeItem(
        case_id=case.id,
        workspace_id=version.workspace_id,
        document_version_id=version.id,
    )
    db.add(scope_item)
    db.flush()
    return scope_item, True


@router.post("/cases/{case_id}/scope", tags=["事项"])
def add_case_scope_item(
    case_id: str,
    payload: ScopeItemCreate,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    case = require_case_access(db, case_id, principal)
    _scope_item, created = _attach_scope_item(db, case, payload, principal)
    if created:
        case.updated_at = utcnow()
        refresh_stale_runs(db, case.id)
        db.commit()
        response.status_code = 201
    else:
        db.commit()
    return case_detail_out(db, case, principal_id=principal.id).model_dump()


@router.post("/cases/{case_id}/scope/batch", tags=["事项"])
def add_case_scope_items(
    case_id: str,
    payload: List[ScopeItemCreate],
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    case = require_case_access(db, case_id, principal)
    # 先校验全部，再写入，保持批量操作原子性
    for item in payload:
        require_scope_version_access(
            db, item.workspace_id, item.document_version_id, principal
        )

    created = 0
    for item in payload:
        _scope_item, is_new = _attach_scope_item(db, case, item, principal)
        created += 1 if is_new else 0

    if created:
        case.updated_at = utcnow()
        refresh_stale_runs(db, case.id)
    db.commit()
    body = case_detail_out(db, case, principal_id=principal.id).model_dump()
    body["created_count"] = created
    return body


@router.delete("/cases/{case_id}/scope/{scope_item_id}", tags=["事项"])
def remove_case_scope_item(
    case_id: str,
    scope_item_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    case = require_case_access(db, case_id, principal)
    scope_item = db.scalars(
        select(RetrievalScopeItem).where(
            RetrievalScopeItem.id == scope_item_id,
            RetrievalScopeItem.case_id == case.id,
        )
    ).first()
    if scope_item is None:
        raise NotFoundError(
            "范围项不存在", details={"scope_item_id": scope_item_id}
        )
    db.delete(scope_item)
    db.flush()
    case.updated_at = utcnow()
    refresh_stale_runs(db, case.id)
    db.commit()
    return case_detail_out(db, case, principal_id=principal.id).model_dump()


# ---------------------------------------------------------------------------
# 检索、索引状态与日志
# ---------------------------------------------------------------------------


@router.post("/cases/{case_id}/retrieve", tags=["检索"])
def retrieve_case_evidence(
    case_id: str,
    payload: RetrieveRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    """Case 级检索入口：范围固定、跨空间、向量 + BM25 融合。"""
    return retrieve_evidence(
        db,
        case_id=case_id,
        principal=principal,
        query=payload.query,
        filters=payload.filters,
        top_k=payload.top_k,
        record_run=payload.record_run,
    )


def _manifest_payload(db: Session, config) -> Optional[Dict[str, Any]]:
    manifest = db.scalars(
        select(RetrievalIndex).where(
            RetrievalIndex.index_version == config.index_version
        )
    ).first()
    if manifest is None:
        return None
    return {
        "index_version": manifest.index_version,
        "status": manifest.status,
        "chunk_count": manifest.chunk_count,
        "version_count": manifest.version_count,
        "created_at": manifest.created_at.isoformat() + "Z",
        "updated_at": manifest.updated_at.isoformat() + "Z",
        "config": manifest.config,
    }


@router.get("/cases/{case_id}/retrieval/index-status", tags=["检索"])
def case_index_status(
    case_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    case = require_case_access(db, case_id, principal)
    config = get_index_config()
    entries = load_scope_entries(db, case.id, principal_id=principal.id)
    snapshot = build_scope_snapshot(case, entries, principal_id=principal.id)

    status_counts: Dict[str, int] = {}
    items: List[Dict[str, Any]] = []
    active_sources = 0
    ready_sources = 0
    for entry in entries:
        version = entry.version
        effective = (
            effective_index_status(version, config) if version is not None else "pending"
        )
        status_counts[effective] = status_counts.get(effective, 0) + 1
        if entry.source_state == "active":
            active_sources += 1
            if version is not None and version.parse_status == "success" and effective == "ready":
                ready_sources += 1
        items.append(
            {
                "scope_item_id": entry.item.id,
                "workspace_id": entry.item.workspace_id,
                "workspace_name": entry.workspace.name if entry.workspace else None,
                "document_version_id": entry.item.document_version_id,
                "document_name": (
                    entry.document.display_name if entry.document else None
                ) or (version.file_name if version else None),
                "source_state": entry.source_state,
                "parse_status": version.parse_status if version else None,
                "index_status": effective,
                "index_reason": index_status_reason(effective),
                "index_error_code": version.index_error_code if version else None,
                "index_error": version.index_error if version else None,
                "index_version": version.index_version if version else None,
                "embedding_model": version.embedding_model if version else None,
                "chunk_count": version.chunk_count if version else None,
                "indexed_at": (
                    version.indexed_at.isoformat() + "Z"
                    if version and version.indexed_at
                    else None
                ),
            }
        )

    collection_count: Optional[int] = None
    vector_error: Optional[str] = None
    try:
        collection_count = vector_store.count(config.index_version)
    except Exception as exc:  # noqa: BLE001
        vector_error = str(exc)

    return {
        "case_id": case.id,
        "scope_hash": snapshot["scope_hash"],
        "scope_counts": snapshot["counts"],
        "config": config.to_dict(),
        "manifest": _manifest_payload(db, config),
        "collection": vector_store.collection_name(config.index_version),
        "collection_count": collection_count,
        "vector_store_error": vector_error,
        "status_counts": status_counts,
        "active_sources": active_sources,
        "ready_sources": ready_sources,
        "ready_for_retrieval": active_sources > 0 and ready_sources == active_sources,
        "items": items,
    }


@router.get("/cases/{case_id}/retrieval/logs", tags=["检索"])
def list_retrieval_logs(
    case_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    case = require_case_access(db, case_id, principal)
    total = db.scalar(
        select(func.count())
        .select_from(RetrievalLog)
        .where(RetrievalLog.case_id == case.id)
    )
    logs = db.scalars(
        select(RetrievalLog)
        .where(RetrievalLog.case_id == case.id)
        .order_by(RetrievalLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "case_id": case.id,
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "logs": [_log_payload(db, log) for log in logs],
    }


@router.get("/retrieval/logs/{log_id}", tags=["检索"])
def get_retrieval_log(
    log_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    log = db.get(RetrievalLog, log_id)
    if log is None:
        raise NotFoundError("检索日志不存在", details={"log_id": log_id})
    if log.owner_id != principal.id:
        raise ForbiddenError(
            "当前访问主体不是该检索日志的所有者",
            code="LOG_FORBIDDEN",
            details={"log_id": log_id},
        )
    return _log_payload(db, log)


def _log_payload(db: Session, log: RetrievalLog) -> Dict[str, Any]:
    results = annotate_log_sources(db, log.results or [])
    deleted_results = sum(
        1 for result in results if not result.get("source_available", True)
    )
    return {
        "id": log.id,
        "case_id": log.case_id,
        "run_id": log.run_id,
        "owner_id": log.owner_id,
        "query": log.query,
        "filters": log.filters,
        "scope_snapshot": log.scope_snapshot,
        "scope_hash": log.scope_hash,
        "status": log.status,
        "empty_reason": log.empty_reason,
        "note": log.note,
        "result_count": log.result_count,
        "counts": log.counts,
        "diagnostics": log.diagnostics,
        "config_snapshot": log.config_snapshot,
        "index_version": log.index_version,
        "latency_ms": log.latency_ms,
        "error_code": log.error_code,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() + "Z",
        "results": results,
        "unavailable_result_count": deleted_results,
        "historical_notice": (
            "部分历史结果来源已删除或不可用"
            if deleted_results
            else None
        ),
    }


@router.get("/cases/{case_id}/runs", tags=["检索"])
def list_case_runs(
    case_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    case = require_case_access(db, case_id, principal)
    runs = db.scalars(
        select(Run)
        .where(Run.case_id == case.id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "case_id": case.id,
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "stale": run.status == "stale",
                "stale_reason": run.stale_reason,
                "stale_at": (
                    run.stale_at.isoformat() + "Z" if run.stale_at else None
                ),
                "query": run.query,
                "scope_hash": run.scope_hash,
                "index_version": run.index_version,
                "retrieval_log_id": run.retrieval_log_id,
                "created_at": run.created_at.isoformat() + "Z",
                "finished_at": (
                    run.finished_at.isoformat() + "Z" if run.finished_at else None
                ),
            }
            for run in runs
        ],
    }


# ---------------------------------------------------------------------------
# 索引维护
# ---------------------------------------------------------------------------


@router.get("/index/status", tags=["检索"])
def global_index_status(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    config = get_index_config()
    versions = db.scalars(
        select(DocumentVersion)
        .join(Workspace, Workspace.id == DocumentVersion.workspace_id)
        .where(Workspace.owner_id == principal.id, Workspace.deleted_at.is_(None))
    ).all()

    status_counts: Dict[str, int] = {}
    for version in versions:
        effective = effective_index_status(version, config)
        status_counts[effective] = status_counts.get(effective, 0) + 1

    collection_count: Optional[int] = None
    vector_error: Optional[str] = None
    try:
        collection_count = vector_store.count(config.index_version)
    except Exception as exc:  # noqa: BLE001
        vector_error = str(exc)

    return {
        "config": config.to_dict(),
        "manifest": _manifest_payload(db, config),
        "collection": vector_store.collection_name(config.index_version),
        "collection_count": collection_count,
        "vector_store_error": vector_error,
        "version_count": len(versions),
        "status_counts": status_counts,
        "ready": status_counts.get("ready", 0) == len(versions) and bool(versions),
    }


@router.post("/documents/{version_id}/index/rebuild", status_code=202, tags=["检索"])
def rebuild_version_index(
    version_id: str,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    version, _document, _workspace = require_version_access(db, version_id, principal)
    background_tasks.add_task(run_index_job, version.id)
    response.status_code = 202
    return {
        "version_id": version.id,
        "status": "queued",
        "index_status": effective_index_status(version),
    }


@router.post("/index/rebuild", status_code=202, tags=["检索"])
def rebuild_owner_index(
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Dict[str, Any]:
    versions = db.scalars(
        select(DocumentVersion)
        .join(Workspace, Workspace.id == DocumentVersion.workspace_id)
        .where(
            Workspace.owner_id == principal.id,
            Workspace.deleted_at.is_(None),
            DocumentVersion.parse_status == "success",
        )
    ).all()
    for version in versions:
        background_tasks.add_task(run_index_job, version.id)
    response.status_code = 202
    return {"queued": len(versions), "version_ids": [version.id for version in versions]}
