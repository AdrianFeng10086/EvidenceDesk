'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArchiveRestore,
  FileText,
  FolderOpen,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  Undo2,
  UploadCloud,
  X,
} from 'lucide-react';

import {
  ApiError,
  deleteDocument,
  getDocumentDeleteImpact,
  listDocuments,
  restoreDocument,
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
import type {
  DocumentDeleteImpact,
  DocumentListResponse,
  DocumentSummary,
} from '@/lib/types/documents';
import { cn } from '@/lib/utils';

interface FileListProps {
  workspaceId: string;
  selectedVersionId: string | null;
  onSelectVersion: (versionId: string | null) => void;
}

const ACCEPT = '.pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown';

export function FileList({ workspaceId, selectedVersionId, onSelectVersion }: FileListProps) {
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [impactLoadingId, setImpactLoadingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteImpact, setDeleteImpact] = useState<DocumentDeleteImpact | null>(null);
  const [showDeleted, setShowDeleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const response = await listDocuments(workspaceId, { includeDeleted: showDeleted });
      setData(response);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '读取文档列表失败');
    } finally {
      setLoading(false);
    }
  }, [workspaceId, showDeleted]);

  useEffect(() => {
    setLoading(true);
    setData(null);
    void load();
  }, [load]);

  const activeDocuments = data?.documents ?? [];
  const hasPending = Boolean(
    activeDocuments.some(
      (doc) => !doc.deleted_at && isPendingStatus(doc.latest_version?.parse_status)
    )
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

  const handleRequestDelete = useCallback(
    async (document: DocumentSummary) => {
      setImpactLoadingId(document.id);
      setError(null);
      try {
        const impact = await getDocumentDeleteImpact(workspaceId, document.id);
        setDeleteImpact(impact);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : '读取删除影响失败');
      } finally {
        setImpactLoadingId(null);
      }
    },
    [workspaceId]
  );

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteImpact) return;
    const document = deleteImpact.document;
    setDeletingId(document.id);
    setError(null);
    try {
      await deleteDocument(workspaceId, document.id);
      if (document.versions.some((version) => version.id === selectedVersionId)) {
        onSelectVersion(null);
      }
      setDeleteImpact(null);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '删除失败，请稍后重试');
    } finally {
      setDeletingId(null);
    }
  }, [deleteImpact, workspaceId, selectedVersionId, onSelectVersion, load]);

  const handleRestore = useCallback(
    async (document: DocumentSummary) => {
      setRestoringId(document.id);
      setError(null);
      try {
        await restoreDocument(workspaceId, document.id);
        await load();
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : '恢复失败，请稍后重试');
      } finally {
        setRestoringId(null);
      }
    },
    [workspaceId, load]
  );

  const documents = showDeleted
    ? activeDocuments.filter((document) => document.deleted_at)
    : activeDocuments.filter((document) => !document.deleted_at);
  const workspace = data?.workspace;

  return (
    <div
      className="relative flex h-full min-h-0 flex-col"
      onDragOver={(event) => {
        event.preventDefault();
        if (!showDeleted) setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragActive(false);
        if (!showDeleted && event.dataTransfer.files.length) {
          void handleFiles(event.dataTransfer.files);
        }
      }}
    >
      <header className="border-b border-slate-200 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 text-slate-900">
            <FolderOpen className="h-5 w-5 flex-shrink-0 text-sky-700" />
            <h2 className="truncate font-medium" title={workspace?.name ?? workspaceId}>
              {showDeleted ? '回收站' : workspace?.name ?? '资料空间'}
            </h2>
          </div>
          <div className="flex flex-shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => {
                setShowDeleted((value) => !value);
                setDeleteImpact(null);
              }}
              className={cn(
                'rounded-lg border p-1.5 transition-colors',
                showDeleted
                  ? 'border-sky-300 bg-sky-50 text-sky-700'
                  : 'border-slate-200 bg-white text-slate-500 hover:border-sky-300 hover:text-sky-700'
              )}
              title={showDeleted ? '返回资料列表' : '打开回收站'}
              aria-label={showDeleted ? '返回资料列表' : '打开回收站'}
              aria-pressed={showDeleted}
            >
              {showDeleted ? (
                <Undo2 className="h-4 w-4" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </button>
            {!showDeleted && (
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
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span>
            {showDeleted
              ? `回收站 ${documents.length} 个`
              : `${workspace ? `${workspace.document_count} / ${workspace.document_limit}` : documents.length} 个文件`}
          </span>
          {workspace && !showDeleted && (
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
            {showDeleted ? (
              <>
                <Trash2 className="mx-auto mb-3 h-12 w-12 opacity-30" />
                <p className="text-sm">回收站为空</p>
                <p className="mt-1 text-xs leading-relaxed">
                  删除的文档会保留 30 天，可在这里恢复。
                </p>
              </>
            ) : (
              <>
                <UploadCloud className="mx-auto mb-3 h-12 w-12 opacity-30" />
                <p className="text-sm">暂无文件</p>
                <p className="mt-1 text-xs leading-relaxed">
                  支持带文字层 PDF、TXT、Markdown。
                  <br />
                  拖拽文件到这里，或点击右上角 + 上传。
                </p>
              </>
            )}
          </div>
        ) : (
          <ul className="space-y-1 p-2">
            {documents.map((document) => (
              <li key={document.id}>
                <DocumentItem
                  document={document}
                  selected={document.versions.some((v) => v.id === selectedVersionId)}
                  deleted={Boolean(document.deleted_at)}
                  onSelect={() => {
                    const latest = document.latest_version ?? document.versions[0];
                    if (latest) onSelectVersion(latest.id);
                  }}
                  onRetry={handleRetry}
                  onDelete={handleRequestDelete}
                  onRestore={handleRestore}
                  retrying={retryingId !== null && document.latest_version?.id === retryingId}
                  deleting={impactLoadingId === document.id}
                  restoring={restoringId === document.id}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      {dragActive && !showDeleted && (
        <div className="pointer-events-none absolute inset-2 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-sky-400 bg-sky-50/80 text-sm font-medium text-sky-700">
          松开以上传文件
        </div>
      )}

      {deleteImpact && (
        <DeleteImpactDialog
          impact={deleteImpact}
          deleting={deletingId === deleteImpact.document.id}
          onCancel={() => setDeleteImpact(null)}
          onConfirm={handleConfirmDelete}
        />
      )}
    </div>
  );
}

function DocumentItem({
  document,
  selected,
  deleted,
  onSelect,
  onRetry,
  onDelete,
  onRestore,
  retrying,
  deleting,
  restoring,
}: {
  document: DocumentSummary;
  selected: boolean;
  deleted: boolean;
  onSelect: () => void;
  onRetry: (versionId: string) => void;
  onDelete: (document: DocumentSummary) => void;
  onRestore: (document: DocumentSummary) => void;
  retrying: boolean;
  deleting: boolean;
  restoring: boolean;
}) {
  const latest = document.latest_version ?? document.versions[0] ?? null;
  const status = parseStatusInfo(latest);
  const failed = !deleted && latest?.parse_status === 'failed';

  return (
    <div
      className={cn(
        'rounded-lg transition-colors',
        selected ? 'bg-white shadow-sm ring-1 ring-slate-200' : 'hover:bg-slate-100',
        deleted && 'opacity-80'
      )}
    >
      <button
        type="button"
        onClick={deleted ? undefined : onSelect}
        disabled={deleted}
        className={cn('w-full px-3 py-2.5 text-left', deleted && 'cursor-default')}
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
              {deleted && document.deleted_at ? (
                <span className="text-amber-700">· {formatDate(document.deleted_at)} 删除</span>
              ) : (
                latest?.uploaded_at && <span>· {formatDate(latest.uploaded_at)}</span>
              )}
            </div>
            {deleted ? (
              <div className="mt-2">
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                  已删除
                </span>
              </div>
            ) : (
              latest && (
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
              )
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

      {deleted ? (
        <div className="flex justify-end px-3 pb-2.5">
          <button
            type="button"
            onClick={() => onRestore(document)}
            disabled={restoring}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-600 transition-colors hover:border-sky-400 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {restoring ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <ArchiveRestore className="h-3 w-3" />
            )}
            恢复
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-end gap-1.5 px-3 pb-2.5">
          {failed && latest && (
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
          )}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onDelete(document);
            }}
            disabled={deleting}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-500 transition-colors hover:border-red-300 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            title="删除文档"
            aria-label={`删除文档：${document.name}`}
          >
            {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
            删除
          </button>
        </div>
      )}
    </div>
  );
}

function DeleteImpactDialog({
  impact,
  deleting,
  onCancel,
  onConfirm,
}: {
  impact: DocumentDeleteImpact;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const document = impact.document;

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-3">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-document-title"
        className="max-h-full w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 id="delete-document-title" className="text-sm font-medium text-slate-900">
              删除「{document.display_name}」？
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              删除后立即从列表和检索中移除，保留 30 天，可在回收站恢复。原始文件和解析结果在保留期内不会删除。
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="flex-shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <dl className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-slate-50 p-2 text-center">
          <div>
            <dt className="text-[10px] text-slate-400">版本</dt>
            <dd className="text-sm font-medium text-slate-700">{impact.version_count}</dd>
          </div>
          <div>
            <dt className="text-[10px] text-slate-400">页面</dt>
            <dd className="text-sm font-medium text-slate-700">{impact.page_count}</dd>
          </div>
          <div>
            <dt className="text-[10px] text-slate-400">证据片段</dt>
            <dd className="text-sm font-medium text-slate-700">{impact.span_count}</dd>
          </div>
        </dl>

        {impact.referencing_cases.length > 0 && (
          <div className="mt-3">
            <p className="text-[11px] font-medium text-slate-600">
              被 {impact.referencing_cases.length} 个事项引用
            </p>
            <ul className="mt-1 space-y-0.5 text-[11px] text-slate-500">
              {impact.referencing_cases.map((item) => (
                <li key={item.id} className="truncate" title={item.title}>
                  · {item.title}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[10px] leading-relaxed text-amber-700">
              删除后这些事项的范围会失效，需要重新选择资料。
            </p>
          </div>
        )}

        {impact.recent_runs.length > 0 && (
          <div className="mt-2">
            <p className="text-[11px] font-medium text-slate-600">最近使用该文档的运行</p>
            <ul className="mt-1 space-y-0.5 text-[11px] text-slate-500">
              {impact.recent_runs.map((run) => (
                <li key={run.id} className="truncate">
                  · {run.id} · {run.status} · {formatDate(run.created_at)}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={deleting}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={deleting}
            className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {deleting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            确认删除
          </button>
        </div>
      </div>
    </div>
  );
}
