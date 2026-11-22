from datetime import date

from rag.bridge.catalog import load_catalog
from rag.bridge.engine import CONFLICT, Fact, convert, eval_cond, resolve_law

CAT = load_catalog()


def F(v, u=None):
    return Fact(v, u)


def test_kleene():
    facts = {"a": F(1), "b": CONFLICT}
    assert eval_cond(None, facts) == "T"
    assert eval_cond({"fact": "a", "op": "eq", "value": 1}, facts) == "T"
    assert eval_cond({"fact": "x", "op": "eq", "value": 1}, facts) == "U"
    assert eval_cond({"fact": "b", "op": "eq", "value": 1}, facts) == "U"
    assert eval_cond({"all": [{"fact": "a", "op": "eq", "value": 2}, {"fact": "x", "op": "eq", "value": 1}]}, facts) == "F"
    assert eval_cond({"all": [{"fact": "a", "op": "eq", "value": 1}, {"fact": "x", "op": "eq", "value": 1}]}, facts) == "U"
    assert eval_cond({"any": [{"fact": "a", "op": "eq", "value": 1}, {"fact": "x", "op": "eq", "value": 1}]}, facts) == "T"
    assert eval_cond({"any": [{"fact": "a", "op": "eq", "value": 2}, {"fact": "x", "op": "eq", "value": 1}]}, facts) == "U"
    assert eval_cond({"not": {"fact": "a", "op": "eq", "value": 1}}, facts) == "F"
    assert eval_cond({"fact": "x", "op": "absent"}, facts) == "T"
    assert eval_cond({"fact": "a", "op": "present"}, facts) == "T"
    assert eval_cond({"fact": "a", "op": "in", "value": [1, 2]}, facts) == "T"


def test_units():
    assert convert(2, "month", "day") == 60
    assert convert(1, "week", "day") == 7
    assert convert(1, "day", "hour") == 24
    assert convert(48, "hour", "day") == 2
    assert convert(3, "workday", "day") is None
    assert convert(5, "percent", "percent") == 5
    assert eval_cond({"fact": "h", "op": "lte", "value": 8, "unit": "hour"}, {"h": F(10, "hour")}) == "F"
    assert eval_cond({"fact": "h", "op": "lte", "value": 3, "unit": "workday"}, {"h": F(3, "day")}) == "U"
    assert eval_cond({"fact": "t", "op": "gte", "value": 12, "unit": "month"}, {"t": F(24, "month")}) == "T"


def test_cases_pick_first_true_and_unknown_blocks():
    rule = CAT.concepts["probation.duration"].rules[0]
    law, st, _ = resolve_law(rule, {"job_level": F("cao_dang_tro_len")}, date(2025, 1, 2))
    assert st == "T" and law["max_probation"] == {"value": 60, "unit": "day"}
    assert resolve_law(rule, {}, date(2025, 1, 2))[1] == "U"
    assert resolve_law(rule, {"job_level": F("khac_hoan_toan")}, date(2025, 1, 2))[1] == "F"


def test_fixed_law_values():
    rule = CAT.concepts["probation.pay"].rules[0]
    law, st, _ = resolve_law(rule, {}, date(2025, 1, 2))
    assert st == "T" and law == {"min_probation_pay": {"value": 85, "unit": "percent"}}


def test_periods_by_sign_date():
    rule = CAT.concepts["wage.minimum_regional"].rules[0]
    law, st, _ = resolve_law(rule, {"wage_region": F("I")}, date(2025, 3, 1))
    assert st == "T" and law["min_wage"] == {"value": 4960000, "unit": "vnd"}
    assert resolve_law(rule, {"wage_region": F("I")}, date(2026, 2, 1))[0]["min_wage"]["value"] == 5310000
    assert resolve_law(rule, {}, date(2026, 2, 1))[1] == "U"
    law, st, reasons = resolve_law(rule, {"wage_region": F("I")}, date(2020, 1, 1))
    assert st == "U" and "law_period_not_covered" in reasons


# ── Task 6: đánh giá rule theo bảng ca ──
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

from rag.bridge.engine import evaluate, evaluate_concept  # noqa: E402

CASES = yaml.safe_load((Path(__file__).parent / "fixtures" / "bridge" / "engine_cases.yaml").read_text(encoding="utf-8"))


def _facts(spec):
    out = {}
    for k, v in (spec or {}).items():
        out[k] = CONFLICT if v == "CONFLICT" else Fact(v[0], v[1] if len(v) > 1 else None)
    return out


@pytest.mark.parametrize("case", CASES, ids=lambda c: f'{c["concept"]}/{c["rule"]}/{c["expect"]["status"]}/{c["expect"]["finding"]}')
def test_engine_case(case):
    day = date.fromisoformat(case.get("day", "2025-03-01"))
    results = evaluate_concept(CAT.concepts[case["concept"]], _facts(case["facts"]), present=case["present"], day=day)
    got = next(r for r in results if r.rule_id == case["rule"])
    assert (got.status, got.finding) == (case["expect"]["status"], case["expect"]["finding"]), got.reasons


def test_every_rule_has_three_cases():
    count = Counter((c["concept"], c["rule"]) for c in CASES)
    # Rule xuyên đối tượng (r.over) cần hồ sơ có đối tượng; bảng ca này là hợp đồng đơn lẻ (xem test_rules_labor_objects.py).
    assert [(k, r.id) for k, x in CAT.concepts.items() for r in x.rules if r.over is None and count[(k, r.id)] < 3] == []


def test_outcome_only_on_findings_and_evidence_passthrough():
    ev = [{"uid": "p0.d3", "quote": "nghỉ phép 08 ngày", "op_id": "o1"}]
    r = evaluate_concept(CAT.concepts["leave.annual"], _facts({"work_condition": ["binh_thuong"], "annual_leave": [8, "day"]}),
                         present=True, evidence=ev, day=date(2025, 3, 1))[0]
    assert (r.legality, r.employee_impact) == ("illegal", "unfavorable")
    assert r.evidence == tuple(ev) and r.law_values["min_annual_leave"]["value"] == 12
    assert r.facts_used["annual_leave"] == {"value": 8, "unit": "day"}
    ok = evaluate_concept(CAT.concepts["leave.annual"], _facts({"work_condition": ["binh_thuong"], "annual_leave": [15, "day"]}),
                          present=True, day=date(2025, 3, 1))[0]
    assert ok.legality is None and ok.employee_impact is None
    miss = evaluate_concept(CAT.concepts["leave.annual"], {}, present=True, day=date(2025, 3, 1))[0]
    assert set(miss.missing_facts) == {"annual_leave", "work_condition"}


def test_evaluate_whole_catalog():
    res = evaluate(CAT, {}, set(), {}, date(2025, 3, 1))
    assert len(res) == sum(len(c.rules) for c in CAT.concepts.values())
    assert {r.finding for r in res} <= {"ok", "missing_content", "hidden_right", "possible_right", "needs_facts"}
