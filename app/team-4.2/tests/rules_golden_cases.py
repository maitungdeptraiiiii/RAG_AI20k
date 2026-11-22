"""Bộ ca golden cho rule engine: đóng băng kết quả của engine cũ để mọi lần tách lõi phải cho kết quả giống hệt
(spec 2026-11-22-rete-rule-engine-design §10).

Ca gồm: (1) các dòng của tests/fixtures/bridge/engine_cases.yaml; (2) quét có hệ thống theo từng rule: mỗi dữ kiện rule
tham chiếu nhận các giá trị ứng viên (thiếu, CONFLICT, giá trị quanh ngưỡng...), nhân với present và hai ngày soát.

Ghi lại golden (chỉ khi cố ý): `python tests/rules_golden_cases.py --write` (chạy từ app/team-4.2)."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import yaml  # noqa: E402

from rag.bridge.catalog import Catalog, _leaves  # noqa: E402
from rag.bridge.engine import CONFLICT, Fact, Facts  # noqa: E402

HERE = Path(__file__).resolve().parent
GOLDEN_PATH = HERE / "fixtures" / "rules" / "golden" / "engine_results.json"
ENGINE_CASES = HERE / "fixtures" / "bridge" / "engine_cases.yaml"
SWEEP_DAYS = (date(2025, 3, 1), date(2026, 2, 1))
MAX_COMBOS = 48
MISSING = "__missing__"
OTHER = "__other__"


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    concept_id: str
    rule_id: str
    facts: dict
    present: bool
    day: date


def facts_from_spec(spec: Mapping[str, Any] | None, fact_cls=Fact, conflict=CONFLICT) -> Facts:
    """{"tên": [giá trị, đơn vị?]} hoặc "CONFLICT" -> Facts (cùng dạng engine_cases.yaml). `fact_cls` / `conflict`
    chọn lớp của engine đang thử (engine cũ và rag.rules có hai lớp Fact khác nhau đến khi bridge.engine thành shim)."""
    out: Facts = {}
    for name, v in (spec or {}).items():
        out[name] = conflict if v == "CONFLICT" else fact_cls(v[0], v[1] if len(v) > 1 else None)
    return out


def _numbers(t, unit):
    return [[t - 1, unit], [t, unit], [t + 1, unit]] if unit else [[t - 1], [t], [t + 1]]


def _law_items(rule, name):
    """Các mục law tên `name` ở rule.law và ở mọi case."""
    items = [rule.law.get(name)] + [c.get("law", {}).get(name) for c in rule.cases]
    return [x for x in items if isinstance(x, dict)]


def _candidates(rule) -> dict[str, list]:
    conds = [rule.applicability, rule.check] + [c.get("when") for c in rule.cases]
    leaves = [leaf for cond in conds for leaf in _leaves(cond)]
    cands: dict[str, list] = {}

    def add(name, entry):
        lst = cands.setdefault(name, [])
        if entry not in lst:
            lst.append(entry)

    for leaf in leaves:
        name = leaf.get("fact")
        if name is None:
            continue
        add(name, MISSING)
        add(name, "CONFLICT")
    for leaf in leaves:
        name, v, unit = leaf.get("fact"), leaf.get("value"), leaf.get("unit")
        if name is None:
            continue
        if "law" in leaf:
            for item in _law_items(rule, leaf["law"]):
                vals = [item["value"]] if isinstance(item.get("value"), (int, float)) else [
                    x for p in item.get("periods") or [] for x in p["values"].values() if isinstance(x, (int, float))]
                for t in vals:
                    for e in _numbers(t, item.get("unit")):
                        add(name, e)
        elif isinstance(v, bool):
            add(name, [True])
            add(name, [False])
        elif isinstance(v, (int, float)):
            for e in _numbers(v, unit):
                add(name, e)
        elif isinstance(v, str):
            add(name, [v])
            add(name, [OTHER])
        elif isinstance(v, list):
            for x in v:
                add(name, [x])
            add(name, [OTHER])
        else:
            add(name, [OTHER])
    for item in list(rule.law.values()) + [x for c in rule.cases for x in c.get("law", {}).values()]:
        by = item.get("by") if isinstance(item, dict) else None
        if by is None:
            continue
        add(by, MISSING)
        add(by, "CONFLICT")
        for p in item.get("periods") or []:
            for key in p["values"]:
                add(by, [key])
        add(by, [OTHER])
    return cands


def _combos(cands: dict[str, list]) -> list[dict]:
    names = list(cands)
    sizes = [len(cands[n]) for n in names]
    total = 1
    for s in sizes:
        total *= s
    picks = range(total) if total <= MAX_COMBOS else [i * total // MAX_COMBOS for i in range(MAX_COMBOS)]
    out = []
    for index in picks:
        spec = {}
        for name, size in zip(names, sizes):
            index, k = divmod(index, size)
            entry = cands[name][k]
            if entry != MISSING:
                spec[name] = entry
        out.append(spec)
    return out


def golden_cases(catalog: Catalog) -> list[GoldenCase]:
    cases: list[GoldenCase] = []

    def add(concept, rule, facts, present, day):
        cases.append(GoldenCase(f"{concept}/{rule}/{len(cases):04d}", concept, rule, facts, present, day))

    for row in yaml.safe_load(ENGINE_CASES.read_text(encoding="utf-8")):
        add(row["concept"], row["rule"], row["facts"] or {}, row["present"], date.fromisoformat(str(row.get("day", "2025-03-01"))))
    for cid, concept in catalog.concepts.items():
        for rule in concept.rules:
            for spec in _combos(_candidates(rule)):
                for present in (False, True):
                    for day in SWEEP_DAYS:
                        add(cid, rule.id, spec, present, day)
    return cases


def run_case(case: GoldenCase, catalog: Catalog, evaluate_concept_fn: Callable, *, fact_cls=Fact,
             conflict=CONFLICT) -> dict:
    """Kết quả của đúng rule `case.rule_id`, dạng dict JSON. `evaluate_concept_fn(concept, facts, present=, evidence=, day=)`."""
    results = evaluate_concept_fn(catalog.concepts[case.concept_id], facts_from_spec(case.facts, fact_cls, conflict),
                                  present=case.present, evidence=(), day=case.day)
    got = next(r for r in results if r.rule_id == case.rule_id)
    return result_json(got)


def result_json(result) -> dict:
    """RuleResult dạng dict JSON như golden. Golden đóng băng từ engine cũ (chưa có `object`, `outcome`, `party_impact`):
    bỏ `object` khi None; `outcome` / `party_impact` (D33) phải khớp hai trường cũ `legality` / `employee_impact` rồi bỏ."""
    d = json.loads(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    if d.get("object", 0) is None:
        d.pop("object")
    outcome, impact = d.pop("outcome", {}), d.pop("party_impact", None)
    assert impact == d["employee_impact"] == outcome.get("party_impact"), (result.concept_id, result.rule_id)
    assert d["legality"] == outcome.get("legality"), (result.concept_id, result.rule_id)
    return d


def case_to_json(case: GoldenCase) -> dict:
    return {"id": case.case_id, "concept": case.concept_id, "rule": case.rule_id, "facts": case.facts,
            "present": case.present, "day": case.day.isoformat()}


def load_golden() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def case_from_json(d: dict) -> GoldenCase:
    return GoldenCase(d["id"], d["concept"], d["rule"], d["facts"], d["present"], date.fromisoformat(d["day"]))


def write_golden(catalog: Catalog, evaluate_concept_fn: Callable) -> int:
    rows = [{"case": case_to_json(c), "result": run_case(c, catalog, evaluate_concept_fn)} for c in golden_cases(catalog)]
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n]\n",
                           encoding="utf-8")
    return len(rows)


def main(argv: list[str]) -> int:
    from rag.bridge.catalog import load_catalog
    from rag.bridge.engine import evaluate_concept
    catalog = load_catalog()
    if "--write" in argv:
        n = write_golden(catalog, evaluate_concept)
        print(f"wrote {n} cases to {GOLDEN_PATH} ({GOLDEN_PATH.stat().st_size // 1024} KB)")
    else:
        print(f"{len(golden_cases(catalog))} cases (add --write to rewrite the golden file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
