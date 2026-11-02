'use client';

import type { BBox } from '@/lib/types/documents';
import { toOverlayRects } from '@/lib/pdf/coordinates';
import { cn } from '@/lib/utils';

export interface HighlightGroup {
  evidenceId: string;
  bboxes: readonly BBox[];
}

interface HighlightOverlayProps {
  groups: readonly HighlightGroup[];
  activeEvidenceId: string | null;
  /** 当前页面 CSS 像素 / PDF 点 的比例。 */
  scale: number;
  /** PDF.js 页面旋转角度；非 0 时不绘制精确矩形。 */
  rotation: number;
  pageWidth: number;
  pageHeight: number;
  /** 默认只画当前 evidenceId，避免同页其他引用被误认为已高亮。 */
  showInactive?: boolean;
}

/**
 * 自研高亮层：把同一 EvidenceSpan 的一个或多个文字框画成红色实线矩形。
 * 每个矩形都带 data-evidence-id，同页多个证据不会互相覆盖或混淆。
 */
export function HighlightOverlay({
  groups,
  activeEvidenceId,
  scale,
  rotation,
  pageWidth,
  pageHeight,
  showInactive = false,
}: HighlightOverlayProps) {
  if (rotation % 360 !== 0 || !(scale > 0)) {
    return null;
  }

  const visibleGroups = showInactive
    ? groups
    : groups.filter((group) => group.evidenceId === activeEvidenceId);

  const rects = visibleGroups.flatMap((group) =>
    toOverlayRects(group.bboxes, scale, rotation, pageWidth, pageHeight).map(
      (rect, index) => ({
        ...rect,
        evidenceId: group.evidenceId,
        index,
      })
    )
  );

  if (rects.length === 0) {
    return null;
  }

  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden="true"
      data-page-width={pageWidth}
      data-page-height={pageHeight}
    >
      {rects.map((rect) => {
        const active = rect.evidenceId === activeEvidenceId;
        return (
          <div
            key={`${rect.evidenceId}-${rect.index}`}
            data-evidence-id={rect.evidenceId}
            data-highlight-active={active || undefined}
            title={`证据 ${rect.evidenceId}`}
            className={cn(
              'absolute rounded-[2px]',
              active
                ? 'border-2 border-red-600 bg-red-500/15 shadow-[0_0_0_1px_rgba(255,255,255,0.65)]'
                : 'border border-dashed border-red-400/70 bg-red-400/5'
            )}
            style={{
              left: rect.left,
              top: rect.top,
              width: rect.width,
              height: rect.height,
            }}
          />
        );
      })}
    </div>
  );
}
