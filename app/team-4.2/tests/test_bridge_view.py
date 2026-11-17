from datetime import datetime, timezone

import pytest

from rag.bridge.catalog import CONTRACT_FACTS, USER_FACTS, load_catalog
from rag.bridge.view import FACT_LABELS, VERDICTS, format_value, result_views
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
    assert set(FACT_LABELS) >= set(USER_FACTS) | set(CONTRACT_FACTS)


def test_verdicts_cover_findings():
    assert set(VERDICTS) == {"ok", "violation", "missing_content", "hidden_right", "possible_right", "needs_facts",
                             "conflict"}


def test_view_for_hidden_right():
    provision = {"in_force": True, "citation": "Khoản 2 Điều 27 Bộ luật Lao động 2019", "text": "Trong thời gian thử việc…"}
    basis = {"probation.cancel_no_notice": {"anchors": [{"pid": PID, "role": "basis", "provision": provision}]}}
    [out] = result_views([_result()], CAT, _contract(), basis)
    v = out["view"]
    concept = CAT.concepts["probation.cancel_no_notice"]
    assert out["concept_id"] == "probation.cancel_no_notice"
    assert v["title"] == concept.label and v["meaning"] == concept.describe
    assert v["holder"] == "Người lao động"
    assert v["verdict"] == VERDICTS["hidden_right"]
    assert v["contract"] == []
    assert v["law"] == [{"pid": PID, "citation": provision["citation"], "text": provision["text"], "in_force": True}]


def test_view_without_legal_graph():
    basis = {"probation.cancel_no_notice": {"anchors": [{"pid": PID, "role": "basis", "provision": None}]}}
    [out] = result_views([_result()], CAT, _contract(), basis)
    assert out["view"]["law"] == [{"pid": PID, "citation": None, "text": None, "in_force": None}]


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
    assert out["view"]["missing"] == [f"{concept.label} (nội dung trong hợp đồng)", FACT_LABELS["pregnant"]]


def test_citation_from_legal_graph_dict():
    cite = {"label": "khoản 2 Điều 27", "doc_title": "Bộ Luật lao động số 45/2019/QH14", "provision_id": PID}
    basis = {"probation.cancel_no_notice": {"anchors": [{"pid": PID, "provision": {
        "in_force": True, "text": "2. Trong thời gian thử việc…", "citation": cite}}]}}
    [out] = result_views([_result()], CAT, _contract(), basis)
    assert out["view"]["law"][0]["citation"] == "Khoản 2 Điều 27 — Bộ Luật lao động số 45/2019/QH14"
