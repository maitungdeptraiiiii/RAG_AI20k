"""K2: bộ sinh gói tổng hợp cho benchmark, nạp bằng loader thật (kế hoạch 2026-11-23-khanh-ingest-bench-eval, Task 4–5)."""
import dataclasses
import json
import random
from datetime import date

import yaml

from rag.rules.bench.synth import (RuleSpec, load_rule_pack, present_all, random_facts, update_batches, write_rule_pack)
from rag.rules.evaluator import evaluator_for

SPEC = RuleSpec(n_rules=50, shared_ratio=0.5, depth=3, n_facts=50, seed=0)
DAY = date(2025, 1, 1)


def _statuses(cat, facts):
    return [r.status for r in evaluator_for(cat, "reference").session(day=DAY, facts=facts, present=present_all(cat), evidence={}).results()]


def test_synth_pack_loads_with_real_loader(tmp_path):
    cat = load_rule_pack(SPEC, tmp_path)
    assert sum(len(c.rules) for c in cat.concepts.values()) == 50


def test_same_seed_same_yaml(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    pid = write_rule_pack(SPEC, a)
    assert write_rule_pack(SPEC, b) == pid
    for f in ("pack.yaml", "concepts.yaml"):
        assert (a / pid / f).read_bytes() == (b / pid / f).read_bytes()


def test_other_seed_other_yaml(tmp_path):
    p1 = write_rule_pack(SPEC, tmp_path / "a")
    p2 = write_rule_pack(dataclasses.replace(SPEC, seed=1), tmp_path / "b")
    assert (tmp_path / "a" / p1 / "concepts.yaml").read_bytes() != (tmp_path / "b" / p2 / "concepts.yaml").read_bytes()


def test_full_facts_give_both_pass_and_fail(tmp_path):
    cat = load_rule_pack(SPEC, tmp_path)
    assert {"PASS", "FAIL"} <= set(_statuses(cat, random_facts(cat, SPEC, random.Random(0), missing=0.0)))


def test_missing_facts_give_unknown(tmp_path):
    cat = load_rule_pack(SPEC, tmp_path)
    assert "UNKNOWN" in _statuses(cat, random_facts(cat, SPEC, random.Random(0), missing=0.5))


def test_shared_ratio_controls_shared_conditions(tmp_path):
    def shared(ratio):
        pid = write_rule_pack(dataclasses.replace(SPEC, shared_ratio=ratio, depth=0), tmp_path / str(ratio))
        rules = [r for c in yaml.safe_load((tmp_path / str(ratio) / pid / "concepts.yaml").read_text(encoding="utf-8"))["concepts"]
                 for r in c["rules"]]
        conds = [json.dumps(r.get("applicability"), sort_keys=True) for r in rules]
        return sum(conds.count(c) > 1 for c in conds)
    assert shared(0.2) < shared(0.5)


def test_depth_zero_has_no_derived(tmp_path):
    pid = write_rule_pack(RuleSpec(20, 0.2, 0, 50, 1), tmp_path)
    assert not yaml.safe_load((tmp_path / pid / "pack.yaml").read_text(encoding="utf-8")).get("derived")


def test_depth_three_chain_reaches_rules(tmp_path):
    pid = write_rule_pack(SPEC, tmp_path)
    pack = yaml.safe_load((tmp_path / pid / "pack.yaml").read_text(encoding="utf-8"))
    assert [d["fact"] for d in pack["derived"]] == ["d1", "d2", "d3"]
    assert "d3" in (tmp_path / pid / "concepts.yaml").read_text(encoding="utf-8")


def test_update_batches_have_size_and_deletions(tmp_path):
    cat = load_rule_pack(SPEC, tmp_path)
    batches = update_batches(cat, SPEC, random.Random(0), size=5, count=20)
    assert len(batches) == 20 and all(len(b) == 5 for b in batches)
    assert any(v is None for b in batches for v in b.values())


# ───────────────────────────── trục 2 (Task 5) ─────────────────────────────
from rag.rules.bench.synth import ObjSpec, load_object_pack, object_changes, random_objects  # noqa: E402


def _canon(cat, objs, kind):
    return json.dumps([dataclasses.asdict(r) for r in evaluator_for(cat, kind).session(
        day=DAY, facts={}, present=set(), evidence={}, objects=objs).results()], default=str, sort_keys=True)


def test_object_pack_has_three_cross_rule_shapes(tmp_path):
    cat = load_object_pack(ObjSpec(20, 6, 0), tmp_path)
    rules = [r for c in cat.concepts.values() for r in c.rules if r.over is not None]
    assert len(rules) == 6
    assert any(len(r.group_by) == 2 for r in rules)
    assert {next(iter(r.check)) for r in rules} == {"count", "not_exists"}


def test_objects_evaluate_and_agree(tmp_path):
    spec = ObjSpec(20, 6, 0)
    cat = load_object_pack(spec, tmp_path)
    objs = random_objects(spec, random.Random(0))
    assert len(objs) == 20
    ref, net = _canon(cat, objs, "reference"), _canon(cat, objs, "network")
    assert ref == net and '"object": "employee=' in ref
    assert '"status": "FAIL"' in ref and '"status": "PASS"' in ref


def test_some_attributes_are_unknown():
    objs = random_objects(ObjSpec(50, 5, 0), random.Random(0))
    contracts = [o for o in objs if o.type == "Contract"]
    assert any(len(o.attrs) < 4 for o in contracts) and any(len(o.attrs) == 4 for o in contracts)


def test_object_changes_cover_add_remove_modify():
    objs = random_objects(ObjSpec(5, 5, 0), random.Random(0))
    ids = {o.id for o in objs}
    add = object_changes(objs, random.Random(1), "add")
    rem = object_changes(objs, random.Random(1), "remove")
    mod = object_changes(objs, random.Random(1), "modify")
    assert len(add.added) == 1 and add.added[0].id not in ids
    assert len(rem.removed) == 1 and rem.removed[0] in ids
    assert len(mod.changed) == 1 and mod.changed[0].id in ids and mod.changed[0] not in objs


def test_object_ids_stay_unique_over_a_change_sequence():
    from rag.rules.bench.runner import _apply
    rng, cur = random.Random(3), random_objects(ObjSpec(1, 5, 0), random.Random(0))
    for i in range(40):
        ch = object_changes(cur, rng, ("add", "remove", "remove")[i % 3] if len(cur) > 1 else "add")
        cur = _apply(cur, ch)
        assert len({o.id for o in cur}) == len(cur), i


def test_synth_pack_declares_questions_so_next_questions_has_work(tmp_path):
    from rag.rules.questions import next_questions
    cat = load_rule_pack(SPEC, tmp_path)
    s = evaluator_for(cat, "network").session(day=DAY, facts=random_facts(cat, SPEC, random.Random(0), missing=0.7),
                                               present=present_all(cat), evidence={})
    assert next_questions(cat, s)
