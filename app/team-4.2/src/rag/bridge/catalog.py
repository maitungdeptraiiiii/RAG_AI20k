"""Danh mục khái niệm HĐLĐ (`concepts.yaml`): nạp và kiểm. Lỗi nào cũng dừng, báo hết một lần
(spec 2026-11-14-contract-concept-check §5)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

DEFAULT_PATH = Path(__file__).with_name("concepts.yaml")

UNITS = frozenset({"day", "workday", "week", "month", "hour", "minute", "percent", "vnd", "count"})
OPS = frozenset({"eq", "lt", "lte", "gt", "gte", "in", "present", "absent"})
MODES = frozenset({"required", "threshold", "prohibited", "default"})
DEROGATIONS = frozenset({"floor", "mandatory", "default"})
SILENCES = frozenset({"missing_content", "hidden_right", "none"})
SLOT_KINDS = frozenset({"duration", "percent", "money", "bool", "enum"})

CONTRACT_FACTS: dict[str, str | None] = {
    "contract_kind": None, "term_months": "month", "base_salary_vnd": "vnd", "has_probation": None,
    "probation_length": "day", "probation_pay_pct": "percent", "job_level": None, "sign_date": None,
}
USER_FACTS = frozenset({"work_condition", "pregnant", "pregnancy_month", "child_under_12_months",
                        "employee_consent", "medical_certificate", "wage_region",
                        "employee_is_female"})


class CatalogError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("Danh mục khái niệm lỗi:\n- " + "\n- ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Slot:
    name: str
    kind: Literal["duration", "percent", "money", "bool", "enum"]
    unit: str | None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    id: str
    mode: str
    derogation: str
    on_silence: str
    applicability: dict | None
    law: dict
    cases: tuple[dict, ...]
    check: dict | None
    outcome: dict


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    scope: str
    phase: str
    holder: str
    counterparty: str
    applies_to: tuple[str, ...]
    describe: str
    phrasing: tuple[str, ...]
    slots: dict[str, Slot]
    anchors: tuple[dict, ...]
    value_sources: tuple[dict, ...]
    rules: tuple[Rule, ...]
    not_about: tuple[dict, ...] = ()   # [{text, see}]: điều khoản dễ gán nhầm vào khái niệm này; see = khái niệm đúng


@dataclass(frozen=True)
class Catalog:
    version: str
    law_values_valid_from: date
    roles: dict[str, dict]
    concepts: dict[str, Concept]


def _leaves(cond: Any) -> list[dict]:
    """Các lá {fact, op, ...} của một điều kiện all / any / not."""
    if not isinstance(cond, dict):
        return []
    for key in ("all", "any"):
        if key in cond:
            return [x for c in cond[key] for x in _leaves(c)]
    if "not" in cond:
        return _leaves(cond["not"])
    return [cond]


def _law_names(rule: dict) -> tuple[set[str], list[set[str]]]:
    return set(rule.get("law") or {}), [set(c.get("law") or {}) for c in rule.get("cases") or []]


def _check_law_values(where: str, law: dict, problems: list[str]) -> None:
    for name, v in (law or {}).items():
        if not isinstance(v, dict):
            problems.append(f"{where}: giá trị luật {name} phải là {{value, unit}}")
            continue
        if v.get("unit") is not None and v["unit"] not in UNITS:
            problems.append(f"{where}: giá trị luật {name} có đơn vị lạ {v['unit']!r}")
        if "periods" in v:
            for p in v["periods"]:
                if "valid_from" not in p or "values" not in p:
                    problems.append(f"{where}: giá trị luật {name}: kỳ thiếu valid_from / values")
        elif "value" not in v:
            problems.append(f"{where}: giá trị luật {name} thiếu value")


def _rule(c: dict, r: dict, roles: set[str], problems: list[str]) -> Rule:
    where = f"{c.get('id')}/{r.get('id')}"
    for key, allowed in (("mode", MODES), ("derogation", DEROGATIONS), ("on_silence", SILENCES)):
        if r.get(key) not in allowed:
            problems.append(f"{where}: {key} {r.get(key)!r} không hợp lệ")
    slots = set((c.get("slots") or {}))
    known = slots | set(CONTRACT_FACTS) | USER_FACTS
    conds = [r.get("applicability"), r.get("check")] + [x.get("when") for x in r.get("cases") or []]
    leaves = [leaf for cond in conds for leaf in _leaves(cond)]
    for leaf in leaves:
        if leaf.get("op") not in OPS:
            problems.append(f"{where}: toán tử {leaf.get('op')!r} không hợp lệ")
        if leaf.get("fact") not in known:
            problems.append(f"{where}: dữ kiện {leaf.get('fact')!r} không phải slot, dữ kiện hợp đồng hay người dùng")
        if leaf.get("unit") is not None and leaf["unit"] not in UNITS:
            problems.append(f"{where}: đơn vị {leaf['unit']!r} không hợp lệ")
    fixed, per_case = _law_names(r)
    for leaf in _leaves(r.get("check")):
        name = leaf.get("law")
        if name is not None and name not in fixed and not (per_case and all(name in s for s in per_case)):
            problems.append(f"{where}: check dùng giá trị law {name!r} không có trong law / mọi cases")
    _check_law_values(where, r.get("law") or {}, problems)
    for case in r.get("cases") or []:
        _check_law_values(where, case.get("law") or {}, problems)
    for name, v in (r.get("law") or {}).items():
        if isinstance(v, dict) and v.get("by") is not None and v["by"] not in known:
            problems.append(f"{where}: dữ kiện {v['by']!r} (by của {name}) không xác định")
    return Rule(str(r.get("id")), r.get("mode"), r.get("derogation"), r.get("on_silence"), r.get("applicability"),
                dict(r.get("law") or {}), tuple(r.get("cases") or ()), r.get("check"), dict(r.get("outcome") or {}))


def _slots(c: dict, problems: list[str]) -> dict[str, Slot]:
    out = {}
    for name, s in (c.get("slots") or {}).items():
        if s.get("kind") not in SLOT_KINDS:
            problems.append(f"{c.get('id')}: slot {name} có kind lạ {s.get('kind')!r}")
        if s.get("unit") is not None and s["unit"] not in UNITS:
            problems.append(f"{c.get('id')}: slot {name} có đơn vị lạ {s['unit']!r}")
        out[name] = Slot(name, s.get("kind"), s.get("unit"), tuple(s.get("options") or ()))
    return out


def load_catalog(path: Path = DEFAULT_PATH) -> Catalog:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    problems: list[str] = []
    roles = {r["id"]: r for r in data.get("roles") or []}
    for r in roles.values():
        if r.get("subtype_of") is not None and r["subtype_of"] not in roles:
            problems.append(f"role {r['id']}: subtype_of {r['subtype_of']!r} không có")
    concepts: dict[str, Concept] = {}
    for c in data.get("concepts") or []:
        cid = c.get("id")
        if cid in concepts:
            problems.append(f"{cid}: trùng id")
        for key in ("holder", "counterparty"):
            if c.get(key) not in roles:
                problems.append(f"{cid}: role {key} {c.get(key)!r} không khai báo")
        for role in c.get("applies_to") or []:
            if role not in roles:
                problems.append(f"{cid}: role applies_to {role!r} không khai báo")
        slots = _slots(c, problems)
        rules = tuple(_rule(c, r, set(roles), problems) for r in c.get("rules") or [])
        concepts[cid] = Concept(cid, c.get("label", ""), c.get("scope", ""), c.get("phase", ""), c.get("holder"),
                                c.get("counterparty"), tuple(c.get("applies_to") or ()), c.get("describe", ""),
                                tuple(c.get("phrasing") or ()), slots, tuple(c.get("anchors") or ()),
                                tuple(c.get("value_sources") or ()), rules,
                                tuple(dict(x) for x in c.get("not_about") or ()))
    for cid, concept in concepts.items():
        for x in concept.not_about:
            if not x.get("text") or x.get("see") not in concepts:
                problems.append(f"{cid}: not_about cần text và see là khái niệm có trong danh mục: {x!r}")
    if problems:
        raise CatalogError(problems)
    return Catalog(str(data.get("version")), date.fromisoformat(str(data["law_values_valid_from"])), roles, concepts)


__all__ = ["CONTRACT_FACTS", "DEFAULT_PATH", "OPS", "UNITS", "USER_FACTS", "Catalog", "CatalogError", "Concept",
           "Rule", "Slot", "load_catalog"]
