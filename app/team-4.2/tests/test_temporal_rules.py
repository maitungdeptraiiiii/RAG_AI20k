from datetime import date, datetime, timezone

from rag.temporal.rules import extract_rule_anchors, resolve_relative

ASKED = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)


def brief(anchors):
    return [(a.role, a.start, a.end, a.precision) for a in anchors]


def test_day_month_year_and_roles():
    q = "Tôi ký hợp đồng ngày 15/06/2023, thực hiện trong năm 2024 và tranh chấp năm 2025"
    anchors = extract_rule_anchors(q, asked_at=ASKED)
    assert brief(anchors) == [
        ("signing", date(2023, 6, 15), date(2023, 6, 15), "day"),
        ("performance", date(2024, 1, 1), date(2024, 12, 31), "year"),
        ("dispute", date(2025, 1, 1), date(2025, 12, 31), "year"),
    ]
    assert all(a.evidence and a.evidence in q and a.source == "question" for a in anchors)


def test_relative_expressions():
    assert resolve_relative("năm ngoái", ASKED) == (date(2025, 1, 1), date(2025, 12, 31), "year")
    assert resolve_relative("cuối năm ngoái", ASKED) == (date(2025, 10, 1), date(2025, 12, 31), "range")
    assert resolve_relative("tháng trước", ASKED) == (date(2026, 10, 1), date(2026, 10, 31), "month")
    assert resolve_relative("một hôm nào đó", ASKED) == (None, None, "relative_unresolved")
    (now,) = extract_rule_anchors("Bây giờ tôi muốn kiện thì sao?", asked_at=ASKED)
    assert (now.role, now.start, now.precision) == ("evaluation", date(2026, 11, 9), "day")
    (month,) = extract_rule_anchors("Tôi mua căn nhà này từ tháng 3/2023.", asked_at=ASKED)
    assert (month.start, month.end, month.precision) == (date(2023, 3, 1), date(2023, 3, 31), "month")
    (late,) = extract_rule_anchors("đến cuối năm ngoái mới phát hiện vi phạm", asked_at=ASKED)
    assert (late.role, late.start, late.end, late.relative_expression) == (
        "discovery", date(2025, 10, 1), date(2025, 12, 31), "cuối năm ngoái")


def test_vietnamese_long_date_and_range():
    (a,) = extract_rule_anchors("Thực hiện từ ngày 01 tháng 7 năm 2024 đến ngày 31/12/2024.", asked_at=ASKED)
    assert (a.role, a.start, a.end, a.precision) == ("performance", date(2024, 7, 1), date(2024, 12, 31), "range")


def test_invalid_date_skipped():
    assert extract_rule_anchors("Hợp đồng ký ngày 30/02/2024 có hiệu lực không?", asked_at=ASKED) == []


def test_no_dates():
    assert extract_rule_anchors("Điều khoản phạt vi phạm này có hợp pháp không?", asked_at=ASKED) == []


def test_law_number_is_not_a_date():
    assert extract_rule_anchors("Theo Luật Nhà ở số 27/2023/QH15 thì sao?", asked_at=ASKED) == []
