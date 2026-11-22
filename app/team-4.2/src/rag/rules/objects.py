"""Đối tượng, đếm, phủ định (spec §5.6). Logic thuần, dùng chung cho Reference và Network.

Một rule xuyên đối tượng khai `over: {biến: {type, where, history?}}`, tùy chọn `group_by: {tên: "<biến>.refs.<ref>" |
"<biến>.<thuộc tính>"}` và `check` là `{count: {of, op, value | law}}`, `{exists: biến}` hoặc `{not_exists: biến}`.
Mỗi ứng viên (một đối tượng) có trị ba trị = AND(thành viên tại ngày soát, `where`); số đếm thật nằm trong
`[n_T, n_T + n_U]`. Kết quả: một `RuleResult` cho mỗi nhóm (`object` = nhãn nhóm)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from rag.rules.derived import derived_order, eval_derived
from rag.rules.model import Context, Rule
from rag.rules.semantics import (Fact, Facts, RuleInputs, RuleResult, Tri, decide_rule, eval_cond, is_unresolved)

COUNT_OPS = frozenset({"lt", "lte", "gt", "gte", "eq"})


@dataclass(frozen=True)
class WorkingObject:
    """Một đối tượng của hồ sơ (`rag.contracts.dossier` cấp). `valid_from=None`: chưa biết từ khi nào có hiệu lực."""
    id: str
    type: str
    attrs: Mapping[str, Any] = field(default_factory=dict)           # tên -> Fact | CONFLICT
    valid_from: date | None = date.min
    valid_to: date | None = None                                       # None: còn hiệu lực
    refs: Mapping[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ObjectChanges:
    added: tuple[WorkingObject, ...] = ()
    removed: tuple[str, ...] = ()                                      # id
    changed: tuple[WorkingObject, ...] = ()


def apply_object_changes(store: dict[str, WorkingObject], changes: ObjectChanges | Mapping) -> set[str]:
    """Ghi `changes` vào `store` (id -> đối tượng): `added` / `changed` ghi đè theo id, `removed` xóa. Trả id đã đổi."""
    if isinstance(changes, Mapping):
        changes = ObjectChanges(tuple(changes.get("added", ())), tuple(changes.get("removed", ())),
                                tuple(changes.get("changed", ())))
    if not isinstance(changes, ObjectChanges):
        raise TypeError(f"objects phải là ObjectChanges hoặc dict, gặp {type(changes).__name__}")
    out: set[str] = set()
    for oid in changes.removed:
        if store.pop(oid, None) is not None:
            out.add(oid)
    for o in (*changes.added, *changes.changed):
        if store.get(o.id) != o:
            store[o.id] = o
            out.add(o.id)
    return out


def membership(o: WorkingObject, day: date, *, history: bool = False) -> Tri:
    """Thành viên tại ngày soát: `valid_from ≤ day` và (`history` hoặc `valid_to` rỗng hoặc `day ≤ valid_to`)."""
    if o.valid_from is None:
        return "U" if history or o.valid_to is None or day <= o.valid_to else "F"
    if o.valid_from > day:
        return "F"
    return "T" if history or o.valid_to is None or day <= o.valid_to else "F"


def object_facts(o: WorkingObject, ctx: Context) -> Facts:
    """Bảng dữ kiện của một đối tượng: thuộc tính cộng dữ kiện suy ra khai cho kiểu của nó (§5.6, theo §5.3)."""
    table: Facts = {k: v for k, v in o.attrs.items() if v is not None}
    typed = {n: d for n, d in ctx.derived.items() if d.object_type == o.type}
    if typed:
        for name in derived_order(typed):
            table.pop(name, None)
        for name in derived_order(typed):
            result = eval_derived(typed[name], table, ctx)
            if result is not None:
                table[name] = result
    return table


def _key(rule: Rule, o: WorkingObject, table: Facts) -> tuple | None:
    out = []
    for _, path in rule.group_by:
        _, rest = path.split(".", 1)
        if rest.startswith("refs."):
            v = o.refs.get(rest[5:])
        else:
            f = table.get(rest)
            v = None if f is None or is_unresolved(f) else f.value
        if v is None:
            return None
        out.append(v)
    return tuple(out)


def candidate(rule: Rule, o: WorkingObject, table: Facts, day: date, ctx: Context) -> tuple[Tri, tuple | None]:
    """(trị ứng viên, khóa nhóm hoặc None nếu chưa biết) của `o` cho rule xuyên đối tượng `rule`."""
    _, _, where, history = rule.over
    m = membership(o, day, history=history)
    w = eval_cond(where, table, ctx) if m != "F" else "F"
    tri = "F" if "F" in (m, w) else ("U" if "U" in (m, w) else "T")
    return tri, _key(rule, o, table)


def aggregate(cands: Iterable[tuple[Tri, tuple | None]]) -> dict[tuple | None, tuple[int, int]]:
    """`{khóa nhóm: (n_T, n_U)}`. Khóa đã biết của mọi ứng viên (kể cả F) tạo nhóm; ứng viên T / U có khóa chưa biết
    cộng U vào mọi nhóm; chỉ có ứng viên khóa chưa biết thì một nhóm khóa None."""
    counts: dict[tuple, list[int]] = {}
    loose = 0
    for tri, key in cands:
        if key is None:
            loose += tri != "F"
            continue
        c = counts.setdefault(key, [0, 0])
        if tri == "T":
            c[0] += 1
        elif tri == "U":
            c[1] += 1
    if not counts:
        return {None: (0, loose)} if loose else {}
    return {k: (t, u + loose) for k, (t, u) in counts.items()}


def count_tri(op: str, lo: int, hi: int, k: float) -> Tri:
    """So khoảng số đếm `[lo, hi]` với ngưỡng `k`: T nếu mọi giá trị thỏa, F nếu không giá trị nào thỏa, còn lại U."""
    if op == "eq":
        return "T" if lo == hi == k else ("F" if k < lo or k > hi else "U")
    sat = {"lt": lambda v: v < k, "lte": lambda v: v <= k, "gt": lambda v: v > k, "gte": lambda v: v >= k}[op]
    a, b = sat(lo), sat(hi)                         # các phép so đơn điệu: chỉ cần hai đầu khoảng
    return "T" if a and b else ("F" if not a and not b else "U")


def object_check(rule: Rule, n_t: int, n_u: int, law: dict | None) -> Tri:
    check = rule.check
    if "exists" in check:
        return count_tri("gte", n_t, n_t + n_u, 1)
    if "not_exists" in check:
        return {"T": "F", "F": "T", "U": "U"}[count_tri("gte", n_t, n_t + n_u, 1)]
    spec = check["count"]
    if "law" in spec:
        ref = (law or {}).get(spec["law"])
        if ref is None or not isinstance(ref.get("value"), (int, float)):
            return "U"
        k = ref["value"]
    else:
        k = spec["value"]
    return count_tri(spec["op"], n_t, n_t + n_u, k)


def group_label(rule: Rule, key: tuple | None) -> str | None:
    if key is None or not rule.group_by:
        return None
    return ",".join(f"{name}={v}" for (name, _), v in zip(rule.group_by, key))


def object_results(concept_id: str, rule: Rule, facts: Facts, evidence: Sequence[dict], inputs: RuleInputs,
                   groups: Mapping[tuple | None, tuple[int, int]], ctx: Context) -> list[RuleResult]:
    """Kết quả theo nhóm của rule xuyên đối tượng (theo nhãn nhóm); không có ứng viên nào -> NOT_APPLICABLE `no_objects`."""
    if not groups:
        none = decide_rule(concept_id, rule, facts, True, evidence, dataclasses.replace(inputs, app="F"), ctx)
        return [dataclasses.replace(none, reasons=("no_objects",))]
    out = []
    for key, (n_t, n_u) in groups.items():
        st = object_check(rule, n_t, n_u, inputs.law)
        r = decide_rule(concept_id, rule, facts, True, evidence, dataclasses.replace(inputs, check_st=st), ctx)
        reasons = r.reasons if r.status == "NOT_APPLICABLE" else (*r.reasons, f"count:{n_t}..{n_t + n_u}")
        out.append(dataclasses.replace(r, object=group_label(rule, key), reasons=reasons))
    return sorted(out, key=lambda r: r.object or "")


def rule_object_results(concept_id: str, rule: Rule, facts: Facts, evidence: Sequence[dict], inputs: RuleInputs,
                        objects: Iterable[WorkingObject], tables: Mapping[str, Facts], day: date,
                        ctx: Context) -> list[RuleResult]:
    """Cả bước: ứng viên của mọi đối tượng cùng kiểu -> nhóm -> kết quả. `tables[id]` = `object_facts` của đối tượng."""
    typ = rule.over[1]
    cands = [candidate(rule, o, tables[o.id], day, ctx) for o in objects if o.type == typ]
    return object_results(concept_id, rule, facts, evidence, inputs, aggregate(cands), ctx)
