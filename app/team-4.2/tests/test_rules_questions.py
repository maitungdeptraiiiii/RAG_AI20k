"""next_questions(): xếp hạng câu hỏi theo số kết quả UNKNOWN chắc chắn được giải quyết (spec §8)."""
from datetime import date

import pytest

from rag.bridge.catalog import load_catalog
from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_pack, load_packs
from rag.rules.model import CatalogError
from rag.rules.questions import next_questions
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

DAY = date(2025, 3, 1)


def eq(name, value=1):
    return {"fact": name, "op": "eq", "value": value}


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("q")
    pack = {"user_facts": ["a", "b", "c", "n"],
            "user_fact_questions": {
                "a": {"question": "A là 1?", "values": [1, 2]}, "b": {"question": "B là 1?", "values": [1, 2]},
                "n": {"question": "Bao nhiêu ngày?", "values": [5, 50], "unit": "day"}}}
    rules = [rule("r1", check=eq("a")), rule("r2", check=eq("a")), rule("r3", check=eq("b")), rule("r4", check=eq("c")),
             rule("r5", check={"fact": "n", "op": "gt", "value": 30, "unit": "day"})]
    write_pack(root, pack, [concept("c.a", rules)], pack_id="qs")
    return load_packs(["qs"], root=root)


@pytest.mark.parametrize("kind", ["reference", "network"])
def test_ranking_counts_certainly_resolved_results_and_skips_unlisted_facts(synth, kind):
    s = evaluator_for(synth, kind).session(day=DAY, facts={}, present={"c.a"}, evidence={})
    before = [r.status for r in s.results()]
    qs = next_questions(synth, s)
    assert [q.fact for q in qs] == ["a", "b", "n"]                        # c không khai miền: không gợi ý
    top = qs[0]
    assert (top.guaranteed, top.possible, top.question) == (2, 2, "A là 1?") and dict(top.outcomes) == {1: 2, 2: 2}
    assert [(q.guaranteed, q.possible) for q in qs] == [(2, 2), (1, 1), (1, 1)]
    assert [r.status for r in s.results()] == before                     # fork: phiên gốc không đổi
    assert next_questions(synth, s) == qs


def test_answered_fact_is_not_asked_again_and_unknown_free_session_has_no_questions(synth):
    s = evaluator_for(synth, "network").session(day=DAY, facts={"a": Fact(1)}, present={"c.a"}, evidence={})
    assert "a" not in [q.fact for q in next_questions(synth, s)]
    full = evaluator_for(synth, "network").session(
        day=DAY, facts={n: Fact(1) for n in "abc"} | {"n": Fact(50, "day")}, present={"c.a"}, evidence={})
    assert next_questions(synth, full) == []


def test_question_uses_declared_unit(synth):
    s = evaluator_for(synth, "reference").session(day=DAY, facts={}, present={"c.a"}, evidence={})
    n = next(q for q in next_questions(synth, s) if q.fact == "n")
    assert n.unit == "day" and dict(n.outcomes) == {5: 1, 50: 1}


def test_labor_expired_fixed_term_contract_asks_about_article_20(tmp_path):
    cat = load_catalog()
    s = evaluator_for(cat, "network").session(day=DAY, facts={"contract_kind": Fact("xac_dinh_thoi_han")},
                                              present={"content.term"}, evidence={})
    unknown_before = sum(r.status == "UNKNOWN" for r in s.results())
    qs = next_questions(cat, s)
    names = [q.fact for q in qs]
    assert {"worked_after_expiry_days", "new_contract_signed", "fixed_term_contract_count"} <= set(names)
    assert all(q.possible > 0 for q in qs) and qs == sorted(qs, key=lambda q: (-q.guaranteed, -q.possible, q.fact))
    best = max(qs[0].outcomes, key=lambda o: o[1])[0]
    fork = s.fork()
    fork.update({qs[0].fact: Fact(best, qs[0].unit, "user")})
    assert sum(r.status == "UNKNOWN" for r in fork.results()) < unknown_before
    assert all(q.question for q in qs)


def _bad(tmp_path, questions, **pack):
    write_pack(tmp_path, {"user_facts": ["a"], **pack, "user_fact_questions": questions}, pack_id="badq")
    with pytest.raises(CatalogError) as e:
        load_pack("badq", root=tmp_path)
    return "\n".join(e.value.problems)


def test_loader_validates_user_fact_questions(tmp_path):
    assert "'khong_co'" in _bad(tmp_path, {"khong_co": {"question": "?", "values": [1]}})
    assert "values" in _bad(tmp_path, {"a": {"question": "?", "values": []}})
    assert "question" in _bad(tmp_path, {"a": {"values": [1]}})
    assert "lightyear" in _bad(tmp_path, {"a": {"question": "?", "values": [1], "unit": "lightyear"}})
    assert "dict" in _bad(tmp_path, ["a"])
