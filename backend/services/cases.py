"""Case 范围快照、来源状态与 Run 过期标记。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import (
    Case,
    Document,
    DocumentVersion,
    RetrievalScopeItem,
    Run,
    Workspace,
    utcnow,
)
from schemas.retrieval import CaseDetailOut, CaseOut, ScopeItemOut
from services.index_config import get_index_config
from services.indexing import effective_index_status, index_status_reason


@dataclass
class ScopeEntry:
    item: RetrievalScopeItem
    version: Optional[DocumentVersion]
    document: Optional[Document]
    workspace: Optional[Workspace]
    source_state: str


def load_scope_entries(
    db: Session, case_id: str, *, principal_id: Optional[str] = None
) -> List[ScopeEntry]:
    rows = db.execute(
        select(RetrievalScopeItem, DocumentVersion, Document, Workspace)
        .outerjoin(
            DocumentVersion,
            DocumentVersion.id == RetrievalScopeItem.document_version_id,
        )
        .outerjoin(Document, Document.id == DocumentVersion.document_id)
        .outerjoin(Workspace, Workspace.id == RetrievalScopeItem.workspace_id)
        .where(RetrievalScopeItem.case_id == case_id)
        .order_by(RetrievalScopeItem.created_at, RetrievalScopeItem.id)
    ).all()

    entries: List[ScopeEntry] = []
    for item, version, document, workspace in rows:
        entries.append(
            ScopeEntry(
                item=item,
                version=version,
                document=document,
                workspace=workspace,
                source_state=_source_state(
                    item=item,
                    version=version,
                    document=document,
                    workspace=workspace,
                    principal_id=principal_id,
                ),
            )
        )
    return entries


def _source_state(
    *,
    item: RetrievalScopeItem,
    version: Optional[DocumentVersion],
    document: Optional[Document],
    workspace: Optional[Workspace],
    principal_id: Optional[str],
) -> str:
    if workspace is None:
        return "workspace_missing"
    if principal_id is not None and workspace.owner_id != principal_id:
        return "unauthorized"
    if workspace.deleted_at is not None:
        return "workspace_deleted"
    if version is None:
        return "version_missing"
    if document is None:
        return "document_missing"
    if document.deleted_at is not None:
        return "document_deleted"
    return "active"


def compute_scope_hash(entries: Sequence[ScopeEntry]) -> str:
    """范围指纹只由固定的 (workspace, version) 对决定。"""
    pairs = sorted(
        f"{entry.item.workspace_id}:{entry.item.document_version_id}"
        for entry in entries
    )
    return hashlib.sha256("|".join(pairs).encode("utf-8")).hexdigest()


def scope_hash_for_case(db: Session, case_id: str) -> str:
    return compute_scope_hash(load_scope_entries(db, case_id))


def build_scope_snapshot(
    case: Case,
    entries: Sequence[ScopeEntry],
    *,
    principal_id: str,
) -> Dict[str, object]:
    config = get_index_config()
    items: List[Dict[str, object]] = []
    state_counts: Dict[str, int] = {}
    for entry in entries:
        state = entry.source_state
        state_counts[state] = state_counts.get(state, 0) + 1
        version = entry.version
        effective = (
            effective_index_status(version, config) if version is not None else None
        )
        items.append(
            {
                "scope_item_id": entry.item.id,
                "workspace_id": entry.item.workspace_id,
                "workspace_name": entry.workspace.name if entry.workspace else None,
                "document_id": version.document_id if version else None,
                "document_version_id": entry.item.document_version_id,
                "document_name": (
                    (entry.document.display_name if entry.document else None)
                    or (version.file_name if version else None)
                ),
                "file_name": version.file_name if version else None,
                "file_suffix": version.file_suffix if version else None,
                "file_version": version.version if version else None,
                "applicable_scope": version.applicable_scope if version else None,
                "upload_source": version.upload_source if version else None,
                "source_state": state,
                "source_available": state == "active",
                "parse_status": version.parse_status if version else None,
                "index_status": effective,
                "index_reason": index_status_reason(effective or ""),
                "chunk_count": version.chunk_count if version else None,
            }
        )

    return {
        "case_id": case.id,
        "case_title": case.title,
        "owner_id": case.owner_id,
        "captured_at": utcnow().isoformat() + "Z",
        "scope_hash": compute_scope_hash(entries),
        "index_version": config.index_version,
        "items": items,
        "state_counts": state_counts,
        "counts": {
            "scope_items": len(items),
            "active_sources": state_counts.get("active", 0),
            "deleted_sources": state_counts.get("document_deleted", 0)
            + state_counts.get("workspace_deleted", 0),
            "unavailable_sources": state_counts.get("version_missing", 0)
            + state_counts.get("document_missing", 0)
            + state_counts.get("workspace_missing", 0),
            "unauthorized_sources": state_counts.get("unauthorized", 0),
        },
    }


def refresh_stale_runs(db: Session, case_id: str) -> int:
    """Case 范围变化后，把基于旧范围的 Run 标记为过期。"""
    entries = load_scope_entries(db, case_id)
    new_hash = compute_scope_hash(entries)
    runs = db.scalars(
        select(Run).where(
            Run.case_id == case_id,
            Run.status != "stale",
            or_(Run.scope_hash.is_(None), Run.scope_hash != new_hash),
        )
    ).all()
    changed = 0
    now = utcnow()
    for run in runs:
        run.status = "stale"
        run.stale_reason = "scope_changed"
        run.stale_at = now
        changed += 1
    return changed


def _entry_index_status(
    entry: ScopeEntry,
) -> Optional[str]:
    if entry.version is None:
        return None
    return effective_index_status(entry.version)


def scope_item_out(entry: ScopeEntry) -> ScopeItemOut:
    version = entry.version
    document = entry.document
    workspace = entry.workspace
    return ScopeItemOut(
        id=entry.item.id,
        workspace_id=entry.item.workspace_id,
        workspace_name=workspace.name if workspace else None,
        document_id=version.document_id if version else None,
        document_version_id=entry.item.document_version_id,
        document_name=(
            (document.display_name if document else None)
            or (version.file_name if version else None)
        ),
        file_name=version.file_name if version else None,
        file_suffix=version.file_suffix if version else None,
        file_version=version.version if version else None,
        applicable_scope=version.applicable_scope if version else None,
        source_state=entry.source_state,
        parse_status=version.parse_status if version else None,
        index_status=_entry_index_status(entry),
        chunk_count=version.chunk_count if version else None,
        created_at=entry.item.created_at.isoformat() + "Z" if entry.item.created_at else None,
    )


def case_out(db: Session, case: Case, entries: Optional[Sequence[ScopeEntry]] = None) -> CaseOut:
    entries = list(entries if entries is not None else load_scope_entries(db, case.id))
    return CaseOut(
        id=case.id,
        owner_id=case.owner_id,
        title=case.title,
        description=case.description,
        primary_workspace_id=case.primary_workspace_id,
        scope_item_count=len(entries),
        scope_hash=compute_scope_hash(entries),
        created_at=case.created_at.isoformat() + "Z",
        updated_at=case.updated_at.isoformat() + "Z",
    )


def case_detail_out(
    db: Session,
    case: Case,
    *,
    principal_id: str,
    entries: Optional[Sequence[ScopeEntry]] = None,
) -> CaseDetailOut:
    entries = list(entries if entries is not None else load_scope_entries(db, case.id))
    base = case_out(db, case, entries)
    return CaseDetailOut(
        **base.model_dump(),
        scope_items=[scope_item_out(entry) for entry in entries],
        scope_snapshot=build_scope_snapshot(case, entries, principal_id=principal_id),
    )
