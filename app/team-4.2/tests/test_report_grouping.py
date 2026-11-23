"""Trình bày báo cáo (hạn chế N.4, 3.9, 7.22): nhiều FAIL trên cùng một điều khoản được nhóm lại; PASS chỉ vì điều khoản có
mặt (rule không có phép kiểm) được đánh dấu để UI ẩn. `RuleResult` không đổi."""
from datetime import date

from rag.bridge.check import CheckReport, presence_only, report_json, report_markdown, shared_clauses
from rag.rules.loader import load_packs
from rag.rules.semantics import RuleResult

CAT = load_packs(["consumer"])


def res(cid, rid, status, finding, uid=None, reasons=()):
    ev = ({"uid": uid, "quote": "q"},) if uid else ()
    return RuleResult(cid, rid, status, finding, None, None, {}, {}, (), ev, tuple(reasons))


def test_shared_clauses_groups_fails_on_same_unit():
    rs = [res("civil.standard_terms_exemption", "r1", "FAIL", "violation", "u7"),
          res("consumer.liability_exclusion", "r1", "FAIL", "violation", "u7"),
          res("consumer.unilateral_change", "r1", "FAIL", "violation", "u9"),
          res("consumer.trader_interprets", "r1", "PASS", "ok", "u7")]
    assert shared_clauses(rs) == {"u7": ["civil.standard_terms_exemption/r1", "consumer.liability_exclusion/r1"]}


def test_report_json_and_markdown_show_shared_clause():
    rs = [res("civil.standard_terms_exemption", "r1", "FAIL", "violation", "u7"),
          res("consumer.liability_exclusion", "r1", "FAIL", "violation", "u7")]
    report = CheckReport("c1", date(2025, 1, 1), "v", rs, {})
    assert report_json(report)["shared_clauses"] == {"u7": ["civil.standard_terms_exemption/r1",
                                                           "consumer.liability_exclusion/r1"]}
    md = report_markdown(report, CAT)
    assert "Một điều khoản vi phạm nhiều quy định" in md and "[u7]" in md


def test_presence_only_marks_pass_without_check():
    no_check = next((c.id, r.id) for c in CAT.concepts.values() for r in c.rules
                    if r.check is None and r.mode != "prohibited" and r.over is None)
    with_check = next((c.id, r.id) for c in CAT.concepts.values() for r in c.rules if r.check is not None)
    rs = [res(*no_check, "PASS", "ok"), res(*with_check, "PASS", "ok"), res(*no_check, "FAIL", "missing_content")]
    assert presence_only(rs, CAT) == [f"{no_check[0]}/{no_check[1]}"]


def test_markdown_counts_presence_only_passes():
    no_check = next((c.id, r.id) for c in CAT.concepts.values() for r in c.rules
                    if r.check is None and r.mode != "prohibited" and r.over is None)
    report = CheckReport("c1", date(2025, 1, 1), "v", [res(*no_check, "PASS", "ok")], {},
                         stats={"presence_only": [f"{no_check[0]}/{no_check[1]}"]})
    assert "1 chỉ vì điều khoản có mặt" in report_markdown(report, CAT)
