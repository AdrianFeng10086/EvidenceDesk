"""Case 检索范围与证据检索 API 模型。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ScopeItemCreate(BaseModel):
    workspace_id: str = Field(..., min_length=1, max_length=64)
    document_version_id: str = Field(..., min_length=1, max_length=64)


class CaseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    primary_workspace_id: Optional[str] = Field(None, max_length=64)
    scope_items: List[ScopeItemCreate] = Field(default_factory=list)


class CaseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)


class RetrievalFiltersIn(BaseModel):
    workspace_ids: List[str] = Field(default_factory=list)
    document_version_ids: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)
    # 文档类型（文件后缀），如 .pdf / .txt / .md
    file_suffixes: List[str] = Field(default_factory=list)
    # 片段类型，如 paragraph / heading / list_item / table / code
    chunk_types: List[str] = Field(default_factory=list)
    applicable_scopes: List[str] = Field(default_factory=list)
    # active：仅活跃来源；deleted：仅已删除来源；all：全部（已删除来源仍不可检索）
    deletion_status: str = Field("active", pattern="^(active|deleted|all)$")


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)
    filters: RetrievalFiltersIn = Field(default_factory=RetrievalFiltersIn)
    record_run: bool = True


class ScopeItemOut(BaseModel):
    id: str
    workspace_id: str
    workspace_name: Optional[str] = None
    document_id: Optional[str] = None
    document_version_id: str
    document_name: Optional[str] = None
    file_name: Optional[str] = None
    file_suffix: Optional[str] = None
    file_version: Optional[int] = None
    applicable_scope: Optional[str] = None
    source_state: str
    parse_status: Optional[str] = None
    index_status: Optional[str] = None
    chunk_count: Optional[int] = None
    created_at: Optional[str] = None


class CaseOut(BaseModel):
    id: str
    owner_id: str
    title: str
    description: Optional[str] = None
    primary_workspace_id: Optional[str] = None
    scope_item_count: int = 0
    scope_hash: Optional[str] = None
    created_at: str
    updated_at: str


class CaseDetailOut(CaseOut):
    scope_items: List[ScopeItemOut] = Field(default_factory=list)
    scope_snapshot: dict = Field(default_factory=dict)
