import { motion } from 'motion/react';
import { Check, Loader2 } from 'lucide-react';
import { PIPELINE_STEPS, getStepSemanticStatus } from '../engine/pipelineState';
import type { AnalysisScenario } from '../types/contract';
import { STATUS_CONFIG } from './StatusBadge';

interface PipelineHeaderRailProps {
  scenario: AnalysisScenario;
  currentStepIndex: number;
  isBusy: boolean;
  statusMessage: string;
  factsConfirmed: boolean;
  canAnalyze: boolean;
  hasLastCheck: boolean;
  showVerify: boolean;
  onSelectStep: (idx: number) => void;
  onToggleVerify: () => void;
  onAnalyze: () => void;
}

export function PipelineHeaderRail({
  scenario,
  currentStepIndex,
  isBusy,
  statusMessage,
  factsConfirmed,
  canAnalyze,
  hasLastCheck,
  showVerify,
  onSelectStep,
  onToggleVerify,
  onAnalyze,
}: PipelineHeaderRailProps) {
  return (
    <section
      aria-label="Tiến trình phân tích 9 bước"
      className="bg-white/95 backdrop-blur border-b border-[#E6E2D8] px-4 lg:px-8 py-3.5 relative overflow-hidden"
    >
      {isBusy && (
        <div className="absolute top-0 left-0 right-0 h-[3px] bg-[#EEF4FF] overflow-hidden">
          <motion.div
            className="h-full w-1/3 bg-gradient-to-r from-transparent via-[#2563EB] to-transparent"
            animate={{ x: ['-100%', '300%'] }}
            transition={{ duration: 1.3, repeat: Infinity, ease: 'easeInOut' }}
          />
        </div>
      )}

      <div className="max-w-[1520px] mx-auto flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 min-w-0 text-xs text-stone-600">
            <span className="font-semibold whitespace-nowrap shrink-0 text-[#16325C] bg-[#EEF4FF] border border-[#DBEAFE] px-2.5 py-0.5 rounded-full inline-flex items-center gap-1.5">
              {isBusy && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#2563EB]" />}
              {isBusy ? statusMessage || 'Đang xử lý...' : 'Hồ sơ phân tích trực tiếp'}
            </span>
            <span className="text-[#D8D2C5]" aria-hidden="true">|</span>
            <span className="font-serif text-[15px] font-semibold text-[#141B29] truncate">
              {scenario.title}
            </span>
            <span className="text-[#D8D2C5] hidden sm:inline" aria-hidden="true">·</span>
            <span className="text-[#64748B] truncate hidden sm:inline">
              {scenario.subtitle}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              disabled={isBusy}
              onClick={onToggleVerify}
              className="px-3.5 py-1.5 rounded-xl border border-[#E6E2D8] bg-white text-xs font-medium text-[#334155] hover:bg-[#FAF8F5] hover:border-[#C68B2C]/50 disabled:opacity-40 transition-colors cursor-pointer"
            >
              {showVerify || !factsConfirmed ? 'Thu gọn xác minh' : 'Thông tin hợp đồng'}
            </button>

            <button
              type="button"
              disabled={!canAnalyze || isBusy}
              onClick={onAnalyze}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-xs font-semibold bg-[#16325C] text-white hover:bg-[#1E437A] shadow-sm disabled:opacity-40 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
            >
              {isBusy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>
                {isBusy
                  ? 'Đang phân tích...'
                  : hasLastCheck
                    ? 'Phân tích lại'
                    : 'Phân tích hợp đồng'}
              </span>
            </button>
          </div>
        </div>

        {/* 9-Stage Architectural Docket Stepper */}
        <div className="overflow-x-auto thin-scroll pb-0.5">
          <div className="min-w-[960px] flex items-center justify-between gap-1">
            {PIPELINE_STEPS.map((step, idx) => {
              const isPast = idx < currentStepIndex;
              const isCurrent = idx === currentStepIndex;
              const stepStatus = getStepSemanticStatus(
                idx,
                currentStepIndex,
                factsConfirmed,
                scenario
              );
              const cfg = STATUS_CONFIG[stepStatus];

              return (
                <div key={step.id} className="flex items-center flex-1 last:flex-none">
                  <button
                    type="button"
                    onClick={() => onSelectStep(idx)}
                    aria-current={isCurrent ? 'step' : undefined}
                    className={`group relative flex items-center gap-2 px-2.5 py-1.5 rounded-xl border text-left transition-all duration-200 cursor-pointer whitespace-nowrap ${
                      isCurrent
                        ? 'bg-[#EEF4FF]/70 border-[#2563EB]/60 ring-2 ring-[#C68B2C]/25 text-[#141B29] shadow-xs'
                        : isPast
                        ? 'bg-white border-[#E6E2D8] text-[#1E293B] hover:border-[#C68B2C]/50 hover:bg-[#FAF8F5]'
                        : 'bg-[#FAF8F5] border-[#E6E2D8]/80 text-[#94A3B8] hover:text-[#475569] hover:border-[#CBD5E1]'
                    }`}
                  >
                    <span
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-mono font-semibold shrink-0 transition-colors ${
                        isCurrent
                          ? 'bg-[#16325C] text-white'
                          : isPast
                          ? 'bg-[#0F766E] text-white'
                          : 'bg-[#ECE8DF] text-[#64748B]'
                      }`}
                    >
                      {isCurrent && isBusy ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : isPast ? (
                        <Check className="w-3 h-3" aria-hidden="true" />
                      ) : (
                        <span className="tabular-nums">{String(idx + 1).padStart(2, '0')}</span>
                      )}
                    </span>

                    <div className="flex flex-col leading-tight">
                      <span
                        className={`text-xs font-medium ${
                          isCurrent
                            ? 'text-[#16325C] font-semibold'
                            : isPast
                            ? 'text-[#1E293B]'
                            : 'text-[#64748B]'
                        }`}
                      >
                        {step.shortLabel.replace(/^\d+\.\s*/, '')}
                      </span>
                      {isCurrent && (
                        <span
                          className="text-[10px] font-medium"
                          style={{ color: cfg.accentHex }}
                        >
                          {isBusy ? 'Đang chạy...' : cfg.label}
                        </span>
                      )}
                    </div>
                  </button>

                  {idx < PIPELINE_STEPS.length - 1 && (
                    <div className="relative flex-1 h-4 mx-1 flex items-center min-w-[14px]">
                      <div className="w-full h-[1.5px] bg-[#E6E2D8] overflow-hidden rounded-full">
                        <motion.div
                          initial={false}
                          animate={{
                            scaleX: isPast ? 1 : isCurrent && isBusy ? 0.65 : 0,
                          }}
                          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                          style={{ transformOrigin: 'left center' }}
                          className={`h-full w-full ${
                            isPast ? 'bg-[#0F766E]' : 'bg-[#2563EB]'
                          }`}
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
