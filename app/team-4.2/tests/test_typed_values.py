"""Đọc giá trị số theo kiểu (spec 2026-11-23-typed-value-reading-design.md): LLM đọc ra dạng có kiểu, code cộng và quy
đổi, mỗi số phải có căn cứ trong câu trích (chữ số hoặc chữ). Không có căn cứ / mâu thuẫn -> không nhận (None), không
bao giờ sai im lặng."""
from datetime import date
from decimal import Decimal

import pytest

from rag.bridge.catalog import Slot, labor_context
from rag.bridge.engine import Fact
from rag.bridge.facts_map import contract_facts, normalize_slot
from rag.contracts.quantity import grounded, numbers_in, read_vi_number
from rag.rules.loader import load_packs

LOAN = load_packs(["civil_loan"]).context
LABOR = labor_context()


# ── bộ đọc số bằng chữ (ngữ pháp đóng) ──
@pytest.mark.parametrize("words,value", [
    ("hai mươi bốn", 24), ("ba mươi mốt", 31), ("mười lăm", 15), ("hai mươi lăm", 25), ("hai mươi tư", 24),
    ("một trăm triệu", 100_000_000), ("năm triệu", 5_000_000), ("một tỷ hai trăm triệu", 1_200_000_000),
    ("một nghìn không trăm linh năm", 1005), ("một trăm lẻ tám", 108), ("một triệu rưỡi", 1_500_000),
    ("mười", 10), ("không", 0), ("một phẩy năm", Decimal("1.5")), ("ba mươi", 30), ("bảy ngàn", 7000),
])
def test_read_vi_number(words, value):
    assert read_vi_number(words.split()) == value


@pytest.mark.parametrize("words", ["hai năm", "mươi", "trăm", "lẻ tám", "nghìn", "mốt", "tư", "lăm"])
def test_read_vi_number_rejects_non_numbers(words):
    assert read_vi_number(words.split()) is None


# ── căn cứ: số có trong câu trích dưới dạng chữ số hoặc chữ, cho phép nghìn / triệu / tỷ ──
@pytest.mark.parametrize("value,text", [
    (100_000_000, "100.000.000đ"), (100_000_000, "100 triệu đồng"), (100_000_000, "một trăm triệu đồng"),
    (5_000_000, "lương 5tr/tháng"), (24, "24 (hai mươi bốn) tháng"), (24, "hai mươi bốn tháng"),
    (Decimal("1.5"), "1,5 %/tháng"), (Decimal("1.5"), "một phẩy năm phần trăm"), (1000, "USD 1,000"),
    (2, "2 năm 6 tháng"), (6, "2 năm 6 tháng"), (12, "12 tháng (từ 02/01/2025 đến 01/01/2026)"),
])
def test_grounded(value, text):
    assert grounded(value, text)


@pytest.mark.parametrize("value,text", [(30, "2 năm 6 tháng"), (36, "24 (hai mươi bốn) tháng"), (13, "12 tháng"),
                                         (2_000_000, "1.000.000 đồng")])
def test_not_grounded(value, text):
    assert not grounded(value, text)


def test_numbers_in_reads_digit_and_word_forms():
    got = numbers_in("vay 100.000.000 (một trăm triệu) đồng trong 24 tháng")
    assert {100_000_000, 24} <= got


# ── slot: dạng có kiểu ──
MONTH = Slot("a", "duration", "month")


def typed(text, **norm):
    return {"text": text, "norm": norm}


def test_compound_duration_is_summed_by_code_not_first_unit():
    raw = typed("2 năm 6 tháng", parts=[{"n": 2, "unit": "year"}, {"n": 6, "unit": "month"}])
    assert normalize_slot(MONTH, raw, LOAN) == Fact(30, "month", "concept")


def test_compound_duration_as_plain_text_is_not_read_as_first_unit():
    """Trước đây '2 năm 6 tháng' -> 24 tháng (sai im lặng). Không có dạng có kiểu: hai thời hạn -> không đọc."""
    assert normalize_slot(MONTH, "2 năm 6 tháng", LOAN) is None


def test_llm_total_not_in_quote_is_rejected():
    """LLM tự cộng thành 30 (không có số 30 trong chữ): không nhận; code mới là nơi tính."""
    assert normalize_slot(MONTH, typed("2 năm 6 tháng", parts=[{"n": 30, "unit": "month"}]), LOAN) is None


@pytest.mark.parametrize("text,parts,expected", [
    ("24 (hai mươi bốn) tháng", [{"n": 24, "unit": "month"}], (24, "month")),
    ("hai mươi bốn tháng", [{"n": 24, "unit": "month"}], (24, "month")),
    ("ba mươi (30) ngày", [{"n": 30, "unit": "day"}], (30, "day")),
    ("một năm", [{"n": 1, "unit": "year"}], (12, "month")),
    ("30 ngày làm việc", [{"n": 30, "unit": "workday"}], (30, "workday")),
])
def test_written_forms_read_through_typed_value(text, parts, expected):
    f = normalize_slot(Slot("a", "duration", "day"), typed(text, parts=parts), LABOR)
    assert (f.value, f.unit) == expected


def test_typed_value_contradicting_deterministic_reading_is_rejected():
    """Chuỗi chỉ có một số, bộ đọc xác định ra 5.000.000 mà LLM nói 5.000 (có trong câu trích ở chỗ khác): mâu thuẫn."""
    slot = Slot("a", "money", "vnd")
    raw = typed("5.000.000 đồng", amount=5000, currency="VND")
    assert normalize_slot(slot, raw, LABOR, quote="Lương 5.000.000 đồng, thưởng 5.000 đồng") is None


@pytest.mark.parametrize("text,amount", [("một trăm triệu đồng", 100_000_000), ("5tr", 5_000_000),
                                         ("100.000.000đ", 100_000_000),
                                         ("100.000.000 (một trăm triệu) đồng", 100_000_000)])
def test_money_written_forms(text, amount):
    f = normalize_slot(Slot("a", "money", "vnd"), typed(text, amount=amount, currency="VND"), LABOR)
    assert (f.value, f.unit) == (amount, "vnd")


def test_percent_period_from_typed_value():
    rate = Slot("interest_rate", "percent", "percent_per_year")
    f = normalize_slot(rate, typed("một phẩy năm phần trăm một tháng", value=1.5, per="month"), LOAN)
    assert (f.value, f.unit) == (1.5, "percent_per_month")
    assert normalize_slot(rate, typed("30%", value=30, per=None), LOAN) is None     # không ghi kỳ: không đoán


@pytest.mark.parametrize("norm", [{"parts": []}, {"parts": [{"n": "x", "unit": "month"}]},
                                  {"parts": [{"n": 2, "unit": "fortnight"}]}, {}])
def test_malformed_typed_value_is_rejected(norm):
    assert normalize_slot(MONTH, {"text": "2 tháng", "norm": norm}, LOAN) is None


# ── dữ kiện cấp hợp đồng (facts.py candidates) ──
def test_contract_fact_uses_typed_value():
    facts = {"candidates": {"term": [{"value": "2 năm 6 tháng", "unit": "p0.d2", "quote": "Thời hạn vay 2 năm 6 tháng.",
                                      "norm": {"parts": [{"n": 2, "unit": "year"}, {"n": 6, "unit": "month"}]}}]}}
    f = contract_facts(facts, sign_date=date(2024, 1, 1), ctx=LOAN)["loan_term_months"]
    assert (f.value, f.unit) == (30, "month")


def test_contract_fact_plain_compound_is_not_guessed():
    facts = {"candidates": {"term": [{"value": "2 năm 6 tháng", "unit": "p0.d2", "quote": "2 năm 6 tháng"}]}}
    assert "loan_term_months" not in contract_facts(facts, sign_date=None, ctx=LOAN)
