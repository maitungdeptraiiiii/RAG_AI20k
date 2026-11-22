"""ReferenceEvaluator (tính toàn bộ) cho kết quả giống hệt engine cũ trên toàn catalog."""
from dataclasses import asdict
from datetime import date

import pytest

from rag.bridge.catalog import load_catalog
from rag.bridge.engine import evaluate as old_evaluate
from rag.rules import semantics as new
from rag.rules.reference import evaluate_all
from rules_golden_cases import facts_from_spec

CAT = load_catalog()
DAY = date(2025, 3, 1)
SPECS = [{}, {"contract_kind": ["xac_dinh_thoi_han"], "term_months": [48, "month"]}]


@pytest.mark.parametrize("spec", SPECS)
def test_evaluate_all_matches_old_engine_on_whole_catalog(spec):
    present = {"content.term"}
    old = old_evaluate(CAT, facts_from_spec(spec), present, {}, DAY)
    got = evaluate_all(CAT, facts_from_spec(spec, new.Fact, new.CONFLICT), present, {}, DAY)
    assert [asdict(r) for r in got] == [asdict(r) for r in old]


def test_evaluate_all_count_and_order():
    res = evaluate_all(CAT, {}, set(), {}, DAY)
    assert len(res) == sum(len(c.rules) for c in CAT.concepts.values())
    assert [(r.concept_id, r.rule_id) for r in res] == [(c.id, r.id) for c in CAT.concepts.values() for r in c.rules]
