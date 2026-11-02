'use client';

import type { ComponentProps } from 'react';
import { FileText } from 'lucide-react';

import { cn } from '@/lib/utils';

export interface DocumentAnchor {
  page: number;
  quote: string;
}

/**
 * 页级跳转兜底，取自 assistant-ui 的 DocumentReference 组件。
 *
 * 当证据缺少文字框、页面旋转或布局不可靠时，仍能按页跳转；
 * 同一文档在同一页有多条摘录时，只把当前页标记为 active。
 */
export function DocumentReference({
  title,
  pages,
  anchors,
  activePage,
  onJump,
  className,
  ...props
}: Omit<
  ComponentProps<'div'>,
  'children' | 'title' | 'pages' | 'anchors' | 'activePage' | 'onJump'
> & {
  title: string;
  pages: number;
  anchors: readonly DocumentAnchor[];
  activePage: number;
  onJump?: (page: number) => void;
}) {
  const currentIndex = anchors.findIndex((anchor) => anchor.page === activePage);

  return (
    <div
      data-slot="document-reference"
      className={cn(
        'flex w-full flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/70 p-3',
        className
      )}
      {...props}
    >
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-slate-500 ring-1 ring-slate-200">
          <FileText className="h-3.5 w-3.5" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[13px] font-medium text-slate-800">{title}</span>
          <span className="font-mono text-[11px] tracking-tight text-slate-400">
            {pages} 页 · {anchors.length} 处引用
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        {anchors.map((anchor, index) => {
          const isActive = anchor.page === activePage;
          const itemClassName = cn(
            'flex flex-col gap-0.5 rounded-lg px-2.5 py-2 text-left transition-colors',
            isActive
              ? 'bg-white ring-1 ring-slate-200'
              : onJump
                ? 'hover:bg-white/80'
                : undefined
          );
          const content = (
            <>
              <span className="font-mono text-[10px] text-slate-400">
                第 {anchor.page} 页
              </span>
              <span className="line-clamp-2 border-s-2 border-slate-200 ps-2 text-[11px] leading-relaxed text-slate-600">
                {anchor.quote}
              </span>
            </>
          );

          return onJump ? (
            <button
              key={`${anchor.page}-${index}`}
              type="button"
              aria-current={isActive || undefined}
              onClick={() => onJump(anchor.page)}
              className={itemClassName}
            >
              {content}
            </button>
          ) : (
            <div
              key={`${anchor.page}-${index}`}
              aria-current={isActive || undefined}
              className={itemClassName}
            >
              {content}
            </div>
          );
        })}
      </div>
    </div>
  );
}
