// Dữ kiện về người lao động / các bên mà hợp đồng không thể chứa. Danh sách do server dựng từ gói luật đang dùng
// (card.user_form): UI chỉ vẽ theo `kind`, không giữ danh sách cố định.
type Field = {
  key: string;
  label: string;
  kind: "bool" | "number" | "choice" | "text";
  question?: string | null;
  options?: { value: unknown; label: string }[];
};

type Props = {
  fields: Field[];
  values: Record<string, unknown>;
  disabled?: boolean;
  onChange: (key: string, value: unknown) => void; // undefined = bỏ trống
};

const box = "w-full border border-stone-300 rounded p-2 mt-1";

export function UserFactsForm({ fields, values, disabled, onChange }: Props) {
  if (!fields.length) return null;
  const raw = (key: string) => (values[key] === undefined ? "" : String(values[key]));
  return (
    <div className="mt-4 border-t border-stone-100 pt-3">
      <h4 className="text-xs font-semibold">
        Thông tin thêm{" "}
        <span className="font-normal text-stone-500">
          (tùy chọn — giúp kết luận các mục còn thiếu dữ kiện)
        </span>
      </h4>
      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3 mt-2">
        {fields.map((f) => (
          <label key={f.key} className="text-xs block" title={f.question || ""}>
            <span className="font-medium">{f.label}</span>
            {f.kind === "bool" || f.kind === "choice" ? (
              <select
                disabled={disabled}
                value={raw(f.key)}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "") return onChange(f.key, undefined);
                  if (f.kind === "bool") return onChange(f.key, v === "true");
                  onChange(f.key, f.options?.find((o) => String(o.value) === v)?.value);
                }}
                className={box}
              >
                <option value="">— bỏ trống —</option>
                {f.kind === "bool" ? (
                  <>
                    <option value="true">Có</option>
                    <option value="false">Không</option>
                  </>
                ) : (
                  f.options?.map((o) => (
                    <option key={String(o.value)} value={String(o.value)}>
                      {o.label}
                    </option>
                  ))
                )}
              </select>
            ) : (
              <input
                disabled={disabled}
                type={f.kind === "number" ? "number" : "text"}
                value={raw(f.key)}
                onChange={(e) => {
                  const v = e.target.value.trim();
                  onChange(f.key, v === "" ? undefined : f.kind === "number" ? Number(v) : v);
                }}
                className={box}
              />
            )}
          </label>
        ))}
      </div>
    </div>
  );
}
