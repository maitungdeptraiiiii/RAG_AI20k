import type {
  AnalysisScenario,
  SemanticStatus,
  ContractGraphModel,
} from "../types/contract";
import type {
  ScreeningParticle,
  StepChoreographyState,
} from "../engine/pipelineState";

export function emptyScenario(): AnalysisScenario {
  return {
    id: "uploading",
    title: "Hợp đồng đang tải lên",
    subtitle: "Đang đọc tài liệu",
    isDemo: false,
    signingDateIso: "",
    summaryText: "",
    sections: [],
    extractedFacts: [],
    contractNodes: [],
    contractEdges: [],
    concepts: [],
    legalNodes: [],
    legalEdges: [],
    legalVersions: [],
    comparisons: [],
    recheckProbes: [],
    findings: [],
    graphModel: { nodes: [], edges: [] },
    candidates: [],
  };
}
const text = (value: any): string =>
  value == null
    ? ""
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
const unique = <T extends { id: string }>(rows: T[], item: T): T[] => [
  ...rows.filter((r) => r.id !== item.id),
  item,
];
const MAX_VISUAL_CONCEPTS = 6;
const MAX_VISUAL_LEGAL = 6;
const isChecklistConcept = (cid: string): boolean => cid.startsWith("content.");
const upsertInPlace = <T extends { id: string }>(rows: T[], item: T): T[] =>
  rows.some((r) => r.id === item.id)
    ? rows.map((r) => (r.id === item.id ? item : r))
    : [...rows, item];
const shouldAcceptConcept = (
  concepts: { id: string }[],
  cid: string,
  allowChecklist = false,
): boolean => {
  if (concepts.some((c) => c.id === cid)) return true;
  if (concepts.length >= MAX_VISUAL_CONCEPTS) return false;
  if (!allowChecklist && isChecklistConcept(cid)) return false;
  return true;
};
const status = (finding: string): SemanticStatus =>
  (({
    violation: "issue",
    missing_content: "issue",
    hidden_right: "completed",
    possible_right: "insufficient_data",
    needs_facts: "insufficient_data",
    conflict: "conflict",
    ok: "completed",
  })[finding] as SemanticStatus) || "insufficient_data";

export function applyGraph(s: AnalysisScenario, graph: any): AnalysisScenario {
  const nodes = graph.nodes || [],
    edges = graph.edges || [];
  const graphModel: ContractGraphModel = {
    nodes: nodes.map((n: any) => ({
      id: n.node_id,
      nodeType: n.node_type,
      label:
        n.display_label ||
        n.label ||
        n.title ||
        n.name ||
        n.concept_id ||
        n.raw ||
        (n.node_type === "Part" ? "Hợp đồng chính" : s.title),
      sublabel: n.role || text(n.value),
      revealAtStep: 0,
      clauseId: n.uid,
      partId: n.part_id,
      pageNumber: n.page_start,
      excerpt: n.text || n.quote,
      rawValue: n.raw,
      conceptId: n.concept_id,
      effectiveDateLabel: n.valid_from,
      factId: n.node_type === "ContractFact" ? n.node_id : undefined,
    })),
    edges: edges.map((e: any) => ({
      id: `${e.type}:${e.src}:${e.dst}`,
      from: e.src,
      to: e.dst,
      edgeType: e.type,
      label: e.type,
      revealAtStep: 0,
      effectiveDateLabel: e.props?.valid_from,
    })),
  };
  const unitIds = new Set(
    nodes.filter((n: any) => n.node_type === "Unit").map((n: any) => n.node_id),
  );
  const childOfParent = new Map<string, string>();
  for (const e of edges) {
    if (e.type === "CHILD_OF" && e.src && e.dst) {
      childOfParent.set(e.src, e.dst);
    }
  }
  const topParentUnit = (id: string): string => {
    let cur = id;
    const seen = new Set<string>();
    while (childOfParent.has(cur) && !seen.has(cur)) {
      seen.add(cur);
      const next = childOfParent.get(cur)!;
      if (!unitIds.has(next)) break;
      cur = next;
    }
    return cur;
  };
  // Chỉ giữ các Điều cha (Unit cấp 1) được chọn / có liên kết (Concept, Sửa đổi, Dẫn chiếu, Dữ kiện), tối đa 6 thẻ cho gọn.
  const topUnits = nodes.filter((n: any) => {
    if (n.node_type !== "Unit") return false;
    const p = childOfParent.get(n.node_id);
    return !p || !unitIds.has(p);
  });
  const scoreMap = new Map<string, number>();
  const bump = (id: string, w: number) => {
    const top = topParentUnit(id);
    scoreMap.set(top, (scoreMap.get(top) || 0) + w);
  };
  for (const e of edges) {
    if (e.type === "ABOUT" && e.dst) bump(e.dst, 10);
    else if (e.type === "AMENDS") {
      if (e.src) bump(e.src, 6);
      if (e.dst) bump(e.dst, 6);
    } else if (e.type === "REFERS_TO") {
      if (e.src) bump(e.src, 4);
      if (e.dst) bump(e.dst, 4);
    } else if (e.type === "EVIDENCE" && e.dst) bump(e.dst, 3);
  }
  const hasConcepts = edges.some((e: any) => e.type === "ABOUT");
  const rankedIds = new Set(
    [...topUnits]
      .filter((u: any) =>
        hasConcepts
          ? (scoreMap.get(u.node_id) || 0) >= 6
          : (scoreMap.get(u.node_id) || 0) > 0,
      )
      .sort(
        (a: any, b: any) =>
          (scoreMap.get(b.node_id) || 0) - (scoreMap.get(a.node_id) || 0),
      )
      .slice(0, 6)
      .map((u: any) => u.node_id),
  );
  const visibleNodes = rankedIds.size
    ? topUnits.filter((u: any) => rankedIds.has(u.node_id))
    : topUnits.slice(0, 5);
  const visibleIds = new Set(visibleNodes.map((n: any) => n.node_id));
  const contractNodes: any[] = visibleNodes.map((n: any, i: number) => ({
    id: n.node_id,
    label:
      n.display_label ||
      n.label ||
      n.title ||
      n.name ||
      n.concept_id ||
      n.raw ||
      (n.node_type === "Part" ? "Hợp đồng chính" : s.title),
    sublabel: n.role || "",
    kind:
      n.node_type === "Contract"
        ? "contract"
        : n.node_type === "Part"
          ? "section"
          : "clause",
    clauseId: n.uid,
    conceptIds: [],
    revealAtStep: 0,
    laneRow: i,
  }));
  let concepts = s.concepts;
  const ciNodes = nodes.filter((n: any) => n.node_type === "ConceptInstance");
  const upsertConceptNode = (n: any, allowChecklist: boolean) => {
    if (
      !n.concept_id ||
      !shouldAcceptConcept(concepts, n.concept_id, allowChecklist)
    )
      return;
    const about = edges
      .filter((e: any) => e.type === "ABOUT" && e.src === n.node_id)
      .map((e: any) => topParentUnit(e.dst))
      .filter((id: string) => visibleIds.has(id));
    const uids = about
      .map((id: string) => visibleNodes.find((u: any) => u.node_id === id)?.uid)
      .filter(Boolean);
    const old = concepts.find((c) => c.id === n.concept_id);
    concepts = upsertInPlace(concepts, {
      id: n.concept_id,
      label: old?.label || n.display_label || n.label || n.concept_id,
      category: "",
      clauseIds: [...new Set([...(old?.clauseIds || []), ...uids])] as string[],
      contractNodeIds: [
        ...new Set([...(old?.contractNodeIds || []), ...about]),
      ],
      legalNodeIds: old?.legalNodeIds || [],
      status: "completed",
      revealAtStep: 0,
      laneRow: old?.laneRow ?? concepts.length,
    });
  };
  for (const n of ciNodes) upsertConceptNode(n, false);
  if (concepts.length < 4) {
    for (const n of ciNodes) {
      if (concepts.length >= 4) break;
      upsertConceptNode(n, true);
    }
  }
  for (const c of concepts)
    for (const n of contractNodes)
      if (c.contractNodeIds.includes(n.id)) n.conceptIds.push(c.id);
  const edgeMap = new Map<string, any>();
  for (const e of edges) {
    if (!["REFERS_TO", "AMENDS", "HAS_UNIT", "HAS_PART"].includes(e.type))
      continue;
    const from = topParentUnit(e.src);
    const to = topParentUnit(e.dst);
    if (from === to || !visibleIds.has(from) || !visibleIds.has(to)) continue;
    const id = `${e.type}:${from}:${to}`;
    if (!edgeMap.has(id)) {
      edgeMap.set(id, {
        id,
        from,
        to,
        kind:
          e.type === "AMENDS"
            ? "addendum_amends"
            : e.type === "REFERS_TO"
              ? "internal_ref"
              : "parent_child",
        label: e.type,
        effectiveDateLabel: e.props?.valid_from,
        revealAtStep: 0,
        highlightAtStep: 3,
      });
    }
  }
  return {
    ...s,
    graphModel,
    contractNodes,
    concepts,
    contractEdges: Array.from(edgeMap.values()),
  };
}

export function applySnapshot(
  s: AnalysisScenario,
  payload: any,
): AnalysisScenario {
  const c = payload.card,
    doc = payload.document;
  if (!c) return s;
  s = {
    ...s,
    id: c.contract_id,
    title: c.filename,
    signingDateIso: c.sign_date || "",
    subtitle: c.last_check?.stale
      ? "Thông tin đã thay đổi — cần phân tích lại"
      : "Hợp đồng tải lên",
    extractedFacts: (c.verification?.fields || []).map((f: any) => ({
      id: f.key,
      key: f.key,
      label: f.label,
      value: text(f.value),
      sourceClauseId: f.unit || "",
      editable: true,
      needsReview: !["confirmed", "corrected", "unknown"].includes(f.status),
    })),
    sections: (doc?.parts || []).map((p: any) => ({
      id: p.part_id,
      kind: p.kind === "main" ? "main" : "addendum",
      fileName: c.filename,
      title: p.title || "Hợp đồng chính",
      revealAtStep: 0,
      clauses: (doc.units || [])
        .filter((u: any) => u.part_id === p.part_id)
        .map((u: any) => ({
          id: u.uid,
          sectionId: p.part_id,
          code: u.label,
          title: "",
          text: u.text,
          conceptIds: [],
          highlightPhrases: [],
          pageNumber: u.page_start,
          parentClauseId: u.parent_uid,
          revealAtStep: 0,
        })),
    })),
  };
  if (payload.graph) s = applyGraph(s, payload.graph);
  if (payload.last_check) s = applyReport(s, payload.last_check);
  return s;
}

function applyLaw(
  s: AnalysisScenario,
  cid: string,
  pid: string,
  p: any,
): AnalysisScenario {
  if (!p) return s;
  const cite = p.citation || {},
    id = cite.version_id || pid;
  if (!cite.provision_id && !p.text) return s;
  const label =
    typeof cite === "string"
      ? cite
      : [cite.label, cite.doc_title || cite.doc_number]
          .filter(Boolean)
          .join(" — ");

  if (cite.valid_from) {
    const docCode = cite.doc_number || cite.document_key || pid;
    const isDuplicate = s.legalVersions.some(
      (v) => v.documentCode === docCode && v.effectiveFrom === cite.valid_from,
    );
    if (!isDuplicate) {
      const entry = {
        id,
        documentCode: docCode,
        title: cite.doc_title || label || pid,
        effectiveFrom: cite.valid_from,
        effectiveTo: cite.valid_to || undefined,
        statusLabel: p.in_force
          ? `Hiệu lực từ ${cite.valid_from}`
          : p.reason === "not_yet_in_force"
            ? `Chưa hiệu lực (từ ${cite.valid_from})`
            : `Hết hiệu lực${cite.valid_to ? ` (${cite.valid_to})` : ""}`,
        note: cite.verification_status || "",
        legalNodeId: id,
        inForce: p.in_force === true,
      };
      if (s.legalVersions.length < 4) {
        s = { ...s, legalVersions: [...s.legalVersions, entry] };
      } else if (
        p.in_force === false &&
        s.legalVersions.every((v) => v.inForce === true)
      ) {
        s = { ...s, legalVersions: [...s.legalVersions.slice(0, 3), entry] };
      }
    }
  }

  if (p.in_force === false) return s;
  const exists = s.legalNodes.some((n) => n.id === id);
  if (!exists) {
    if (s.legalNodes.length >= MAX_VISUAL_LEGAL) return s;
    if (
      s.concepts.length > 0 &&
      !s.concepts.some((c) => c.id === cid) &&
      s.legalNodes.length >= 2
    )
      return s;
  }
  const legalNodes = upsertInPlace(s.legalNodes, {
    id,
    label: cite.label || label || pid,
    sublabel:
      [
        cite.doc_title || cite.doc_number,
        p.in_force === true
          ? "Có phiên bản tại mốc"
          : p.reason || "Chưa xác định hiệu lực",
      ]
        .filter(Boolean)
        .join(" · ") || "Căn cứ pháp lý",
    kind: cite.version_id ? "version" : "article",
    citation: label || pid,
    excerpt: p.text || "",
    conceptIds: [
      ...new Set([
        ...(s.legalNodes.find((n) => n.id === id)?.conceptIds || []),
        cid,
      ]),
    ],
    revealAtStep: 0,
    laneRow: s.legalNodes.find((n) => n.id === id)?.laneRow ?? s.legalNodes.length,
    isSelectedVersion: p.in_force === true,
  });
  return {
    ...s,
    legalNodes,
    legalEdges: s.legalEdges,
    concepts: s.concepts.map((c) =>
      c.id === cid
        ? { ...c, legalNodeIds: [...new Set([...c.legalNodeIds, id])] }
        : c,
    ),
  };
}

export function applyReport(s: AnalysisScenario, data: any): AnalysisScenario {
  const rows = data.views || data.results || data.report?.results || [];
  const basis = data.report?.basis || data.basis || {};
  for (const [cid, b] of Object.entries(basis) as any)
    for (const a of b.anchors || []) {
      const p = a.provision;
      const decision = p
        ? p.in_force === true
          ? "kept"
          : p.in_force === false &&
              ["not_yet_in_force", "no_longer_in_force", "no_version_at_date"].includes(
                p.reason,
              )
            ? "excluded"
            : "unknown"
        : "unknown";
      s = {
        ...s,
        candidates: unique(s.candidates || [], {
          id: `${cid}:${a.pid}`,
          conceptId: cid,
          decision,
        }),
      };
      s = applyLaw(s, cid, a.pid, a.provision);
    }
  for (const row of rows) {
    const cid = row.concept_id,
      id = `${cid}/${row.rule_id}`,
      view = row.view || {};
    const concept = s.concepts.find((c) => c.id === cid);
    if (concept) {
      const nextStatus = status(row.finding);
      s = {
        ...s,
        concepts: s.concepts.map((c) =>
          c.id === cid
            ? {
                ...c,
                label: view.title || c.label,
                status: nextStatus === "issue" ? "issue" : c.status,
              }
            : c,
        ),
      };
    }
    const evidence = row.evidence || [],
      quote = evidence
        .map((e: any) => e.quote)
        .filter(Boolean)
        .join("\n"),
      uid = evidence[0]?.uid || "";
    const laws = view.law || [],
      law = laws.find((l: any) => l.in_force === true) || laws[0];
    const lawValue =
      (view.law_values || []).map((v: any) => v.text).join("; ") ||
      Object.entries(row.law_values || {})
        .map(([k, v]: any) => `${k}: ${v.value} ${v.unit || ""}`)
        .join("; ");
    const factValue = Object.entries(row.facts_used || {})
      .map(([k, v]: any) => `${k}: ${text(v.value)} ${v.unit || ""}`)
      .join("; ");
    const f: any = {
      id,
      title: view.title || concept?.label || cid,
      status: status(row.finding),
      severityLabel: view.verdict || row.finding,
      summary: view.meaning || row.finding,
      contractClauseId: uid,
      contractClauseRef:
        s.sections.flatMap((p) => p.clauses).find((c) => c.id === uid)?.code ||
        uid ||
        "Không có đoạn xác nhận",
      contractQuote: quote,
      legalCitation: law?.citation || law?.pid || "Chưa có căn cứ đã truy xuất",
      legalQuote: law?.text || "Chưa có lời văn luật",
      recommendation: (view.missing || row.missing_facts || []).length
        ? `Cần bổ sung: ${(view.missing || row.missing_facts).join(", ")}`
        : "Chưa có đề xuất sửa từ bước kiểm tra này",
      conceptId: cid,
      relatedContractNodeIds: concept?.contractNodeIds || [],
      relatedLegalNodeIds: s.legalNodes
        .filter((n) => n.conceptIds.includes(cid))
        .map((n) => n.id),
      relatedEdgeIds: [],
      comparisonId: id,
    };
    if (row.finding !== "ok") s = { ...s, findings: unique(s.findings, f) };
    else s = { ...s, findings: s.findings.filter((f) => f.id !== id) };
    s = {
      ...s,
      comparisons: unique(s.comparisons, {
        id,
        findingId: id,
        conceptId: cid,
        conceptLabel: f.title,
        contractClauseCode: f.contractClauseRef,
        contractExcerpt: quote,
        contractValueLabel: "Dữ kiện được dùng",
        contractValue: factValue,
        legalCitation: f.legalCitation,
        legalExcerpt: f.legalQuote,
        legalThresholdLabel: "Giá trị rule trong danh mục",
        legalThreshold: lawValue,
        verdict: f.status,
        reasoning: [view.verdict || row.finding, ...(row.reasons || [])].join(
          " · ",
        ),
      }),
    };
  }
  if (data.markdown)
    s = {
      ...s,
      summaryText: `Đã kiểm tra ${data.report?.results?.length || rows.length} quy tắc trong danh mục. Có ${s.findings.length} kết quả cần xem, gồm nội dung cần chú ý, quyền chưa được nhắc và thông tin còn thiếu.`,
    };
  const warnings = [...(s.warnings || []), ...(data.report?.warnings || [])];
  if (
    Object.values(basis).some((b: any) =>
      b.problems?.includes("basis_unavailable"),
    )
  )
    warnings.push(
      "Chưa lấy được căn cứ từ legal graph. Các giá trị đối chiếu hiện đến từ danh mục rule, chưa phải xác minh đầy đủ bằng lời văn luật.",
    );
  if (warnings.length) s = { ...s, warnings: [...new Set(warnings)] };
  return s;
}

export function applyEvent(s: AnalysisScenario, e: any): AnalysisScenario {
  if (e.card) s = applySnapshot(s, e);
  if (["fact_batch", "tag_batch", "recheck"].includes(e.type)) {
    const key = `${e.type}:${e.batch ?? e.concept_id ?? e.uids?.join(",")}`,
      activeBatches = { ...s.activeBatches };
    if (e.status === "start") activeBatches[key] = e.uids || [];
    else delete activeBatches[key];
    s = {
      ...s,
      activeBatches,
      activeUnitIds: [...new Set(Object.values(activeBatches).flat())],
    };
  }
  if (e.type === "structure")
    s = {
      ...s,
      sections: [
        {
          id: "parsed",
          kind: "main",
          title: "Nội dung đã đọc",
          fileName: s.title,
          revealAtStep: 0,
          clauses: e.units.map((u: any) => ({
            id: u.uid,
            code: u.label,
            title: "",
            sectionId: "parsed",
            text: u.text,
            pageNumber: u.page,
            conceptIds: [],
            revealAtStep: 0,
          })),
        },
      ],
    };
  if (e.type === "graph") s = applyGraph(s, e);
  if (
    e.type === "concept" &&
    e.concept_id &&
    shouldAcceptConcept(s.concepts, e.concept_id, false)
  ) {
    const old = s.concepts.find((c) => c.id === e.concept_id);
    const matchingIds = s.contractNodes
      .filter(
        (cn) =>
          cn.clauseId &&
          e.uid &&
          (cn.clauseId === e.uid || e.uid.startsWith(cn.clauseId + ".")),
      )
      .map((cn) => cn.id);
    const matchSet = new Set(matchingIds);
    s = {
      ...s,
      activeConceptId: e.concept_id,
      contractNodes: s.contractNodes.map((cn) =>
        matchSet.has(cn.id)
          ? { ...cn, conceptIds: [...new Set([...cn.conceptIds, e.concept_id])] }
          : cn,
      ),
      concepts: upsertInPlace(s.concepts, {
        id: e.concept_id,
        label: e.label,
        category: "",
        clauseIds: [...new Set([...(old?.clauseIds || []), e.uid])],
        contractNodeIds: [
          ...new Set([...(old?.contractNodeIds || []), ...matchingIds]),
        ],
        legalNodeIds: old?.legalNodeIds || [],
        status: e.op?.status === "pending" ? "needs_confirmation" : "completed",
        revealAtStep: 0,
        laneRow: old?.laneRow ?? s.concepts.length,
      }),
    };
  }
  if (e.type === "legal_candidate")
    s = {
      ...s,
      activeConceptId: e.concept_id,
      candidates: unique(s.candidates || [], {
        id: `${e.concept_id}:${e.pid}`,
        conceptId: e.concept_id,
        decision: "pending",
      }),
    };
  if (e.type === "legal_resolution") {
    s = {
      ...s,
      candidates: unique(s.candidates || [], {
        id: `${e.concept_id}:${e.pid}`,
        conceptId: e.concept_id,
        decision: e.decision,
      }),
    };
    s = applyLaw(s, e.concept_id, e.pid, e.provision);
  }
  if (e.type === "evaluation") s = applyReport(s, { results: [e.result] });
  if (e.type === "partial") s = applyReport(s, e);
  if (e.type === "recheck")
    s = {
      ...s,
      recheckProbes: unique(s.recheckProbes, {
        id: e.concept_id,
        targetTopic: e.label || e.concept_id,
        suspectedMissingReason: "Kiểm tra lại trước khi báo thiếu",
        scannedClauses: e.uids || [],
        scanResult:
          e.status === "done"
            ? e.found
              ? "Tìm thấy nội dung"
              : "Không tìm thấy trong các đoạn đã kiểm tra"
            : e.status === "error"
              ? "Chưa kiểm tra được"
              : "Đang kiểm tra",
        finalStatus: e.status === "done" ? "completed" : "processing",
      }),
    };
  if (e.result) s = applyReport(s, e.result);
  return s;
}

export function stepFor(e: any, fallback: number): number {
  if (e.type === "structure" || e.type === "document") return 0;
  if (e.type === "tag_batch" || e.type === "concept") return 2;
  if (e.type === "graph") return e.phase === "read" ? 0 : 3;
  if (e.type === "evaluation" || e.type === "partial") return 6;
  if (e.type === "recheck") return 7;
  if (e.type === "legal_candidate") return 4;
  if (e.type === "legal_resolution") return 5;
  if (e.type === "stage")
    return (
      ({ read: 0, facts: 0, tag: 2, evaluate: 6, recheck: 7, basis: 4 } as any)[
        e.stage
      ] ?? fallback
    );
  return fallback;
}

export function particlesFor(s: AnalysisScenario): ScreeningParticle[] {
  const candidates = s.candidates || [];
  const count = candidates.length;
  if (!count) return [];
  const goldenAngle = 2.399963229728653;
  const safeConceptCount = Math.max(1, s.concepts.length);
  const filterStride = count === 56 ? 19 : 17;
  let keptIdx = 0,
    exclIdx = 0;

  return candidates.map((c, i) => {
    const t = (i + 0.5) / count;
    const r = Math.sqrt(t);
    const theta = i * goldenAngle;
    const centerX = Math.round(Math.cos(theta) * r * 54 * 10) / 10;
    const centerY = Math.round(Math.sin(theta) * r * 24 * 10) / 10;

    const isRelevant = c.decision === "kept";
    const subIdx = isRelevant ? keptIdx++ : exclIdx++;
    const subAngle = i * goldenAngle * 1.15;
    const subR = Math.sqrt(((subIdx % 28) + 0.6) / 28);
    const splitX = Math.round(Math.cos(subAngle) * subR * 52 * 10) / 10;
    const splitY = isRelevant
      ? Math.round((-62 + Math.sin(subAngle) * subR * 20) * 10) / 10
      : Math.round((74 + Math.sin(subAngle) * subR * 20) * 10) / 10;

    const batchIdx = Math.max(
      0,
      s.concepts.findIndex((n) => n.id === c.conceptId),
    );
    const batchSize = Math.max(1, Math.ceil(count / safeConceptCount));
    const indexInBatch = i - Math.floor((batchIdx * count) / safeConceptCount);
    const slotDuration = 3200 / safeConceptCount;
    const discoveredAtMs = Math.round(
      180 +
        batchIdx * slotDuration +
        (Math.min(batchSize - 1, Math.max(0, indexInBatch)) / batchSize) *
          (slotDuration * 0.85),
    );

    const filterOrder = (i * filterStride) % count;
    const filteredAtMs =
      c.decision === "pending"
        ? Infinity
        : Math.round(650 + (filterOrder / Math.max(1, count - 1)) * 1750);

    return {
      id: c.id,
      index: i,
      batchIndex: batchIdx,
      group:
        c.decision === "kept"
          ? "relevant"
          : c.decision === "excluded"
            ? "excluded"
            : "unknown",
      discoveredAtMs,
      filteredAtMs,
      centerX,
      centerY,
      splitX,
      splitY,
      radius: 2.1 + (i % 3) * 0.45,
      driftX: ((i % 5) - 2) * 1.1,
      driftY: (((i + 2) % 5) - 2) * 0.9,
      delay: (i % 10) * 0.02,
    };
  });
}
export function choreographyFor(
  s: AnalysisScenario,
  step: number,
  elapsedMs: number = Number.MAX_SAFE_INTEGER,
): StepChoreographyState {
  const candidates = s.candidates || [];
  const resolved = candidates.filter((c) => c.decision !== "pending");
  const totalContract = s.contractNodes.length;
  const totalFacts = s.extractedFacts.length;
  const totalConcepts = s.concepts.length;
  const totalLegal = s.legalNodes.length;

  let assemblyStage: StepChoreographyState["assemblyStage"] = "docked";
  if (step === 0) {
    assemblyStage =
      !s.graphModel?.nodes.length || elapsedMs < 700
        ? "folio_scan"
        : "graph_build";
  } else if (step === 1) {
    assemblyStage = s.graphModel?.nodes.length ? "graph_build" : "folio_scan";
  } else if (step === 2 && elapsedMs < 600) {
    assemblyStage = "docking_left";
  }

  let visibleContractCount = totalContract;
  if (step === 0) {
    if (assemblyStage === "folio_scan") visibleContractCount = 0;
    else if (assemblyStage === "graph_build") {
      visibleContractCount = Math.min(
        totalContract,
        Math.max(1, Math.floor((elapsedMs - 750) / 220) + 1),
      );
    }
  }

  const visibleFactCount =
    step === 1
      ? Math.min(totalFacts, Math.max(1, Math.floor(elapsedMs / 160) + 1))
      : totalFacts;

  let visibleConceptCount = 0;
  let activeQueryConceptIndex: number | null = s.activeConceptId
    ? s.concepts.findIndex((c) => c.id === s.activeConceptId)
    : null;

  if (step === 2) {
    const SLOT_MS = 640;
    const PREPARE_MS = 240;
    if (totalConcepts > 0) {
      visibleConceptCount = Math.min(
        totalConcepts,
        elapsedMs < PREPARE_MS
          ? 0
          : Math.floor((elapsedMs - PREPARE_MS) / SLOT_MS) + 1,
      );
      const curIdx = Math.floor(elapsedMs / SLOT_MS);
      activeQueryConceptIndex = curIdx < totalConcepts ? curIdx : null;
    }
  } else if (step > 2) {
    visibleConceptCount = totalConcepts;
  }

  const activeRelationPhase: StepChoreographyState["activeRelationPhase"] =
    step === 3 ? (elapsedMs < 1100 ? "internal_ref" : "addendum_amends") : "all";

  let discoveredParticleCount = 0;
  let allParticlesDiscovered = false;

  const pts = particlesFor(s);
  if (step === 4) {
    const slotDuration = 3200 / Math.max(1, totalConcepts);
    if (elapsedMs < 3300) {
      activeQueryConceptIndex = Math.min(
        totalConcepts - 1,
        Math.floor(elapsedMs / slotDuration),
      );
    }
    discoveredParticleCount = pts.filter(
      (p) => elapsedMs >= p.discoveredAtMs,
    ).length;
    allParticlesDiscovered =
      !s.isBusy && discoveredParticleCount >= pts.length;
  } else if (step > 4) {
    discoveredParticleCount = candidates.length;
    allParticlesDiscovered = !s.isBusy;
  }

  let filteringStarted = false;
  let filteringComplete = false;
  let filteredParticleCount = 0;
  let keptParticleCount = 0;
  let droppedParticleCount = 0;
  let visibleLegalCount = 0;

  if (step === 5) {
    filteringStarted = resolved.length > 0 && elapsedMs >= 650;
    for (const p of pts) {
      if (p.filteredAtMs !== Infinity && elapsedMs >= p.filteredAtMs) {
        filteredParticleCount += 1;
        if (p.group === "relevant") keptParticleCount += 1;
        else if (p.group === "excluded") droppedParticleCount += 1;
      }
    }
    filteringComplete =
      s.legalNodes.length > 0 &&
      elapsedMs >= 2450 &&
      filteredParticleCount >= pts.length;
    if (filteringComplete) {
      const legalElapsed = Math.max(0, elapsedMs - 2550);
      visibleLegalCount = Math.min(
        totalLegal,
        Math.max(1, Math.floor(legalElapsed / 420) + 1),
      );
    }
  } else if (step > 5) {
    filteringStarted = resolved.length > 0;
    filteringComplete = s.legalNodes.length > 0;
    filteredParticleCount = resolved.length;
    keptParticleCount = resolved.filter((c) => c.decision === "kept").length;
    droppedParticleCount = resolved.filter(
      (c) => c.decision === "excluded",
    ).length;
    visibleLegalCount = totalLegal;
  }

  return {
    assemblyStage,
    visibleContractCount,
    visibleFactCount,
    visibleConceptCount,
    activeRelationPhase,
    activeQueryConceptIndex,
    discoveredParticleCount,
    allParticlesDiscovered,
    filteringStarted,
    filteringComplete,
    filteredParticleCount,
    keptParticleCount,
    droppedParticleCount,
    visibleLegalCount,
    activeComparisonIndex: Math.max(0, s.comparisons.length - 1),
    activeRecheckClauseCount:
      s.recheckProbes.at(-1)?.scannedClauses.length || 0,
    activeSubPhaseId: "",
  };
}
