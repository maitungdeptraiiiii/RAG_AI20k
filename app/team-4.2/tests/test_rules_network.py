"""NetworkEvaluator: mạng điều kiện tăng dần phải cho kết quả giống hệt Reference (spec §2, §6, §10)."""
import json
import random
from dataclasses import asdict

import pytest

from rag.rules import semantics
from rag.rules.evaluator import ReferenceEvaluator, evaluator_for, make_evaluator
from rag.rules.loader import PACKS_ROOT, load_concepts, load_pack
from rag.rules.model import leaves
from rag.rules.semantics import CONFLICT, UNKNOWN, Fact
from rules_golden_cases import MISSING, _candidates, case_from_json, facts_from_spec, load_golden

CAT = load_concepts(PACKS_ROOT / "labor" / "concepts.yaml", load_pack("labor"))
REF, NET = ReferenceEvaluator(CAT), evaluator_for(CAT, "network")
CONCEPTS = list(CAT.concepts)
DAY = __import__("datetime").date(2025, 3, 1)


def _universe():
    """Tên dữ kiện -> các giá trị ứng viên, gộp từ mọi rule của catalog (cùng nguồn với golden)."""
    uni = {}
    for concept in CAT.concepts.values():
        for rule in concept.rules:
            for name, entries in _candidates(rule).items():
                bucket = uni.setdefault(name, [])
                bucket += [e for e in entries if e not in bucket]
    return uni


UNI = _universe()
NAMES = sorted(UNI)


def rand_fact(rng, name):
    entry = rng.choice(UNI[name] + ["UNKNOWN"])
    if entry == MISSING:
        return None
    if entry == "CONFLICT":
        return CONFLICT
    if entry == "UNKNOWN":
        return UNKNOWN
    return Fact(entry[0], entry[1] if len(entry) > 1 else None)


def rand_state(rng):
    facts = {n: f for n in NAMES if (f := rand_fact(rng, n)) is not None and rng.random() < 0.4}
    present = {c for c in CONCEPTS if rng.random() < 0.3}
    evidence = {c: [{"uid": f"p0.{c}", "quote": "q"}] for c in CONCEPTS if rng.random() < 0.1}
    return facts, present, evidence


def rand_update(rng):
    changes = {n: rand_fact(rng, n) for n in rng.sample(NAMES, rng.randint(0, 3))}
    kw = {}
    if rng.random() < 0.3:
        kw["present"] = {c for c in CONCEPTS if rng.random() < 0.3}
    if rng.random() < 0.2:
        kw["evidence"] = {c: [{"uid": f"p0.{c}", "quote": "q"}] for c in CONCEPTS if rng.random() < 0.1}
    return changes, kw


def diff_key(d):
    return [(c.concept_id, c.rule_id, c.before, c.after) for c in d.changes]


def sessions(facts=None, present=(), evidence=None):
    kw = dict(day=DAY, facts=dict(facts or {}), present=set(present), evidence=dict(evidence or {}))
    return REF.session(**kw), NET.session(**kw)


def test_network_session_results_equal_golden():
    bad = []
    for row in load_golden():
        case = case_from_json(row["case"])
        s = NET.session(day=case.day, facts=facts_from_spec(case.facts, semantics.Fact, semantics.CONFLICT),
                        present={case.concept_id} if case.present else set(), evidence={})
        got = next(r for r in s.results() if (r.concept_id, r.rule_id) == (case.concept_id, case.rule_id))
        if json.loads(json.dumps(asdict(got), ensure_ascii=False, sort_keys=True)) != row["result"]:
            bad.append(case.case_id)
    assert bad == [], bad[:5]


@pytest.mark.parametrize("seed", range(20))
def test_random_update_sequences_equal_reference(seed):
    rng = random.Random(seed)
    facts, present, evidence = rand_state(rng)
    ref, net = sessions(facts, present, evidence)
    assert net.results() == ref.results()
    for step in range(150):
        changes, kw = rand_update(rng)
        dr, dn = ref.update(changes, **kw), net.update(changes, **kw)
        assert net.results() == ref.results(), (seed, step)
        assert diff_key(dn) == diff_key(dr), (seed, step)


def test_shared_condition_is_one_node_and_updates_all_dependent_rules():
    leaf = {"fact": "contract_kind", "op": "eq", "value": "xac_dinh_thoi_han"}
    graph = NET.network.graph
    occurrences = sum(1 for c in CAT.concepts.values() for r in c.rules
                      for cond in [r.applicability, *[x.get("when") for x in r.cases]]
                      for lf in leaves(cond) if lf == leaf)
    assert occurrences >= 2 and graph.conds.count(leaf) == 1       # nhiều chỗ dùng, một node
    dependents = NET.network.rules_by_fact["contract_kind"]
    assert len(dependents) >= 2
    ref, net = sessions()
    change = {"contract_kind": Fact("xac_dinh_thoi_han")}
    assert diff_key(net.update(change)) == diff_key(ref.update(change))
    assert net.stats["rules_recomputed"] >= len(dependents)


def test_present_change_recomputes_only_that_concept():
    ref, net = sessions({"work_condition": Fact("binh_thuong")})
    dn, dr = net.update({}, present={"leave.annual"}), ref.update({}, present={"leave.annual"})
    assert net.stats["rules_recomputed"] == len(CAT.concepts["leave.annual"].rules)
    assert diff_key(dn) == diff_key(dr) and net.results() == ref.results()
    dn, dr = net.update({}, evidence={"leave.annual": [{"uid": "p0.d2", "quote": "q"}]}), \
        ref.update({}, evidence={"leave.annual": [{"uid": "p0.d2", "quote": "q"}]})
    assert net.stats["rules_recomputed"] == len(CAT.concepts["leave.annual"].rules)
    assert diff_key(dn) == diff_key(dr) and net.results() == ref.results()


def test_update_recomputes_fewer_rules_than_total():
    _ref, net = sessions({"work_condition": Fact("binh_thuong")}, {"leave.annual"})
    net.update({"annual_leave": Fact(8, "day")})
    total = sum(len(c.rules) for c in CAT.concepts.values())
    assert 1 <= net.stats["rules_recomputed"] < total
    assert net.stats["rules_recomputed"] == len(NET.network.rules_by_fact["annual_leave"])


def test_fork_is_independent_including_counters():
    ref, net = sessions({"work_condition": Fact("binh_thuong"), "contract_kind": Fact("xac_dinh_thoi_han")},
                        {"leave.annual"})
    fork = net.fork()
    fork.update({"contract_kind": Fact("khong_xac_dinh_thoi_han"), "annual_leave": Fact(8, "day")})
    assert net.results() == ref.results() and fork.results() != net.results()
    change = {"term_months": Fact(48, "month")}
    assert diff_key(net.update(change)) == diff_key(ref.update(change)) and net.results() == ref.results()


def test_removing_a_fact_never_creates_a_violation():
    rng = random.Random(99)
    checked = 0
    for _ in range(40):
        facts, present, evidence = rand_state(rng)
        _ref, net = sessions(facts, present, evidence)
        for name in list(facts):
            diff = net.fork().update({name: None})
            for c in diff.changes:
                assert not (c.after.finding == "violation" and c.before.finding != "violation"), (name, c)
            checked += 1
    assert checked > 100


def test_objects_not_supported_yet():
    _ref, net = sessions()
    with pytest.raises(NotImplementedError):
        net.update({}, objects=[object()])
    with pytest.raises(NotImplementedError):
        NET.session(day=DAY, facts={}, present=set(), evidence={}, objects=[object()])


def test_make_evaluator_network_runs():
    kw = dict(day=DAY, facts={"work_condition": Fact("binh_thuong")}, present={"leave.annual"}, evidence={})
    assert make_evaluator(["labor"], "network").session(**kw).results() == REF.session(**kw).results()


def _case_by_catalog(tmp_path):
    """Catalog tổng hợp: giá trị luật theo kỳ có khóa `by` khai ở cases[*].law (không ở law của rule)."""
    import yaml
    data = {"version": "t", "law_values_valid_from": "2021-01-01",
            "roles": [{"id": "NLD", "label": "NLĐ"}, {"id": "NSDLD", "label": "NSDLĐ"}],
            "concepts": [{
                "id": "x.a", "label": "A", "scope": "core", "phase": "P0", "holder": "NLD", "counterparty": "NSDLD",
                "applies_to": ["NLD"], "describe": "d", "phrasing": ["a", "b", "c"], "slots": {},
                "anchors": [{"pid": "bo-luat:45/2019/QH14#d1", "role": "basis"}],
                "rules": [{"id": "r1", "mode": "threshold", "derogation": "floor", "on_silence": "none",
                           "cases": [{"when": {"fact": "has_probation", "op": "eq", "value": True},
                                      "law": {"min_wage": {"by": "wage_region", "unit": "vnd", "periods": [
                                          {"valid_from": "2022-07-01", "values": {"I": 4680000, "IV": 3250000}}]}}}],
                           "check": {"fact": "base_salary_vnd", "op": "gte", "law": "min_wage"},
                           "outcome": {"legality": "illegal"}}]}]}
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return load_concepts(path, load_pack("labor"))


def test_case_level_by_fact_is_tracked(tmp_path):
    cat = _case_by_catalog(tmp_path)
    kw = dict(day=DAY, facts={"has_probation": Fact(True), "base_salary_vnd": Fact(4500000, "vnd"),
                              "wage_region": Fact("I")}, present={"x.a"}, evidence={})
    ref, net = ReferenceEvaluator(cat).session(**kw), evaluator_for(cat, "network").session(**kw)
    assert net.results() == ref.results() and net.results()[0].finding == "violation"       # 4.5tr < 4.68tr (vùng I)
    change = {"wage_region": Fact("IV")}                                                    # vùng IV: 3.25tr -> đạt
    assert diff_key(net.update(change)) == diff_key(ref.update(change))
    assert net.results() == ref.results() and net.results()[0].finding == "ok"
    assert "wage_region" in net.results()[0].facts_used


@pytest.mark.parametrize("old,new", [(1, True), (True, 1), (0, False), (1, 1.0)])
def test_update_value_of_other_type_but_equal_in_python_is_not_skipped(old, new):
    names = sorted({n for c in CAT.concepts.values() for r in c.rules for n in semantics.referenced(r)})
    for name in names:
        net = NET.session(day=DAY, facts={name: Fact(old)}, present=set(), evidence={})
        ref = REF.session(day=DAY, facts={name: Fact(old)}, present=set(), evidence={})
        net.update({name: Fact(new)}), ref.update({name: Fact(new)})
        assert net.results() == ref.results(), name
