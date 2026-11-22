"""Gộp nhiều gói: extends, trùng id, xung đột khai báo. Gói dựng trong tmp_path."""
import copy

import pytest
import yaml

from rag.bridge.catalog import load_catalog
from rag.rules.loader import load_packs
from rag.rules.model import CatalogError

ROLES = [{"id": "NLD", "label": "NLĐ"}, {"id": "NSDLD", "label": "NSDLĐ"}]


def mk_pack(root, pid, **kw):
    data = {"id": pid, "version": "1", "extends": [], "units": [], "conversions": {}, "user_facts": [],
            "document_facts": {}, "findings": [], "silences": {}}
    data.update(kw)
    (root / pid).mkdir(exist_ok=True)
    (root / pid / "pack.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def concept(cid, applicability_fact=None):
    rule = {"id": "r1", "mode": "threshold", "law": {"min_days": {"value": 3, "unit": "day"}},
            "check": {"fact": "days", "op": "gte", "law": "min_days"}, "derogation": "floor",
            "on_silence": "none", "outcome": {"legality": "illegal"}}
    if applicability_fact:
        rule["applicability"] = {"fact": applicability_fact, "op": "eq", "value": True}
    return {"id": cid, "label": cid, "scope": "core", "phase": "P0", "holder": "NLD", "counterparty": "NSDLD",
            "applies_to": ["NLD"], "describe": "d", "phrasing": ["a", "b", "c"],
            "slots": {"days": {"kind": "duration", "unit": "day"}},
            "anchors": [{"pid": "bo-luat:45/2019/QH14#d1", "role": "basis"}], "rules": [rule]}


def mk_concepts(root, pid, concepts, roles=ROLES, version="1", valid_from="2021-01-01"):
    data = {"version": version, "law_values_valid_from": valid_from, "roles": roles, "concepts": concepts}
    (root / pid / "concepts.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


DAY_HOUR = {"units": ["day", "hour"], "conversions": {"day": {"base": "hour", "factor": 24},
                                                      "hour": {"base": "hour", "factor": 1}}}


def test_child_sees_parent_declarations_and_parent_loads_first(tmp_path):
    mk_pack(tmp_path, "base", user_facts=["flag_x"], **DAY_HOUR)
    mk_concepts(tmp_path, "base", [concept("b.one")], version="b1")
    mk_pack(tmp_path, "kid", extends=["base"])
    mk_concepts(tmp_path, "kid", [concept("k.one", applicability_fact="flag_x")], version="k1")
    cat = load_packs(["kid"], root=tmp_path)
    assert list(cat.concepts) == ["b.one", "k.one"]
    assert cat.context.units.convert(1, "day", "hour") == 24
    assert cat.version == "base@b1+kid@k1"


def test_duplicate_concept_id_across_packs_rejected(tmp_path):
    mk_pack(tmp_path, "a", **DAY_HOUR)
    mk_concepts(tmp_path, "a", [concept("x.same")])
    mk_pack(tmp_path, "b", **DAY_HOUR)
    mk_concepts(tmp_path, "b", [concept("x.same")])
    with pytest.raises(CatalogError) as e:
        load_packs(["a", "b"], root=tmp_path)
    assert any("trùng id" in p and "x.same" in p for p in e.value.problems), e.value.problems


def test_extends_missing_and_cycle_rejected(tmp_path):
    mk_pack(tmp_path, "orphan", extends=["khong_co"])
    mk_pack(tmp_path, "p", extends=["q"])
    mk_pack(tmp_path, "q", extends=["p"])
    for ids in (["orphan"], ["p"]):
        with pytest.raises(CatalogError) as e:
            load_packs(ids, root=tmp_path)
        assert any("extends" in p for p in e.value.problems), e.value.problems


def test_conflicting_unit_factor_rejected(tmp_path):
    mk_pack(tmp_path, "a", **DAY_HOUR)
    mk_concepts(tmp_path, "a", [concept("a.one")])
    other = copy.deepcopy(DAY_HOUR)
    other["conversions"]["day"]["factor"] = 8
    mk_pack(tmp_path, "b", **other)
    mk_concepts(tmp_path, "b", [concept("b.one")])
    with pytest.raises(CatalogError) as e:
        load_packs(["a", "b"], root=tmp_path)
    assert any("conversions" in p and "day" in p for p in e.value.problems), e.value.problems


def test_identical_roles_merge_but_different_roles_rejected(tmp_path):
    mk_pack(tmp_path, "a", **DAY_HOUR)
    mk_concepts(tmp_path, "a", [concept("a.one")])
    mk_pack(tmp_path, "b", **DAY_HOUR)
    mk_concepts(tmp_path, "b", [concept("b.one")])
    assert list(load_packs(["a", "b"], root=tmp_path).concepts) == ["a.one", "b.one"]
    mk_concepts(tmp_path, "b", [concept("b.one")], roles=[ROLES[0], {"id": "NSDLD", "label": "khác"}])
    with pytest.raises(CatalogError) as e:
        load_packs(["a", "b"], root=tmp_path)
    assert any("role" in p and "NSDLD" in p for p in e.value.problems), e.value.problems


def test_load_packs_labor_only_equals_load_catalog():
    one, ref = load_packs(["labor"]), load_catalog()
    assert list(one.concepts) == list(ref.concepts) and one.version == ref.version
    assert one.law_values_valid_from == ref.law_values_valid_from
    assert one.context.units.convert(2, "month", "day") == 60
