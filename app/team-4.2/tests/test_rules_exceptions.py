"""Ngoại lệ giữa rule (spec §5.4): bảng ba hàng, nhiều ngoại lệ, ngoại lệ lồng nhau, bộ nạp."""
import itertools

import pytest

from rag.rules.exceptions import (ExceptionIndex, Override, apply_exceptions, applies_states, exception_open, finalize,
                                  rule_key, rule_state)
from rag.rules.loader import load_packs
from rag.rules.model import CatalogError, Rule
from rag.rules.semantics import Fact, RuleInputs, RuleResult
from rules_synth import OUTCOME, concept, rule, write_pack

KINDS = {"document_facts": {}, "user_facts": ["a", "b"]}


def res(status, finding, *, legality="illegal", missing=("m",), reasons=("r",)):
    return RuleResult("c", "x", status, finding, legality, "unfavorable", {"v": {"value": 1}}, {"f": {"value": 1}},
                      missing, ({"uid": "u"},), reasons)


def make_rule(rid, exception_of=None, applicability=None):
    return Rule(rid, "required", "mandatory", "none", applicability, {}, (), None, dict(OUTCOME), False, exception_of)


def test_finalize_three_rows_for_every_base_status():
    for status, finding in (("PASS", "ok"), ("FAIL", "violation"), ("UNKNOWN", "needs_facts")):
        base = res(status, finding)
        out = finalize(base, [Override("c/e", "T", ())])
        assert (out.status, out.finding, out.legality, out.employee_impact, out.law_values, out.missing_facts,
                out.reasons) == ("NOT_APPLICABLE", "ok", None, None, {}, (), ("overridden_by:c/e",)), status
        assert out.facts_used == base.facts_used and out.evidence == base.evidence
        assert finalize(base, [Override("c/e", "F", ())]) is base
        assert finalize(base, []) is base
    fail = finalize(res("FAIL", "violation"), [Override("c/e", "U", ("q1", "m", "q2"))])
    assert (fail.status, fail.finding, fail.legality, fail.employee_impact) == ("UNKNOWN", "needs_facts", None, None)
    assert fail.missing_facts == ("m", "q1", "q2") and fail.reasons == ("r", "exception_unknown:c/e")
    for status, finding in (("PASS", "ok"), ("UNKNOWN", "needs_facts")):
        kept = finalize(res(status, finding), [Override("c/e", "U", ("q1",))])
        assert (kept.status, kept.finding, kept.missing_facts) == (status, finding, ("m",))
        assert kept.reasons == ("r", "exception_unknown:c/e")


def test_two_true_overrides_list_both_and_true_beats_unknown():
    out = finalize(res("FAIL", "violation"), [Override("c/e1", "T", ()), Override("c/e2", "T", ()),
                                              Override("c/e3", "U", ("q",))])
    assert out.status == "NOT_APPLICABLE" and out.reasons == ("overridden_by:c/e1", "overridden_by:c/e2")
    out = finalize(res("FAIL", "violation"), [Override("c/e1", "U", ("q",)), Override("c/e2", "U", ("p", "q"))])
    assert out.missing_facts == ("m", "q", "p") and out.reasons == ("r", "exception_unknown:c/e1",
                                                                       "exception_unknown:c/e2")


def test_rule_state_truth_table():
    for app, law_st in itertools.product("TFU", "TFU"):
        expected = "F" if "F" in (app, law_st) else ("T" if (app, law_st) == ("T", "T") else "U")
        assert rule_state(RuleInputs(app, None, law_st, (), None)) == expected, (app, law_st)


def chain():
    """X <- R <- R2 (R là ngoại lệ của X, R2 là ngoại lệ của R)."""
    items = [("c", make_rule("X")), ("c", make_rule("R", "c/X")), ("c", make_rule("R2", "c/R"))]
    return items, ExceptionIndex.build(items)


def test_index_children_ancestors_order_and_unknown_target_ignored():
    items, index = chain()
    assert index.keys == ("c/X", "c/R", "c/R2")
    assert index.children == ((1,), (2,), ()) and index.ancestors == ((), (0,), (1, 0))
    assert index.order == (2, 1, 0) and index.involved == frozenset({0, 1, 2})
    items.append(("d", make_rule("lone", "d/khong_co")))
    lone = ExceptionIndex.build(items)
    assert 3 not in lone.involved and lone.children[3] == () and lone.ancestors[3] == ()
    assert rule_key("c", items[0][1]) == "c/X"


def test_nested_exception_applies_through_chain():
    """Review Focus 4: chỉ ngoại lệ của ngoại lệ áp dụng thì rule gốc vẫn bị thay thế."""
    items, index = chain()
    assert applies_states(index, ("F", "F", "T")) == {2: "T", 1: "T", 0: "T"}
    bases = [res("FAIL", "violation"), res("PASS", "ok"), res("PASS", "ok")]
    out = apply_exceptions(index, bases, ("F", "F", "T"), lambda i: ())
    assert out[0].status == "NOT_APPLICABLE" and out[0].reasons == ("overridden_by:c/R",)
    assert out[1].status == "NOT_APPLICABLE" and out[1].reasons == ("overridden_by:c/R2",)
    assert out[2].status == "PASS"
    # ngoại lệ sâu nhất không áp dụng, ngoại lệ giữa áp dụng: gốc bị thay thế, ngoại lệ giữa giữ nguyên kết quả
    out = apply_exceptions(index, bases, ("F", "T", "F"), lambda i: ())
    assert out[0].status == "NOT_APPLICABLE" and out[1].status == "PASS"
    # ngoại lệ sâu nhất chưa biết: gốc FAIL hạ UNKNOWN, dữ kiện cần hỏi lấy từ cả cây
    out = apply_exceptions(index, bases, ("F", "F", "U"), lambda i: {2: ("deep",), 1: ("mid",)}.get(i, ()))
    assert out[0].status == "UNKNOWN" and out[0].missing_facts == ("m", "mid", "deep")
    assert "exception_unknown:c/R" in out[0].reasons
    assert apply_exceptions(index, bases, ("F", "F", "T"), lambda i: (), only={0})[0].status == "NOT_APPLICABLE"
    assert set(apply_exceptions(index, bases, ("F", "F", "T"), lambda i: (), only={0})) == {0}


def test_exception_open_lists_missing_inputs_of_applicability_and_cases():
    from rag.rules.loader import load_pack
    ctx = load_pack("labor").context()
    r = Rule("e", "required", "mandatory", "none", {"fact": "a", "op": "eq", "value": 1}, {},
             ({"when": {"fact": "b", "op": "eq", "value": 1}},), None, dict(OUTCOME), False, "c/X")
    assert exception_open(r, {"a": Fact(1)}, ctx) == ("b",)
    assert exception_open(r, {}, ctx) == ("a", "b")


def _problems(tmp_path, rules_by_concept, **pack):
    write_pack(tmp_path, {**KINDS, **pack}, [concept(cid, rs) for cid, rs in rules_by_concept.items()], pack_id="p")
    with pytest.raises(CatalogError) as e:
        load_packs(["p"], root=tmp_path)
    return "\n".join(e.value.problems)


def test_loader_rejects_missing_target_self_cycle_and_bad_format(tmp_path):
    text = _problems(tmp_path, {"c.a": [rule("x", exception_of="c.a/khong_co")]})
    assert "c.a/khong_co" in text
    text = _problems(tmp_path, {"c.a": [rule("x", exception_of="c.a/x")]})
    assert "c.a/x" in text
    text = _problems(tmp_path, {"c.a": [rule("x", exception_of="c.b/y")], "c.b": [rule("y", exception_of="c.a/x")]})
    assert "vòng" in text and "c.a/x" in text and "c.b/y" in text
    text = _problems(tmp_path, {"c.a": [rule("x", exception_of="khong_co_gach_cheo")]})
    assert "khong_co_gach_cheo" in text and "<concept>/<rule>" in text
    text = _problems(tmp_path, {"c.a": [rule("x", exception_of="gia.dinh/khong")]})              # concept đích cũng không có
    assert "gia.dinh/khong" in text


def test_loader_cross_pack_target_resolved_after_merge(tmp_path):
    cha = write_pack(tmp_path, KINDS, [concept("c.a", [rule("r1")])], pack_id="cha")
    write_pack(tmp_path, {"extends": [cha]}, [concept("c.b", [rule("e1", exception_of="c.a/r1")])], pack_id="con")
    cat = load_packs(["con"], root=tmp_path)
    assert cat.concepts["c.b"].rules[0].exception_of == "c.a/r1"
    write_pack(tmp_path, KINDS, [concept("c.b", [rule("e1", exception_of="c.a/r1")])], pack_id="le")  # không extends cha
    with pytest.raises(CatalogError) as e:
        load_packs(["le"], root=tmp_path)
    assert any("c.a/r1" in p for p in e.value.problems), e.value.problems
