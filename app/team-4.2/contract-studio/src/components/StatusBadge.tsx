import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  GitCompareArrows,
  HelpCircle,
  UserCheck,
} from 'lucide-react';
import type { SemanticStatus } from '../types/contract';

export const STATUS_CONFIG: Record<
  SemanticStatus,
  {
    label: string;
    bgClass: string;
    textClass: string;
    borderClass: string;
    accentHex: string;
  }
> = {
  processing: {
    label: 'Đang xử lý',
    bgClass: 'bg-[#EEF4FF]',
    textClass: 'text-[#16325C]',
    borderClass: 'border-[#BFDBFE]',
    accentHex: '#2563EB',
  },
  needs_confirmation: {
    label: 'Cần xác nhận',
    bgClass: 'bg-[#FDF6E7]',
    textClass: 'text-[#9A5B13]',
    borderClass: 'border-[#F1DFB6]',
    accentHex: '#C68B2C',
  },
  issue: {
    label: 'Phát hiện vấn đề',
    bgClass: 'bg-[#FFF1F2]',
    textClass: 'text-[#BE123C]',
    borderClass: 'border-[#FECDD3]',
    accentHex: '#BE123C',
  },
  conflict: {
    label: 'Mâu thuẫn',
    bgClass: 'bg-[#FDF2F8]',
    textClass: 'text-[#9D174D]',
    borderClass: 'border-[#FBCFE8]',
    accentHex: '#9D174D',
  },
  insufficient_data: {
    label: 'Chưa đủ dữ kiện',
    bgClass: 'bg-[#F1F5F9]',
    textClass: 'text-[#334155]',
    borderClass: 'border-[#CBD5E1]',
    accentHex: '#475569',
  },
  completed: {
    label: 'Hoàn tất',
    bgClass: 'bg-[#ECFDF5]',
    textClass: 'text-[#0F766E]',
    borderClass: 'border-[#A7F3D0]',
    accentHex: '#0F766E',
  },
};

export function StatusIcon({
  status,
  className = 'w-3.5 h-3.5',
}: {
  status: SemanticStatus;
  className?: string;
}) {
  switch (status) {
    case 'processing':
      return <Clock className={className} aria-hidden="true" />;
    case 'needs_confirmation':
      return <UserCheck className={className} aria-hidden="true" />;
    case 'issue':
      return <AlertTriangle className={className} aria-hidden="true" />;
    case 'conflict':
      return <GitCompareArrows className={className} aria-hidden="true" />;
    case 'insufficient_data':
      return <HelpCircle className={className} aria-hidden="true" />;
    case 'completed':
      return <CheckCircle2 className={className} aria-hidden="true" />;
  }
}

export function StatusBadge({
  status,
  customLabel,
  compact = false,
}: {
  status: SemanticStatus;
  customLabel?: string;
  compact?: boolean;
}) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 border font-medium whitespace-nowrap shrink-0 rounded ${
        compact ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-0.5 text-xs'
      } ${cfg.bgClass} ${cfg.textClass} ${cfg.borderClass}`}
    >
      <StatusIcon status={status} className={compact ? 'w-3 h-3' : 'w-3.5 h-3.5'} />
      <span>{customLabel || cfg.label}</span>
    </span>
  );
}
