"""Lớp tương thích bridge.engine / bridge.catalog trên rag.rules: tên công khai và hành vi mặc định như cũ."""
from datetime import date

from rag.bridge.catalog import CONTRACT_FACTS, DEFAULT_PATH, OPS, UNITS, USER_FACTS, _leaves, load_catalog
from rag.bridge.engine import (CONFLICT, Fact, Facts, RuleResult, Tri, _Conflict, compare, convert, eval_cond,
                               evaluate, evaluate_concept, resolve_law)
from rag.rules import semantics
from rag.rules.loader import load_pack
from rag.rules.model import Concept, Context, Rule
from rag.rules.units import Units


def test_compat_exports_and_labor_defaults():
    assert convert(2, "month", "day") == 60 and isinstance(CONFLICT, _Conflict)
    assert compare(10, "hour", "lte", 8, "hour") == "F"
    assert eval_cond({"fact": "h", "op": "lte", "value": 3, "unit": "workday"}, {"h": Fact(3, "day")}) == "U"
    assert Fact is semantics.Fact and RuleResult is semantics.RuleResult and CONFLICT is semantics.CONFLICT


def _hour_rule_concept():
    rule = Rule("r1", "threshold", "floor", "none", None, {}, (), {"fact": "h", "op": "lte", "value": 8, "unit": "hour"},
                {"legality": "illegal", "employee_impact": "unfavorable"})
    return Concept("x.a", "A", "core", "P0", "NLD", "NSDLD", ("NLD",), "d", ("a", "b", "c"), {}, (), (), (rule,))


def test_evaluate_concept_without_ctx_uses_labor_units_and_with_ctx_uses_given():
    concept, facts, day = _hour_rule_concept(), {"h": Fact(1, "day")}, date(2025, 3, 1)
    r = evaluate_concept(concept, facts, present=True, day=day)[0]
    assert (r.status, r.finding) == ("FAIL", "violation")          # bảng labor: 1 ngày = 24 giờ > 8
    custom = Context(Units(frozenset({"day", "hour"}), {"day": ("hour", 8), "hour": ("hour", 1)}), frozenset(),
                     load_pack("labor").silences)
    r = evaluate_concept(concept, facts, present=True, day=day, ctx=custom)[0]
    assert (r.status, r.finding) == ("PASS", "ok")                 # bảng của gói truyền vào: 1 ngày = 8 giờ


def test_bridge_catalog_shim_exports():
    pack = load_pack("labor")
    assert CONTRACT_FACTS == dict(pack.document_facts) and USER_FACTS == pack.user_facts and UNITS == pack.units.names
    assert "eq" in OPS and _leaves({"all": [{"fact": "a", "op": "eq", "value": 1}]}) == [{"fact": "a", "op": "eq", "value": 1}]
    assert DEFAULT_PATH.is_file()
    cat = load_catalog()
    assert isinstance(cat.context, Context)
    res = evaluate(cat, {}, set(), {}, date(2025, 3, 1))
    assert len(res) == sum(len(c.rules) for c in cat.concepts.values())
