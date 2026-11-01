import type { DocumentVersion, ParseStatus, SupportLevel } from '@/lib/types/documents';

export const PENDING_STATUSES: ParseStatus[] = ['uploaded', 'parsing', 'indexing'];

export function isPendingStatus(status?: ParseStatus | null): boolean {
  return Boolean(status && PENDING_STATUSES.includes(status));
}

export interface StatusInfo {
  label: string;
  className: string;
  pulse?: boolean;
}

export function parseStatusInfo(version?: DocumentVersion | null): StatusInfo {
  if (!version) {
    return { label: '等待解析', className: 'border-slate-200 bg-slate-100 text-slate-500' };
  }

  switch (version.parse_status) {
    case 'uploaded':
      return {
        label: '已上传 · 等待解析',
        className: 'border-slate-200 bg-slate-100 text-slate-600',
      };
    case 'parsing':
      return {
        label: '解析中',
        className: 'border-amber-300 bg-amber-50 text-amber-700',
        pulse: true,
      };
    case 'indexing':
      return {
        label: '索引准备中',
        className: 'border-sky-300 bg-sky-50 text-sky-700',
        pulse: true,
      };
    case 'failed':
      return {
        label: '解析失败',
        className: 'border-red-300 bg-red-50 text-red-700',
      };
    case 'success':
      return version.support_level === 'restricted'
        ? { label: '已解析 · 受限', className: 'border-amber-300 bg-amber-50 text-amber-700' }
        : { label: '已就绪', className: 'border-teal-300 bg-teal-50 text-teal-700' };
    default:
      return { label: version.parse_status, className: 'border-slate-200 bg-slate-100 text-slate-600' };
  }
}

export function supportLevelLabel(level?: SupportLevel | null): string {
  switch (level) {
    case 'full':
      return '完整文本层';
    case 'restricted':
      return '受限解析';
    case 'unsupported':
      return '不支持';
    case 'pending':
      return '待解析';
    default:
      return level ?? '未知';
  }
}

export function formatFileSize(bytes?: number | null): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
