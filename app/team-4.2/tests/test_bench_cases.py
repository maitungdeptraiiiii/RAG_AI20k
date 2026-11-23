"""K3: hồ sơ mẫu tests/fixtures/rete/* đọc thành ca eval (kế hoạch 2026-11-23-khanh-ingest-bench-eval, Task 2)."""
from rag.rules.bench.cases import FLAT_SUITES, load_cases, result_key
from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_packs


def test_every_fixture_dir_is_loaded_or_reported():
    cases, no_gold = load_cases()
    seen = {c.suite for c in cases} | set(no_gold)
    assert {"a1", "b1", "b2", "b3", "b4", "b5", "r1", "loan", "lease", "consumer", "commercial"} <= seen


def test_dossier_cases_cover_every_period_boundary():
    a1 = {c.day.isoformat() for c in load_cases()[0] if c.suite == "a1"}
    assert {"2024-06-30", "2024-07-01", "2024-08-31", "2024-09-01", "2026-01-01"} <= a1


def test_dossier_case_groups_labels_of_the_same_day():
    a1 = [c for c in load_cases()[0] if c.suite == "a1"]
    assert len({c.case_id for c in a1}) == len(a1)
    day = next(c for c in a1 if c.day.isoformat() == "2024-09-01")
    assert {e.rule for e in day.expected} >= {"wage.minimum_regional/r1", "content.term/r7"}
    assert day.objects and day.packs == ("labor",)


def test_flat_case_object_is_none_and_kind_from_suite():
    lease = [c for c in load_cases()[0] if c.suite == "lease"]
    assert lease and all(e.object is None for c in lease for e in c.expected)
    assert {c.document_kind for c in lease} == {"lease_contract"} and lease[0].packs == ("civil_lease",)


def test_flat_cases_match_existing_fixture_test_on_network():
    """Bộ đọc dựng đúng đầu vào: network trên Case cho đúng trạng thái gold như tests/test_rete_*_fixtures.py."""
    for c in [c for c in load_cases()[0] if c.suite in FLAT_SUITES]:
        got = {result_key(r): r.status for r in evaluator_for(load_packs(list(c.packs)), "network")
               .session(day=c.day, facts=c.facts, present=set(c.present), evidence={}).results()}
        assert all(got[e.rule] == e.status for e in c.expected), c.case_id


def test_dossier_cases_match_gold_on_reference():
    for c in [c for c in load_cases()[0] if c.suite not in FLAT_SUITES]:
        got = {result_key(r): r.status for r in evaluator_for(load_packs(list(c.packs)), "reference")
               .session(day=c.day, facts=c.facts, present=set(c.present), evidence={}, objects=c.objects).results()}
        for e in c.expected:
            k = e.rule + (f"@{e.object}" if e.object else "")
            assert got[k] == e.status, (c.case_id, k)
