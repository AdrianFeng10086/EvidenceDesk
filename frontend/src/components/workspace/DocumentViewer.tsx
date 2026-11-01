'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Minus,
  Plus,
  RefreshCw,
} from 'lucide-react';

import { MarkdownContent } from '@/components/markdown/MarkdownContent';
import {
  ApiError,
  getDocument,
  getPageContent,
  originalFileUrl,
  retryParse,
} from '@/lib/api/documents';
import {
  formatFileSize,
  isPendingStatus,
  parseStatusInfo,
  supportLevelLabel,
} from '@/lib/document-status';
import type { DocumentDetail, EvidenceSpan, PageContent } from '@/lib/types/documents';
import { cn } from '@/lib/utils';

interface DocumentViewerProps {
  workspaceId: string;
  versionId: string | null;
  onSelectVersion: (versionId: string) => void;
}

const SPAN_KIND_LABELS: Record<string, string> = {
  heading: '标题',
  paragraph: '段落',
  list_item: '列表项',
  line: '文本行',
  code: '代码块',
  table: '表格',
  quote: '引用',
};

export function DocumentViewer({
  workspaceId,
  versionId,
  onSelectVersion,
}: DocumentViewerProps) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [content, setContent] = useState<PageContent | null>(null);
  const [contentError, setContentError] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [page, setPage] = useState(1);
  const [fontSize, setFontSize] = useState(14);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  // 拉取文档元数据；解析中/索引中时轮询直到终态
  useEffect(() => {
    if (!versionId) {
      setDetail(null);
      setDetailError(null);
      setLoadingDetail(false);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    setDetail((current) =>
      current?.version.id === versionId ? current : null
    );
    setDetailError(null);
    setLoadingDetail(true);
    setPage(1);
    setSelectedSpanId(null);

    const fetchDetail = async () => {
      try {
        const next = await getDocument(versionId);
        if (cancelled) return;
        setDetail(next);
        setDetailError(null);
        setLoadingDetail(false);
        if (isPendingStatus(next.version.parse_status)) {
          timer = setTimeout(fetchDetail, 1200);
        }
      } catch (cause) {
        if (cancelled) return;
        setDetailError(cause instanceof ApiError ? cause.message : '读取文档信息失败');
        setLoadingDetail(false);
      }
    };

    void fetchDetail();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [versionId, refreshTick]);

  // 解析成功后读取当前页原文与证据片段
  useEffect(() => {
    if (!detail || detail.version.parse_status !== 'success') {
      setContent(null);
      setContentError(null);
      return;
    }

    let cancelled = false;
    setLoadingContent(true);
    setContentError(null);

    getPageContent(detail.version.id, page)
      .then((next) => {
        if (cancelled) return;
        setContent(next);
      })
      .catch((cause) => {
        if (cancelled) return;
        setContent(null);
        setContentError(cause instanceof ApiError ? cause.message : '读取原文失败');
      })
      .finally(() => {
        if (!cancelled) setLoadingContent(false);
      });

    return () => {
      cancelled = true;
    };
  }, [detail?.version.id, detail?.version.parse_status, page]);

  const handleRetry = useCallback(async () => {
    if (!versionId) return;
    setRetrying(true);
    try {
      await retryParse(versionId);
      setRefreshTick((value) => value + 1);
    } catch (cause) {
      setDetailError(cause instanceof ApiError ? cause.message : '重新解析失败');
    } finally {
      setRetrying(false);
    }
  }, [versionId]);

  if (!versionId) {
    return (
      <div className="flex h-full flex-col">
        <ViewerHeader />
        <div className="flex flex-1 items-center justify-center px-6 text-center text-slate-500">
          <div>
            <FileText className="mx-auto mb-4 h-16 w-16 opacity-25" />
            <p className="text-sm">从左侧选择一份文档</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              解析成功后，这里会显示按页、段落和文字框抽取的原文。
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewerHeader
        detail={detail}
        onSelectVersion={onSelectVersion}
        versionId={versionId}
      />

      {detailError && (
        <div className="m-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <span className="min-w-0 flex-1 break-words">{detailError}</span>
        </div>
      )}

      {loadingDetail && !detail ? (
        <div className="flex flex-1 items-center justify-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在读取文档…
        </div>
      ) : detail ? (
        <ViewerBody
          detail={detail}
          content={content}
          contentError={contentError}
          loadingContent={loadingContent}
          page={page}
          setPage={setPage}
          fontSize={fontSize}
          setFontSize={setFontSize}
          selectedSpanId={selectedSpanId}
          setSelectedSpanId={setSelectedSpanId}
          retrying={retrying}
          onRetry={handleRetry}
          workspaceId={workspaceId}
        />
      ) : (
        <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
          暂无文档信息
        </div>
      )}
    </div>
  );
}

function ViewerHeader({
  detail,
  versionId,
  onSelectVersion,
}: {
  detail?: DocumentDetail | null;
  versionId?: string;
  onSelectVersion?: (versionId: string) => void;
}) {
  const version = detail?.version;
  const versions = detail?.document.versions ?? [];
  const status = parseStatusInfo(version);

  return (
    <header className="flex-shrink-0 border-b border-slate-200 bg-slate-50 px-3 py-3 sm:px-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-slate-900">
          <FileText className="h-4 w-4 flex-shrink-0 text-sky-700" />
          <div className="min-w-0">
            <h2 className="truncate text-sm font-medium" title={version?.file_name}>
              {version?.file_name ?? '文档阅读'}
            </h2>
            {version && (
              <p className="truncate text-[11px] text-slate-500">
                {formatFileSize(version.file_size)} ·{' '}
                {supportLevelLabel(version.support_level)}
                {version.page_count ? ` · ${version.page_count} 页` : ''}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-2">
          {version && (
            <span
              className={cn(
                'hidden rounded-full border px-2 py-0.5 text-[11px] font-medium sm:inline-flex',
                status.className
              )}
            >
              {status.label}
            </span>
          )}
          {versions.length > 1 && onSelectVersion && (
            <select
              value={versionId}
              onChange={(event) => onSelectVersion(event.target.value)}
              className="max-w-[110px] rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-100"
              aria-label="选择文档版本"
            >
              {versions.map((item) => (
                <option key={item.id} value={item.id}>
                  v{item.version}
                  {item.parse_status === 'failed' ? '（失败）' : ''}
                </option>
              ))}
            </select>
          )}
          {versionId && (
            <a
              href={originalFileUrl(versionId)}
              className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-900"
              title="下载原始文件"
              aria-label="下载原始文件"
            >
              <Download className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>
    </header>
  );
}

function ViewerBody({
  detail,
  content,
  contentError,
  loadingContent,
  page,
  setPage,
  fontSize,
  setFontSize,
  selectedSpanId,
  setSelectedSpanId,
  retrying,
  onRetry,
  workspaceId,
}: {
  detail: DocumentDetail;
  content: PageContent | null;
  contentError: string | null;
  loadingContent: boolean;
  page: number;
  setPage: (page: number) => void;
  fontSize: number;
  setFontSize: (updater: (size: number) => number) => void;
  selectedSpanId: string | null;
  setSelectedSpanId: (id: string | null) => void;
  retrying: boolean;
  onRetry: () => void;
  workspaceId: string;
}) {
  const version = detail.version;

  if (version.parse_status === 'failed') {
    return (
      <div className="flex-1 overflow-y-auto p-4">
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="flex items-start gap-2 text-red-800">
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
            <div className="min-w-0">
              <h3 className="text-sm font-medium">解析失败</h3>
              <p className="mt-1 text-xs leading-relaxed">
                {version.parse_error_code && (
                  <span className="mr-1 font-mono text-[11px]">{version.parse_error_code}</span>
                )}
                {version.parse_error || '未知错误'}
              </p>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={onRetry}
              disabled={retrying}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs text-slate-700 shadow-sm ring-1 ring-slate-200 transition-colors hover:text-sky-700 hover:ring-sky-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {retrying ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              重新解析
            </button>
            <a
              href={originalFileUrl(version.id)}
              className="text-xs text-slate-500 underline decoration-slate-300 underline-offset-2 hover:text-slate-700"
            >
              下载原始文件
            </a>
          </div>
        </div>
      </div>
    );
  }

  if (isPendingStatus(version.parse_status)) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <ParseProgress detail={detail} />
      </div>
    );
  }

  if (version.parse_status !== 'success') {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
        未知解析状态：{version.parse_status}
      </div>
    );
  }

  const isMarkdown = /\.(md|markdown)$/i.test(version.file_name);
  const pageCount = version.page_count ?? 1;
  const restrictedWarnings = detail.version.warnings.filter(
    (warning) => warning.code !== 'ENCODING_FALLBACK' && warning.code !== 'LONG_BLOCK_SPLIT'
  );

  return (
    <>
      <div className="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 sm:px-4">
        {pageCount > 1 ? (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <input
              type="number"
              min={1}
              max={pageCount}
              value={page}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (Number.isFinite(next)) {
                  setPage(Math.min(pageCount, Math.max(1, next)));
                }
              }}
              className="w-14 rounded border border-slate-300 bg-white px-2 py-1 text-center text-slate-700 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-100"
              aria-label="页码"
            />
            <span>/ {pageCount} 页</span>
          </div>
        ) : (
          <span className="text-xs text-slate-500">单页文本</span>
        )}

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setFontSize((size) => Math.max(12, size - 1))}
            className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-900"
            title="缩小字号"
            aria-label="缩小字号"
          >
            <Minus className="h-4 w-4" />
          </button>
          <span className="w-10 text-center text-[11px] text-slate-600">{fontSize}px</span>
          <button
            type="button"
            onClick={() => setFontSize((size) => Math.min(22, size + 1))}
            className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-900"
            title="放大字号"
            aria-label="放大字号"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </div>

      {restrictedWarnings.length > 0 && (
        <div className="flex flex-shrink-0 items-start gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800 sm:px-4">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <div className="min-w-0 space-y-0.5">
            <div className="font-medium">
              受限解析：{supportLevelLabel(version.support_level)}，请人工核对文字框
            </div>
            {restrictedWarnings.map((warning, index) => (
              <div key={`${warning.code}-${warning.page ?? 'doc'}-${index}`}>
                {warning.code}
                {warning.page ? `（第 ${warning.page} 页）` : ''} · {warning.message}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto bg-slate-100 p-3 sm:p-4">
        {loadingContent ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在读取第 {page} 页…
          </div>
        ) : contentError ? (
          <div className="mx-auto max-w-[760px] rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {contentError}
          </div>
        ) : content ? (
          <div className="mx-auto w-full max-w-[760px] bg-white shadow-sm ring-1 ring-slate-200">
            <div className="border-b border-slate-100 px-4 py-2 text-[11px] text-slate-400 sm:px-6">
              第 {content.page_number} 页
              {content.width && content.height
                ? ` · ${Math.round(content.width)} × ${Math.round(content.height)} pt`
                : ''}
              {' · '}
              {content.char_count} 字符 · {content.spans.length} 个片段
            </div>

            <div className="px-4 py-4 sm:px-6" style={{ fontSize }}>
              {content.is_blank ? (
                <p className="text-sm text-slate-400">本页没有可抽取的文字。</p>
              ) : isMarkdown ? (
                <MarkdownContent
                  content={content.text}
                  className="text-slate-800"
                />
              ) : (
                <div className="space-y-1">
                  {content.spans.map((span) => (
                    <SpanBlock
                      key={span.id}
                      span={span}
                      selected={selectedSpanId === span.id}
                      onSelect={() =>
                        setSelectedSpanId(selectedSpanId === span.id ? null : span.id)
                      }
                    />
                  ))}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-2 text-[10px] text-slate-400 sm:px-6">
              <span className="truncate" title={`SHA-256: ${version.file_hash}`}>
                SHA-256 {version.file_hash.slice(0, 12)}…
              </span>
              <span>
                {detail.document.version_count} 个版本 · 空间 {workspaceId}
              </span>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

function SpanBlock({
  span,
  selected,
  onSelect,
}: {
  span: EvidenceSpan;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'block w-full rounded-md px-2 py-1.5 text-left transition-colors',
        selected ? 'bg-sky-50 ring-1 ring-sky-200' : 'hover:bg-slate-50'
      )}
    >
      <span className="block whitespace-pre-wrap break-words leading-relaxed text-slate-800">
        {span.text}
      </span>
      <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-slate-400">
        <span>{SPAN_KIND_LABELS[span.kind] ?? span.kind}</span>
        <span>字符 {span.char_start}–{span.char_end}</span>
        <span>{span.bboxes.length > 0 ? `${span.bboxes.length} 个文字框` : '无坐标（纯文本）'}</span>
      </span>
      {selected && span.bboxes.length > 0 && (
        <span className="mt-1 block space-y-0.5 font-mono text-[10px] leading-relaxed text-slate-500">
          {span.bboxes.map((box, index) => (
            <span key={`${span.id}-${index}`} className="block">
              框 {index + 1}: x {box.x0}–{box.x1}, y {box.y0}–{box.y1}, 字符{' '}
              {box.char_start}–{box.char_end}
            </span>
          ))}
        </span>
      )}
    </button>
  );
}

function ParseProgress({ detail }: { detail: DocumentDetail }) {
  const version = detail.version;
  const steps = [
    { key: 'uploaded', label: '原文已保存' },
    { key: 'parsing', label: '解析页面、段落与文字框' },
    { key: 'indexing', label: '准备检索索引' },
    { key: 'success', label: '完成' },
  ];
  const currentIndex = steps.findIndex((step) => step.key === version.parse_status);
  const status = parseStatusInfo(version);

  return (
    <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2">
        {status.pulse && <Loader2 className="h-4 w-4 animate-spin text-sky-600" />}
        <span className="text-sm font-medium text-slate-900">{status.label}</span>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        文档版本 v{version.version} · 任务尝试 {detail.parse_job?.attempt ?? 1} 次
      </p>
      <ol className="mt-4 space-y-2.5">
        {steps.map((step, index) => {
          const done = currentIndex > index || version.parse_status === 'success';
          const active = currentIndex === index && version.parse_status !== 'success';
          return (
            <li key={step.key} className="flex items-start gap-2 text-xs">
              {done ? (
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-teal-600" />
              ) : active ? (
                <Loader2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 animate-spin text-sky-600" />
              ) : (
                <span className="mt-1 h-2 w-2 flex-shrink-0 rounded-full border border-slate-300" />
              )}
              <span className={done ? 'text-slate-600' : active ? 'text-slate-900' : 'text-slate-400'}>
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="mt-4 text-[11px] leading-relaxed text-slate-400">
        页面会自动刷新状态。解析失败时会显示明确错误码，可在资料列表或此处重试。
      </p>
    </div>
  );
}
