"""Sự kiện stream `evaluation_diff` (spec §8, checklist D19)."""
from datetime import date

from rag.bridge.check import check_contract
from rag.rules.evaluator import Diff, RuleChange, evaluator_for
from rag.rules.events import diff_event
from rag.rules.semantics import Fact
from rag.bridge.catalog import load_catalog
from test_bridge_check import AT, ScriptLLM, contract


def test_diff_event_shape_and_json_safe():
    import json
    cat = load_catalog()
    s = evaluator_for(cat, "network").session(day=date(2025, 3, 1), facts={"contract_kind": Fact("xac_dinh_thoi_han")},
                                              present={"content.term"}, evidence={})
    diff = s.update({"worked_after_expiry_days": Fact(45, "day"), "new_contract_signed": Fact(False)})
    event = diff_event(diff, s.stats)
    assert event["type"] == "evaluation_diff" and event["stats"]["rules_recomputed"] >= 1
    change = next(c for c in event["changes"] if (c["concept_id"], c["rule_id"]) == ("content.term", "r4"))
    assert change["before"]["status"] == "UNKNOWN" and change["after"]["status"] == "FAIL"
    assert change["before"]["missing_facts"] == ["worked_after_expiry_days", "new_contract_signed"]
    assert json.loads(json.dumps(event))["changes"]
    assert diff_event(Diff(()), None) == {"type": "evaluation_diff", "changes": [], "stats": None}
    added = diff_event(Diff((RuleChange("c", "r", None, None),)))
    assert added["changes"] == [{"concept_id": "c", "rule_id": "r", "object": None, "before": None, "after": None}]


def test_check_contract_emits_evaluation_diff_only_after_recheck():
    events = []
    report = check_contract(ScriptLLM(), contract(), at=AT, on_event=events.append)
    diffs = [(i, e) for i, e in enumerate(events) if e["type"] == "evaluation_diff"]
    assert report.stats["recheck_concepts"] > 0 and len(diffs) == 1
    kinds = [e.get("stage") or e["type"] for e in events]
    index = diffs[0][0]
    assert events[index]["changes"] is not None
    assert "partial" in kinds[:index] and ("recheck" in kinds[:index])
