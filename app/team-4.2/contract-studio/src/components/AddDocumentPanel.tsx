import { useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { jsonBody, request, stream } from "../live/api";
import { UserFactsForm } from "./UserFactsForm";

type Kind = "appendix" | "contract";
type Answers = Record<string, { action: string; value?: string }>;

const url = (id: string) => `/api/contracts/${encodeURIComponent(id)}`;

/** Xác minh các trường còn thiếu của một hợp đồng (bản nháp hoặc hợp đồng bổ sung). */
function Verify({ title, card, answers, disabled, onChange }: {
  title: string;
  card: any;
  answers: Answers;
  disabled: boolean;
  onChange: (a: Answers) => void;
}) {
  const fields = card.verification.fields.filter(
    (f: any) => f.required && !["confirmed", "corrected", "unknown"].includes(f.status),
  );
  if (!fields.length) return null;
  return (
    <div className="space-y-2">
      <h4 className="font-semibold text-xs">{title}</h4>
      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {fields.map((f: any) => (
          <label key={f.key} className="text-xs block">
            <span className="font-medium">{f.label} *</span>
            {f.options?.length ? (
              <select
                disabled={disabled}
                value={answers[f.key]?.value ?? f.value ?? ""}
                onChange={(e) => onChange({ ...answers, [f.key]: { action: "set", value: e.target.value } })}
                className="w-full border border-stone-300 rounded p-2 mt-1"
              >
                <option value="">Chọn giá trị</option>
                {f.options.map((o: any) => (
                  <option key={o.value ?? o} value={o.value ?? o}>
                    {o.label ?? f.option_labels?.[o] ?? o}
                  </option>
                ))}
              </select>
            ) : (
              <input
                disabled={disabled}
                type={f.kind === "date" ? "date" : "text"}
                value={answers[f.key]?.value ?? f.value ?? ""}
                onChange={(e) => onChange({ ...answers, [f.key]: { action: "set", value: e.target.value } })}
                className="w-full border border-stone-300 rounded p-2 mt-1"
              />
            )}
            {f.status === "conflict" && (
              <span className="text-amber-700">
                Văn bản ghi nhiều giá trị: {f.candidates.map((c: any) => c.value).join(" / ")}
              </span>
            )}
          </label>
        ))}
      </div>
    </div>
  );
}

/** Gửi câu trả lời xác minh; trường máy đọc được mà người dùng không sửa thì xác nhận. */
async function confirm(card: any, answers: Answers) {
  const payload: Answers = {};
  for (const f of card.verification.fields) {
    if (answers[f.key]) payload[f.key] = answers[f.key];
    else if (f.required && f.status === "found") payload[f.key] = { action: "confirm" };
  }
  if (!Object.keys(payload).length) return card;
  return request(`${url(card.contract_id)}/facts`, jsonBody({ answers: payload }));
}

export function AddDocumentPanel({ contractId, onDone, onClose }: {
  contractId: string;
  onDone: (versionId: string) => void;
  onClose: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [upload, setUpload] = useState<any>(null);
  const [kind, setKind] = useState<Kind | "">("");
  const [prepared, setPrepared] = useState<any>(null);
  const [answers, setAnswers] = useState<{ draft: Answers; other: Answers }>({ draft: {}, other: {} });
  const [day, setDay] = useState("");
  const [sameParty, setSameParty] = useState(false);
  const [continuous, setContinuous] = useState("");
  const [userFacts, setUserFacts] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await work();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  const choose = (file: File) =>
    run("Đang đọc văn bản", async () => {
      const form = new FormData();
      form.append("file", file);
      const got = await request(`${url(contractId)}/additions`, { method: "POST", body: form });
      setUpload(got);
      setKind(got.suggested_kind || "");
      setPrepared(null);
    });

  const prepare = () =>
    run(kind === "appendix" ? "AI đang đọc phụ lục" : "Đang đọc hợp đồng bổ sung", async () => {
      await stream(
        `${url(contractId)}/additions/${upload.addition_id}/prepare/stream`,
        jsonBody({ kind }),
        (e) => {
          if (e.type === "done") {
            setPrepared(e);
            setDay(e.review_date || "");
            setAnswers({ draft: {}, other: {} });
          }
        },
      );
    });

  const analyze = () =>
    run("Đang kiểm luật và đối chiếu", async () => {
      const draft = await confirm(prepared.draft.card, answers.draft);
      const other = prepared.other ? await confirm(prepared.other.card, answers.other) : null;
      setPrepared({
        ...prepared,
        draft: { ...prepared.draft, card: draft },
        other: other ? { ...prepared.other, card: other } : null,
      });
      if (!draft.verification.complete || (other && !other.verification.complete))
        throw new Error("Còn thông tin bắt buộc chưa xác nhận.");
      await stream(
        `${url(draft.contract_id)}/additions/analyze/stream`,
        jsonBody({
          user_facts: userFacts,
          review_date: day,
          same_party: sameParty,
          continuous_employment: continuous === "" ? null : continuous === "yes",
        }),
        (e) => {
          if (e.type === "done") onDone(draft.contract_id);
        },
      );
    });

  const ready = prepared && day && (kind !== "contract" || sameParty);
  return (
    <section className="border border-[#1E3A5F]/30 rounded bg-white p-4 space-y-3 text-xs">
      <div className="flex justify-between">
        <h3 className="font-semibold text-sm">Bổ sung văn bản</h3>
        <button disabled={!!busy} onClick={onClose} className="underline text-stone-500">Đóng</button>
      </div>
      <p className="text-stone-500">
        Phụ lục của hợp đồng này, hoặc một hợp đồng khác cùng bên. Kết quả hiện tại được giữ nguyên để đối chiếu.
      </p>
      <input
        ref={input}
        type="file"
        disabled={!!busy}
        accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.tif,.tiff"
        onChange={(e) => {
          if (e.target.files?.[0]) void choose(e.target.files[0]);
        }}
      />
      {upload && (
        <div className="space-y-2">
          <p className="whitespace-pre-line line-clamp-4 border-l-2 border-stone-200 pl-2 text-stone-600">
            {upload.excerpt}
          </p>
          <label className="flex items-center gap-2">
            <span className="font-medium">Loại văn bản</span>
            <select
              disabled={!!busy || !!prepared}
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind | "")}
              className="border border-stone-300 rounded p-2"
            >
              <option value="">Chọn loại</option>
              <option value="appendix">Phụ lục của hợp đồng này</option>
              <option value="contract">Hợp đồng khác cùng bên</option>
            </select>
            {!upload.suggested_kind && <span className="text-amber-700">Máy chưa nhận ra loại, hãy chọn.</span>}
          </label>
          {!prepared && (
            <button
              disabled={!!busy || !kind}
              onClick={() => void prepare()}
              className="px-4 py-2 bg-[#1E3A5F] text-white rounded disabled:opacity-40"
            >
              Đọc văn bản bổ sung
            </button>
          )}
        </div>
      )}
      {prepared && (
        <div className="space-y-3">
          <Verify
            title={kind === "appendix" ? "Cần xác minh lại sau phụ lục" : "Xác minh hợp đồng đang xem"}
            card={prepared.draft.card}
            answers={answers.draft}
            disabled={!!busy}
            onChange={(a) => setAnswers({ ...answers, draft: a })}
          />
          {prepared.other && (
            <Verify
              title="Xác minh hợp đồng bổ sung"
              card={prepared.other.card}
              answers={answers.other}
              disabled={!!busy}
              onChange={(a) => setAnswers({ ...answers, other: a })}
            />
          )}
          <label className="flex items-center gap-2">
            <span className="font-medium">Ngày đánh giá *</span>
            <input
              type="date"
              disabled={!!busy}
              value={day}
              onChange={(e) => setDay(e.target.value)}
              className="border border-stone-300 rounded p-2"
            />
            <span className="text-stone-500">
              Áp cho cả bản trước và bản mới
              {kind === "appendix" ? " (mặc định: ngày phụ lục có hiệu lực)." : " (mặc định: hôm nay)."}
            </span>
          </label>
          {kind === "contract" && (
            <div className="space-y-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  disabled={!!busy}
                  checked={sameParty}
                  onChange={(e) => setSameParty(e.target.checked)}
                />
                Hai hợp đồng cùng người lao động / cùng bên
              </label>
              <label className="flex items-center gap-2">
                Làm việc liên tục giữa các hợp đồng
                <select
                  disabled={!!busy}
                  value={continuous}
                  onChange={(e) => setContinuous(e.target.value)}
                  className="border border-stone-300 rounded p-2"
                >
                  <option value="">Không rõ</option>
                  <option value="yes">Có</option>
                  <option value="no">Không</option>
                </select>
              </label>
            </div>
          )}
          <UserFactsForm
            fields={prepared.draft.card.user_form || []}
            values={userFacts}
            disabled={!!busy}
            onChange={(key, value) =>
              setUserFacts((prev) => {
                const next = { ...prev };
                if (value === undefined) delete next[key];
                else next[key] = value;
                return next;
              })
            }
          />
          <button
            disabled={!!busy || !ready}
            onClick={() => void analyze()}
            className="px-4 py-2 bg-[#1E3A5F] text-white rounded font-semibold disabled:opacity-40"
          >
            Xác nhận và đối chiếu
          </button>
        </div>
      )}
      {busy && (
        <p role="status" className="flex items-center gap-2 text-stone-600">
          <Loader2 size={14} className="animate-spin" />
          {busy}…
        </p>
      )}
      {error && <p role="alert" className="text-red-700">{error}</p>}
    </section>
  );
}
