'use client';

import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Download, Loader2, RefreshCw } from 'lucide-react';
import type {
  PDFDocumentProxy,
  PDFDocumentLoadingTask,
  RenderTask,
} from 'pdfjs-dist';

import { originalFileUrl } from '@/lib/api/documents';
import { fitScale } from '@/lib/pdf/coordinates';
import type { BBox } from '@/lib/types/documents';
import { cn } from '@/lib/utils';
import { HighlightOverlay } from './HighlightOverlay';

interface PdfPageMetrics {
  width: number;
  height: number;
  scale: number;
  rotation: number;
  sourceWidth: number;
  sourceHeight: number;
}

interface PdfPageViewProps {
  versionId: string;
  pageNumber: number;
  zoom: number;
  activeEvidenceId: string | null;
  activeBboxes: readonly BBox[];
  onPageMetrics?: (metrics: {
    rotation: number;
    sourceWidth: number;
    sourceHeight: number;
  }) => void;
  onLoadError?: (message: string) => void;
}

export function PdfPageView({
  versionId,
  pageNumber,
  zoom,
  activeEvidenceId,
  activeBboxes,
  onPageMetrics,
  onLoadError,
}: PdfPageViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [containerWidth, setContainerWidth] = useState(0);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [metrics, setMetrics] = useState<PdfPageMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const callbacks = useRef({ onPageMetrics, onLoadError });
  useEffect(() => {
    callbacks.current = { onPageMetrics, onLoadError };
  }, [onPageMetrics, onLoadError]);

  // 面板宽度变化（窗口缩放、侧栏拖动）时重新计算 fitScale
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const measure = () => setContainerWidth(element.clientWidth);
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // 文档版本变化时销毁旧 PDF，避免连续点击不同引用时显示旧文件
  useEffect(() => {
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;

    setPdf(null);
    setMetrics(null);
    setError(null);
    setLoading(true);
    callbacks.current.onPageMetrics?.({
      rotation: 0,
      sourceWidth: 0,
      sourceHeight: 0,
    });

    const load = async () => {
      try {
        const pdfjs = await import('pdfjs-dist');
        pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';

        if (cancelled) return;
        loadingTask = pdfjs.getDocument({
          url: originalFileUrl(versionId),
          isEvalSupported: false,
        });
        const document = await loadingTask.promise;
        if (cancelled) {
          void document.destroy();
          return;
        }
        setPdf(document);
      } catch (cause) {
        if (cancelled) return;
        const message = formatPdfError(cause);
        setError(message);
        setLoading(false);
        callbacks.current.onLoadError?.(message);
      }
    };

    void load();

    return () => {
      cancelled = true;
      void loadingTask?.destroy();
    };
  }, [versionId, reloadTick]);

  // 页码、缩放、面板宽度变化都会重新渲染，并按同一 scale 重算高亮坐标
  useEffect(() => {
    if (!pdf || !canvasRef.current || !(containerWidth > 0)) {
      return;
    }

    const canvas = canvasRef.current;
    const context = canvas.getContext('2d');
    if (!context) return;

    let cancelled = false;
    let renderTask: RenderTask | null = null;

    setMetrics(null);
    setLoading(true);
    setError(null);

    const run = async () => {
      try {
        const page = await pdf.getPage(pageNumber);
        if (cancelled) return;

        const rotation = page.rotate || 0;
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = fitScale(containerWidth, baseViewport.width, zoom);
        const viewport = page.getViewport({ scale });

        const outputScale =
          typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1;
        canvas.width = Math.max(1, Math.floor(viewport.width * outputScale));
        canvas.height = Math.max(1, Math.floor(viewport.height * outputScale));
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;

        const transform: [number, number, number, number, number, number] =
          outputScale === 1
            ? [1, 0, 0, 1, 0, 0]
            : [outputScale, 0, 0, outputScale, 0, 0];

        renderTask = page.render({
          canvasContext: context,
          viewport,
          transform,
        });
        await renderTask.promise;

        if (cancelled) return;

        setMetrics({
          width: viewport.width,
          height: viewport.height,
          scale,
          rotation,
          sourceWidth: baseViewport.width,
          sourceHeight: baseViewport.height,
        });
        callbacks.current.onPageMetrics?.({
          rotation,
          sourceWidth: baseViewport.width,
          sourceHeight: baseViewport.height,
        });
      } catch (cause) {
        if (cancelled || isRenderCancelled(cause)) return;
        const message = formatPdfError(cause);
        setError(message);
        callbacks.current.onLoadError?.(message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();

    return () => {
      cancelled = true;
      try {
        renderTask?.cancel();
      } catch {
        // 渲染已完成时 cancel 会抛错，忽略即可
      }
    };
  }, [pdf, pageNumber, containerWidth, zoom]);

  const handleRetry = () => {
    setReloadTick((value) => value + 1);
  };

  return (
    <div
      ref={scrollRef}
      className="relative min-h-0 flex-1 overflow-auto bg-slate-200/70 p-4"
    >
      {error ? (
        <div className="mx-auto max-w-md rounded-xl border border-red-200 bg-red-50 p-4 text-red-800 shadow-sm">
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <div className="min-w-0">
              <h3 className="text-sm font-medium">无法显示原始 PDF</h3>
              <p className="mt-1 break-words text-xs leading-relaxed">{error}</p>
              <p className="mt-2 text-[11px] leading-relaxed text-red-700/80">
                证据仍指向该文档版本，但原始文件不存在或已不可访问；请重新上传原文后再定位。
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleRetry}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs text-slate-700 shadow-sm ring-1 ring-slate-200 transition-colors hover:text-sky-700 hover:ring-sky-300"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              重试
            </button>
            <a
              href={originalFileUrl(versionId)}
              className="inline-flex items-center gap-1 text-xs text-slate-500 underline decoration-slate-300 underline-offset-2 hover:text-slate-700"
            >
              <Download className="h-3.5 w-3.5" />
              尝试下载原始文件
            </a>
          </div>
        </div>
      ) : (
        <div
          className={cn(
            'relative mx-auto bg-white shadow-sm ring-1 ring-slate-200',
            !metrics && 'hidden'
          )}
          style={
            metrics
              ? { width: metrics.width, height: metrics.height }
              : undefined
          }
        >
          <canvas ref={canvasRef} className="block" />
          {metrics && (
            <HighlightOverlay
              groups={
                activeEvidenceId
                  ? [{ evidenceId: activeEvidenceId, bboxes: activeBboxes }]
                  : []
              }
              activeEvidenceId={activeEvidenceId}
              scale={metrics.scale}
              rotation={metrics.rotation}
              pageWidth={metrics.sourceWidth}
              pageHeight={metrics.sourceHeight}
            />
          )}
        </div>
      )}

      {loading && !error && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-100/60">
          <div className="flex items-center gap-2 rounded-lg bg-white/90 px-3 py-2 text-xs text-slate-600 shadow-sm ring-1 ring-slate-200">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在渲染第 {pageNumber} 页…
          </div>
        </div>
      )}
    </div>
  );
}

function isRenderCancelled(cause: unknown): boolean {
  return (
    cause instanceof Error &&
    (cause.name === 'RenderingCancelledException' ||
      cause.name === 'AbortException')
  );
}

function formatPdfError(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : String(cause);
  if (/404|missing|not found/i.test(message)) {
    return '原始 PDF 不存在或已被删除（HTTP 404）。';
  }
  if (/password/i.test(message)) {
    return '原始 PDF 已加密，无法在前端渲染。';
  }
  return message || '未知的 PDF 渲染错误';
}
