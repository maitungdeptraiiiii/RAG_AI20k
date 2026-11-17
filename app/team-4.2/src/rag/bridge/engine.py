"""Rule engine ba trị trên danh mục khái niệm (spec 2026-11-14-contract-concept-check §8). Thuần Python, không I/O.

Giá trị chân lý: "T" đúng, "F" sai, "U" chưa biết (thiếu dữ kiện, dữ kiện mâu thuẫn, khác đơn vị không quy đổi được).
Thiếu dữ kiện không bao giờ thành vi phạm."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from rag.bridge.catalog import CONTRACT_FACTS, Rule, _leaves

Tri = Literal["T", "F", "U"]


@dataclass(frozen=True)
class Fact:
    value: Any
    unit: str | None = None
    source: Literal["contract", "concept", "user"] = "contract"
    uid: str | None = None
    quote: str | None = None
    amended_from: tuple[dict, ...] = ()   # giá trị cũ bị phụ lục sửa đổi thay thế: ({value, unit, uid}, ...)
    later_amendments: tuple[dict, ...] = ()   # sửa đổi hiệu lực sau ngày soát: ({value, unit, uid, valid_from}, ...)


class _Conflict:
    """Hai nguồn cho hai giá trị khác nhau: không chọn, coi như chưa biết."""

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "CONFLICT"


CONFLICT = _Conflict()
Facts = dict[str, "Fact | _Conflict"]

# quy đổi được phép (Global Constraints của kế hoạch): về đơn vị gốc rồi sang đích
_BASE = {"day": ("hour", 24), "week": ("hour", 168), "month": ("hour", 720), "hour": ("hour", 1),
         "minute": ("hour", 1 / 60)}


def convert(value: float, unit: str | None, to: str | None) -> float | None:
    if unit == to:
        return value
    if unit in _BASE and to in _BASE:
        a, b = _BASE[unit], _BASE[to]
        return value * a[1] / b[1]
    return None


def _num(x: Any) -> float | None:
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def compare(left: Any, left_unit: str | None, op: str, right: Any, right_unit: str | None) -> Tri:
    """So một giá trị dữ kiện với vế phải (giá trị luật hoặc hằng)."""
    if op == "in":
        return "T" if left in (right or []) else "F"
    if op == "eq":
        if _num(left) is not None and _num(right) is not None and right_unit is not None:
            v = convert(left, left_unit, right_unit)
            return "U" if v is None else ("T" if v == right else "F")
        return "T" if left == right else "F"
    if _num(left) is None or _num(right) is None:
        return "U"
    v = left if right_unit is None and left_unit is None else convert(left, left_unit, right_unit)
    if v is None:
        return "U"
    ok = {"lt": v < right, "lte": v <= right, "gt": v > right, "gte": v >= right}[op]
    return "T" if ok else "F"


def _leaf(cond: dict, facts: Facts) -> Tri:
    op, f = cond.get("op"), facts.get(cond.get("fact"))
    if op == "absent":
        return "T" if f is None else ("U" if f is CONFLICT else "F")
    if op == "present":
        return "F" if f is None else ("U" if f is CONFLICT else "T")
    if f is None or f is CONFLICT:
        return "U"
    return compare(f.value, f.unit, op, cond.get("value"), cond.get("unit"))


def eval_cond(cond: dict | None, facts: Facts) -> Tri:
    if cond is None:
        return "T"
    if "all" in cond:
        vals = [eval_cond(c, facts) for c in cond["all"]]
        return "F" if "F" in vals else ("U" if "U" in vals else "T")
    if "any" in cond:
        vals = [eval_cond(c, facts) for c in cond["any"]]
        return "T" if "T" in vals else ("U" if "U" in vals else "F")
    if "not" in cond:
        return {"T": "F", "F": "T", "U": "U"}[eval_cond(cond["not"], facts)]
    return _leaf(cond, facts)


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
        if key is None or key is CONFLICT:
            reasons.append(f"missing_fact:{v.get('by')}")
            return None, "U"
        if key.value not in period["values"]:
            reasons.append(f"law_value_not_found:{v.get('by')}={key.value}")
            return None, "U"
        out[name] = {"value": period["values"][key.value], "unit": v.get("unit")}
    return out, "T"


def resolve_law(rule: Rule, facts: Facts, day: date) -> tuple[dict[str, dict] | None, Tri, tuple[str, ...]]:
    """(giá trị luật đã chọn, trạng thái chọn, lý do). Có `cases`: lấy case đầu tiên `when = T`; gặp `U` trước thì `U`;
    không case nào khớp thì `F` (rule không áp dụng)."""
    reasons: list[str] = []
    if rule.cases:
        for case in rule.cases:
            st = eval_cond(case.get("when"), facts)
            if st == "U":
                return None, "U", ("case_needs_facts",)
            if st == "T":
                law, st2 = _materialize({**rule.law, **(case.get("law") or {})}, facts, day, reasons)
                return law, st2, tuple(reasons)
        return None, "F", ("no_case_matches",)
    law, st = _materialize(rule.law, facts, day, reasons)
    return law, st, tuple(reasons)


Status = Literal["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"]
Finding = Literal["ok", "violation", "missing_content", "hidden_right", "possible_right", "needs_facts", "conflict"]
_REPORTED = frozenset({"violation", "missing_content", "hidden_right", "possible_right"})


@dataclass(frozen=True)
class RuleResult:
    concept_id: str
    rule_id: str
    status: Status
    finding: Finding
    legality: str | None
    employee_impact: str | None
    law_values: dict
    facts_used: dict
    missing_facts: tuple[str, ...]
    evidence: tuple[dict, ...]
    reasons: tuple[str, ...]


def _fact_names(cond: Any) -> list[str]:
    return [leaf["fact"] for leaf in _leaves(cond) if leaf.get("fact")]


def _referenced(rule: Rule) -> list[str]:
    names = _fact_names(rule.applicability) + _fact_names(rule.check)
    names += [n for c in rule.cases for n in _fact_names(c.get("when"))]
    names += [v["by"] for v in rule.law.values() if isinstance(v, dict) and v.get("by")]
    return list(dict.fromkeys(names))


def _check(cond: dict, facts: Facts, law: dict) -> Tri:
    """Như eval_cond, nhưng lá có `law: <tên>` so với giá trị luật đã chọn."""
    if "all" in cond:
        vals = [_check(c, facts, law) for c in cond["all"]]
        return "F" if "F" in vals else ("U" if "U" in vals else "T")
    if "law" not in cond:
        return eval_cond(cond, facts)
    f, ref = facts.get(cond["fact"]), law.get(cond["law"])
    if f is None or f is CONFLICT or ref is None:
        return "U"
    return compare(f.value, f.unit, cond["op"], ref["value"], ref.get("unit"))


def _contract_level_check(rule: Rule, facts: Facts) -> bool:
    """Rule mà check chỉ dùng dữ kiện cấp hợp đồng (lương, thử việc, thời hạn) được xét khi có dữ kiện đó, kể cả khi
    LLM không gắn khái niệm cho điều khoản nào: dữ kiện đã được facts.py trích và kiểm trích dẫn."""
    names = _fact_names(rule.check)
    return bool(names) and all(n in CONTRACT_FACTS for n in names) and any(facts.get(n) is not None for n in names)


def _unstated_restriction(rule: Rule, facts: Facts, slots) -> bool:
    """Phép kiểm là một slot có/không "= false" (hợp đồng không có hạn chế / hành vi cấm) mà slot không được điền:
    khái niệm có mặt nhưng điều khoản không nói tới hạn chế (vd. "theo quy định của pháp luật") -> coi là không có.
    Kiểm "= true" (cần có điều kiện, vd. hợp đồng đào tạo riêng) không thuộc trường hợp này."""
    c = rule.check
    return (c is not None and c.get("op") == "eq" and c.get("value") is False and "law" not in c
            and c.get("fact") in slots and facts.get(c.get("fact")) is None)


def _result(concept_id, rule, status, finding, law, facts, evidence, reasons) -> RuleResult:
    names = _referenced(rule)
    used = {n: {"value": f.value, "unit": f.unit, **({"amended_from": list(f.amended_from)} if f.amended_from else {}),
                **({"later_amendments": list(f.later_amendments)} if f.later_amendments else {})}
            for n in names if (f := facts.get(n)) is not None and f is not CONFLICT}
    missing = tuple(n for n in names if facts.get(n) is None)
    reported = finding in _REPORTED
    return RuleResult(concept_id, rule.id, status, finding,
                      rule.outcome.get("legality") if reported else None,
                      rule.outcome.get("employee_impact") if reported else None,
                      law or {}, used, missing, tuple(evidence), tuple(reasons))


def _evaluate_rule(concept_id: str, rule: Rule, facts: Facts, present: bool, evidence, day: date,
                   slots=()) -> RuleResult:
    def out(status, finding, law=None, reasons=()):
        return _result(concept_id, rule, status, finding, law, facts, evidence, reasons)

    app = eval_cond(rule.applicability, facts)
    if app == "F":
        return out("NOT_APPLICABLE", "ok", reasons=("not_applicable",))
    law, law_st, reasons = resolve_law(rule, facts, day)
    if law_st == "F":
        return out("NOT_APPLICABLE", "ok", reasons=reasons)
    present = present or _contract_level_check(rule, facts)

    if present:
        if rule.check is None:
            if rule.mode == "prohibited":     # điều cấm không có phép kiểm trên chữ: cần người xem
                return out("UNKNOWN", "needs_facts", law, ("needs_review",))
            return out("PASS", "ok", law, reasons)
        if _unstated_restriction(rule, facts, slots):
            return out("PASS", "ok", law, (*reasons, "restriction_not_stated"))
        conflict = any(facts.get(n) is CONFLICT for n in _fact_names(rule.check))
        if law_st == "U":
            return out("UNKNOWN", "conflict" if conflict else "needs_facts", law, reasons)
        st = _check(rule.check, facts, law or {})
        if st == "U":
            return out("UNKNOWN", "conflict" if conflict else "needs_facts", law, (*reasons, "check_unknown"))
        if st == "T":
            return out("PASS", "ok", law, reasons)
        if app == "U":
            return out("UNKNOWN", "needs_facts", law, (*reasons, "applicability_unknown"))
        return out("FAIL", "violation", law, reasons)

    if rule.on_silence == "missing_content":
        return (out("UNKNOWN", "needs_facts", law, ("applicability_unknown",)) if app == "U"
                else out("FAIL", "missing_content", law, reasons))
    if rule.on_silence == "hidden_right":
        return (out("UNKNOWN", "possible_right", law, ("applicability_unknown",)) if app == "U"
                else out("PASS", "hidden_right", law, reasons))
    return out("PASS", "ok", law, reasons)


def evaluate_concept(concept, facts: Facts, *, present: bool, evidence=(), day: date) -> list[RuleResult]:
    return [_evaluate_rule(concept.id, r, facts, present, evidence, day, concept.slots) for r in concept.rules]


def evaluate(catalog, facts: Facts, present: set[str], evidence: dict[str, list[dict]], day: date) -> list[RuleResult]:
    return [r for cid, c in catalog.concepts.items()
            for r in evaluate_concept(c, facts, present=cid in present, evidence=evidence.get(cid, ()), day=day)]


__all__ = ["CONFLICT", "Fact", "Facts", "RuleResult", "Tri", "compare", "convert", "eval_cond", "evaluate",
           "evaluate_concept", "resolve_law"]
