"""Soát theo kỳ (D28): kết quả theo khoảng thời gian, ranh giới lấy từ ngày hiệu lực của đối tượng và kỳ giá trị luật."""
from datetime import date

import pytest

from rag.bridge.catalog import load_catalog
from rag.rules.evaluator import evaluator_for
from rag.rules.objects import WorkingObject
from rag.rules.semantics import Fact
from rag.rules.timeline import Period, periods, review_days, review_timeline

CAT = load_catalog()
CONTRACT = WorkingObject("h1", "Contract", {"kind": Fact("khong_xac_dinh_thoi_han")}, date(2023, 1, 1), None,
                         {"employee": "E1"})
TERM_EDIT = WorkingObject("p2", "Amendment", {"modifies_term": Fact(True)}, date(2024, 6, 1), None, {"contract": "h1"})


def test_review_days_include_object_dates_and_law_periods_inside_range():
    days = review_days(CAT, [CONTRACT, TERM_EDIT], date(2023, 1, 1), date(2025, 12, 31))
    assert days[0] == date(2023, 1, 1) and days == sorted(set(days))
    assert date(2024, 6, 1) in days                                  # phụ lục có hiệu lực
    assert date(2024, 7, 1) in days                                  # kỳ lương tối thiểu vùng (NĐ 74/2024)
    assert date(2026, 1, 1) not in days and date(2022, 7, 1) not in days   # ngoài khoảng soát
    ended = WorkingObject("h0", "Contract", {}, date(2023, 3, 1), date(2023, 8, 31), {})
    assert date(2023, 9, 1) in review_days(CAT, [ended], date(2023, 1, 1), date(2023, 12, 31))  # ngày sau valid_to


@pytest.mark.parametrize("kind", ["reference", "network"])
def test_a1_term_amendment_violation_starts_when_amendment_takes_effect(kind):
    days = review_days(CAT, [CONTRACT, TERM_EDIT], date(2023, 1, 1), date(2025, 12, 31))
    timeline = review_timeline(evaluator_for(CAT, kind), days=days, facts={}, present=set(), evidence={},
                               objects=[CONTRACT, TERM_EDIT])
    r7 = [p for p in periods(timeline, date(2025, 12, 31)) if (p.concept_id, p.rule_id) == ("content.term", "r7")]
    assert [(p.start, p.end, p.status) for p in r7] == [
        (date(2023, 1, 1), date(2024, 5, 31), "PASS"), (date(2024, 6, 1), date(2025, 12, 31), "FAIL")]
    assert all(p.object == "contract=h1" for p in r7)


def test_minimum_wage_changes_with_law_period():
    days = review_days(CAT, [], date(2024, 1, 1), date(2024, 12, 31))
    facts = {"wage_region": Fact("I"), "base_salary_vnd": Fact(4_800_000, "vnd")}
    timeline = review_timeline(evaluator_for(CAT, "network"), days=days, facts=facts,
                               present={"wage.minimum_regional"}, evidence={})
    wage = [p for p in periods(timeline, date(2024, 12, 31)) if p.concept_id == "wage.minimum_regional"]
    assert [(p.start, p.end, p.status) for p in wage] == [
        (date(2024, 1, 1), date(2024, 6, 30), "PASS"), (date(2024, 7, 1), date(2024, 12, 31), "FAIL")]
    assert isinstance(wage[0], Period)


def test_review_days_reject_inverted_range():
    with pytest.raises(ValueError):
        review_days(CAT, [], date(2025, 1, 1), date(2024, 1, 1))
