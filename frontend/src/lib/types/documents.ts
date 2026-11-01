/**
 * 与后端 /api/workspaces、/api/documents 接口对应的类型。
 */

export type ParseStatus = 'uploaded' | 'parsing' | 'indexing' | 'success' | 'failed';
export type SupportLevel = 'pending' | 'full' | 'restricted' | 'unsupported';

export interface ParseWarning {
  code: string;
  message: string;
  page?: number;
}

export interface Workspace {
  id: string;
  name: string;
  description?: string | null;
  owner_id: string;
  document_count: number;
  document_limit: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  workspace_id: string;
  file_name: string;
  file_suffix: string;
  media_type: string;
  file_hash: string;
  file_size: number;
  version: number;
  upload_source?: string | null;
  applicable_scope?: string | null;
  uploaded_by: string;
  uploaded_at: string;
  parse_status: ParseStatus;
  parse_error_code?: string | null;
  parse_error?: string | null;
  support_level: SupportLevel;
  warnings: ParseWarning[];
  page_count?: number | null;
  char_count?: number | null;
  parsed_at?: string | null;
}

export interface DocumentSummary {
  id: string;
  name: string;
  display_name: string;
  version_count: number;
  latest_version?: DocumentVersion | null;
  versions: DocumentVersion[];
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  workspace: Workspace;
  documents: DocumentSummary[];
}

export interface ParseJob {
  id: string;
  status: ParseStatus | 'queued';
  error_code?: string | null;
  error_message?: string | null;
  warnings: ParseWarning[];
  attempt: number;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
}

export interface PageSummary {
  page_number: number;
  char_count: number;
  line_count: number;
  width?: number | null;
  height?: number | null;
  is_blank: boolean;
  span_count: number;
}

export interface DocumentDetail {
  workspace: Workspace;
  document: DocumentSummary;
  version: DocumentVersion;
  pages: PageSummary[];
  parse_job?: ParseJob | null;
}

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page_width: number;
  page_height: number;
  char_start: number;
  char_end: number;
}

export interface EvidenceSpan {
  id: string;
  document_version_id: string;
  page: number;
  block_index: number;
  kind: string;
  text: string;
  char_start: number;
  char_end: number;
  bboxes: BBox[];
  context_before?: string | null;
  context_after?: string | null;
  created_at: string;
}

export interface PageContent {
  version_id: string;
  page_number: number;
  text: string;
  char_count: number;
  line_count: number;
  width?: number | null;
  height?: number | null;
  is_blank: boolean;
  spans: EvidenceSpan[];
}

export interface UploadResponse {
  duplicate: boolean;
  document: DocumentSummary;
  version: DocumentVersion;
  parse_job: ParseJob;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
