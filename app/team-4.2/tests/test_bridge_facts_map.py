from datetime import date, datetime



from rag.bridge.catalog import Slot
from rag.bridge.engine import CONFLICT, Fact
from rag.bridge.facts_map import build_factset, contract_facts, normalize_slot
from rag.contracts.graph.oplog import machine_op

AT = datetime(2026, 11, 14, 9, 0)


def cand(value, uid="p0.d1"):
    return {"value": value, "unit": uid, "quote": value}


FACTS = {"candidates": {
    "labor_kind": [cand("Xác định thời hạn")],
    "term": [cand("12 tháng (từ 02/01/2025 đến 01/01/2026)")],
    # chuỗi có cả lương và phụ cấp: LLM chỉ rõ giá trị của trường bằng `norm` (spec 2026-11-23 typed value)
    "salary": [cand("15.000.000 đồng/tháng lương căn bản; phụ cấp 1.000.000 đồng/tháng", "p0.d2")
               | {"norm": {"amount": 15000000, "currency": "VND"}},
               cand("Lương căn bản 17.000.000 đồng/tháng; phụ cấp trách nhiệm 500.000 đồng/tháng", "p2.d1")
               | {"norm": {"amount": 17000000, "currency": "VND"}}],
    "probation_period": [cand("02 tháng")],
    "probation_salary": [cand("85% mức lương căn bản quy định tại Điều 2")],
    "job_level": [cand("Công việc cần trình độ cao đẳng trở lên")],
}}


def test_contract_facts_real_shape():
    f = contract_facts(FACTS, sign_date=date(2025, 1, 2))
    assert f["contract_kind"].value == "xac_dinh_thoi_han"
    assert (f["term_months"].value, f["term_months"].unit) == (12, "month")
    assert f["base_salary_vnd"] is CONFLICT
    assert f["has_probation"].value is True
    assert (f["probation_length"].value, f["probation_length"].unit) == (2, "month")
    assert (f["probation_pay_pct"].value, f["probation_pay_pct"].unit) == (85, "percent")
    assert f["job_level"].value == "cao_dang_tro_len"
    assert f["sign_date"].value == date(2025, 1, 2)
    assert f["contract_kind"].uid == "p0.d1"


AMEND = "Lương căn bản của Người lao động được điều chỉnh từ 15.000.000 đồng/tháng lên 17.000.000 đồng/tháng."


def test_appendix_amendment_supersedes_main_contract_value():
    # Lần chạy thật 14/11: 15 triệu (hợp đồng chính) và 17 triệu (Phụ lục 2 "điều chỉnh ... lên") báo là mâu thuẫn.
    facts = {"candidates": {"salary": [
        {"value": "15.000.000 đồng/tháng", "unit": "p0.d2", "quote": "Lương căn bản: 15.000.000 đồng/tháng"},
        {"value": "17.000.000 đồng/tháng", "unit": "p2.d1", "quote": AMEND}]}}
    f = contract_facts(facts, sign_date=None)["base_salary_vnd"]
    assert (f.value, f.unit, f.uid) == (17000000, "vnd", "p2.d1")
    assert f.amended_from == ({"value": 15000000, "unit": "vnd", "uid": "p0.d2"},)


def test_amendment_sentence_as_value_takes_new_amount():
    facts = {"candidates": {"salary": [cand("15.000.000 đồng/tháng", "p0.d2"), cand(AMEND, "p2.d1")]}}
    assert contract_facts(facts, sign_date=None)["base_salary_vnd"].value == 17000000


def test_same_part_or_no_amend_wording_stays_conflict():
    same = {"candidates": {"salary": [cand("15.000.000 đồng/tháng", "p0.d2"), cand("17.000.000 đồng/tháng", "p0.d5")]}}
    assert contract_facts(same, sign_date=None)["base_salary_vnd"] is CONFLICT
    back = {"candidates": {"salary": [cand(AMEND, "p0.d2"), cand("15.000.000 đồng/tháng", "p2.d1")]}}
    assert contract_facts(back, sign_date=None)["base_salary_vnd"] is CONFLICT   # phụ lục không nói sửa đổi


def test_salary_and_allowance_without_typed_value_is_not_guessed():
    """Trước đây lấy số tiền đầu tiên; nay hai số tiền khác nhau mà không có `norm` -> không đọc (UNKNOWN)."""
    facts = {"candidates": {"salary": [cand("15.000.000 đồng/tháng lương căn bản; phụ cấp 1.000.000 đồng/tháng")]}}
    assert "base_salary_vnd" not in contract_facts(facts, sign_date=None)


def test_contract_facts_single_salary_and_workdays():
    facts = {"candidates": {"salary": [cand("15.000.000 đồng/tháng")],
                            "probation_period": [cand("06 ngày làm việc")],
                            "labor_kind": [cand("Không xác định thời hạn")]}}
    f = contract_facts(facts, sign_date=None)
    assert (f["base_salary_vnd"].value, f["base_salary_vnd"].unit) == (15000000, "vnd")
    assert (f["probation_length"].value, f["probation_length"].unit) == (6, "workday")
    assert f["contract_kind"].value == "khong_xac_dinh_thoi_han"
    assert "sign_date" not in f and "job_level" not in f


def test_normalize_slot():
    assert normalize_slot(Slot("a", "duration", "day"), "08 ngày") == Fact(8, "day", "concept")
    assert normalize_slot(Slot("a", "duration", "hour"), "48 giờ/tuần") == Fact(48, "hour", "concept")
    assert normalize_slot(Slot("a", "duration", "day"), "tám ngày") is None
    assert normalize_slot(Slot("a", "percent", "percent"), "150% lương") == Fact(150.0, "percent", "concept")
    assert normalize_slot(Slot("a", "bool", None), "true") == Fact(True, None, "concept")
    assert normalize_slot(Slot("a", "bool", None), False) == Fact(False, None, "concept")
    assert normalize_slot(Slot("a", "bool", None), "có lẽ") is None
    assert normalize_slot(Slot("a", "enum", None, ("hang_thang", "khac")), "hang_thang") == Fact("hang_thang", None, "concept")
    assert normalize_slot(Slot("a", "enum", None, ("hang_thang",)), "hằng tháng") is None


def _op(concept, slots, uid="p0.d3", quote="q", status="auto_accepted", kind="concept"):
    content = ({"kind": kind, "concept_id": concept, "slots_raw": {}, "slots": slots, "catalog_version": "t",
                "found_by": "tagger"} if kind == "concept"
               else {"kind": kind, "concept_id": concept, "searched_uids": [uid], "catalog_version": "t"})
    op = machine_op("c1", "ASSERT", concept, content, "llm", status, source_uid=uid, quote=(quote,), at=AT)
    return op


def test_build_factset():
    ops = [_op("leave.annual", {"annual_leave": {"value": 12, "unit": "day"}}, "p0.d3", "12 ngày"),
           _op("leave.annual", {"annual_leave": {"value": 14, "unit": "day"}}, "p1.d1", "14 ngày"),
           _op("wage.night_pay", {"night_extra_pct": {"value": 30, "unit": "percent"}}, status="rejected"),
           _op("content.raise_policy", {}, kind="concept_absent")]
    fs = build_factset({"contract_kind": Fact("xac_dinh_thoi_han")}, ops)
    assert fs.facts["annual_leave"] is CONFLICT
    assert fs.facts["contract_kind"].value == "xac_dinh_thoi_han"
    assert fs.present == frozenset({"leave.annual"})
    assert [e["uid"] for e in fs.evidence["leave.annual"]] == ["p0.d3", "p1.d1"]
    assert fs.absent_checked == frozenset({"content.raise_policy"})
    assert "night_extra_pct" not in fs.facts


def test_build_factset_same_value_twice_is_not_conflict_and_slot_vs_contract_conflict():
    ops = [_op("leave.annual", {"annual_leave": {"value": 12, "unit": "day"}}, "p0.d3"),
           _op("leave.annual", {"annual_leave": {"value": 12, "unit": "day"}}, "p0.d4")]
    assert build_factset({}, ops).facts["annual_leave"] == Fact(12, "day", "concept", "p0.d3", "q")
    ops = [_op("probation.pay", {"probation_pay_pct": {"value": 70, "unit": "percent"}})]
    fs = build_factset({"probation_pay_pct": Fact(85, "percent")}, ops)
    assert fs.facts["probation_pay_pct"] is CONFLICT


def test_fact_ops_one_per_normalized_candidate():
    from rag.bridge.facts_map import fact_ops
    facts = {"candidates": {
        "salary": [{"value": "15.000.000 đồng/tháng", "unit": "p0.d2", "quote": "15.000.000 đồng/tháng"}],
        "probation_salary": [{"value": "85%", "unit": "p0.d6", "quote": "hưởng 85%"}],
        "term": [{"value": "không rõ", "unit": "p0.d1", "quote": "x"}],
        "labor_kind": [{"value": "Không xác định thời hạn", "quote": "không có unit"}]}}
    ops = fact_ops(facts, "c1", at=AT)
    got = {(o.content["name"], o.content["value"], o.content["unit"], o.source_uid) for o in ops}
    assert got == {("base_salary_vnd", 15000000, "vnd", "p0.d2"), ("probation_pay_pct", 85.0, "percent", "p0.d6")}
    assert all(o.op_type == "ASSERT" and o.content["kind"] == "fact" and o.status == "auto_accepted" for o in ops)
    assert [o.op_id for o in fact_ops(facts, "c1", at=AT)] == [o.op_id for o in ops]


def test_fact_ops_one_candidate_many_names():
    from rag.bridge.facts_map import fact_ops
    ops = fact_ops({"candidates": {"probation_period": [cand("02 tháng", "p0.d6")]}}, "c1", at=AT)
    assert {(o.content["name"], o.content["value"], o.content["unit"]) for o in ops} == {
        ("has_probation", True, None), ("probation_length", 2, "month")}


# ── V.9: đơn vị LLM ghi trong `norm` phải có trong câu trích ──
def _loan_ctx():
    from rag.rules.loader import load_packs
    return load_packs(["civil_loan"]).context


def test_duration_unit_must_be_named_in_quote():
    from rag.bridge.facts_map import read_quantity
    norm = {"parts": [{"n": 8, "unit": "month"}]}
    assert read_quantity("duration", "08", norm, unit="day", evidence="thử việc 08 ngày") is None
    assert read_quantity("duration", "08", norm, unit="day", evidence="thử việc 08 tháng") == (8, "month")
    two = {"parts": [{"n": 2, "unit": "year"}, {"n": 6, "unit": "month"}]}
    assert read_quantity("duration", "", two, unit="month", evidence="thời hạn 2 năm 6 tháng") == (30, "month")
    assert read_quantity("duration", "", two, unit="month", evidence="thời hạn 2 tuần 6 tháng") is None


def test_percent_period_must_be_named_in_quote_when_pack_declares_forms():
    from rag.bridge.facts_map import read_quantity
    ctx = _loan_ctx()
    norm = {"value": 2, "per": "month"}
    got = read_quantity("percent", "", norm, unit="percent_per_year", ctx=ctx, evidence="lãi suất 2%/năm")
    assert got is None                                               # LLM ghi /tháng cho câu "/năm"
    ok = read_quantity("percent", "", norm, unit="percent_per_year", ctx=ctx, evidence="lãi suất 2% mỗi tháng")
    assert ok == (2, "percent_per_month")
