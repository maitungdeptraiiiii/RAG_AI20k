import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowLeftRight,
  CalendarCheck2,
  Check,
  CheckCircle2,
  FileSearch,
  Filter,
  Loader2,
  Scale,
  SearchCheck,
} from 'lucide-react';
import {
  computeComparisonRatios,
  type ActiveHighlightTrace,
  type StepChoreographyState,
} from '../engine/pipelineState';
import type {
  AnalysisScenario,
  ExtractedFact,
} from '../types/contract';
import { STATUS_CONFIG, StatusBadge, StatusIcon } from './StatusBadge';

interface StageOutcomePanelProps {
  scenario: AnalysisScenario;
  currentStepIndex: number;
  choreography: StepChoreographyState;
  particleTotal: number;
  activeVersionIds: Set<string>;
  factsConfirmed: boolean;
  trace: ActiveHighlightTrace;
  onConfirmFacts: (editedFacts: ExtractedFact[]) => void;
  onSelectFinding: (findingId: string | null) => void;
  onJumpToDetails?: () => void;
}

export function StageOutcomePanel({
  scenario,
  currentStepIndex,
  choreography,
  particleTotal,
  activeVersionIds,
  factsConfirmed,
  trace,
  onConfirmFacts,
  onSelectFinding,
  onJumpToDetails,
}: StageOutcomePanelProps) {
  const [draftFacts, setDraftFacts] = useState<ExtractedFact[]>(scenario.extractedFacts);
  const [trackedId, setTrackedId] = useState(scenario.id);
  const [manualCompIdx, setManualCompIdx] = useState<number | null>(null);

  if (trackedId !== scenario.id) {
    setTrackedId(scenario.id);
    setDraftFacts(scenario.extractedFacts);
    setManualCompIdx(null);
  }

  const handleFactChange = (id: string, value: string) => {
    setDraftFacts((prev) => prev.map((f) => (f.id === id ? { ...f, value } : f)));
  };

  const selectedFinding = scenario.findings.find((f) => f.id === trace.findingId) ?? null;
  const activeCompIdx =
    manualCompIdx !== null
      ? Math.min(scenario.comparisons.length - 1, manualCompIdx)
      : choreography.activeComparisonIndex;
  const spotlightComparison = selectedFinding?.comparisonId
    ? scenario.comparisons.find((c) => c.id === selectedFinding.comparisonId)
    : scenario.comparisons[activeCompIdx] ?? scenario.comparisons[0];

  const allClauses = scenario.sections.flatMap((sec) =>
    sec.clauses.map((cl) => ({
      ...cl,
      sectionLabel: sec.kind === 'addendum' ? 'Phụ lục' : 'HĐ gốc',
    }))
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between gap-1.5 text-xs font-semibold text-stone-800 pb-2 border-b border-stone-200 mb-2.5">
        <div className="flex items-center gap-1.5">
          <Scale className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
          <span>Kết quả &amp; Trạng thái bước</span>
        </div>
        {currentStepIndex >= 6 && onJumpToDetails && (
          <button
            type="button"
            onClick={onJumpToDetails}
            className="text-[11px] font-medium text-[#1E3A5F] hover:underline cursor-pointer whitespace-nowrap"
          >
            Xem chi tiết ↓
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto thin-scroll pr-0.5">
        <AnimatePresence mode="wait">
          {/* STEP 1: Unfolding files -> sequential Contract Graph extraction */}
          {currentStepIndex === 0 && (
            <motion.div
              key="stage-step-0"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              transition={{ duration: 0.22 }}
              className="rounded border border-stone-200 bg-[#FAF9F6] p-3 space-y-2.5"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-stone-900">
                  {choreography.assemblyStage === 'folio_scan'
                    ? 'Đang mở hồ sơ văn bản'
                    : choreography.assemblyStage === 'graph_build'
                    ? 'Đang tách Contract Graph'
                    : 'Neo đồ thị hợp đồng'}
                </span>
                <span className="text-[11px] font-mono font-semibold text-[#1E3A5F] tabular-nums">
                  {choreography.visibleContractCount}/{scenario.contractNodes.length} nút
                </span>
              </div>
              <div className="divide-y divide-stone-200 border border-stone-200 rounded bg-white">
                {scenario.sections.map((sec, idx) => (
                  <div key={sec.id} className="px-2.5 py-2 space-y-1.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-stone-800 truncate">{sec.title}</span>
                      <span className="font-mono text-[11px] text-[#1E3A5F] shrink-0 tabular-nums">
                        {sec.clauses.length} điều
                      </span>
                    </div>
                    <div className="h-[2px] w-full bg-stone-100 overflow-hidden">
                      <motion.div
                        initial={{ scaleX: 0 }}
                        animate={{
                          scaleX:
                            choreography.assemblyStage === 'folio_scan'
                              ? 0.45
                              : 1,
                        }}
                        transition={{ duration: 0.65, delay: idx * 0.14 }}
                        style={{ transformOrigin: 'left' }}
                        className={`h-full ${
                          sec.kind === 'addendum' ? 'bg-[#881337]' : 'bg-[#1E3A5F]'
                        }`}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="text-[11px] text-stone-500 leading-relaxed">
                {choreography.assemblyStage === 'folio_scan'
                  ? 'Đang quét cấu trúc chương, điều và tệp phụ lục đính kèm...'
                  : choreography.assemblyStage === 'graph_build'
                  ? 'Khởi tạo lần lượt các node điều khoản ở trung tâm.'
                  : 'Thu gọn đồ thị hợp đồng về cột trái để mở không gian đối chiếu.'}
              </div>
            </motion.div>
          )}

          {/* STEP 2: Interactive Verification Gate */}
          {currentStepIndex === 1 && <motion.div initial={{opacity:0}} animate={{opacity:1}} className="text-xs p-3 border border-stone-200 rounded bg-stone-50">Xác minh thông tin tại bảng phía trên. Các dữ kiện chỉ được xác nhận sau khi máy chủ chấp nhận.</motion.div>}

          {/* STEP 3: Sequential Concept Extraction */}
          {currentStepIndex === 2 && (
            <motion.div
              key="stage-step-2"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              className="rounded border border-stone-200 bg-[#FAF9F6] p-3 space-y-2.5"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-stone-900">
                  Nhận diện Concept cầu nối
                </span>
                <span className="text-[11px] font-mono font-semibold text-[#1E3A5F] tabular-nums">
                  {choreography.visibleConceptCount}/{scenario.concepts.length} chủ đề
                </span>
              </div>

              <div className="divide-y divide-stone-200 border border-stone-200 rounded bg-white">
                {scenario.concepts
                  .slice(0, choreography.visibleConceptCount)
                  .map((c, idx) => {
                    const isLatest = idx === choreography.visibleConceptCount - 1;
                    return (
                      <motion.div
                        key={c.id}
                        initial={{ opacity: 0, x: 6 }}
                        animate={{ opacity: 1, x: 0 }}
                        className={`px-2.5 py-2 flex items-center justify-between gap-2 text-xs ${
                          isLatest ? 'bg-[#F3F6FA]' : 'bg-white'
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="font-semibold text-stone-900 truncate">
                            {idx + 1}. {c.label}
                          </div>
                          <div className="text-[10px] text-stone-500 truncate">
                            {c.category} · {c.clauseIds.length} đoạn điều khoản
                          </div>
                        </div>
                        <Check className="w-3.5 h-3.5 text-[#166534] shrink-0" aria-hidden="true" />
                      </motion.div>
                    );
                  })}
              </div>
            </motion.div>
          )}

          {/* STEP 4: Contract Relations (Internal Ref -> Addendum Overrides Root) */}
          {currentStepIndex === 3 && (
            <motion.div
              key="stage-step-3"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              className="rounded border border-stone-200 bg-[#FAF9F6] p-3 space-y-2.5"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-stone-900">
                  Truy vết quan hệ Hợp đồng
                </span>
                <StatusBadge status="processing" compact />
              </div>

              <div className="space-y-1.5">
                {scenario.contractEdges
                  .filter((e) => e.kind !== 'parent_child')
                  .map((edge) => {
                    const isAmend = edge.kind === 'addendum_amends';
                    const isFocused =
                      choreography.activeRelationPhase === 'all' ||
                      (choreography.activeRelationPhase === 'internal_ref' && !isAmend) ||
                      (choreography.activeRelationPhase === 'addendum_amends' && isAmend);

                    return (
                      <motion.div
                        key={edge.id}
                        animate={{ opacity: isFocused ? 1 : 0.45 }}
                        className={`rounded border px-2.5 py-2 text-xs transition-colors ${
                          isAmend
                            ? 'bg-[#FDF2F4] border-[#DFB4BF] text-[#881337]'
                            : 'bg-[#FDF8EE] border-[#E7D3AD] text-[#92400E]'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold">{edge.label}</span>
                          {isFocused && (
                            <span className="text-[10px] font-mono uppercase">Đang soi</span>
                          )}
                        </div>
                        <div className="text-[11px] opacity-85 mt-0.5">
                          {isAmend
                            ? 'Phụ lục ghi đè giá trị điều khoản hợp đồng gốc'
                            : 'Điều khoản dẫn chiếu chéo nội bộ'}
                        </div>
                      </motion.div>
                    );
                  })}
              </div>
            </motion.div>
          )}

          {/* STEP 5: Live Per-Concept Candidate Discovery into Particle Cloud */}
          {currentStepIndex === 4 && (
            <motion.div
              key="stage-step-4"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              className="rounded border border-stone-200 bg-[#FAF9F6] p-3 space-y-2.5"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-stone-900">
                  Tìm căn cứ theo concept
                </span>
                <span className="text-[11px] font-mono font-semibold text-[#1E3A5F] tabular-nums">
                  {choreography.discoveredParticleCount}/{particleTotal} hạt
                </span>
              </div>

              <div className="divide-y divide-stone-200 border border-stone-200 rounded bg-white">
                {scenario.concepts.map((c, idx) => {
                  const isSearchingNow = choreography.activeQueryConceptIndex === idx;
                  const isDoneBatch =
                    choreography.allParticlesDiscovered ||
                    (choreography.activeQueryConceptIndex !== null &&
                      idx < choreography.activeQueryConceptIndex);
                  const batchCount = (scenario.candidates||[]).filter(p=>p.conceptId===c.id).length;

                  return (
                    <div
                      key={c.id}
                      className={`px-2.5 py-2 flex items-center justify-between gap-2 text-xs transition-colors ${
                        isSearchingNow ? 'bg-[#EEF3F9]' : 'bg-white'
                      }`}
                    >
                      <div className="min-w-0">
                        <div
                          className={`truncate font-medium ${
                            isSearchingNow || isDoneBatch ? 'text-stone-900' : 'text-stone-400'
                          }`}
                        >
                          {idx + 1}. {c.label}
                        </div>
                        <div className="text-[10px] text-stone-500">
                          {isDoneBatch
                            ? `Đã gom +${batchCount} ứng viên điều luật`
                            : isSearchingNow
                            ? 'Đang truy vấn văn bản liên quan...'
                            : 'Chờ lượt truy vấn'}
                        </div>
                      </div>
                      {isDoneBatch ? (
                        <Check className="w-3.5 h-3.5 text-[#166534] shrink-0" aria-hidden="true" />
                      ) : isSearchingNow ? (
                        <Loader2
                          className="w-3.5 h-3.5 text-[#1E3A5F] animate-spin shrink-0"
                          aria-hidden="true"
                        />
                      ) : (
                        <span className="text-[10px] font-mono text-stone-300">···</span>
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="text-[11px] text-stone-600 leading-relaxed">
                {choreography.allParticlesDiscovered
                  ? `Đã tìm đủ ${particleTotal} ứng viên trong đám mây. Sẵn sàng sang Bước 6 để lọc hiệu lực.`
                  : 'Tìm được căn cứ nào sẽ nạp từng chấm ứng viên vào đám mây trước khi lọc.'}
              </div>
            </motion.div>
          )}

          {/* STEP 6: Dot-by-Dot Temporal Filtering -> Only When Done Pop Legal Graph */}
          {currentStepIndex === 5 && (
            <motion.div
              key="stage-step-5"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              className="rounded border border-stone-200 bg-[#FAF9F6] p-3 space-y-2.5"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-stone-900">
                  <CalendarCheck2 className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
                  <span>Lọc hiệu lực theo ngày ký</span>
                </div>
                <span className="text-[11px] font-mono font-semibold text-[#166534] tabular-nums">
                  {choreography.filteredParticleCount}/{particleTotal}
                </span>
              </div>

              {/* Real-time kept vs dropped particle breakdown */}
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded border border-[#BBD7C5] bg-[#F2F8F4] px-2.5 py-1.5">
                  <div className="text-[10px] text-[#166534] font-medium">Giữ · Hiệu lực</div>
                  <div className="text-sm font-mono font-bold text-[#166534] tabular-nums">
                    {choreography.keptParticleCount} hạt
                  </div>
                </div>
                <div className="rounded border border-stone-200 bg-white px-2.5 py-1.5">
                  <div className="text-[10px] text-stone-500 font-medium">Đẩy xuống · Loại</div>
                  <div className="text-sm font-mono font-bold text-stone-600 tabular-nums">
                    {choreography.droppedParticleCount} hạt
                  </div>
                </div>
              </div>

              {/* Filter pipeline stage status */}
              <div className="rounded border border-stone-200 bg-white px-2.5 py-2 text-[11px] flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-stone-700 font-medium">
                  <Filter className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
                  {!choreography.filteringStarted
                    ? `Khóa mốc ${scenario.signingDateIso.split('-').reverse().join('/')}`
                    : !choreography.filteringComplete
                    ? 'Đang chuyển từng hạt không phù hợp xuống dưới...'
                    : `Đã lọc xong → Mở ${choreography.visibleLegalCount}/${scenario.legalNodes.length} nút Legal Graph`}
                </span>
              </div>

              <div className="divide-y divide-stone-200 border border-stone-200 rounded bg-white">
                {scenario.legalVersions.map((ver) => {
                  const isActive = activeVersionIds.has(ver.id);
                  return (
                    <div
                      key={ver.id}
                      className={`px-2.5 py-1.5 flex items-center justify-between gap-2 text-[11px] ${
                        choreography.filteringComplete && !isActive ? 'opacity-50' : 'opacity-100'
                      }`}
                    >
                      <span className="font-mono font-semibold text-stone-900 truncate">
                        {ver.documentCode}
                      </span>
                      <span
                        className={`font-semibold shrink-0 ${
                          !choreography.filteringStarted
                            ? 'text-stone-400'
                            : isActive
                            ? 'text-[#166534]'
                            : 'text-stone-400'
                        }`}
                      >
                        {!choreography.filteringStarted
                          ? 'Chờ lọc'
                          : isActive
                          ? 'Áp dụng'
                          : 'Đẩy xuống'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}

          {/* STEP 7: Side-by-Side Threshold Gauge Comparator with Rule Switcher */}
          {currentStepIndex === 6 && spotlightComparison && (
            <motion.div
              key="stage-step-6"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="rounded border border-stone-200 bg-white overflow-hidden"
            >
              <div className="px-3 py-2 bg-[#FAF9F6] border-b border-stone-200 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-stone-900 truncate">
                  <ArrowLeftRight className="w-3.5 h-3.5 text-[#1E3A5F] shrink-0" aria-hidden="true" />
                  <span className="truncate">{spotlightComparison.conceptLabel}</span>
                </div>
                <StatusBadge status={spotlightComparison.verdict} compact />
              </div>

              {scenario.comparisons.length > 1 && (
                <div className="px-3 pt-2 flex items-center gap-1 border-b border-stone-100 pb-2">
                  {scenario.comparisons.map((cmp, idx) => (
                    <button
                      key={cmp.id}
                      type="button"
                      onClick={() => setManualCompIdx(idx)}
                      className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors cursor-pointer ${
                        idx === activeCompIdx
                          ? 'bg-[#1E3A5F] text-white font-semibold'
                          : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                      }`}
                    >
                      #{idx + 1} {cmp.conceptLabel.split(' ')[0]}
                    </button>
                  ))}
                </div>
              )}

              <div className="p-3 space-y-2.5 text-xs">
                {(() => {
                  const gauge = computeComparisonRatios(
                    spotlightComparison.contractValue,
                    spotlightComparison.legalThreshold
                  );
                  return (
                    <div className="space-y-2">
                      <div className="rounded bg-[#FDF2F4] border border-[#DFB4BF] p-2 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[10px] text-stone-600">
                            {spotlightComparison.contractValueLabel}
                          </span>
                          <span className="font-mono font-semibold text-[#881337] tabular-nums">
                            {spotlightComparison.contractValue}
                          </span>
                        </div>
                        {gauge && (
                          <div className="h-1.5 w-full bg-[#F5D0D8] overflow-hidden rounded-full">
                            <motion.div
                              key={`c-${spotlightComparison.id}`}
                              initial={{ scaleX: 0 }}
                              animate={{ scaleX: 1 }}
                              transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                              style={{
                                width: `${gauge.contractPercent}%`,
                                transformOrigin: 'left',
                              }}
                              className="h-full bg-[#881337]"
                            />
                          </div>
                        )}
                      </div>

                      <div className="rounded bg-[#F2F8F4] border border-[#BBD7C5] p-2 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[10px] text-stone-600">
                            {spotlightComparison.legalThresholdLabel}
                          </span>
                          <span className="font-mono font-semibold text-[#166534] tabular-nums">
                            {spotlightComparison.legalThreshold}
                          </span>
                        </div>
                        {gauge && (
                          <div className="h-1.5 w-full bg-[#D1E7D8] overflow-hidden rounded-full">
                            <motion.div
                              key={`l-${spotlightComparison.id}`}
                              initial={{ scaleX: 0 }}
                              animate={{ scaleX: 1 }}
                              transition={{ duration: 0.55, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
                              style={{
                                width: `${gauge.legalPercent}%`,
                                transformOrigin: 'left',
                              }}
                              className="h-full bg-[#166534]"
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                <p className="text-[11px] text-stone-700 leading-relaxed">
                  {spotlightComparison.reasoning}
                </p>
              </div>
            </motion.div>
          )}

          {/* STEP 8: Sequential Boomerang Clause-by-Clause Recheck */}
          {currentStepIndex === 7 && (
            <motion.div
              key="stage-step-7"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="rounded border border-[#C7CBE6] bg-[#F4F5FA] p-3 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-[#312E81]">
                  <SearchCheck className="w-4 h-4" aria-hidden="true" />
                  <span>Quét ngược toàn văn bản</span>
                </div>
                <span className="text-[11px] font-mono font-semibold text-[#312E81] tabular-nums">
                  {choreography.activeRecheckClauseCount}/{allClauses.length} điều
                </span>
              </div>

              <div className="bg-white border border-stone-200 rounded divide-y divide-stone-100">
                {allClauses.map((cl, idx) => {
                  const scanned = idx < choreography.activeRecheckClauseCount;
                  const scanningNow = idx === choreography.activeRecheckClauseCount - 1;
                  return (
                    <div
                      key={cl.id}
                      className={`px-2.5 py-1.5 flex items-center justify-between gap-2 text-[11px] ${
                        scanningNow ? 'bg-[#EEF0FA]' : 'bg-white'
                      }`}
                    >
                      <span className="truncate font-medium text-stone-800">
                        {cl.code} ({cl.sectionLabel})
                      </span>
                      <span className="font-mono text-[10px] shrink-0 text-[#312E81]">
                        {scanned ? 'Đã rà' : 'Chờ quét'}
                      </span>
                    </div>
                  );
                })}
              </div>

              {choreography.activeRecheckClauseCount >= allClauses.length &&
                scenario.recheckProbes[0] && (
                  <div className="bg-white border border-stone-200 rounded p-2 text-[11px] text-stone-600 leading-relaxed">
                    {scenario.recheckProbes[0].scanResult}
                  </div>
                )}
            </motion.div>
          )}

          {/* STEP 9: Interactive Outcome Bundle List */}
          {currentStepIndex === 8 && (
            <motion.div
              key="stage-step-8"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-1.5"
            >
              <div className="flex items-center justify-between text-[11px] text-stone-500 mb-1">
                <span>Chọn phát hiện để đối chiếu đường liên kết</span>
                <span className="font-mono font-semibold text-stone-800 tabular-nums">
                  {scenario.findings.length} kết quả
                </span>
              </div>

              <div className="divide-y divide-stone-200 border border-stone-200 rounded bg-white overflow-hidden">
                {scenario.findings.map((finding, idx) => {
                  const isSelected = trace.findingId === finding.id;
                  const st = STATUS_CONFIG[finding.status];
                  return (
                    <motion.button
                      key={finding.id}
                      type="button"
                      onClick={() => onSelectFinding(isSelected ? null : finding.id)}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: idx * 0.05 }}
                      className={`w-full text-left px-3 py-2 transition-colors cursor-pointer ${
                        isSelected
                          ? 'bg-[#F3F6FA]'
                          : 'bg-white hover:bg-[#FAF9F6]'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 text-[11px]">
                        <span
                          className="inline-flex items-center gap-1 font-semibold"
                          style={{ color: st.accentHex }}
                        >
                          <StatusIcon status={finding.status} className="w-3 h-3" />
                          <span>{st.label}</span>
                        </span>
                        <span className="font-mono text-stone-500 truncate">
                          {finding.contractClauseRef.split('→')[0]}
                        </span>
                      </div>
                      <div
                        className={`text-xs font-semibold mt-0.5 line-clamp-2 ${
                          isSelected ? 'text-[#1E3A5F]' : 'text-stone-900'
                        }`}
                      >
                        {finding.title}
                      </div>
                    </motion.button>
                  );
                })}
              </div>

              {selectedFinding ? (
                <div className="rounded bg-[#FAF9F6] border border-stone-200 p-2 text-[11px] text-stone-700 flex items-start gap-1.5">
                  <Scale className="w-3.5 h-3.5 text-[#166534] shrink-0 mt-0.5" aria-hidden="true" />
                  <span>{selectedFinding.legalCitation}</span>
                </div>
              ) : (
                <div className="rounded bg-[#FAF9F6] border border-stone-200 p-2 text-[11px] text-stone-500 flex items-center gap-1.5">
                  <FileSearch className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                  <span>Nhấp vào một phát hiện để soi toàn bộ đường dẫn lập luận.</span>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

