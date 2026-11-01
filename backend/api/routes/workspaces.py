"""资料空间接口。

每个资料空间在创建时绑定 owner_id（访问主体）。首版只有演示账户，
但所有权校验贯穿所有文档与证据接口，后续接入登录无需改业务路由。
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.serializers import workspace_out
from core.database import get_db
from db.models import Workspace, new_id
from schemas.document import WorkspaceCreate, WorkspaceOut
from services.access import Principal, get_principal, require_workspace_access

router = APIRouter()


@router.get("/workspaces", response_model=List[WorkspaceOut], tags=["资料空间"])
def list_workspaces(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> List[WorkspaceOut]:
    workspaces = db.scalars(
        select(Workspace)
        .where(Workspace.owner_id == principal.id)
        .order_by(Workspace.created_at)
    ).all()
    return [workspace_out(db, workspace) for workspace in workspaces]


@router.post("/workspaces", response_model=WorkspaceOut, status_code=201, tags=["资料空间"])
def create_workspace(
    payload: WorkspaceCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> WorkspaceOut:
    workspace = Workspace(
        id=new_id("ws"),
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        owner_id=principal.id,
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace_out(db, workspace)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut, tags=["资料空间"])
def get_workspace(
    workspace_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> WorkspaceOut:
    workspace = require_workspace_access(db, workspace_id, principal)
    return workspace_out(db, workspace)
