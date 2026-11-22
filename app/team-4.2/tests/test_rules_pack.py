"""Gói luật (pack.yaml): khai báo đơn vị, dữ kiện cấp hợp đồng, finding; bộ nạp báo hết lỗi một lần."""
import pytest
import yaml

from rag.rules.loader import load_pack
from rag.rules.model import CORE_SILENCES, CatalogError, Silence


def test_labor_pack_declarations_match_legacy_constants():
    p = load_pack("labor")
    assert p.document_facts == {"contract_kind": None, "term_months": "month", "base_salary_vnd": "vnd",
                                "has_probation": None, "probation_length": "day", "probation_pay_pct": "percent",
                                "job_level": None, "sign_date": None}
    assert p.user_facts == frozenset({"work_condition", "pregnant", "pregnancy_month", "child_under_12_months",
                                      "employee_consent", "medical_certificate", "wage_region",
                                      "employee_is_female"})
    assert p.units.names == frozenset({"day", "workday", "week", "month", "hour", "minute", "percent", "vnd", "count"})
    assert p.silences["hidden_right"] == Silence(("PASS", "hidden_right"), ("UNKNOWN", "possible_right"))
    assert p.silences["none"] == CORE_SILENCES["none"]
    assert p.document_kinds == ("labor_contract",) and p.extends == ()
    assert p.context().reported == frozenset({"violation", "missing_content", "hidden_right", "possible_right"})


def test_units_convert_matches_legacy_table():
    u = load_pack("labor").units
    assert (u.convert(2, "month", "day"), u.convert(1, "week", "day"), u.convert(1, "day", "hour"),
            u.convert(48, "hour", "day")) == (60, 7, 24, 2)
    assert u.convert(3, "workday", "day") is None and u.convert(5, "percent", "percent") == 5
    assert u.convert(1, "minute", "hour") == 1 / 60
    assert u.convert(1, None, "day") is None


def _write_pack(root, data):
    (root / "bad").mkdir()
    (root / "bad" / "pack.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_pack_problems_reported_together(tmp_path):
    _write_pack(tmp_path, {
        "id": "bad", "version": "1", "extends": "labor",
        "units": ["day", "hour"],
        "conversions": {"day": {"base": "hour", "factor": 0}, "year": {"base": "hour", "factor": 8760}},
        "document_facts": {"x": "lightyear"},
        "silences": {"odd": {"applicable": ["PASS", "khong_khai_bao"], "unknown": ["UNKNOWN", "needs_facts"]}}})
    with pytest.raises(CatalogError) as e:
        load_pack("bad", root=tmp_path)
    text = "\n".join(e.value.problems)
    assert len(e.value.problems) >= 4, e.value.problems
    for needle in ("extends", "factor", "year", "lightyear", "khong_khai_bao"):
        assert needle in text, (needle, e.value.problems)


def test_unknown_pack_id_rejected(tmp_path):
    with pytest.raises(CatalogError) as e:
        load_pack("khong_co", root=tmp_path)
    assert "khong_co" in "\n".join(e.value.problems)
