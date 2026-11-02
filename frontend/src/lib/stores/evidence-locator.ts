'use client';

import { create } from 'zustand';

import type {
  BBox,
  DocumentVersion,
  EvidenceSpan,
} from '@/lib/types/documents';
import type { EvidenceSpanSample } from '@/lib/types/stream-events';

export type EvidenceLocationSource =
  | 'evidence-card'
  | 'document-reference'
  | 'viewer';

export interface EvidenceTarget {
  /** 每次点击都生成新值，保证同一证据重复点击也会重新定位/滚动。 */
  requestId: string;
  /** 目标所属资料空间，避免切换空间后仍被旧目标拉回。 */
  workspaceId: string | null;
  documentVersionId: string;
  spanId: string | null;
  page: number;
  text: string;
  bboxes: BBox[];
  charStart: number;
  charEnd: number;
  contextBefore: string | null;
  contextAfter: string | null;
  documentName: string;
  fileName: string;
  fileSuffix: string;
  supportLevel: string;
  source: EvidenceLocationSource;
}

export type EvidenceLocationStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; message: string }
  | {
      kind: 'exact';
      page: number;
      evidenceId: string;
      message: string;
    }
  | {
      kind: 'approximate';
      page: number;
      evidenceId: string;
      message: string;
    }
  | { kind: 'page'; page: number; evidenceId?: string; message: string }
  | { kind: 'text'; page: number; evidenceId: string; message: string }
  | { kind: 'failed'; message: string; evidenceId?: string };

export interface EvidenceLocateInput {
  documentVersionId: string;
  spanId: string | null;
  page: number;
  text?: string;
  bboxes?: BBox[];
  charStart?: number;
  charEnd?: number;
  contextBefore?: string | null;
  contextAfter?: string | null;
  documentName: string;
  fileName?: string;
  fileSuffix?: string;
  supportLevel?: string;
  source?: EvidenceLocationSource;
}

interface EvidenceLocatorState {
  workspaceId: string | null;
  target: EvidenceTarget | null;
  status: EvidenceLocationStatus;
  setWorkspace: (workspaceId: string) => void;
  locate: (input: EvidenceLocateInput) => EvidenceTarget;
  locatePage: (
    input: Omit<EvidenceLocateInput, 'spanId' | 'text' | 'bboxes'> & {
      spanId?: string | null;
      bboxes?: BBox[];
      text?: string;
    }
  ) => EvidenceTarget;
  setStatus: (status: EvidenceLocationStatus) => void;
  clear: () => void;
}

let sequence = 0;

function nextRequestId(): string {
  sequence += 1;
  return `${Date.now()}-${sequence}`;
}

function buildTarget(
  input: EvidenceLocateInput,
  workspaceId: string | null
): EvidenceTarget {
  return {
    requestId: nextRequestId(),
    workspaceId,
    documentVersionId: input.documentVersionId,
    spanId: input.spanId,
    page: input.page,
    text: input.text ?? '',
    bboxes: input.bboxes ?? [],
    charStart: input.charStart ?? 0,
    charEnd: input.charEnd ?? 0,
    contextBefore: input.contextBefore ?? null,
    contextAfter: input.contextAfter ?? null,
    documentName: input.documentName,
    fileName: input.fileName ?? input.documentName,
    fileSuffix: input.fileSuffix ?? '',
    supportLevel: input.supportLevel ?? 'full',
    source: input.source ?? 'evidence-card',
  };
}

export const useEvidenceLocator = create<EvidenceLocatorState>((set, get) => ({
  workspaceId: null,
  target: null,
  status: { kind: 'idle' },

  setWorkspace: (workspaceId) => {
    if (get().workspaceId !== workspaceId) {
      set({ workspaceId, target: null, status: { kind: 'idle' } });
    }
  },

  locate: (input) => {
    const target = buildTarget(input, get().workspaceId);
    set({
      target,
      status: {
        kind: 'loading',
        message: target.spanId ? '正在定位证据片段…' : '正在定位到页码…',
      },
    });
    return target;
  },

  locatePage: (input) => {
    const target = buildTarget(
      { ...input, spanId: input.spanId ?? null },
      get().workspaceId
    );
    set({
      target,
      status: {
        kind: 'loading',
        message: `正在定位到第 ${target.page} 页…`,
      },
    });
    return target;
  },

  setStatus: (status) => set({ status }),

  clear: () => set({ target: null, status: { kind: 'idle' } }),
}));

export function isTextFileName(fileName: string): boolean {
  return /\.(txt|md|markdown)$/i.test(fileName);
}

/**
 * 证据卡点击：PDF 有文字框时精确定位；纯文本按字符/段落定位；
 * PDF 无文字框时退回页级定位（spanId = null）。
 */
export function locateInputFromEvidenceSpan(
  span: EvidenceSpanSample
): EvidenceLocateInput | null {
  if (!span.document_version_id) {
    return null;
  }

  const fileSuffix = span.file_suffix ?? '';
  const fileName = span.file_name ?? span.document_name;
  const isText = isTextFileName(fileName) || fileSuffix === '.txt' || fileSuffix === '.md';
  const hasBoxes = (span.bboxes?.length ?? 0) > 0;
  const precise = isText || hasBoxes;

  return {
    documentVersionId: span.document_version_id,
    spanId: precise ? span.id : null,
    page: span.page,
    text: span.text,
    bboxes: span.bboxes ?? [],
    charStart: span.char_start,
    charEnd: span.char_end,
    contextBefore: span.context_before ?? null,
    contextAfter: span.context_after ?? null,
    documentName: span.document_name,
    fileName,
    fileSuffix,
    supportLevel: span.support_level,
    source: 'evidence-card',
  };
}

export function locateInputFromContentSpan(
  span: EvidenceSpan,
  version: DocumentVersion,
  documentName: string
): EvidenceLocateInput {
  return {
    documentVersionId: version.id,
    spanId: span.id,
    page: span.page,
    text: span.text,
    bboxes: span.bboxes,
    charStart: span.char_start,
    charEnd: span.char_end,
    contextBefore: span.context_before ?? null,
    contextAfter: span.context_after ?? null,
    documentName,
    fileName: version.file_name,
    fileSuffix: version.file_suffix,
    supportLevel: version.support_level,
    source: 'viewer',
  };
}
