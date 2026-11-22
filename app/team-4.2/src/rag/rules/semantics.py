"""Logic thuần của rule engine ba trị (spec 2026-11-14-contract-concept-check §8, 2026-11-22-rete-rule-engine-design §5).
Không I/O. Đơn vị, dữ kiện cấp hợp đồng và bảng on_silence do gói cung cấp qua `Context`.

Giá trị chân lý: "T" đúng, "F" sai, "U" chưa biết (thiếu dữ kiện, dữ kiện mâu thuẫn, khác đơn vị không quy đổi được).
Thiếu dữ kiện không bao giờ thành vi phạm."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Sequence

from rag.rules.model import Context, Rule, leaves
from rag.rules.units import Units

Tri = Literal["T", "F", "U"]
Status = Literal["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"]


@dataclass(frozen=True)
class Fact:
    value: Any
    unit: str | None = None
    source: Literal["contract", "concept", "user", "derived"] = "contract"
    uid: str | None = None
    quote: str | None = None
    amended_from: tuple[dict, ...] = ()   # giá trị cũ bị phụ lục sửa đổi thay thế: ({value, unit, uid}, ...)
    later_amendments: tuple[dict, ...] = ()   # sửa đổi hiệu lực sau ngày soát: ({value, unit, uid, valid_from}, ...)
    derived_by: str | None = None             # dữ kiện suy ra: id định nghĩa thắng (spec §5.3)


class _Conflict:
    """Hai nguồn cho hai giá trị khác nhau: không chọn, coi như chưa biết."""

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "CONFLICT"


class _Unknown:
    """Dữ kiện suy ra mà chưa xác định được: ở lá xử lý như CONFLICT."""

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "UNKNOWN"


CONFLICT = _Conflict()
UNKNOWN = _Unknown()
Facts = dict[str, "Fact | _Conflict | _Unknown"]


def is_unresolved(f: object) -> bool:
    return f is CONFLICT or f is UNKNOWN


def _num(x: Any) -> float | None:
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def compare(left: Any, left_unit: str | None, op: str, right: Any, right_unit: str | None, units: Units) -> Tri:
    """So một giá trị dữ kiện với vế phải (giá trị luật hoặc hằng)."""
    if op == "in":
        return "T" if left in (right or []) else "F"
    if op == "eq":
        if _num(left) is not None and _num(right) is not None and right_unit is not None:
            v = units.convert(left, left_unit, right_unit)
            return "U" if v is None else ("T" if v == right else "F")
        return "T" if left == right else "F"
    if _num(left) is None or _num(right) is None:
        return "U"
    v = left if right_unit is None and left_unit is None else units.convert(left, left_unit, right_unit)
    if v is None:
        return "U"
    ok = {"lt": v < right, "lte": v <= right, "gt": v > right, "gte": v >= right}[op]
    return "T" if ok else "F"


def _leaf(cond: dict, facts: Facts, ctx: Context) -> Tri:
    op, f = cond.get("op"), facts.get(cond.get("fact"))
    if op == "absent":
        return "T" if f is None else ("U" if is_unresolved(f) else "F")
    if op == "present":
        return "F" if f is None else ("U" if is_unresolved(f) else "T")
    if f is None or is_unresolved(f):
        return "U"
    return compare(f.value, f.unit, op, cond.get("value"), cond.get("unit"), ctx.units)


def eval_cond(cond: dict | None, facts: Facts, ctx: Context) -> Tri:
    if cond is None:
        return "T"
    if "all" in cond:
        vals = [eval_cond(c, facts, ctx) for c in cond["all"]]
        return "F" if "F" in vals else ("U" if "U" in vals else "T")
    if "any" in cond:
        vals = [eval_cond(c, facts, ctx) for c in cond["any"]]
        return "T" if "T" in vals else ("U" if "U" in vals else "F")
    if "not" in cond:
        return {"T": "F", "F": "T", "U": "U"}[eval_cond(cond["not"], facts, ctx)]
    return _leaf(cond, facts, ctx)


def _materialize(law: dict, facts: Facts, day: date, reasons: list[str]) -> tuple[dict | None, Tri]:
    """Giá trị luật cụ thể {name: {value, unit}}; giá trị theo kỳ chọn kỳ hiệu lực ngày `day` và khóa `by`."""
    out: dict[str, dict] = {}
    for name, v in law.items():
        if "periods" not in v:
            out[name] = {"value": v.get("value"), "unit": v.get("unit")}
            continue
        live = [p for p in v["periods"] if date.fromisoformat(str(p["valid_from"])) <= day]
        if not live:
            reasons.append("law_period_not_covered")
            return None, "U"
        period = max(live, key=lambda p: str(p["valid_from"]))
        key = facts.get(v.get("by"))
        if key is None or is_unresolved(key):
            reasons.append(f"missing_fact:{v.get('by')}")
            return None, "U"
        if key.value not in period["values"]:
            reasons.append(f"law_value_not_found:{v.get('by')}={key.value}")
            return None, "U"
        out[name] = {"value": period["values"][key.value], "unit": v.get("unit")}
    return out, "T"


def resolve_law_with(rule: Rule, whens: Sequence[Tri], facts: Facts,
                     day: date) -> tuple[dict[str, dict] | None, Tri, tuple[str, ...]]:
    """(giá trị luật đã chọn, trạng thái chọn, lý do) khi đã biết trị của `rule.cases[i].when`. Có `cases`: lấy case đầu
    tiên `when = T`; gặp `U` trước thì `U`; không case nào khớp thì `F` (rule không áp dụng)."""
    reasons: list[str] = []
    if rule.cases:
        for case, st in zip(rule.cases, whens):
            if st == "U":
                return None, "U", ("case_needs_facts",)
            if st == "T":
                law, st2 = _materialize({**rule.law, **(case.get("law") or {})}, facts, day, reasons)
                return law, st2, tuple(reasons)
        return None, "F", ("no_case_matches",)
    law, st = _materialize(rule.law, facts, day, reasons)
    return law, st, tuple(reasons)


def resolve_law(rule: Rule, facts: Facts, day: date, ctx: Context) -> tuple[dict[str, dict] | None, Tri, tuple[str, ...]]:
    return resolve_law_with(rule, [eval_cond(c.get("when"), facts, ctx) for c in rule.cases], facts, day)


@dataclass(frozen=True)
class RuleResult:
    concept_id: str
    rule_id: str
    status: Status
    finding: str
    legality: str | None
    employee_impact: str | None
    law_values: dict
    facts_used: dict
    missing_facts: tuple[str, ...]
    evidence: tuple[dict, ...]
    reasons: tuple[str, ...]


def fact_names(cond: Any) -> list[str]:
    return [leaf["fact"] for leaf in leaves(cond) if leaf.get("fact")]


def referenced(rule: Rule) -> list[str]:
    names = fact_names(rule.applicability) + fact_names(rule.check)
    names += [n for c in rule.cases for n in fact_names(c.get("when"))]
    laws = [rule.law, *[c.get("law") or {} for c in rule.cases]]            # `by` có thể khai ở law của rule hoặc của một case
    names += [v["by"] for law in laws for v in law.values() if isinstance(v, dict) and v.get("by")]
    return list(dict.fromkeys(names))


def check_cond(cond: dict, facts: Facts, law: dict, ctx: Context) -> Tri:
    """Như eval_cond, nhưng lá có `law: <tên>` so với giá trị luật đã chọn."""
    if "all" in cond:
        vals = [check_cond(c, facts, law, ctx) for c in cond["all"]]
        return "F" if "F" in vals else ("U" if "U" in vals else "T")
    if "law" not in cond:
        return eval_cond(cond, facts, ctx)
    f, ref = facts.get(cond["fact"]), law.get(cond["law"])
    if f is None or is_unresolved(f) or ref is None:
        return "U"
    return compare(f.value, f.unit, cond["op"], ref["value"], ref.get("unit"), ctx.units)


def _contract_level_check(rule: Rule, facts: Facts, ctx: Context) -> bool:
    """Rule mà check chỉ dùng dữ kiện cấp hợp đồng của gói được xét khi có dữ kiện đó, kể cả khi LLM không gắn khái niệm
    cho điều khoản nào: dữ kiện đã được facts.py trích và kiểm trích dẫn."""
    names = fact_names(rule.check)
    return bool(names) and all(n in ctx.document_facts for n in names) and any(facts.get(n) is not None for n in names)


def _result(concept_id: str, rule: Rule, status: str, finding: str, law, facts: Facts, evidence, reasons,
            ctx: Context) -> RuleResult:
    names = referenced(rule)
    used = {n: {"value": f.value, "unit": f.unit, **({"amended_from": list(f.amended_from)} if f.amended_from else {}),
                **({"later_amendments": list(f.later_amendments)} if f.later_amendments else {}),
                **({"derived_by": f.derived_by} if f.derived_by else {})}
            for n in names if (f := facts.get(n)) is not None and not is_unresolved(f)}
    if ctx.derived:
        from rag.rules.derived import missing_inputs    # nạp muộn: derived.py import lại semantics
        missing = missing_inputs(names, facts, ctx)
        reasons = (*reasons, *[f"derived_unknown:{n}" for n in names
                               if n in ctx.derived and (facts.get(n) is None or facts.get(n) is UNKNOWN)])
    else:
        missing = tuple(n for n in names if facts.get(n) is None)
    reported = finding in ctx.reported
    return RuleResult(concept_id, rule.id, status, finding,
                      rule.outcome.get("legality") if reported else None,
                      rule.outcome.get("employee_impact") if reported else None,
                      law or {}, used, missing, tuple(evidence), tuple(reasons))


@dataclass(frozen=True)
class RuleInputs:
    """Những gì bảng quyết định cần từ dữ kiện: mạng tăng dần giữ chúng trong bộ nhớ, Reference tính lại mỗi lần."""
    app: Tri                                # eval_cond(applicability)
    law: dict | None
    law_st: Tri
    law_reasons: tuple[str, ...]            # kết quả resolve_law
    check_st: Tri | None                    # check_cond(check, ..., law); None khi rule không có check


def rule_inputs(rule: Rule, facts: Facts, day: date, ctx: Context) -> RuleInputs:
    law, law_st, law_reasons = resolve_law(rule, facts, day, ctx)
    check_st = None if rule.check is None else check_cond(rule.check, facts, law or {}, ctx)
    return RuleInputs(eval_cond(rule.applicability, facts, ctx), law, law_st, law_reasons, check_st)


def evaluate_rule(concept_id: str, rule: Rule, facts: Facts, present: bool, evidence, day: date,
                  ctx: Context) -> RuleResult:
    return decide_rule(concept_id, rule, facts, present, evidence, rule_inputs(rule, facts, day, ctx), ctx)


def decide_rule(concept_id: str, rule: Rule, facts: Facts, present: bool, evidence, inputs: RuleInputs,
                ctx: Context) -> RuleResult:
    """Bảng trạng thái của một rule (applicability -> giá trị luật -> present -> check -> on_silence) trên đầu vào đã tính."""
    def out(status, finding, law=None, reasons=()):
        return _result(concept_id, rule, status, finding, law, facts, evidence, reasons, ctx)

    app = inputs.app
    if app == "F":
        return out("NOT_APPLICABLE", "ok", reasons=("not_applicable",))
    law, law_st, reasons = inputs.law, inputs.law_st, inputs.law_reasons
    if law_st == "F":
        return out("NOT_APPLICABLE", "ok", reasons=reasons)
    present = present or _contract_level_check(rule, facts, ctx)

    if present:
        if rule.check is None:
            if rule.mode == "prohibited":     # điều cấm không có phép kiểm trên chữ: cần người xem
                return out("UNKNOWN", "needs_facts", law, ("needs_review",))
            return out("PASS", "ok", law, reasons)
        if rule.unstated_false and facts.get(rule.check["fact"]) is None:
            return out("PASS", "ok", law, (*reasons, "restriction_not_stated"))
        conflict = any(facts.get(n) is CONFLICT for n in fact_names(rule.check))
        if law_st == "U":
            return out("UNKNOWN", "conflict" if conflict else "needs_facts", law, reasons)
        st = inputs.check_st
        if st == "U":
            return out("UNKNOWN", "conflict" if conflict else "needs_facts", law, (*reasons, "check_unknown"))
        if st == "T":
            return out("PASS", "ok", law, reasons)
        if app == "U":
            return out("UNKNOWN", "needs_facts", law, (*reasons, "applicability_unknown"))
        return out("FAIL", "violation", law, reasons)

    silence = ctx.silences[rule.on_silence]
    if app == "U" and silence.unknown != silence.applicable:
        status, finding = silence.unknown
        return out(status, finding, law, ("applicability_unknown",))
    status, finding = silence.applicable
    return out(status, finding, law, reasons)
