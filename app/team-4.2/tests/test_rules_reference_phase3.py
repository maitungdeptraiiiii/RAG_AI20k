"""ReferenceEvaluator với dữ kiện suy ra và ngoại lệ giữa rule (gói tổng hợp, bộ nạp thật)."""
import itertools
from datetime import date

import pytest

from rag.rules import reference
from rag.rules.loader import load_packs
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

DAY = date(2025, 3, 1)
PACK = {
    "document_facts": {"kind": None}, "user_facts": ["a", "b", "p"],
    "derived": [{"fact": "kind_eff", "unit": None, "definitions": [
        {"id": "base", "from": "kind"},
        {"id": "x", "exception_of": "base", "when": {"all": [{"fact": "a", "op": "eq", "value": 1},
                                                           {"fact": "b", "op": "eq", "value": 1}]}, "value": "k2"}]}],
}
CONCEPTS = [
    concept("c.a", [rule("uses", check={"fact": "kind_eff", "op": "eq", "value": "k1"})]),
    concept("c.b", [rule("lim", check={"fact": "p", "op": "eq", "value": 1}),
                    rule("exc1", exception_of="c.b/lim", applicability={"fact": "a", "op": "eq", "value": 1})]),
    concept("c.c", [rule("xexc", exception_of="c.b/lim", applicability={"fact": "b", "op": "eq", "value": 1})]),
]


@pytest.fixture(scope="module")
def cat(tmp_path_factory):
    root = tmp_path_factory.mktemp("synth")
    write_pack(root, PACK, CONCEPTS, pack_id="synth")
    return load_packs(["synth"], root=root)


def run(cat, facts, present=("c.a", "c.b", "c.c")):
    out = reference.evaluate_all(cat, {k: Fact(v) for k, v in facts.items()}, set(present), {}, DAY)
    return {f"{r.concept_id}/{r.rule_id}": r for r in out}


def test_rule_reads_derived_fact_and_missing_inputs_expanded(cat):
    """Review Focus 5: missing_facts là dữ kiện đầu vào, không phải tên dữ kiện suy ra."""
    r = run(cat, {"kind": "k1"})["c.a/uses"]
    assert (r.status, r.finding) == ("UNKNOWN", "needs_facts")
    assert r.missing_facts == ("a", "b") and "kind_eff" not in r.missing_facts
    assert "derived_unknown:kind_eff" in r.reasons and "check_unknown" in r.reasons
    assert r.facts_used == {}
    r = run(cat, {"kind": "k1", "a": 2})["c.a/uses"]                       # ngoại lệ F -> kind_eff = k1
    assert (r.status, r.missing_facts, r.facts_used["kind_eff"]) == ("PASS", (), {"value": "k1", "unit": None,
                                                                              "derived_by": "base"})
    r = run(cat, {"kind": "k1", "a": 1, "b": 1})["c.a/uses"]               # ngoại lệ T -> kind_eff = k2
    assert (r.status, r.finding) == ("FAIL", "violation") and r.facts_used["kind_eff"]["derived_by"] == "x"
    r = run(cat, {})["c.a/uses"]                                           # kind thiếu: mở cả `from`
    assert r.status == "UNKNOWN" and r.missing_facts == ("kind", "a", "b")


def test_raw_fact_with_derived_name_is_ignored(cat):
    r = run(cat, {"kind": "k1", "a": 2, "kind_eff": "k2"})["c.a/uses"]
    assert r.status == "PASS"


def test_override_rows_in_evaluate_all(cat):
    lim = lambda facts: run(cat, facts)["c.b/lim"]                         # noqa: E731
    r = lim({"p": 2, "a": 1})
    assert r.status == "NOT_APPLICABLE" and r.reasons == ("overridden_by:c.b/exc1",)
    assert run(cat, {"p": 2, "a": 1})["c.b/exc1"].status == "PASS"
    r = lim({"p": 2, "a": 2, "b": 2})
    assert (r.status, r.finding) == ("FAIL", "violation")
    r = lim({"p": 2, "a": 2, "b": 1})                                      # ngoại lệ ở concept khác áp dụng
    assert r.status == "NOT_APPLICABLE" and r.reasons == ("overridden_by:c.c/xexc",)
    r = lim({"p": 2, "a": 1, "b": 1})                                      # hai ngoại lệ cùng T
    assert r.reasons == ("overridden_by:c.b/exc1", "overridden_by:c.c/xexc")
    r = lim({"p": 2, "a": 2})                                              # b thiếu: ngoại lệ xexc chưa biết
    assert (r.status, r.finding) == ("UNKNOWN", "needs_facts") and r.legality is None
    assert r.missing_facts == ("b",) and r.reasons == ("exception_unknown:c.c/xexc",)
    r = lim({"p": 1, "a": 2})                                              # PASS giữ nguyên, thêm reason
    assert r.status == "PASS" and r.reasons == ("exception_unknown:c.c/xexc",)


def test_evaluate_concept_applies_only_same_concept_exceptions(cat):
    facts = {k: Fact(v) for k, v in {"p": 2, "a": 2, "b": 1}.items()}
    concept_b = cat.concepts["c.b"]
    r = reference.evaluate_concept(concept_b, facts, present=True, day=DAY, ctx=cat.context)
    assert r[0].status == "FAIL" and r[0].reasons == ()                     # xexc ở c.c không được xét
    facts["a"] = Fact(1)
    r = reference.evaluate_concept(concept_b, facts, present=True, day=DAY, ctx=cat.context)
    assert r[0].status == "NOT_APPLICABLE" and r[0].reasons == ("overridden_by:c.b/exc1",)


def test_invariant_missing_fact_never_causes_fail(cat):
    names = ["kind", "a", "b", "p"]
    for full in itertools.product(["k1", "k2"], [1, 2], [1, 2], [1, 2]):
        assign = dict(zip(names, full))
        results = {}
        for keep in itertools.product([False, True], repeat=4):
            sub = {n: v for (n, v), k in zip(assign.items(), keep) if k}
            results[keep] = {k: r.status for k, r in run(cat, sub).items()}
        for small, big in itertools.product(results, results):
            if all(b or not s for s, b in zip(small, big)):                # big ⊇ small
                for key, status in results[small].items():
                    if status == "FAIL":
                        assert results[big][key] == "FAIL", (assign, small, big, key)
