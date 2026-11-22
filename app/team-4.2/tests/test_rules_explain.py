"""explain(): cây giải thích tới quote hợp đồng, nguồn giá trị luật, ngoại lệ bị loại (spec §8)."""
import json
from datetime import date

import pytest

from rag.bridge.catalog import load_catalog
from rag.rules.evaluator import evaluator_for
from rag.rules.explain import ExplanationNode, explain
from rag.rules.semantics import Fact

CAT = load_catalog()
DAY = date(2025, 3, 1)
XDTH = "xac_dinh_thoi_han"
NO_EXC = {k: Fact(False) for k in ("is_state_enterprise_director", "is_elderly_employee", "is_foreign_employee",
                                   "is_union_leader_in_term")}


def session(kind, facts, present=("content.term",)):
    return evaluator_for(CAT, kind).session(day=DAY, facts=facts, present=set(present), evidence={})


def walk(node):
    yield node
    for c in node.children:
        yield from walk(c)


def find(node, kind, label=None):
    return [n for n in walk(node) if n.kind == kind and (label is None or n.label == label)]


R4_FACTS = {"contract_kind": Fact(XDTH, source="contract", uid="p0.d1", quote="Hợp đồng xác định thời hạn 12 tháng"),
            "worked_after_expiry_days": Fact(45, "day", "user"), "new_contract_signed": Fact(False, None, "user")}


@pytest.mark.parametrize("kind", ["reference", "network"])
def test_session_exposes_merged_facts_and_day(kind):
    s = session(kind, R4_FACTS)
    assert s.day == DAY
    table = s.facts()
    assert table["contract_kind_effective"].derived_by == "d20k2b" and table["contract_kind"].uid == "p0.d1"
    table.pop("contract_kind")                                          # bản sao: sửa không ảnh hưởng phiên
    assert "contract_kind" in s.facts()


def test_both_evaluators_expose_identical_fact_tables():
    assert session("reference", R4_FACTS).facts() == session("network", R4_FACTS).facts()
    a, b = session("reference", R4_FACTS), session("network", R4_FACTS)
    for s in (a, b):
        s.update({"worked_after_expiry_days": Fact(10, "day", "user")})
    assert a.facts() == b.facts() and "contract_kind_effective" in a.facts()      # 10 ngày: suy ra = kind gốc


@pytest.mark.parametrize("kind", ["reference", "network"])
def test_explain_derived_fact_winning_definition_and_excluded_exception(kind):
    tree = explain(CAT, session(kind, R4_FACTS), "content.term", "r4")
    assert tree.kind == "rule" and tree.status == "FAIL" and tree.label == "content.term/r4"
    derived = find(tree, "derived", "contract_kind_effective")[0]
    assert derived.detail["value"] == "khong_xac_dinh_thoi_han" and derived.detail["derived_by"] == "d20k2b"
    defs = {n.label: n for n in find(derived, "definition")}
    assert defs["d20k2b"].detail["outcome"] == "chosen"
    assert defs["d20k2b"].detail["anchors"] == [{"pid": "bo-luat:45/2019/QH14#d20.k2.b", "role": "basis"}]
    assert defs["base"].detail["outcome"] == "overridden_by_exception"
    contract_kind = [n for n in find(tree, "fact", "contract_kind")][0]
    assert contract_kind.detail["quote"] == "Hợp đồng xác định thời hạn 12 tháng" and contract_kind.detail["uid"] == "p0.d1"


def test_explain_excluded_definition_when_false():
    facts = {**R4_FACTS, "worked_after_expiry_days": Fact(10, "day", "user")}
    derived = find(explain(CAT, session("network", facts), "content.term", "r4"), "derived")[0]
    defs = {n.label: n for n in find(derived, "definition")}
    assert defs["d20k2b"].detail["outcome"] == "excluded_when_false" and defs["base"].detail["outcome"] == "chosen"


def test_explain_rule_overridden_by_exception_rule():
    facts = {"contract_kind": Fact(XDTH), "fixed_term_contract_count": Fact(3), **NO_EXC,
             "is_elderly_employee": Fact(True)}
    tree = explain(CAT, session("network", facts), "content.term", "r3")
    assert tree.status == "NOT_APPLICABLE" and "overridden_by:content.term/r3_elderly" in tree.detail["reasons"]
    exc = find(tree, "exception", "content.term/r3_elderly")[0]
    assert exc.status == "PASS" and exc.detail["relation"] == "overridden_by"


def test_explain_cases_law_values_with_period_source_and_check_tree():
    facts = {"has_probation": Fact(True), "job_level": Fact("cao_dang_tro_len"), "probation_length": Fact(70, "day")}
    tree = explain(CAT, session("reference", facts, ("probation.duration",)), "probation.duration", "r1")
    case = find(tree, "case")
    assert [c.detail["chosen"] for c in case] == [False, True, False, False]
    assert find(tree, "law", "max_probation")[0].detail["value"] == 60
    check = find(tree, "check")[0]
    assert tree.status == "FAIL" and check.status == "F"
    wage = explain(CAT, session("network", {"wage_region": Fact("I"), "base_salary_vnd": Fact(4_000_000, "vnd")},
                                 ("wage.minimum_regional",)), "wage.minimum_regional", "r1")
    law = find(wage, "law", "min_wage")[0]
    assert law.detail["value"] == 4960000 and law.detail["source"] == "nghi-dinh:74/2024/NĐ-CP"
    assert law.detail["valid_from"] == "2024-07-01"


def test_explain_json_and_markdown():
    tree = explain(CAT, session("network", R4_FACTS), "content.term", "r4")
    data = json.loads(json.dumps(tree.to_json(), ensure_ascii=False))
    assert data["kind"] == "rule" and data["children"] and isinstance(data["children"][0]["children"], list)
    md = tree.to_markdown()
    assert "content.term/r4" in md and "d20k2b" in md and "Hợp đồng xác định thời hạn 12 tháng" in md
    assert md.splitlines()[0].startswith("- ") and any(line.startswith("  - ") for line in md.splitlines())
    assert isinstance(tree, ExplanationNode)


def test_explain_unknown_rule_is_key_error():
    with pytest.raises(KeyError):
        explain(CAT, session("network", {}), "content.term", "khong_co")
