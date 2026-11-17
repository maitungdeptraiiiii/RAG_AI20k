"""Bảng dữ kiện đọc từ đồ thị hợp đồng, giá trị đang hiệu lực tại ngày soát (spec 2026-11-16 §5.5, §7)."""
from datetime import date, datetime, timezone
from pathlib import Path

from rag.bridge.engine import CONFLICT
from rag.bridge.facts_map import fact_ops
from rag.bridge.graph_facts import factset_from_graph
from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.oplog import OperationLog, machine_op
from rag.contracts.graph.view import MemoryGraphView

T = datetime(2026, 11, 16, tzinfo=timezone.utc)
SIGN = date(2025, 1, 2)
DEMO = Path(__file__).resolve().parents[3] / "data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt"


def salary(value, uid, quote=None):
    return {"value": value, "unit": uid, "quote": quote or value}


def view_for(text, salaries, extra_ops=()):
    log = OperationLog("c1")
    for o in fact_ops({"candidates": {"salary": salaries}}, "c1", at=T):
        log.add(o)
    for o in extra_ops:
        log.add(o)
    b, _ = build_graph("c1", [PageText(1, text)], log, file_checksum="x", built_at=T)
    assert b.problems == ()
    return MemoryGraphView(b)


def demo_view():
    return view_for(DEMO.read_text(encoding="utf-8"), [
        salary("15.000.000 đồng/tháng", "p0.d2"),
        salary("17.000.000 đồng/tháng", "p2.d1", "được điều chỉnh từ 15.000.000 đồng/tháng lên 17.000.000 đồng/tháng")])


def test_salary_at_sign_date_is_original_with_later_amendment():
    fs, warnings = factset_from_graph(demo_view(), day=SIGN, sign_date=SIGN)
    f = fs.facts["base_salary_vnd"]
    assert (f.value, f.unit, f.uid) == (15000000, "vnd", "p0.d2") and f.amended_from == ()
    assert [(a["value"], a["uid"], a["valid_from"]) for a in f.later_amendments] == [(17000000, "p2.d1", "2025-07-01")]
    assert fs.facts["sign_date"].value == SIGN and warnings == []


def test_salary_after_effective_date_is_amended():
    fs, _ = factset_from_graph(demo_view(), day=date(2025, 8, 1), sign_date=SIGN)
    f = fs.facts["base_salary_vnd"]
    assert (f.value, f.uid) == (17000000, "p2.d1") and f.later_amendments == ()
    assert [(a["value"], a["uid"]) for a in f.amended_from] == [(15000000, "p0.d2")]


MAIN = "Điều 1. Lương\nLương 10.000.000 đồng.\nĐiều 2. Phụ cấp\nPhụ cấp 12.000.000 đồng.\n"


def test_unrelated_different_values_conflict():
    v = view_for(MAIN, [salary("10.000.000 đồng", "p0.d1"), salary("12.000.000 đồng", "p0.d2")])
    assert factset_from_graph(v, day=SIGN, sign_date=SIGN)[0].facts["base_salary_vnd"] is CONFLICT


def test_same_value_twice_is_one_fact():
    v = view_for(MAIN, [salary("10.000.000 đồng", "p0.d1"), salary("10.000.000 đồng", "p0.d2")])
    assert factset_from_graph(v, day=SIGN, sign_date=SIGN)[0].facts["base_salary_vnd"].value == 10000000


def appendix(n, verb_line, when=None):
    eff = f"\nNội dung trên có hiệu lực từ ngày {when}." if when else ""
    return f"PHỤ LỤC {n}\nĐiều 1. Nội dung\n{verb_line}{eff}\n"


def test_amend_without_date_applies_with_warning():
    v = view_for(MAIN + appendix(1, "Sửa đổi Điều 1 Hợp đồng lao động: lương lên 11.000.000 đồng."),
                 [salary("10.000.000 đồng", "p0.d1"), salary("11.000.000 đồng", "p1.d1")])
    fs, warnings = factset_from_graph(v, day=SIGN, sign_date=SIGN)
    assert fs.facts["base_salary_vnd"].value == 11000000
    assert any("không rõ ngày hiệu lực của sửa đổi" in w for w in warnings)


def test_two_amendments_pick_latest_in_force():
    text = (MAIN + appendix(1, "Sửa đổi Điều 1 Hợp đồng lao động: lương lên 11.000.000 đồng.", "01/03/2025")
            + appendix(2, "Sửa đổi Điều 1 Hợp đồng lao động: lương lên 13.000.000 đồng.", "01/09/2025"))
    v = view_for(text, [salary("10.000.000 đồng", "p0.d1"), salary("11.000.000 đồng", "p1.d1"),
                        salary("13.000.000 đồng", "p2.d1")])
    f = factset_from_graph(v, day=date(2025, 5, 1), sign_date=SIGN)[0].facts["base_salary_vnd"]
    assert f.value == 11000000 and [a["value"] for a in f.amended_from] == [10000000]
    assert [(a["value"], a["valid_from"]) for a in f.later_amendments] == [(13000000, "2025-09-01")]


def test_amendment_without_original_not_in_force_yet():
    v = view_for(MAIN + appendix(1, "Sửa đổi Điều 1 Hợp đồng lao động: lương lên 11.000.000 đồng.", "01/03/2025"),
                 [salary("11.000.000 đồng", "p1.d1")])
    fs, warnings = factset_from_graph(v, day=SIGN, sign_date=SIGN)
    assert "base_salary_vnd" not in fs.facts and any("base_salary_vnd" in w for w in warnings)


def test_no_facts():
    fs, warnings = factset_from_graph(view_for(MAIN, []), day=SIGN, sign_date=None)
    assert fs.facts == {} and fs.present == frozenset() and warnings == []


def test_concept_instances_feed_present_slots_and_absent():
    ops = [machine_op("c1", "ASSERT", "concept:leave.annual",
                      {"kind": "concept", "concept_id": "leave.annual", "found_by": "tag",
                       "slots": {"annual_leave": {"value": 12, "unit": "day"}}},
                      "llm", "auto_accepted", source_uid="p0.d2", quote=("Phụ cấp 12.000.000 đồng",), at=T),
           machine_op("c1", "ASSERT", "absent:x", {"kind": "concept_absent", "concept_id": "content.raise_policy"},
                      "llm", "auto_accepted", at=T),
           machine_op("c1", "ASSERT", "absent:y", {"kind": "concept_absent", "concept_id": "leave.annual"},
                      "llm", "auto_accepted", at=T)]
    fs, _ = factset_from_graph(view_for(MAIN, [], ops), day=SIGN, sign_date=SIGN)
    assert fs.present == frozenset({"leave.annual"})
    assert fs.facts["annual_leave"].value == 12 and fs.facts["annual_leave"].unit == "day"
    assert fs.evidence["leave.annual"][0]["uid"] == "p0.d2" and fs.evidence["leave.annual"][0]["op_id"]
    assert fs.absent_checked == frozenset({"content.raise_policy"})
