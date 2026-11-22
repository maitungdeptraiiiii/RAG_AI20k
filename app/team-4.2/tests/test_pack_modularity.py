"""Cắm gói mới như module (checklist D38–D41): những gì quanh engine phải đọc từ gói, không viết cứng lao động."""
import pytest

from rag.bridge.catalog import load_catalog
from rag.bridge.facts_map import normalize_slot
from rag.rules.loader import load_pack, load_packs
from rag.rules.model import CatalogError, Slot
from rules_synth import concept, rule, write_pack

LOAN = load_packs(["civil_loan"])
RATE = Slot("interest_rate", "percent", "percent_per_year")


# ── D38: đơn vị của slot theo gói ──
@pytest.mark.parametrize("raw,expected", [
    ("30%/năm", (30.0, "percent_per_year")), ("30% / năm", (30.0, "percent_per_year")),
    ("18% một năm", (18.0, "percent_per_year")), ("2%/tháng", (2.0, "percent_per_month")),
    ("1,5% mỗi tháng", (1.5, "percent_per_month")),
])
def test_percent_slot_reads_period_declared_by_pack(raw, expected):
    f = normalize_slot(RATE, raw, LOAN.context)
    assert (f.value, f.unit) == expected


def test_percent_without_period_is_not_guessed_for_a_per_period_slot():
    """'30%' không ghi kỳ: không được đoán là theo năm (lệch 12 lần nếu là theo tháng) -> không chuẩn hóa được."""
    assert normalize_slot(RATE, "30%", LOAN.context) is None


def test_loan_rule_sees_violation_end_to_end_from_slot_text():
    from datetime import date
    from rag.rules.evaluator import evaluator_for
    from rag.rules.semantics import Fact
    f = normalize_slot(RATE, "30%/năm", LOAN.context)
    s = evaluator_for(LOAN, "network").session(day=date(2025, 3, 1), facts={"interest_rate": f,
                                                                             "special_law_applies": Fact(False)},
                                               present={"loan.interest_cap"}, evidence={})
    r = next(x for x in s.results() if (x.concept_id, x.rule_id) == ("loan.interest_cap", "r1"))
    assert (r.status, r.finding) == ("FAIL", "violation")
    monthly = normalize_slot(RATE, "2%/tháng", LOAN.context)                   # 24%/năm
    s.update({"interest_rate": monthly})
    assert next(x for x in s.results() if (x.concept_id, x.rule_id) == ("loan.interest_cap", "r1")).status == "FAIL"


def test_labor_percent_slots_unchanged():
    labor = load_catalog()
    slot = labor.concepts["wage.overtime_pay"].slots["ot_weekday_pct"]
    for ctx in (None, labor.context):
        f = normalize_slot(slot, "150%", ctx)
        assert (f.value, f.unit) == (150.0, "percent")


def test_loader_validates_unit_forms(tmp_path):
    write_pack(tmp_path, {"units": ["percent_per_year"], "unit_forms": {"percent_per_year": ["/năm"], "la": ["/x"]}},
               pack_id="uf")
    with pytest.raises(CatalogError) as e:
        load_pack("uf", root=tmp_path)
    assert any("'la'" in p for p in e.value.problems)
    write_pack(tmp_path, {"units": ["percent_per_year"], "unit_forms": {"percent_per_year": "/năm"}}, pack_id="uf2")
    with pytest.raises(CatalogError):
        load_pack("uf2", root=tmp_path)
