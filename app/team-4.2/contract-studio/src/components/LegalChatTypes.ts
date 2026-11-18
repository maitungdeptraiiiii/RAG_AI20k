export type ChatMode = "general" | "contract" | "graph";

export interface ChatSource {
  n?: number;
  chunk_id?: string;
  source?: string;
  title?: string;
  section?: string;
  page?: number | null;
  score?: number | null;
  text?: string;
  quote?: string;
  store?: string;
  document_status?: string;
  provision_status?: string;
  valid_from?: string | null;
  valid_to?: string | null;
  provenance?: string[];
  anchor_roles?: string[];
  pid?: string;
  citation?: string;
  note?: string;
  source_url?: string;
}

export interface ChatTimelineAnchor {
  role: string;
  start?: string;
  end?: string;
  precision?: string;
  source: string;
}

export interface ChatTransitionRule {
  rule_id: string;
  source_article?: string;
  source_document_key?: string;
  excerpt?: string;
}

export interface ChatTransitionAssessment {
  rule_id: string;
  assessment?: string;
  missing_information?: string[];
}

export interface ChatResponsePayload {
  answer?: string;
  status?: string;
  confidence?: string;
  sources?: ChatSource[];
  citations?: ChatSource[];
  timeline?: {
    anchors?: ChatTimelineAnchor[];
    warnings?: string[];
  };
  certainty?: string;
  transition_rules?: ChatTransitionRule[];
  transition_assessments?: ChatTransitionAssessment[];
  follow_up_questions?: string[];
  query_pii?: Record<string, number>;
  trace?: any;
  path?: any[];
  law?: any[];
  seen_unused?: any[];
  warnings?: string[];
  stats?: {
    steps?: number;
    seen?: number;
    seconds?: number;
    backend?: string;
  };
  contract_units?: any[];
  legal_status?: string;
  contract_warnings?: string[];
}

export interface ChatTurn {
  id: string;
  query: string;
  mode: ChatMode;
  think: boolean;
  asOf?: string;
  contractLabel?: string;
  status: "streaming" | "done" | "error";
  progressText?: string;
  streamedText?: string;
  error?: string;
  data?: ChatResponsePayload;
  graphSteps?: any[];
  timestamp: string;
}

export const ROLE_LABEL: Record<string, string> = {
  signing: "Ký kết",
  contract_effective: "Hợp đồng có hiệu lực",
  performance: "Thực hiện",
  discovery: "Phát hiện",
  dispute: "Tranh chấp",
  evaluation: "Đánh giá",
  unspecified: "Mốc",
};

export const SOURCE_LABEL: Record<string, string> = {
  calendar: "ngày đã chọn",
  question: "từ câu hỏi",
  default: "mặc định hôm nay",
};

export const DOC_STATUS_LABEL: Record<string, [string, string, string]> = {
  verified: ["✓", "Đã xác minh phiên bản", "#166534"],
  partially_verified: ["◐", "Xác minh một phần", "#92400E"],
  unversioned: ["?", "Chưa xác định phiên bản", "#92400E"],
  outdated: ["⊘", "Không còn hiệu lực tại mốc", "#B91C1C"],
  unknown: ["?", "Chưa đủ dữ liệu", "#92400E"],
};

export const ASSESS_LABEL: Record<string, string> = {
  not_applicable: "Không áp dụng",
  potentially_applicable: "Có thể áp dụng — cần xem xét",
  applicable: "Áp dụng (theo phân tích)",
  undetermined: "Chưa xác định — thiếu dữ kiện",
};

export const WARN_LABEL: Record<string, string> = {
  "timeline.default_today":
    "Không thấy mốc thời gian trong câu hỏi — đang áp dụng pháp luật hiện hành.",
  "timeline.llm_failed":
    "Không phân tích được vai trò các mốc; đã dùng nhận diện theo quy tắc.",
  "timeline.evidence_not_found":
    "Đã bỏ một mốc không có căn cứ trong câu hỏi.",
};

export function fmtDay(d?: string | null): string {
  if (!d) return "";
  return d.slice(0, 10).split("-").reverse().join("/");
}

export function agentStatusLabel(status?: string): string {
  return (
    (
      {
        answer: "Đã kiểm chứng theo tài liệu",
        partial: "Mới xác minh được một phần",
        clarify: "Cần làm rõ dữ kiện",
        abstain: "Chưa đủ căn cứ",
        error: "Chưa thể kiểm chứng",
      } as Record<string, string>
    )[status || ""] || "Đã kết thúc"
  );
}

export function formatToolVi(tool: string, args: Record<string, any> = {}): string {
  const shortId = (id?: string) => String(id || "").split(":").slice(-1)[0] || "?";
  const map: Record<string, () => string> = {
    find_units: () =>
      args.text
        ? `Tìm điều khoản chứa “${args.text}”`
        : `Tìm điều khoản ${args.label ? `“${args.label}”` : ""}`.trim(),
    find_concept: () => `Tìm vị trí khái niệm ${args.concept_id || ""}`.trim(),
    expand: () => `Mở các nút kề ${args.node_id ? `của ${shortId(args.node_id)}` : ""}`.trim(),
    find_path: () => `Tìm đường ${args.src ? `từ ${shortId(args.src)} tới ${shortId(args.dst)}` : "giữa hai nút"}`,
    subgraph: () => `Lấy đồ thị con ${args.node_id ? `quanh ${shortId(args.node_id)}` : ""}`.trim(),
    contract_facts: () => "Đọc dữ kiện hợp đồng tại ngày soát",
    law_text_at: () => `Đọc lời văn điều luật ${args.pid || ""}${args.day ? ` ngày ${args.day}` : ""}`.trim(),
    law_changes: () => `Xem các phiên bản điều luật ${args.pid || ""}`.trim(),
    law_guidance: () => `Tìm văn bản hướng dẫn ${args.pid || ""}`.trim(),
    law_references: () => `Xem dẫn chiếu ${args.pid || ""}`.trim(),
    concept_basis: () => `Lấy căn cứ luật của khái niệm ${args.concept_id || ""}`.trim(),
    check_concept: () => `Chạy bộ kiểm luật cho khái niệm ${args.concept_id || ""}`.trim(),
    cypher_query: () => "Truy vấn Cypher trên đồ thị hợp đồng",
  };
  return (map[tool] ? map[tool]() : tool) || tool;
}

export function shortDocTitle(source?: string): string {
  if (!source) return "Văn bản luật";
  const cleaned = source.replace(/^[a-z_]+:/, "");
  const m = cleaned.match(/(?:Luật|Bộ luật|Nghị định|Thông tư|Hợp đồng)[^–—|]{0,42}/i);
  return (m ? m[0] : cleaned).slice(0, 46);
}
