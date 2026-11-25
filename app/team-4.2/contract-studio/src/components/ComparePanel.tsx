import { compareRows, type CompareRow } from "../live/versions";

const GROUP = { changed: "Đổi kết luận", added: "Mới xuất hiện", removed: "Không còn" } as const;

function Side({ result, empty }: { result?: any; empty: string }) {
  if (!result) return <p className="text-stone-400">{empty}</p>;
  const view = result.view || {};
  const values = Object.entries(result.facts_used || {}).map(([name, v]: [string, any]) =>
    `${name}: ${v?.value ?? v}${v?.unit ? ` ${v.unit}` : ""}`,
  );
  return (
    <div className="space-y-1">
      <p className="font-semibold">{view.verdict || result.finding}</p>
      {values.length > 0 && <p className="text-stone-500">{values.join(" · ")}</p>}
      {(view.contract || []).slice(0, 2).map((c: any, i: number) => (
        <p key={i} className="text-stone-500 line-clamp-2" title={c.quote || ""}>
          {c.label}: “{c.quote}”
        </p>
      ))}
    </div>
  );
}

function Section({ title, rows, unchanged, note }: {
  title: string;
  rows: CompareRow[];
  unchanged: number;
  note?: string;
}) {
  return (
    <div className="space-y-2">
      <h4 className="font-semibold text-sm">{title}</h4>
      {note && <p className="text-xs text-stone-500">{note}</p>}
      {rows.length === 0 && <p className="text-xs text-stone-500">Không có mục nào thay đổi.</p>}
      {rows.length > 0 && (
        <table className="w-full text-xs border border-stone-200">
          <thead className="bg-stone-50 text-left">
            <tr>
              <th className="p-2 w-1/4">Mục kiểm</th>
              <th className="p-2">Bản trước</th>
              <th className="p-2">Bản này</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.scope}-${r.key}`} className="border-t border-stone-200 align-top">
                <td className="p-2">
                  <p className="font-medium">{(r.after || r.before)?.view?.title || r.key}</p>
                  <p className="text-stone-400">{GROUP[r.group]}</p>
                </td>
                <td className="p-2"><Side result={r.before} empty="Chưa có" /></td>
                <td className="p-2"><Side result={r.after} empty="Không còn" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-stone-400">{unchanged} mục không đổi.</p>
    </div>
  );
}

export function ComparePanel({ compare, previousVersion }: { compare: any; previousVersion: number }) {
  const rows = compareRows(compare);
  const cross = compare.cross;
  return (
    <section className="border border-stone-200 rounded bg-white p-4 space-y-4">
      <div>
        <h3 className="font-semibold">So với bản trước (v{previousVersion})</h3>
        <p className="text-xs text-stone-500">
          Cả hai bản được đánh giá tại ngày {compare.day}.
        </p>
        {compare.before_differs_from_saved && (
          <p className="text-xs text-amber-700">
            Cột “Bản trước” khác kết quả đã lưu của v{previousVersion} vì ngày đánh giá hoặc dữ kiện trả lời khác.
          </p>
        )}
        {compare.catalog_changed && (
          <p className="text-xs text-amber-700">Gói luật đã đổi phiên bản giữa hai lần phân tích.</p>
        )}
      </div>
      {compare.contract && (
        <Section
          title="Các mục của hợp đồng"
          rows={rows.filter((r) => r.scope === "contract")}
          unchanged={compare.contract.unchanged}
        />
      )}
      {cross && !cross.supported && <p className="text-xs text-stone-500">{cross.note}</p>}
      {cross?.supported && (
        <Section
          title="Quy tắc liên hợp đồng"
          rows={rows.filter((r) => r.scope === "cross")}
          unchanged={cross.compare.unchanged}
          note={`Tính lại ${cross.recomputed}/${cross.total} quy tắc khi thêm văn bản.`}
        />
      )}
    </section>
  );
}
