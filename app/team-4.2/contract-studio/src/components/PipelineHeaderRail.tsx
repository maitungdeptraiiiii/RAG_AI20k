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
      className="bg-white border-b border-stone-200 px-4 lg:px-8 py-3 relative overflow-hidden"
    >
      {isBusy && (
        <div className="absolute top-0 left-0 right-0 h-[2.5px] bg-stone-100 overflow-hidden">
          <motion.div
            className="h-full w-1/3 bg-gradient-to-r from-transparent via-[#1E3A5F] to-transparent"
            animate={{ x: ['-100%', '300%'] }}
            transition={{ duration: 1.3, repeat: Infinity, ease: 'easeInOut' }}
          />
        </div>
      )}

      <div className="max-w-[1520px] mx-auto flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 min-w-0 text-xs text-stone-600">
            <span className="font-semibold whitespace-nowrap shrink-0 text-[#1E3A5F] inline-flex items-center gap-1.5">
              {isBusy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {isBusy ? statusMessage || 'Đang xử lý...' : 'Hồ sơ phân tích thực tế'}
            </span>
            <span className="text-stone-300" aria-hidden="true">|</span>
            <span className="font-serif text-sm font-semibold text-stone-900 truncate">
              {scenario.title}
            </span>
            <span className="text-stone-300 hidden sm:inline" aria-hidden="true">·</span>
            <span className="text-stone-500 truncate hidden sm:inline">
              {scenario.subtitle}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              disabled={isBusy}
              onClick={onToggleVerify}
              className="px-3 py-1.5 rounded border border-stone-200 text-xs font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-40 transition-colors cursor-pointer"
            >
              {showVerify || !factsConfirmed ? 'Thu gọn xác minh' : 'Thông tin hợp đồng'}
            </button>

            <button
              type="button"
              disabled={!canAnalyze || isBusy}
              onClick={onAnalyze}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded text-xs font-semibold bg-[#1E3A5F] text-white hover:bg-[#162C49] disabled:opacity-40 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
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
                    className={`group relative flex items-center gap-2 px-2.5 py-1.5 rounded border text-left transition-colors duration-200 cursor-pointer whitespace-nowrap ${
                      isCurrent
                        ? 'bg-[#F5F7FA] border-[#1E3A5F] text-stone-900'
                        : isPast
                        ? 'bg-white border-stone-200 text-stone-800 hover:border-stone-300 hover:bg-stone-50'
                        : 'bg-[#FAF9F6] border-stone-200/80 text-stone-400 hover:text-stone-700 hover:border-stone-300'
                    }`}
                  >
                    <span
                      className={`w-5 h-5 rounded-sm flex items-center justify-center text-[11px] font-mono font-semibold shrink-0 transition-colors ${
                        isCurrent
                          ? 'bg-[#1E3A5F] text-white'
                          : isPast
                          ? 'bg-[#166534] text-white'
                          : 'bg-stone-200/80 text-stone-500'
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
                            ? 'text-stone-900 font-semibold'
                            : isPast
                            ? 'text-stone-800'
                            : 'text-stone-500'
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
                      <div className="w-full h-[1.5px] bg-stone-200 overflow-hidden">
                        <motion.div
                          initial={false}
                          animate={{
                            scaleX: isPast ? 1 : isCurrent && isBusy ? 0.65 : 0,
                          }}
                          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                          style={{ transformOrigin: 'left center' }}
                          className={`h-full w-full ${
                            isPast ? 'bg-[#166534]' : 'bg-[#1E3A5F]'
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
