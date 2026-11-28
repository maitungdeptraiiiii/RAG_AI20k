// Soát hồ sơ nhiều văn bản: tải nhiều file -> server nhận diện loại (hợp đồng / phụ lục) -> người dùng sửa loại, phụ lục
// thuộc hợp đồng nào, các bên -> server trích dữ kiện từng bộ, dựng đối tượng, chạy luật xuyên văn bản.
// Danh sách loại, vai trò, dữ kiện người dùng đều do server dựng từ gói luật: UI không giữ danh sách cố định.
import { useRef, useState } from "react";
import { FileStack, Loader2, AlertCircle, Plus, Trash2, ChevronRight, Sparkles } from "lucide-react";
import { AtelierHeader } from "./components/AtelierHeader";
import { request, stream, jsonBody } from "./live/api";
import { UserFactsForm } from "./components/UserFactsForm";
import { QuestionsPanel } from "./components/QuestionsPanel";

type Kind = { id: string; label: string; refs: string[] };
type Doc = {
  doc_id: string;
  filename: string;
  pages: number;
  kind: string | null;
  confidence?: number | null;
  evidence?: string | null;
  reason?: string | null;
  excerpt: string;
  refs: Record<string, string>;
};
type Party = { id: string; role: string; name: string; continuous_employment?: boolean };
type Meta = {
  packs: string[];
  roles: { id: string; label: string }[];
  user_fields: any[];
  supports_dossier: boolean;
};
type Draft = Meta & { dossier_id: string; documents: Doc[]; kinds: Kind[]; review_date: string };
type ExplainNode = { kind: string; label: string; status?: string | null; detail: Record<string, unknown>; children: ExplainNode[] };

const AMENDMENT = "amendment";
const STATUS: Record<string, { label: string; cls: string }> = {
  FAIL: { label: "Vi phạm", cls: "bg-red-50 text-red-800 border-red-200" },
  PASS: { label: "Phù hợp", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  UNKNOWN: { label: "Chưa đủ dữ kiện", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  NOT_APPLICABLE: { label: "Không áp dụng", cls: "bg-stone-50 text-stone-600 border-stone-200" },
};
const ORDER = ["FAIL", "UNKNOWN", "PASS", "NOT_APPLICABLE"];
const box = "border border-stone-300 rounded px-2 py-1 text-xs bg-white";

const show = (v: unknown) =>
  v === true ? "Có" : v === false ? "Không" : v === null || v === undefined ? "—" : String(v);

export default function DossierStudio({ onExit }: { onExit: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [reviewDate, setReviewDate] = useState("");
  const [userFacts, setUserFacts] = useState<Record<string, unknown>>({});
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [result, setResult] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);

  const log = (line: string) => setProgress((p) => [...p, line]);

  async function upload(files: FileList) {
    setBusy(true);
    setError("");
    setProgress([]);
    setResult(null);
    setDraft(null);
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    let done: Draft | null = null;
    try {
      await stream("/api/contract-studio/dossier/upload/stream", { method: "POST", body: form }, (e) => {
        if (e.type === "dossier_file")
          log(
            `${e.filename}: ${
              e.status === "read" ? "đang đọc" : e.status === "classify" ? "đang nhận diện loại" : "xong"
            }`,
          );
        if (e.type === "done") done = e as Draft;
      });
      if (done) {
        const d: Draft = done;
        setDraft(d);
        setDocs(d.documents);
        setMeta(d);
        setReviewDate(d.review_date);
        setParties(d.roles.map((r, i) => ({ id: `b${i + 1}`, role: r.id, name: "" })));
        setUserFacts({});
        setAnswers({});
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function refreshMeta(next: Doc[]) {
    const kinds = [...new Set(next.map((d) => d.kind).filter((k): k is string => !!k && k !== AMENDMENT))];
    try {
      const m: Meta = await request(`/api/contract-studio/dossier/meta?kinds=${encodeURIComponent(kinds.join(","))}`);
      setMeta(m);
      setParties((ps) => {
        const ids = new Set(m.roles.map((r) => r.id));
        return ps.every((p) => ids.has(p.role)) && ps.length ? ps : m.roles.map((r, i) => ({ id: `b${i + 1}`, role: r.id, name: "" }));
      });
    } catch (e: any) {
      setError(e.message);
    }
  }

  function setDoc(i: number, patch: Partial<Doc>) {
    const next = docs.map((d, j) => (j === i ? { ...d, ...patch } : d));
    setDocs(next);
    if (patch.kind !== undefined) void refreshMeta(next);
  }

  async function analyze(extra: Record<string, unknown> = answers) {
    if (!draft) return;
    setBusy(true);
    setError("");
    setProgress([]);
    let done: any = null;
    try {
      await stream(
        `/api/contract-studio/dossier/${draft.dossier_id}/analyze/stream`,
        jsonBody({
          review_date: reviewDate,
          parties,
          documents: docs.map((d) => ({ doc_id: d.doc_id, kind: d.kind, refs: d.refs })),
          user_facts: userFacts,
          answers: extra,
        }),
        (e) => {
          if (e.type === "stage" && e.stage === "facts")
            log(e.status === "start" ? "Đang trích dữ kiện từng bộ hợp đồng + phụ lục" : "Đã trích dữ kiện");
          if (e.type === "objects") log(`Đã dựng ${e.objects.length} đối tượng của hồ sơ`);
          if (e.type === "done") done = e;
        },
      );
      setResult(done);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function answer(qi: number, oi: number) {
    const q = result?.questions?.[qi];
    if (!q) return;
    const next = { ...answers, [q.fact]: q.options[oi].value };
    setAnswers(next);
    void analyze(next);
  }

  const kinds = draft?.kinds || [];
  const kindOf = (id: string | null) => kinds.find((k) => k.id === id);
  const mains = docs.filter((d) => d.kind && d.kind !== AMENDMENT);
  const fileOf = (id: string) => docs.find((d) => d.doc_id === id)?.filename || id;

  return (
    <div className="min-h-screen atelier-canvas text-[#141B29]">
      <AtelierHeader
        active="dossier"
        subtitle="Soát hồ sơ nhiều văn bản & phụ lục"
        onExitDossier={onExit}
        actions={
          <>
            <button
              disabled={busy}
              onClick={() => input.current?.click()}
              className="px-4 py-2 rounded-xl bg-[#16325C] hover:bg-[#1E437A] text-white inline-flex gap-2 items-center shadow-[0_8px_20px_-6px_rgba(22,50,92,0.45)] transition-all disabled:opacity-50 text-xs font-semibold cursor-pointer"
            >
              <FileStack size={15} />
              {draft ? "Tải hồ sơ khác" : "Tải các văn bản của hồ sơ"}
            </button>
            <input
              ref={input}
              hidden
              multiple
              type="file"
              accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.tif,.tiff"
              onChange={(e) => {
                if (e.target.files?.length) void upload(e.target.files);
              }}
            />
          </>
        }
      />

      <main className="max-w-6xl mx-auto p-6 space-y-5">
        {error && (
          <div className="flex gap-2 items-start border border-rose-200 bg-rose-50 text-rose-800 rounded-2xl p-4 text-sm">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}
        {busy && (
          <div className="atelier-card p-5 text-sm">
            <div className="flex items-center gap-2 text-[#16325C] font-medium">
              <Loader2 size={16} className="animate-spin text-[#2563EB]" /> Đang xử lý…
            </div>
            <ul className="mt-2 text-xs text-[#64748B] space-y-0.5">
              {progress.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}

        {!draft && !busy && (
          <section className="mt-10 atelier-card p-10 sm:p-14 text-center relative overflow-hidden">
            <div className="pointer-events-none absolute -top-24 -right-24 w-64 h-64 rounded-full bg-[#EEF4FF] blur-3xl opacity-80" />
            <div className="pointer-events-none absolute -bottom-24 -left-24 w-64 h-64 rounded-full bg-[#FDF6E7] blur-3xl opacity-90" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#FDF6E7] border border-[#F1DFB6] text-[#9A5B13] text-xs font-medium mb-5">
                <Sparkles size={13} />
                <span>Kiểm định chuỗi hợp đồng &amp; phụ lục</span>
              </div>
              <h2 className="font-serif text-3xl font-semibold text-[#16325C]">
                Soát cả hồ sơ: hợp đồng và các phụ lục
              </h2>
              <p className="text-[#475569] text-[15px] mt-3.5 max-w-xl mx-auto leading-relaxed">
                Chọn cùng lúc mọi văn bản của một hồ sơ (các hợp đồng đã ký nối tiếp, phụ lục sửa đổi). Hệ thống đoán loại
                từng văn bản; bạn xác nhận phụ lục thuộc hợp đồng nào và các bên, rồi soát các quy định xuyên văn bản.
              </p>
              <button
                onClick={() => input.current?.click()}
                className="mt-7 px-6 py-2.5 rounded-xl bg-[#16325C] hover:bg-[#1E437A] text-white text-sm font-semibold shadow-[0_8px_20px_-6px_rgba(22,50,92,0.45)] transition-all inline-flex items-center gap-2 cursor-pointer"
              >
                <FileStack size={16} />
                Chọn nhiều văn bản trong hồ sơ
              </button>
            </div>
          </section>
        )}

        {draft && (
          <>
            <section className="atelier-card p-5">
              <h2 className="font-semibold text-sm">1. Văn bản trong hồ sơ</h2>
              <p className="text-xs text-stone-500 mt-1">
                Loại do hệ thống đoán từ phần đầu văn bản — sửa nếu sai. Phụ lục cần chỉ rõ hợp đồng mà nó sửa đổi.
              </p>
              <table className="w-full mt-3 text-xs">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="py-1 pr-2">Văn bản</th>
                    <th className="py-1 pr-2">Loại</th>
                    <th className="py-1">Liên kết</th>
                  </tr>
                </thead>
                <tbody>
                  {docs.map((d, i) => (
                    <tr key={d.doc_id} className="border-t border-stone-100 align-top">
                      <td className="py-2 pr-2 w-2/5">
                        <button
                          className="font-medium text-left hover:underline inline-flex items-center gap-1"
                          onClick={() => setOpen(open === d.doc_id ? null : d.doc_id)}
                        >
                          <ChevronRight size={12} className={open === d.doc_id ? "rotate-90" : ""} />
                          {d.filename}
                        </button>
                        <div className="text-stone-400">
                          {d.pages} trang
                          {d.kind === null && d.reason ? ` · chưa nhận diện được (${d.reason})` : ""}
                        </div>
                        {open === d.doc_id && (
                          <pre className="mt-2 whitespace-pre-wrap bg-stone-50 border border-stone-100 rounded p-2 max-h-48 overflow-auto font-sans">
                            {d.excerpt}…
                          </pre>
                        )}
                      </td>
                      <td className="py-2 pr-2">
                        <select
                          className={box}
                          disabled={busy}
                          value={d.kind || ""}
                          onChange={(e) => setDoc(i, { kind: e.target.value || null, refs: {} })}
                        >
                          <option value="">— chọn loại —</option>
                          {kinds.map((k) => (
                            <option key={k.id} value={k.id}>
                              {k.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-2 space-y-1">
                        {d.kind === AMENDMENT && (
                          <label className="flex items-center gap-2">
                            <span className="text-stone-500">sửa đổi hợp đồng</span>
                            <select
                              className={box}
                              disabled={busy}
                              value={d.refs.contract || ""}
                              onChange={(e) => setDoc(i, { refs: { contract: e.target.value } })}
                            >
                              <option value="">— chọn —</option>
                              {mains.map((m) => (
                                <option key={m.doc_id} value={m.doc_id}>
                                  {m.filename}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                        {kindOf(d.kind)?.refs.map((ref) => (
                          <label key={ref} className="flex items-center gap-2">
                            <span className="text-stone-500">{ref}</span>
                            <select
                              className={box}
                              disabled={busy}
                              value={d.refs[ref] || ""}
                              onChange={(e) => setDoc(i, { refs: { ...d.refs, [ref]: e.target.value } })}
                            >
                              <option value="">— chọn bên —</option>
                              {parties.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name || p.id} ({meta?.roles.find((r) => r.id === p.role)?.label || p.role})
                                </option>
                              ))}
                            </select>
                          </label>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="atelier-card p-5">
              <h2 className="font-serif text-base font-semibold text-[#16325C]">2. Các bên và ngày soát</h2>
              <div className="mt-3 space-y-2">
                {parties.map((p, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 text-xs">
                    <input
                      className={`${box} w-20`}
                      value={p.id}
                      disabled={busy}
                      onChange={(e) => setParties(parties.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)))}
                      title="Mã bên (dùng để liên kết văn bản)"
                    />
                    <input
                      className={`${box} w-64`}
                      placeholder="Tên"
                      value={p.name}
                      disabled={busy}
                      onChange={(e) => setParties(parties.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                    />
                    <select
                      className={box}
                      value={p.role}
                      disabled={busy}
                      onChange={(e) => setParties(parties.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))}
                    >
                      {meta?.roles.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                    <label className="inline-flex items-center gap-1" title="Văn bản không ghi; chỉ dùng để tính khoảng nghỉ giữa hai hợp đồng">
                      <input
                        type="checkbox"
                        disabled={busy}
                        checked={!!p.continuous_employment}
                        onChange={(e) =>
                          setParties(parties.map((x, j) => (j === i ? { ...x, continuous_employment: e.target.checked || undefined } : x)))
                        }
                      />
                      làm việc liên tục suốt hồ sơ
                    </label>
                    <button
                      className="p-1 text-stone-400 hover:text-red-700"
                      disabled={busy}
                      onClick={() => setParties(parties.filter((_, j) => j !== i))}
                      title="Bỏ bên này"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
                <button
                  className="text-xs inline-flex items-center gap-1 text-[#1E3A5F] hover:underline"
                  disabled={busy}
                  onClick={() =>
                    setParties([...parties, { id: `b${parties.length + 1}`, role: meta?.roles[0]?.id || "", name: "" }])
                  }
                >
                  <Plus size={13} /> Thêm bên
                </button>
              </div>
              <label className="text-xs flex items-center gap-2 mt-4">
                <span className="font-medium">Ngày soát</span>
                <input type="date" className={box} value={reviewDate} disabled={busy} onChange={(e) => setReviewDate(e.target.value)} />
                <span className="text-stone-400">luật và văn bản có hiệu lực tại ngày này</span>
              </label>
              <UserFactsForm
                fields={meta?.user_fields || []}
                values={userFacts}
                disabled={busy}
                onChange={(k, v) =>
                  setUserFacts((u) => {
                    const n = { ...u };
                    if (v === undefined) delete n[k];
                    else n[k] = v;
                    return n;
                  })
                }
              />
              {meta && !meta.supports_dossier && (
                <p className="mt-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
                  Gói luật của loại văn bản này chưa khai quy định xét theo cả hồ sơ: hãy soát từng hợp đồng ở màn hình
                  chính.
                </p>
              )}
              <button
                disabled={busy || !mains.length}
                onClick={() => {
                  setAnswers({});
                  void analyze({});
                }}
                className="mt-4 px-4 py-2 rounded bg-[#1E3A5F] text-white text-sm disabled:opacity-50"
              >
                Soát hồ sơ
              </button>
            </section>
          </>
        )}

        {result && <Results result={result} fileOf={fileOf} disabled={busy} onAnswer={answer} />}
      </main>
    </div>
  );
}

function Results({
  result,
  fileOf,
  disabled,
  onAnswer,
}: {
  result: any;
  fileOf: (id: string) => string;
  disabled: boolean;
  onAnswer: (qi: number, oi: number) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const results = [...result.results].sort((a: any, b: any) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
  const objects = [...result.objects].sort((a: any, b: any) => (a.valid_from || "").localeCompare(b.valid_from || ""));
  return (
    <>
      <section className="atelier-card p-5">
        <h2 className="font-serif text-base font-semibold text-[#16325C]">3. Hồ sơ theo thời gian</h2>
        <p className="text-xs text-stone-500 mt-1">
          Mỗi văn bản là một đối tượng; thuộc tính lấy từ câu trích trong văn bản. Ô trống: văn bản không ghi hoặc chưa
          xác định được — luật coi là chưa biết, không phải vi phạm.
        </p>
        <table className="w-full mt-3 text-xs">
          <thead className="text-left text-stone-500">
            <tr>
              <th className="py-1 pr-2">Văn bản</th>
              <th className="py-1 pr-2">Kiểu</th>
              <th className="py-1 pr-2">Hiệu lực</th>
              <th className="py-1">Thuộc tính</th>
            </tr>
          </thead>
          <tbody>
            {objects.map((o: any) => (
              <tr key={o.id} className="border-t border-stone-100 align-top">
                <td className="py-2 pr-2 font-medium">
                  {o.filename}
                  {Object.entries(o.refs).map(([k, v]) => (
                    <div key={k} className="font-normal text-stone-400">
                      {k}: {k === "contract" ? fileOf(String(v)) : String(v)}
                    </div>
                  ))}
                </td>
                <td className="py-2 pr-2">{o.type}</td>
                <td className="py-2 pr-2 whitespace-nowrap">
                  {o.valid_from || "?"} → {o.valid_to || "…"}
                </td>
                <td className="py-2">
                  {Object.entries(o.attrs).map(([k, a]: [string, any]) => (
                    <div key={k} title={a.quote || ""}>
                      <span className="text-stone-500">{k}</span>: {a.unresolved ? "mâu thuẫn" : show(a.value)}
                      {a.unit ? ` ${a.unit}` : ""}
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <QuestionsPanel questions={result.questions || []} disabled={disabled} onAnswer={onAnswer} />

      <section className="atelier-card p-5">
        <h2 className="font-serif text-base font-semibold text-[#16325C]">4. Kết luận cấp hồ sơ (ngày soát {result.review_date})</h2>
        {!results.length && (
          <p className="text-xs text-stone-500 mt-2">
            Không có quy định nào xét theo cả hồ sơ cho các văn bản này.
          </p>
        )}
        <div className="mt-3 space-y-2">
          {results.map((r: any, i: number) => {
            const st = STATUS[r.status] || STATUS.UNKNOWN;
            return (
              <div key={i} className="border border-stone-200 rounded">
                <button className="w-full text-left p-3 flex items-start gap-3" onClick={() => setOpen(open === i ? null : i)}>
                  <span className={`text-[11px] px-2 py-0.5 rounded border whitespace-nowrap ${st.cls}`}>{st.label}</span>
                  <span className="text-xs flex-1">
                    <span className="font-medium">{r.concept_label}</span>
                    <span className="text-stone-400"> · {r.object_label}</span>
                    <div className="text-stone-600 mt-0.5">{r.verdict}</div>
                    {r.missing_facts.length > 0 && (
                      <div className="text-amber-700 mt-0.5">Thiếu: {r.missing_facts.join(", ")}</div>
                    )}
                  </span>
                  <ChevronRight size={14} className={`mt-1 text-stone-400 ${open === i ? "rotate-90" : ""}`} />
                </button>
                {open === i && (
                  <div className="px-3 pb-3 text-xs border-t border-stone-100 pt-2 space-y-2">
                    {r.reasons.length > 0 && (
                      <div>
                        <span className="text-stone-500">Lý do:</span> {r.reasons.join("; ")}
                      </div>
                    )}
                    {Object.keys(r.law_values).length > 0 && (
                      <div>
                        <span className="text-stone-500">Giá trị luật:</span>{" "}
                        {Object.entries(r.law_values)
                          .map(([k, v]: [string, any]) => `${k} = ${show(v?.value)}${v?.unit ? " " + v.unit : ""}`)
                          .join("; ")}
                      </div>
                    )}
                    <Tree node={r.explain} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}

function Tree({ node, depth = 0 }: { node: ExplainNode; depth?: number }) {
  const detail = Object.entries(node.detail || {}).filter(
    ([k, v]) => k !== "anchors" && v !== null && v !== undefined && !(Array.isArray(v) && !v.length),
  );
  return (
    <div style={{ marginLeft: depth * 14 }} className="leading-relaxed">
      <span className="text-stone-400">{node.kind}</span> {node.label}
      {node.status ? <span className="ml-1 text-stone-500">[{node.status}]</span> : null}
      {detail.length > 0 && (
        <span className="text-stone-400">
          {" "}
          — {detail.map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join("; ")}
        </span>
      )}
      {node.children?.map((c, i) => (
        <Tree key={i} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}
