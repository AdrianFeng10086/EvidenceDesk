import type { EvidenceLocationStatus } from '@/lib/stores/evidence-locator';

export type LocationTone =
  | 'loading'
  | 'exact'
  | 'approximate'
  | 'page'
  | 'text'
  | 'failed';

export interface LocationStatusDisplay {
  tone: LocationTone;
  label: string;
  detail: string;
}

export function describeLocationStatus(
  status: EvidenceLocationStatus
): LocationStatusDisplay | null {
  switch (status.kind) {
    case 'idle':
      return null;
    case 'loading':
      return { tone: 'loading', label: '定位中', detail: status.message };
    case 'exact':
      return {
        tone: 'exact',
        label: '已精确定位',
        detail: status.message,
      };
    case 'approximate':
      return {
        tone: 'approximate',
        label: '受限定位',
        detail: status.message,
      };
    case 'page':
      return { tone: 'page', label: '页级定位', detail: status.message };
    case 'text':
      return { tone: 'text', label: '段落定位', detail: status.message };
    case 'failed':
      return { tone: 'failed', label: '定位失败', detail: status.message };
    default:
      return null;
  }
}

export const LOCATION_TONE_CLASSES: Record<LocationTone, string> = {
  loading: 'border-sky-200 bg-sky-50 text-sky-800',
  exact: 'border-red-200 bg-red-50 text-red-800',
  approximate: 'border-amber-200 bg-amber-50 text-amber-800',
  page: 'border-sky-200 bg-sky-50 text-sky-800',
  text: 'border-sky-200 bg-sky-50 text-sky-800',
  failed: 'border-red-300 bg-red-50 text-red-800',
};
