import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, LayoutGroup, motion } from 'motion/react';
import {
  ArrowRight,
  BookOpen,
  CalendarClock,
  Check,
  CheckCircle2,
  FileCode2,
  FileText,
  Filter,
  GitBranch,
  Link2,
  Scale,
} from 'lucide-react';
import {
  buildContractGraphModel,
  filterContractGraphForStep,
  resolve7NodeSelectionTrace,
  type SevenNodeSelection,
} from '../engine/contractGraph';
import {
  getSubPhasesForStep,
  type ActiveHighlightTrace,
  type ScreeningParticle,
  type StepChoreographyState,
} from '../engine/pipelineState';
import type {
  AnalysisScenario,
  ContractGraph7Node,
  ExtractedFact,
} from '../types/contract';
import {
  CenteredContractGraphTree,
  ContractUnitInspectorDrawer,
} from './ContractGraphExplorer';
import { STATUS_CONFIG, StatusIcon } from './StatusBadge';
import { StageOutcomePanel } from './StageOutcomePanel';

interface DualGraphCanvasProps {
  scenario: AnalysisScenario;
  currentStepIndex: number;
  stepElapsedMs: number;
  choreography: StepChoreographyState;
  screeningParticles: ScreeningParticle[];
  activeVersionIds: Set<string>;
  factsConfirmed: boolean;
  trace: ActiveHighlightTrace;
  onJumpToSubPhase: (targetMs: number) => void;
  onSelectConcept: (conceptId: string) => void;
  onSelectContractNode: (nodeId: string, clauseId?: string) => void;
  onSelectLegalNode: (nodeId: string) => void;
  onConfirmFacts: (editedFacts: ExtractedFact[]) => void;
  onSelectFinding: (findingId: string | null) => void;
  onJumpToDetails?: () => void;
  onOpenReportCanvas?: () => void;
  isGeneratingReport?: boolean;
  hasNarrativeReport?: boolean;
}

interface Point {
  left: number;
  right: number;
  top: number;
  bottom: number;
  cx: number;
  cy: number;
}

interface ComputedPath {
  id: string;
  d: string;
  stroke: string;
  strokeWidth: number;
  dashed: boolean;
  subtleDash?: boolean;
  opacity?: number;
  active: boolean;
  label?: string;
  labelX?: number;
  labelY?: number;
  dimmed: boolean;
}

export function DualGraphCanvas({
  scenario,
  currentStepIndex,
  stepElapsedMs,
  choreography,
  screeningParticles,
  activeVersionIds,
  factsConfirmed,
  trace,
  onJumpToSubPhase,
  onSelectConcept,
  onSelectContractNode,
  onSelectLegalNode,
  onConfirmFacts,
  onSelectFinding,
  onJumpToDetails,
  onOpenReportCanvas,
  isGeneratingReport = false,
}: DualGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const nodeRefs = useRef<Record<string, HTMLElement | null>>({});
  const lastSignatureRef = useRef<string>('');

  const [paths, setPaths] = useState<ComputedPath[]>([]);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [recheckArc, setRecheckArc] = useState<{
    d: string;
    labelX: number;
    labelY: number;
  } | null>(null);

  const [trackedScenarioId, setTrackedScenarioId] = useState(scenario.id);
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [drawerMode, setDrawerMode] = useState<'closed' | 'unit' | 'all_nodes'>('closed');
  const [sevenNodeSelection, setSevenNodeSelection] =
    useState<SevenNodeSelection | null>(null);

  if (trackedScenarioId !== scenario.id) {
    setTrackedScenarioId(scenario.id);
    setSelectedUnitId(null);
    setDrawerMode('closed');
    setSevenNodeSelection(null);
  }

  const assemblyStage = choreography.assemblyStage;
  const isCenteredStage =
    assemblyStage === 'folio_scan' || assemblyStage === 'graph_build';

  const subPhases = useMemo(
    () => getSubPhasesForStep(currentStepIndex),
    [currentStepIndex]
  );

  const totalClauseCount = useMemo(
    () => scenario.sections.reduce((acc, s) => acc + s.clauses.length, 0),
    [scenario.sections]
  );

  const formattedSigningDate = useMemo(
    () => scenario.signingDateIso.split('-').reverse().join('/'),
    [scenario.signingDateIso]
  );

  const full7Model = useMemo(
    () => buildContractGraphModel(scenario),
    [scenario]
  );

  const step7Model = useMemo(
    () => filterContractGraphForStep(full7Model, currentStepIndex),
    [full7Model, currentStepIndex]
  );

  const effective7Selection = useMemo<SevenNodeSelection | null>(() => {
    if (!sevenNodeSelection) return null;
    const nodeExists = step7Model.nodes.some((n) => n.id === sevenNodeSelection.id);
    return nodeExists ? sevenNodeSelection : null;
  }, [sevenNodeSelection, step7Model.nodes]);

  const sevenNodeTrace = useMemo(
    () => resolve7NodeSelectionTrace(step7Model, effective7Selection),
    [step7Model, effective7Selection]
  );

  const unit7Nodes = useMemo(
    () => step7Model.nodes.filter((n) => n.nodeType === 'Unit'),
    [step7Model.nodes]
  );

  const amendedTargetNodes = useMemo(() => {
    const map = new Map<string, string>();
    for (const edge of scenario.contractEdges) {
      if (edge.kind === 'addendum_amends') {
        const source = scenario.contractNodes.find((n) => n.id === edge.from);
        map.set(edge.to, source?.sublabel || edge.label);
      }
    }
    return map;
  }, [scenario.contractEdges, scenario.contractNodes]);

  const handleOpenMajorNodeInspector = useCallback(
    (nodeId: string, clauseId?: string) => {
      if (clauseId) {
        const targetUnit = unit7Nodes.find((u) => u.clauseId === clauseId);
        if (targetUnit) {
          setSelectedUnitId(targetUnit.id);
          setDrawerMode('unit');
          setSevenNodeSelection({ kind: 'unit', id: targetUnit.id });
        }
      }
      onSelectContractNode(nodeId, clauseId);
    },
    [onSelectContractNode, unit7Nodes]
  );

  const visibleContractNodes = useMemo(
    () => scenario.contractNodes.filter((n) => currentStepIndex >= n.revealAtStep),
    [scenario.contractNodes, currentStepIndex]
  );

  const visibleConcepts = useMemo(
    () =>
      currentStepIndex === 2
        ? scenario.concepts.slice(0, choreography.visibleConceptCount)
        : scenario.concepts.filter((c) => currentStepIndex >= c.revealAtStep),
    [scenario.concepts, currentStepIndex, choreography.visibleConceptCount]
  );

  // Strict requirement: Legal Graph cards reveal ONLY after particle filtering finishes!
  const visibleLegalNodes = useMemo(
    () =>
      choreography.filteringComplete
        ? scenario.legalNodes.slice(0, choreography.visibleLegalCount)
        : [],
    [scenario.legalNodes, choreography.filteringComplete, choreography.visibleLegalCount]
  );

  const visibleLegalNodeIds = useMemo(
    () => new Set(visibleLegalNodes.map((n) => n.id)),
    [visibleLegalNodes]
  );

  // Spotlight Concept in Step 3 (clause -> concept emergence), Step 5 (querying), Step 7 (comparing)
  const activeStepConceptId = useMemo(() => {
    if (currentStepIndex === 2) {
      if (choreography.activeQueryConceptIndex !== null) {
        return scenario.concepts[choreography.activeQueryConceptIndex]?.id ?? null;
      }
      return visibleConcepts.at(-1)?.id ?? null;
    }
    if (currentStepIndex === 4 && choreography.activeQueryConceptIndex !== null) {
      return scenario.concepts[choreography.activeQueryConceptIndex]?.id ?? null;
    }
    if (currentStepIndex === 6) {
      return (
        scenario.comparisons[choreography.activeComparisonIndex]?.conceptId ?? null
      );
    }
    return null;
  }, [
    currentStepIndex,
    visibleConcepts,
    choreography.activeQueryConceptIndex,
    choreography.activeComparisonIndex,
    scenario.concepts,
    scenario.comparisons,
  ]);

  const discoveredParticles = useMemo(() => {
    if (currentStepIndex < 4) return [];
    if (currentStepIndex === 4) {
      return screeningParticles.filter((p) => stepElapsedMs >= p.discoveredAtMs);
    }
    return screeningParticles;
  }, [currentStepIndex, screeningParticles, stepElapsedMs]);

  const isCloudActive = currentStepIndex >= 4;
  const isCloudSplit = choreography.filteringStarted;
  const showReportZone = currentStepIndex >= 6 && choreography.filteringComplete;

  const reportSummary = useMemo(() => {
    const issueCount = scenario.findings.filter(
      (f) => f.status === 'issue' || f.status === 'conflict'
    ).length;
    const attentionCount = scenario.findings.filter(
      (f) => f.status === 'insufficient_data' || f.status === 'needs_confirmation'
    ).length;
    const okCount = scenario.findings.length - issueCount - attentionCount;
    return {
      totalCount: scenario.findings.length,
      issueCount,
      attentionCount,
      okCount,
    };
  }, [scenario.findings]);

  const hasSelectedTrace =
    trace.findingId !== null ||
    trace.conceptIds.size > 0 ||
    trace.contractNodeIds.size > 0 ||
    trace.legalNodeIds.size > 0;

  // Measure SVG lines for the Docked 5-Zone Stage (with faint dotted streaming lines like video ref)
  const measureAndBuildPaths = useCallback(() => {
    if (isCenteredStage) {
      if (paths.length > 0) {
        lastSignatureRef.current = '';
        setPaths([]);
        setRecheckArc(null);
      }
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    const cRect = container.getBoundingClientRect();
    const scrollX = container.scrollLeft;
    const scrollY = container.scrollTop;
    const nextWidth = Math.max(container.scrollWidth, Math.round(cRect.width));
    const nextHeight = Math.max(container.scrollHeight, Math.round(cRect.height));
    if (nextWidth < 60 || nextHeight < 60) return;

    const points: Record<string, Point> = {};
    for (const [id, el] of Object.entries(nodeRefs.current)) {
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      points[id] = {
        left: r.left - cRect.left + scrollX,
        right: r.right - cRect.left + scrollX,
        top: r.top - cRect.top + scrollY,
        bottom: r.bottom - cRect.top + scrollY,
        cx: r.left - cRect.left + scrollX + r.width / 2,
        cy: r.top - cRect.top + scrollY + r.height / 2,
      };
    }

    const nextPaths: ComputedPath[] = [];

    // 0. Source Anchor -> Major Contract Graph nodes
    const anchorPt = points['source_anchor'];
    if (anchorPt && visibleContractNodes.length > 0) {
      for (const targetNode of visibleContractNodes) {
        const tPt = points[targetNode.id];
        if (!tPt) continue;
        const x1 = anchorPt.right;
        const y1 = anchorPt.cy;
        const x2 = tPt.left;
        const y2 = tPt.cy;
        const midX = x1 + (x2 - x1) * 0.42;
        const d = `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(midX)} ${Math.round(
          y1
        )}, ${Math.round(midX)} ${Math.round(y2)}, ${Math.round(x2)} ${Math.round(y2)}`;
        const isHighlighted = trace.contractNodeIds.has(targetNode.id);

        nextPaths.push({
          id: `anchor_to_${targetNode.id}`,
          d,
          stroke: isHighlighted
            ? '#1E3A5F'
            : targetNode.kind === 'section'
            ? '#BE123C'
            : '#64748B',
          strokeWidth: isHighlighted ? 1.9 : 1.4,
          dashed: false,
          opacity: isHighlighted ? 1 : 0.78,
          active: isHighlighted || currentStepIndex === 0,
          dimmed: hasSelectedTrace && !isHighlighted,
        });
      }
    }

    // 1. Contract Graph internal ref (thin) & addendum amendment (prominent + effective date from Step 4 onward)
    for (const edge of scenario.contractEdges) {
      if (currentStepIndex < Math.max(3, edge.revealAtStep)) continue;
      if (edge.kind === 'parent_child') continue;
      const fromPt = points[edge.from];
      const toPt = points[edge.to];
      if (!fromPt || !toPt) continue;

      const isAmendment = edge.kind === 'addendum_amends';
      const isRelationPhaseMatch =
        currentStepIndex === 3 &&
        (choreography.activeRelationPhase === 'all' ||
          (choreography.activeRelationPhase === 'internal_ref' && !isAmendment) ||
          (choreography.activeRelationPhase === 'addendum_amends' && isAmendment));
      const isTraceHighlighted =
        trace.edgeIds.has(edge.id) ||
        (trace.contractNodeIds.has(edge.from) && trace.contractNodeIds.has(edge.to));
      const active = isRelationPhaseMatch || isTraceHighlighted || isAmendment;

      const gutterOffset = isAmendment ? -22 : -13;
      const xStart = fromPt.left;
      const yStart = fromPt.cy;
      const xEnd = toPt.left;
      const yEnd = toPt.cy;
      const gutterLeft = anchorPt ? anchorPt.right + 6 : 6;
      const gutterRight = Math.min(xStart, xEnd) - 4;
      const ctrlX = Math.max(
        gutterLeft + 4,
        Math.min(xStart, xEnd) + gutterOffset
      );

      const d = `M ${Math.round(xStart)} ${Math.round(yStart)} C ${Math.round(
        ctrlX
      )} ${Math.round(yStart)}, ${Math.round(ctrlX)} ${Math.round(yEnd)}, ${Math.round(
        xEnd
      )} ${Math.round(yEnd)}`;
      const conciseLabel = isAmendment
        ? edge.label.replace(/^Sửa đổi\s*·\s*HL\s*/i, 'Sửa · ')
        : 'Dẫn chiếu';
      const labelWidth = Math.max(54, Math.round(conciseLabel.length * 4.8 + 14));
      const centeredX = Math.round((gutterLeft + gutterRight - labelWidth) / 2);

      nextPaths.push({
        id: edge.id,
        d,
        stroke: isAmendment
          ? active
            ? '#881337'
            : '#BE123C'
          : active
          ? '#B45309'
          : '#D97706',
        strokeWidth: isAmendment ? (isRelationPhaseMatch ? 2.4 : 2.0) : active ? 1.7 : 1.35,
        dashed: !isAmendment,
        subtleDash: !isAmendment && !active,
        opacity: isAmendment ? 0.96 : active ? 0.95 : 0.76,
        active,
        label:
          isAmendment || (currentStepIndex === 3 && active) ? conciseLabel : undefined,
        labelX: Math.max(gutterLeft, centeredX),
        labelY: Math.round((yStart + yEnd) / 2),
        dimmed: hasSelectedTrace && !isTraceHighlighted && !isAmendment,
      });
    }

    // 2. Contract Node -> Concept Bridge
    for (const concept of visibleConcepts) {
      const cPt = points[concept.id];
      if (!cPt) continue;

      for (const cnId of concept.contractNodeIds) {
        const cnPt = points[cnId];
        if (!cnPt) continue;

        const isTraceActive =
          (trace.conceptIds.has(concept.id) &&
            (trace.contractNodeIds.size === 0 || trace.contractNodeIds.has(cnId))) ||
          activeStepConceptId === concept.id;
        const isResolved = currentStepIndex >= 6 || isTraceActive;
        const isDottedStream = currentStepIndex >= 2 && currentStepIndex < 6 && !isTraceActive;

        const x1 = cnPt.right;
        const y1 = cnPt.cy;
        const x2 = cPt.left;
        const y2 = cPt.cy;
        const dx = (x2 - x1) * 0.5;
        const d = `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(
          x1 + dx
        )} ${Math.round(y1)}, ${Math.round(x2 - dx)} ${Math.round(y2)}, ${Math.round(
          x2
        )} ${Math.round(y2)}`;

        const st = STATUS_CONFIG[concept.status];
        nextPaths.push({
          id: `link_${cnId}_${concept.id}`,
          d,
          stroke: isTraceActive ? '#1E3A5F' : isResolved ? st.accentHex : '#475569',
          strokeWidth: isTraceActive ? 2.2 : isResolved ? 1.65 : 1.5,
          dashed: isDottedStream && !isTraceActive || (hasSelectedTrace && !isTraceActive),
          subtleDash: isDottedStream && !isTraceActive,
          opacity: isTraceActive ? 1 : isDottedStream ? 0.8 : 0.88,
          active: isTraceActive || currentStepIndex === 2,
          dimmed: hasSelectedTrace && !isTraceActive,
        });
      }
    }

    // 3. Concept Bridge -> Screening Particle Cloud (progressive Concept-by-Concept query beams in Step 5)
    const cloudCenterPt = points['cloud_center'];
    const cloudRelevantPt = points['cloud_relevant'];

    if (currentStepIndex >= 4 && cloudCenterPt) {
      const targetCloudPt =
        choreography.filteringComplete && cloudRelevantPt ? cloudRelevantPt : cloudCenterPt;

      for (let cIdx = 0; cIdx < visibleConcepts.length; cIdx += 1) {
        const concept = visibleConcepts[cIdx];
        const cPt = points[concept.id];
        if (!cPt) continue;

        const isQueryingNow =
          currentStepIndex === 4 && choreography.activeQueryConceptIndex === cIdx;
        const isQueuedInStep5 =
          currentStepIndex === 4 &&
          !choreography.allParticlesDiscovered &&
          choreography.activeQueryConceptIndex !== null &&
          cIdx > choreography.activeQueryConceptIndex;
        const isTraceActive =
          trace.conceptIds.has(concept.id) ||
          isQueryingNow ||
          activeStepConceptId === concept.id;

        const x1 = cPt.right;
        const y1 = cPt.cy;
        const x2 = targetCloudPt.left;
        const y2 = targetCloudPt.cy;
        const dx = (x2 - x1) * 0.52;
        const d = `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(
          x1 + dx
        )} ${Math.round(y1)}, ${Math.round(x2 - dx)} ${Math.round(y2)}, ${Math.round(
          x2
        )} ${Math.round(y2)}`;

        nextPaths.push({
          id: `concept_to_cloud_${concept.id}`,
          d,
          stroke: isTraceActive ? '#1E3A5F' : '#475569',
          strokeWidth: isTraceActive ? 2.1 : 1.5,
          dashed: !isTraceActive || isQueryingNow,
          subtleDash: !isTraceActive && !isQueryingNow,
          opacity: isQueuedInStep5 ? 0.34 : isTraceActive ? 1 : 0.78,
          active: !isQueuedInStep5,
          dimmed: hasSelectedTrace && !trace.conceptIds.has(concept.id),
        });
      }
    }

    // 4. Screening Particle Cloud (upper Hiệu lực cluster) -> Legal Graph cards (STRICTLY post-filtering!)
    if (choreography.filteringComplete && visibleLegalNodes.length > 0) {
      const sourceCloudPt =
        isCloudSplit && cloudRelevantPt ? cloudRelevantPt : cloudCenterPt;

      if (sourceCloudPt) {
        for (const ln of visibleLegalNodes) {
          const lnPt = points[ln.id];
          if (!lnPt) continue;

          const isDimmedByVersion =
            currentStepIndex >= 5 && ln.isSelectedVersion === false;
          const isStepActiveLegal =
            activeStepConceptId !== null && ln.conceptIds.includes(activeStepConceptId);
          const isTraceActive = trace.legalNodeIds.has(ln.id) || isStepActiveLegal;

          const x1 = sourceCloudPt.right;
          const y1 = sourceCloudPt.cy;
          const x2 = lnPt.left;
          const y2 = lnPt.cy;
          const dx = (x2 - x1) * 0.48;
          const d = `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(
            x1 + dx
          )} ${Math.round(y1)}, ${Math.round(x2 - dx)} ${Math.round(y2)}, ${Math.round(
            x2
          )} ${Math.round(y2)}`;

          const isPending = isDimmedByVersion;
          nextPaths.push({
            id: `cloud_to_${ln.id}`,
            d,
            stroke: isTraceActive
              ? '#15803D'
              : isDimmedByVersion
              ? '#94A3B8'
              : '#15803D',
            strokeWidth: isTraceActive ? 2.1 : isPending ? 1.25 : 1.65,
            dashed: isPending || (hasSelectedTrace && !trace.legalNodeIds.has(ln.id)),
            subtleDash: isPending,
            opacity: isDimmedByVersion ? 0.35 : isTraceActive ? 1 : 0.88,
            active: !isDimmedByVersion,
            dimmed: (hasSelectedTrace && !trace.legalNodeIds.has(ln.id)) || isDimmedByVersion,
          });
        }
      }
    }

    // 5. Legal Graph internal edges (right gutter — strictly post-filtering once both nodes visible)
    const rightGutterLabelYs: number[] = [];
    if (choreography.filteringComplete && visibleLegalNodes.length > 1) {
      for (const edge of scenario.legalEdges) {
        if (!visibleLegalNodeIds.has(edge.from) || !visibleLegalNodeIds.has(edge.to)) {
          continue;
        }
        const fromPt = points[edge.from];
        const toPt = points[edge.to];
        if (!fromPt || !toPt) continue;

        const isTraceActive =
          trace.edgeIds.has(edge.id) ||
          (trace.legalNodeIds.has(edge.from) && trace.legalNodeIds.has(edge.to));
        const active =
          (currentStepIndex === 5 && edge.isQueried) ||
          (currentStepIndex === 6 && edge.isQueried) ||
          isTraceActive;

        const xStart = fromPt.right;
        const yStart = fromPt.cy;
        const xEnd = toPt.right;
        const yEnd = toPt.cy;
        const ctrlX = Math.max(xStart, xEnd) + 18;
        const d = `M ${Math.round(xStart)} ${Math.round(yStart)} C ${Math.round(
          ctrlX
        )} ${Math.round(yStart)}, ${Math.round(ctrlX)} ${Math.round(yEnd)}, ${Math.round(
          xEnd
        )} ${Math.round(yEnd)}`;

        const midY = Math.round((yStart + yEnd) / 2);
        const canPlaceLabel =
          active &&
          Boolean(edge.label) &&
          !rightGutterLabelYs.some((y) => Math.abs(y - midY) < 22);
        if (canPlaceLabel) {
          rightGutterLabelYs.push(midY);
        }

        nextPaths.push({
          id: edge.id,
          d,
          stroke: active ? '#15803D' : '#0F766E',
          strokeWidth: active ? 2.0 : 1.45,
          dashed: edge.kind === 'guides' || edge.kind === 'replaces',
          subtleDash: !active,
          opacity: active ? 1 : 0.74,
          active,
          label: canPlaceLabel ? edge.label : undefined,
          labelX: Math.round(Math.max(xStart, xEnd) + 6),
          labelY: midY,
          dimmed: hasSelectedTrace && !isTraceActive,
        });
      }
    }

    // 7. Legal Graph -> Compact Report Card (Zone 5, revealed after Legal Graph completes)
    if (showReportZone && visibleLegalNodes.length > 0) {
      const reportPt = points['report_summary_anchor'];
      if (reportPt) {
        for (const ln of visibleLegalNodes) {
          if (currentStepIndex >= 5 && ln.isSelectedVersion === false) continue;
          const lnPt = points[ln.id];
          if (!lnPt) continue;

          const matchedFinding = scenario.findings.find(
            (f) =>
              f.relatedLegalNodeIds.includes(ln.id) ||
              ln.conceptIds.includes(f.conceptId)
          );
          const isHighlighted =
            trace.legalNodeIds.has(ln.id) ||
            (matchedFinding ? trace.findingId === matchedFinding.id : false);
          const isIssue =
            matchedFinding?.status === 'issue' || matchedFinding?.status === 'conflict';

          const x1 = lnPt.right;
          const y1 = lnPt.cy;
          const x2 = reportPt.left;
          const y2 = reportPt.cy;
          const dx = (x2 - x1) * 0.48;
          const d = `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(
            x1 + dx
          )} ${Math.round(y1)}, ${Math.round(x2 - dx)} ${Math.round(y2)}, ${Math.round(
            x2
          )} ${Math.round(y2)}`;

          nextPaths.push({
            id: `legal_to_report_${ln.id}`,
            d,
            stroke: isIssue ? '#9F1239' : isHighlighted ? '#1E3A5F' : '#166534',
            strokeWidth: isHighlighted ? 1.85 : isIssue ? 1.4 : 1.25,
            dashed: currentStepIndex === 6,
            subtleDash: currentStepIndex === 6 && !isHighlighted,
            opacity: hasSelectedTrace && !isHighlighted ? 0.22 : 0.82,
            active: isHighlighted || isIssue,
            dimmed: hasSelectedTrace && !isHighlighted,
          });
        }
      }
    }

    // 6. Step 8 Return Scan Arc (sweeping across Contract Graph)
    let nextArc: { d: string; labelX: number; labelY: number } | null = null;
    if (
      currentStepIndex === 7 &&
      visibleConcepts.length > 0 &&
      visibleContractNodes.length > 0
    ) {
      const targetNodeIdx = Math.min(
        visibleContractNodes.length - 1,
        Math.max(0, choreography.activeRecheckClauseCount - 1)
      );
      const lastConcept = points[visibleConcepts[visibleConcepts.length - 1].id];
      const targetContract =
        points[visibleContractNodes[targetNodeIdx]?.id] ??
        points[visibleContractNodes[0].id];
      if (lastConcept && targetContract) {
        const maxContractBottom = visibleContractNodes.reduce(
          (maxB, n) => Math.max(maxB, points[n.id]?.bottom ?? 0),
          targetContract.bottom
        );
        const bottomAnchor = Math.max(lastConcept.bottom, maxContractBottom) + 34;
        nextArc = {
          d: `M ${Math.round(lastConcept.cx)} ${Math.round(
            lastConcept.bottom + 8
          )} C ${Math.round(lastConcept.cx)} ${Math.round(
            bottomAnchor
          )}, ${Math.round(targetContract.cx)} ${Math.round(
            bottomAnchor
          )}, ${Math.round(targetContract.cx)} ${Math.round(
            maxContractBottom + 8
          )}`,
          labelX: Math.round((lastConcept.cx + targetContract.cx) / 2 - 59),
          labelY: Math.round(bottomAnchor - 10),
        };
      }
    }

    const signature = JSON.stringify({
      w: nextWidth,
      h: nextHeight,
      p: nextPaths.map((x) => [x.id, x.d, x.stroke, x.dashed, x.active, x.dimmed, x.label]),
      a: nextArc,
    });

    if (signature !== lastSignatureRef.current) {
      lastSignatureRef.current = signature;
      setCanvasSize({ width: nextWidth, height: nextHeight });
      setPaths(nextPaths);
      setRecheckArc(nextArc);
    }
  }, [
    activeStepConceptId,
    choreography.activeQueryConceptIndex,
    choreography.activeRecheckClauseCount,
    choreography.activeRelationPhase,
    choreography.allParticlesDiscovered,
    choreography.filteringComplete,
    currentStepIndex,
    hasSelectedTrace,
    isCenteredStage,
    isCloudSplit,
    paths.length,
    scenario.activeUnitIds,
    scenario.contractEdges,
    scenario.findings,
    scenario.legalEdges,
    showReportZone,
    trace,
    visibleConcepts,
    visibleContractNodes,
    visibleLegalNodeIds,
    visibleLegalNodes,
  ]);

  useEffect(() => {
    const raf = window.requestAnimationFrame(measureAndBuildPaths);
    const t1 = window.setTimeout(measureAndBuildPaths, 280);
    const t2 = window.setTimeout(measureAndBuildPaths, 760);
    const t3 = window.setTimeout(measureAndBuildPaths, 980);
    return () => {
      window.cancelAnimationFrame(raf);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
    };
  }, [
    measureAndBuildPaths,
    scenario.id,
    currentStepIndex,
    assemblyStage,
    showReportZone,
  ]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      window.requestAnimationFrame(measureAndBuildPaths);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [measureAndBuildPaths]);

  const renderMajorContractCard = (
    node: AnalysisScenario['contractNodes'][number]
  ) => {
    const isRoot = node.kind === 'contract';
    const isAddendum = node.kind === 'section';
    const amendedDetail = amendedTargetNodes.get(node.id);
    const showAmendmentTransform =
      Boolean(amendedDetail) &&
      (currentStepIndex > 3 ||
        (currentStepIndex === 3 && choreography.activeRelationPhase !== 'internal_ref'));
    const isUnitBeingTagged = Boolean(
      currentStepIndex === 2 &&
        node.clauseId &&
        scenario.activeUnitIds?.some(
          (uid) => uid === node.clauseId || uid.startsWith(`${node.clauseId}.`)
        )
    );
    const spotlightConcept =
      activeStepConceptId !== null
        ? scenario.concepts.find((c) => c.id === activeStepConceptId) ?? null
        : null;
    const isSpotlightSourceClause = Boolean(
      currentStepIndex === 2 &&
        spotlightConcept &&
        (spotlightConcept.contractNodeIds.includes(node.id) ||
          node.conceptIds.includes(spotlightConcept.id))
    );
    const isExaminedInStep3 = isSpotlightSourceClause || isUnitBeingTagged;
    const hasActiveStep3Examination =
      currentStepIndex === 2 &&
      (Boolean(scenario.activeUnitIds?.length) || spotlightConcept !== null);

    const isRefHighlightedInStep4 =
      currentStepIndex === 3 &&
      choreography.activeRelationPhase === 'internal_ref' &&
      scenario.contractEdges.some(
        (e) => e.kind === 'internal_ref' && (e.from === node.id || e.to === node.id)
      );

    const isStepHighlighted =
      (currentStepIndex === 3 &&
        (isRefHighlightedInStep4 ||
          (choreography.activeRelationPhase !== 'internal_ref' &&
            (isAddendum || Boolean(amendedDetail))))) ||
      isExaminedInStep3 ||
      (currentStepIndex !== 2 &&
        activeStepConceptId !== null &&
        node.conceptIds.includes(activeStepConceptId));
    const is7Matched = Boolean(
      node.clauseId &&
        Array.from(sevenNodeTrace.highlightedUnitIds).some((uid) =>
          uid.endsWith(node.clauseId!)
        )
    );
    const isHighlighted =
      trace.contractNodeIds.has(node.id) || isStepHighlighted || is7Matched;
    const dimmed =
      (hasSelectedTrace &&
        trace.contractNodeIds.size > 0 &&
        !trace.contractNodeIds.has(node.id)) ||
      (hasActiveStep3Examination && !isExaminedInStep3);

    const cardBg =
      showAmendmentTransform && currentStepIndex === 3
        ? 'bg-[#FBE6EC] ring-1 ring-inset ring-[#9F1239]/55'
        : isExaminedInStep3
        ? 'bg-[#DCE9F7] ring-2 ring-[#1E3A5F] shadow-sm'
        : isHighlighted
        ? 'bg-[#E5EEF7] ring-1 ring-inset ring-[#1E3A5F]/55'
        : isAddendum
        ? 'bg-[#FDF0F3] hover:bg-[#FCE6EC]'
        : isRoot
        ? 'bg-[#EDF3F9] hover:bg-[#E4ECF6]'
        : 'bg-[#FEF6D6] hover:bg-[#FDF0C2]';

    const leftStripeColor =
      showAmendmentTransform && currentStepIndex === 3
        ? 'bg-[#881337]'
        : isExaminedInStep3
        ? 'bg-[#1E3A5F]'
        : isAddendum
        ? 'bg-[#9F1239]'
        : isRoot
        ? 'bg-[#1E3A5F]'
        : 'bg-[#EAB308]';

    return (
      <motion.div
        key={node.id}
        ref={(el) => {
          nodeRefs.current[node.id] = el;
        }}
        initial={{ opacity: 0.88, x: 0 }}
        animate={{ opacity: dimmed ? (hasActiveStep3Examination && !isExaminedInStep3 ? 0.62 : 0.42) : 1, x: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      >
        <button
          type="button"
          onClick={() => handleOpenMajorNodeInspector(node.id, node.clauseId)}
          title={`${node.label}${node.sublabel ? ` — ${node.sublabel}` : ''}`}
          className={`chamfer-tr w-full h-[46px] text-left relative pl-2.5 pr-2 py-1 flex flex-col justify-center transition-all duration-300 cursor-pointer ${cardBg}`}
        >
          <span
            aria-hidden="true"
            className={`absolute left-0 top-0 bottom-0 w-[3.5px] ${leftStripeColor}`}
          />

          <div className="flex items-center justify-between gap-1.5 min-w-0">
            <span className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold text-stone-900 truncate min-w-0">
              {isExaminedInStep3 && (
                <span
                  className="w-1.5 h-1.5 rounded-full bg-[#1E3A5F] animate-pulse shrink-0"
                  aria-hidden="true"
                />
              )}
              <span className="truncate">{node.label}</span>
            </span>
            <div className="flex items-center gap-1 shrink-0">
              {factsConfirmed &&
                currentStepIndex >= 2 &&
                node.kind !== 'contract' && (
                  <CheckCircle2
                    className="w-3 h-3 text-[#166534]"
                    aria-hidden="true"
                  />
                )}
              {isAddendum && (
                <GitBranch
                  className="w-3 h-3 text-[#881337]"
                  aria-hidden="true"
                />
              )}
            </div>
          </div>

          {showAmendmentTransform ? (
            <div className="mt-0.5 text-[10.5px] font-semibold text-[#881337] truncate">
              → {amendedDetail}
            </div>
          ) : (
            node.sublabel && (
              <div className="text-[10.5px] text-stone-600 mt-0.5 truncate">
                {node.sublabel}
              </div>
            )
          )}
        </button>
      </motion.div>
    );
  };

  return (
    <section
      aria-label="Sân khấu phân tích Hai Đồ thị và Concept Cầu nối"
      className="bg-white border border-stone-200 rounded flex flex-col overflow-hidden"
    >
      {/* Judicial Stage Top Bar */}
      <div className="px-4 lg:px-6 py-2.5 border-b border-stone-200 flex flex-wrap items-center justify-between gap-2 bg-[#FAF9F6]">
        <div className="flex items-center gap-3">
          <h2 className="font-serif text-sm font-semibold text-stone-900">
            {isCenteredStage
              ? 'Tách Contract Graph từ Hồ sơ Hợp đồng'
              : 'Không gian Đối chiếu Hai Đồ thị & Concept Cầu nối'}
          </h2>
          {factsConfirmed && currentStepIndex >= 2 && (
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#166534]">
              <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
              Đã xác minh dữ kiện
            </span>
          )}
        </div>

        {subPhases.length > 0 ? (
          <div className="flex flex-wrap items-center gap-3 text-[11px]">
            {subPhases.map((sp, idx) => {
              const activeIdx = subPhases.findIndex(
                (s) => s.id === choreography.activeSubPhaseId
              );
              const isCurrent = sp.id === choreography.activeSubPhaseId;
              const isPast = activeIdx > idx;
              return (
                <button
                  key={sp.id}
                  type="button"
                  onClick={() => onJumpToSubPhase(sp.targetMs)}
                  className={`inline-flex items-center gap-1.5 transition-colors cursor-pointer ${
                    isCurrent
                      ? 'text-[#1E3A5F] font-semibold'
                      : isPast
                      ? 'text-[#166534] font-medium'
                      : 'text-stone-400 hover:text-stone-700'
                  }`}
                >
                  <span className="font-mono tabular-nums">{sp.num}</span>
                  <span>{sp.label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-stone-600">
            <span className="inline-flex items-center gap-1.5">
              <span className="w-4 h-[2px] bg-[#64748B] inline-block" aria-hidden="true" />
              Cấu trúc HĐ
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-4 h-[2.5px] bg-[#881337] inline-block" aria-hidden="true" />
              Sửa đổi (AMENDS)
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-4 border-t-[1.5px] border-dashed border-[#D97706] inline-block" aria-hidden="true" />
              Dẫn chiếu
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-4 h-[2px] bg-[#1E3A5F] inline-block" aria-hidden="true" />
              Gắn Concept / Sàng lọc
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-4 h-[2px] bg-[#15803D] inline-block" aria-hidden="true" />
              Căn cứ hiệu lực
            </span>
          </div>
        )}
      </div>

      {/* Interactive Graph Stage with LayoutGroup */}
      <LayoutGroup id={`stage-group-${scenario.id}`}>
        <div
          ref={containerRef}
          data-testid="dual-graph-canvas"
          className="relative px-4 lg:px-6 py-4 min-h-[440px] max-h-[540px] overflow-y-auto overflow-x-auto thin-scroll bg-white"
        >
          {isCenteredStage ? (
            <CenteredContractGraphTree
              scenario={scenario}
              fullModel={full7Model}
              currentStepIndex={currentStepIndex}
              assemblyStage={assemblyStage}
              stepElapsedMs={stepElapsedMs}
              selectedUnitId={drawerMode === 'unit' ? selectedUnitId : null}
              onSelectUnit={(unitId) => {
                const target = unit7Nodes.find((u) => u.id === unitId);
                if (target) {
                  handleOpenMajorNodeInspector(
                    target.legacyNodeId || target.id,
                    target.clauseId
                  );
                }
              }}
            />
          ) : (
            <>
              {/* Dynamic SVG Layer with Faint Dotted Drifting Curves & Resolved Solid Curves */}
              {canvasSize.width > 0 && (
                <>
                  <svg
                    aria-hidden="true"
                    className="hidden lg:block absolute top-0 left-0 z-0 pointer-events-none overflow-visible"
                    style={{ width: canvasSize.width, height: canvasSize.height }}
                    viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
                  >
                    {paths.map((p) => (
                      <g
                        key={p.id}
                        opacity={p.dimmed ? 0.16 : p.opacity ?? 1}
                      >
                        <motion.path
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
                          d={p.d}
                          fill="none"
                          stroke={p.stroke}
                          strokeWidth={p.strokeWidth}
                          strokeDasharray={
                            p.dashed && (currentStepIndex < 7 || scenario.isBusy)
                              ? '4 4'
                              : undefined
                          }
                          className={
                            p.dashed && (currentStepIndex < 7 || scenario.isBusy)
                              ? p.subtleDash
                                ? 'animate-dash-flow-subtle'
                                : 'animate-dash-flow'
                              : ''
                          }
                          strokeLinecap="round"
                        />
                      </g>
                    ))}

                    {recheckArc && (
                      <motion.path
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 0.55 }}
                        d={recheckArc.d}
                        fill="none"
                        stroke="#312E81"
                        strokeWidth={1.85}
                        strokeDasharray="4 4"
                        className="animate-dash-flow-subtle"
                      />
                    )}
                  </svg>

                  {/* Unclipped z-20 Edge Badge Overlay */}
                  <svg
                    aria-hidden="true"
                    className="hidden lg:block absolute top-0 left-0 z-20 pointer-events-none overflow-visible"
                    style={{ width: canvasSize.width, height: canvasSize.height }}
                    viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
                  >
                    {paths.map((p) => {
                      if (!p.label || p.labelX === undefined || p.labelY === undefined) {
                        return null;
                      }
                      const badgeW = Math.max(54, Math.round(p.label.length * 4.8 + 14));
                      return (
                        <g
                          key={`${p.id}_badge`}
                          opacity={p.dimmed ? 0.16 : p.opacity ?? 1}
                          transform={`translate(${p.labelX}, ${p.labelY})`}
                        >
                          <rect
                            x="0"
                            y="-8.5"
                            width={badgeW}
                            height="17"
                            rx="3"
                            fill="#FFFFFF"
                            stroke={p.stroke}
                            strokeWidth="1"
                          />
                          <text
                            x={badgeW / 2}
                            y="3"
                            textAnchor="middle"
                            fontSize="8"
                            fontWeight="600"
                            fill={p.stroke}
                          >
                            {p.label}
                          </text>
                        </g>
                      );
                    })}

                    {recheckArc && (
                      <g transform={`translate(${recheckArc.labelX}, ${recheckArc.labelY})`}>
                        <rect
                          x="0"
                          y="-10"
                          width="124"
                          height="19"
                          rx="3"
                          fill="#F4F5FA"
                          stroke="#312E81"
                          strokeWidth="1"
                        />
                        <text x="62" y="3" textAnchor="middle" fontSize="9.5" fontWeight="600" fill="#312E81">
                          Quét lại toàn văn bản
                        </text>
                      </g>
                    )}
                  </svg>
                </>
              )}

              {/* Symmetrical 5-Zone Stage: [Source Anchor + Contract Graph] | Concept | Screening Cloud | Legal Graph | Minimal Report */}
              <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-[352px_164px_156px_minmax(190px,1fr)_168px] gap-4 lg:gap-6 items-stretch">
                {/* Docked Left Shell (Source Anchor + Contract Graph) */}
                <motion.div
                  layoutId="contract-graph-shell"
                  onLayoutAnimationComplete={measureAndBuildPaths}
                  transition={{
                    layout: { duration: 0.65, ease: [0.22, 1, 0.36, 1] },
                  }}
                  className="md:col-span-2 lg:col-span-1 grid grid-cols-1 sm:grid-cols-[114px_minmax(0,1fr)] gap-2 items-stretch"
                >
                  {/* Zone 0: Uploaded Contract Source Anchor */}
                  <div className="flex flex-col">
                    <div className="flex items-center justify-between gap-1 text-xs font-semibold text-stone-800 pb-2 border-b border-stone-200 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <FileText className="w-3.5 h-3.5 text-[#1E3A5F] shrink-0" aria-hidden="true" />
                        <span className="truncate">Hồ sơ nguồn</span>
                      </div>
                      <span className="text-[11px] font-mono text-stone-400 tabular-nums shrink-0">
                        {scenario.sections.length} tệp
                      </span>
                    </div>

                    <div className="flex-1 flex flex-col justify-center py-3">
                      <div
                        ref={(el) => {
                          nodeRefs.current['source_anchor'] = el;
                        }}
                        data-testid="contract-source-anchor"
                        className="chamfer-tr-lg bg-[#1E3A5F] text-white p-3 space-y-1.5"
                      >
                        <div className="text-[10px] font-medium text-slate-300">
                          {'Hợp đồng tải lên'}
                        </div>
                        <div className="font-serif text-[12px] font-semibold leading-snug text-white line-clamp-3">
                          {scenario.title}
                        </div>
                        <div className="pt-1 border-t border-white/15 space-y-0.5">
                          {scenario.sections.map((sec) => (
                            <div
                              key={sec.id}
                              title={sec.fileName}
                              className="text-[10px] font-mono text-slate-200 truncate"
                            >
                              · {sec.fileName}
                            </div>
                          ))}
                        </div>
                        <div className="text-[10px] font-mono text-slate-300 pt-0.5 tabular-nums truncate">
                          Ký {formattedSigningDate} · {totalClauseCount} điều
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Zone 1: Clean Simplified Contract Graph (Parent Units Only) */}
                  <div className="sm:pl-[74px] flex flex-col relative">
                    <div className="flex items-center justify-between gap-1 text-xs font-semibold text-stone-800 pb-2 border-b border-stone-200 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <FileCode2 className="w-3.5 h-3.5 text-[#CA8A04] shrink-0" aria-hidden="true" />
                        <span className="truncate">Contract Graph</span>
                      </div>
                      <span className="text-[11px] font-mono text-stone-400 tabular-nums shrink-0">
                        {visibleContractNodes.length} nút
                      </span>
                    </div>

                    <div className="flex-1 flex flex-col justify-center py-3 space-y-1.5">
                      {visibleContractNodes.map((node) =>
                        renderMajorContractCard(node)
                      )}
                    </div>
                  </div>
                </motion.div>

                {/* Zone 2: Concept Cầu nối (Pop-out spring capsules, no placeholder clutter) */}
                <motion.div
                  initial={{ opacity: 0, x: 14 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    duration: 0.4,
                    delay: assemblyStage === 'docking_left' ? 0.15 : 0,
                    ease: [0.22, 1, 0.36, 1],
                  }}
                  className="flex flex-col"
                >
                  <div className="flex items-center justify-between gap-1 text-xs font-semibold text-stone-800 pb-2 border-b border-stone-200 whitespace-nowrap">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Link2 className="w-3.5 h-3.5 text-[#475569] shrink-0" aria-hidden="true" />
                      <span className="truncate">Concept</span>
                    </div>
                    <span className="text-[11px] font-mono text-stone-400 tabular-nums shrink-0">
                      {visibleConcepts.length} chủ đề
                    </span>
                  </div>

                  <div className="flex-1 flex flex-col justify-center py-3">
                    {visibleConcepts.length > 0 && (
                      <div className="space-y-1.5">
                        {visibleConcepts.map((concept, idx) => {
                          const st = STATUS_CONFIG[concept.status];
                          const isQueryingNow =
                            currentStepIndex === 4 &&
                            choreography.activeQueryConceptIndex === idx;
                          const isHighlighted =
                            trace.conceptIds.has(concept.id) ||
                            isQueryingNow ||
                            activeStepConceptId === concept.id;
                          const dimmed =
                            hasSelectedTrace &&
                            trace.conceptIds.size > 0 &&
                            !trace.conceptIds.has(concept.id);

                          return (
                            <motion.button
                              key={concept.id}
                              ref={(el) => {
                                nodeRefs.current[concept.id] = el;
                              }}
                              type="button"
                              onClick={() => onSelectConcept(concept.id)}
                              initial={{ opacity: 0, scale: 0.92, x: -20 }}
                              animate={{
                                opacity: dimmed ? 0.42 : 1,
                                scale: isQueryingNow ? 1.02 : 1,
                                x: 0,
                              }}
                              onAnimationComplete={measureAndBuildPaths}
                              transition={{
                                duration: 0.42,
                                ease: [0.22, 1, 0.36, 1],
                              }}
                              title={`${concept.label} — ${st.label}`}
                              aria-label={`${concept.label}: ${st.label}`}
                              className={`w-full h-[32px] text-left px-2.5 rounded-full border transition-colors duration-250 cursor-pointer flex items-center justify-between gap-1.5 ${
                                isHighlighted
                                  ? 'bg-[#DCE9F7] border-[#1E3A5F] shadow-2xs'
                                  : currentStepIndex === 2
                                  ? 'bg-[#F4F6F9] border-[#94A3B8] hover:border-[#1E3A5F]'
                                  : 'bg-[#F4F6F9] border-[#CBD5E1] hover:bg-[#EBEEF4] hover:border-[#94A3B8]'
                              }`}
                            >
                              <div className="flex items-center gap-1.5 min-w-0">
                                <span
                                  className="text-[11px] font-semibold text-stone-800 shrink-0 tabular-nums"
                                  aria-hidden="true"
                                >
                                  {idx + 1}
                                </span>
                                <span className="text-[11.5px] font-medium text-stone-800 truncate">
                                  {concept.label}
                                </span>
                              </div>
                              <span
                                className="shrink-0 flex items-center"
                                style={{ color: st.accentHex }}
                                title={st.label}
                              >
                                <StatusIcon status={concept.status} className="w-3.5 h-3.5" />
                              </span>
                            </motion.button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </motion.div>

                {/* Zone 3: Screening Particle Cloud — Progressive discovery -> Dot-by-dot downward filtering -> Post-filter Legal Graph */}
                <div className="hidden lg:flex flex-col">
                  <div className="flex items-center justify-between text-xs font-semibold text-stone-800 pb-2 border-b border-stone-200">
                    <div className="flex items-center gap-1.5">
                      <Filter className="w-3.5 h-3.5 text-stone-600" aria-hidden="true" />
                      <span>Sàng lọc</span>
                    </div>
                    <span className="text-[11px] font-mono text-stone-500 tabular-nums">
                      {currentStepIndex >= 5
                        ? `${choreography.keptParticleCount}/${screeningParticles.length}`
                        : isCloudActive
                        ? `${discoveredParticles.length}/${screeningParticles.length}`
                        : '0'}
                    </span>
                  </div>

                  <div
                    data-testid="screening-particle-cloud"
                    className="flex-1 flex items-center justify-center py-3 min-h-[312px]"
                  >
                    <div className="relative w-full h-[296px] flex items-center justify-center">
                      {/* Invisible anchor points aligned with SVG cy=0 (50%) and upper splitY=-62 (27.9%) */}
                      <div
                        ref={(el) => {
                          nodeRefs.current['cloud_center'] = el;
                        }}
                        aria-hidden="true"
                        className="pointer-events-none absolute left-[12%] right-[12%] top-1/2 -translate-y-1/2 h-12"
                      />
                      <div
                        ref={(el) => {
                          nodeRefs.current['cloud_relevant'] = el;
                        }}
                        aria-hidden="true"
                        className="pointer-events-none absolute left-[12%] right-[12%] top-[27.9%] -translate-y-1/2 h-10"
                      />

                      {isCloudActive && (
                        <svg
                          aria-hidden="true"
                          viewBox="-72 -140 144 280"
                          className="w-full h-full pointer-events-none"
                        >
                          <text
                            x="0"
                            y={isCloudSplit ? -94 : -36}
                            textAnchor="middle"
                            fontSize="9.5"
                            fontWeight="600"
                            fill={
                              isCloudSplit
                                ? '#166534'
                                : choreography.allParticlesDiscovered
                                ? '#1E3A5F'
                                : '#475569'
                            }
                          >
                            {isCloudSplit
                              ? `Có phiên bản tại mốc (${choreography.keptParticleCount})`
                              : currentStepIndex === 5
                              ? `Đối chiếu mốc ${formattedSigningDate}`
                              : choreography.allParticlesDiscovered
                              ? `Đã tìm đủ ${screeningParticles.length} ứng viên`
                              : `Tìm ứng viên (${discoveredParticles.length}/${screeningParticles.length})`}
                          </text>

                          {isCloudSplit &&
                            discoveredParticles.some(
                              (p) => p.group !== 'relevant'
                            ) && (
                            <motion.text
                              x="0"
                              y="36"
                              textAnchor="middle"
                              fontSize="9.5"
                              fontWeight="500"
                              fill="#94A3B8"
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              transition={{ duration: 0.3 }}
                            >
                              Hết hiệu lực / Loại (
                              {
                                discoveredParticles.filter(
                                  (p) => p.group !== 'relevant'
                                ).length
                              }
                              )
                            </motion.text>
                          )}

                          {discoveredParticles.map((p) => {
                            const isSorted =
                              currentStepIndex > 5 ||
                              (currentStepIndex === 5 &&
                                p.filteredAtMs !== Infinity &&
                                stepElapsedMs >= p.filteredAtMs);
                            const isEvaluatingNow =
                              currentStepIndex === 5 &&
                              stepElapsedMs >= p.filteredAtMs - 180 &&
                              stepElapsedMs < p.filteredAtMs;

                            const targetX = isSorted ? p.splitX : p.centerX;
                            const targetY = isSorted ? p.splitY : p.centerY;
                            const isExcluded = isSorted && p.group !== 'relevant';

                            const dotFill = isEvaluatingNow
                              ? '#B45309'
                              : !isSorted
                              ? '#334155'
                              : p.group === 'relevant'
                              ? '#1E3A5F'
                              : '#CBD5E1';

                            const conceptRatio =
                              (p.batchIndex + 0.5) /
                              Math.max(1, scenario.concepts.length);
                            const entryY = Math.round((conceptRatio - 0.5) * 92);

                            return (
                              <motion.circle
                                key={p.id}
                                r={isEvaluatingNow ? p.radius + 1.15 : p.radius}
                                fill={dotFill}
                                initial={{
                                  cx: -66,
                                  cy: entryY,
                                  opacity: 0,
                                }}
                                animate={{
                                  cx: targetX,
                                  cy: targetY,
                                  opacity: isExcluded ? 0.46 : 0.94,
                                }}
                                transition={{
                                  cx: { type: 'spring', stiffness: 175, damping: 21 },
                                  cy: { type: 'spring', stiffness: 175, damping: 21 },
                                  opacity: { duration: 0.25 },
                                }}
                              />
                            );
                          })}
                        </svg>
                      )}
                    </div>
                  </div>
                </div>

                {/* Zone 4: Legal Graph (STRICTLY revealed only after all particles finish filtering!) */}
                <motion.div
                  initial={{ opacity: 0, x: 14 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    duration: 0.4,
                    delay: assemblyStage === 'docking_left' ? 0.22 : 0,
                    ease: [0.22, 1, 0.36, 1],
                  }}
                  className="flex flex-col"
                >
                  <div className="flex items-center justify-between text-xs font-semibold text-stone-800 pb-2 border-b border-stone-200">
                    <div className="flex items-center gap-1.5">
                      <Scale className="w-3.5 h-3.5 text-[#166534]" aria-hidden="true" />
                      <span>Legal Graph</span>
                    </div>
                    <span className="text-[11px] font-mono text-stone-400 tabular-nums">
                      {visibleLegalNodes.length} căn cứ
                    </span>
                  </div>

                  <div className="flex-1 flex flex-col justify-center py-3">
                    {visibleLegalNodes.length > 0 && (
                      <div className="space-y-1.5">
                        {visibleLegalNodes.map((ln) => {
                          const isStepActive =
                            activeStepConceptId !== null &&
                            ln.conceptIds.includes(activeStepConceptId);
                          const isHighlighted =
                            trace.legalNodeIds.has(ln.id) || isStepActive;
                          const isDimmedByVersion =
                            currentStepIndex >= 5 && ln.isSelectedVersion === false;
                          const dimmedByTrace =
                            hasSelectedTrace &&
                            trace.legalNodeIds.size > 0 &&
                            !trace.legalNodeIds.has(ln.id);

                          const cardBg = isHighlighted
                            ? 'bg-[#E4EFE8] ring-1 ring-inset ring-[#166534]/50'
                            : isDimmedByVersion
                            ? 'bg-[#F4F4F5]'
                            : 'bg-[#EFF4F1] hover:bg-[#E7EFEA]';

                          return (
                            <motion.div
                              key={ln.id}
                              ref={(el) => {
                                nodeRefs.current[ln.id] = el;
                              }}
                              initial={{ opacity: 0, scale: 0.92, x: -12 }}
                              animate={{
                                opacity: isDimmedByVersion ? 0.42 : dimmedByTrace ? 0.42 : 1,
                                scale: 1,
                                x: 0,
                              }}
                              onAnimationComplete={measureAndBuildPaths}
                              transition={{
                                duration: 0.38,
                                ease: [0.22, 1, 0.36, 1],
                              }}
                            >
                              <button
                                type="button"
                                onClick={() => onSelectLegalNode(ln.id)}
                                title={`${ln.label} — ${ln.sublabel}`}
                                className={`chamfer-tr w-full h-[52px] text-left px-2.5 py-1 flex flex-col justify-between transition-colors cursor-pointer ${cardBg}`}
                              >
                                <div className="min-w-0">
                                  <div className="flex items-center justify-between gap-1.5">
                                    <span className="text-[11.5px] font-semibold text-stone-900 truncate">
                                      {ln.label}
                                    </span>
                                    <BookOpen
                                      className={`w-3 h-3 shrink-0 ${
                                        isDimmedByVersion ? 'text-stone-400' : 'text-[#166534]'
                                      }`}
                                      aria-hidden="true"
                                    />
                                  </div>
                                  <div className="text-[10px] text-stone-500 mt-0.5 truncate">
                                    {ln.sublabel}
                                  </div>
                                </div>
                                <div className="flex items-center justify-between gap-2">
                                  <div className="flex items-center gap-1" aria-hidden="true">
                                    <span
                                      className={`w-3.5 h-[3.5px] rounded-full ${
                                        isDimmedByVersion ? 'bg-stone-300' : 'bg-[#166534]'
                                      }`}
                                    />
                                    <span
                                      className={`w-3.5 h-[3.5px] rounded-full ${
                                        isDimmedByVersion
                                          ? 'bg-stone-300'
                                          : isHighlighted
                                          ? 'bg-[#1E3A5F]'
                                          : 'bg-[#94A3B8]'
                                      }`}
                                    />
                                    <span
                                      className={`w-3.5 h-[3.5px] rounded-full ${
                                        isDimmedByVersion ? 'bg-stone-200' : 'bg-[#EAB308]/80'
                                      }`}
                                    />
                                  </div>
                                  <span className="text-[10px] font-mono text-stone-500 shrink-0">
                                    {ln.isSelectedVersion === undefined ? 'Cấu trúc' : isDimmedByVersion ? 'Không được chọn' : 'Có phiên bản'}
                                  </span>
                                </div>
                              </button>
                            </motion.div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </motion.div>

                {/* Zone 5: Minimalist Report Card (hidden cleanly before Legal Graph finishes; clicks open right Canvas) */}
                {!showReportZone ? (
                  <div className="hidden lg:block" aria-hidden="true" />
                ) : (
                  <motion.div
                    initial={{ opacity: 0, x: 14 }}
                    animate={{ opacity: 1, x: 0 }}
                    onAnimationComplete={measureAndBuildPaths}
                    transition={{
                      duration: 0.35,
                      ease: [0.22, 1, 0.36, 1],
                    }}
                    className="md:col-span-2 lg:col-span-1 flex flex-col"
                  >
                    <div className="flex items-center justify-between text-xs font-semibold text-stone-800 pb-2 border-b border-stone-200">
                      <div className="flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
                        <span>Báo cáo</span>
                      </div>
                    </div>

                    <div className="flex-1 flex flex-col justify-center py-3">
                      <motion.div
                        ref={(el) => {
                          nodeRefs.current['report_summary_anchor'] = el;
                        }}
                        onAnimationComplete={measureAndBuildPaths}
                        initial={{ opacity: 0, scale: 0.94, x: 12 }}
                        animate={{ opacity: 1, scale: 1, x: 0 }}
                        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                      >
                        <button
                          type="button"
                          onClick={() => onOpenReportCanvas?.()}
                          className={`chamfer-tr relative w-full text-left border pl-3.5 pr-3 py-2.5 transition-colors cursor-pointer group ${
                            reportSummary.issueCount > 0
                              ? 'bg-[#FDF0F3] hover:bg-[#FAE3E8] border-[#DFB8C2]'
                              : reportSummary.attentionCount > 0
                              ? 'bg-[#FDF6DE] hover:bg-[#FAF0CA] border-[#DFCFA0]'
                              : 'bg-[#E9F3EC] hover:bg-[#DDECE2] border-[#B6D4BF]'
                          }`}
                        >
                          <span
                            aria-hidden="true"
                            className={`absolute left-0 top-0 bottom-0 w-[3.5px] ${
                              reportSummary.issueCount > 0
                                ? 'bg-[#881337]'
                                : reportSummary.attentionCount > 0
                                ? 'bg-[#B45309]'
                                : 'bg-[#166534]'
                            }`}
                          />
                          <div className="flex items-center justify-between gap-2">
                            <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-stone-900 truncate">
                              {isGeneratingReport && (
                                <span
                                  className="w-1.5 h-1.5 rounded-full bg-[#1E3A5F] animate-pulse shrink-0"
                                  aria-hidden="true"
                                />
                              )}
                              <span>Báo cáo rủi ro</span>
                            </span>
                            <ArrowRight
                              className="w-3.5 h-3.5 text-stone-500 group-hover:text-stone-900 group-hover:translate-x-0.5 transition-all shrink-0"
                              aria-hidden="true"
                            />
                          </div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] tabular-nums text-stone-700">
                            <span
                              className={
                                reportSummary.issueCount > 0
                                  ? 'font-semibold text-[#881337]'
                                  : ''
                              }
                            >
                              {reportSummary.issueCount} thiếu
                            </span>
                            <span className="text-stone-400">·</span>
                            <span>{reportSummary.attentionCount} lưu ý</span>
                            <span className="text-stone-400">·</span>
                            <span className="text-[#166534] font-medium">
                              {reportSummary.okCount} đạt chuẩn
                            </span>
                          </div>
                        </button>
                      </motion.div>
                    </div>
                  </motion.div>
                )}
              </div>
            </>
          )}

          {/* Collapsed-by-default Interactive Unit Inspector Drawer */}
          <AnimatePresence>
            {drawerMode !== 'closed' && (
              <ContractUnitInspectorDrawer
                model={full7Model}
                currentStepIndex={currentStepIndex}
                selectedUnitId={selectedUnitId}
                sevenNodeSelection={effective7Selection}
                sevenNodeTrace={sevenNodeTrace}
                onClose={() => {
                  setDrawerMode('closed');
                  setSevenNodeSelection(null);
                }}
                onSelectUnit={(unitId) => {
                  const target = unit7Nodes.find((u) => u.id === unitId);
                  if (target) {
                    handleOpenMajorNodeInspector(
                      target.legacyNodeId || target.id,
                      target.clauseId
                    );
                  }
                }}
                onSelectFact={(factNode) => {
                  setSevenNodeSelection({ kind: 'fact', id: factNode.id });
                  if (factNode.clauseId) {
                    const targetUnit = unit7Nodes.find(
                      (u) => u.clauseId === factNode.clauseId
                    );
                    if (targetUnit) setSelectedUnitId(targetUnit.id);
                  }
                }}
                onSelectConceptInstance={(ciNode) => {
                  setSevenNodeSelection({ kind: 'conceptInstance', id: ciNode.id });
                  if (ciNode.clauseId) {
                    const targetUnit = unit7Nodes.find(
                      (u) => u.clauseId === ciNode.clauseId
                    );
                    if (targetUnit) setSelectedUnitId(targetUnit.id);
                  }
                }}
                onSelectParty={(partyId) => {
                  setSevenNodeSelection({ kind: 'party', id: partyId });
                }}
              />
            )}
          </AnimatePresence>
        </div>
      </LayoutGroup>

      {/* Temporal Version Timeline Docked Across Full-Width Stage Bottom */}
      <div className="border-t border-stone-200 bg-[#FAF9F6] px-4 lg:px-6 py-3 relative overflow-hidden">
        {currentStepIndex === 5 && (
          <motion.div
            aria-hidden="true"
            initial={{ scaleX: 0, opacity: 0.9 }}
            animate={{ scaleX: 1, opacity: 1 }}
            transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
            style={{ transformOrigin: 'left' }}
            className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-[#1E3A5F] via-[#166534] to-[#1E3A5F]"
          />
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
          <div className="flex items-center gap-2">
            <CalendarClock className="w-4 h-4 text-[#1E3A5F]" aria-hidden="true" />
            <span className="text-xs font-semibold text-stone-900">
              Timeline Phiên bản Pháp luật theo thời điểm đánh giá
            </span>
            {currentStepIndex === 5 && (
              <span className="text-[11px] font-medium text-[#1E3A5F]">
                · Đang lọc phiên bản hiệu lực theo ngày ký
              </span>
            )}
          </div>
          <span className="text-xs font-mono font-medium text-stone-700 bg-white border border-stone-200 rounded px-2 py-0.5 tabular-nums">
            Mốc ngày ký: {formattedSigningDate}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {scenario.legalVersions.map((ver, idx) => {
            const isEffective = ver.inForce ?? activeVersionIds.has(ver.id);
            const showVersionFocus = currentStepIndex >= 5;

            return (
              <motion.div
                key={ver.id}
                animate={{
                  opacity: !showVersionFocus ? 0.88 : isEffective ? 1 : 0.42,
                }}
                transition={{ duration: 0.3, delay: showVersionFocus ? idx * 0.05 : 0 }}
                className={`rounded border px-3 py-2 transition-colors ${
                  !showVersionFocus
                    ? 'bg-white border-stone-200'
                    : isEffective
                    ? 'bg-white border-[#1E3A5F]'
                    : 'bg-stone-100/80 border-stone-200'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-mono font-semibold text-stone-900 truncate">
                    {ver.documentCode}
                  </span>
                  {showVersionFocus && (
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-semibold shrink-0 ${
                        isEffective ? 'text-[#166534]' : 'text-stone-500'
                      }`}
                    >
                      {isEffective && <Check className="w-3 h-3" aria-hidden="true" />}
                      {isEffective ? 'Áp dụng' : 'Không phù hợp'}
                    </span>
                  )}
                </div>
                <div
                  className={`text-xs font-medium truncate mt-0.5 ${
                    showVersionFocus && !isEffective
                      ? 'text-stone-500 line-through'
                      : 'text-stone-800'
                  }`}
                >
                  {ver.title}
                </div>
                <div className="text-[11px] text-stone-500 mt-0.5 truncate">
                  {ver.statusLabel}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
