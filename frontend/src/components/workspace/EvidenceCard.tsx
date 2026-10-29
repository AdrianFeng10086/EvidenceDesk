'use client';

import * as Accordion from '@radix-ui/react-accordion';
import { ChevronDown, FlaskConical } from 'lucide-react';

import { makeAssistantToolUI } from '@assistant-ui/react';

import type { EvidenceToolArgs, EvidenceToolResult } from '@/lib/chat-adapter';
import { cn } from '@/lib/utils';

/**
 * search_evidence 工具调用的折叠证据卡。
 * Day 2 范围：后端固定返回样例证据（is_sample: true），这里始终显示
 * "样例数据" 徽标，避免被误认为真实检索结果。真实检索接入后，
 * is_sample 会随数据变为 false，徽标随之消失。
 */
export const EvidenceCard = makeAssistantToolUI<EvidenceToolArgs, EvidenceToolResult>({
  toolName: 'search_evidence',
  render: function EvidenceCardImpl({ args, result, status }) {
    const isLoading = status.type === 'running' && !result;
    const spans = result?.evidence_spans ?? [];

    return (
      <div className="my-2 max-w-[85%] rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-2.5 text-xs text-slate-500">
          <FlaskConical className="h-3.5 w-3.5 flex-shrink-0 text-amber-600" />
          <span className="truncate">检索证据：{args?.query ?? '...'}</span>
          {result?.is_sample && (
            <span className="ml-auto flex-shrink-0 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
              样例数据 · 非真实检索结果
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 px-4 py-3 text-sm text-slate-500">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" />
            正在检索…
          </div>
        ) : (
          <Accordion.Root type="multiple" className="divide-y divide-slate-200">
            {spans.map((span) => (
              <Accordion.Item key={span.id} value={span.id}>
                <Accordion.Header>
                  <Accordion.Trigger
                    className={cn(
                      'group flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left text-sm text-slate-700',
                      'hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sky-300',
                      'transition-colors'
                    )}
                  >
                    <span className="truncate">
                      {span.document_name} · 第 {span.page} 页
                    </span>
                    <ChevronDown className="h-4 w-4 flex-shrink-0 text-slate-400 transition-transform group-data-[state=open]:rotate-180" />
                  </Accordion.Trigger>
                </Accordion.Header>
                <Accordion.Content className="overflow-hidden px-4 pb-3 text-sm leading-relaxed text-slate-600 data-[state=open]:animate-[accordion-down_150ms_ease-out] data-[state=closed]:animate-[accordion-up_150ms_ease-out]">
                  {span.text}
                </Accordion.Content>
              </Accordion.Item>
            ))}
          </Accordion.Root>
        )}

        {result?.note && (
          <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
            {result.note}
          </div>
        )}

        {result?.claim_text && (
          <div className="border-t border-slate-200 px-4 py-2.5 text-xs text-slate-500">
            {result.claim_text}
          </div>
        )}
      </div>
    );
  },
});
