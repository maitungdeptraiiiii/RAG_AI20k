import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { FilePlus2, FileText } from 'lucide-react';
import type {
  ActiveHighlightTrace,
  StepChoreographyState,
} from '../engine/pipelineState';
import type { AnalysisScenario, DocumentClause } from '../types/contract';
import { STATUS_CONFIG } from './StatusBadge';

interface DocumentPanelProps {
  scenario: AnalysisScenario;
  currentStepIndex: number;
  choreography?: StepChoreographyState;
  trace: ActiveHighlightTrace;
  onClauseClick: (clauseId: string) => void;
}

function renderHighlightedText(
  text: string,
  phrases: string[] | undefined,
  isHighlightedClause: boolean
) {
  if (!phrases || phrases.length === 0) {
    return text;
  }

  const escaped = phrases
    .filter((p) => p.trim().length > 0)
    .map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (escaped.length === 0) return text;

  const regex = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(regex);

  return parts.map((part, i) => {
    const matched = phrases.some((p) => p.toLowerCase() === part.toLowerCase());
    if (!matched) return <span key={i}>{part}</span>;
    return (
      <mark
        key={i}
        className={`rounded-xs px-1 py-0.5 transition-colors duration-200 ${
          isHighlightedClause
            ? 'bg-[#FDE68A]/70 text-stone-950 font-medium'
            : 'bg-[#EEF2F6] text-[#1E3A5F] font-medium'
        }`}
      >
        {part}
      </mark>
    );
  });
}

export function DocumentPanel({
  scenario,
  currentStepIndex,
  choreography,
  trace,
  onClauseClick,
}: DocumentPanelProps) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const clauseRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    if (trace.clauseIds.size === 1) {
      const targetId = Array.from(trace.clauseIds)[0];
      const el = clauseRefs.current[targetId];
      const container = scrollContainerRef.current;
      if (el && container) {
        const elRect = el.getBoundingClientRect();
        const cRect = container.getBoundingClientRect();
        const offsetTop = elRect.top - cRect.top + container.scrollTop;
        container.scrollTo({
          top: Math.max(0, offsetTop - 20),
          behavior: 'smooth',
        });
      }
    }
  }, [trace.clauseIds]);

  const showConceptsOnClauses = currentStepIndex >= 2;
  const isScanningDocs = currentStepIndex === 0 || currentStepIndex === 2 || currentStepIndex === 7;
  const totalClauses = scenario.sections.reduce((acc, s) => acc + s.clauses.length, 0);
  const visibleConcepts =
    currentStepIndex === 2 && choreography
      ? scenario.concepts.slice(0, choreography.visibleConceptCount)
      : scenario.concepts;
  const visibleConceptIds = new Set(visibleConcepts.map((c) => c.id));
  const activeStep3ConceptId =
    currentStepIndex === 2 && visibleConcepts.length > 0
      ? visibleConcepts[visibleConcepts.length - 1].id
      : null;

  let runningClauseIndex = 0;

  return (
    <aside
      aria-label="Tài liệu hợp đồng và phụ lục"
      className="bg-white border border-stone-200 rounded-md flex flex-col h-full overflow-hidden"
    >
      <div className="px-4 py-3 border-b border-stone-200 flex items-center justify-between gap-3 bg-[#FAF9F6] shrink-0">
        <div className="min-w-0">
          <h2 className="font-serif text-[15px] font-semibold text-stone-900">
            Hồ sơ Hợp đồng &amp; Phụ lục
          </h2>
          <p className="text-xs text-stone-500 mt-0.5 tabular-nums">
            {scenario.sections.length} văn bản · {totalClauses} điều khoản trích xuất
          </p>
        </div>
        {isScanningDocs && (
          <span className="text-[11px] font-medium text-[#1E3A5F] shrink-0">
            {currentStepIndex === 7 ? 'Đang rà soát lại văn bản' : 'Đang đối chiếu văn bản'}
          </span>
        )}
      </div>

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto thin-scroll p-4 space-y-4 relative"
      >
        <AnimatePresence mode="popLayout">
          {scenario.sections.map((section, secIdx) => {
            const isAddendum = section.kind === 'addendum';
            return (
              <motion.div
                key={section.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.35,
                  delay: currentStepIndex === 0 ? secIdx * 0.2 : 0,
                  ease: [0.22, 1, 0.36, 1],
                }}
                className="border border-stone-200 rounded overflow-hidden bg-white"
              >
                {/* Document File Header */}
                <div
                  className={`px-3.5 py-2.5 border-b border-stone-200 flex items-center justify-between gap-2 ${
                    isAddendum ? 'bg-[#FDFBF7]' : 'bg-[#FAF9F6]'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {isAddendum ? (
                      <FilePlus2
                        className="w-4 h-4 text-[#92400E] shrink-0"
                        aria-hidden="true"
                      />
                    ) : (
                      <FileText
                        className="w-4 h-4 text-[#1E3A5F] shrink-0"
                        aria-hidden="true"
                      />
                    )}
                    <div className="min-w-0">
                      <div className="font-serif text-[13px] font-semibold text-stone-900 truncate">
                        {section.title}
                      </div>
                      <div className="text-[11px] text-stone-500 font-mono truncate tabular-nums">
                        {section.fileName}
                        {section.signedDate ? ` · Ký ${section.signedDate}` : ''}
                      </div>
                    </div>
                  </div>
                  <span className="text-[11px] font-medium text-stone-600 shrink-0">
                    {isAddendum ? 'Phụ lục' : 'Bản chính'}
                  </span>
                </div>

                {/* Clauses */}
                <div className="divide-y divide-stone-100">
                  {section.clauses.map((clause: DocumentClause, clIdx) => {
                    const flatIdx = runningClauseIndex++;
                    const attachedConcepts = scenario.concepts.filter(
                      (c) =>
                        clause.conceptIds.includes(c.id) &&
                        (currentStepIndex !== 2 || visibleConceptIds.has(c.id))
                    );
                    const isActiveStep3Clause =
                      activeStep3ConceptId !== null &&
                      attachedConcepts.some((c) => c.id === activeStep3ConceptId);
                    const isHighlighted =
                      trace.clauseIds.has(clause.id) || isActiveStep3Clause;
                    const recheckLimit = choreography?.activeRecheckClauseCount ?? totalClauses;
                    const isScannedByRecheck =
                      currentStepIndex === 7 && flatIdx < recheckLimit;
                    const isBeingRechecked =
                      isScannedByRecheck &&
                      (flatIdx === recheckLimit - 1 ||
                        scenario.recheckProbes.some((p) =>
                          p.scannedClauses.includes(clause.id)
                        ));

                    return (
                      <motion.button
                        key={clause.id}
                        ref={(el) => {
                          clauseRefs.current[clause.id] = el;
                        }}
                        type="button"
                        onClick={() => onClauseClick(clause.id)}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          duration: 0.25,
                          delay: currentStepIndex === 0 ? secIdx * 0.2 + clIdx * 0.08 : 0,
                        }}
                        className={`w-full text-left py-3 transition-colors duration-150 relative cursor-pointer ${
                          clause.parentClauseId ? 'pl-7 pr-3.5 bg-[#FAF9F6]/40' : 'px-3.5'
                        } ${
                          isHighlighted
                            ? 'bg-[#F3F6FA] ring-1 ring-inset ring-[#1E3A5F]/40'
                            : isBeingRechecked
                            ? 'bg-[#F4F5FA] ring-1 ring-inset ring-[#312E81]/30'
                            : 'hover:bg-[#FAF9F6]'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-semibold text-stone-900">
                            {clause.parentClauseId ? '↳ ' : ''}
                            {clause.code} — {clause.title}
                          </span>
                          {isBeingRechecked && (
                            <span className="text-[10px] font-medium text-[#312E81] shrink-0">
                              Đang rà soát lại
                            </span>
                          )}
                        </div>

                        <p className="text-[13px] leading-relaxed text-stone-700">
                          {renderHighlightedText(
                            clause.text,
                            showConceptsOnClauses &&
                              (currentStepIndex !== 2 || attachedConcepts.length > 0)
                              ? clause.highlightPhrases
                              : undefined,
                            isHighlighted
                          )}
                        </p>

                        {/* Clean typographic concept footnote (no pill clutter) */}
                        {showConceptsOnClauses && attachedConcepts.length > 0 && (
                          <div className="mt-2 pt-1.5 border-t border-stone-100 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-stone-500">
                            <span className="text-stone-400">Khái niệm liên kết:</span>
                            {attachedConcepts.map((c, idx) => {
                              const st = STATUS_CONFIG[c.status];
                              const conceptActive = trace.conceptIds.has(c.id);
                              return (
                                <span
                                  key={c.id}
                                  className={
                                    conceptActive ? 'font-semibold underline underline-offset-2' : 'font-medium'
                                  }
                                  style={{ color: conceptActive ? '#1E3A5F' : st.accentHex }}
                                >
                                  {c.label}
                                  {idx < attachedConcepts.length - 1 ? ' ·' : ''}
                                </span>
                              );
                            })}
                          </div>
                        )}
                      </motion.button>
                    );
                  })}
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </aside>
  );
}
