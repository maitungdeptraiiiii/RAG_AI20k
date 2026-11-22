"""Network = Reference khi có đối tượng (spec §6.1 phần 2, §10): thêm / xóa / đổi đối tượng, dữ kiện, fork."""
import json
import random
from dataclasses import asdict
from datetime import date

import pytest

from rag.rules.evaluator import ReferenceEvaluator, evaluator_for
from rag.rules.loader import load_packs
from rag.rules.objects import ObjectChanges, WorkingObject
from rag.rules.semantics import CONFLICT, Fact
from rules_synth import concept, rule, write_pack
from test_rules_objects import PACK, RULES

DAY = date(2025, 3, 1)
EXTRA = [rule("flat_base", check={"fact": "exempt", "op": "eq", "value": False}),
         rule("flat_exc", exception_of="c.b/flat_base", applicability={"fact": "exempt", "op": "eq", "value": True}),
         rule("by_job", over={"c": {"type": "Contract", "where": {"fact": "kind", "op": "eq", "value": "fixed"}}},
              group_by={"employee": "c.refs.employee", "kind": "c.kind"}, check={"count": {"of": "c", "op": "lte",
                                                                                            "value": 1}})]


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    root = tmp_path_factory.mktemp("netobj")
    write_pack(root, PACK, [concept("c.a", RULES), concept("c.b", EXTRA)], pack_id="objs")
    cat = load_packs(["objs"], root=root)
    return cat, ReferenceEvaluator(cat), evaluator_for(cat, "network")


def dump(results):
    return json.dumps([asdict(r) for r in results], ensure_ascii=False, sort_keys=True, default=str)


def diff_key(d):
    return [(c.concept_id, c.rule_id, c.object, dump([c.before]) if c.before else None,
             dump([c.after]) if c.after else None) for c in d.changes]


def rand_obj(rng, oid):
    if rng.random() < 0.3:
        return WorkingObject(oid, "Amendment", {"modifies_term": Fact(rng.choice([True, False]))},
                             rng.choice([date(2020, 1, 1), date(2026, 1, 1), None]), None,
                             {"contract": rng.choice(["k1", "k2", None])})
    attrs = {}
    for name, values in (("kind", ["fixed", "open"]), ("days", [0, 10, 45]), ("signed", [True, False])):
        r = rng.random()
        if r < 0.7:
            v = rng.choice(values)
            attrs[name] = Fact(v, "day" if name == "days" else None)
        elif r < 0.8:
            attrs[name] = CONFLICT
    return WorkingObject(oid, "Contract", attrs, rng.choice([date(2020, 1, 1), date(2020, 1, 1), None, date(2026, 1, 1)]),
                         rng.choice([None, None, date(2024, 1, 1)]), {"employee": rng.choice(["E1", "E1", "E2", None])})


def rand_changes(rng, ids):
    added = tuple(rand_obj(rng, f"o{rng.randint(0, 9)}") for _ in range(rng.randint(0, 2)))
    changed = tuple(rand_obj(rng, oid) for oid in rng.sample(sorted(ids), min(len(ids), rng.randint(0, 2))))
    removed = tuple(rng.sample(sorted(ids), min(len(ids), rng.randint(0, 1))))
    return ObjectChanges(added, removed, changed)


@pytest.mark.parametrize("seed", range(20))
def test_network_equals_reference_with_random_object_changes(pair, seed):
    _cat, ref_ev, net_ev = pair
    rng = random.Random(seed)
    objects = [rand_obj(rng, f"o{i}") for i in range(rng.randint(0, 6))]
    objects = list({o.id: o for o in objects}.values())
    kw = dict(day=DAY, facts={}, present={"c.a", "c.b"}, evidence={}, objects=objects)
    ref, net = ref_ev.session(**kw), net_ev.session(**kw)
    ids = {o.id for o in objects}
    assert dump(net.results()) == dump(ref.results())
    for step in range(120):
        facts = {}
        if rng.random() < 0.3:
            facts["exempt"] = None if rng.random() < 0.3 else Fact(rng.choice([True, False]))
        changes = rand_changes(rng, ids) if rng.random() < 0.8 else None
        dr, dn = ref.update(facts, objects=changes), net.update(facts, objects=changes)
        if changes:
            ids = (ids - set(changes.removed)) | {o.id for o in changes.added + changes.changed}   # xóa trước, ghi sau
        assert dump(net.results()) == dump(ref.results()), (seed, step)
        assert diff_key(dn) == diff_key(dr), (seed, step)
        if step % 40 == 30:
            ref, net = ref.fork(), net.fork()


def test_object_change_recomputes_only_candidates_of_that_type(pair):
    _cat, _ref, net_ev = pair
    c1 = WorkingObject("k1", "Contract", {"kind": Fact("fixed"), "days": Fact(0, "day")}, date(2020, 1, 1), None,
                       {"employee": "E1"})
    net = net_ev.session(day=DAY, facts={"exempt": Fact(False)}, present={"c.a", "c.b"}, evidence={}, objects=[c1])
    contract_rules = len(net_ev.network.object_slots_by_type["Contract"])
    net.update({}, objects=ObjectChanges(changed=(WorkingObject("k1", "Contract", {"kind": Fact("open")},
                                                                date(2020, 1, 1), None, {"employee": "E1"}),)))
    assert net.stats["objects_recomputed"] == contract_rules and net.stats["rules_recomputed"] == contract_rules
    net.update({}, objects=ObjectChanges(added=(WorkingObject("a1", "Amendment", {"modifies_term": Fact(True)},
                                                              date(2020, 1, 1), None, {"contract": "k1"}),)))
    assert net.stats["objects_recomputed"] == len(net_ev.network.object_slots_by_type["Amendment"]) == 1
    net.update({"exempt": Fact(True)})
    assert net.stats["objects_recomputed"] == 0


def test_fork_keeps_object_memory_independent(pair):
    _cat, ref_ev, net_ev = pair
    c1 = WorkingObject("k1", "Contract", {"kind": Fact("fixed"), "days": Fact(0, "day")}, date(2020, 1, 1), None,
                       {"employee": "E1"})
    net = net_ev.session(day=DAY, facts={}, present=set(), evidence={}, objects=[c1])
    fork = net.fork()
    fork.update({}, objects={"removed": ["k1"]})
    ref = ref_ev.session(day=DAY, facts={}, present=set(), evidence={}, objects=[c1])
    assert dump(net.results()) == dump(ref.results()) and dump(fork.results()) != dump(net.results())
