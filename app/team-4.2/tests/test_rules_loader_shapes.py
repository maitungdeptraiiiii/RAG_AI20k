"""Bộ nạp: YAML sai hình dạng -> CatalogError có tên tệp, không phải AttributeError / TypeError (hạn chế 1.4); version của
pack.yaml vào Catalog.version (1.5); dữ kiện suy ra `value: null` (3.8) và `from` khác đơn vị đã khai (3.11)."""
from datetime import date

import pytest
import yaml

from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_pack, load_packs
from rag.rules.model import CatalogError
from rag.rules.semantics import Fact
from rules_synth import ROLES, concept, rule, write_pack

DAY = date(2025, 3, 1)
GOOD = [concept("x.a", [rule("r1")])]


def _concepts(root, pid, body):
    (root / pid / "concepts.yaml").write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")


def _body(concepts):
    return {"version": "c1", "law_values_valid_from": "2021-01-01", "roles": ROLES, "concepts": concepts}


@pytest.mark.parametrize("bad", [
    {"x.a": {}},                                                     # concepts là dict
    ["chuỗi"],                                                       # một concept là chuỗi
    [{**concept("x.a", [rule("r1")]), "slots": ["a", "b"]}],         # slots là list
    [{**concept("x.a", []), "rules": ["r1"]}],                       # rule là chuỗi
    [{**concept("x.a", []), "rules": {"id": "r1"}}],                 # rules là dict
    [{**concept("x.a", [rule("r1")]), "slots": {"s": "bool"}}],      # slot là chuỗi
])
def test_bad_concepts_shape_is_catalog_error(tmp_path, bad):
    pid = write_pack(tmp_path, {}, GOOD)
    _concepts(tmp_path, pid, _body(bad))
    with pytest.raises(CatalogError) as e:
        load_packs([pid], root=tmp_path)
    assert any("concepts.yaml" in p or "x.a" in p or "concepts" in p for p in e.value.problems), e.value.problems


def test_concepts_file_not_a_mapping(tmp_path):
    pid = write_pack(tmp_path, {}, GOOD)
    (tmp_path / pid / "concepts.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        load_packs([pid], root=tmp_path)


@pytest.mark.parametrize("bad", [{"units": {"day": 1}}, {"document_facts": "kind"}, {"silences": {"s": "x"}},
                                 {"conversions": ["day"]}, {"user_facts": "a"}, {"user_fact_questions": {"a": "b"}}])
def test_bad_pack_shape_is_catalog_error(tmp_path, bad):
    pid = write_pack(tmp_path, bad, GOOD)
    with pytest.raises(CatalogError):
        load_pack(pid, root=tmp_path)


def test_pack_file_not_a_mapping(tmp_path):
    pid = write_pack(tmp_path, {}, GOOD)
    (tmp_path / pid / "pack.yaml").write_text("- a\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        load_pack(pid, root=tmp_path)


def test_catalog_version_includes_pack_yaml_version(tmp_path):
    pid = write_pack(tmp_path, {"version": "p7"}, GOOD)
    assert load_packs([pid], root=tmp_path).version == f"{pid}@p7/t"


def test_derived_value_null_rejected(tmp_path):
    pack = {"user_facts": ["a"], "derived": [{"fact": "d", "definitions": [{"id": "x", "value": None}]}]}
    pid = write_pack(tmp_path, pack, GOOD)
    with pytest.raises(CatalogError) as e:
        load_pack(pid, root=tmp_path)
    assert any("value" in p and "null" in p for p in e.value.problems), e.value.problems


UNITS = {"units": ["day", "month", "money"], "conversions": {"day": {"base": "day", "factor": 1},
                                                             "month": {"base": "day", "factor": 30}}}


def test_derived_from_unit_not_convertible_rejected(tmp_path):
    pack = {**UNITS, "user_facts": ["amount"], "user_fact_units": {"amount": "money"},
            "derived": [{"fact": "d", "unit": "day", "definitions": [{"id": "x", "from": "amount"}]}]}
    pid = write_pack(tmp_path, pack, GOOD)
    with pytest.raises(CatalogError) as e:
        load_pack(pid, root=tmp_path)
    assert any("đơn vị" in p and "amount" in p for p in e.value.problems), e.value.problems


@pytest.mark.parametrize("kind", ["reference", "network"])
def test_derived_from_converts_to_declared_unit(tmp_path, kind):
    pack = {**UNITS, "user_facts": ["wait"], "user_fact_units": {"wait": "month"},
            "derived": [{"fact": "wait_d", "unit": "day", "definitions": [{"id": "x", "from": "wait"}]}]}
    c = concept("x.a", [rule("r1", check={"fact": "wait_d", "op": "lte", "value": 45, "unit": "day"})])
    pid = write_pack(tmp_path, pack, [c])
    cat = load_packs([pid], root=tmp_path)
    s = evaluator_for(cat, kind).session(day=DAY, facts={"wait": Fact(2, "month")}, present={"x.a"}, evidence={})
    r = s.results()[0]
    assert r.status == "FAIL" and r.facts_used["wait_d"] == {"value": 60, "unit": "day", "derived_by": "x"}


def test_labels_facts_must_name_known_facts(tmp_path):
    """Hạn chế R.8: `labels.facts` có khóa không phải dữ kiện nào của gói (gõ sai tên) -> CatalogError."""
    c = concept("x.a", [rule("r1")], slots={"s1": {"kind": "bool", "unit": None}})
    pid = write_pack(tmp_path, {"user_facts": ["u1"], "labels": {"facts": {"s1": "Slot", "u1": "Dữ kiện"}}}, [c])
    load_packs([pid], root=tmp_path)
    pid = write_pack(tmp_path, {"user_facts": ["u1"], "labels": {"facts": {"s1": "Slot", "u_typo": "Sai tên"}}}, [c],
                     pack_id="bad")
    with pytest.raises(CatalogError) as e:
        load_packs([pid], root=tmp_path)
    assert any("u_typo" in p for p in e.value.problems), e.value.problems


def test_real_packs_labels_name_known_facts():
    for pid in ("labor", "civil_loan", "civil_lease", "consumer", "commercial"):
        load_packs([pid])


def test_packs_for_kind_reads_pack_yaml_once_until_changed(tmp_path, monkeypatch):
    """Hạn chế R.8: chọn gói theo loại không đọc lại mọi pack.yaml mỗi lần; sửa tệp thì đọc lại."""
    import os
    import rag.rules.loader as loader
    pid = write_pack(tmp_path, {"document_kinds": ["k1"]}, GOOD)
    calls = []
    real = loader.load_pack
    monkeypatch.setattr(loader, "load_pack", lambda *a, **k: calls.append(a) or real(*a, **k))
    assert loader.packs_for_kind("k1", root=tmp_path) == [pid]
    assert loader.packs_for_kind("k1", root=tmp_path) == [pid] and len(calls) == 1
    path = tmp_path / pid / "pack.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("- k1", "- k2"), encoding="utf-8")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert loader.packs_for_kind("k1", root=tmp_path) == [] and loader.packs_for_kind("k2", root=tmp_path) == [pid]
