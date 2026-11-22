"""Nạp concepts.yaml theo gói: kiểm theo khai báo của gói, suy `unstated_false`, báo hết lỗi một lần."""
import copy
import dataclasses
from pathlib import Path

import pytest
import yaml

from rag.rules.loader import PACKS_ROOT, load_concepts, load_pack
from rag.rules.model import CORE_SILENCES, CatalogError

LABOR = load_pack("labor")
LABOR_CONCEPTS = PACKS_ROOT / "labor" / "concepts.yaml"
OUTCOME = {"legality": "illegal", "employee_impact": "unfavorable"}

BASE = {
    "version": "t",
    "law_values_valid_from": "2021-01-01",
    "roles": [{"id": "NLD", "label": "NLĐ"}, {"id": "NSDLD", "label": "NSDLĐ"}],
    "concepts": [{
        "id": "x.a", "label": "A", "scope": "core", "phase": "P0", "holder": "NLD", "counterparty": "NSDLD",
        "applies_to": ["NLD"], "describe": "d", "phrasing": ["a", "b", "c"],
        "slots": {"flag": {"kind": "bool", "unit": None}, "days": {"kind": "duration", "unit": "day"}},
        "anchors": [{"pid": "bo-luat:45/2019/QH14#d1", "role": "basis"}],
        "rules": [{"id": "r1", "mode": "prohibited", "derogation": "mandatory", "on_silence": "hidden_right",
                   "check": {"fact": "flag", "op": "eq", "value": False}, "outcome": OUTCOME}],
    }],
}


def _load(tmp_path, data, pack=LABOR):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return load_concepts(p, pack)


def _with_rule(**rule):
    d = copy.deepcopy(BASE)
    d["concepts"][0]["rules"][0].update(rule)
    return d


def test_real_labor_catalog_via_new_loader():
    c = load_concepts(LABOR_CONCEPTS, LABOR)
    assert len(c.concepts) == 39 and sum(len(x.rules) for x in c.concepts.values()) == 54
    assert c.context.units.convert(2, "month", "day") == 60


def test_unstated_false_inferred_on_known_rules():
    c = load_concepts(LABOR_CONCEPTS, LABOR)
    assert c.concepts["probation.once"].rules[0].unstated_false is True
    assert c.concepts["probation.pay"].rules[0].unstated_false is False


def test_unstated_false_inferred_explicit_override_and_mismatch(tmp_path):
    assert _load(tmp_path, BASE).concepts["x.a"].rules[0].unstated_false is True
    assert _load(tmp_path, _with_rule(unstated_false=False)).concepts["x.a"].rules[0].unstated_false is False
    bad = _with_rule(unstated_false=True, check={"fact": "days", "op": "gte", "value": 3, "unit": "day"})
    with pytest.raises(CatalogError) as e:
        _load(tmp_path, bad)
    assert any("unstated_false" in p for p in e.value.problems), e.value.problems


def test_on_silence_must_be_declared_by_pack(tmp_path):
    no_hidden = dataclasses.replace(LABOR, silences=dict(CORE_SILENCES))
    with pytest.raises(CatalogError) as e:
        _load(tmp_path, BASE, pack=no_hidden)
    assert any("on_silence" in p for p in e.value.problems), e.value.problems


def test_all_problems_reported_at_once(tmp_path):
    d = copy.deepcopy(BASE)
    c = d["concepts"][0]
    c["holder"] = "XYZ"
    c["slots"]["days"]["unit"] = "lightyear"
    c["rules"][0]["check"]["op"] = "geq"
    with pytest.raises(CatalogError) as e:
        _load(tmp_path, d)
    assert len(e.value.problems) >= 3, e.value.problems


def test_labor_concepts_yaml_moved_and_old_path_gone():
    from rag.bridge.catalog import DEFAULT_PATH
    assert DEFAULT_PATH.parts[-4:] == ("rules", "packs", "labor", "concepts.yaml")
    assert not (Path(__file__).resolve().parents[1] / "src" / "rag" / "bridge" / "concepts.yaml").exists()


def test_case_level_by_must_be_a_known_fact(tmp_path):
    d = copy.deepcopy(BASE)
    d["concepts"][0]["rules"][0] = {
        "id": "r1", "mode": "threshold", "derogation": "floor", "on_silence": "none",
        "cases": [{"when": {"fact": "flag", "op": "eq", "value": True},
                   "law": {"v": {"by": "khong_co", "unit": "day", "periods": [{"valid_from": "2022-01-01", "values": {"I": 1}}]}}}],
        "check": {"fact": "days", "op": "gte", "law": "v"}, "outcome": OUTCOME}
    with pytest.raises(CatalogError) as e:
        _load(tmp_path, d)
    assert any("khong_co" in p and "by" in p for p in e.value.problems), e.value.problems


def test_standalone_flag_must_be_bool_and_is_loaded(tmp_path):
    ok = _with_rule(standalone=True)
    assert _load(tmp_path, ok).concepts["x.a"].rules[0].standalone is True
    assert _load(tmp_path, BASE).concepts["x.a"].rules[0].standalone is False
    with pytest.raises(CatalogError) as e:
        _load(tmp_path, _with_rule(standalone="co"))
    assert any("standalone" in p for p in e.value.problems), e.value.problems
