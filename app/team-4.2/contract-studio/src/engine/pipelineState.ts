import type {
  AnalysisScenario,
  ExtractedFact,
  LegalVersionEntry,
  PipelineStepMeta,
  SemanticStatus,
} from "../types/contract";

export const PIPELINE_STEPS: PipelineStepMeta[] = [
  {
    id: "read_docs",
    index: 0,
    shortLabel: "1. Đọc tài liệu",
    title: "Đọc tài liệu hợp đồng & phụ lục",
    description:
      "Mở tệp hợp đồng chính, phụ lục đính kèm và phân rã từng điều khoản gốc.",
    defaultStatus: "processing",
  },
  {
    id: "verify_info",
    index: 1,
    shortLabel: "2. Xác minh",
    title: "Xác minh thông tin trích xuất",
    description:
      "Kiểm tra ngày ký, loại hợp đồng, các bên và dữ kiện lương/thử việc trước khi suy luận.",
    defaultStatus: "needs_confirmation",
  },
  {
    id: "detect_concepts",
    index: 2,
    shortLabel: "3. Concept",
    title: "Nhận diện concept pháp lý",
    description:
      "Đánh dấu đoạn điều khoản và gắn nhãn cầu nối như Thử việc, Tiền lương, Nghỉ phép.",
    defaultStatus: "processing",
  },
  {
    id: "contract_relations",
    index: 3,
    shortLabel: "4. Quan hệ HĐ",
    title: "Đọc quan hệ trong Contract Graph",
    description:
      "Làm sáng dẫn chiếu nội bộ và đường sửa đổi từ phụ lục tác động lên điều khoản gốc.",
    defaultStatus: "processing",
  },
  {
    id: "find_legal_basis",
    index: 4,
    shortLabel: "5. Căn cứ luật",
    title: "Truy vấn Legal Graph từ Concept",
    description:
      "Mở các node luật, nghị định hướng dẫn và làm sáng từng quan hệ được truy vấn.",
    defaultStatus: "processing",
  },
  {
    id: "select_version",
    index: 5,
    shortLabel: "6. Phiên bản",
    title: "Chọn phiên bản luật theo ngày ký",
    description:
      "Đối chiếu mốc thời gian hiệu lực để giữ phiên bản đang áp dụng và làm mờ bản hết hiệu lực.",
    defaultStatus: "completed",
  },
  {
    id: "compare_clauses",
    index: 6,
    shortLabel: "7. Đối chiếu",
    title: "Đối chiếu điều khoản & căn cứ luật",
    description:
      "Đặt trích đoạn hợp đồng cạnh điều luật và kiểm tra ngưỡng giá trị, điều kiện áp dụng.",
    defaultStatus: "issue",
  },
  {
    id: "recheck_missing",
    index: 7,
    shortLabel: "8. Kiểm tra lại",
    title: "Quét lại hợp đồng trước khi báo thiếu",
    description:
      "Nếu nghi thiếu nội dung bắt buộc, quay lại rà soát hợp đồng chính và phụ lục lần cuối.",
    defaultStatus: "insufficient_data",
  },
  {
    id: "generate_report",
    index: 8,
    shortLabel: "9. Báo cáo",
    title: "Tổng hợp báo cáo & đề xuất sửa",
    description:
      "Gom toàn bộ bằng chứng thành thẻ phát hiện; chọn thẻ để xem lại toàn bộ đường liên kết.",
    defaultStatus: "completed",
  },
];

export interface ActiveHighlightTrace {
  findingId: string | null;
  clauseIds: Set<string>;
  conceptIds: Set<string>;
  contractNodeIds: Set<string>;
  legalNodeIds: Set<string>;
  edgeIds: Set<string>;
  comparisonId: string | null;
}

export function buildHighlightTrace(
  scenario: AnalysisScenario,
  currentStepIndex: number,
  selectedFindingId: string | null,
): ActiveHighlightTrace {
  const trace: ActiveHighlightTrace = {
    findingId: selectedFindingId,
    clauseIds: new Set(),
    conceptIds: new Set(),
    contractNodeIds: new Set(),
    legalNodeIds: new Set(),
    edgeIds: new Set(),
    comparisonId: null,
  };

  for (const uid of scenario.activeUnitIds || []) {
    trace.clauseIds.add(uid);
    scenario.graphModel?.nodes
      .filter((n) => n.clauseId === uid)
      .forEach((n) => trace.contractNodeIds.add(n.id));
  }

  if (selectedFindingId) {
    const finding = scenario.findings.find((f) => f.id === selectedFindingId);
    if (finding) {
      trace.clauseIds.add(finding.contractClauseId);
      trace.conceptIds.add(finding.conceptId);
      finding.relatedContractNodeIds.forEach((id) =>
        trace.contractNodeIds.add(id),
      );
      finding.relatedLegalNodeIds.forEach((id) => trace.legalNodeIds.add(id));
      finding.relatedEdgeIds.forEach((id) => trace.edgeIds.add(id));
      trace.comparisonId = finding.comparisonId ?? null;
      return trace;
    }
  }

  // Step-driven automatic highlights when no single finding is locked
  if (currentStepIndex === 2) {
    // Concept detection step: highlight concepts & tagged clauses
    scenario.concepts.forEach((c) => {
      trace.conceptIds.add(c.id);
      c.clauseIds.forEach((cid) => trace.clauseIds.add(cid));
    });
  } else if (currentStepIndex === 3) {
    // Contract relations step: highlight internal refs and addendum amends
    scenario.contractEdges
      .filter((e) => e.kind !== "parent_child")
      .forEach((e) => {
        trace.edgeIds.add(e.id);
        trace.contractNodeIds.add(e.from);
        trace.contractNodeIds.add(e.to);
      });
  } else if (currentStepIndex === 4) {
    // Legal basis lookup: highlight queried legal edges & connected concepts
    scenario.legalEdges
      .filter((e) => e.isQueried)
      .forEach((e) => {
        trace.edgeIds.add(e.id);
        trace.legalNodeIds.add(e.from);
        trace.legalNodeIds.add(e.to);
      });
    scenario.concepts.forEach((c) => trace.conceptIds.add(c.id));
  } else if (currentStepIndex === 7) {
    // Recheck missing: highlight clauses scanned during recheck
    scenario.recheckProbes.forEach((p) => {
      p.scannedClauses.forEach((cid) => trace.clauseIds.add(cid));
    });
  }

  return trace;
}

export function getStepSemanticStatus(
  stepIndex: number,
  currentStepIndex: number,
  factsConfirmed: boolean,
  scenario: AnalysisScenario,
): SemanticStatus {
  if (stepIndex > currentStepIndex) {
    return "processing";
  }
  if (stepIndex === 1 && !factsConfirmed) {
    return "needs_confirmation";
  }
  if (stepIndex < currentStepIndex) {
    return "completed";
  }

  if (scenario.isBusy) return "processing";
  const step = PIPELINE_STEPS[stepIndex];
  if (step?.id === "compare_clauses") {
    const hasConflict = scenario.findings.some((f) => f.status === "conflict");
    if (hasConflict) return "conflict";
    const hasIssue = scenario.findings.some((f) => f.status === "issue");
    if (hasIssue) return "issue";
  }
  if (step?.id === "recheck_missing") {
    const hasInsufficient = scenario.recheckProbes.some(
      (p) => p.finalStatus === "insufficient_data",
    );
    if (hasInsufficient) return "insufficient_data";
  }
  return step?.defaultStatus ?? "processing";
}

export interface ComparisonGaugeRatios {
  contractPercent: number;
  legalPercent: number;
}

/**
 * Extracts normalized 0-100 gauge bar widths from contract vs legal numeric strings
 * (e.g., "75%" vs "85%", "90 ngày" vs "60 ngày") for animated threshold comparison.
 */
export function computeComparisonRatios(
  contractValue: string,
  legalThreshold: string,
): ComparisonGaugeRatios | null {
  const cMatch = /(\d+(?:[.,]\d+)?)/.exec(contractValue);
  const lMatch = /(\d+(?:[.,]\d+)?)/.exec(legalThreshold);
  if (!cMatch || !lMatch) return null;

  const cNum = Number(cMatch[1].replace(",", "."));
  const lNum = Number(lMatch[1].replace(",", "."));
  if (
    !Number.isFinite(cNum) ||
    !Number.isFinite(lNum) ||
    (cNum <= 0 && lNum <= 0)
  ) {
    return null;
  }

  const scaleMax =
    contractValue.includes("%") && legalThreshold.includes("%")
      ? 100
      : Math.max(cNum, lNum) * 1.15;

  return {
    contractPercent: Math.min(
      100,
      Math.max(8, Math.round((cNum / scaleMax) * 100)),
    ),
    legalPercent: Math.min(
      100,
      Math.max(8, Math.round((lNum / scaleMax) * 100)),
    ),
  };
}

export interface SubPhaseDef {
  id: string;
  num: string;
  label: string;
  targetMs: number;
}
export function getSubPhasesForStep(_stepIndex: number): SubPhaseDef[] {
  return [];
}

export type Step1AssemblyStage =
  "folio_scan" | "graph_build" | "docking_left" | "docked";

/**
 * Pure phase selector for Step 1 (Reading contract -> building Contract Graph in center -> docking left).
 */
export interface ScreeningParticle {
  id: string;
  index: number;
  batchIndex: number;
  group: "relevant" | "excluded" | "unknown";
  discoveredAtMs: number;
  filteredAtMs: number;
  centerX: number;
  centerY: number;
  splitX: number;
  splitY: number;
  radius: number;
  driftX: number;
  driftY: number;
  delay: number;
}

/**
 * Generates deterministic Concept-grouped coordinates and staggered discovery/filter timings
 * for the Legal Screening dot cloud:
 * - Step 5: each particle appears only once its Concept query finds it (`discoveredAtMs`)
 * - Step 6: after all candidates gather, each dot evaluates sequentially (`filteredAtMs`):
 *   excluded dots drop downward into `Hết hiệu lực / Loại`, relevant dots rise into `Hiệu lực · Phù hợp`.
 */
export interface StepChoreographyState {
  assemblyStage: Step1AssemblyStage;
  visibleContractCount: number;
  visibleFactCount: number;
  visibleConceptCount: number;
  activeRelationPhase: "internal_ref" | "addendum_amends" | "all";
  activeQueryConceptIndex: number | null;
  discoveredParticleCount: number;
  allParticlesDiscovered: boolean;
  filteringStarted: boolean;
  filteringComplete: boolean;
  filteredParticleCount: number;
  keptParticleCount: number;
  droppedParticleCount: number;
  visibleLegalCount: number;
  activeComparisonIndex: number;
  activeRecheckClauseCount: number;
  activeSubPhaseId: string;
}

/**
 * Pure choreography solver translating (stepIndex, stepElapsedMs, scenario, particles)
 * into deterministic micro-stage counts and active highlights across all 9 steps.
 */
