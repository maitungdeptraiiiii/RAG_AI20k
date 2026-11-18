import { useEffect, useMemo, useRef, useState } from "react";
import { FileUp, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { motion } from "motion/react";
import { DualGraphCanvas } from "./components/DualGraphCanvas";
import { DocumentPanel } from "./components/DocumentPanel";
import { InspectorPanel } from "./components/InspectorPanel";
import { LegalChatPopup } from "./components/LegalChatPopup";
import { PipelineHeaderRail } from "./components/PipelineHeaderRail";
import { ReportCanvasDrawer } from "./components/ReportCanvasDrawer";
import { StageOutcomePanel } from "./components/StageOutcomePanel";
import { buildHighlightTrace } from "./engine/pipelineState";
import {
  applyEvent,
  applySnapshot,
  emptyScenario,
  choreographyFor,
  particlesFor,
  stepFor,
} from "./live/model";
import { request, stream, jsonBody } from "./live/api";
import type { AnalysisScenario } from "./types/contract";

export default function App() {
  const [scenario, setScenario] = useState<AnalysisScenario | null>(null);
  const [card, setCard] = useState<any>(null);
  const [step, setStep] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [message, setMessage] = useState(""),
    [selected, setSelected] = useState<string | null>(null);
  const [stages, setStages] = useState<Record<number, string>>({});
  const [answers, setAnswers] = useState<
    Record<string, { action: string; value?: string }>
  >({});
  const [persist, setPersist] = useState(false);
  const [showVerify, setShowVerify] = useState(false);
  const [showAllFields, setShowAllFields] = useState(false);
  const [replayNonce, setReplayNonce] = useState(0);
  const [stepElapsedMs, setStepElapsedMs] = useState(0);
  const [reportCanvasOpen, setReportCanvasOpen] = useState(false);
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [reportLoading, setReportLoading] = useState(false);
  const [reportLlmUsed, setReportLlmUsed] = useState(false);
  const [reportError, setReportError] = useState("");
  const reportFetchingRef = useRef(false);
  const reportReqIdRef = useRef(0);
  useEffect(() => {
    setStepElapsedMs(0);
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const delta = now - last;
      last = now;
      setStepElapsedMs((prev) => {
        const next = prev + delta;
        if (next >= 4500) {
          window.clearInterval(timer);
          return 4500;
        }
        return next;
      });
    }, 40);
    return () => window.clearInterval(timer);
  }, [step, replayNonce]);
  const input = useRef<HTMLInputElement>(null),
    operation = useRef(false),
    analyzingRef = useRef(false),
    mounted = useRef(true);
  const details = useRef<HTMLDivElement>(null);
  const current = useRef<AnalysisScenario | null>(null);
  function update(fn: (s: AnalysisScenario) => AnalysisScenario) {
    const next = fn(current.current || emptyScenario());
    current.current = next;
    setScenario(next);
  }
  function receive(e: any) {
    if (!mounted.current) return;
    update((s) => applyEvent(s, e));
    if (e.card) {
      setCard(e.card);
      sessionStorage.setItem("contract-studio-cid", e.card.contract_id);
    }
    setStep((prev) => {
      const target = stepFor(e, prev);
      return analyzingRef.current ? Math.min(3, Math.max(2, target)) : target;
    });
    const i = stepFor(e, -1);
    if (i >= 0) {
      setStages((p) => ({
        ...p,
        [i]:
          e.type === "stage"
            ? e.status === "done"
              ? "done"
              : "running"
            : "running",
      }));
    }
    if (e.type === "progress")
      setMessage(`Đã đọc ${e.done}/${e.total} lô điều khoản`);
    else if (e.type === "legal_candidate") setMessage(`Đang truy vấn ${e.pid}`);
    else if (e.type === "legal_resolution")
      setMessage(
        `${e.pid}: ${e.decision === "kept" ? "có phiên bản tại mốc đánh giá" : e.decision === "excluded" ? "không được chọn" : "chưa đủ dữ liệu"}`,
      );
    else if (e.type === "recheck")
      setMessage(`Kiểm tra lại: ${e.label || e.concept_id}`);
    else if (e.type === "stage")
      setMessage(
        (
          {
            read: "Đọc tài liệu",
            facts: "Trích dữ kiện",
            tag: "Nhận diện concept",
            evaluate: "Đối chiếu dữ kiện",
            recheck: "Kiểm tra nội dung còn thiếu",
            basis: "Tìm căn cứ luật",
          } as any
        )[e.stage] || e.stage,
      );
  }
  async function open(cid: string) {
    try {
      const data = await request(
        `/api/contracts/${encodeURIComponent(cid)}/studio`,
      );
      if (!mounted.current) return;
      update((s) => applySnapshot(s, data));
      setCard(data.card);
      setStep(data.last_check ? 8 : 1);
      setMessage(
        data.last_check
          ? "Đã tải kết quả lưu gần nhất"
          : "Hãy xác minh thông tin trước khi phân tích",
      );
    } catch (e: any) {
      if (mounted.current) setError(e.message);
    }
  }
  useEffect(() => {
    mounted.current = true;
    const cid =
      new URLSearchParams(location.search).get("contract") ||
      sessionStorage.getItem("contract-studio-cid");
    if (cid) void open(cid);
    return () => {
      mounted.current = false;
    };
  }, []);

  async function upload(file: File) {
    if (file.size > 50 * 1024 * 1024) {
      setError("File quá lớn: tối đa 50 MB");
      return;
    }
    if (operation.current) return;
    operation.current = true;
    setBusy(true);
    setError("");
    setCard(null);
    setSelected(null);
    setAnswers({});
    setReportCanvasOpen(false);
    setReportMarkdown("");
    setReportError("");
    setReportLlmUsed(false);
    setStages({ 0: "running" });
    setStep(0);
    current.current = emptyScenario();
    setScenario(current.current);
    setMessage("Đang tải file và đọc nội dung");
    const form = new FormData();
    form.append("file", file);
    form.append("persist", persist ? "1" : "0");
    try {
      await stream(
        "/api/contract-studio/upload/stream",
        { method: "POST", body: form },
        receive,
      );
      if (!mounted.current) return;
      if (current.current?.graphModel?.nodes.length) {
        setStep(0);
        setReplayNonce((n) => n + 1);
        setMessage("Đang dựng đồ thị hợp đồng 4 tầng (Contract -> Part -> Unit -> Value)");
        await new Promise((resolve) => window.setTimeout(resolve, 3400));
        if (!mounted.current) return;
      }
      setStep(1);
      setReplayNonce((n) => n + 1);
      setStages((p) => ({ ...p, 0: "done", 1: "running" }));
      setMessage("Kiểm tra và xác nhận các thông tin được trích xuất");
    } catch (e: any) {
      setError(e.message);
      setMessage("Chưa hoàn tất đọc hợp đồng");
    } finally {
      setBusy(false);
      operation.current = false;
      if (input.current) input.current.value = "";
    }
  }
  async function analyze(targetCard = card) {
    if (!targetCard || operation.current) return;
    operation.current = true;
    analyzingRef.current = true;
    setBusy(true);
    setError("");
    setSelected(null);
    setShowVerify(false);
    setReportCanvasOpen(false);
    setReportMarkdown("");
    setReportError("");
    setReportLlmUsed(false);
    setStep(2);
    setReplayNonce((n) => n + 1);
    setStages({ 0: "done", 1: "done", 2: "running" });
    setMessage("Thu gọn Contract Graph & nhận diện concept");
    update((s) => ({
      ...s,
      concepts: [],
      candidates: [],
      findings: [],
      comparisons: [],
      recheckProbes: [],
      legalNodes: [],
      legalEdges: [],
      legalVersions: [],
      summaryText: "",
      warnings: [],
    }));
    try {
      await stream(
        `/api/contracts/${encodeURIComponent(targetCard.contract_id)}/studio/analyze/stream`,
        jsonBody({}),
        receive,
      );
      if (!mounted.current) return;
      analyzingRef.current = false;

      // Bước 5: Tập hợp đám mây hạt ở tâm (Legal Graph chưa mở)
      setStep(4);
      setReplayNonce((n) => n + 1);
      setStages((p) => ({ ...p, 2: "done", 3: "done", 4: "running" }));
      setMessage("Đang tập hợp các neo & chuỗi văn bản vào đám mây ứng viên...");
      await new Promise((r) => setTimeout(r, 2500));
      if (!mounted.current) return;

      // Bước 6: Lọc tách cụm (lên trên: Hiệu lực · Phù hợp | xuống dưới: Hết hiệu lực / Loại) -> mở Legal Graph
      setStep(5);
      setReplayNonce((n) => n + 1);
      setStages((p) => ({ ...p, 4: "done", 5: "running" }));
      setMessage("Đang lọc hiệu lực theo ngày ký & tách cụm kết quả...");
      await new Promise((r) => setTimeout(r, 3600));
      if (!mounted.current) return;

      // Bước 7 -> 9: Đối chiếu Legal Graph & tổng hợp báo cáo sau Legal Graph (kích hoạt LLM viết báo cáo)
      setStep(6);
      setReplayNonce((n) => n + 1);
      setStages((p) => ({ ...p, 5: "done", 6: "running", 7: "done" }));
      setMessage("Đang đối chiếu với Legal Graph & tổng hợp báo cáo...");
      void generateReport(targetCard.contract_id, false);
      await new Promise((r) => setTimeout(r, 2400));
      if (!mounted.current) return;

      setStep(8);
      setReplayNonce((n) => n + 1);
      setStages((p) => ({
        ...Object.fromEntries(Object.entries(p).map(([k]) => [k, "done"])),
        8: "done",
      }));
      setMessage("Hoàn tất tổng hợp báo cáo");
    } catch (e: any) {
      analyzingRef.current = false;
      setError(e.message);
      setMessage(
        "Phân tích chưa hoàn tất — dữ liệu đang hiển thị có thể là kết quả từng phần",
      );
    } finally {
      analyzingRef.current = false;
      setBusy(false);
      operation.current = false;
    }
  }
  async function generateReport(cid: string, force = false) {
    if (!cid || (reportFetchingRef.current && !force)) return;
    const reqId = ++reportReqIdRef.current;
    reportFetchingRef.current = true;
    setReportLoading(true);
    setReportError("");
    if (force) setReportMarkdown("");
    try {
      await stream(
        `/api/contracts/${encodeURIComponent(cid)}/studio/report/stream`,
        jsonBody({ force }),
        (evt) => {
          if (!mounted.current || reqId !== reportReqIdRef.current) return;
          if (evt.type === "token" && evt.delta) {
            setReportMarkdown((prev) => prev + evt.delta);
          } else if (evt.type === "done") {
            if (evt.markdown) setReportMarkdown(evt.markdown);
            setReportLlmUsed(Boolean(evt.llm_used));
          }
        },
      );
    } catch (e: any) {
      if (mounted.current && reqId === reportReqIdRef.current) {
        setReportError(e?.message || "Không tổng hợp được báo cáo.");
      }
    } finally {
      if (reqId === reportReqIdRef.current) {
        reportFetchingRef.current = false;
        if (mounted.current) setReportLoading(false);
      }
    }
  }
  function openReportCanvas() {
    setReportCanvasOpen(true);
    if (card?.contract_id && !reportMarkdown && !reportFetchingRef.current) {
      void generateReport(card.contract_id, false);
    }
  }
  async function verify() {
    if (operation.current || !card) return;
    operation.current = true;
    setBusy(true);
    setError("");
    let nextCard: any = null;
    try {
      const payload: Record<string, any> = {};
      for (const field of card.verification.fields) {
        if (answers[field.key]) payload[field.key] = answers[field.key];
        else if (field.status === "found")
          payload[field.key] = { action: "confirm" };
      }
      const c = await request(
        `/api/contracts/${encodeURIComponent(card.contract_id)}/facts`,
        jsonBody({ answers: payload }),
      );
      setCard(c);
      setAnswers({});
      const snap = await request(
        `/api/contracts/${encodeURIComponent(card.contract_id)}/studio`,
      );
      update((s) => applySnapshot(s, snap));
      if (!c.verification.complete)
        throw new Error(
          "Còn thông tin bắt buộc chưa xác nhận. Hãy chọn hoặc nhập giá trị.",
        );
      nextCard = c;
      setShowVerify(false);
      setMessage("Thông tin đã được xác nhận. Đang tự động phân tích...");
      setStages((p) => ({ ...p, 1: "done", 2: "running" }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
      operation.current = false;
    }
    if (nextCard) {
      await analyze(nextCard);
    }
  }
  const [activeNodes, setActiveNodes] = useState<string[]>([]);
  const s = scenario ? { ...scenario, isBusy: busy } : null;
  const trace = useMemo(() => {
    if (!s) return null;
    const t = buildHighlightTrace(s, step, selected);
    activeNodes.forEach((id) => t.contractNodeIds.add(id));
    return t;
  }, [scenario, step, selected, activeNodes]);
  const choreography = s ? choreographyFor(s, step, stepElapsedMs) : null,
    particles = s ? particlesFor(s) : [];
  const selectedFinding = s?.findings.find((f) => f.id === selected) || null;
  const comparison =
    s?.comparisons.find((c) => c.id === selectedFinding?.comparisonId) ||
    s?.comparisons.at(-1) ||
    null;
  const factsConfirmed = !!card?.verification?.complete;
  const chooseClause = (uid: string) => {
    const finding = s?.findings.find((f) => f.contractClauseId === uid);
    if (finding) setSelected(finding.id);
  };
  return (
    <div className="min-h-screen bg-[#F7F6F2] text-stone-900">
      <header className="h-16 border-b border-stone-200 bg-white px-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="font-serif text-xl font-semibold">PhápLý HợpĐồng</h1>
          <p className="text-xs text-stone-500">
            Contract Studio · Phân tích trực tiếp
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <a href="/contracts" className="text-stone-500 hover:underline">
            Giao diện cũ
          </a>
          <label className="inline-flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={persist}
              onChange={(e) => setPersist(e.target.checked)}
              disabled={busy}
            />
            Lưu hợp đồng
          </label>
          <button
            disabled={busy}
            onClick={() => input.current?.click()}
            className="px-4 py-2 rounded bg-[#1E3A5F] text-white inline-flex gap-2 items-center disabled:opacity-50"
          >
            <FileUp size={15} />
            Upload hợp đồng
          </button>
          <input
            ref={input}
            hidden
            type="file"
            accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.tif,.tiff"
            onChange={(e) => {
              if (e.target.files?.[0]) void upload(e.target.files[0]);
            }}
          />
        </div>
      </header>
      {!s ? (
        <main className="max-w-3xl mx-auto mt-28 p-12 border border-dashed border-stone-300 bg-white text-center rounded relative overflow-hidden">
          {busy ? (
            <div className="py-6 space-y-4">
              <Loader2 className="mx-auto text-[#1E3A5F] animate-spin" size={40} />
              <h2 className="font-serif text-xl text-[#1E3A5F]">
                Đang tải lên và phân tích cấu trúc hợp đồng...
              </h2>
              <p className="text-stone-500 text-sm">
                {message || "Hệ thống đang đọc văn bản, OCR (nếu có) và trích xuất dữ kiện."}
              </p>
              <div className="max-w-md mx-auto h-1.5 bg-stone-100 rounded-full overflow-hidden">
                <motion.div
                  className="h-full w-1/2 bg-gradient-to-r from-[#1E3A5F] via-sky-600 to-[#1E3A5F] rounded-full"
                  animate={{ x: ["-100%", "200%"] }}
                  transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>
            </div>
          ) : (
            <>
              <FileUp className="mx-auto text-[#1E3A5F] mb-5" size={36} />
              <h2 className="font-serif text-2xl">
                Đọc và đối chiếu hợp đồng lao động
              </h2>
              <p className="text-stone-500 text-sm mt-3 mb-6">
                Tải file hợp đồng và phụ lục trong cùng tài liệu. Xác nhận thông
                tin, sau đó theo dõi quá trình phân tích và căn cứ được tìm thấy.
              </p>
              <button
                onClick={() => input.current?.click()}
                className="px-5 py-2 bg-[#1E3A5F] text-white rounded hover:bg-[#162d4b] transition-colors"
              >
                Chọn file hợp đồng
              </button>
              <p className="mt-4 text-xs text-stone-400">
                PDF, DOCX, TXT, Markdown hoặc ảnh · Tối đa 50 MB, 150 trang
              </p>
            </>
          )}
        </main>
      ) : (
        <>
          <PipelineHeaderRail
            scenario={s}
            currentStepIndex={step}
            isBusy={busy}
            statusMessage={message}
            factsConfirmed={factsConfirmed}
            canAnalyze={
              factsConfirmed && !busy && Object.keys(answers).length === 0
            }
            hasLastCheck={Boolean(card?.last_check)}
            showVerify={showVerify}
            onSelectStep={(idx) => {
              setStep(idx);
              setReplayNonce((n) => n + 1);
            }}
            onToggleVerify={() => setShowVerify((v) => !v)}
            onAnalyze={() => {
              setShowVerify(false);
              void analyze();
            }}
          />
          <main className="max-w-[1520px] mx-auto p-4 lg:p-6 space-y-4">
            {!!s.warnings?.length && (
              <div
                role="status"
                className="border border-amber-200 bg-amber-50 text-amber-900 p-3 text-xs space-y-1 rounded"
              >
                {s.warnings.map((w) => (
                  <p key={w}>{w}</p>
                ))}
              </div>
            )}
            {card && step >= 1 && (!factsConfirmed || showVerify) && (
              <motion.section
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                className="border border-stone-200 rounded bg-white p-4"
              >
                <h3 className="font-semibold mb-2">
                  Xác minh thông tin hợp đồng
                </h3>
                <p className="text-xs text-stone-500 mb-4">
                  Xác nhận dữ kiện máy đã đọc. Thông tin bắt buộc cần được xác
                  minh trước khi phân tích.
                </p>
                <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {card.verification.fields
                    .filter(
                      (f: any) =>
                        showAllFields ||
                        f.required ||
                        f.status === "missing" ||
                        f.status === "conflict" ||
                        Boolean(answers[f.key]),
                    )
                    .map((f: any) => (
                    <label key={f.key} className="text-xs block">
                      <span className="font-medium">
                        {f.label}
                        {f.required ? " *" : ""}
                      </span>
                      <span className="text-stone-400 ml-2">
                        {
                          (
                            {
                              found: "Đã đọc",
                              missing: "Chưa có",
                              conflict: "Mâu thuẫn",
                              confirmed: "Đã xác nhận",
                              corrected: "Đã sửa",
                              unknown: "Không biết",
                            } as any
                          )[f.status]
                        }
                      </span>
                      {f.options?.length ? (
                        <select
                          disabled={busy}
                          value={answers[f.key]?.value ?? f.value ?? ""}
                          onChange={(e) =>
                            setAnswers((a) => ({
                              ...a,
                              [f.key]: { action: "set", value: e.target.value },
                            }))
                          }
                          className="w-full border border-stone-300 rounded p-2 mt-1"
                        >
                          <option value="">Chọn giá trị</option>
                          {f.options.map((o: any) => (
                            <option
                              key={typeof o === "object" ? o.value : o}
                              value={typeof o === "object" ? o.value : o}
                            >
                              {typeof o === "object"
                                ? o.label
                                : f.option_labels?.[o] || o}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          disabled={busy}
                          type={f.kind === "date" ? "date" : "text"}
                          value={
                            answers[f.key]?.action === "unknown"
                              ? ""
                              : (answers[f.key]?.value ?? f.value ?? "")
                          }
                          onChange={(e) =>
                            setAnswers((a) => ({
                              ...a,
                              [f.key]: { action: "set", value: e.target.value },
                            }))
                          }
                          className="w-full border border-stone-300 rounded p-2 mt-1"
                        />
                      )}
                      {f.quote && (
                        <p
                          className="mt-1 text-stone-500 line-clamp-2"
                          title={f.quote}
                        >
                          “{f.quote}”
                        </p>
                      )}
                      {!["party", "sign_date"].includes(f.key) && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            setAnswers((a) => ({
                              ...a,
                              [f.key]: { action: "unknown" },
                            }))
                          }
                          className="text-stone-500 underline mt-1"
                        >
                          {answers[f.key]?.action === "unknown"
                            ? "Đã chọn: Không biết"
                            : "Không biết"}
                        </button>
                      )}
                    </label>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-4 mt-4">
                  <button
                    disabled={busy}
                    onClick={() => void verify()}
                    className="px-4 py-2 bg-[#1E3A5F] text-white rounded text-xs font-semibold hover:bg-[#162C49] disabled:opacity-40 inline-flex items-center gap-2 cursor-pointer"
                  >
                    {busy && <Loader2 size={14} className="animate-spin" />}
                    {busy ? "Đang xử lý..." : "Xác nhận & Phân tích"}
                  </button>
                  {card.verification.fields.some(
                    (f: any) =>
                      !f.required &&
                      f.status !== "missing" &&
                      f.status !== "conflict",
                  ) && (
                    <button
                      type="button"
                      onClick={() => setShowAllFields((v) => !v)}
                      className="text-xs text-stone-500 hover:text-stone-900 underline cursor-pointer"
                    >
                      {showAllFields
                        ? "Ẩn trường bổ sung"
                        : `Hiện tất cả (${card.verification.fields.length} trường)`}
                    </button>
                  )}
                </div>
              </motion.section>
            )}
            <DualGraphCanvas
              scenario={s}
              currentStepIndex={step}
              stepElapsedMs={stepElapsedMs}
              choreography={choreography!}
              screeningParticles={particles}
              activeVersionIds={
                new Set(
                  s.legalNodes
                    .filter((n) => n.isSelectedVersion)
                    .map((n) => n.id),
                )
              }
              factsConfirmed={factsConfirmed}
              trace={trace!}
              onJumpToSubPhase={(ms) => setStepElapsedMs(ms)}
              onSelectConcept={(id) => {
                setSelected(
                  s.findings.find((f) => f.conceptId === id)?.id || null,
                );
              }}
              onSelectContractNode={(_id, uid) => {
                if (uid) chooseClause(uid);
              }}
              onSelectLegalNode={(id) =>
                setSelected(
                  s.findings.find((f) => f.relatedLegalNodeIds.includes(id))
                    ?.id || null,
                )
              }
              onConfirmFacts={() => void verify()}
              onSelectFinding={setSelected}
              onJumpToDetails={() =>
                details.current?.scrollIntoView({ behavior: "smooth" })
              }
              onOpenReportCanvas={openReportCanvas}
              isGeneratingReport={reportLoading}
              hasNarrativeReport={Boolean(reportMarkdown)}
            />
            <div ref={details} className="grid lg:grid-cols-12 gap-4">
              <div className="lg:col-span-3 h-[650px] overflow-y-auto thin-scroll bg-white border border-stone-200 rounded p-3">
                <StageOutcomePanel
                  scenario={s}
                  currentStepIndex={step}
                  choreography={choreography!}
                  particleTotal={particles.length}
                  activeVersionIds={
                    new Set(
                      s.legalNodes
                        .filter((n) => n.isSelectedVersion)
                        .map((n) => n.id),
                    )
                  }
                  factsConfirmed={factsConfirmed}
                  trace={trace!}
                  onConfirmFacts={() => void verify()}
                  onSelectFinding={setSelected}
                  onJumpToDetails={() =>
                    details.current?.scrollIntoView({ behavior: "smooth" })
                  }
                />
              </div>
              <div className="lg:col-span-4 h-[650px]">
                <DocumentPanel
                  scenario={s}
                  currentStepIndex={step}
                  choreography={choreography!}
                  trace={trace!}
                  onClauseClick={chooseClause}
                />
              </div>
              <div className="lg:col-span-5 h-[650px]">
                <InspectorPanel
                  scenario={s}
                  currentStepIndex={step}
                  factsConfirmed={true}
                  trace={trace!}
                  selectedFinding={selectedFinding}
                  activeComparison={comparison}
                  onConfirmFacts={() => {}}
                  onSelectFinding={setSelected}
                  onJumpToGraph={() =>
                    window.scrollTo({ top: 0, behavior: "smooth" })
                  }
                />
              </div>
            </div>
          </main>
        </>
      )}
      {error && (
        <div
          role="alert"
          className="max-w-[1460px] mx-auto my-4 p-4 bg-red-50 border border-red-200 text-red-800 flex items-start gap-3 text-sm"
        >
          <AlertCircle size={18} />
          <div>
            {error}
            {card && (
              <button
                disabled={busy}
                onClick={() => void open(card.contract_id)}
                className="ml-4 underline"
              >
                Tải lại trạng thái đã lưu
              </button>
            )}
          </div>
        </div>
      )}
      <LegalChatPopup
        contractCard={card}
        studioBusy={busy}
        onHighlightNodes={setActiveNodes}
      />
      {s && (
        <ReportCanvasDrawer
          open={reportCanvasOpen}
          scenario={s}
          markdown={reportMarkdown}
          isGenerating={reportLoading}
          llmUsed={reportLlmUsed}
          error={reportError}
          onClose={() => setReportCanvasOpen(false)}
          onRegenerate={() => {
            if (card?.contract_id) void generateReport(card.contract_id, true);
          }}
          onSelectFinding={(id) => setSelected(id)}
        />
      )}
    </div>
  );
}
