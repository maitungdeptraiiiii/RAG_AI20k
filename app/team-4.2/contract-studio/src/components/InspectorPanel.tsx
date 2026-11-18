import { useState } from 'react';
import { motion } from 'motion/react';
import {
  ArrowLeftRight,
  CheckCircle2,
  ClipboardCheck,
  Scale,
  SearchCheck,
} from 'lucide-react';
import {
  PIPELINE_STEPS,
  getStepSemanticStatus,
  type ActiveHighlightTrace,
} from '../engine/pipelineState';
import type {
  AnalysisScenario,
  ComparisonDetail,
  ExtractedFact,
  FindingCard,
} from '../types/contract';
import { StatusBadge } from './StatusBadge';

interface InspectorPanelProps {
  scenario: AnalysisScenario;
  currentStepIndex: number;
  factsConfirmed: boolean;
  trace: ActiveHighlightTrace;
  selectedFinding: FindingCard | null;
  activeComparison: ComparisonDetail | null;
  onConfirmFacts: (editedFacts: ExtractedFact[]) => void;
  onSelectFinding: (findingId: string | null) => void;
  onJumpToGraph?: () => void;
}

export function InspectorPanel({
  scenario,
  currentStepIndex,
  factsConfirmed,
  trace,
  selectedFinding,
  activeComparison,
  onConfirmFacts,
  onSelectFinding,
  onJumpToGraph,
}: InspectorPanelProps) {
  const [draftFacts, setDraftFacts] = useState<ExtractedFact[]>(scenario.extractedFacts);

  // Keep draftFacts synced if scenario switches
  const [trackedScenarioId, setTrackedScenarioId] = useState(scenario.id);
  if (trackedScenarioId !== scenario.id) {
    setTrackedScenarioId(scenario.id);
    setDraftFacts(scenario.extractedFacts);
  }

  const currentStep = PIPELINE_STEPS[currentStepIndex] ?? PIPELINE_STEPS[0];
  const currentStepStatus = getStepSemanticStatus(
    currentStepIndex,
    currentStepIndex,
    factsConfirmed,
    scenario
  );

  const showVerificationTable = false;
  const showComparison = Boolean(activeComparison) && (currentStepIndex >= 6 || selectedFinding !== null);
  const showRecheckBox = currentStepIndex === 7 && scenario.recheckProbes.length > 0;
  const showFindings = currentStepIndex >= 6;

  const handleFactChange = (id: string, value: string) => {
    setDraftFacts((prev) => prev.map((f) => (f.id === id ? { ...f, value } : f)));
  };

  return (
    <aside
      aria-label="Tiến trình và kết quả"
      className="bg-white border border-stone-200 rounded-md flex flex-col h-full overflow-hidden"
    >
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-stone-200 bg-[#FAF9F6] flex items-center justify-between gap-2">
        <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-900">
          <ClipboardCheck className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
          <span>Tiến trình &amp; Kết quả</span>
        </div>

        {selectedFinding && (
          <div className="flex items-center gap-3 shrink-0">
            {onJumpToGraph && (
              <button
                type="button"
                onClick={onJumpToGraph}
                className="text-xs font-medium text-[#1E3A5F] hover:underline whitespace-nowrap cursor-pointer"
              >
                Xem trên đồ thị ↑
              </button>
            )}
            <button
              type="button"
              onClick={() => onSelectFinding(null)}
              className="text-xs font-medium text-stone-600 hover:text-stone-900 hover:underline whitespace-nowrap cursor-pointer"
            >
              Bỏ chọn
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto thin-scroll p-4 space-y-4">
          {/* Active Stage Banner */}
          <div className="rounded border border-stone-200 bg-[#FAF9F6] p-3">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="font-serif text-sm font-semibold text-stone-900 tabular-nums">
                Bước {currentStepIndex + 1}/9: {currentStep.title}
              </span>
              <StatusBadge status={currentStepStatus} compact />
            </div>
            <p className="text-xs text-stone-600 leading-relaxed">
              {currentStep.description}
            </p>
          </div>

          {/* Step 2: Interactive Verification Table */}
          {showVerificationTable && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded border border-[#D9C6A3] bg-[#FDFBF7] p-3.5 space-y-3"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-serif text-sm font-semibold text-stone-900">
                  Xác minh dữ kiện trích xuất
                </h3>
                <StatusBadge
                  status={factsConfirmed ? 'completed' : 'needs_confirmation'}
                  customLabel={factsConfirmed ? 'Đã xác nhận' : 'Cần xác nhận'}
                  compact
                />
              </div>

              <div className="bg-white border border-stone-200 rounded divide-y divide-stone-100">
                {draftFacts.map((fact) => (
                  <div
                    key={fact.id}
                    className="px-3 py-2 flex items-center justify-between gap-2"
                  >
                    <label
                      htmlFor={`fact-${fact.id}`}
                      className="text-xs text-stone-600 shrink-0 w-[42%]"
                    >
                      {fact.label}
                    </label>
                    {fact.editable ? (
                      <input
                        id={`fact-${fact.id}`}
                        type="text"
                        value={fact.value}
                        onChange={(e) => handleFactChange(fact.id, e.target.value)}
                        className="w-[58%] text-xs font-medium text-stone-900 bg-[#FAF9F6] border border-stone-200 rounded px-2 py-1 focus:outline-none focus:border-[#1E3A5F] tabular-nums"
                      />
                    ) : (
                      <span className="w-[58%] text-xs font-medium text-stone-900 text-right tabular-nums">
                        {fact.value}
                      </span>
                    )}
                  </div>
                ))}
              </div>

              <button
                type="button"
                onClick={() => onConfirmFacts(draftFacts)}
                className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded text-xs font-semibold bg-[#1E3A5F] text-white hover:bg-[#162C49] transition-colors cursor-pointer"
              >
                <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                <span>
                  {factsConfirmed
                    ? 'Cập nhật lại dữ kiện đã xác nhận'
                    : 'Xác nhận thông tin & Tiếp tục phân tích'}
                </span>
              </button>
            </motion.div>
          )}

          {/* Step 8: Recheck Missing Clauses */}
          {showRecheckBox && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded border border-[#C7CBE6] bg-[#F4F5FA] p-3.5 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-[#312E81]">
                  <SearchCheck className="w-4 h-4" aria-hidden="true" />
                  <span>Kiểm tra lại trước khi báo thiếu</span>
                </div>
                <StatusBadge status="insufficient_data" compact />
              </div>
              {scenario.recheckProbes.map((probe) => (
                <div key={probe.id} className="bg-white border border-stone-200 rounded p-2.5 text-xs space-y-1">
                  <div className="font-semibold text-stone-900">{probe.targetTopic}</div>
                  <p className="text-stone-600 leading-relaxed">{probe.scanResult}</p>
                </div>
              ))}
            </motion.div>
          )}

          {/* Step 7-8: Standalone Side-by-Side Clause vs Law Comparison */}
          {showComparison && activeComparison && currentStepIndex < 8 && (
            <motion.div
              key={activeComparison.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded border border-stone-200 bg-white overflow-hidden"
            >
              <div className="px-3.5 py-2 bg-[#FAF9F6] border-b border-stone-200 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-stone-900">
                  <ArrowLeftRight className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
                  <span>Đối chiếu: {activeComparison.conceptLabel}</span>
                </div>
                <StatusBadge status={activeComparison.verdict} compact />
              </div>

              <div className="grid grid-cols-2 divide-x divide-stone-200">
                <div className="p-3 space-y-1.5 bg-[#FAF9F6]/50">
                  <div className="text-[11px] font-semibold text-[#1E3A5F]">
                    {activeComparison.contractClauseCode}
                  </div>
                  <p className="text-xs text-stone-700 leading-relaxed">
                    {activeComparison.contractExcerpt}
                  </p>
                  <div className="pt-1.5 border-t border-stone-200">
                    <div className="text-[10px] text-stone-500">
                      {activeComparison.contractValueLabel}
                    </div>
                    <div className="text-xs font-mono font-semibold text-[#881337] tabular-nums">
                      {activeComparison.contractValue}
                    </div>
                  </div>
                </div>

                <div className="p-3 space-y-1.5 bg-[#F2F8F4]/40">
                  <div className="text-[11px] font-semibold text-[#166534]">
                    {activeComparison.legalCitation}
                  </div>
                  <p className="text-xs text-stone-700 leading-relaxed">
                    {activeComparison.legalExcerpt}
                  </p>
                  <div className="pt-1.5 border-t border-stone-200">
                    <div className="text-[10px] text-stone-500">
                      {activeComparison.legalThresholdLabel}
                    </div>
                    <div className="text-xs font-mono font-semibold text-[#166534] tabular-nums">
                      {activeComparison.legalThreshold}
                    </div>
                  </div>
                </div>
              </div>

              <div className="px-3.5 py-2.5 bg-[#FAF9F6] border-t border-stone-200 text-xs text-stone-700 leading-relaxed">
                <span className="font-semibold text-stone-900">Nhận định: </span>
                {activeComparison.reasoning}
              </div>
            </motion.div>
          )}

          {/* Executive Summary + Findings Report */}
          {showFindings ? (
            <div className="space-y-3.5">
              {currentStepIndex >= 8 && (
                <div className="rounded border border-stone-200 bg-[#FAF9F6] p-3.5">
                  <div className="flex items-center gap-1.5 font-serif text-sm font-semibold text-stone-900 mb-1.5">
                    <Scale className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
                    <span>Kết luận tổng quan hồ sơ</span>
                  </div>
                  <p className="text-xs text-stone-700 leading-relaxed">
                    {scenario.summaryText}
                  </p>
                </div>
              )}

              <div className="flex items-center justify-between">
                <h3 className="font-serif text-sm font-semibold text-stone-900">
                  Các phát hiện &amp; Đề xuất sửa ({scenario.findings.length})
                </h3>
                <span className="text-[11px] text-stone-500">
                  Chọn mục để đối chiếu trên đồ thị
                </span>
              </div>

              <div className="divide-y divide-stone-200 border border-stone-200 rounded bg-white overflow-hidden">
                {scenario.findings.map((finding) => {
                  const isSelected = trace.findingId === finding.id;
                  const inlineComparison = isSelected
                    ? scenario.comparisons.find((c) => c.id === finding.comparisonId)
                    : null;

                  return (
                    <button
                      key={finding.id}
                      type="button"
                      onClick={() =>
                        onSelectFinding(isSelected ? null : finding.id)
                      }
                      className={`w-full text-left p-3.5 transition-colors duration-150 cursor-pointer block ${
                        isSelected
                          ? 'bg-[#F3F6FA]'
                          : 'bg-white hover:bg-[#FAF9F6]'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5 text-[11px]">
                        <StatusBadge
                          status={finding.status}
                          customLabel={finding.severityLabel}
                          compact
                        />
                        <span className="font-mono text-stone-500 truncate">
                          {finding.contractClauseRef}
                        </span>
                      </div>

                      <div
                        className={`font-serif text-[14px] font-semibold leading-snug ${
                          isSelected ? 'text-[#1E3A5F]' : 'text-stone-900'
                        }`}
                      >
                        {finding.title}
                      </div>

                      <p className="text-xs text-stone-600 mt-1 leading-relaxed">
                        {finding.summary}
                      </p>

                      {inlineComparison && (
                        <div className="mt-2.5 rounded border border-stone-200 bg-white overflow-hidden">
                          <div className="grid grid-cols-2 divide-x divide-stone-200 text-[11px]">
                            <div className="p-2.5">
                              <div className="font-semibold text-[#1E3A5F]">
                                Hợp đồng ghi nhận
                              </div>
                              <div className="font-mono font-semibold text-[#881337] mt-0.5 tabular-nums">
                                {inlineComparison.contractValue}
                              </div>
                            </div>
                            <div className="p-2.5 bg-[#F2F8F4]/40">
                              <div className="font-semibold text-[#166534]">
                                Ngưỡng pháp luật
                              </div>
                              <div className="font-mono font-semibold text-[#166534] mt-0.5 tabular-nums">
                                {inlineComparison.legalThreshold}
                              </div>
                            </div>
                          </div>
                          <div className="px-2.5 py-2 bg-[#FAF9F6] border-t border-stone-200 text-[11px] text-stone-700">
                            {inlineComparison.reasoning}
                          </div>
                        </div>
                      )}

                      <div className="mt-2.5 pt-2 border-t border-stone-100 text-[11px] text-stone-600 space-y-1">
                        <div>
                          <span className="font-semibold text-stone-800">Căn cứ luật: </span>
                          <span className="text-[#166534] font-medium">
                            {finding.legalCitation}
                          </span>
                        </div>
                        <div>
                          <span className="font-semibold text-stone-800">Đề xuất sửa: </span>
                          <span>{finding.recommendation}</span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="rounded border border-stone-200 bg-[#FAF9F6] p-4 text-center text-xs text-stone-500 space-y-1">
              <div className="font-medium text-stone-700">
                Báo cáo chi tiết sẽ hiển thị từ Bước 7 (Đối chiếu) &amp; Bước 9 (Báo cáo)
              </div>
              <p>
                Kết quả xuất hiện khi máy chủ hoàn tất từng bước phân tích.
              </p>
            </div>
          )}
        </div>
    </aside>
  );
}
