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
    bgClass: 'bg-[#F3F6FA]',
    textClass: 'text-[#1E3A5F]',
    borderClass: 'border-[#CBD5E1]',
    accentHex: '#1E3A5F',
  },
  needs_confirmation: {
    label: 'Cần xác nhận',
    bgClass: 'bg-[#FDF8EE]',
    textClass: 'text-[#92400E]',
    borderClass: 'border-[#E7D3AD]',
    accentHex: '#92400E',
  },
  issue: {
    label: 'Phát hiện vấn đề',
    bgClass: 'bg-[#FEF4F4]',
    textClass: 'text-[#991B1B]',
    borderClass: 'border-[#E5BABA]',
    accentHex: '#991B1B',
  },
  conflict: {
    label: 'Mâu thuẫn',
    bgClass: 'bg-[#FDF2F4]',
    textClass: 'text-[#881337]',
    borderClass: 'border-[#DFB4BF]',
    accentHex: '#881337',
  },
  insufficient_data: {
    label: 'Chưa đủ dữ kiện',
    bgClass: 'bg-[#F4F5FA]',
    textClass: 'text-[#312E81]',
    borderClass: 'border-[#C7CBE6]',
    accentHex: '#312E81',
  },
  completed: {
    label: 'Hoàn tất',
    bgClass: 'bg-[#F2F8F4]',
    textClass: 'text-[#166534]',
    borderClass: 'border-[#BBD7C5]',
    accentHex: '#166534',
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
