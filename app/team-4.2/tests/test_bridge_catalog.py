import copy
from pathlib import Path

import pytest
import yaml

from rag.bridge.catalog import CatalogError, load_catalog

RAW = Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "legal" / "raw"

BASE = {
    "version": "t",
    "law_values_valid_from": "2021-01-01",
    "roles": [{"id": "NLD", "label": "NLĐ"}, {"id": "NSDLD", "label": "NSDLĐ"}],
    "concepts": [{
        "id": "x.a", "label": "A", "scope": "core", "phase": "P0", "holder": "NLD", "counterparty": "NSDLD",
        "applies_to": ["NLD"], "describe": "d", "phrasing": ["a", "b", "c"],
        "slots": {"days": {"kind": "duration", "unit": "day"}},
        "anchors": [{"pid": "bo-luat:45/2019/QH14#d1", "role": "basis"}],
        "rules": [{"id": "r1", "mode": "threshold", "law": {"min_days": {"value": 3, "unit": "day"}},
                   "check": {"fact": "days", "op": "gte", "law": "min_days"}, "derogation": "floor",
                   "on_silence": "hidden_right", "outcome": {"legality": "illegal", "employee_impact": "unfavorable"}}],
    }],
}


def _broken(name):
    d = copy.deepcopy(BASE)
    c, r = d["concepts"][0], d["concepts"][0]["rules"][0]
    if name == "dup_id":
        d["concepts"].append(copy.deepcopy(c))
    elif name == "bad_role":
        c["holder"] = "XYZ"
    elif name == "bad_op":
        r["check"]["op"] = "geq"
    elif name == "missing_law":
        r["law"] = {}
    elif name == "unknown_fact":
        r["check"]["fact"] = "foo"
    elif name == "bad_mode":
        r["mode"] = "maybe"
    elif name == "bad_unit":
        c["slots"]["days"]["unit"] = "lightyear"
    elif name == "bad_not_about":
        c["not_about"] = [{"text": "t", "see": "x.khong_co"}]
    return d


def _write(tmp_path, data):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_real_catalog_loads():
    c = load_catalog()
    assert len(c.concepts) == 40
    assert c.concepts["leave.annual"].slots["annual_leave"].unit == "day"
    assert all(len(x.phrasing) >= 3 for x in c.concepts.values())
    assert list(c.concepts)[0] == "content.party_info"


def test_not_about_loads_and_points_to_known_concept():
    c = load_catalog()
    na = c.concepts["termination.employee_unilateral"].not_about
    assert any(x["see"] == "training.cost_repayment" for x in na)
    assert all(x["see"] in c.concepts for cc in c.concepts.values() for x in cc.not_about)
    assert c.concepts["leave.annual"].not_about == ()


def test_minimal_catalog_loads(tmp_path):
    c = load_catalog(_write(tmp_path, BASE))
    rule = c.concepts["x.a"].rules[0]
    assert rule.law == {"min_days": {"value": 3, "unit": "day"}} and rule.cases == ()


@pytest.mark.parametrize("name,needle", [
    ("dup_id", "trùng id"), ("bad_role", "role"), ("bad_op", "toán tử"), ("missing_law", "law"),
    ("unknown_fact", "dữ kiện"), ("bad_mode", "mode"), ("bad_unit", "đơn vị"),
    ("bad_not_about", "not_about")])
def test_broken_catalog_rejected(tmp_path, name, needle):
    with pytest.raises(CatalogError) as e:
        load_catalog(_write(tmp_path, _broken(name)))
    assert any(needle in p for p in e.value.problems), e.value.problems


def test_min_wage_values_match_decree_text():
    rule = load_catalog().concepts["wage.minimum_regional"].rules[0]
    periods = rule.law["min_wage"]["periods"]
    assert len(periods) == 3
    checked = 0
    for period in periods:
        number, year = period["source"].split(":")[1].split("/")[:2]
        files = sorted(RAW.glob(f"nghi-dinh_{number}_{year}_*/*.txt"))
        if not files:
            continue
        text = files[0].read_text(encoding="utf-8")
        for v in period["values"].values():
            assert f"{v:,}".replace(",", ".") in text, (period["source"], v)
        checked += 1
    if not checked:
        pytest.skip("kho luật chưa giải nén")
