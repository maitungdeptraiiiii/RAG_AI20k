from datetime import datetime, timezone

import pytest

from rag.bridge.catalog import CONTRACT_FACTS, USER_FACTS, load_catalog
from rag.bridge.view import format_value, law_entry, result_views
from rag.contracts.models import Contract, ContractUnit

CAT = load_catalog()
PID = "bo-luat:45/2019/QH14#d27.k2"


def _contract():
    units = [ContractUnit("p0.d2", "Điều 2", "Người lao động được nghỉ phép 08 ngày/năm.")]
    return Contract("c1", "hd.txt", False, datetime(2026, 11, 14, tzinfo=timezone.utc), units[0].text, units, 1)


def _result(concept_id="probation.cancel_no_notice", finding="hidden_right", **kw):
    base = {"concept_id": concept_id, "rule_id": "r1", "status": "UNKNOWN", "finding": finding, "legality": None,
            "employee_impact": None, "law_values": {}, "facts_used": {}, "missing_facts": [], "evidence": [],
            "reasons": []}
    return {**base, **kw}


@pytest.mark.parametrize("value, unit, text", [
    (150, "percent", "150%"), (30, "day", "30 ngày"), (14, "workday", "14 ngày làm việc"), (60, "minute", "60 phút"),
    (5000000, "vnd", "5.000.000 đồng"), (3, None, "3"), (8, "hour", "8 giờ"), (2, "month", "2 tháng")])
def test_format_value(value, unit, text):
    assert format_value(value, unit) == text


def test_fact_labels_cover_catalog():
    assert {n for n in set(USER_FACTS) | set(CONTRACT_FACTS) if CAT.fact_label(n) == n} == set()


def test_verdicts_cover_findings():
    findings = {"ok", "violation", "missing_content", "hidden_right", "possible_right", "needs_facts", "conflict"}
    assert all(CAT.verdict_label(f) != f for f in findings)


def test_view_for_hidden_right():
    provision = {"in_force": True, "citation": "Khoản 2 Điều 27 Bộ luật Lao động 2019", "text": "Trong thời gian thử việc…"}
    basis = {"probation.cancel_no_notice": {"anchors": [{"pid": PID, "role": "basis", "provision": provision}]}}
    [out] = result_views([_result()], CAT, _contract(), basis)
    v = out["view"]
    concept = CAT.concepts["probation.cancel_no_notice"]
    assert out["concept_id"] == "probation.cancel_no_notice"
    assert v["title"] == concept.label and v["meaning"] == concept.describe
    assert v["holder"] == "Người lao động"
    assert v["verdict"] == CAT.verdict_label("hidden_right")
    assert v["contract"] == []
    assert v["law"] == [{"pid": PID, "citation": provision["citation"], "text": provision["text"], "in_force": True,
                         "source_url": None, "valid_from": None, "valid_to": None, "note": None}]


def test_view_without_legal_graph():
    basis = {"probation.cancel_no_notice": {"anchors": [{"pid": PID, "role": "basis", "provision": None}]}}
    [out] = result_views([_result()], CAT, _contract(), basis)
    assert out["view"]["law"] == [{"pid": PID, "citation": None, "text": None, "in_force": None,
                                   "source_url": None, "valid_from": None, "valid_to": None, "note": None}]


def test_view_contract_quotes_and_law_values():
    r = _result("leave.annual", "needs_facts", evidence=[{"uid": "p0.d2", "quote": "được nghỉ phép 08 ngày/năm"}],
                law_values={"min_annual_leave": {"value": 12, "unit": "workday"}})
    [out] = result_views([r], CAT, _contract(), {})
    assert out["view"]["contract"] == [{"label": "Điều 2", "quote": "được nghỉ phép 08 ngày/năm"}]
    assert out["view"]["law_values"] == [{"key": "min_annual_leave", "text": "12 ngày làm việc"}]
    assert out["view"]["law"] == []


def test_missing_slot_and_fact_labels():
    concept = CAT.concepts["probation.cancel_no_notice"]
    slot = next(iter(concept.slots))
    r = _result(missing_facts=[slot, "pregnant"])
    [out] = result_views([r], CAT, _contract(), {})
    assert out["view"]["missing"] == [f"{concept.label} (nội dung trong hợp đồng)", CAT.fact_label("pregnant")]


def test_citation_from_legal_graph_dict():
    cite = {"label": "khoản 2 Điều 27", "doc_title": "Bộ Luật lao động số 45/2019/QH14", "provision_id": PID}
    basis = {"probation.cancel_no_notice": {"anchors": [{"pid": PID, "provision": {
        "in_force": True, "text": "2. Trong thời gian thử việc…", "citation": cite}}]}}
    [out] = result_views([_result()], CAT, _contract(), basis)
    assert out["view"]["law"][0]["citation"] == "Khoản 2 Điều 27 — Bộ Luật lao động số 45/2019/QH14"


def test_law_entry_carries_source_and_validity():
    cite = {"label": "điều 98", "doc_title": "Bộ luật Lao động", "source_url": "https://vbpl.vn/x",
            "valid_from": "2021-01-01", "valid_to": None}
    e = law_entry(PID, {"in_force": True, "text": "t", "citation": cite})
    assert (e["source_url"], e["valid_from"], e["valid_to"], e["note"]) == ("https://vbpl.vn/x", "2021-01-01", None, None)


def test_law_entry_explains_why_not_in_force():
    e = law_entry(PID, {"in_force": False, "reason": "no_longer_in_force", "until": "2025-07-01"})
    assert e["in_force"] is False and e["note"] == "Đã hết hiệu lực ở ngày áp luật (đến 2025-07-01)"
    e = law_entry(PID, {"in_force": None, "reason": "overlapping_versions", "provision_id": PID})
    assert e["in_force"] is None and "chồng nhau" in e["note"]
    e = law_entry(PID, {"in_force": False, "reason": "no_version_at_date"})
    assert "không có phiên bản" in e["note"]
