"""Golden: kết quả engine cũ trên các ca của rules_golden_cases phải giữ nguyên qua mọi lần tách lõi."""
from collections import Counter

from rag.bridge.catalog import load_catalog
from rag.bridge.engine import evaluate_concept
from rules_golden_cases import case_from_json, golden_cases, load_golden, run_case

CAT = load_catalog()


def _mismatches(evaluate_concept_fn, **kw):
    bad = []
    for row in load_golden():
        case = case_from_json(row["case"])
        if run_case(case, CAT, evaluate_concept_fn, **kw) != row["result"]:
            bad.append(case.case_id)
    return bad


# Rule thêm sau khi đóng băng golden (giai đoạn 3, Điều 20.2): có bảng ca riêng ở tests/fixtures/bridge/engine_cases.yaml
# và tests/test_rules_labor_term.py; golden không có (nó đóng băng kết quả của engine cũ).
POST_GOLDEN_RULES = {("content.term", r) for r in ("r3", "r3_state_director", "r3_elderly", "r3_foreign",
                                                   "r3_union_leader", "r4", "r5", "r6", "r7")} | {("probation.once", "r2"), ("appendix.states_change", "r1")}
# r5, r6, r7, probation.once/r2, appendix.states_change/r1 là rule xuyên đối tượng (giai đoạn 7): kiểm ở tests/test_rules_labor_objects.py.


def test_golden_has_every_rule_with_enough_cases():
    count = Counter((r["case"]["concept"], r["case"]["rule"]) for r in load_golden())
    in_catalog = {(c.id, r.id) for c in CAT.concepts.values() for r in c.rules}
    assert sorted(set(count) - in_catalog) == [], "rule trong golden không còn trong catalog"
    assert [k for k, n in count.items() if n < 3] == []
    assert in_catalog - set(count) == POST_GOLDEN_RULES
    assert sum(count.values()) >= 500


def test_golden_via_bridge_api_unchanged():
    bad = _mismatches(evaluate_concept)
    assert bad == [], f"{len(bad)} ca lệch golden, 5 ca đầu: {bad[:5]}"


def test_golden_generation_is_deterministic():
    assert golden_cases(CAT) == golden_cases(CAT)


def test_golden_via_rules_reference():
    from functools import partial

    from rag.rules import reference, semantics
    bad = _mismatches(partial(reference.evaluate_concept, ctx=CAT.context), fact_cls=semantics.Fact,
                      conflict=semantics.CONFLICT)
    assert bad == [], f"{len(bad)} ca lệch golden, 5 ca đầu: {bad[:5]}"
