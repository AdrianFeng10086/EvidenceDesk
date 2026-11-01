"""文档、版本、解析状态与证据片段 API 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class WorkspaceOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    owner_id: str
    document_count: int = 0
    document_limit: int = 10
    created_at: datetime
    updated_at: datetime


class WarningOut(BaseModel):
    code: str
    message: str
    page: Optional[int] = None


class BBoxOut(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float
    page_height: float
    char_start: int
    char_end: int


class EvidenceSpanOut(BaseModel):
    id: str
    document_version_id: str
    page: int
    block_index: int
    kind: str
    text: str
    char_start: int
    char_end: int
    bboxes: List[BBoxOut] = Field(default_factory=list)
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    created_at: datetime


class PageSummaryOut(BaseModel):
    page_number: int
    char_count: int
    line_count: int
    width: Optional[float] = None
    height: Optional[float] = None
    is_blank: bool
    span_count: int = 0


class ParseJobOut(BaseModel):
    id: str
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    attempt: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class DocumentVersionOut(BaseModel):
    id: str
    document_id: str
    workspace_id: str
    file_name: str
    file_suffix: str
    media_type: str
    file_hash: str
    file_size: int
    version: int
    upload_source: Optional[str] = None
    applicable_scope: Optional[str] = None
    uploaded_by: str
    uploaded_at: datetime
    parse_status: str
    parse_error_code: Optional[str] = None
    parse_error: Optional[str] = None
    support_level: str
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    page_count: Optional[int] = None
    char_count: Optional[int] = None
    parsed_at: Optional[datetime] = None


class DocumentSummaryOut(BaseModel):
    id: str
    name: str
    display_name: str
    version_count: int
    latest_version: Optional[DocumentVersionOut] = None
    versions: List[DocumentVersionOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DocumentListOut(BaseModel):
    workspace: WorkspaceOut
    documents: List[DocumentSummaryOut]


class DocumentDetailOut(BaseModel):
    workspace: WorkspaceOut
    document: DocumentSummaryOut
    version: DocumentVersionOut
    pages: List[PageSummaryOut]
    parse_job: Optional[ParseJobOut] = None


class PageContentOut(BaseModel):
    version_id: str
    page_number: int
    text: str
    char_count: int
    line_count: int
    width: Optional[float] = None
    height: Optional[float] = None
    is_blank: bool
    spans: List[EvidenceSpanOut]


class UploadResponseOut(BaseModel):
    duplicate: bool
    document: DocumentSummaryOut
    version: DocumentVersionOut
    parse_job: ParseJobOut


class RetryParseResponseOut(BaseModel):
    version: DocumentVersionOut
    parse_job: ParseJobOut


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
