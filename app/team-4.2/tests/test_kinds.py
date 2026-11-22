"""D35/B1 (spec bản 3 §5.5): danh sách `kind` là CHUNG cho mọi gói (src/rag/rules/packs/kinds.yaml, bộ nạp đọc).
Mọi khái niệm của ba miền có kind hoặc nằm trong `not_fitting` kèm lý do; kind chỉ dùng ở một miền ghi rõ miền đó."""
from pathlib import Path

import pytest
import yaml

from rag.rules.loader import PACKS_ROOT, CatalogError, load_pack, load_packs

ROOT = Path(__file__).resolve().parents[1]
SHARED = yaml.safe_load((PACKS_ROOT / "kinds.yaml").read_text(encoding="utf-8"))
DOMAINS = {"labor": "labor", "civil_general": "civil", "civil_loan": "loan", "civil_lease": "lease"}


def _concepts_by_domain():
    """concept -> miền của gói khai báo nó (gói con không tính khái niệm thừa kế từ gói cha)."""
    out = {}
    for pack, domain in DOMAINS.items():
        for cid in load_packs([pack]).concepts:
            out.setdefault(cid, domain)
    return out


def test_shared_kinds_are_seen_by_every_pack():
    for pack in DOMAINS:
        spec = load_pack(pack)
        for name, k in SHARED["kinds"].items():
            assert spec.concept_kinds.get(name) == tuple(k["slot_kinds"]), (pack, name)


def test_every_concept_of_three_domains_has_a_kind_or_a_reason():
    cat = load_packs(list(DOMAINS))
    not_fitting = {x["concept"]: x["why"] for x in SHARED["not_fitting"]}
    for cid, c in cat.concepts.items():
        assert (c.kind is None) == (cid in not_fitting), cid
        if c.kind is None:
            assert not_fitting[cid].strip(), cid
    assert set(not_fitting) <= set(cat.concepts)


def test_declared_domains_match_actual_use():
    cat, where = load_packs(list(DOMAINS)), _concepts_by_domain()
    used: dict[str, set[str]] = {}
    for cid, c in cat.concepts.items():
        if c.kind:
            used.setdefault(c.kind, set()).add(where[cid])
    for name, k in SHARED["kinds"].items():
        assert set(k["domains"]) == used.get(name, set()), (name, sorted(used.get(name, set())))
    assert sum(len(v) > 1 for v in used.values()) >= 3      # có kind dùng chung giữa các miền, không chỉ nhãn riêng


def test_a_pack_cannot_redefine_a_shared_kind(tmp_path):
    (tmp_path / "kinds.yaml").write_text("kinds:\n  rate_cap: {slot_kinds: [percent], domains: [x]}\nnot_fitting: []\n",
                                         encoding="utf-8")
    d = tmp_path / "p"
    d.mkdir()
    (d / "pack.yaml").write_text("id: p\nunits: []\nconcept_kinds:\n  rate_cap: {slot_kinds: [bool]}\n"
                                 "  own_kind: {slot_kinds: []}\n", encoding="utf-8")
    with pytest.raises(CatalogError) as e:
        load_pack("p", root=tmp_path)
    assert any("rate_cap" in p and "kinds.yaml" in p for p in e.value.problems)


def test_inventory_kinds_are_shared_kinds():
    for name in ("labor_w04.yaml", "civil_general.yaml", "civil_loan.yaml", "civil_lease.yaml"):
        for e in yaml.safe_load((ROOT / "docs" / "rule_inventory" / name).read_text(encoding="utf-8")):
            assert e["kind"] in set(SHARED["kinds"]) | {"none"}, (name, e["id"], e["kind"])
