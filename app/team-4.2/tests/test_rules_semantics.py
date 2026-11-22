"""Logic thuần của rule engine: ba trị, đơn vị theo gói, UNKNOWN, bảng on_silence, hai hook lao động đã khai báo hóa."""
from datetime import date

import pytest

from rag.rules.loader import load_pack
from rag.rules.model import Context, Rule
from rag.rules.semantics import CONFLICT, UNKNOWN, Fact, eval_cond, evaluate_rule, resolve_law

CTX = load_pack("labor").context()
DAY = date(2025, 3, 1)


def F(v, u=None):
    return Fact(v, u)


def mk_rule(**kw):
    base = dict(id="r1", mode="threshold", derogation="floor", on_silence="none", applicability=None, law={},
                cases=(), check=None, outcome={})
    base.update(kw)
    return Rule(**base)


def ev(rule, facts, present=False, ctx=CTX):
    return evaluate_rule("c.x", rule, facts, present, (), DAY, ctx)


def test_kleene_and_units_ported():
    facts = {"a": F(1), "b": CONFLICT}
    assert eval_cond(None, facts, CTX) == "T"
    assert eval_cond({"fact": "a", "op": "eq", "value": 1}, facts, CTX) == "T"
    assert eval_cond({"fact": "x", "op": "eq", "value": 1}, facts, CTX) == "U"
    assert eval_cond({"fact": "b", "op": "eq", "value": 1}, facts, CTX) == "U"
    assert eval_cond({"all": [{"fact": "a", "op": "eq", "value": 2}, {"fact": "x", "op": "eq", "value": 1}]}, facts, CTX) == "F"
    assert eval_cond({"all": [{"fact": "a", "op": "eq", "value": 1}, {"fact": "x", "op": "eq", "value": 1}]}, facts, CTX) == "U"
    assert eval_cond({"any": [{"fact": "a", "op": "eq", "value": 1}, {"fact": "x", "op": "eq", "value": 1}]}, facts, CTX) == "T"
    assert eval_cond({"any": [{"fact": "a", "op": "eq", "value": 2}, {"fact": "x", "op": "eq", "value": 1}]}, facts, CTX) == "U"
    assert eval_cond({"not": {"fact": "a", "op": "eq", "value": 1}}, facts, CTX) == "F"
    assert eval_cond({"fact": "x", "op": "absent"}, facts, CTX) == "T"
    assert eval_cond({"fact": "a", "op": "present"}, facts, CTX) == "T"
    assert eval_cond({"fact": "a", "op": "in", "value": [1, 2]}, facts, CTX) == "T"
    assert eval_cond({"fact": "h", "op": "lte", "value": 8, "unit": "hour"}, {"h": F(10, "hour")}, CTX) == "F"
    assert eval_cond({"fact": "h", "op": "lte", "value": 3, "unit": "workday"}, {"h": F(3, "day")}, CTX) == "U"
    assert eval_cond({"fact": "t", "op": "gte", "value": 12, "unit": "month"}, {"t": F(24, "month")}, CTX) == "T"


def test_cases_pick_first_true_and_unknown_blocks():
    rule = mk_rule(cases=(
        {"when": {"fact": "job_level", "op": "eq", "value": "cao_dang_tro_len"}, "law": {"max_probation": {"value": 60, "unit": "day"}}},
        {"when": {"fact": "job_level", "op": "eq", "value": "trung_cap_ky_thuat"}, "law": {"max_probation": {"value": 30, "unit": "day"}}}))
    law, st, _ = resolve_law(rule, {"job_level": F("cao_dang_tro_len")}, DAY, CTX)
    assert st == "T" and law["max_probation"] == {"value": 60, "unit": "day"}
    assert resolve_law(rule, {}, DAY, CTX)[1] == "U"
    assert resolve_law(rule, {"job_level": F("khac_hoan_toan")}, DAY, CTX)[1] == "F"


WAGE = mk_rule(law={"min_wage": {"by": "wage_region", "unit": "vnd", "periods": [
    {"valid_from": "2022-07-01", "values": {"I": 4680000}},
    {"valid_from": "2024-07-01", "values": {"I": 4960000}},
    {"valid_from": "2026-01-01", "values": {"I": 5310000}}]}})


def test_periods_by_sign_date():
    law, st, _ = resolve_law(WAGE, {"wage_region": F("I")}, date(2025, 3, 1), CTX)
    assert st == "T" and law["min_wage"] == {"value": 4960000, "unit": "vnd"}
    assert resolve_law(WAGE, {"wage_region": F("I")}, date(2026, 2, 1), CTX)[0]["min_wage"]["value"] == 5310000
    assert resolve_law(WAGE, {}, date(2026, 2, 1), CTX)[1] == "U"
    _, st, reasons = resolve_law(WAGE, {"wage_region": F("I")}, date(2020, 1, 1), CTX)
    assert st == "U" and "law_period_not_covered" in reasons


def test_unknown_behaves_like_conflict_at_leaves():
    for op in ("eq", "lt", "present", "absent"):
        assert eval_cond({"fact": "d", "op": op, "value": 1}, {"d": UNKNOWN}, CTX) == "U", op
    assert resolve_law(WAGE, {"wage_region": UNKNOWN}, DAY, CTX) == (None, "U", ("missing_fact:wage_region",))


def test_unknown_excluded_from_facts_used_and_missing():
    r = ev(mk_rule(check={"fact": "d", "op": "eq", "value": 1}), {"d": UNKNOWN}, present=True)
    assert (r.status, r.finding) == ("UNKNOWN", "needs_facts")
    assert "d" not in r.facts_used and "d" not in r.missing_facts


APP = {"fact": "a", "op": "eq", "value": True}


@pytest.mark.parametrize("silence,facts,expected", [
    ("missing_content", {"a": F(True)}, ("FAIL", "missing_content", ())),
    ("missing_content", {}, ("UNKNOWN", "needs_facts", ("applicability_unknown",))),
    ("hidden_right", {"a": F(True)}, ("PASS", "hidden_right", ())),
    ("hidden_right", {}, ("UNKNOWN", "possible_right", ("applicability_unknown",))),
    ("none", {"a": F(True)}, ("PASS", "ok", ())),
    ("none", {}, ("PASS", "ok", ())),
])
def test_on_silence_table(silence, facts, expected):
    r = ev(mk_rule(on_silence=silence, applicability=APP), facts, present=False)
    assert (r.status, r.finding, r.reasons) == expected


def test_document_level_check_counts_as_present():
    rule = mk_rule(on_silence="hidden_right", check={"fact": "base_salary_vnd", "op": "gte", "value": 5000000, "unit": "vnd"},
                   outcome={"legality": "illegal", "employee_impact": "unfavorable"})
    facts = {"base_salary_vnd": F(4000000, "vnd")}
    r = ev(rule, facts)
    assert (r.status, r.finding, r.legality) == ("FAIL", "violation", "illegal")
    no_doc = Context(CTX.units, frozenset(), CTX.silences)
    r = ev(rule, facts, ctx=no_doc)
    assert (r.status, r.finding) == ("PASS", "hidden_right")


def test_unstated_restriction_flag():
    check = {"fact": "x", "op": "eq", "value": False}
    r = ev(mk_rule(check=check, unstated_false=True), {}, present=True)
    assert (r.status, r.finding) == ("PASS", "ok") and "restriction_not_stated" in r.reasons
    r = ev(mk_rule(check=check, unstated_false=False), {}, present=True)
    assert (r.status, r.finding) == ("UNKNOWN", "needs_facts")
