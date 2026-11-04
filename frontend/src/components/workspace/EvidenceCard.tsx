'use client';

import { useMemo, useState } from 'react';
import {
  AlertCircle,
  ChevronDown,
  Crosshair,
  Loader2,
  Quote,
  ScanSearch,
} from 'lucide-react';

import { makeAssistantToolUI } from '@assistant-ui/react';

import { DocumentReference } from '@/components/evidence/DocumentReference';
import { describeLocationStatus, LOCATION_TONE_CLASSES } from '@/lib/evidence/location-status';
import {
  isTextFileName,
  locateInputFromEvidenceSpan,
  useEvidenceLocator,
} from '@/lib/stores/evidence-locator';
import type { EvidenceToolArgs, EvidenceToolResult } from '@/lib/chat-adapter';
import type { EvidenceSpanSample } from '@/lib/types/stream-events';
import { cn } from '@/lib/utils';

const SPAN_KIND_LABELS: Record<string, string> = {
  heading: '标题',
  paragraph: '段落',
  list_item: '列表项',
  line: '文本行',
  code: '代码块',
  table: '表格',
  quote: '引用',
};

interface EvidenceDocGroup {
  versionId: string;
  title: string;
  fileName: string;
  fileSuffix: string;
  pageCount: number;
  supportLevel: string;
  spans: EvidenceSpanSample[];
}

/**
 * search_evidence 工具调用的证据卡。
 *
 * - 真实证据片段带 document_version_id / page / bboxes / context
 * - 点击“定位”精确定位；无文字框的 PDF 退回页级跳转
 * - PDF 底部渲染 assistant-ui DocumentReference 作为页级兜底
 * - TXT/Markdown 只显示段落/行范围，不伪造 PDF 页码
 */
export const EvidenceCard = makeAssistantToolUI<EvidenceToolArgs, EvidenceToolResult>({
  toolName: 'search_evidence',
  render: function EvidenceCardImpl({ args, result, status }) {
    const isLoading = status.type === 'running' && !result;
    const spans = useMemo(() => result?.evidence_spans ?? [], [result]);
    const target = useEvidenceLocator((state) => state.target);
    const locationStatus = useEvidenceLocator((state) => state.status);
    const locate = useEvidenceLocator((state) => state.locate);
    const locatePage = useEvidenceLocator((state) => state.locatePage);

    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [inlineError, setInlineError] = useState<string | null>(null);
    const [collapsed, setCollapsed] = useState(false);

    const groups = useMemo(() => groupByDocument(spans), [spans]);
    const targetGroup = target
      ? groups.find((group) => group.versionId === target.documentVersionId)
      : undefined;
    const statusDisplay = targetGroup ? describeLocationStatus(locationStatus) : null;

    const handleLocate = (span: EvidenceSpanSample) => {
      const input = locateInputFromEvidenceSpan(span);
      if (!input) {
        setInlineError('该证据缺少文档版本信息，无法定位到原文。');
        return;
      }
      setInlineError(null);
      locate(input);
    };

    const handlePageJump = (group: EvidenceDocGroup, page: number) => {
      setInlineError(null);
      locatePage({
        documentVersionId: group.versionId,
        page,
        documentName: group.title,
        fileName: group.fileName,
        fileSuffix: group.fileSuffix,
        supportLevel: group.supportLevel,
        source: 'document-reference',
      });
    };

    return (
      <div className="my-2 max-w-[85%] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-expanded={!collapsed}
          className="flex w-full items-center gap-2 border-b border-slate-200 px-4 py-2.5 text-left text-xs text-slate-500 transition-colors hover:bg-slate-50"
        >
          <ScanSearch className="h-3.5 w-3.5 flex-shrink-0 text-sky-700" />
          <span className="truncate">检索证据：{args?.query ?? '...'}</span>
          {result?.is_sample && (
            <span className="ml-auto flex-shrink-0 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
              样例数据 · 非真实检索结果
            </span>
          )}
          {result && !result.is_sample && spans.length > 0 && (
            <span className="ml-auto flex-shrink-0 text-[11px] text-slate-400">
              {spans.length} 处真实原文
            </span>
          )}
          <ChevronDown
            aria-hidden="true"
            className={cn(
              'h-3.5 w-3.5 flex-shrink-0 text-slate-400 transition-transform',
              collapsed && '-rotate-90'
            )}
          />
          <span className="sr-only">{collapsed ? '展开检索证据' : '收起检索证据'}</span>
        </button>

        {!collapsed && (
          <>
            {inlineError && (
              <div className="flex items-start gap-2 border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                <span className="min-w-0 flex-1 break-words">{inlineError}</span>
              </div>
            )}

            {statusDisplay && (
              <div
                className={cn(
                  'flex items-start gap-2 border-b px-4 py-2 text-[11px] leading-relaxed',
                  LOCATION_TONE_CLASSES[statusDisplay.tone]
                )}
              >
                {statusDisplay.tone === 'loading' ? (
                  <Loader2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 animate-spin" />
                ) : (
                  <Crosshair className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{statusDisplay.label}</span>
                  {' · '}
                  {statusDisplay.detail}
                </span>
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center gap-2 px-4 py-3 text-sm text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在检索原文证据…
              </div>
            ) : spans.length === 0 ? (
              <div className="px-4 py-3 text-sm text-slate-500">
                {result?.note ?? '没有找到可引用的原文片段。'}
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {spans.map((span) => {
                  const isActive =
                    !!target &&
                    target.documentVersionId === span.document_version_id &&
                    (target.spanId === span.id ||
                      (!target.spanId && target.page === span.page));
                  const expanded = expandedId === span.id;
                  const isText = isTextFileName(span.file_name ?? span.document_name);
                  const hasBoxes = (span.bboxes?.length ?? 0) > 0;

                  return (
                    <div
                      key={span.id}
                      className={cn(
                        'transition-colors',
                        isActive ? 'bg-red-50/60' : 'hover:bg-slate-50/70'
                      )}
                    >
                      <div className="flex items-start gap-2 px-3 py-3 sm:px-4">
                        <button
                          type="button"
                          onClick={() => setExpandedId(expanded ? null : span.id)}
                          aria-expanded={expanded}
                          aria-label={`${expanded ? '收起' : '查看'}证据上下文：${span.document_name}`}
                          className="min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sky-300"
                        >
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                            <span
                              className="max-w-full truncate font-medium text-slate-700"
                              title={span.document_name}
                            >
                              {span.document_name}
                            </span>
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
                              {isText
                                ? '纯文本段落'
                                : `第 ${span.page} 页`}
                            </span>
                            {isActive && (
                              <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-medium text-red-700">
                                当前定位
                              </span>
                            )}
                          </div>

                          <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-slate-700">
                            {span.text}
                          </p>

                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-slate-400">
                            <span>{SPAN_KIND_LABELS[span.kind ?? ''] ?? span.kind ?? '片段'}</span>
                            {typeof span.char_start === 'number' &&
                              typeof span.char_end === 'number' && (
                                <span>
                                  字符 {span.char_start}–{span.char_end}
                                </span>
                              )}
                            <span>
                              {hasBoxes
                                ? `${span.bboxes?.length} 个文字框`
                                : isText
                                  ? '按段落/行定位'
                                  : '无文字框 · 仅页级定位'}
                            </span>
                            <span className="inline-flex items-center gap-0.5">
                              {expanded ? '收起上下文' : '查看前后段落'}
                              <ChevronDown
                                className={cn(
                                  'h-3 w-3 transition-transform',
                                  expanded && 'rotate-180'
                                )}
                              />
                            </span>
                          </div>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleLocate(span)}
                          aria-label={`定位证据：${span.text.slice(0, 24)}`}
                          className="mt-0.5 inline-flex flex-shrink-0 items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-600 transition-colors hover:border-red-300 hover:text-red-700 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-300"
                          title="在右侧原文中定位"
                        >
                          <Crosshair className="h-3 w-3" />
                          定位
                        </button>
                      </div>

                      {expanded && (
                        <div className="space-y-2 border-t border-slate-100 bg-slate-50/70 px-3 py-2.5 text-xs leading-relaxed text-slate-600 sm:px-4">
                          <ContextBlock label="上文" text={span.context_before} />
                          <div className="rounded-md border border-slate-200 bg-white px-2.5 py-2 text-slate-800">
                            {span.text}
                          </div>
                          <ContextBlock label="下文" text={span.context_after} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {groups
              .filter(
                (group) =>
                  !isTextFileName(group.fileName) &&
                  !/\.(txt|md|markdown)$/i.test(group.fileSuffix)
              )
              .map((group) => (
                <div
                  key={`reference-${group.versionId}`}
                  className="border-t border-slate-200 p-3"
                >
                  <DocumentReference
                    title={group.title}
                    pages={group.pageCount}
                    anchors={group.spans.map((span) => ({
                      page: span.page,
                      quote: span.text,
                    }))}
                    activePage={
                      target?.documentVersionId === group.versionId
                        ? target.page
                        : -1
                    }
                    onJump={(page) => handlePageJump(group, page)}
                  />
                  <p className="mt-1.5 px-1 text-[10px] leading-relaxed text-slate-400">
                    页级兜底：无文字框、页面旋转或布局不可靠时，仍可按页跳转到正确位置。
                  </p>
                </div>
              ))}

            {result?.note && spans.length > 0 && (
              <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
                {result.note}
              </div>
            )}

            {result?.claim_text && (
              <div className="flex items-start gap-1.5 border-t border-slate-200 px-4 py-2.5 text-xs text-slate-500">
                <Quote className="mt-0.5 h-3 w-3 flex-shrink-0" />
                <span className="min-w-0 flex-1">{result.claim_text}</span>
              </div>
            )}
          </>
        )}
      </div>
    );
  },
});

function ContextBlock({ label, text }: { label: string; text?: string | null }) {
  return (
    <div>
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </span>
      <p className="mt-0.5 whitespace-pre-wrap break-words text-slate-500">
        {text || '（没有更多上下文）'}
      </p>
    </div>
  );
}

function groupByDocument(spans: readonly EvidenceSpanSample[]): EvidenceDocGroup[] {
  const groups = new Map<string, EvidenceDocGroup>();

  for (const span of spans) {
    if (!span.document_version_id) continue;

    const existing = groups.get(span.document_version_id);
    if (existing) {
      existing.spans.push(span);
      existing.pageCount = Math.max(existing.pageCount, span.page_count ?? span.page);
      continue;
    }

    groups.set(span.document_version_id, {
      versionId: span.document_version_id,
      title: span.document_name,
      fileName: span.file_name ?? span.document_name,
      fileSuffix: span.file_suffix ?? '',
      pageCount: span.page_count ?? span.page,
      supportLevel: span.support_level ?? 'full',
      spans: [span],
    });
  }

  return [...groups.values()];
}
