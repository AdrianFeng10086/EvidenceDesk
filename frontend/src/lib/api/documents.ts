import type {
  ApiErrorBody,
  DocumentDeleteImpact,
  DocumentDetail,
  DocumentListResponse,
  DocumentSummary,
  PageContent,
  UploadResponse,
} from '@/lib/types/documents';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown>;

  constructor(
    message: string,
    options: { code?: string; status?: number; details?: Record<string, unknown> } = {}
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = options.code ?? 'REQUEST_FAILED';
    this.status = options.status ?? 0;
    this.details = options.details;
  }
}

async function readError(response: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // 非 JSON 错误响应
  }
  return new ApiError(body?.error?.message ?? `请求失败（HTTP ${response.status}）`, {
    code: body?.error?.code ?? 'REQUEST_FAILED',
    status: response.status,
    details: body?.error?.details,
  });
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as T;
}

export function listDocuments(
  workspaceId: string,
  options: { includeDeleted?: boolean } = {}
): Promise<DocumentListResponse> {
  const query = options.includeDeleted ? '?include_deleted=true' : '';
  return request<DocumentListResponse>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/documents${query}`,
    { cache: 'no-store' }
  );
}

export function getDocumentDeleteImpact(
  workspaceId: string,
  documentId: string
): Promise<DocumentDeleteImpact> {
  return request<DocumentDeleteImpact>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/documents/${encodeURIComponent(
      documentId
    )}/delete-impact`,
    { cache: 'no-store' }
  );
}

export function deleteDocument(
  workspaceId: string,
  documentId: string
): Promise<DocumentSummary> {
  return request<DocumentSummary>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/documents/${encodeURIComponent(
      documentId
    )}`,
    { method: 'DELETE' }
  );
}

export function restoreDocument(
  workspaceId: string,
  documentId: string
): Promise<DocumentSummary> {
  return request<DocumentSummary>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/documents/${encodeURIComponent(
      documentId
    )}/restore`,
    { method: 'POST' }
  );
}

export async function uploadDocument(
  workspaceId: string,
  file: File,
  fields: { upload_source?: string; applicable_scope?: string } = {}
): Promise<UploadResponse> {
  const body = new FormData();
  body.append('file', file, file.name);
  if (fields.upload_source) body.append('upload_source', fields.upload_source);
  if (fields.applicable_scope) body.append('applicable_scope', fields.applicable_scope);

  return request<UploadResponse>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/documents`,
    { method: 'POST', body }
  );
}

export function getDocument(versionId: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/documents/${encodeURIComponent(versionId)}`, {
    cache: 'no-store',
  });
}

export function getPageContent(versionId: string, page: number): Promise<PageContent> {
  return request<PageContent>(
    `/api/documents/${encodeURIComponent(versionId)}/content?page=${page}`,
    { cache: 'no-store' }
  );
}

export function retryParse(versionId: string): Promise<{ version: unknown; parse_job: unknown }> {
  return request(`/api/documents/${encodeURIComponent(versionId)}/parse/retry`, {
    method: 'POST',
  });
}

export function originalFileUrl(versionId: string): string {
  return `/api/documents/${encodeURIComponent(versionId)}/original`;
}
