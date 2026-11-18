import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Brain,
  Calendar,
  ExternalLink,
  FileText,
  GitBranch,
  Loader2,
  Maximize2,
  MessageSquare,
  Mic,
  Minimize2,
  Plus,
  Scale,
  Send,
  X,
} from "lucide-react";
import { jsonBody, stream } from "../live/api";
import { LegalChatMessageView } from "./LegalChatMessageView";
import {
  DOC_STATUS_LABEL,
  fmtDay,
  formatToolVi,
  shortDocTitle,
  type ChatMode,
  type ChatResponsePayload,
  type ChatSource,
  type ChatTurn,
} from "./LegalChatTypes";

export interface PopupContractInfo {
  contract_id: string;
  filename: string;
  sign_date?: string | null;
  last_check?: { stale?: boolean } | null;
}

interface LegalChatPopupProps {
  contractCard: PopupContractInfo | null;
  studioBusy: boolean;
  onHighlightNodes?: (nodeIds: string[]) => void;
}

const GENERAL_SUGGESTIONS = [
  "Thời hiệu khởi kiện tranh chấp hợp đồng dân sự là bao lâu?",
  "Thời gian thử việc tối đa theo Bộ luật Lao động là bao nhiêu ngày?",
  "Mức lương thử việc tối thiểu phải trả bao nhiêu phần trăm lương chính thức?",
];

const CONTRACT_SUGGESTIONS = [
  "Lúc thử việc tôi được trả bao nhiêu tiền mỗi tháng, có đúng luật không?",
  "Phụ lục sửa những điều khoản nào và có hiệu lực từ ngày nào?",
  "Những điều khoản nào cần tôi kiểm tra thêm?",
];

const nextId = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

export function LegalChatPopup({
  contractCard,
  studioBusy,
  onHighlightNodes,
}: LegalChatPopupProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [unreadDone, setUnreadDone] = useState(false);
  const [mode, setMode] = useState<ChatMode>("general");
  const [modePinned, setModePinned] = useState(false);
  const [thinkEnabled, setThinkEnabled] = useState(false);
  const [asOf, setAsOf] = useState("");
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState(() => `studio_${nextId()}`);
  const [isSending, setIsSending] = useState(false);
  const [listening, setListening] = useState(false);
  const [speakingTurnId, setSpeakingTurnId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<ChatSource | null>(null);
  const [fullDocContent, setFullDocContent] = useState<string | null>(null);
  const [loadingDoc, setLoadingDoc] = useState(false);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const docCacheRef = useRef<Record<string, string>>({});
  const isOpenRef = useRef(isOpen);
  isOpenRef.current = isOpen;

  const canAskContract = Boolean(contractCard?.contract_id);
  const canAskGraph = Boolean(
    contractCard?.contract_id &&
      contractCard.last_check &&
      !contractCard.last_check.stale &&
      !studioBusy,
  );

  // Sync default mode when contract is uploaded or finishes graph analysis (unless user explicitly switched mode)
  useEffect(() => {
    if (!contractCard) {
      setMode("general");
      setModePinned(false);
      return;
    }
    if (!modePinned) {
      setMode(canAskGraph ? "graph" : "contract");
    } else if (mode === "graph" && !canAskGraph) {
      setMode("contract");
    }
  }, [contractCard?.contract_id, canAskGraph, modePinned]);

  useEffect(() => {
    if (isOpen) {
      setUnreadDone(false);
      window.setTimeout(() => textareaRef.current?.focus(), 60);
    }
  }, [isOpen]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns, isOpen]);

  useEffect(() => {
    return () => {
      window.speechSynthesis?.cancel();
    };
  }, []);

  const stopSpeak = () => {
    window.speechSynthesis?.cancel();
    setSpeakingTurnId(null);
  };

  const speakTurn = (turnId: string, text: string) => {
    if (!window.speechSynthesis || !text) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "vi-VN";
    utter.rate = 1.0;
    utter.onend = () => setSpeakingTurnId((cur) => (cur === turnId ? null : cur));
    utter.onerror = () => setSpeakingTurnId(null);
    setSpeakingTurnId(turnId);
    window.speechSynthesis.speak(utter);
  };

  const openCitation = async (src: ChatSource) => {
    setSelectedCitation(src);
    setFullDocContent(null);
    const fname = src.source || "";
    const isLink = /^https?:\/\//i.test(fname);
    const noFile =
      !fname ||
      isLink ||
      src.store === "versioned" ||
      fname.startsWith("Luật có phiên bản: ") ||
      fname.startsWith("Hợp đồng: ");
    if (noFile) return;
    if (docCacheRef.current[fname]) {
      setFullDocContent(docCacheRef.current[fname]);
      return;
    }
    setLoadingDoc(true);
    try {
      const resp = await fetch(`/api/doc_content/${encodeURIComponent(fname)}`);
      if (resp.ok) {
        const data = await resp.json();
        if (data.content) {
          docCacheRef.current[fname] = data.content;
          setFullDocContent(data.content);
        }
      }
    } catch {
      // keep excerpt fallback silently
    } finally {
      setLoadingDoc(false);
    }
  };

  const handleVoiceInput = () => {
    const SpeechRec =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      window.alert("Trình duyệt hiện tại chưa hỗ trợ Web Speech API nhận diện giọng nói.");
      return;
    }
    try {
      const rec = new SpeechRec();
      rec.lang = "vi-VN";
      rec.interimResults = false;
      setListening(true);
      rec.onresult = (event: any) => {
        const spoken = event.results?.[0]?.[0]?.transcript;
        if (spoken) {
          setInput((prev) => (prev ? `${prev} ${spoken}` : spoken));
          textareaRef.current?.focus();
        }
      };
      rec.onend = () => setListening(false);
      rec.onerror = () => setListening(false);
      rec.start();
    } catch {
      setListening(false);
    }
  };

  const handleNewChat = () => {
    if (isSending) return;
    stopSpeak();
    setTurns([]);
    setSelectedCitation(null);
    setSessionId(`studio_${nextId()}`);
    setThinkEnabled(false);
  };

  const sendQuery = async (rawQuery: string, overrideOpts?: Partial<Pick<ChatTurn, "mode" | "think" | "asOf">>) => {
    const query = rawQuery.trim();
    if (!query || isSending) return;

    const activeMode = overrideOpts?.mode ?? mode;
    const activeThink = activeMode === "graph" ? false : (overrideOpts?.think ?? thinkEnabled);
    const activeAsOf = activeMode === "general" ? (overrideOpts?.asOf ?? asOf) : "";
    const activeContract =
      activeMode !== "general" && contractCard ? contractCard : null;

    if (activeMode === "graph" && (!activeContract || !canAskGraph)) return;
    if (activeMode === "contract" && !activeContract) return;

    const turnId = `turn_${nextId()}`;
    const stamp = new Date().toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
    });

    const historyPayload = turns
      .filter((t) => t.status === "done" && (t.data?.answer || t.streamedText))
      .slice(-3)
      .map((t) => ({
        query: t.query,
        answer: (t.data?.answer || t.streamedText || "").slice(0, 250),
      }));

    const newTurn: ChatTurn = {
      id: turnId,
      query,
      mode: activeMode,
      think: activeThink,
      asOf: activeAsOf || undefined,
      contractLabel: activeContract?.filename,
      status: "streaming",
      progressText:
        activeMode === "graph"
          ? "Đang tìm đường trên đồ thị hợp đồng..."
          : activeThink
          ? "Think · Đang phân tích & đối chiếu đa nguồn..."
          : "Đang tra cứu căn cứ pháp lý...",
      graphSteps: [],
      timestamp: stamp,
    };

    setTurns((prev) => [...prev, newTurn]);
    setIsSending(true);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const patchTurn = (fn: (cur: ChatTurn) => ChatTurn) =>
      setTurns((prev) => prev.map((t) => (t.id === turnId ? fn(t) : t)));

    try {
      if (activeMode === "graph" && activeContract) {
        await stream(
          `/api/contracts/${encodeURIComponent(activeContract.contract_id)}/ask/stream`,
          jsonBody({ question: query, history: historyPayload }),
          (e) => {
            if (e.type === "step") {
              onHighlightNodes?.(e.nodes || []);
              patchTurn((cur) => ({
                ...cur,
                progressText: formatToolVi(e.tool, e.args || {}),
                graphSteps: [...(cur.graphSteps || []), e],
              }));
            } else if (e.type === "done") {
              onHighlightNodes?.((e.path || []).map((n: any) => n.node_id));
              const payload: ChatResponsePayload = {
                ...e,
                answer: [e.answer, ...(e.warnings || [])].filter(Boolean).join("\n\n"),
                citations: (e.law || []).map((law: any, idx: number) => ({
                  n: idx + 1,
                  chunk_id: law.pid || `law-${idx}`,
                  source: law.citation || law.pid,
                  section: law.citation,
                  text: law.text || law.note || "Chưa có lời văn đã xác minh",
                  store: law.valid_from ? "versioned" : undefined,
                  valid_from: law.valid_from,
                  valid_to: law.valid_to,
                  source_url: law.source_url,
                })),
              };
              patchTurn((cur) => ({ ...cur, status: "done", data: payload }));
            }
          },
        );
      } else {
        const body: Record<string, any> = {
          query,
          session_id: sessionId,
          history: historyPayload,
          stream: true,
          think: activeThink,
        };
        if (activeContract) body.contract_id = activeContract.contract_id;
        if (activeAsOf) body.as_of = activeAsOf;

        await stream("/api/chat", jsonBody(body), (evt) => {
          if (evt.type === "progress") {
            patchTurn((cur) => ({
              ...cur,
              progressText: evt.message || "Think · Đang kiểm chứng…",
            }));
          } else if (evt.type === "sources") {
            const count = (evt.sources || []).length;
            patchTurn((cur) => ({
              ...cur,
              progressText: `Đã tìm thấy ${count} trích dẫn luật · Đang sinh câu trả lời...`,
              data: { ...(cur.data || {}), sources: evt.sources || [] },
            }));
          } else if (evt.type === "token") {
            patchTurn((cur) => ({
              ...cur,
              streamedText: (cur.streamedText || "") + (evt.delta || ""),
            }));
          } else if (evt.type === "done") {
            patchTurn((cur) => ({
              ...cur,
              status: "done",
              data: {
                ...evt,
                sources: evt.sources?.length ? evt.sources : cur.data?.sources,
              },
            }));
          }
        });
      }
      if (!isOpenRef.current) setUnreadDone(true);
    } catch (e: any) {
      patchTurn((cur) => ({
        ...cur,
        status: "error",
        error: e?.message || "Lỗi kết nối máy chủ.",
      }));
    } finally {
      setIsSending(false);
    }
  };

  const suggestions = mode === "general" ? GENERAL_SUGGESTIONS : CONTRACT_SUGGESTIONS;

  return (
    <>
      {/* Corner Rectangular Popup */}
      <AnimatePresence>
        {isOpen && (
          <motion.section
            aria-label="Hỏi đáp pháp lý"
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.96 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className={`fixed bottom-20 right-5 z-40 bg-white border border-stone-200 rounded-xl shadow-2xl flex flex-col overflow-hidden transition-[width,height] duration-200 ${
              isExpanded
                ? "w-[min(680px,calc(100vw-2rem))] h-[min(740px,calc(100vh-6rem))]"
                : "w-[min(460px,calc(100vw-2rem))] h-[min(620px,calc(100vh-6.5rem))]"
            }`}
          >
            {/* Header */}
            <div className="px-3.5 py-2.5 bg-[#1E3A5F] text-white flex items-center justify-between gap-2 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <Scale className="w-4 h-4 shrink-0 text-slate-200" />
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold leading-tight truncate">
                    Hỏi đáp pháp lý · Just-ice
                  </div>
                  <div className="text-[10.5px] text-slate-300 truncate">
                    {isSending
                      ? "Đang tra cứu & xử lý..."
                      : mode === "graph"
                      ? "Đồ thị 7-node hợp đồng"
                      : thinkEnabled
                      ? "Think Agent đang bật"
                      : "Tra cứu theo mốc & trích dẫn"}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={handleNewChat}
                  disabled={isSending}
                  title="Đoạn chat mới"
                  className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] bg-white/10 hover:bg-white/20 disabled:opacity-40 transition-colors cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Mới</span>
                </button>
                <button
                  type="button"
                  onClick={() => setIsExpanded((v) => !v)}
                  title={isExpanded ? "Thu gọn kích thước" : "Mở rộng khung chat"}
                  className="p-1.5 rounded hover:bg-white/15 transition-colors cursor-pointer"
                >
                  {isExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                </button>
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  title="Thu nhỏ xuống góc"
                  className="p-1.5 rounded hover:bg-white/15 transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Scope + Legal Date Bar */}
            <div className="px-3 py-2 border-b border-stone-200 bg-[#FAF9F6] space-y-1.5 shrink-0">
              {canAskContract && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      setMode("general");
                      setModePinned(true);
                    }}
                    className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors cursor-pointer ${
                      mode === "general"
                        ? "bg-[#1E3A5F] text-white border-[#1E3A5F]"
                        : "bg-white text-stone-600 border-stone-200 hover:bg-stone-100"
                    }`}
                  >
                    Luật chung
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMode("contract");
                      setModePinned(true);
                    }}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors cursor-pointer ${
                      mode === "contract"
                        ? "bg-[#1E3A5F] text-white border-[#1E3A5F]"
                        : "bg-white text-stone-600 border-stone-200 hover:bg-stone-100"
                    }`}
                  >
                    <FileText className="w-3 h-3" />
                    <span>Hợp đồng này</span>
                  </button>
                  <button
                    type="button"
                    disabled={!canAskGraph}
                    title={
                      canAskGraph
                        ? "Hỏi Agent trực tiếp trên đồ thị 7-node"
                        : "Cần phân tích concept xong mới hỏi trên đồ thị 7-node"
                    }
                    onClick={() => {
                      setMode("graph");
                      setModePinned(true);
                    }}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors ${
                      mode === "graph"
                        ? "bg-[#1E3A5F] text-white border-[#1E3A5F] cursor-pointer"
                        : canAskGraph
                        ? "bg-white text-stone-600 border-stone-200 hover:bg-stone-100 cursor-pointer"
                        : "bg-stone-100 text-stone-400 border-stone-200 cursor-not-allowed"
                    }`}
                  >
                    <GitBranch className="w-3 h-3" />
                    <span>Đồ thị 7-node</span>
                  </button>
                </div>
              )}

              {mode === "general" ? (
                <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-stone-600">
                  <Calendar className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                  <label htmlFor="popup-as-of" className="font-medium text-stone-700">
                    Mốc pháp lý:
                  </label>
                  <input
                    id="popup-as-of"
                    type="date"
                    value={asOf}
                    onChange={(e) => setAsOf(e.target.value)}
                    className="border border-stone-300 rounded px-1.5 py-0.5 text-[11px] text-stone-800 bg-white"
                  />
                  {asOf && (
                    <button
                      type="button"
                      onClick={() => setAsOf("")}
                      aria-label="Xóa mốc ngày"
                      className="text-stone-400 hover:text-stone-800 px-1 cursor-pointer"
                    >
                      ✕
                    </button>
                  )}
                  <span className="text-[10px] text-stone-400 truncate">
                    {asOf ? fmtDay(asOf) : "trống: tự nhận trong câu hỏi / hiện hành"}
                  </span>
                </div>
              ) : (
                contractCard && (
                  <div className="flex items-center justify-between gap-2 text-[11px] text-stone-600">
                    <span className="truncate font-medium text-stone-800">
                      📎 {contractCard.filename}
                    </span>
                    {contractCard.sign_date && (
                      <span className="text-[10.5px] font-mono text-stone-500 shrink-0">
                        Ký {fmtDay(contractCard.sign_date)}
                      </span>
                    )}
                  </div>
                )
              )}
            </div>

            {/* Message Thread / Citation Detail */}
            <div className="relative flex-1 overflow-hidden flex flex-col">
              <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto thin-scroll p-3.5 space-y-4 bg-white"
              >
                {turns.length === 0 ? (
                  <div className="space-y-3 pt-2">
                    <div className="rounded-xl bg-[#FAF9F6] border border-stone-200 p-3 text-[12px] text-stone-700 leading-relaxed">
                      <div className="font-serif text-[13.5px] font-semibold text-stone-900 mb-1">
                        Hỏi đáp pháp lý &amp; đối chiếu căn cứ
                      </div>
                      Bật nút <strong className="text-[#3569ce]">Think</strong> để dùng Agent kiểm chứng đa bước, chọn <strong>Mốc pháp lý</strong> theo ngày hiệu lực hoặc hỏi trực tiếp trên hợp đồng đang mở.
                    </div>
                    <div className="space-y-1.5">
                      <div className="text-[10.5px] font-medium text-stone-500">
                        Gợi ý câu hỏi:
                      </div>
                      {suggestions.map((q) => (
                        <button
                          key={q}
                          type="button"
                          disabled={isSending}
                          onClick={() => void sendQuery(q)}
                          className="w-full text-left text-[11.5px] text-[#1E3A5F] bg-[#FAF9F6] hover:bg-[#EDF3F9] border border-stone-200 rounded-lg px-3 py-2 transition-colors cursor-pointer"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  turns.map((turn) => (
                    <LegalChatMessageView
                      key={turn.id}
                      turn={turn}
                      isSpeaking={speakingTurnId === turn.id}
                      onSpeak={speakTurn}
                      onStopSpeak={stopSpeak}
                      onReask={(t) =>
                        void sendQuery(t.query, {
                          mode: t.mode,
                          think: t.think,
                          asOf: t.asOf,
                        })
                      }
                      onFollowUp={(q) => void sendQuery(q)}
                      onOpenCitation={(src) => void openCitation(src)}
                    />
                  ))
                )}
              </div>

              {/* Citation Source Sheet Overlay */}
              {selectedCitation && (
                <div className="absolute inset-0 z-20 bg-white flex flex-col border-t border-stone-200">
                  <div className="px-3.5 py-2.5 bg-[#FAF9F6] border-b border-stone-200 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[12px] font-semibold text-stone-900 truncate">
                        {selectedCitation.n ? `[${selectedCitation.n}] ` : ""}
                        {shortDocTitle(selectedCitation.source || selectedCitation.title)}
                      </div>
                      <div className="text-[10.5px] text-stone-500 truncate">
                        {selectedCitation.section || "Toàn văn"}
                        {selectedCitation.score != null
                          ? ` · Độ khớp p = ${selectedCitation.score}`
                          : ""}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedCitation(null)}
                      className="p-1 rounded hover:bg-stone-200 text-stone-500 cursor-pointer shrink-0"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="px-3.5 py-2 border-b border-stone-100 flex flex-wrap items-center justify-between gap-2 text-[10.5px] bg-white">
                    <div className="flex flex-wrap items-center gap-2 text-stone-600">
                      {selectedCitation.valid_from && (
                        <span>
                          Hiệu lực {fmtDay(selectedCitation.valid_from)} →{" "}
                          {selectedCitation.valid_to ? fmtDay(selectedCitation.valid_to) : "nay"}
                        </span>
                      )}
                      {selectedCitation.document_status &&
                        DOC_STATUS_LABEL[selectedCitation.document_status] && (
                          <span
                            className="font-medium"
                            style={{
                              color: DOC_STATUS_LABEL[selectedCitation.document_status][2],
                            }}
                          >
                            {DOC_STATUS_LABEL[selectedCitation.document_status][0]}{" "}
                            {DOC_STATUS_LABEL[selectedCitation.document_status][1]}
                          </span>
                        )}
                    </div>
                    {selectedCitation.source &&
                      selectedCitation.store !== "versioned" &&
                      !selectedCitation.source.startsWith("Luật có phiên bản: ") &&
                      !selectedCitation.source.startsWith("Hợp đồng: ") && (
                        <a
                          href={
                            /^https?:\/\//i.test(selectedCitation.source)
                              ? selectedCitation.source
                              : `/doc/${encodeURIComponent(selectedCitation.source)}`
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[#1E3A5F] font-medium hover:underline"
                        >
                          <span>
                            {/^https?:\/\//i.test(selectedCitation.source)
                              ? "Mở link"
                              : "Mở toàn văn"}
                          </span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                  </div>

                  <div className="flex-1 overflow-y-auto thin-scroll p-3.5 text-[12px] leading-relaxed text-stone-700 whitespace-pre-wrap">
                    {selectedCitation.quote && (
                      <div className="mb-3 p-2.5 rounded-lg bg-[#FDFBF5] border border-[#E7D3AD] text-stone-800">
                        {selectedCitation.quote}
                      </div>
                    )}
                    {loadingDoc ? (
                      <div className="flex items-center gap-1.5 text-stone-400">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Đang tải toàn văn...</span>
                      </div>
                    ) : (
                      fullDocContent ||
                      selectedCitation.text ||
                      selectedCitation.note ||
                      "Không có nội dung trích dẫn."
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Composer */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void sendQuery(input);
              }}
              className="p-2.5 border-t border-stone-200 bg-[#FAF9F6] shrink-0"
            >
              <div className="bg-white border border-stone-300 focus-within:border-[#1E3A5F] rounded-2xl px-2.5 py-1.5 flex items-end gap-1.5 shadow-2xs">
                <textarea
                  ref={textareaRef}
                  rows={1}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 100)}px`;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void sendQuery(input);
                    }
                  }}
                  placeholder={
                    mode === "graph"
                      ? "Hỏi Agent trên đồ thị hợp đồng..."
                      : "Đặt câu hỏi pháp lý..."
                  }
                  disabled={isSending}
                  className="flex-1 min-w-0 max-h-[100px] resize-none border-0 bg-transparent text-[12.5px] text-stone-900 placeholder-stone-400 py-1 px-1 focus:outline-none leading-snug"
                />

                {/* Think Toggle Button (from old UI) */}
                <button
                  type="button"
                  aria-pressed={mode !== "graph" && thinkEnabled}
                  disabled={mode === "graph" || isSending}
                  onClick={() => setThinkEnabled((v) => !v)}
                  title={
                    mode === "graph"
                      ? "Đồ thị 7-node đã tự chạy Agent"
                      : thinkEnabled
                      ? "Think đang bật — dùng Agent đa bước"
                      : "Bật Think để dùng Agent kiểm chứng"
                  }
                  className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full text-[11.5px] font-medium transition-colors shrink-0 ${
                    mode === "graph"
                      ? "text-stone-400 bg-stone-100 cursor-not-allowed"
                      : thinkEnabled
                      ? "text-[#3569ce] bg-[#eaf0fb] hover:bg-[#dfe8fa] cursor-pointer"
                      : "text-stone-600 hover:bg-stone-100 cursor-pointer"
                  }`}
                >
                  <Brain className="w-3.5 h-3.5" />
                  <span>Think</span>
                </button>

                {/* Voice Input Mic */}
                <button
                  type="button"
                  onClick={handleVoiceInput}
                  disabled={isSending}
                  title="Nhập bằng giọng nói (Tiếng Việt)"
                  className={`p-1.5 rounded-full transition-colors shrink-0 cursor-pointer ${
                    listening
                      ? "bg-red-50 text-red-600 animate-pulse"
                      : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                  }`}
                >
                  <Mic className="w-4 h-4" />
                </button>

                {/* Send */}
                <button
                  type="submit"
                  disabled={!input.trim() || isSending}
                  aria-label="Gửi câu hỏi"
                  className="w-8 h-8 rounded-full bg-[#1E3A5F] hover:bg-[#162C49] text-white flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0 cursor-pointer"
                >
                  {isSending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </form>
          </motion.section>
        )}
      </AnimatePresence>

      {/* Corner Floating Launcher Icon Button */}
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        aria-label={isOpen ? "Đóng cửa sổ hỏi đáp pháp lý" : "Mở hỏi đáp pháp lý"}
        className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-[#1E3A5F] hover:bg-[#162C49] text-white px-4 py-3 shadow-lg border border-white/15 transition-all cursor-pointer"
      >
        {isOpen ? (
          <X className="w-5 h-5" />
        ) : (
          <MessageSquare className="w-5 h-5" />
        )}
        <span className="text-xs font-semibold">
          {isOpen ? "Thu gọn" : "Hỏi đáp pháp lý"}
        </span>
        {(isSending || unreadDone) && !isOpen && (
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              isSending ? "bg-amber-400 animate-ping" : "bg-emerald-400"
            }`}
          />
        )}
      </button>
    </>
  );
}
