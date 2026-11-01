'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  FileText,
  FolderOpen,
  Loader2,
  Plus,
  RefreshCw,
  UploadCloud,
} from 'lucide-react';

import {
  ApiError,
  listDocuments,
  retryParse,
  uploadDocument,
} from '@/lib/api/documents';
import {
  formatDate,
  formatFileSize,
  isPendingStatus,
  parseStatusInfo,
  supportLevelLabel,
} from '@/lib/document-status';
import type { DocumentListResponse, DocumentSummary } from '@/lib/types/documents';
import { cn } from '@/lib/utils';

interface FileListProps {
  workspaceId: string;
  selectedVersionId: string | null;
  onSelectVersion: (versionId: string) => void;
}

const ACCEPT = '.pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown';

export function FileList({ workspaceId, selectedVersionId, onSelectVersion }: FileListProps) {
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const response = await listDocuments(workspaceId);
      setData(response);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '读取文档列表失败');
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setLoading(true);
    setData(null);
    void load();
  }, [load]);

  const hasPending = Boolean(
    data?.documents.some((doc) => isPendingStatus(doc.latest_version?.parse_status))
  );

  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => {
      void load();
    }, 1200);
    return () => clearInterval(timer);
  }, [hasPending, load]);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const file = Array.from(files)[0];
      if (!file) return;

      setUploading(true);
      setError(null);
      try {
        const response = await uploadDocument(workspaceId, file);
        onSelectVersion(response.version.id);
        await load();
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : '上传失败，请稍后重试');
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [workspaceId, load, onSelectVersion]
  );

  const handleRetry = useCallback(
    async (versionId: string) => {
      setRetryingId(versionId);
      setError(null);
      try {
        await retryParse(versionId);
        onSelectVersion(versionId);
        await load();
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : '重新解析失败');
      } finally {
        setRetryingId(null);
      }
    },
    [load, onSelectVersion]
  );

  const documents = data?.documents ?? [];
  const workspace = data?.workspace;

  return (
    <div
      className="relative flex h-full min-h-0 flex-col"
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragActive(false);
        if (event.dataTransfer.files.length) void handleFiles(event.dataTransfer.files);
      }}
    >
      <header className="border-b border-slate-200 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 text-slate-900">
            <FolderOpen className="h-5 w-5 flex-shrink-0 text-sky-700" />
            <h2 className="truncate font-medium" title={workspace?.name ?? workspaceId}>
              {workspace?.name ?? '资料空间'}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500 transition-colors hover:border-sky-300 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
            title="上传文件（PDF / TXT / Markdown）"
            aria-label="上传文件"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span>
            {workspace ? `${workspace.document_count} / ${workspace.document_limit}` : documents.length}{' '}
            个文件
          </span>
          {workspace && (
            <span className="truncate text-slate-400" title={`所有者：${workspace.owner_id}`}>
              · {workspace.owner_id}
            </span>
          )}
        </div>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(event) => {
            if (event.target.files?.length) void handleFiles(event.target.files);
          }}
        />

        {error && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
            <span className="min-w-0 flex-1 break-words">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="flex-shrink-0 text-red-500 hover:text-red-700"
              aria-label="关闭错误提示"
            >
              ×
            </button>
          </div>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-6 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在读取文档…
          </div>
        ) : documents.length === 0 ? (
          <div className="p-6 text-center text-slate-500">
            <UploadCloud className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p className="text-sm">暂无文件</p>
            <p className="mt-1 text-xs leading-relaxed">
              支持带文字层 PDF、TXT、Markdown。
              <br />
              拖拽文件到这里，或点击右上角 + 上传。
            </p>
          </div>
        ) : (
          <ul className="space-y-1 p-2">
            {documents.map((document) => (
              <li key={document.id}>
                <DocumentItem
                  document={document}
                  selected={document.versions.some((v) => v.id === selectedVersionId)}
                  onSelect={() => {
                    const latest = document.latest_version ?? document.versions[0];
                    if (latest) onSelectVersion(latest.id);
                  }}
                  onRetry={handleRetry}
                  retrying={retryingId !== null && document.latest_version?.id === retryingId}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      {dragActive && (
        <div className="pointer-events-none absolute inset-2 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-sky-400 bg-sky-50/80 text-sm font-medium text-sky-700">
          松开以上传文件
        </div>
      )}
    </div>
  );
}

function DocumentItem({
  document,
  selected,
  onSelect,
  onRetry,
  retrying,
}: {
  document: DocumentSummary;
  selected: boolean;
  onSelect: () => void;
  onRetry: (versionId: string) => void;
  retrying: boolean;
}) {
  const latest = document.latest_version ?? document.versions[0] ?? null;
  const status = parseStatusInfo(latest);
  const failed = latest?.parse_status === 'failed';

  return (
    <div
      className={cn(
        'rounded-lg transition-colors',
        selected ? 'bg-white shadow-sm ring-1 ring-slate-200' : 'hover:bg-slate-100'
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="w-full px-3 py-2.5 text-left"
        aria-pressed={selected}
      >
        <div className="flex items-start gap-2">
          <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-500" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-slate-900" title={document.name}>
              {document.name}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
              {latest && <span className="font-mono">v{latest.version}</span>}
              {document.version_count > 1 && <span>· {document.version_count} 个版本</span>}
              {latest?.page_count && <span>· {latest.page_count} 页</span>}
              {latest?.file_size != null && <span>· {formatFileSize(latest.file_size)}</span>}
              {latest?.uploaded_at && <span>· {formatDate(latest.uploaded_at)}</span>}
            </div>
            {latest && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
                    status.className
                  )}
                >
                  {status.pulse && (
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                  )}
                  {status.label}
                </span>
                {latest.parse_status === 'success' && (
                  <span className="text-[11px] text-slate-400">
                    {supportLevelLabel(latest.support_level)}
                  </span>
                )}
              </div>
            )}
            {failed && latest?.parse_error && (
              <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-red-600" title={latest.parse_error}>
                {latest.parse_error_code ? `${latest.parse_error_code} · ` : ''}
                {latest.parse_error}
              </p>
            )}
          </div>
        </div>
      </button>

      {failed && latest && (
        <div className="flex justify-end px-3 pb-2.5">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onRetry(latest.id);
            }}
            disabled={retrying}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-600 transition-colors hover:border-sky-400 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {retrying ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            重新解析
          </button>
        </div>
      )}
    </div>
  );
}
