import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  ArrowRight,
  BookOpenText,
  Building2,
  CornerDownRight,
  FileCode2,
  GitBranch,
  Hash,
  Layers,
  Link2,
  Sparkles,
  UserCheck,
  X,
} from 'lucide-react';
import {
  getUnitDetailBundle,
  type SevenNodeSelection,
  type SevenNodeTrace,
} from '../engine/contractGraph';
import type {
  AnalysisScenario,
  ContractGraph7Node,
  ContractGraphModel,
} from '../types/contract';

interface CenteredContractGraphTreeProps {
  scenario: AnalysisScenario;
  fullModel: ContractGraphModel;
  currentStepIndex: number;
  assemblyStage: 'folio_scan' | 'graph_build' | 'docking_left' | 'docked';
  stepElapsedMs: number;
  selectedUnitId: string | null;
  onSelectUnit: (unitId: string) => void;
}

interface TreeEdgePath {
  id: string;
  d: string;
  stroke: string;
  strokeWidth: number;
  dashed: boolean;
  label?: string;
  labelX?: number;
  labelY?: number;
  isAmends?: boolean;
}

export function CenteredContractGraphTree({
  scenario,
  fullModel,
  currentStepIndex,
  assemblyStage,
  stepElapsedMs,
  selectedUnitId,
  onSelectUnit,
}: CenteredContractGraphTreeProps) {
  const treeRef = useRef<HTMLDivElement | null>(null);
  const elRefs = useRef<Record<string, HTMLElement | null>>({});
  const lastSigRef = useRef<string>('');
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 });
  const [edgePaths, setEdgePaths] = useState<TreeEdgePath[]>([]);

  const contractNode = useMemo(
    () => fullModel.nodes.find((n) => n.nodeType === 'Contract') ?? null,
    [fullModel.nodes]
  );
  const partNodes = useMemo(
    () => fullModel.nodes.filter((n) => n.nodeType === 'Part'),
    [fullModel.nodes]
  );
  const partyNodes = useMemo(
    () => fullModel.nodes.filter((n) => n.nodeType === 'Party'),
    [fullModel.nodes]
  );
  const unitNodes = useMemo(() => {
    const allUnits = fullModel.nodes.filter((n) => n.nodeType === 'Unit');
    const unitIds = new Set(allUnits.map((n) => n.id));
    const childUnitIds = new Set(
      fullModel.edges
        .filter((e) => e.edgeType === 'CHILD_OF' && unitIds.has(e.to))
        .map((e) => e.from)
    );
    const parents = allUnits.filter((n) => !childUnitIds.has(n.id));
    if (parents.length <= 6) return parents;
    const score = new Map<string, number>();
    for (const e of fullModel.edges) {
      if (e.edgeType === 'AMENDS' || e.edgeType === 'REFERS_TO') {
        score.set(e.from, (score.get(e.from) || 0) + 4);
        score.set(e.to, (score.get(e.to) || 0) + 4);
      } else if (e.edgeType === 'HAS_VALUE' || e.edgeType === 'EVIDENCE') {
        score.set(e.from, (score.get(e.from) || 0) + 2);
        score.set(e.to, (score.get(e.to) || 0) + 2);
      }
    }
    const chosen = new Set(
      [...parents]
        .sort((a, b) => (score.get(b.id) || 0) - (score.get(a.id) || 0))
        .slice(0, 6)
        .map((u) => u.id)
    );
    return parents.filter((u) => chosen.has(u.id));
  }, [fullModel.nodes, fullModel.edges]);
  const valueNodes = useMemo(
    () => fullModel.nodes.filter((n) => n.nodeType === 'Value'),
    [fullModel.nodes]
  );

  // Pick up to 1 concise primary Value leaf per Unit so the complex graph reads cleanly without vertical bloat
  const primaryValuesByUnit = useMemo(() => {
    const map = new Map<string, ContractGraph7Node>();
    for (const edge of fullModel.edges) {
      if (edge.edgeType !== 'HAS_VALUE') continue;
      if (!map.has(edge.from)) {
        const val = valueNodes.find((v) => v.id === edge.to);
        if (val) map.set(edge.from, val);
      }
    }
    return map;
  }, [fullModel.edges, valueNodes]);

  const leafValues = useMemo(
    () => Array.from(primaryValuesByUnit.entries()),
    [primaryValuesByUnit]
  );

  // Layered progressive graph construction: Contract -> Part/Party -> Unit -> Value -> Cross-links
  const isSettledBuild = currentStepIndex >= 1;
  const hasContractRoot = Boolean(contractNode);
  const showStructureLayer =
    hasContractRoot &&
    (isSettledBuild ||
      (assemblyStage !== 'folio_scan' && stepElapsedMs >= 700));
  const visibleUnitCount = isSettledBuild
    ? unitNodes.length
    : !hasContractRoot || assemblyStage === 'folio_scan' || stepElapsedMs < 1300
    ? 0
    : Math.min(unitNodes.length, Math.floor((stepElapsedMs - 1300) / 170) + 1);
  const visibleUnits = useMemo(
    () => unitNodes.slice(0, visibleUnitCount),
    [unitNodes, visibleUnitCount]
  );
  const visibleUnitIdSet = useMemo(
    () => new Set(visibleUnits.map((u) => u.id)),
    [visibleUnits]
  );

  const visibleLeafCount = isSettledBuild
    ? leafValues.length
    : !hasContractRoot || assemblyStage === 'folio_scan' || stepElapsedMs < 2250
    ? 0
    : Math.min(leafValues.length, Math.floor((stepElapsedMs - 2250) / 120) + 1);
  const visibleLeaves = useMemo(
    () => leafValues.slice(0, visibleLeafCount),
    [leafValues, visibleLeafCount]
  );
  const showCrossEdges =
    hasContractRoot &&
    (isSettledBuild ||
      (assemblyStage !== 'folio_scan' && stepElapsedMs >= 2750));

  const buildPhaseIndex = !hasContractRoot
    ? 0
    : isSettledBuild || (showCrossEdges && visibleLeafCount >= leafValues.length)
    ? 4
    : visibleLeafCount > 0 || showCrossEdges
    ? 3
    : visibleUnitCount > 0
    ? 2
    : showStructureLayer
    ? 1
    : 0;

  const formattedSigningDate = useMemo(
    () => scenario.signingDateIso.split('-').reverse().join('/'),
    [scenario.signingDateIso]
  );

  const measureTreeEdges = useCallback(() => {
    const container = treeRef.current;
    if (!container) return;
    const cRect = container.getBoundingClientRect();
    const w = Math.round(cRect.width);
    const h = Math.round(cRect.height);
    if (w < 80 || h < 80) return;

    const getPt = (id: string) => {
      const el = elRefs.current[id];
      if (!el) return null;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return null;
      return {
        left: r.left - cRect.left,
        right: r.right - cRect.left,
        top: r.top - cRect.top,
        bottom: r.bottom - cRect.top,
        cx: r.left - cRect.left + r.width / 2,
        cy: r.top - cRect.top + r.height / 2,
      };
    };

    const next: TreeEdgePath[] = [];

    // Layer 1: Contract -> Part & Contract -> Party
    const cPt = contractNode ? getPt(contractNode.id) : null;
    if (cPt && showStructureLayer) {
      for (const part of partNodes) {
        const pPt = getPt(part.id);
        if (!pPt) continue;
        const x1 = cPt.right;
        const y1 = cPt.cy;
        const x2 = pPt.left;
        const y2 = pPt.cy;
        const mx = x1 + (x2 - x1) * 0.48;
        next.push({
          id: `c_part_${part.id}`,
          d: `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(mx)} ${Math.round(y1)}, ${Math.round(mx)} ${Math.round(y2)}, ${Math.round(x2)} ${Math.round(y2)}`,
          stroke: part.label.includes('Phụ lục') ? '#9F1239' : '#1E3A5F',
          strokeWidth: 1.5,
          dashed: false,
        });
      }

      for (const party of partyNodes) {
        const pyPt = getPt(party.id);
        if (!pyPt) continue;
        const x1 = cPt.right;
        const y1 = cPt.cy + 14;
        const x2 = pyPt.left;
        const y2 = pyPt.cy;
        const mx = x1 + (x2 - x1) * 0.45;
        next.push({
          id: `c_party_${party.id}`,
          d: `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(mx)} ${Math.round(y1)}, ${Math.round(mx)} ${Math.round(y2)}, ${Math.round(x2)} ${Math.round(y2)}`,
          stroke: '#64748B',
          strokeWidth: 1.15,
          dashed: true,
        });
      }
    }

    // Layer 2: Part -> Unit & Unit -> Parent Unit (CHILD_OF)
    for (const unit of visibleUnits) {
      const uPt = getPt(unit.id);
      if (!uPt) continue;

      if (unit.parentUnitId && visibleUnitIdSet.has(unit.parentUnitId)) {
        const parentPt = getPt(unit.parentUnitId);
        if (parentPt) {
          const x1 = parentPt.left + 12;
          const y1 = parentPt.bottom;
          const x2 = uPt.left;
          const y2 = uPt.cy;
          next.push({
            id: `u_child_${unit.id}`,
            d: `M ${Math.round(x1)} ${Math.round(y1)} L ${Math.round(x1)} ${Math.round(y2)} L ${Math.round(x2)} ${Math.round(y2)}`,
            stroke: '#B45309',
            strokeWidth: 1.35,
            dashed: false,
          });
        }
      } else if (unit.partId) {
        const pPt = getPt(unit.partId);
        if (pPt) {
          const x1 = pPt.right;
          const y1 = pPt.cy;
          const x2 = uPt.left;
          const y2 = uPt.cy;
          const mx = x1 + (x2 - x1) * 0.48;
          next.push({
            id: `p_unit_${unit.id}`,
            d: `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(mx)} ${Math.round(y1)}, ${Math.round(mx)} ${Math.round(y2)}, ${Math.round(x2)} ${Math.round(y2)}`,
            stroke: unit.sublabel?.includes('Phụ lục') ? '#D8A3B1' : '#94A3B8',
            strokeWidth: 1.25,
            dashed: false,
          });
        }
      }
    }

    // Layer 3a: Cross-clause REFERS_TO (thin) & AMENDS (prominent) between Units
    if (showCrossEdges) {
      for (const edge of fullModel.edges) {
        if (edge.edgeType !== 'REFERS_TO' && edge.edgeType !== 'AMENDS') continue;
        if (!visibleUnitIdSet.has(edge.from) || !visibleUnitIdSet.has(edge.to)) continue;
        const fPt = getPt(edge.from);
        const tPt = getPt(edge.to);
        if (!fPt || !tPt) continue;

        const isAmends = edge.edgeType === 'AMENDS';
        const ctrlX = Math.min(fPt.left, tPt.left) - (isAmends ? 32 : 18);
        const amendsLabel = isAmends
          ? edge.effectiveDateLabel
            ? `Sửa đổi · ${edge.effectiveDateLabel}`
            : 'Sửa đổi'
          : undefined;
        const amendsWidth = amendsLabel
          ? Math.max(68, Math.round(amendsLabel.length * 5.0 + 14))
          : 0;
        next.push({
          id: `u_rel_${edge.id}`,
          d: `M ${Math.round(fPt.left)} ${Math.round(fPt.cy)} C ${Math.round(ctrlX)} ${Math.round(fPt.cy)}, ${Math.round(ctrlX)} ${Math.round(tPt.cy)}, ${Math.round(tPt.left)} ${Math.round(tPt.cy)}`,
          stroke: isAmends ? '#881337' : '#B45309',
          strokeWidth: isAmends ? 2.1 : 1.0,
          dashed: !isAmends,
          isAmends,
          label: amendsLabel,
          labelX: Math.round(Math.min(fPt.left, tPt.left) - amendsWidth / 2 - 28),
          labelY: Math.round((fPt.cy + tPt.cy) / 2),
        });
      }
    }

    // Layer 3b: Unit -> Value / Fact leaf nodes
    for (const [unitId, valNode] of visibleLeaves) {
      const uPt = getPt(unitId);
      const vPt = getPt(valNode.id);
      if (!uPt || !vPt) continue;
      const x1 = uPt.right;
      const y1 = uPt.cy;
      const x2 = vPt.left;
      const y2 = vPt.cy;
      const mx = x1 + (x2 - x1) * 0.45;
      next.push({
        id: `u_val_${valNode.id}`,
        d: `M ${Math.round(x1)} ${Math.round(y1)} C ${Math.round(mx)} ${Math.round(y1)}, ${Math.round(mx)} ${Math.round(y2)}, ${Math.round(x2)} ${Math.round(y2)}`,
        stroke: '#CA8A04',
        strokeWidth: 1.15,
        dashed: true,
      });
    }

    const sig = JSON.stringify({
      w,
      h,
      p: next.map((x) => [x.id, x.d, x.stroke, x.label]),
    });
    if (sig !== lastSigRef.current) {
      lastSigRef.current = sig;
      setSvgSize({ width: w, height: h });
      setEdgePaths(next);
    }
  }, [
    contractNode,
    fullModel.edges,
    partNodes,
    partyNodes,
    showCrossEdges,
    showStructureLayer,
    visibleLeaves,
    visibleUnitIdSet,
    visibleUnits,
  ]);

  useEffect(() => {
    const raf = window.requestAnimationFrame(measureTreeEdges);
    const t1 = window.setTimeout(measureTreeEdges, 140);
    return () => {
      window.cancelAnimationFrame(raf);
      window.clearTimeout(t1);
    };
  }, [measureTreeEdges, visibleUnitCount, visibleLeafCount, showStructureLayer, scenario.id]);

  const buildStages = [
    '1. Contract Root',
    '2. Part & Party',
    '3. Unit (Điều khoản)',
    '4. Value & Relations',
  ];
  const buildStatusLabel = !hasContractRoot
    ? 'Đang đọc văn bản & trích xuất thực thể cấu trúc...'
    : buildPhaseIndex === 0
    ? 'Khởi tạo gốc Contract Document...'
    : buildPhaseIndex === 1
    ? 'Liên kết cấu trúc Part & Chủ thể Party (HAS_PART · HAS_PARTY)...'
    : buildPhaseIndex === 2
    ? `Xây cây Điều khoản trọng tâm (${visibleUnits.length}/${unitNodes.length} Unit · HAS_UNIT)...`
    : buildPhaseIndex === 3
    ? 'Gắn Giá trị định lượng (HAS_VALUE) & liên kết AMENDS / REFERS_TO...'
    : 'Hoàn tất xây dựng Contract Graph 4 tầng · Chọn một Điều khoản để xem chi tiết';

  return (
    <div
      data-testid="step1-center-assembly"
      className="min-h-[420px] flex flex-col items-center justify-center py-2.5 gap-3"
    >
      <div className="w-full max-w-[1080px] px-2 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] bg-stone-50 border border-stone-200 px-3 py-1.5 rounded">
          <span className="font-medium text-stone-800">{buildStatusLabel}</span>
          <span className="font-mono text-[10px] text-stone-500 tabular-nums">
            Tầng {Math.min(4, buildPhaseIndex + 1)}/4
          </span>
        </div>
        <div className="hidden md:grid grid-cols-[178px_162px_minmax(0,1fr)_172px] gap-x-14 text-[10px] font-medium">
          {buildStages.map((stageLabel, idx) => {
            const active = hasContractRoot && buildPhaseIndex === idx;
            const done = hasContractRoot && buildPhaseIndex > idx;
            return (
              <div
                key={stageLabel}
                className={`px-2 py-1 rounded border transition-colors ${
                  active
                    ? 'bg-[#1E3A5F] text-white border-[#1E3A5F]'
                    : done
                    ? 'bg-[#EDF3F9] text-[#1E3A5F] border-[#CBD5E1]'
                    : 'bg-white text-stone-400 border-stone-200'
                }`}
              >
                {stageLabel}
              </div>
            );
          })}
        </div>
      </div>

      <motion.div
        ref={treeRef}
        layoutId="contract-graph-shell"
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-[1080px] grid grid-cols-1 md:grid-cols-[178px_162px_minmax(0,1fr)_172px] gap-6 md:gap-x-14 items-center px-2"
      >
        {svgSize.width > 0 && (
          <>
            <svg
              aria-hidden="true"
              className="hidden md:block absolute inset-0 z-0 w-full h-full pointer-events-none overflow-visible"
              viewBox={`0 0 ${svgSize.width} ${svgSize.height}`}
            >
              {edgePaths.map((ep) => (
                <motion.path
                  key={ep.id}
                  initial={
                    ep.dashed ? { opacity: 0 } : { pathLength: 0, opacity: 0.25 }
                  }
                  animate={
                    ep.dashed
                      ? { opacity: ep.isAmends ? 0.96 : 0.78 }
                      : { pathLength: 1, opacity: ep.isAmends ? 0.96 : 0.78 }
                  }
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                  d={ep.d}
                  fill="none"
                  stroke={ep.stroke}
                  strokeWidth={ep.strokeWidth}
                  strokeDasharray={ep.dashed ? '4 4' : undefined}
                  strokeLinecap="round"
                />
              ))}
            </svg>
            <svg
              aria-hidden="true"
              className="hidden md:block absolute inset-0 z-20 w-full h-full pointer-events-none overflow-visible"
              viewBox={`0 0 ${svgSize.width} ${svgSize.height}`}
            >
              {edgePaths.map((ep) => {
                if (!ep.label || ep.labelX === undefined || ep.labelY === undefined) {
                  return null;
                }
                const rectWidth = Math.max(68, Math.round(ep.label.length * 5.0 + 14));
                return (
                  <g key={`${ep.id}_label`} transform={`translate(${ep.labelX}, ${ep.labelY})`}>
                    <rect
                      x="0"
                      y="-9"
                      width={rectWidth}
                      height="18"
                      rx="3"
                      fill="#FFFFFF"
                      stroke={ep.stroke}
                      strokeWidth="1.15"
                    />
                    <text
                      x={rectWidth / 2}
                      y="3.2"
                      textAnchor="middle"
                      fontSize="8.5"
                      fontWeight="700"
                      fill={ep.stroke}
                    >
                      {ep.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </>
        )}

        {/* Col 1: Uploaded Contract Document */}
        <div className="relative z-10 flex flex-col justify-center">
          {contractNode ? (
            <div
              ref={(el) => {
                elRefs.current[contractNode.id] = el;
              }}
              data-testid="contract-source-anchor"
              className="chamfer-tr-lg bg-[#1E3A5F] text-white p-4 space-y-2 shadow-xs"
            >
              <div className="text-[10px] font-medium text-slate-300">
                {scenario.isDemo ? 'Hợp đồng gốc' : 'Hợp đồng tải lên'}
              </div>
              <div className="font-serif text-[13.5px] font-semibold leading-snug text-white">
                {contractNode.label}
              </div>
              <div className="pt-1.5 border-t border-white/15 space-y-0.5">
                {scenario.sections.map((sec) => (
                  <div
                    key={sec.id}
                    className="text-[10px] font-mono text-slate-200 truncate"
                  >
                    · {sec.fileName}
                  </div>
                ))}
              </div>
              <div className="text-[10px] font-mono text-slate-300 pt-0.5 tabular-nums">
                Ký {formattedSigningDate}
              </div>
            </div>
          ) : (
            <div className="chamfer-tr-lg bg-[#1E3A5F]/90 text-white p-4 space-y-2 shadow-xs animate-pulse">
              <div className="text-[10px] font-medium text-slate-300">
                Hồ sơ đang nạp
              </div>
              <div className="font-serif text-[13px] font-semibold text-white">
                {scenario.title || 'Đang bóc tách hợp đồng...'}
              </div>
              <div className="text-[10px] font-mono text-slate-300">
                Đang tạo các tầng cấu trúc...
              </div>
            </div>
          )}
        </div>

        {/* Col 2: Document Parts + Parties */}
        <div className="relative z-10 space-y-3">
          {showStructureLayer && (
            <>
              <div className="space-y-2">
                {partNodes.map((part) => {
                  const isAddendum = part.label.toLowerCase().includes('phụ lục');
                  return (
                    <motion.div
                      key={part.id}
                      ref={(el) => {
                        elRefs.current[part.id] = el;
                      }}
                      initial={{ opacity: 0, scale: 0.9, x: -10 }}
                      animate={{ opacity: 1, scale: 1, x: 0 }}
                      transition={{ duration: 0.25 }}
                      className={`chamfer-tr px-3 py-2 relative ${
                        isAddendum ? 'bg-[#FDF0F3]' : 'bg-[#EDF3F9]'
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className={`absolute left-0 top-0 bottom-0 w-[3px] ${
                          isAddendum ? 'bg-[#9F1239]' : 'bg-[#1E3A5F]'
                        }`}
                      />
                      <div className="text-[11.5px] font-semibold text-stone-900 truncate pl-1">
                        {part.label}
                      </div>
                      {part.sublabel && (
                        <div className="text-[9.5px] font-mono text-stone-500 truncate pl-1 mt-0.5">
                          {part.sublabel}
                        </div>
                      )}
                    </motion.div>
                  );
                })}
              </div>

              <div className="space-y-1.5 pt-1">
                {partyNodes.map((party, idx) => (
                  <motion.div
                    key={party.id}
                    ref={(el) => {
                      elRefs.current[party.id] = el;
                    }}
                    initial={{ opacity: 0, scale: 0.9, x: -8 }}
                    animate={{ opacity: 1, scale: 1, x: 0 }}
                    transition={{ duration: 0.25, delay: 0.08 + idx * 0.06 }}
                    className="chamfer-tr bg-[#F4F6F9] px-2.5 py-1.5"
                  >
                    <div className="text-[10.5px] font-semibold text-[#1E3A5F] truncate">
                      {party.label}
                    </div>
                    {party.sublabel && (
                      <div className="text-[9.5px] text-stone-600 truncate">
                        {party.sublabel}
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Col 3: Clause Units & Sub-Units */}
        <div className="relative z-10 space-y-1.5">
          {visibleUnits.map((unit) => {
            const isChild = Boolean(unit.parentUnitId);
            const isSelected = selectedUnitId === unit.id;
            const isAddendumUnit = unit.sublabel?.includes('Phụ lục');
            return (
              <motion.div
                key={unit.id}
                ref={(el) => {
                  elRefs.current[unit.id] = el;
                }}
                initial={{ opacity: 0, scale: 0.9, x: -10 }}
                animate={{ opacity: 1, scale: 1, x: 0 }}
                transition={{ duration: 0.22 }}
                className={isChild ? 'pl-4' : ''}
              >
                <button
                  type="button"
                  onClick={() => onSelectUnit(unit.id)}
                  className={`chamfer-tr w-full text-left px-2.5 py-1.5 relative flex items-center justify-between gap-2 transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-[#E5EEF7] ring-1 ring-inset ring-[#1E3A5F]'
                      : isAddendumUnit
                      ? 'bg-[#FDF0F3] hover:bg-[#FCE6EC]'
                      : 'bg-[#FEF6D6] hover:bg-[#FDF0C2]'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`absolute left-0 top-0 bottom-0 w-[3px] ${
                      isAddendumUnit
                        ? 'bg-[#9F1239]'
                        : isChild
                        ? 'bg-[#B45309]'
                        : 'bg-[#EAB308]'
                    }`}
                  />
                  <div className="min-w-0 flex items-center gap-1.5 pl-0.5">
                    {isChild && (
                      <CornerDownRight
                        className="w-3 h-3 text-[#B45309] shrink-0"
                        aria-hidden="true"
                      />
                    )}
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold text-stone-900 truncate">
                        {unit.label}
                      </div>
                    </div>
                  </div>
                </button>
              </motion.div>
            );
          })}
        </div>

        {/* Col 4: Extracted Values & Quantified Facts */}
        <div className="relative z-10 space-y-1.5">
          {visibleLeaves.map(([, val]) => (
            <motion.div
              key={val.id}
              ref={(el) => {
                elRefs.current[val.id] = el;
              }}
              initial={{ opacity: 0, scale: 0.85, x: -10 }}
              animate={{ opacity: 1, scale: 1, x: 0 }}
              transition={{ duration: 0.22 }}
              className="rounded border border-[#E7D3AD] bg-[#FDFBF5] px-2.5 py-1 text-[10.5px] font-mono font-medium text-[#92400E] truncate"
            >
              {val.label}
            </motion.div>
          ))}
        </div>
      </motion.div>
      <div className="w-full max-w-[1080px] px-2 pt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-stone-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-4 h-[1.5px] bg-[#1E3A5F]" /> HAS_PART / HAS_UNIT
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-4 border-t border-dashed border-slate-500" /> HAS_PARTY
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-4 h-[2px] bg-[#881337]" /> AMENDS (Sửa đổi)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-4 border-t border-dashed border-amber-700" /> REFERS_TO (Dẫn chiếu)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-4 border-t border-dashed border-yellow-600" /> HAS_VALUE
        </span>
      </div>
    </div>
  );
}

interface ContractUnitInspectorDrawerProps {
  model: ContractGraphModel;
  currentStepIndex: number;
  selectedUnitId: string | null;
  sevenNodeSelection: SevenNodeSelection | null;
  sevenNodeTrace: SevenNodeTrace;
  onClose: () => void;
  onSelectUnit: (unitId: string) => void;
  onSelectFact: (factNode: ContractGraph7Node) => void;
  onSelectConceptInstance: (ciNode: ContractGraph7Node) => void;
  onSelectParty: (partyId: string) => void;
}

export function ContractUnitInspectorDrawer({
  model,
  currentStepIndex,
  selectedUnitId,
  sevenNodeSelection,
  sevenNodeTrace,
  onClose,
  onSelectUnit,
  onSelectFact,
  onSelectConceptInstance,
  onSelectParty,
}: ContractUnitInspectorDrawerProps) {
  const effectiveUnitId = useMemo(() => {
    if (selectedUnitId) return selectedUnitId;
    const firstUnit = model.nodes.find((n) => n.nodeType === 'Unit');
    return firstUnit?.id ?? null;
  }, [selectedUnitId, model.nodes]);

  const bundle = useMemo(
    () =>
      effectiveUnitId
        ? getUnitDetailBundle(model, effectiveUnitId, currentStepIndex)
        : null,
    [model, effectiveUnitId, currentStepIndex]
  );

  const allParties = useMemo(
    () => model.nodes.filter((n) => n.nodeType === 'Party'),
    [model.nodes]
  );

  if (!bundle) return null;

  const isValuesUnlocked = currentStepIndex >= 1;
  const isConceptInstancesUnlocked = currentStepIndex >= 2;

  return (
    <motion.div
      data-testid="unit-inspector-drawer"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      transition={{ duration: 0.22 }}
      className="mt-4 rounded border border-stone-200 bg-[#FAF9F6] overflow-hidden"
    >
      <div className="px-4 py-2.5 bg-white border-b border-stone-200 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <FileCode2 className="w-4 h-4 text-[#1E3A5F] shrink-0" aria-hidden="true" />
          <span className="font-serif text-sm font-semibold text-stone-900 truncate">
            {bundle.unit.label}
          </span>
          {bundle.unit.pageNumber && (
            <span className="text-[11px] font-mono text-[#1E3A5F] bg-[#EDF3F9] px-2 py-0.5 rounded tabular-nums">
              Trang {bundle.unit.pageNumber}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Đóng chi tiết điều khoản"
          className="p-1 rounded text-stone-400 hover:text-stone-800 hover:bg-stone-100 transition-colors cursor-pointer"
        >
          <X className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>

      <div className="p-4 space-y-3">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <div className="lg:col-span-7 bg-white border border-stone-200 rounded p-3 space-y-2">
            <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-stone-700">
              <span className="inline-flex items-center gap-1.5">
                <BookOpenText className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
                Nguyên văn điều khoản
              </span>
              {sevenNodeTrace.highlightedUnitIds.has(bundle.unit.id) &&
                sevenNodeSelection &&
                sevenNodeSelection.kind !== 'unit' && (
                  <span className="text-[10px] font-mono font-semibold text-[#166534] bg-[#F2F8F4] border border-[#BBD7C5] px-1.5 py-0.5 rounded">
                    {sevenNodeSelection.kind === 'fact'
                      ? '← Bằng chứng dữ kiện'
                      : '← Khái niệm liên kết'}
                  </span>
                )}
            </div>
            <p className="text-[13px] leading-relaxed text-stone-800">
              {bundle.unit.excerpt || bundle.unit.label}
            </p>
          </div>

          <div className="lg:col-span-5 bg-white border border-stone-200 rounded p-3 space-y-2">
            <div className="text-[11px] font-semibold text-stone-700 flex items-center gap-1.5">
              <GitBranch className="w-3.5 h-3.5 text-[#881337]" aria-hidden="true" />
              Liên kết nội bộ &amp; Sửa đổi
            </div>
            <div className="space-y-1.5 text-[11px]">
              {bundle.parentUnit && (
                <button
                  type="button"
                  onClick={() => onSelectUnit(bundle.parentUnit!.id)}
                  className="w-full text-left px-2 py-1 rounded bg-[#FEF6D6]/70 hover:bg-[#FEF6D6] flex items-center justify-between gap-2 cursor-pointer"
                >
                  <span className="font-mono text-[10px] font-semibold text-[#B45309]">
                    Thuộc →
                  </span>
                  <span className="text-stone-800 truncate flex-1">
                    {bundle.parentUnit.label}
                  </span>
                </button>
              )}

              {bundle.childUnits.map((cu) => (
                <button
                  key={cu.id}
                  type="button"
                  onClick={() => onSelectUnit(cu.id)}
                  className="w-full text-left px-2 py-1 rounded bg-[#FEF6D6]/50 hover:bg-[#FEF6D6] flex items-center justify-between gap-2 cursor-pointer"
                >
                  <span className="font-mono text-[10px] font-semibold text-[#B45309]">
                    Mục con →
                  </span>
                  <span className="text-stone-800 truncate flex-1">{cu.label}</span>
                </button>
              ))}

              {bundle.amendsUnits.map(({ edge, unit: target }) => (
                <button
                  key={edge.id}
                  type="button"
                  onClick={() => onSelectUnit(target.id)}
                  className="w-full text-left px-2 py-1.5 rounded bg-[#FDF0F3] border border-[#881337]/40 hover:bg-[#FCE6EC] flex items-center justify-between gap-2 cursor-pointer"
                >
                  <span className="font-mono text-[10px] font-bold text-[#881337] shrink-0">
                    Sửa đổi →
                  </span>
                  <span className="text-stone-900 font-medium truncate flex-1">
                    {target.label}
                  </span>
                  {edge.effectiveDateLabel && (
                    <span className="text-[10px] font-mono text-[#881337] shrink-0">
                      {edge.effectiveDateLabel}
                    </span>
                  )}
                </button>
              ))}

              {bundle.amendedByUnits.map(({ edge, unit: src }) => (
                <button
                  key={edge.id}
                  type="button"
                  onClick={() => onSelectUnit(src.id)}
                  className="w-full text-left px-2 py-1.5 rounded bg-[#FDF0F3] border border-[#881337]/40 hover:bg-[#FCE6EC] flex items-center justify-between gap-2 cursor-pointer"
                >
                  <span className="font-mono text-[10px] font-bold text-[#881337] shrink-0">
                    Bị sửa bởi →
                  </span>
                  <span className="text-stone-900 font-medium truncate flex-1">
                    {src.label}
                  </span>
                  {edge.effectiveDateLabel && (
                    <span className="text-[10px] font-mono text-[#881337] shrink-0">
                      {edge.effectiveDateLabel}
                    </span>
                  )}
                </button>
              ))}

              {bundle.refersToUnits.map(({ edge, unit: target }) => (
                <button
                  key={edge.id}
                  type="button"
                  onClick={() => onSelectUnit(target.id)}
                  className="w-full text-left px-2 py-1 rounded border border-dashed border-[#D9B36C] bg-white hover:bg-[#FDFBF7] flex items-center justify-between gap-2 cursor-pointer"
                >
                  <span className="font-mono text-[10px] text-[#B45309] shrink-0">
                    Dẫn chiếu →
                  </span>
                  <span className="text-stone-700 truncate flex-1">{target.label}</span>
                </button>
              ))}

              {bundle.referredByUnits.map(({ edge, unit: src }) => (
                <button
                  key={edge.id}
                  type="button"
                  onClick={() => onSelectUnit(src.id)}
                  className="w-full text-left px-2 py-1 rounded border border-dashed border-[#D9B36C] bg-white hover:bg-[#FDFBF7] flex items-center justify-between gap-2 cursor-pointer"
                >
                  <span className="font-mono text-[10px] text-[#B45309] shrink-0">
                    Được dẫn chiếu bởi →
                  </span>
                  <span className="text-stone-700 truncate flex-1">{src.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {(isValuesUnlocked || isConceptInstancesUnlocked) && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {isValuesUnlocked && (
              <div className="bg-white border border-stone-200 rounded p-3 space-y-2">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold text-stone-800">
                  <Hash className="w-3.5 h-3.5 text-[#B45309]" aria-hidden="true" />
                  <span>Giá trị trong văn bản</span>
                </div>
                {bundle.values.length === 0 ? (
                  <div className="text-[11px] text-stone-400">Không có giá trị định lượng riêng.</div>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {bundle.values.map((val) => (
                      <div
                        key={val.id}
                        className="rounded border border-[#E7D3AD] bg-[#FDF8EE] px-2 py-1 text-[11px] font-mono font-medium text-[#92400E]"
                      >
                        {val.label}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {isValuesUnlocked && (
              <div className="bg-white border border-stone-200 rounded p-3 space-y-2">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold text-stone-800">
                  <Layers className="w-3.5 h-3.5 text-[#1E3A5F]" aria-hidden="true" />
                  <span>Dữ kiện chuẩn hóa</span>
                </div>
                {bundle.facts.length === 0 ? (
                  <div className="text-[11px] text-stone-400">Không có dữ kiện riêng tại đoạn này.</div>
                ) : (
                  <div className="space-y-1.5">
                    {bundle.facts.map((fact) => {
                      const isActive = sevenNodeTrace.highlightedFactIds.has(fact.id);
                      return (
                        <button
                          key={fact.id}
                          type="button"
                          onClick={() => onSelectFact(fact)}
                          className={`w-full text-left px-2.5 py-1.5 rounded border text-[11px] transition-colors cursor-pointer flex items-center justify-between gap-1.5 ${
                            isActive
                              ? 'bg-[#E5EEF7] border-[#1E3A5F] text-stone-950 font-semibold'
                              : 'bg-[#FAF9F6] border-stone-200 hover:border-[#1E3A5F]/50 text-stone-800'
                          }`}
                        >
                          <span className="truncate">{fact.label}</span>
                          <ArrowRight className="w-3 h-3 text-[#1E3A5F] shrink-0" aria-hidden="true" />
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {isConceptInstancesUnlocked && (
              <div className="bg-white border border-stone-200 rounded p-3 space-y-2">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold text-stone-800">
                  <Sparkles className="w-3.5 h-3.5 text-[#166534]" aria-hidden="true" />
                  <span>Khái niệm pháp lý</span>
                </div>
                {bundle.conceptInstances.length === 0 ? (
                  <div className="text-[11px] text-stone-400">Chưa gắn khái niệm tại đoạn này.</div>
                ) : (
                  <div className="space-y-1.5">
                    {bundle.conceptInstances.map(({ node: ci, holderParty }) => {
                      const isActive =
                        sevenNodeTrace.highlightedConceptInstanceIds.has(ci.id);
                      return (
                        <button
                          key={ci.id}
                          type="button"
                          onClick={() => onSelectConceptInstance(ci)}
                          className={`w-full text-left px-2.5 py-1.5 rounded border text-[11px] transition-colors cursor-pointer ${
                            isActive
                              ? 'bg-[#E4EFE8] border-[#166534] text-stone-950'
                              : 'bg-[#F4F6F9] border-stone-200 hover:border-[#166534]/50 text-stone-800'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1.5 font-semibold">
                            <span className="truncate">{ci.label}</span>
                            <Link2 className="w-3 h-3 text-[#166534] shrink-0" aria-hidden="true" />
                          </div>
                          {holderParty && (
                            <div className="text-[10px] text-[#1E3A5F] mt-0.5">
                              Chủ thể: {holderParty.label}
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {isConceptInstancesUnlocked && allParties.length > 0 && (
          <div className="bg-white border border-stone-200 rounded px-3 py-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-stone-700">
              Các bên liên quan:
            </span>
            <div className="flex flex-wrap items-center gap-2">
              {allParties.map((party) => {
                const isHolderHighlighted = sevenNodeTrace.highlightedPartyIds.has(party.id);
                const Icon = party.partyRole === 'employer' ? Building2 : UserCheck;
                return (
                  <button
                    key={party.id}
                    type="button"
                    onClick={() => onSelectParty(party.id)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded border text-[11px] transition-colors cursor-pointer ${
                      isHolderHighlighted
                        ? 'bg-[#1E3A5F] text-white border-[#1E3A5F] font-semibold'
                        : 'bg-[#FAF9F6] text-stone-700 border-stone-200 hover:border-[#1E3A5F]/50'
                    }`}
                  >
                    <Icon className="w-3 h-3 shrink-0" aria-hidden="true" />
                    <span>{party.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
