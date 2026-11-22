"""Khai báo `derived` trong pack.yaml: nạp, kiểm vòng / trùng tên, gộp qua extends (spec §5.3)."""
import pytest

from rag.rules.loader import load_pack, load_packs
from rag.rules.model import CatalogError
from rules_synth import concept, rule, write_pack

KIND_EFF = {"fact": "kind_eff", "unit": None, "definitions": [
    {"id": "base", "from": "kind"},
    {"id": "x", "exception_of": "base", "when": {"fact": "a", "op": "eq", "value": 1}, "value": "k2",
     "anchors": [{"pid": "p#d1", "role": "basis"}]}]}
FACTS = {"document_facts": {"kind": None}, "user_facts": ["a"]}


def test_derived_loaded_from_pack_yaml(tmp_path):
    write_pack(tmp_path, {**FACTS, "derived": [KIND_EFF]})
    spec = load_pack("synth", root=tmp_path)
    base, exc = spec.derived["kind_eff"].definitions
    assert (base.id, base.from_fact, base.when, base.has_value, base.exception_of) == ("base", "kind", None, False, None)
    assert (exc.exception_of, exc.has_value, exc.value, exc.from_fact) == ("base", True, "k2", None)
    assert exc.when == {"fact": "a", "op": "eq", "value": 1} and exc.anchors == ({"pid": "p#d1", "role": "basis"},)
    assert spec.context().derived == spec.derived


def test_value_false_or_none_still_counts_as_a_value(tmp_path):
    write_pack(tmp_path, {**FACTS, "derived": [{"fact": "f", "definitions": [{"id": "d", "value": False}]}]})
    d = load_pack("synth", root=tmp_path).derived["f"].definitions[0]
    assert d.has_value is True and d.value is False


def test_derived_problems_reported_together(tmp_path):
    bad = {"fact": "bad", "unit": "lightyear", "definitions": [
        {"id": "d1", "value": 1}, {"id": "d1", "value": 2},                       # trùng id
        {"id": "d2", "exception_of": "khong_co", "value": 1},                     # đích không có
        {"id": "d3", "from": "kind", "value": 1},                                 # vừa from vừa value
        {"id": "d4"}]}                                                            # không from lẫn value
    clash = {"fact": "a", "definitions": [{"id": "c", "value": 1}]}               # trùng user_facts
    write_pack(tmp_path, {**FACTS, "derived": [bad, clash]})
    with pytest.raises(CatalogError) as e:
        load_pack("synth", root=tmp_path)
    text = "\n".join(e.value.problems)
    assert len(e.value.problems) >= 5, e.value.problems
    for needle in ("d1", "khong_co", "d3", "d4", "lightyear", "'a'"):
        assert needle in text, (needle, text)


def test_duplicate_derived_names_in_one_pack_rejected(tmp_path):
    d = {"fact": "f", "definitions": [{"id": "d", "value": 1}]}
    write_pack(tmp_path, {**FACTS, "derived": [d, d]})
    with pytest.raises(CatalogError) as e:
        load_pack("synth", root=tmp_path)
    assert any("trùng" in p and "'f'" in p for p in e.value.problems), e.value.problems


def test_derived_cycle_between_facts_rejected(tmp_path):
    a = {"fact": "fa", "definitions": [{"id": "d", "from": "fb"}]}
    b = {"fact": "fb", "definitions": [{"id": "d", "when": {"fact": "fa", "op": "eq", "value": 1}, "value": 2}]}
    write_pack(tmp_path, {**FACTS, "derived": [a, b]})
    with pytest.raises(CatalogError) as e:
        load_pack("synth", root=tmp_path)
    assert any("vòng" in p and "fa" in p and "fb" in p for p in e.value.problems), e.value.problems


def test_exception_of_cycle_inside_one_fact_rejected(tmp_path):
    d = {"fact": "f", "definitions": [{"id": "p", "exception_of": "q", "value": 1},
                                      {"id": "q", "exception_of": "p", "value": 2}]}
    write_pack(tmp_path, {**FACTS, "derived": [d]})
    with pytest.raises(CatalogError) as e:
        load_pack("synth", root=tmp_path)
    assert any("vòng" in p and "'f'" in p for p in e.value.problems), e.value.problems


def test_derived_merged_across_extends_and_duplicates_rejected(tmp_path):
    cha = write_pack(tmp_path, {**FACTS, "derived": [KIND_EFF]}, [concept("c.a", [rule("r1")])], pack_id="cha")
    con = {"fact": "kind_eff2", "definitions": [{"id": "b", "from": "kind_eff"}]}
    write_pack(tmp_path, {"extends": [cha], "derived": [con]}, [concept("c.b", [rule("r1")])], pack_id="con")
    cat = load_packs(["con"], root=tmp_path)
    assert set(cat.context.derived) == {"kind_eff", "kind_eff2"}
    write_pack(tmp_path, {"extends": [cha], "derived": [KIND_EFF]}, [concept("c.c", [rule("r1")])], pack_id="dup")
    with pytest.raises(CatalogError) as e:
        load_packs(["dup"], root=tmp_path)
    assert any("trùng" in p and "kind_eff" in p for p in e.value.problems), e.value.problems


def test_derived_names_checked_against_slots_and_known_facts_with_concepts(tmp_path):
    ok = concept("c.a", [rule("r1", applicability={"fact": "kind_eff", "op": "eq", "value": "k2"})])
    write_pack(tmp_path, {**FACTS, "derived": [KIND_EFF]}, [ok], pack_id="ok")
    assert "kind_eff" in load_packs(["ok"], root=tmp_path).context.derived          # rule được dùng tên suy ra

    clash = concept("c.a", [rule("r1")], slots={"kind_eff": {"kind": "enum", "unit": None, "options": ["x"]}})
    write_pack(tmp_path, {**FACTS, "derived": [KIND_EFF]}, [clash], pack_id="clash")
    with pytest.raises(CatalogError) as e:
        load_packs(["clash"], root=tmp_path)
    assert any("kind_eff" in p and "slot" in p for p in e.value.problems), e.value.problems

    unknown = {"fact": "u", "definitions": [{"id": "d", "when": {"fact": "khong_ai_khai", "op": "eq", "value": 1},
                                            "value": 1}]}
    write_pack(tmp_path, {**FACTS, "derived": [unknown]}, [concept("c.a", [rule("r1")])], pack_id="unk")
    with pytest.raises(CatalogError) as e:
        load_packs(["unk"], root=tmp_path)
    assert any("khong_ai_khai" in p for p in e.value.problems), e.value.problems
