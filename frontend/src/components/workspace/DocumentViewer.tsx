'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  Download,
  FileText,
  Loader2,
  RefreshCw,
  ScanText,
} from 'lucide-react';

import { PdfPageView } from '@/components/evidence/PdfPageView';
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
import {
  LOCATION_TONE_CLASSES,
  describeLocationStatus,
} from '@/lib/evidence/location-status';
import { formatLineRange, lineRangeAt } from '@/lib/evidence/text-range';
import { hasDrawableBboxes } from '@/lib/pdf/coordinates';
import {
  isTextFileName,
  locateInputFromContentSpan,
  useEvidenceLocator,
  type EvidenceLocationStatus,
  type EvidenceTarget,
} from '@/lib/stores/evidence-locator';
import type {
  DocumentDetail,
  EvidenceSpan,
  PageContent,
} from '@/lib/types/documents';
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

const ZOOM_OPTIONS = [0.75, 1, 1.5] as const;
type Zoom = (typeof ZOOM_OPTIONS)[number];

interface PdfPageInfo {
  rotation: number;
  sourceWidth: number;
  sourceHeight: number;
}

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
  const [zoom, setZoom] = useState<Zoom>(1);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [pdfInfo, setPdfInfo] = useState<PdfPageInfo | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const evidenceTarget = useEvidenceLocator((state) => state.target);
  const setLocationStatus = useEvidenceLocator((state) => state.setStatus);

  const target =
    evidenceTarget && evidenceTarget.documentVersionId === versionId
      ? evidenceTarget
      : null;

  // 拉取文档元数据；解析中/索引中时轮询直到终态
  useEffect(() => {
    if (!versionId) {
      setDetail(null);
      setDetailError(null);
      setLoadingDetail(false);
      setContent(null);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    setDetail((current) => (current?.version.id === versionId ? current : null));
    setDetailError(null);
    setLoadingDetail(true);
    setContent(null);
    setContentError(null);
    setPage(1);
    setSelectedSpanId(null);
    setPdfInfo(null);
    setPdfError(null);

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

  // 证据跳转：等目标版本元数据就绪后再切页，避免落到旧文件
  useEffect(() => {
    if (!target) return;
    if (!detail || detail.version.id !== target.documentVersionId) return;
    setPage(Math.max(1, target.page));
  }, [target, detail]);

  useEffect(() => {
    setPdfInfo(null);
    setPdfError(null);
  }, [versionId, page]);

  // 读取当前页原文与证据片段（PDF 用于同页引用导航，TXT/MD 用于段落高亮）
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

  const handlePdfMetrics = useCallback((metrics: PdfPageInfo) => {
    setPdfInfo(metrics);
    setPdfError(null);
  }, []);

  const handlePdfError = useCallback((message: string) => {
    setPdfError(message);
  }, []);

  const version = detail?.version;
  const isText = version ? isTextFileName(version.file_name) : false;
  const isPdf = !!version && !isText && version.file_suffix.toLowerCase() === '.pdf';
  const pageContent =
    content && content.page_number === page && content.version_id === version?.id
      ? content
      : null;

  const locationStatus = useMemo<EvidenceLocationStatus | null>(() => {
    if (!target) return null;

    if (detailError) {
      return {
        kind: 'failed',
        message: detailError,
        evidenceId: target.spanId ?? undefined,
      };
    }
    if (!detail || detail.version.id !== target.documentVersionId) {
      return { kind: 'loading', message: '正在打开证据所在文档…' };
    }
    if (detail.version.parse_status !== 'success') {
      return {
        kind: 'failed',
        message: `文档尚未解析成功（${detail.version.parse_status}），暂时无法定位原文。`,
        evidenceId: target.spanId ?? undefined,
      };
    }

    if (isText) {
      if (contentError) {
        return {
          kind: 'failed',
          message: contentError,
          evidenceId: target.spanId ?? undefined,
        };
      }
      if (!pageContent) {
        return { kind: 'loading', message: '正在读取纯文本原文…' };
      }
      if (!target.spanId) {
        return {
          kind: 'page',
          page: target.page,
          message: '纯文本没有 PDF 页码，已打开全文；请从证据卡点击具体段落。',
        };
      }

      const index = pageContent.spans.findIndex((span) => span.id === target.spanId);
      if (index < 0) {
        return {
          kind: 'failed',
          message: '证据片段不存在于当前文档版本，可能已被重新解析。',
          evidenceId: target.spanId,
        };
      }
      const span = pageContent.spans[index];
      const range = lineRangeAt(pageContent.text, span.char_start, span.char_end);
      const exactText =
        pageContent.text.slice(span.char_start, span.char_end) === span.text;
      return {
        kind: 'text',
        page: target.page,
        evidenceId: target.spanId,
        message: `第 ${index + 1} 段 · ${formatLineRange(range)}${
          exactText ? '' : ' · 字符范围与原文不一致，已按片段 ID 定位'
        }`,
      };
    }

    if (pdfError) {
      return {
        kind: 'failed',
        message: pdfError,
        evidenceId: target.spanId ?? undefined,
      };
    }
    if (!pdfInfo || !(pdfInfo.sourceWidth > 0)) {
      return { kind: 'loading', message: '正在加载 PDF 页面…' };
    }
    if (pdfInfo.rotation % 360 !== 0) {
      return {
        kind: 'page',
        page: target.page,
        evidenceId: target.spanId ?? undefined,
        message: `第 ${target.page} 页旋转 ${pdfInfo.rotation}°，暂不支持精确高亮，已做页级定位。`,
      };
    }
    if (!hasDrawableBboxes(target.bboxes)) {
      return {
        kind: 'page',
        page: target.page,
        evidenceId: target.spanId ?? undefined,
        message:
          target.source === 'document-reference'
            ? `已按页定位到第 ${target.page} 页（页级兜底，不显示精确红框）。`
            : `该证据没有可用文字框，已定位到第 ${target.page} 页。`,
      };
    }
    if (detail.version.support_level === 'restricted') {
      return {
        kind: 'approximate',
        page: target.page,
        evidenceId: target.spanId ?? '',
        message: `受限解析（多栏/表格）：红色实线已画出，但坐标可能不精确，请人工核对。`,
      };
    }
    return {
      kind: 'exact',
      page: target.page,
      evidenceId: target.spanId ?? '',
      message: `第 ${target.page} 页 · 红色实线为证据范围（${target.bboxes.length} 个文字框）。`,
    };
  }, [
    target,
    detailError,
    detail,
    isText,
    contentError,
    pageContent,
    pdfError,
    pdfInfo,
    setLocationStatus,
  ]);

  useEffect(() => {
    if (locationStatus) {
      setLocationStatus(locationStatus);
    }
  }, [locationStatus, setLocationStatus]);

  if (!versionId) {
    return (
      <div className="flex h-full flex-col">
        <ViewerHeader />
        <div className="flex flex-1 items-center justify-center px-6 text-center text-slate-500">
          <div>
            <FileText className="mx-auto mb-4 h-16 w-16 opacity-25" />
            <p className="text-sm">从左侧选择一份文档，或点击对话中的证据引用</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              PDF 会按文字框显示红色实线高亮；TXT/Markdown 按段落、行范围定位。
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
          content={pageContent}
          contentError={contentError}
          loadingContent={loadingContent}
          page={page}
          setPage={setPage}
          zoom={zoom}
          setZoom={setZoom}
          selectedSpanId={selectedSpanId}
          setSelectedSpanId={setSelectedSpanId}
          retrying={retrying}
          onRetry={handleRetry}
          workspaceId={workspaceId}
          target={target}
          locationStatus={locationStatus}
          isText={isText}
          isPdf={isPdf}
          pdfInfo={pdfInfo}
          pdfError={pdfError}
          onPdfMetrics={handlePdfMetrics}
          onPdfError={handlePdfError}
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
                {version.page_count && !isTextFileName(version.file_name)
                  ? ` · ${version.page_count} 页`
                  : ' · 纯文本'}
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
  zoom,
  setZoom,
  selectedSpanId,
  setSelectedSpanId,
  retrying,
  onRetry,
  workspaceId,
  target,
  locationStatus,
  isText,
  isPdf,
  pdfInfo,
  pdfError,
  onPdfMetrics,
  onPdfError,
}: {
  detail: DocumentDetail;
  content: PageContent | null;
  contentError: string | null;
  loadingContent: boolean;
  page: number;
  setPage: (page: number) => void;
  zoom: Zoom;
  setZoom: (zoom: Zoom) => void;
  selectedSpanId: string | null;
  setSelectedSpanId: (id: string | null) => void;
  retrying: boolean;
  onRetry: () => void;
  workspaceId: string;
  target: EvidenceTarget | null;
  locationStatus: EvidenceLocationStatus | null;
  isText: boolean;
  isPdf: boolean;
  pdfInfo: PdfPageInfo | null;
  pdfError: string | null;
  onPdfMetrics: (metrics: PdfPageInfo) => void;
  onPdfError: (message: string) => void;
}) {
  const version = detail.version;
  const locate = useEvidenceLocator((state) => state.locate);

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

  const pageCount = version.page_count ?? 1;
  const restrictedWarnings = version.warnings.filter(
    (warning) => warning.code !== 'ENCODING_FALLBACK' && warning.code !== 'LONG_BLOCK_SPLIT'
  );

  const pageEvidenceSpans =
    (content?.spans ?? []).filter((span) => span.bboxes.length > 0);
  const activeEvidenceIndex = target?.spanId
    ? pageEvidenceSpans.findIndex((span) => span.id === target.spanId)
    : -1;
  const canCycle = isPdf && pageEvidenceSpans.length > 1;

  const jumpToSpan = (span: EvidenceSpan) => {
    locate(locateInputFromContentSpan(span, version, detail.document.display_name));
  };

  const cycleEvidence = (direction: -1 | 1) => {
    if (pageEvidenceSpans.length === 0) return;
    const next =
      activeEvidenceIndex < 0
        ? direction > 0
          ? 0
          : pageEvidenceSpans.length - 1
        : (activeEvidenceIndex + direction + pageEvidenceSpans.length) %
          pageEvidenceSpans.length;
    jumpToSpan(pageEvidenceSpans[next]);
  };

  return (
    <>
      <div className="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 sm:px-4">
        {isText ? (
          <span className="text-xs text-slate-500">
            全文
            {content ? ` · ${content.spans.length} 段 · ${content.line_count} 行` : ''}
          </span>
        ) : pageCount > 1 ? (
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
          <span className="text-xs text-slate-500">单页 PDF</span>
        )}

        <div className="flex items-center gap-1" role="group" aria-label="缩放">
          {ZOOM_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setZoom(option)}
              aria-pressed={zoom === option}
              className={cn(
                'rounded px-2 py-1 text-[11px] transition-colors',
                zoom === option
                  ? 'bg-sky-600 text-white'
                  : 'text-slate-500 hover:bg-slate-200/70 hover:text-slate-900'
              )}
            >
              {Math.round(option * 100)}%
            </button>
          ))}
        </div>
      </div>

      {locationStatus && <LocationBanner status={locationStatus} target={target} />}

      {canCycle && (
        <div className="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-500 sm:px-4">
          <span>
            本页有 {pageEvidenceSpans.length} 处证据引用
            {activeEvidenceIndex >= 0
              ? ` · 当前第 ${activeEvidenceIndex + 1} 处`
              : ''}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => cycleEvidence(-1)}
              className="inline-flex items-center gap-0.5 rounded border border-slate-200 px-1.5 py-0.5 text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-700"
            >
              <ChevronLeft className="h-3 w-3" />
              上一处
            </button>
            <button
              type="button"
              onClick={() => cycleEvidence(1)}
              className="inline-flex items-center gap-0.5 rounded border border-slate-200 px-1.5 py-0.5 text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-700"
            >
              下一处
              <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}

      {target && <EvidenceContext target={target} />}

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

      {isPdf ? (
        <PdfPageView
          versionId={version.id}
          pageNumber={page}
          zoom={zoom}
          activeEvidenceId={target?.spanId ?? null}
          activeBboxes={target?.bboxes ?? []}
          onPageMetrics={onPdfMetrics}
          onLoadError={onPdfError}
        />
      ) : (
        <TextViewer
          detail={detail}
          content={content}
          contentError={contentError}
          loadingContent={loadingContent}
          zoom={zoom}
          activeEvidenceId={target?.spanId ?? null}
          targetRequestId={target?.requestId ?? null}
          selectedSpanId={selectedSpanId}
          setSelectedSpanId={setSelectedSpanId}
        />
      )}

      <div className="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50 px-3 py-1.5 text-[10px] text-slate-400 sm:px-4">
        <span className="truncate" title={`SHA-256: ${version.file_hash}`}>
          SHA-256 {version.file_hash.slice(0, 12)}…
        </span>
        <span>
          {detail.document.version_count} 个版本 · 空间 {workspaceId}
          {pdfInfo && !isText ? ` · 页面旋转 ${pdfInfo.rotation}°` : ''}
        </span>
      </div>
    </>
  );
}

function LocationBanner({
  status,
  target,
}: {
  status: EvidenceLocationStatus;
  target: EvidenceTarget | null;
}) {
  const display = describeLocationStatus(status);
  if (!display) return null;

  const evidenceId = target?.spanId;

  return (
    <div
      className={cn(
        'flex flex-shrink-0 items-start gap-2 border-b px-3 py-2 text-[11px] leading-relaxed sm:px-4',
        LOCATION_TONE_CLASSES[display.tone]
      )}
      role="status"
    >
      {display.tone === 'loading' ? (
        <Loader2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 animate-spin" />
      ) : display.tone === 'failed' ? (
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
      ) : display.tone === 'approximate' ? (
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
      ) : display.tone === 'text' ? (
        <ScanText className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
      ) : (
        <Crosshair className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
      )}
      <span className="min-w-0 flex-1">
        <span className="font-medium">{display.label}</span>
        {' · '}
        {display.detail}
        {evidenceId && (
          <span className="ml-1 font-mono text-[10px] opacity-70">
            #{evidenceId.slice(-8)}
          </span>
        )}
      </span>
    </div>
  );
}

function EvidenceContext({ target }: { target: EvidenceTarget }) {
  if (!target.text && !target.contextBefore && !target.contextAfter) return null;

  return (
    <details className="flex-shrink-0 border-b border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-500 sm:px-4">
      <summary className="cursor-pointer select-none text-slate-500 hover:text-slate-700">
        查看证据上下文（前后段落）
      </summary>
      <div className="mt-1.5 space-y-1.5 pb-1 leading-relaxed">
        <ContextLine label="上文" text={target.contextBefore} />
        <div className="rounded border border-red-200 bg-red-50/60 px-2 py-1 text-slate-800">
          {target.text}
        </div>
        <ContextLine label="下文" text={target.contextAfter} />
      </div>
    </details>
  );
}

function ContextLine({ label, text }: { label: string; text?: string | null }) {
  return (
    <div>
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </span>
      <p className="whitespace-pre-wrap break-words text-slate-500">
        {text || '（没有更多上下文）'}
      </p>
    </div>
  );
}

function TextViewer({
  detail,
  content,
  contentError,
  loadingContent,
  zoom,
  activeEvidenceId,
  targetRequestId,
  selectedSpanId,
  setSelectedSpanId,
}: {
  detail: DocumentDetail;
  content: PageContent | null;
  contentError: string | null;
  loadingContent: boolean;
  zoom: Zoom;
  activeEvidenceId: string | null;
  targetRequestId: string | null;
  selectedSpanId: string | null;
  setSelectedSpanId: (id: string | null) => void;
}) {
  const activeRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!activeEvidenceId) return;
    const timer = window.setTimeout(() => {
      activeRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 30);
    return () => window.clearTimeout(timer);
  }, [activeEvidenceId, targetRequestId, content?.version_id]);

  if (loadingContent) {
    return (
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        正在读取全文…
      </div>
    );
  }

  if (contentError) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <div className="max-w-md rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {contentError}
        </div>
      </div>
    );
  }

  if (!content) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
        暂无可显示的原文
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-slate-100 p-3 sm:p-4">
      <div className="mx-auto w-full max-w-[760px] bg-white shadow-sm ring-1 ring-slate-200">
        <div className="border-b border-slate-100 px-4 py-2 text-[11px] text-slate-400 sm:px-6">
          全文 · {content.char_count} 字符 · {content.line_count} 行 ·{' '}
          {content.spans.length} 个段落
        </div>

        <div className="space-y-1 px-3 py-3 sm:px-5" style={{ fontSize: 14 * zoom }}>
          {content.is_blank ? (
            <p className="text-sm text-slate-400">本文件没有可抽取的文字。</p>
          ) : (
            content.spans.map((span, index) => {
              const active = span.id === activeEvidenceId;
              const selected = span.id === selectedSpanId;
              const range = lineRangeAt(content.text, span.char_start, span.char_end);
              const exact =
                content.text.slice(span.char_start, span.char_end) === span.text;

              return (
                <div
                  key={span.id}
                  ref={active ? activeRef : undefined}
                  onClick={() =>
                    setSelectedSpanId(selected ? null : span.id)
                  }
                  className={cn(
                    'cursor-pointer rounded-md border-2 px-2.5 py-1.5 transition-colors',
                    active
                      ? 'border-red-600 bg-red-50/80 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.8)]'
                      : selected
                        ? 'border-sky-300 bg-sky-50'
                        : 'border-transparent hover:bg-slate-50'
                  )}
                >
                  <div className="mb-0.5 flex flex-wrap items-center gap-x-2 text-[10px] text-slate-400">
                    <span>第 {index + 1} 段</span>
                    <span>{formatLineRange(range)}</span>
                    <span>{SPAN_KIND_LABELS[span.kind] ?? span.kind}</span>
                    {active && (
                      <span className="rounded-full bg-red-100 px-1.5 py-0.5 font-medium text-red-700">
                        证据位置
                      </span>
                    )}
                    {!exact && <span className="text-amber-600">字符范围不一致</span>}
                  </div>

                  <p className="whitespace-pre-wrap break-words leading-relaxed text-slate-800">
                    {span.text}
                  </p>

                  {active && (span.context_before || span.context_after) && (
                    <div className="mt-1 space-y-1 border-t border-red-200/70 pt-1 text-[11px] leading-relaxed text-slate-500">
                      <ContextLine label="上文" text={span.context_before} />
                      <ContextLine label="下文" text={span.context_after} />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="border-t border-slate-100 px-4 py-2 text-[10px] text-slate-400 sm:px-6">
          {detail.document.display_name} · 纯文本按段落与行号定位，不显示 PDF 页码
        </div>
      </div>
    </div>
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
