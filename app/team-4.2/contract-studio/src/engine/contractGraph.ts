import type {
  AnalysisScenario,
  ContractGraph7Edge,
  ContractGraph7Node,
  ContractGraphModel,
  DocumentClause,
  LegalConceptNode,
  SevenNodeKind,
} from "../types/contract";

export type SevenNodeSelection =
  | { kind: "unit"; id: string }
  | { kind: "fact"; id: string }
  | { kind: "conceptInstance"; id: string }
  | { kind: "party"; id: string };

export interface SevenNodeTrace {
  selection: SevenNodeSelection | null;
  highlightedNodeIds: Set<string>;
  highlightedEdgeIds: Set<string>;
  highlightedUnitIds: Set<string>;
  highlightedPartyIds: Set<string>;
  highlightedFactIds: Set<string>;
  highlightedConceptInstanceIds: Set<string>;
}

export interface UnitDetailBundle {
  unit: ContractGraph7Node;
  part: ContractGraph7Node | null;
  parentUnit: ContractGraph7Node | null;
  childUnits: ContractGraph7Node[];
  refersToUnits: Array<{ edge: ContractGraph7Edge; unit: ContractGraph7Node }>;
  referredByUnits: Array<{
    edge: ContractGraph7Edge;
    unit: ContractGraph7Node;
  }>;
  amendsUnits: Array<{ edge: ContractGraph7Edge; unit: ContractGraph7Node }>;
  amendedByUnits: Array<{ edge: ContractGraph7Edge; unit: ContractGraph7Node }>;
  values: ContractGraph7Node[];
  facts: ContractGraph7Node[];
  conceptInstances: Array<{
    node: ContractGraph7Node;
    holderParty: ContractGraph7Node | null;
    otherOccurrences: ContractGraph7Node[];
  }>;
}

export function buildContractGraphModel(
  scenario: AnalysisScenario,
): ContractGraphModel {
  return scenario.graphModel ?? { nodes: [], edges: [] };
}

export function filterContractGraphForStep(
  model: ContractGraphModel,
  currentStepIndex: number,
): ContractGraphModel {
  const visibleNodes = model.nodes.filter(
    (n) => currentStepIndex >= n.revealAtStep,
  );
  const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = model.edges.filter(
    (e) =>
      currentStepIndex >= e.revealAtStep &&
      visibleNodeIds.has(e.from) &&
      visibleNodeIds.has(e.to),
  );
  return { nodes: visibleNodes, edges: visibleEdges };
}

export function countNodesByKind(
  model: ContractGraphModel,
): Record<SevenNodeKind, number> {
  const counts: Record<SevenNodeKind, number> = {
    Contract: 0,
    Part: 0,
    Unit: 0,
    Value: 0,
    Party: 0,
    ContractFact: 0,
    ConceptInstance: 0,
  };
  for (const node of model.nodes) {
    counts[node.nodeType] += 1;
  }
  return counts;
}

export function resolve7NodeSelectionTrace(
  model: ContractGraphModel,
  selection: SevenNodeSelection | null,
): SevenNodeTrace {
  const trace: SevenNodeTrace = {
    selection,
    highlightedNodeIds: new Set(),
    highlightedEdgeIds: new Set(),
    highlightedUnitIds: new Set(),
    highlightedPartyIds: new Set(),
    highlightedFactIds: new Set(),
    highlightedConceptInstanceIds: new Set(),
  };

  if (!selection) return trace;

  if (selection.kind === "unit") {
    trace.highlightedNodeIds.add(selection.id);
    trace.highlightedUnitIds.add(selection.id);
    for (const edge of model.edges) {
      if (edge.from === selection.id || edge.to === selection.id) {
        trace.highlightedEdgeIds.add(edge.id);
        trace.highlightedNodeIds.add(edge.from);
        trace.highlightedNodeIds.add(edge.to);
        if (
          edge.edgeType === "AMENDS" ||
          edge.edgeType === "REFERS_TO" ||
          edge.edgeType === "CHILD_OF"
        ) {
          const otherId = edge.from === selection.id ? edge.to : edge.from;
          trace.highlightedUnitIds.add(otherId);
        }
      }
    }
    return trace;
  }

  if (selection.kind === "fact") {
    trace.highlightedNodeIds.add(selection.id);
    trace.highlightedFactIds.add(selection.id);
    for (const edge of model.edges) {
      if (edge.from === selection.id && edge.edgeType === "EVIDENCE") {
        trace.highlightedEdgeIds.add(edge.id);
        trace.highlightedNodeIds.add(edge.to);
        trace.highlightedUnitIds.add(edge.to);
      }
      if (edge.to === selection.id && edge.edgeType === "HAS_FACT") {
        trace.highlightedEdgeIds.add(edge.id);
        trace.highlightedNodeIds.add(edge.from);
      }
    }
    return trace;
  }

  if (selection.kind === "conceptInstance") {
    trace.highlightedNodeIds.add(selection.id);
    trace.highlightedConceptInstanceIds.add(selection.id);
    for (const edge of model.edges) {
      if (edge.from === selection.id && edge.edgeType === "ABOUT") {
        trace.highlightedEdgeIds.add(edge.id);
        trace.highlightedNodeIds.add(edge.to);
        trace.highlightedUnitIds.add(edge.to);
      }
      if (edge.from === selection.id && edge.edgeType === "HOLDER") {
        trace.highlightedEdgeIds.add(edge.id);
        trace.highlightedNodeIds.add(edge.to);
        trace.highlightedPartyIds.add(edge.to);
      }
    }
    return trace;
  }

  if (selection.kind === "party") {
    trace.highlightedNodeIds.add(selection.id);
    trace.highlightedPartyIds.add(selection.id);
    for (const edge of model.edges) {
      if (edge.to === selection.id && edge.edgeType === "HOLDER") {
        trace.highlightedEdgeIds.add(edge.id);
        trace.highlightedNodeIds.add(edge.from);
        trace.highlightedConceptInstanceIds.add(edge.from);
        // Also resolve connected Unit via ABOUT
        for (const aboutEdge of model.edges) {
          if (aboutEdge.from === edge.from && aboutEdge.edgeType === "ABOUT") {
            trace.highlightedEdgeIds.add(aboutEdge.id);
            trace.highlightedNodeIds.add(aboutEdge.to);
            trace.highlightedUnitIds.add(aboutEdge.to);
          }
        }
      }
    }
  }

  return trace;
}

export function getUnitDetailBundle(
  model: ContractGraphModel,
  unitNodeId: string,
  currentStepIndex: number,
): UnitDetailBundle | null {
  const stepFiltered = filterContractGraphForStep(model, currentStepIndex);
  const nodeMap = new Map(stepFiltered.nodes.map((n) => [n.id, n]));
  const unit = nodeMap.get(unitNodeId);
  if (!unit || unit.nodeType !== "Unit") return null;

  const part = unit.partId ? (nodeMap.get(unit.partId) ?? null) : null;
  const parentUnit = unit.parentUnitId
    ? (nodeMap.get(unit.parentUnitId) ?? null)
    : null;

  const childUnits: ContractGraph7Node[] = [];
  const refersToUnits: Array<{
    edge: ContractGraph7Edge;
    unit: ContractGraph7Node;
  }> = [];
  const referredByUnits: Array<{
    edge: ContractGraph7Edge;
    unit: ContractGraph7Node;
  }> = [];
  const amendsUnits: Array<{
    edge: ContractGraph7Edge;
    unit: ContractGraph7Node;
  }> = [];
  const amendedByUnits: Array<{
    edge: ContractGraph7Edge;
    unit: ContractGraph7Node;
  }> = [];
  const values: ContractGraph7Node[] = [];
  const facts: ContractGraph7Node[] = [];
  const conceptInstances: UnitDetailBundle["conceptInstances"] = [];

  for (const edge of stepFiltered.edges) {
    if (edge.edgeType === "CHILD_OF" && edge.to === unit.id) {
      const child = nodeMap.get(edge.from);
      if (child) childUnits.push(child);
    } else if (edge.edgeType === "REFERS_TO" && edge.from === unit.id) {
      const target = nodeMap.get(edge.to);
      if (target) refersToUnits.push({ edge, unit: target });
    } else if (edge.edgeType === "REFERS_TO" && edge.to === unit.id) {
      const src = nodeMap.get(edge.from);
      if (src) referredByUnits.push({ edge, unit: src });
    } else if (edge.edgeType === "AMENDS" && edge.from === unit.id) {
      const target = nodeMap.get(edge.to);
      if (target) amendsUnits.push({ edge, unit: target });
    } else if (edge.edgeType === "AMENDS" && edge.to === unit.id) {
      const src = nodeMap.get(edge.from);
      if (src) amendedByUnits.push({ edge, unit: src });
    } else if (edge.edgeType === "HAS_VALUE" && edge.from === unit.id) {
      const val = nodeMap.get(edge.to);
      if (val) values.push(val);
    } else if (edge.edgeType === "EVIDENCE" && edge.to === unit.id) {
      const fact = nodeMap.get(edge.from);
      if (fact) facts.push(fact);
    } else if (edge.edgeType === "ABOUT" && edge.to === unit.id) {
      const ci = nodeMap.get(edge.from);
      if (ci) {
        const holderEdge = stepFiltered.edges.find(
          (he) => he.from === ci.id && he.edgeType === "HOLDER",
        );
        const holderParty = holderEdge
          ? (nodeMap.get(holderEdge.to) ?? null)
          : null;
        const otherOccurrences = stepFiltered.nodes.filter(
          (n) =>
            n.nodeType === "ConceptInstance" &&
            n.conceptId === ci.conceptId &&
            n.id !== ci.id,
        );
        conceptInstances.push({ node: ci, holderParty, otherOccurrences });
      }
    }
  }

  return {
    unit,
    part,
    parentUnit,
    childUnits,
    refersToUnits,
    referredByUnits,
    amendsUnits,
    amendedByUnits,
    values,
    facts,
    conceptInstances,
  };
}
