from decimal import Decimal
from pathlib import Path

from rag.quality.numeric import NumericFactDraft, NumericNormalizationConfig, compare, parse_decimal, sum_matches
from rag.quality.pii import mask_cells
from rag.quality.tables import parse_csv


ROOT = Path(__file__).resolve().parents[3]
TABLES = ROOT / "data/team-4.2/fixtures/raw/tables"
DECIMAL_DOT = NumericNormalizationConfig(locale="fixture-decimal-dot", decimal_separator=".", group_separator=None)
UNKNOWN_LOCALE = NumericNormalizationConfig(locale="und", decimal_separator=None, group_separator=None)


def _fact(raw: str, *, unit: str | None = "VND", period: str | None = "2026-01", metric: str | None = "Nộp hồ sơ quá hạn"):
    return NumericFactDraft(raw, metric, unit, period, (("Vùng", "Bắc"),))


def test_csv_preserves_multiline_header_and_note():
    table = parse_csv(TABLES / "19_budget_valid_multiline_header.csv", header_rows=2)
    assert len(table.headers) == 2
    assert table.rows[0] == ("Nộp chậm", "triệu VND", "1", "1")
    assert table.notes == (("Ghi chú", "", "", "Kỳ 2026-Q1; số liệu đã xác minh"),)


def test_pii_is_masked_from_fixture_cells_without_safe_evidence_leak():
    table = parse_csv(TABLES / "22_contact_pii.csv")
    masked, findings = mask_cells(table.rows)
    flattened = "\n".join(cell for row in masked for cell in row)
    assert "nguyen.minh.an@example.test" not in flattened
    assert "0900000001" not in flattened
    assert "[EMAIL_1]" in flattened and "[PHONE_1]" in flattened
    assert [finding.code for finding in findings] == ["pii.detected", "pii.detected"]
    assert [finding.entity_type for finding in findings] == ["email", "phone"]


def test_equivalent_vnd_and_million_vnd_compare_equal():
    result = compare(_fact("1500000", unit="VND"), _fact("1.5", unit="triệu VND"), config=DECIMAL_DOT)
    assert result.relation == "equal"
    assert result.left_value == result.right_value == Decimal("1500000")


def test_period_and_ambiguous_locale_do_not_create_false_conflict():
    assert compare(_fact("1500000"), _fact("100", unit="triệu VND", period="2026-Q1"), config=DECIMAL_DOT).relation == "incomparable"
    assert parse_decimal("1,500.000", config=UNKNOWN_LOCALE) is None
    assert compare(_fact("1,500.000"), _fact("1500000"), config=UNKNOWN_LOCALE).relation == "invalid"


def test_sum_mismatch_is_arithmetic_finding_not_verification():
    parts = (_fact("100", unit="triệu VND", period="2026-Q1", metric="Tổng xử phạt"),
             _fact("50", unit="triệu VND", period="2026-Q1", metric="Tổng xử phạt"))
    result = sum_matches(parts, _fact("180", unit="triệu VND", period="2026-Q1", metric="Tổng xử phạt"), config=DECIMAL_DOT)
    assert result.relation == "different"
    assert result.reason == "arithmetic_only_not_verified"
