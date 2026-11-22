"""Network = Reference khi có dữ kiện suy ra (nhiều tầng, ngoại lệ lồng) và ngoại lệ giữa rule (kể cả chéo concept)."""
import json
import random
from dataclasses import asdict
from datetime import date

import pytest

from rag.rules.evaluator import ReferenceEvaluator, evaluator_for
from rag.rules.loader import load_packs
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

DAY = date(2025, 3, 1)
EQ = lambda name, value: {"fact": name, "op": "eq", "value": value}            # noqa: E731
PACK = {
    "document_facts": {"kind": None}, "user_facts": ["a", "b", "c", "d", "p", "q"],
    "derived": [
        {"fact": "kind_eff", "unit": None, "definitions": [
            {"id": "base", "from": "kind"},
            {"id": "x", "exception_of": "base", "when": {"all": [EQ("a", 1), EQ("b", 1)]}, "value": "k2"},
            {"id": "y", "exception_of": "x", "when": EQ("c", 1), "value": "k3"}]},
        {"fact": "tier", "unit": None, "definitions": [
            {"id": "hi", "when": EQ("kind_eff", "k2"), "value": "high"},
            {"id": "lo", "when": EQ("kind_eff", "k1"), "value": "low"}]},
    ],
}
CONCEPTS = [
    concept("c.a", [rule("uses", check=EQ("kind_eff", "k1")),
                    rule("uses2", applicability=EQ("d", 1), check=EQ("tier", "low"))]),
    concept("c.b", [rule("lim", check=EQ("p", 1)),
                    rule("exc1", exception_of="c.b/lim", applicability=EQ("a", 1)),
                    rule("exc1b", exception_of="c.b/exc1", applicability=EQ("d", 1), check=EQ("q", 1))]),
    concept("c.c", [rule("xexc", exception_of="c.b/lim", applicability=EQ("q", 1),
                         cases=[{"when": EQ("b", 1), "law": {"n": {"value": 1, "unit": None}}}])]),
]
CONCEPT_IDS = ["c.a", "c.b", "c.c"]
VALUES = [1, 2, True, 1.0]


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    root = tmp_path_factory.mktemp("synth3")
    write_pack(root, PACK, CONCEPTS, pack_id="synth")
    cat = load_packs(["synth"], root=root)
    return cat, ReferenceEvaluator(cat), evaluator_for(cat, "network")


def dump(results):
    return json.dumps([asdict(r) for r in results], ensure_ascii=False, sort_keys=True, default=str)


def diff_key(d):
    return [(c.concept_id, c.rule_id, dump([c.before]), dump([c.after])) for c in d.changes]


def rand_fact(rng, name):
    return Fact(rng.choice(["k1", "k2", "k3"]) if name == "kind" else rng.choice(VALUES))


def rand_state(rng):
    facts = {n: rand_fact(rng, n) for n in ["kind", "a", "b", "c", "d", "p", "q"] if rng.random() < 0.5}
    return facts, {c for c in CONCEPT_IDS if rng.random() < 0.6}


def rand_update(rng):
    names = ["kind", "a", "b", "c", "d", "p", "q", "kind_eff", "tier", "zz"]
    changes = {n: (None if rng.random() < 0.3 else rand_fact(rng, n)) for n in rng.sample(names, rng.randint(0, 4))}
    kw = {}
    if rng.random() < 0.2:
        kw["present"] = {c for c in CONCEPT_IDS if rng.random() < 0.6}
    if rng.random() < 0.1:
        kw["evidence"] = {c: [{"uid": f"p0.{c}", "quote": "q"}] for c in CONCEPT_IDS if rng.random() < 0.5}
    return changes, kw


def both(pair, facts=None, present=("c.a", "c.b", "c.c")):
    _cat, ref, net = pair
    kw = dict(day=DAY, facts=dict(facts or {}), present=set(present), evidence={})
    return ref.session(**kw), net.session(**kw)


@pytest.mark.parametrize("seed", range(20))
def test_network_equals_reference_on_synthetic_pack_random_updates(pair, seed):
    rng = random.Random(seed)
    facts, present = rand_state(rng)
    ref, net = both(pair, facts, present)
    assert dump(net.results()) == dump(ref.results())
    for step in range(150):
        changes, kw = rand_update(rng)
        dr, dn = ref.update(changes, **kw), net.update(changes, **kw)
        assert dump(net.results()) == dump(ref.results()), (seed, step)
        assert diff_key(dn) == diff_key(dr), (seed, step)
        if step % 40 == 20:
            ref, net = ref.fork(), net.fork()
            assert dump(net.results()) == dump(ref.results())


def test_fork_is_independent_with_derived_and_exceptions(pair):
    ref, net = both(pair, {"kind": Fact("k1"), "p": Fact(2)})
    fork_ref, fork_net = ref.fork(), net.fork()
    changes = {"a": Fact(1), "b": Fact(1)}
    fork_net.update(changes), fork_ref.update(changes)
    assert dump(net.results()) == dump(ref.results()) and dump(fork_net.results()) == dump(fork_ref.results())
    assert dump(fork_net.results()) != dump(net.results())


def test_raw_fact_with_derived_name_ignored_in_both(pair):
    """Review Focus 2."""
    base = {"kind": Fact("k1"), "a": Fact(2)}
    ref0, net0 = both(pair, base)
    ref, net = both(pair, {**base, "kind_eff": Fact("k9"), "tier": Fact("zzz")})
    assert dump(net.results()) == dump(ref.results()) == dump(ref0.results()) == dump(net0.results())
    ref.update({"kind_eff": Fact("k9")}), net.update({"kind_eff": Fact("k9")})
    assert dump(net.results()) == dump(ref.results()) == dump(ref0.results())


def test_derived_recomputed_on_type_changing_input(pair):
    """Review Focus 3: kind đổi 1 -> True làm kind_eff đổi kiểu giá trị; kết quả phải theo kiểu mới như Reference."""
    ref, net = both(pair, {"kind": Fact(1), "a": Fact(2), "c": Fact(2)})        # kind_eff = kind (các ngoại lệ đều F)
    assert '"kind_eff": {"derived_by": "base", "unit": null, "value": 1}' in dump(net.results())
    ref.update({"kind": Fact(True)}), net.update({"kind": Fact(True)})
    assert dump(net.results()) == dump(ref.results())
    assert '"kind_eff": {"derived_by": "base", "unit": null, "value": true}' in dump(net.results())


def test_update_recomputes_only_affected_rules(pair):
    _cat, _ref, ev = pair
    _r, net = both(pair, {"kind": Fact("k1")})
    assert net.update({"zz": Fact(1)}).changes == () and net.stats["rules_recomputed"] == 0
    net.update({"q": Fact(1)})
    assert net.stats["rules_recomputed"] == len(ev.network.rules_by_fact["q"])
    net.update({"a": Fact(2)})
    dependents = ev.network.rules_by_fact["a"]                                   # gồm rule đọc kind_eff / tier qua đầu vào
    assert net.stats["rules_recomputed"] == len(dependents)
    keys = {ev.network.rules[i].concept_id + "/" + ev.network.rules[i].rule.id for i in dependents}
    assert {"c.a/uses", "c.a/uses2", "c.b/exc1"} <= keys


def test_missing_facts_follow_derived_inputs_when_derived_stays_unknown(pair):
    ref, net = both(pair, {"kind": Fact("k1")})
    first = next(r for r in net.results() if r.rule_id == "uses")
    assert first.status == "UNKNOWN" and first.missing_facts == ("a", "b", "c")     # x cần a, b; y (ngoại lệ của x) cần c
    ref.update({"a": Fact(1)}), net.update({"a": Fact(1)})                       # kind_eff vẫn UNKNOWN, thiếu còn b, c
    second = next(r for r in net.results() if r.rule_id == "uses")
    assert second.status == "UNKNOWN" and second.missing_facts == ("b", "c")
    assert dump(net.results()) == dump(ref.results())


def test_override_follows_exception_input_changes_through_chain(pair):
    ref, net = both(pair, {"kind": Fact("k1"), "p": Fact(2), "a": Fact(2), "d": Fact(2), "q": Fact(2), "b": Fact(2)})
    lim = lambda s: next(r for r in s.results() if r.rule_id == "lim")           # noqa: E731
    assert lim(net).status == "FAIL"
    steps = (({"q": Fact(1)}, "FAIL"),                                            # xexc: applicability T nhưng không case nào khớp (b = 2)
             ({"b": Fact(1)}, "NOT_APPLICABLE"),                                  # case khớp: xexc áp dụng
             ({"q": Fact(2)}, "FAIL"),
             ({"a": Fact(1)}, "NOT_APPLICABLE"),                                  # exc1
             ({"d": Fact(1)}, "NOT_APPLICABLE"),                                  # exc1b áp dụng: exc1 bị thay, gốc vẫn bị thay
             ({"a": None, "d": Fact(2)}, "UNKNOWN"))                              # exc1 chưa biết, không ngoại lệ nào áp dụng
    for changes, status in steps:
        ref.update(changes), net.update(changes)
        assert dump(net.results()) == dump(ref.results()), changes
        assert lim(net).status == status, (changes, lim(net))
