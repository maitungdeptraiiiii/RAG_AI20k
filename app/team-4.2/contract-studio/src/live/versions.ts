export type CompareGroup = "changed" | "added" | "removed";

export interface CompareRow {
  group: CompareGroup;
  scope: "contract" | "cross";
  key: string;
  before?: any;
  after?: any;
}

const keyOf = (r: any) => `${r.concept_id}/${r.rule_id}@${r.object || ""}`;

function rowsOf(diff: any, scope: CompareRow["scope"]): CompareRow[] {
  if (!diff) return [];
  return [
    ...(diff.changed || []).map((x: any) => ({
      group: "changed" as const,
      scope,
      key: x.key,
      before: x.before,
      after: x.after,
    })),
    ...(diff.added || []).map((r: any) => ({
      group: "added" as const,
      scope,
      key: keyOf(r),
      after: r,
    })),
    ...(diff.removed || []).map((r: any) => ({
      group: "removed" as const,
      scope,
      key: keyOf(r),
      before: r,
    })),
  ];
}

/** Các dòng của bảng "So với bản trước": hợp đồng đang xem trước, quy tắc liên hợp đồng sau. */
export function compareRows(compare: any): CompareRow[] {
  return [
    ...rowsOf(compare?.contract, "contract"),
    ...rowsOf(compare?.cross?.compare, "cross"),
  ];
}
