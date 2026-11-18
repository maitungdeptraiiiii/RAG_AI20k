import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Check,
  Copy,
  Download,
  FileText,
  Loader2,
  Printer,
  RefreshCw,
  Scale,
  Sparkles,
  X,
} from "lucide-react";
import type { AnalysisScenario } from "../types/contract";
import { StatusBadge } from "./StatusBadge";

interface ReportCanvasDrawerProps {
  open: boolean;
  scenario: AnalysisScenario;
  markdown: string;
  isGenerating: boolean;
  llmUsed: boolean;
  error: string;
  onClose: () => void;
  onRegenerate: () => void;
  onSelectFinding: (findingId: string) => void;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      out.push(
        <strong key={k++} className="font-semibold text-stone-900">
          {tok.slice(2, -2)}
        </strong>,
      );
    } else {
      out.push(
        <code
          key={k++}
          className="px-1.5 py-0.5 rounded bg-stone-100 font-mono text-[11.5px] text-stone-800"
        >
          {tok.slice(1, -1)}
        </code>,
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function CanvasMarkdownDocument({ markdown }: { markdown: string }) {
  const blocks = useMemo(() => {
    const rawLines = markdown.replace(/\r\n/g, "\n").split("\n");
    const groups: string[][] = [];
    let cur: string[] = [];
    for (const line of rawLines) {
      if (!line.trim()) {
        if (cur.length) {
          groups.push(cur);
          cur = [];
        }
      } else {
        cur.push(line);
      }
    }
    if (cur.length) groups.push(cur);
    return groups;
  }, [markdown]);

  return (
    <div className="space-y-3 text-[13.5px] leading-relaxed text-stone-800 select-text">
      {blocks.map((lines, idx) => {
        if (lines.length === 1 && /^#\s+/.test(lines[0])) {
          return (
            <h1
              key={idx}
              className="font-serif text-[20px] font-bold text-stone-900 pb-2 border-b border-stone-200"
            >
              {renderInlineMarkdown(lines[0].replace(/^#\s+/, ""))}
            </h1>
          );
        }
        if (lines.length === 1 && /^##\s+/.test(lines[0])) {
          return (
            <h2
              key={idx}
              className="font-serif text-[15.5px] font-semibold text-[#1E3A5F] pt-3 border-t border-stone-100 first:border-t-0 first:pt-0"
            >
              {renderInlineMarkdown(lines[0].replace(/^##\s+/, ""))}
            </h2>
          );
        }
        if (lines.length === 1 && /^###\s+/.test(lines[0])) {
          return (
            <h3 key={idx} className="text-[13.5px] font-semibold text-stone-900 pt-1.5">
              {renderInlineMarkdown(lines[0].replace(/^###\s+/, ""))}
            </h3>
          );
        }
        if (lines.every((l) => /^>\s?/.test(l))) {
          return (
            <blockquote
              key={idx}
              className="border-l-4 border-[#1E3A5F] bg-[#F3F6FA] px-3.5 py-2.5 rounded-r-lg text-[12.5px] text-stone-800 space-y-1"
            >
              {lines.map((l, j) => (
                <div key={j}>{renderInlineMarkdown(l.replace(/^>\s?/, ""))}</div>
              ))}
            </blockquote>
          );
        }
        if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
          return (
            <ul key={idx} className="list-disc pl-5 space-y-1.5">
              {lines.map((l, j) => (
                <li key={j}>{renderInlineMarkdown(l.replace(/^\s*[-*•]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        if (lines.every((l) => /^\s*\d+\.\s+/.test(l))) {
          return (
            <ol key={idx} className="list-decimal pl-5 space-y-1.5">
              {lines.map((l, j) => (
                <li key={j}>{renderInlineMarkdown(l.replace(/^\s*\d+\.\s+/, ""))}</li>
              ))}
            </ol>
          );
        }
        if (
          lines.length >= 2 &&
          lines[0].includes("|") &&
          /^\|?[\s:-]+\|/.test(lines[1])
        ) {
          const splitRow = (r: string) =>
            r
              .trim()
              .replace(/^\|/, "")
              .replace(/\|$/, "")
              .split("|")
              .map((c) => c.trim());
          const headers = splitRow(lines[0]);
          const rows = lines.slice(2).map(splitRow);
          return (
            <div key={idx} className="overflow-x-auto border border-stone-200 rounded-lg">
              <table className="w-full text-[12px] border-collapse">
                <thead className="bg-[#FAF9F6] border-b border-stone-200">
                  <tr>
                    {headers.map((h, hi) => (
                      <th key={hi} className="text-left px-3 py-2 font-semibold text-stone-800">
                        {renderInlineMarkdown(h)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {rows.map((r, ri) => (
                    <tr key={ri}>
                      {r.map((cell, ci) => (
                        <td key={ci} className="px-3 py-2 text-stone-700 align-top">
                          {renderInlineMarkdown(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={idx} className="whitespace-pre-wrap">
            {lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {renderInlineMarkdown(line)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

export function ReportCanvasDrawer({
  open,
  scenario,
  markdown,
  isGenerating,
  llmUsed,
  error,
  onClose,
  onRegenerate,
  onSelectFinding,
}: ReportCanvasDrawerProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const counts = useMemo(() => {
    const issue = scenario.findings.filter(
      (f) => f.status === "issue" || f.status === "conflict",
    ).length;
    const attention = scenario.findings.filter(
      (f) => f.status === "insufficient_data" || f.status === "needs_confirmation",
    ).length;
    const ok = scenario.findings.length - issue - attention;
    return { issue, attention, ok };
  }, [scenario.findings]);

  const handleCopy = () => {
    if (!markdown) return;
    navigator.clipboard.writeText(markdown).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    });
  };

  const handleDownloadMd = () => {
    if (!markdown) return;
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bao-cao-${scenario.id || "hop-dong"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Dimmed backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-stone-950/25 backdrop-blur-[1px] z-40"
          />

          {/* ChatGPT-style Right Slide-Over Canvas */}
          <motion.aside
            aria-label="Canvas Báo cáo chi tiết"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="fixed top-0 right-0 h-full w-[min(700px,95vw)] bg-white border-l border-stone-200 shadow-[-16px_0_48px_rgba(0,0,0,0.14)] z-50 flex flex-col"
          >
            {/* Header */}
            <div className="px-5 py-3.5 border-b border-stone-200 bg-white flex items-center justify-between gap-3 shrink-0">
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-[#EDF3F9] text-[#1E3A5F] border border-[#CBD5E1] shrink-0">
                  <Sparkles className="w-3 h-3" />
                  <span>Canvas Báo cáo</span>
                </span>
                <div className="min-w-0">
                  <h2 className="font-serif text-[14.5px] font-semibold text-stone-900 truncate">
                    {scenario.title}
                  </h2>
                  <p className="text-[11px] text-stone-500 truncate">
                    {scenario.signingDateIso
                      ? `Mốc ngày ký ${scenario.signingDateIso.split("-").reverse().join("/")}`
                      : "Báo cáo tổng hợp từ Contract Graph & Legal Graph"}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  disabled={isGenerating}
                  onClick={onRegenerate}
                  title="Tổng hợp lại báo cáo bằng LLM"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11.5px] font-medium text-stone-600 hover:text-stone-900 hover:bg-stone-100 disabled:opacity-40 transition-colors cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isGenerating ? "animate-spin" : ""}`} />
                  <span className="hidden sm:inline">Viết lại AI</span>
                </button>
                <button
                  type="button"
                  disabled={!markdown}
                  onClick={handleCopy}
                  title="Sao chép Markdown"
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11.5px] font-medium text-stone-600 hover:text-stone-900 hover:bg-stone-100 disabled:opacity-40 transition-colors cursor-pointer"
                >
                  {copied ? (
                    <Check className="w-3.5 h-3.5 text-emerald-700" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                  <span className="hidden sm:inline">{copied ? "Đã chép" : "Sao chép"}</span>
                </button>
                <button
                  type="button"
                  disabled={!markdown}
                  onClick={handleDownloadMd}
                  title="Tải file Markdown (.md)"
                  className="p-1.5 rounded-lg text-stone-600 hover:text-stone-900 hover:bg-stone-100 disabled:opacity-40 transition-colors cursor-pointer"
                >
                  <Download className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  disabled={!markdown}
                  onClick={() => window.print()}
                  title="In hoặc xuất PDF"
                  className="p-1.5 rounded-lg text-stone-600 hover:text-stone-900 hover:bg-stone-100 disabled:opacity-40 transition-colors cursor-pointer"
                >
                  <Printer className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  title="Đóng Canvas (Esc)"
                  className="p-1.5 rounded-lg text-stone-400 hover:text-stone-900 hover:bg-stone-100 transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Subheader Banner */}
            <div className="px-5 py-2 bg-[#FAF9F6] border-b border-stone-200 flex flex-wrap items-center justify-between gap-2 text-[11px] shrink-0">
              <div className="flex items-center gap-2 text-stone-600">
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    isGenerating ? "bg-amber-500 animate-pulse" : "bg-emerald-600"
                  }`}
                />
                <span>
                  {isGenerating
                    ? "LLM đang viết báo cáo có cấu trúc từ kết quả đối chiếu..."
                    : llmUsed
                    ? "Báo cáo do LLM tổng hợp từ dữ liệu đối chiếu đã xác minh"
                    : "Báo cáo tổng hợp có cấu trúc theo danh mục kiểm tra"}
                </span>
              </div>
              <div className="flex items-center gap-2 font-mono text-[10.5px]">
                <span className="text-[#991B1B]">{counts.issue} vi phạm</span>
                <span className="text-stone-300">·</span>
                <span className="text-[#92400E]">{counts.attention} lưu ý</span>
                <span className="text-stone-300">·</span>
                <span className="text-[#166534]">{counts.ok} đạt</span>
              </div>
            </div>

            {/* Canvas Scrollable Document */}
            <div className="flex-1 overflow-y-auto thin-scroll bg-[#F7F6F2] p-4 sm:p-6 space-y-5">
              {/* Highlight Quick Summary Bar */}
              <div className="grid grid-cols-3 gap-2.5">
                <div className="rounded-lg bg-white border border-stone-200 p-3">
                  <div className="text-[10.5px] text-stone-500">Vi phạm / Thiếu sót</div>
                  <div className="text-lg font-mono font-bold text-[#991B1B] tabular-nums">
                    {counts.issue}
                  </div>
                </div>
                <div className="rounded-lg bg-white border border-stone-200 p-3">
                  <div className="text-[10.5px] text-stone-500">Quyền / Cần lưu ý</div>
                  <div className="text-lg font-mono font-bold text-[#92400E] tabular-nums">
                    {counts.attention}
                  </div>
                </div>
                <div className="rounded-lg bg-white border border-stone-200 p-3">
                  <div className="text-[10.5px] text-stone-500">Hạng mục phù hợp</div>
                  <div className="text-lg font-mono font-bold text-[#166534] tabular-nums">
                    {counts.ok}
                  </div>
                </div>
              </div>

              {/* Paper Surface */}
              <div className="bg-white border border-stone-200 rounded-xl p-5 sm:p-6 shadow-2xs space-y-4">
                {error && (
                  <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-800">
                    {error}
                  </div>
                )}

                {isGenerating && !markdown ? (
                  <div className="py-10 text-center space-y-2.5 text-stone-500">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto text-[#1E3A5F]" />
                    <div className="text-xs font-medium text-stone-700">
                      Đang tổng hợp báo cáo chi tiết...
                    </div>
                    <p className="text-[11px] text-stone-400">
                      Sắp xếp theo mức độ ưu tiên, dẫn chiếu điều khoản hợp đồng và căn cứ pháp luật.
                    </p>
                  </div>
                ) : markdown ? (
                  <div>
                    <CanvasMarkdownDocument markdown={markdown} />
                    {isGenerating && (
                      <span className="inline-block w-1.5 h-4 ml-1 bg-[#1E3A5F] animate-pulse align-middle" />
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-stone-500 flex items-center gap-2 py-4">
                    <FileText className="w-4 h-4" />
                    <span>Chưa có nội dung báo cáo. Bấm “Viết lại AI” để tổng hợp.</span>
                  </div>
                )}
              </div>

              {/* Interactive Reference Links Back to Graph */}
              {scenario.findings.length > 0 && (
                <div className="bg-white border border-stone-200 rounded-xl p-4 space-y-2.5">
                  <div className="flex items-center justify-between text-xs font-semibold text-stone-800">
                    <span className="inline-flex items-center gap-1.5">
                      <Scale className="w-3.5 h-3.5 text-[#1E3A5F]" />
                      <span>Đối chiếu từng phát hiện trên đồ thị</span>
                    </span>
                    <span className="text-[10.5px] font-normal text-stone-400">
                      Chọn để tô sáng liên kết
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {scenario.findings.map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        onClick={() => {
                          onSelectFinding(f.id);
                          onClose();
                        }}
                        className="w-full text-left rounded-lg border border-stone-200 bg-[#FAF9F6] hover:bg-[#EDF3F9] px-3 py-2 flex items-center justify-between gap-2 transition-colors cursor-pointer"
                      >
                        <div className="min-w-0">
                          <div className="text-xs font-medium text-stone-900 truncate">
                            {f.title}
                          </div>
                          <div className="text-[10.5px] font-mono text-stone-500 truncate">
                            {f.contractClauseRef} · {f.legalCitation}
                          </div>
                        </div>
                        <StatusBadge status={f.status} customLabel={f.severityLabel} compact />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
