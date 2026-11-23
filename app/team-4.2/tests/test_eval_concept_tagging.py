"""Chấm điểm của scripts/eval_concept_tagging.py (không gọi LLM)."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("eval_tag", Path(__file__).resolve().parents[1] / "scripts" / "eval_concept_tagging.py")
ev = importlib.util.module_from_spec(spec)
sys.modules["eval_tag"] = ev                   # @dataclass cần module đã đăng ký
spec.loader.exec_module(ev)

GOLD_DOC = {"slots": {"x.a": {"flag": [False, "q"]}, "x.b": {}}, "present_quotes": {"x.c": "q"}}


def test_score_counts_concepts_slots_rules_and_false_fails():
    found = {"x.a": {"flag": {"value": True, "unit": None}}, "x.b": {}, "x.z": {}}
    s = ev.score("d1", GOLD_DOC, {"x.a/r1": "PASS", "x.b/r1": "FAIL"}, found, {"x.c"},
                 {"x.a/r1": "FAIL", "x.b/r1": "FAIL", "x.z/r1": "FAIL"})
    assert (s.tp, len(s.gold_concepts), len(s.found)) == (2, 3, 3)
    assert (s.slots_ok, s.slots_total) == (0, 1) and "x.a.flag" in s.slot_errors[0]
    assert (s.rules_ok, s.rules_total) == (1, 2)
    assert s.false_fail == ["x.a/r1", "x.z/r1"] and s.missed_fail == []


def test_summarize_precision_recall():
    s = ev.score("d1", GOLD_DOC, {}, {"x.a": {"flag": {"value": False}}, "x.z": {}}, set(), {})
    out = ev.summarize([s])
    assert (out["concept_precision"], out["concept_recall"], out["slots"]) == (0.5, 0.333, "1/1")
