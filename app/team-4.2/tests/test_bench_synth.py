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
