import { Fragment, useState, type ReactNode } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Lock,
  RotateCcw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Volume2,
  VolumeX,
} from "lucide-react";
import {
  ASSESS_LABEL,
  DOC_STATUS_LABEL,
  ROLE_LABEL,
  SOURCE_LABEL,
  WARN_LABEL,
  agentStatusLabel,
  fmtDay,
  formatToolVi,
  shortDocTitle,
  type ChatResponsePayload,
  type ChatSource,
  type ChatTimelineAnchor,
  type ChatTurn,
} from "./LegalChatTypes";

interface LegalChatMessageViewProps {
  turn: ChatTurn;
  isSpeaking: boolean;
  onSpeak: (turnId: string, text: string) => void;
  onStopSpeak: () => void;
  onReask: (turn: ChatTurn) => void;
  onFollowUp: (question: string) => void;
  onOpenCitation: (src: ChatSource) => void;
}

function anchorWhen(a: ChatTimelineAnchor): string {
  if (!a.start) return "chưa xác định";
  if (a.start === a.end) return fmtDay(a.start);
  if (a.precision === "year") return `năm ${a.start.slice(0, 4)}`;
  if (a.precision === "month") return `tháng ${a.start.slice(5, 7)}/${a.start.slice(0, 4)}`;
  return `${fmtDay(a.start)} – ${fmtDay(a.end)}`;
}

function warningText(w: string): string {
  if (WARN_LABEL[w]) return WARN_LABEL[w];
  if (w.startsWith("timeline.calendar_conflict"))
    return "Câu hỏi nhắc một mốc khác ngày đã chọn — đang ưu tiên ngày đã chọn, xem lại nếu chưa đúng.";
  if (w.startsWith("timeline.relative_unresolved"))
    return `Chưa quy được "${w.split(":").slice(1).join(":")}" ra ngày cụ thể — hãy cho ngày rõ hơn.`;
  return w;
}

function findSourceByNum(sources: ChatSource[], numStr: string): ChatSource | undefined {
  return sources.find((s) => String(s.n) === String(numStr));
}

function extractCitationLabel(src: ChatSource | undefined, firstNum: string): string {
  if (!src) return `[${firstNum}]`;
  const sec = src.section || "";
  const art = sec.match(/Điều\s+\d+[a-z]?/i)?.[0];
  const shortDoc = shortDocTitle(src.source || src.title);
  if (art) return `${art} · ${shortDoc}`;
  return shortDoc || `[${firstNum}]`;
}

function renderInline(
  text: string,
  sources: ChatSource[],
  onOpenCitation: (src: ChatSource) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenRe =
    /(\*\*[^*]+\*\*|`[^`]+`|\[([^\]]+)\]\((https?:\/\/[^)]+|\/doc\/[^)]+)\)|\[(\d+(?:\s*[,;]\s*\d+)*)\](?!\())/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = tokenRe.exec(text)) !== null) {
    if (match.index > lastIdx) {
      nodes.push(text.slice(lastIdx, match.index));
    }
    const raw = match[0];
    if (raw.startsWith("**") && raw.endsWith("**")) {
      nodes.push(
        <strong key={key++} className="font-semibold text-stone-900">
          {raw.slice(2, -2)}
        </strong>,
      );
    } else if (raw.startsWith("`") && raw.endsWith("`")) {
      nodes.push(
        <code
          key={key++}
          className="px-1 py-0.5 rounded bg-stone-100 font-mono text-[11px] text-stone-800"
        >
          {raw.slice(1, -1)}
        </code>,
      );
    } else if (match[2] && match[3]) {
      nodes.push(
        <a
          key={key++}
          href={match[3]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#1E3A5F] underline hover:text-[#162C49]"
        >
          {match[2]}
        </a>,
      );
    } else if (match[4]) {
      const nums = match[4].split(/\s*[,;]\s*/).filter(Boolean);
      const firstNum = nums[0];
      const src = findSourceByNum(sources, firstNum);
      const unverified = src?.document_status && src.document_status !== "verified";
      const label = extractCitationLabel(src, firstNum);
      nodes.push(
        <button
          key={key++}
          type="button"
          onClick={() =>
            onOpenCitation(
              src || {
                n: Number(firstNum) || undefined,
                source: `Nguồn [${firstNum}]`,
                text: "Không tìm thấy chi tiết trích dẫn kèm theo.",
              },
            )
          }
          title={src?.section || src?.source || `Xem nguồn [${firstNum}]`}
          className="inline-flex items-center gap-1 mx-0.5 px-1.5 py-0.5 rounded-full border border-slate-300 bg-[#F3F6FA] hover:bg-[#E5EEF7] text-[10.5px] font-medium text-[#1E3A5F] align-baseline transition-colors cursor-pointer"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#1E3A5F]" aria-hidden="true" />
          {unverified && (
            <span className="text-amber-700" title="Căn cứ chưa xác minh đầy đủ">
              ⚠
            </span>
          )}
          <span className="max-w-[160px] truncate">{label}</span>
          {nums.length > 1 && <span className="text-slate-500">+{nums.length - 1}</span>}
        </button>,
      );
    }
    lastIdx = match.index + raw.length;
  }
  if (lastIdx < text.length) nodes.push(text.slice(lastIdx));
  return nodes;
}

function MarkdownAnswer({
  markdown,
  sources,
  onOpenCitation,
}: {
  markdown: string;
  sources: ChatSource[];
  onOpenCitation: (src: ChatSource) => void;
}) {
  const blocks = markdown.trim().split(/\n{2,}/);
  return (
    <div className="space-y-2 text-[12.5px] leading-relaxed text-stone-800 select-text">
      {blocks.map((block, idx) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
          return (
            <ul key={idx} className="list-disc pl-4 space-y-1">
              {lines.map((l, j) => (
                <li key={j}>{renderInline(l.replace(/^\s*[-*•]\s+/, ""), sources, onOpenCitation)}</li>
              ))}
            </ul>
          );
        }
        if (lines.every((l) => /^\s*\d+\.\s+/.test(l))) {
          return (
            <ol key={idx} className="list-decimal pl-4 space-y-1">
              {lines.map((l, j) => (
                <li key={j}>{renderInline(l.replace(/^\s*\d+\.\s+/, ""), sources, onOpenCitation)}</li>
              ))}
            </ol>
          );
        }
        if (lines.length === 1 && /^#{1,3}\s+/.test(lines[0])) {
          const text = lines[0].replace(/^#{1,3}\s+/, "");
          return (
            <h4 key={idx} className="font-semibold text-stone-900 pt-1">
              {renderInline(text, sources, onOpenCitation)}
            </h4>
          );
        }
        return (
          <p key={idx} className="whitespace-pre-wrap">
            {lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {renderInline(line, sources, onOpenCitation)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function HitList({ hits }: { hits: any[] }) {
  if (!hits?.length) {
    return <div className="text-[10.5px] text-stone-400 italic">Không có ứng viên</div>;
  }
  return (
    <div className="space-y-1">
      {hits.map((h, i) => (
        <div
          key={`${h.chunk_id || i}`}
          className="p-1.5 rounded bg-white text-[10.5px] border border-stone-200 space-y-0.5"
        >
          <div className="flex justify-between font-mono text-[9.5px] text-stone-400">
            <span>
              #{h.rank ?? i + 1} · {h.section || "Điều luật"}
            </span>
            {h.score != null && <span className="text-teal-700 font-medium">{h.score}</span>}
          </div>
          <div className="text-stone-800 truncate font-medium">{shortDocTitle(h.source)}</div>
          {h.text && <div className="text-stone-500 line-clamp-2 text-[10px]">{h.text}</div>}
        </div>
      ))}
    </div>
  );
}

function TraceSection({
  data,
  graphSteps,
  sources,
  onOpenCitation,
}: {
  data: ChatResponsePayload;
  graphSteps?: any[];
  sources: ChatSource[];
  onOpenCitation: (src: ChatSource) => void;
}) {
  const trace = data.trace || {};
  const steps = Array.isArray(graphSteps) && graphSteps.length > 0
    ? graphSteps
    : Array.isArray(data.trace)
    ? data.trace
    : [];

  if (steps.length > 0) {
    return (
      <div className="mt-2.5 border border-stone-200 rounded-lg bg-stone-50 p-2.5 text-[11px] space-y-1.5">
        <div className="font-semibold text-stone-700">
          Các bước Agent trên đồ thị ({steps.length} bước)
        </div>
        {steps.map((s: any, i: number) => (
          <div key={i} className="border-l-2 border-slate-300 pl-2 py-0.5 space-y-0.5">
            <div className="font-medium text-stone-800">
              {s.error ? "✗" : "✓"} {s.n || i + 1}. {formatToolVi(s.tool, s.args || {})}
              {s.ms != null && <span className="text-stone-400 ml-1">· {s.ms} ms</span>}
            </div>
            {s.thought && <div className="text-stone-500">{s.thought}</div>}
          </div>
        ))}
      </div>
    );
  }

  if (trace.agent) {
    const budget = trace.agent.budget || {};
    const assessments = trace.agent.assessments || [];
    return (
      <div className="mt-2.5 border border-blue-200 rounded-lg bg-blue-50/40 p-2.5 text-[11px] space-y-2">
        <div className="font-semibold text-blue-700">
          Think · {agentStatusLabel(trace.agent.status)}
        </div>
        <div className="text-stone-500">
          {Number(budget.rounds || 0)} vòng tra cứu · {Number(budget.searches || 0)} truy vấn ·{" "}
          {Number(budget.xref_targets || 0)} dẫn chiếu
        </div>
        {(trace.agent.requirements || []).map((r: any) => {
          const a = assessments.find((x: any) => x.requirement_id === r.id);
          return (
            <div key={r.id} className="pt-1.5 border-t border-blue-100">
              <div className="font-medium text-stone-800">{r.question}</div>
              <div className="text-stone-600">{a?.reason || "Chưa có đánh giá bằng chứng."}</div>
            </div>
          );
        })}
        {trace.agent.scope_warning && (
          <div className="text-stone-500">{trace.agent.scope_warning}</div>
        )}
      </div>
    );
  }

  const arms = trace.arms || {};
  const finalHits = trace.final_hits || [];
  const hasArms = Boolean(arms.bm25?.length || arms.dense?.length || finalHits.length);

  return (
    <div className="mt-2.5 border border-stone-200 rounded-lg bg-stone-50 p-2.5 text-[11px] space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-1 font-semibold text-stone-700 pb-1.5 border-b border-stone-200">
        <span>Minh bạch đối chiếu Retrieval</span>
        <span className="text-[10px] font-normal text-teal-700">
          {trace.context_mode || "threshold"} · {trace.retrieval || "bm25"}
        </span>
      </div>
      {trace.condensed_query && (
        <div className="text-[10.5px] text-stone-500">
          Câu hỏi chuẩn hoá ngữ cảnh: <span className="text-stone-700">{trace.condensed_query}</span>
        </div>
      )}
      {hasArms ? (
        <div className="space-y-2">
          <div>
            <div className="font-semibold text-stone-600 text-[10px] uppercase mb-1">BM25 Lexical</div>
            <HitList hits={arms.bm25 || []} />
          </div>
          <div>
            <div className="font-semibold text-stone-600 text-[10px] uppercase mb-1">Dense Vector</div>
            <HitList hits={arms.dense || []} />
          </div>
          <div>
            <div className="font-semibold text-teal-800 text-[10px] uppercase mb-1">Kết quả cuối (RRF)</div>
            <HitList hits={finalHits} />
          </div>
        </div>
      ) : (
        <div className="space-y-1">
          <div className="text-[10.5px] text-stone-500">
            {sources.length} căn cứ pháp lý được truy xuất:
          </div>
          {sources.slice(0, 6).map((s, i) => {
            const ds = s.document_status ? DOC_STATUS_LABEL[s.document_status] : null;
            return (
              <button
                key={s.chunk_id || i}
                type="button"
                onClick={() => onOpenCitation(s)}
                className="w-full text-left p-1.5 rounded bg-white border border-stone-200 hover:border-slate-300 transition-colors cursor-pointer"
              >
                <div className="flex items-center justify-between gap-1 font-medium text-stone-800">
                  <span className="truncate">
                    [{s.n ?? i + 1}] {shortDocTitle(s.source || s.title)} · {s.section || "Điều luật"}
                  </span>
                  {ds && (
                    <span className="text-[9.5px] shrink-0" style={{ color: ds[2] }}>
                      {ds[0]} {ds[1]}
                    </span>
                  )}
                </div>
                {s.valid_from && (
                  <div className="text-[9.5px] text-stone-400">
                    Hiệu lực {fmtDay(s.valid_from)} → {s.valid_to ? fmtDay(s.valid_to) : "nay"}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function LegalChatMessageView({
  turn,
  isSpeaking,
  onSpeak,
  onStopSpeak,
  onReask,
  onFollowUp,
  onOpenCitation,
}: LegalChatMessageViewProps) {
  const [copied, setCopied] = useState(false);
  const [rated, setRated] = useState<"up" | "down" | null>(null);
  const [showTrace, setShowTrace] = useState(false);

  const data = turn.data || {};
  const mergedSources = [...(data.sources || []), ...(data.citations || [])];
  const uniqueSources: ChatSource[] = [];
  const seenKey = new Set<string>();
  for (const s of mergedSources) {
    const k = String(s.chunk_id || s.n || s.pid || uniqueSources.length);
    if (!seenKey.has(k)) {
      seenKey.add(k);
      uniqueSources.push(s);
    }
  }

  const answerText =
    data.answer || turn.streamedText || (turn.status === "error" ? turn.error || "Lỗi xử lý" : "");
  const piiEntries = Object.entries(data.query_pii || {}).sort(([a], [b]) => a.localeCompare(b));
  const timeline = data.timeline;
  const assessMap = Object.fromEntries(
    (data.transition_assessments || []).map((t) => [t.rule_id, t]),
  );

  const handleCopy = () => {
    if (!answerText) return;
    navigator.clipboard.writeText(answerText).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="space-y-2.5">
      {/* User Bubble */}
      <div className="flex justify-end">
        <div className="bg-[#1E3A5F] text-white rounded-2xl rounded-tr-xs px-3.5 py-2 max-w-[88%] text-[12.5px] leading-relaxed shadow-2xs space-y-1">
          {(turn.contractLabel || turn.asOf || turn.think || turn.mode === "graph") && (
            <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-200">
              {turn.mode === "graph" && (
                <span className="px-1.5 py-0.5 rounded bg-white/15">Đồ thị 7-node</span>
              )}
              {turn.contractLabel && (
                <span className="px-1.5 py-0.5 rounded bg-white/15 truncate max-w-[180px]">
                  📎 {turn.contractLabel}
                </span>
              )}
              {turn.think && (
                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-blue-400/25 text-blue-100">
                  <Sparkles className="w-2.5 h-2.5" /> Think
                </span>
              )}
              {turn.asOf && (
                <span className="px-1.5 py-0.5 rounded bg-white/15">
                  Mốc {fmtDay(turn.asOf)}
                </span>
              )}
            </div>
          )}
          <div className="whitespace-pre-wrap">{turn.query}</div>
        </div>
      </div>

      {/* Assistant Area */}
      <div className="bg-[#FAF9F6] border border-stone-200 rounded-2xl rounded-tl-xs p-3 space-y-2">
        {turn.status === "streaming" && !turn.streamedText && (
          <div className="flex items-center gap-2 text-[11.5px] text-stone-500 py-1">
            <span className="inline-flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#1E3A5F] animate-bounce" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#1E3A5F] animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#1E3A5F] animate-bounce [animation-delay:300ms]" />
            </span>
            <span>{turn.progressText || "Đang phân rã câu hỏi & tra cứu căn cứ..."}</span>
          </div>
        )}

        {turn.status === "error" && (
          <div className="p-2.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-[12px]">
            ⚠️ {turn.error || "Chưa thể xử lý câu hỏi."}
          </div>
        )}

        {/* Timeline Anchors */}
        {timeline?.anchors && timeline.anchors.length > 0 && (
          <div className="space-y-1 pb-1.5 border-b border-stone-200/80">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-stone-500">
              Mốc pháp lý đang sử dụng
            </div>
            <div className="flex flex-wrap gap-1">
              {timeline.anchors.map((a, i) => (
                <span
                  key={i}
                  className="inline-flex items-baseline gap-1 bg-white border border-stone-200 rounded px-1.5 py-0.5 text-[10.5px]"
                >
                  <span className="text-stone-500">{ROLE_LABEL[a.role] || a.role}</span>
                  <span className="font-medium text-stone-800">{anchorWhen(a)}</span>
                  <span className="text-[9.5px] text-stone-400">
                    ({SOURCE_LABEL[a.source] || a.source})
                  </span>
                </span>
              ))}
            </div>
            {(timeline.warnings || []).map((w, i) => (
              <div key={i} className="text-[10.5px] text-amber-800">
                ⚠ {warningText(w)}
              </div>
            ))}
          </div>
        )}

        {/* Think Agent Status Pill */}
        {data.trace?.agent && (
          <div
            className={`text-[11px] font-medium ${
              data.status === "answer" ? "text-blue-700" : "text-amber-700"
            }`}
          >
            Think · {agentStatusLabel(data.status)}
          </div>
        )}

        {/* Answer Text (streaming or final Markdown + citations) */}
        {answerText && (
          <MarkdownAnswer
            markdown={answerText}
            sources={uniqueSources}
            onOpenCitation={onOpenCitation}
          />
        )}

        {/* Certainty Warning */}
        {data.certainty && data.certainty !== "firm" && (
          <div className="text-[11px] rounded-lg px-2.5 py-1.5 border border-amber-300 bg-amber-50 text-amber-900">
            ⚠{" "}
            {data.certainty === "cannot_conclude"
              ? "Chưa đủ căn cứ để kết luận."
              : "Kết luận có điều kiện — phụ thuộc vào căn cứ chưa xác minh đầy đủ, quy định chuyển tiếp hoặc mốc thời gian chưa đủ cụ thể."}
          </div>
        )}

        {/* Transition Rules */}
        {data.transition_rules && data.transition_rules.length > 0 && (
          <div className="border border-stone-200 bg-white rounded-lg p-2 space-y-1.5">
            <div className="text-[11px] font-semibold text-stone-800">
              Quy định chuyển tiếp cần xem xét
            </div>
            {data.transition_rules.map((r) => {
              const a = assessMap[r.rule_id] || {};
              return (
                <div key={r.rule_id} className="text-[11px] border-t border-stone-100 pt-1">
                  <div className="font-medium text-stone-800">
                    {r.source_article} — {r.source_document_key}{" "}
                    <span
                      className={
                        a.assessment === "not_applicable" ? "text-emerald-700" : "text-amber-700"
                      }
                    >
                      · {ASSESS_LABEL[a.assessment || ""] || "Chưa đánh giá"}
                    </span>
                  </div>
                  {r.excerpt && (
                    <div className="text-stone-500 text-[10.5px] line-clamp-3">{r.excerpt}</div>
                  )}
                  {!!a.missing_information?.length && (
                    <div className="text-stone-600 text-[10.5px]">
                      Cần bổ sung: {a.missing_information.join("; ")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Graph QA Citations */}
        {data.law && data.law.length > 0 && (
          <div className="pt-1.5 border-t border-stone-200 space-y-1">
            <div className="text-[10px] font-semibold uppercase text-stone-500">
              Căn cứ luật trên đồ thị
            </div>
            {data.law.map((l: any, i: number) => (
              <div
                key={l.pid || i}
                className="text-[11px] bg-white border border-stone-200 rounded p-1.5 space-y-0.5"
              >
                <div className="font-medium text-stone-800">{l.citation || l.pid}</div>
                {l.valid_from && (
                  <div className="text-[10px] text-stone-400">
                    Hiệu lực {fmtDay(l.valid_from)} → {l.valid_to ? fmtDay(l.valid_to) : "nay"}
                  </div>
                )}
                {l.text && <div className="text-[10.5px] text-stone-600 line-clamp-3">{l.text}</div>}
              </div>
            ))}
          </div>
        )}

        {/* Follow-up Questions */}
        {data.follow_up_questions && data.follow_up_questions.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {data.follow_up_questions.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onFollowUp(q)}
                className="text-[10.5px] text-left bg-white border border-stone-300 hover:bg-slate-100 text-stone-700 rounded-full px-2.5 py-1 transition-colors cursor-pointer"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* PII Masking Notice */}
        {piiEntries.length > 0 && (
          <div className="flex items-center gap-1 text-[10.5px] text-stone-500">
            <Lock className="w-3 h-3 shrink-0" />
            <span>
              Đã ẩn thông tin cá nhân trước khi gửi đi (
              {piiEntries.map(([k, n]) => `${k} ×${n}`).join(", ")}).
            </span>
          </div>
        )}

        {/* Action Bar */}
        {turn.status === "done" && (
          <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-stone-200/80 text-stone-400">
            <button
              type="button"
              onClick={handleCopy}
              title="Sao chép câu trả lời"
              className="p-1 rounded hover:bg-stone-200/60 hover:text-stone-700 transition-colors cursor-pointer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-700" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
            <button
              type="button"
              onClick={() => setRated((r) => (r === "up" ? null : "up"))}
              title="Câu trả lời tốt"
              className={`p-1 rounded hover:bg-stone-200/60 transition-colors cursor-pointer ${
                rated === "up" ? "text-stone-900 bg-stone-200" : "hover:text-stone-700"
              }`}
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setRated((r) => (r === "down" ? null : "down"))}
              title="Câu trả lời chưa tốt"
              className={`p-1 rounded hover:bg-stone-200/60 transition-colors cursor-pointer ${
                rated === "down" ? "text-stone-900 bg-stone-200" : "hover:text-stone-700"
              }`}
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => (isSpeaking ? onStopSpeak() : onSpeak(turn.id, answerText))}
              title={isSpeaking ? "Dừng đọc" : "Đọc câu trả lời"}
              className={`p-1 rounded hover:bg-stone-200/60 transition-colors cursor-pointer ${
                isSpeaking ? "text-blue-600 bg-blue-50" : "hover:text-stone-700"
              }`}
            >
              {isSpeaking ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
            </button>
            <button
              type="button"
              onClick={() => onReask(turn)}
              title="Hỏi lại"
              className="p-1 rounded hover:bg-stone-200/60 hover:text-stone-700 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setShowTrace((v) => !v)}
              className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10.5px] font-medium text-stone-600 hover:bg-stone-200/60 hover:text-stone-900 transition-colors cursor-pointer"
            >
              <span>Minh bạch đối chiếu</span>
              {showTrace ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          </div>
        )}

        {/* Retrieval / Think / Graph Trace */}
        {showTrace && turn.status === "done" && (
          <TraceSection
            data={data}
            graphSteps={turn.graphSteps}
            sources={uniqueSources}
            onOpenCitation={onOpenCitation}
          />
        )}
      </div>
    </div>
  );
}
