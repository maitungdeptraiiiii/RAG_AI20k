"""Sửa theo review giai đoạn 4, 5, 7 (mỗi test tái hiện một phát hiện trước khi sửa)."""
from datetime import date

import pytest

from rag.bridge.catalog import load_catalog
from rag.rules.evaluator import ReferenceEvaluator, evaluator_for
from rag.rules.loader import load_packs
from rag.rules.model import CatalogError
from rag.rules.objects import WorkingObject, aggregate, apply_object_changes
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

DAY = date(2025, 3, 1)
NO_EXC = {k: Fact(False) for k in ("is_state_enterprise_director", "is_elderly_employee", "is_foreign_employee",
                                   "is_union_leader_in_term")}


def _contract(cid, start, end=None, **attrs):
    return WorkingObject(cid, "Contract", {"kind": Fact("xac_dinh_thoi_han"), **attrs}, start, end, {"employee": "E1"})


@pytest.mark.parametrize("kind", ["reference", "network"])
def test_important1_current_contract_without_expiry_facts_is_counted(kind):
    """Hồ sơ thật: HĐ đang hiệu lực chưa có worked_after_expiry_days (chưa hết hạn) -> loại hiệu lực = loại ghi."""
    expired = dict(worked_after_expiry_days=Fact(0, "day"), new_contract_signed=Fact(True))
    b1 = [_contract("h1", date(2022, 1, 1), date(2022, 12, 31), **expired),
          _contract("h2", date(2023, 1, 1), date(2023, 12, 31), **expired),
          _contract("h3", date(2024, 1, 1))]
    s = evaluator_for(load_catalog(), kind).session(day=DAY, facts=dict(NO_EXC), present=set(), evidence={}, objects=b1)
    out = {(r.rule_id, r.object): r for r in s.results() if r.concept_id == "content.term"}
    assert out[("r5", "employee=E1")].status == "FAIL" and "count:3..3" in out[("r5", "employee=E1")].reasons
    assert out[("r6", "employee=E1")].status == "PASS"
    # HĐ đã hết hạn trước ngày soát mà thiếu dữ kiện quá hạn: vẫn UNKNOWN (đúng: chưa biết có tự chuyển loại không)
    b1[0] = _contract("h1", date(2022, 1, 1), date(2022, 12, 31))
    s = evaluator_for(load_catalog(), kind).session(day=DAY, facts=dict(NO_EXC), present=set(), evidence={}, objects=b1)
    assert next(r for r in s.results() if r.rule_id == "r6").status == "UNKNOWN"


def test_important2_user_facts_of_other_packs_accepted_by_bridge():
    from rag.bridge.check import user_fact_set
    loan = load_packs(["civil_loan"])
    facts = user_fact_set({"special_law_applies": True}, loan.context)
    assert facts["special_law_applies"].value is True
    with pytest.raises(ValueError):
        user_fact_set({"special_law_applies": True})                     # mặc định vẫn là gói labor
    with pytest.raises(ValueError):
        user_fact_set({"khong_co": 1}, loan.context)
    labor = load_catalog().context
    assert user_fact_set({"worked_after_expiry_days": 45}, labor)["worked_after_expiry_days"].unit == "day"
    assert user_fact_set({"term_months": 12}, labor)["term_months"].unit == "month"


def test_important2_check_contract_with_civil_loan_and_its_user_facts():
    from rag.bridge.check import check_contract
    from test_bridge_check import AT, ScriptLLM, contract
    report = check_contract(ScriptLLM(), contract(), at=AT, packs=["civil_loan"], user_facts={"special_law_applies": False})
    assert {r.concept_id for r in report.results} >= {"loan.interest_cap"}


def test_minor3_present_but_excluded_objects_are_not_no_objects():
    assert aggregate([("F", None)]) == {None: (0, 0)}
    assert aggregate([]) == {}


def test_minor5_removed_must_be_a_sequence_of_ids_and_objects_validated():
    store = {"k": WorkingObject("k", "Contract"), "1": WorkingObject("1", "Contract"),
             "k1": WorkingObject("k1", "Contract")}
    with pytest.raises(TypeError):
        apply_object_changes(store, {"removed": "k1"})
    with pytest.raises(TypeError):
        apply_object_changes(store, {"added": WorkingObject("x", "Contract")})
    assert set(store) == {"k", "1", "k1"}
    for bad in (WorkingObject("a", "Contract", {"kind": "fixed"}), WorkingObject("a", "Contract", None),
                WorkingObject("a", "Contract", refs=None), WorkingObject("a", "Contract", valid_from="2020-01-01")):
        with pytest.raises(TypeError):
            ReferenceEvaluator(load_catalog()).session(day=DAY, facts={}, present=set(), evidence={}, objects=[bad])
        with pytest.raises(TypeError):
            evaluator_for(load_catalog(), "network").session(day=DAY, facts={}, present=set(), evidence={},
                                                              objects=[bad])


def test_minor7_explain_requires_obj_when_rule_has_several_groups():
    from rag.rules.explain import explain
    objs = [_contract("h1", date(2024, 1, 1)), WorkingObject("h2", "Contract", {"kind": Fact("xac_dinh_thoi_han")},
                                                              date(2024, 1, 1), None, {"employee": "E2"})]
    cat = load_catalog()
    s = evaluator_for(cat, "network").session(day=DAY, facts={}, present=set(), evidence={}, objects=objs)
    with pytest.raises(KeyError):
        explain(cat, s, "content.term", "r5")
    assert explain(cat, s, "content.term", "r5", obj="employee=E2").detail["object"] == "employee=E2"


def test_minor10_empty_packs_is_an_error():
    from rag.bridge.catalog import resolve_catalog
    with pytest.raises(ValueError):
        resolve_catalog(None, [])


PACK = {"object_types": {"Contract": {"attrs": ["kind"], "refs": ["employee"]}}}


@pytest.mark.parametrize("over,check,extra", [
    ({"c": {"type": "Contract", "where": ["kind"]}}, {"exists": "c"}, {}),
    ({"c": {"type": "Contract", "where": "kind"}}, {"exists": "c"}, {}),
    ({"c": {"type": "Contract"}}, {"count": {"of": "c", "op": "lte", "value": "2"}}, {}),
    ({"c": {"type": "Contract"}}, {"count": {"of": "c", "op": "lte", "value": True}}, {}),
    ({"c": {"type": "Contract", "history": "no"}}, {"exists": "c"}, {}),
    ({"c": {"type": "Contract"}}, {"exists": "c"}, {"group_by": ["c.refs.employee"]}),
])
def test_minor4_malformed_object_rules_are_catalog_errors(tmp_path, over, check, extra):
    write_pack(tmp_path, PACK, [concept("c.a", [rule("r", over=over, check=check, **extra)])], pack_id="bad")
    with pytest.raises(CatalogError):
        load_packs(["bad"], root=tmp_path)


def test_minor4_concept_kind_must_be_a_string(tmp_path):
    c = concept("c.a", [rule("r")])
    c["kind"] = ["rate_cap"]
    write_pack(tmp_path, {}, [c], pack_id="badk")
    with pytest.raises(CatalogError):
        load_packs(["badk"], root=tmp_path)
