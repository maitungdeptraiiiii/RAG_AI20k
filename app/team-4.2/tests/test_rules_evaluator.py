"""ReferenceEvaluator / Session / Diff: interface công bố cho benchmark (spec §7), đã thay stub."""
from datetime import date

import pytest

from rag.rules import evaluator
from rag.rules.evaluator import Diff, RuleChange, evaluator_for, make_evaluator
from rag.rules.loader import PACKS_ROOT, load_concepts, load_pack
from rag.rules.model import CatalogError
from rag.rules.reference import evaluate_all
from rag.rules.semantics import Fact

CAT = load_concepts(PACKS_ROOT / "labor" / "concepts.yaml", load_pack("labor"))
DAY = date(2025, 3, 1)
BASE_FACTS = {"work_condition": Fact("binh_thuong")}


def _session(present=("leave.annual",)):
    return evaluator_for(CAT).session(day=DAY, facts=dict(BASE_FACTS), present=set(present), evidence={})


def _leave(results):
    return next(r for r in results if (r.concept_id, r.rule_id) == ("leave.annual", "r1"))


def test_session_results_equal_evaluate_all():
    assert _session().results() == evaluate_all(CAT, dict(BASE_FACTS), {"leave.annual"}, {}, DAY)


def test_make_evaluator_uses_real_catalog_and_rejects_unknown_pack():
    s = make_evaluator(["labor"]).session(day=DAY, facts=dict(BASE_FACTS), present={"leave.annual"}, evidence={})
    assert s.results() == _session().results()
    with pytest.raises(CatalogError):
        make_evaluator(["khong_co"])


def test_update_diff_sequence_on_leave_annual():
    s = _session()
    first = _leave(s.results())
    assert (first.status, first.finding) == ("UNKNOWN", "needs_facts")
    d = s.update({"annual_leave": Fact(8, "day")})
    assert isinstance(d, Diff) and [(c.concept_id, c.rule_id) for c in d.changes] == [("leave.annual", "r1")]
    assert isinstance(d.changes[0], RuleChange) and d.changes[0].before == first
    assert (d.changes[0].after.status, d.changes[0].after.finding) == ("FAIL", "violation")
    d = s.update({"annual_leave": Fact(15, "day")})
    assert (d.changes[0].after.status, d.changes[0].after.finding) == ("PASS", "ok")
    assert s.update({"annual_leave": Fact(15, "day")}).changes == ()
    d = s.update({"annual_leave": None})
    assert (d.changes[0].after.status, d.changes[0].after.finding) == ("UNKNOWN", "needs_facts")


def test_update_present_replaces_and_results_follow():
    s = _session()
    d = s.update({}, present=set())
    assert any((c.concept_id, c.rule_id) == ("leave.annual", "r1") for c in d.changes)
    assert s.results() == evaluate_all(CAT, dict(BASE_FACTS), set(), {}, DAY)


def test_fork_is_independent():
    s = _session()
    f = s.fork()
    f.update({"annual_leave": Fact(8, "day")})
    assert _leave(s.results()).status == "UNKNOWN" and _leave(f.results()).status == "FAIL"


def test_objects_not_supported_yet():
    s = _session()
    with pytest.raises(NotImplementedError):
        s.update({}, objects=[object()])
    with pytest.raises(NotImplementedError):
        evaluator_for(CAT).session(day=DAY, facts={}, present=set(), evidence={}, objects=[object()])


def test_network_kind_not_available_yet():
    with pytest.raises(NotImplementedError):
        make_evaluator(["labor"], "network")
    with pytest.raises(NotImplementedError):
        evaluator_for(CAT, "network")


def test_stub_removed():
    assert not hasattr(evaluator, "StubEvaluator")
