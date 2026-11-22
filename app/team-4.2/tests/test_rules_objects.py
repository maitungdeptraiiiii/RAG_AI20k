"""Đối tượng, đếm, phủ định (spec §5.6): ngữ nghĩa thuần, bộ nạp, ReferenceEvaluator."""
import itertools
from datetime import date

import pytest

from rag.rules.evaluator import ReferenceEvaluator
from rag.rules.loader import load_packs
from rag.rules.model import CatalogError
from rag.rules.objects import (ObjectChanges, WorkingObject, aggregate, apply_object_changes, count_tri, membership)
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

DAY = date(2025, 3, 1)


def obj(oid, typ="Contract", attrs=None, refs=None, valid_from=date(2020, 1, 1), valid_to=None):
    attrs = {k: v if isinstance(v, Fact) else Fact(v, "day" if k == "days" else None) for k, v in (attrs or {}).items()}
    return WorkingObject(oid, typ, attrs, valid_from, valid_to, refs or {})


# ── ngữ nghĩa thuần ──
def test_count_tri_interval_semantics():
    def brute(op, lo, hi, k):
        sat = [{"lt": v < k, "lte": v <= k, "gt": v > k, "gte": v >= k, "eq": v == k}[op] for v in range(lo, hi + 1)]
        return "T" if all(sat) else ("F" if not any(sat) else "U")
    for op, lo, n_u, k in itertools.product(["lt", "lte", "gt", "gte", "eq"], range(4), range(4), range(5)):
        assert count_tri(op, lo, lo + n_u, k) == brute(op, lo, lo + n_u, k), (op, lo, n_u, k)
    assert count_tri("gt", 3, 5, 2) == "T" and count_tri("gt", 0, 2, 2) == "F" and count_tri("gt", 1, 3, 2) == "U"


def test_membership_at_day_and_history():
    assert membership(obj("a"), DAY) == "T"
    assert membership(obj("a", valid_from=date(2026, 1, 1)), DAY) == "F"
    assert membership(obj("a", valid_to=date(2024, 12, 31)), DAY) == "F"
    assert membership(obj("a", valid_to=date(2024, 12, 31)), DAY, history=True) == "T"
    assert membership(obj("a", valid_from=None), DAY) == "U"
    assert membership(obj("a", valid_to=DAY), DAY) == "T"


def test_aggregate_groups_unknown_keys_count_as_u_everywhere():
    cands = [("T", ("E1",)), ("U", ("E1",)), ("F", ("E2",)), ("T", None), ("F", None)]
    assert aggregate(cands) == {("E1",): (1, 2), ("E2",): (0, 1)}
    assert aggregate([("T", None), ("U", None)]) == {None: (0, 2)}
    assert aggregate([]) == {} and aggregate([("F", ())]) == {(): (0, 0)}


def test_apply_object_changes_upsert_and_remove():
    store = {"a": obj("a")}
    changed = apply_object_changes(store, ObjectChanges(added=(obj("b"),), changed=(obj("a", attrs={"x": 1}),),
                                                       removed=("zz",)))
    assert changed == {"a", "b"} and store["a"].attrs["x"] == Fact(1)
    assert apply_object_changes(store, {"removed": ["a"]}) == {"a"} and set(store) == {"b"}
    with pytest.raises(TypeError):
        apply_object_changes(store, ["a"])


# ── gói tổng hợp ──
PACK = {
    "user_facts": ["exempt"],
    "object_types": {"Contract": {"attrs": ["kind", "days", "signed"], "refs": ["employee"]},
                     "Amendment": {"attrs": ["modifies_term"], "refs": ["contract"]}},
    "derived": [{"fact": "kind_eff", "object_type": "Contract", "definitions": [
        {"id": "base", "from": "kind"},
        {"id": "conv", "exception_of": "base",
         "when": {"all": [{"fact": "kind", "op": "eq", "value": "fixed"},
                          {"fact": "days", "op": "gt", "value": 30, "unit": "day"},
                          {"fact": "signed", "op": "eq", "value": False}]}, "value": "open"}]}],
}
RULES = [
    rule("limit", mode="threshold", law={"max_n": {"value": 2, "unit": None}},
         applicability={"not": {"fact": "exempt", "op": "eq", "value": True}},
         over={"c": {"type": "Contract", "where": {"fact": "kind_eff", "op": "eq", "value": "fixed"}, "history": True}},
         group_by={"employee": "c.refs.employee"}, check={"count": {"of": "c", "op": "lte", "law": "max_n"}}),
    rule("converted", over={"c": {"type": "Contract", "where": {"all": [
        {"fact": "kind", "op": "eq", "value": "fixed"}, {"fact": "kind_eff", "op": "eq", "value": "open"}]}}},
         group_by={"employee": "c.refs.employee"}, check={"not_exists": "c"}),
    rule("no_term_edit", over={"a": {"type": "Amendment", "where": {"fact": "modifies_term", "op": "eq", "value": True}}},
         group_by={"contract": "a.refs.contract"}, check={"not_exists": "a"}),
    rule("any_contract", over={"c": {"type": "Contract"}}, check={"exists": "c"}),
    rule("flat", check={"fact": "exempt", "op": "eq", "value": False}),
]


@pytest.fixture(scope="module")
def cat(tmp_path_factory):
    root = tmp_path_factory.mktemp("obj")
    write_pack(root, PACK, [concept("c.a", RULES)], pack_id="objs")
    return load_packs(["objs"], root=root)


def run(cat, objects, facts=None):
    s = ReferenceEvaluator(cat).session(day=DAY, facts=facts or {}, present={"c.a"}, evidence={}, objects=objects)
    return {(r.rule_id, r.object): r for r in s.results()}


def contracts(*kinds, employee="E1", **attrs):
    """Mặc định days = 0 (không làm việc quá hạn) để kind_eff = kind; không có days thì kind_eff đúng là UNKNOWN."""
    attrs = {"days": 0, **attrs}
    return [obj(f"k{i}", attrs={"kind": k, **attrs}, refs={"employee": employee}) for i, k in enumerate(kinds)]


def test_object_rules_without_objects_are_not_applicable_never_violations(cat):
    out = run(cat, [])
    for rid in ("limit", "converted", "no_term_edit", "any_contract"):
        assert out[(rid, None)].status == "NOT_APPLICABLE" and out[(rid, None)].reasons == ("no_objects",), rid
    assert out[("flat", None)].status == "UNKNOWN"


def test_count_per_group_with_history_and_law_value(cat):
    two = run(cat, contracts("fixed", "fixed"), {"exempt": Fact(False)})
    assert two[("limit", "employee=E1")].status == "PASS"
    three = run(cat, contracts("fixed", "fixed", "fixed"), {"exempt": Fact(False)})
    r = three[("limit", "employee=E1")]
    assert (r.status, r.finding, r.law_values["max_n"]["value"]) == ("FAIL", "violation", 2)
    assert "count:3..3" in r.reasons
    expired = contracts("fixed", "fixed") + [obj("old", attrs={"kind": "fixed", "days": 0}, refs={"employee": "E1"},
                                                 valid_to=date(2023, 1, 1))]
    assert run(cat, expired, {"exempt": Fact(False)})[("limit", "employee=E1")].status == "FAIL"   # history: đếm cả HĐ cũ
    other = run(cat, contracts("fixed", "fixed") + contracts("fixed", employee="E2"), {"exempt": Fact(False)})
    assert other[("limit", "employee=E1")].status == "PASS" and other[("limit", "employee=E2")].status == "PASS"


def test_unknown_candidates_and_keys_give_unknown_not_violation(cat):
    unknown_kind = contracts("fixed", "fixed") + [obj("k9", refs={"employee": "E1"})]      # kind thiếu -> ứng viên U
    r = run(cat, unknown_kind, {"exempt": Fact(False)})[("limit", "employee=E1")]
    assert r.status == "UNKNOWN" and "count:2..3" in r.reasons
    unknown_key = contracts("fixed", "fixed") + [obj("k9", attrs={"kind": "fixed"})]         # chưa biết của ai
    assert run(cat, unknown_key, {"exempt": Fact(False)})[("limit", "employee=E1")].status == "UNKNOWN"
    only_unknown_key = [obj("k9", attrs={"kind": "fixed"})]
    assert run(cat, only_unknown_key, {"exempt": Fact(False)})[("limit", None)].status == "PASS"   # [0,1] <= 2
    unknown_from = contracts("fixed", "fixed") + [obj("k9", attrs={"kind": "fixed"}, refs={"employee": "E1"},
                                                      valid_from=None)]
    assert run(cat, unknown_from, {"exempt": Fact(False)})[("limit", "employee=E1")].status == "UNKNOWN"


def test_applicability_exception_on_user_fact(cat):
    three = contracts("fixed", "fixed", "fixed")
    assert run(cat, three, {"exempt": Fact(True)})[("limit", "employee=E1")].status == "NOT_APPLICABLE"
    r = run(cat, three)[("limit", "employee=E1")]                                          # chưa biết có được miễn không
    assert (r.status, r.finding) == ("UNKNOWN", "needs_facts")


def test_per_object_derived_fact_and_not_exists(cat):
    ok = run(cat, contracts("fixed", days=10, signed=False))
    assert ok[("converted", "employee=E1")].status == "PASS"
    conv = contracts("fixed", days=45, signed=False)
    out = run(cat, conv)
    assert out[("converted", "employee=E1")].status == "FAIL"
    assert out[("limit", "employee=E1")].status != "FAIL"                                  # kind_eff = open: không đếm
    unknown = [obj("k0", attrs={"kind": "fixed", "days": 45}, refs={"employee": "E1"})]   # chưa biết đã ký mới chưa
    assert run(cat, unknown)[("converted", "employee=E1")].status == "UNKNOWN"


def test_amendment_grouped_by_contract_and_exists(cat):
    amends = [obj("a1", "Amendment", {"modifies_term": False}, {"contract": "k0"}),
              obj("a2", "Amendment", {"modifies_term": True}, {"contract": "k1"})]
    out = run(cat, contracts("open") + amends)
    assert out[("no_term_edit", "contract=k0")].status == "PASS"
    assert out[("no_term_edit", "contract=k1")].status == "FAIL"
    assert out[("any_contract", None)].status == "PASS"
    future = [obj("a3", "Amendment", {"modifies_term": True}, {"contract": "k0"}, valid_from=date(2026, 1, 1))]
    assert run(cat, future)[("no_term_edit", "contract=k0")].status == "PASS"              # chưa hiệu lực ngày soát


def test_session_update_objects_and_diff_keys(cat):
    s = ReferenceEvaluator(cat).session(day=DAY, facts={"exempt": Fact(False)}, present={"c.a"}, evidence={},
                                        objects=contracts("fixed", "fixed"))
    diff = s.update({}, objects=ObjectChanges(added=(obj("k7", attrs={"kind": "fixed"}, refs={"employee": "E1"}),)))
    keys = {(c.rule_id, c.object) for c in diff.changes}
    assert ("limit", "employee=E1") in keys
    diff = s.update({}, objects=ObjectChanges(added=(obj("x", attrs={"kind": "fixed"}, refs={"employee": "E3"}),)))
    added = [c for c in diff.changes if c.object == "employee=E3" and c.rule_id == "limit"]
    assert added and added[0].before is None and added[0].after.status == "PASS"
    diff = s.update({}, objects={"removed": ["x"]})
    gone = [c for c in diff.changes if c.object == "employee=E3" and c.rule_id == "limit"]
    assert gone and gone[0].after is None


# ── bộ nạp ──
def _problems(tmp_path, rules, pack=PACK):
    write_pack(tmp_path, pack, [concept("c.a", rules)], pack_id="bad")
    with pytest.raises(CatalogError) as e:
        load_packs(["bad"], root=tmp_path)
    return "\n".join(e.value.problems)


def test_loader_rejects_bad_object_rules(tmp_path):
    base = dict(over={"c": {"type": "Contract"}}, check={"exists": "c"})
    assert "Khong" in _problems(tmp_path, [rule("r", over={"c": {"type": "Khong"}}, check={"exists": "c"})])
    assert "'x'" in _problems(tmp_path, [rule("r", **base, group_by={"g": "x.refs.employee"})])
    assert "'boss'" in _problems(tmp_path, [rule("r", **base, group_by={"g": "c.refs.boss"})])
    assert "'zz'" in _problems(tmp_path, [rule("r", over={"c": {"type": "Contract", "where": {
        "fact": "zz", "op": "eq", "value": 1}}}, check={"exists": "c"})])
    assert "một biến" in _problems(tmp_path, [rule("r", over={"c": {"type": "Contract"}, "d": {"type": "Contract"}},
                                                   check={"exists": "c"})])
    assert "'d'" in _problems(tmp_path, [rule("r", over={"c": {"type": "Contract"}}, check={"exists": "d"})])
    assert "count" in _problems(tmp_path, [rule("r", over={"c": {"type": "Contract"}},
                                                check={"count": {"of": "c", "op": "geq", "value": 1}})])
    assert "check" in _problems(tmp_path, [rule("r", over={"c": {"type": "Contract"}},
                                                check={"fact": "exempt", "op": "eq", "value": True})])
    text = _problems(tmp_path, [rule("r", **base), rule("e", exception_of="c.a/r", applicability={
        "fact": "exempt", "op": "eq", "value": True})])
    assert "exception_of" in text
    assert "group_by" in _problems(tmp_path, [rule("r", group_by={"g": "c.refs.employee"})])


def test_loader_rejects_bad_object_types_and_typed_derived(tmp_path):
    bad_type = {**PACK, "object_types": {"Contract": {"attrs": "kind"}}}
    assert "object_types" in _problems(tmp_path, [rule("r")], bad_type)
    bad_derived = {**PACK, "derived": [{"fact": "k2", "object_type": "Khong", "definitions": [{"id": "d", "value": 1}]}]}
    assert "Khong" in _problems(tmp_path, [rule("r")], bad_derived)
    bad_input = {**PACK, "derived": [{"fact": "k2", "object_type": "Contract", "definitions": [
        {"id": "d", "from": "khong_co"}]}]}
    assert "khong_co" in _problems(tmp_path, [rule("r")], bad_input)
