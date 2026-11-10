"""W02-02h — kiểm tra số liệu: đơn vị, kỳ, tổng, locale, conflict, ngày; không báo nhầm trên file sạch."""

from decimal import Decimal
from pathlib import Path

import pytest

from rag.ingest.tables import load_tables, parse_csv
from rag.quality.numeric import CSV_MACHINE, VI_TEXT, NumericFactDraft, compare, normalize_unit, parse_decimal
from rag.quality.validate import (
    detect_conflicts,
    extract_facts,
    normalize_period,
    validate_dates,
    validate_table,
)

ROOT = Path(__file__).resolve().parents[3]
TABLES = ROOT / "data/team-4.2/fixtures/raw/tables"

EXPECTED = {   # theo data/team-4.2/fixtures/labels.jsonl (chỉ phần do validate phát hiện)
    "03_staff_valid.csv": [],
    "09_output_january_kg.csv": [],
    "10_output_january_ton.csv": [],
    "11_output_january_conflict.csv": ["numeric.conflict"],
    "12_penalty_february_vnd.csv": [],
    "13_penalty_ambiguous_locale.csv": ["numeric.invalid_locale"],
    "19_budget_valid_multiline_header.csv": [],
    "20_budget_sum_mismatch.csv": ["numeric.sum_mismatch"],
    "21_budget_missing_unit_period.csv": ["table.missing_unit", "table.missing_period"],
    "22_contact_pii.csv": [],
    "28_fee_schedule_pii.xlsx": [],
}


def test_fixture_tables_match_labels_in_ingest_order():
    existing = []
    for name, expected in EXPECTED.items():
        table = load_tables(TABLES / name, header_rows=2 if name.startswith("19") else 1)[0]
        facts = extract_facts(table)
        issues = validate_table(table) + detect_conflicts(facts, existing)
        existing += [(name, f) for f in facts]
        assert sorted(set(i.type for i in issues)) == sorted(expected), name


def test_issue_has_location_and_detector():
    table = parse_csv(TABLES / "20_budget_sum_mismatch.csv")
    (issue,) = validate_table(table)
    assert issue.location == "table:0/row:2/col:Giá trị" and issue.detector == "validate.v1"
    assert issue.severity == "error" and "không xác minh nguồn" in issue.detail


def test_sum_tolerance_and_units():
    assert normalize_unit("tỷ đồng") == Decimal("1000000000") and normalize_unit("Nghìn  VNĐ") == Decimal("1000")
    cfg = CSV_MACHINE.__class__("csv-machine", ".", None, tolerance=Decimal("1000000"))
    from rag.quality.numeric import sum_matches

    parts = (NumericFactDraft("100", "m", "triệu VND", "2026", ()), NumericFactDraft("50", "m", "triệu VND", "2026", ()))
    assert sum_matches(parts, NumericFactDraft("151", "m", "triệu VND", "2026", ()), config=cfg).relation == "equal"
    assert sum_matches(parts, NumericFactDraft("152", "m", "triệu VND", "2026", ()), config=cfg).relation == "different"


def test_vietnamese_number_format():
    assert parse_decimal("1.500", config=VI_TEXT) == Decimal("1500")
    assert parse_decimal("1,5", config=VI_TEXT) == Decimal("1.5")
    assert parse_decimal("1,500.000", config=VI_TEXT) is None           # mơ hồ -> không đoán
    left = NumericFactDraft("4.960.000", "lương vùng I", "đồng", "2026", ())
    right = NumericFactDraft("4.960", "lương vùng I", "nghìn đồng", "2026", ())
    assert compare(left, right, config=VI_TEXT).relation == "equal"


@pytest.mark.parametrize("raw, expected", [
    ("2026-Q1", "2026-Q1"), ("Quý I/2026", "2026-Q1"), ("2026-01", "2026-01"), ("tháng 1/2026", "2026-01"),
    ("2026", "2026"), ("2026-13", None), ("2026-Q5", None), ("quý 5/2026", None), ("abc", None),
])
def test_normalize_period(raw, expected):
    assert normalize_period(raw) == expected


def test_invalid_period_and_period_mismatch_with_title(tmp_path):
    path = tmp_path / "k.csv"
    path.write_text("Hành vi,Mức phạt,Đơn vị,Kỳ\nA,1,VND,2026-13\nB,2,VND,2025-Q4\nGhi chú,,,Kỳ 2026\n",
                    encoding="utf-8")
    types = [i.type for i in validate_table(parse_csv(path))]
    assert types == ["table.invalid_period", "table.invalid_period"]


def test_fee_table_from_legal_doc_unit_in_middle_header_and_no_period_column(tmp_path):
    """Như bảng OCR của w02-24: đơn vị ở tầng header giữa, không có cột Kỳ, có cột STT -> không issue."""
    path = tmp_path / "phi.csv"
    path.write_text(
        "Các khoản thu, mức thu theo NQ 17/2025,,,\n"
        "TT,Danh mục,Mức thu tối đa (nghìn đồng),Mức thu tối đa (nghìn đồng)\n"
        ",,Mầm non,Tiểu học\n"
        "1,Dịch vụ bán trú,25,30\n2,Nước uống,5,5\n", encoding="utf-8")
    table = parse_csv(path, header_rows=3)
    assert validate_table(table) == []
    assert {f.fact.unit for f in extract_facts(table) if "Mầm non" in f.location} == {"nghìn đồng"}


def test_type_mismatch_in_numeric_column(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text("Hành vi,Mức phạt,Đơn vị,Kỳ\nA,1000,VND,2026\nB,không rõ,VND,2026\n", encoding="utf-8")
    assert [i.type for i in validate_table(parse_csv(path))] == ["table.type_mismatch"]


def test_validate_dates():
    assert validate_dates(published_at="2026-01-01", effective_from="2026-01-15", effective_to="2026-07-01") == []
    assert [i.type for i in validate_dates(effective_from="2026-07-01", effective_to="2026-07-01")] == ["date.range_invalid"]
    assert [i.type for i in validate_dates(effective_from="01/07/2026")] == ["date.invalid"]
    (late,) = validate_dates(published_at="2026-03-01", effective_from="2026-01-01")
    assert late.severity == "warning"
