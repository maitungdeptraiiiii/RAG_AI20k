export type PipelineStepId =
  | "read_docs"
  | "verify_info"
  | "detect_concepts"
  | "contract_relations"
  | "find_legal_basis"
  | "select_version"
  | "compare_clauses"
  | "recheck_missing"
  | "generate_report";

export type SemanticStatus =
  | "processing"
  | "needs_confirmation"
  | "issue"
  | "conflict"
  | "insufficient_data"
  | "completed";

export interface PipelineStepMeta {
  id: PipelineStepId;
  index: number;
  shortLabel: string;
  title: string;
  description: string;
  defaultStatus: SemanticStatus;
}

export interface DocumentClause {
  id: string;
  sectionId: string;
  code: string;
  title: string;
  text: string;
  conceptIds: string[];
  /** Optional highlights inside text */
  highlightPhrases?: string[];
  /** Page index (1-based) in the uploaded document */
  pageNumber?: number;
  /** Optional parent clause ID for CHILD_OF hierarchy */
  parentClauseId?: string;
  /** Step index from which this clause opens */
  revealAtStep: number;
}

export interface DocumentSection {
  id: string;
  kind: "main" | "addendum";
  fileName: string;
  title: string;
  signedDate?: string;
  clauses: DocumentClause[];
  revealAtStep: number;
}

export interface ExtractedFact {
  id: string;
  key: string;
  label: string;
  value: string;
  sourceClauseId: string;
  editable?: boolean;
  needsReview?: boolean;
  confidence?: number;
}

export type ContractNodeKind =
  "contract" | "section" | "clause" | "party" | "fact";

export interface ContractGraphNode {
  id: string;
  label: string;
  sublabel?: string;
  kind: ContractNodeKind;
  clauseId?: string;
  conceptIds: string[];
  revealAtStep: number;
  /** Row index (0-based) for deterministic layout in Contract Graph lane */
  laneRow: number;
}

export type ContractEdgeKind =
  "parent_child" | "internal_ref" | "addendum_amends";

export interface ContractGraphEdge {
  id: string;
  from: string;
  to: string;
  kind: ContractEdgeKind;
  label: string;
  effectiveDateLabel?: string;
  revealAtStep: number;
  highlightAtStep: number;
}

export type SevenNodeKind =
  | "Contract"
  | "Part"
  | "Unit"
  | "Value"
  | "Party"
  | "ContractFact"
  | "ConceptInstance";

export type SevenEdgeKind =
  | "HAS_PART"
  | "HAS_UNIT"
  | "CHILD_OF"
  | "HAS_PARTY"
  | "HAS_FACT"
  | "EVIDENCE"
  | "HAS_VALUE"
  | "REFERS_TO"
  | "AMENDS"
  | "ABOUT"
  | "HOLDER";

export interface ContractGraph7Node {
  id: string;
  nodeType: SevenNodeKind;
  label: string;
  sublabel?: string;
  revealAtStep: number;
  partId?: string;
  clauseId?: string;
  parentUnitId?: string;
  pageNumber?: number;
  excerpt?: string;
  rawValue?: string;
  factId?: string;
  conceptId?: string;
  partyRole?: "employer" | "employee";
  effectiveDateLabel?: string;
  legacyNodeId?: string;
}

export interface ContractGraph7Edge {
  id: string;
  from: string;
  to: string;
  edgeType: SevenEdgeKind;
  label: string;
  effectiveDateLabel?: string;
  revealAtStep: number;
}

export interface ContractGraphModel {
  nodes: ContractGraph7Node[];
  edges: ContractGraph7Edge[];
}

export interface LegalConceptNode {
  id: string;
  label: string;
  category: string;
  clauseIds: string[];
  contractNodeIds: string[];
  legalNodeIds: string[];
  status: SemanticStatus;
  revealAtStep: number;
  laneRow: number;
}

export type LegalNodeKind = "statute" | "article" | "decree" | "version";

export interface LegalGraphNode {
  id: string;
  label: string;
  sublabel: string;
  kind: LegalNodeKind;
  citation: string;
  excerpt: string;
  conceptIds: string[];
  revealAtStep: number;
  laneRow: number;
  isSelectedVersion?: boolean;
}

export type LegalEdgeKind =
  | "has_provision"
  | "has_version"
  | "guides"
  | "amends"
  | "replaces"
  | "cites"
  | "repeals";

export interface LegalGraphEdge {
  id: string;
  from: string;
  to: string;
  kind: LegalEdgeKind;
  label: string;
  revealAtStep: number;
  isQueried: boolean;
}

export interface LegalVersionEntry {
  id: string;
  documentCode: string;
  title: string;
  effectiveFrom: string; // YYYY-MM-DD
  effectiveTo?: string; // YYYY-MM-DD
  statusLabel: string;
  note: string;
  legalNodeId: string;
  inForce?: boolean;
}

export interface ComparisonDetail {
  id: string;
  findingId: string;
  conceptId: string;
  conceptLabel: string;
  contractClauseCode: string;
  contractExcerpt: string;
  contractValueLabel: string;
  contractValue: string;
  legalCitation: string;
  legalExcerpt: string;
  legalThresholdLabel: string;
  legalThreshold: string;
  verdict: SemanticStatus;
  reasoning: string;
}

export interface RecheckProbe {
  id: string;
  targetTopic: string;
  suspectedMissingReason: string;
  scannedClauses: string[];
  scanResult: string;
  finalStatus: SemanticStatus;
}

export interface FindingCard {
  id: string;
  title: string;
  status: SemanticStatus;
  severityLabel: string;
  summary: string;
  contractClauseId: string;
  contractClauseRef: string;
  contractQuote: string;
  legalCitation: string;
  legalQuote: string;
  recommendation: string;
  conceptId: string;
  relatedContractNodeIds: string[];
  relatedLegalNodeIds: string[];
  relatedEdgeIds: string[];
  comparisonId?: string;
}

export interface AnalysisScenario {
  warnings?: string[];
  activeUnitIds?: string[];
  activeBatches?: Record<string, string[]>;
  graphModel?: ContractGraphModel;
  candidates?: { id: string; conceptId: string; decision: string }[];
  activeConceptId?: string;
  isBusy?: boolean;
  id: string;
  title: string;
  subtitle: string;
  isDemo: boolean;
  signingDateIso: string; // YYYY-MM-DD
  summaryText: string;
  sections: DocumentSection[];
  extractedFacts: ExtractedFact[];
  contractNodes: ContractGraphNode[];
  contractEdges: ContractGraphEdge[];
  concepts: LegalConceptNode[];
  legalNodes: LegalGraphNode[];
  legalEdges: LegalGraphEdge[];
  legalVersions: LegalVersionEntry[];
  comparisons: ComparisonDetail[];
  recheckProbes: RecheckProbe[];
  findings: FindingCard[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  timestamp: string;
}
