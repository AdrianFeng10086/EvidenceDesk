"""访问主体与资料空间所有权校验。

首版只有演示账户，但所有读写入口都必须经过这里：
- 请求头 X-Demo-User 指定访问主体（缺省为 DEMO_USER_ID）
- 资料空间创建时写入 owner_id
- 任何文档/证据访问都先解析到 Workspace，再比对 owner_id

这样后续接入真实登录时，只需替换 get_principal，而无需改动业务路由。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from core.config import get_settings
from db.models import Document, DocumentVersion, Workspace
from services.errors import ForbiddenError, NotFoundError


@dataclass(frozen=True)
class Principal:
    id: str
    display_name: str
    is_demo: bool


def get_principal(request: Request) -> Principal:
    settings = get_settings()
    raw = request.headers.get("X-Demo-User", "").strip()
    user_id = raw or settings.demo_user_id
    return Principal(
        id=user_id,
        display_name="演示账户" if user_id == settings.demo_user_id else user_id,
        is_demo=user_id == settings.demo_user_id,
    )


def _ensure_owner(workspace: Workspace, principal: Principal) -> Workspace:
    if workspace.owner_id != principal.id:
        # 不暴露其他空间是否存在
        raise ForbiddenError(
            "当前访问主体不是该资料空间的所有者",
            code="WORKSPACE_FORBIDDEN",
            details={"workspace_id": workspace.id},
        )
    return workspace


def require_workspace_access(
    db: Session, workspace_id: str, principal: Principal
) -> Workspace:
    settings = get_settings()
    workspace = db.get(Workspace, workspace_id)

    # 演示模式下允许演示账户自动创建配置中的演示空间（通常启动时已创建）
    if (
        workspace is None
        and settings.demo_mode
        and principal.id == settings.demo_user_id
        and workspace_id == settings.demo_workspace_id
    ):
        workspace = Workspace(
            id=workspace_id,
            name=settings.demo_workspace_name,
            description="演示资料空间",
            owner_id=principal.id,
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "资料空间不存在或已删除",
            code="WORKSPACE_DELETED" if workspace is not None else "NOT_FOUND",
            details={"workspace_id": workspace_id},
        )

    return _ensure_owner(workspace, principal)


def require_document_access(
    db: Session, document_id: str, principal: Principal
) -> tuple[Document, Workspace]:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("文档不存在", details={"document_id": document_id})
    workspace = require_workspace_access(db, document.workspace_id, principal)
    return document, workspace


def require_version_access(
    db: Session, version_id: str, principal: Principal
) -> tuple[DocumentVersion, Document, Workspace]:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise NotFoundError("文档版本不存在", details={"version_id": version_id})
    document = db.get(Document, version.document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError(
            "文档不存在或已删除",
            code="DOCUMENT_DELETED",
            details={"version_id": version_id},
        )
    workspace = require_workspace_access(db, version.workspace_id, principal)
    return version, document, workspace
