"""Golden: kết quả engine cũ trên các ca của rules_golden_cases phải giữ nguyên qua mọi lần tách lõi."""
from collections import Counter

from rag.bridge.catalog import load_catalog
from rag.bridge.engine import evaluate_concept
from rules_golden_cases import case_from_json, golden_cases, load_golden, run_case

CAT = load_catalog()


def _mismatches(evaluate_concept_fn):
    bad = []
    for row in load_golden():
        case = case_from_json(row["case"])
        if run_case(case, CAT, evaluate_concept_fn) != row["result"]:
            bad.append(case.case_id)
    return bad


def test_golden_has_every_rule_with_enough_cases():
    count = Counter((r["case"]["concept"], r["case"]["rule"]) for r in load_golden())
    assert [(c.id, r.id) for c in CAT.concepts.values() for r in c.rules if count[(c.id, r.id)] < 3] == []
    assert sum(count.values()) >= 500


def test_golden_via_bridge_api_unchanged():
    bad = _mismatches(evaluate_concept)
    assert bad == [], f"{len(bad)} ca lệch golden, 5 ca đầu: {bad[:5]}"


def test_golden_generation_is_deterministic():
    assert golden_cases(CAT) == golden_cases(CAT)
