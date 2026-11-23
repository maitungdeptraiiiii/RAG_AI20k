"""H1: dữ kiện theo đối tượng cho hồ sơ nhiều văn bản (rag.contracts.dossier).

Đầu vào: dossier.yaml + văn bản + kết quả bước trích (LLM) của từng bộ hợp đồng (ở đây là `extracted.yaml`, kết quả
GIẢ có câu trích nguyên văn). Đáp án: `objects.yaml` viết tay (tests/fixtures/rete/README.md §3)."""
from __future__ import annotations

import dataclasses
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
import yaml

from rag.contracts.dossier import Dossier, bundle, dossier_objects, load_dossier
from rag.contracts.llm_json import quote_ok
from rag.contracts.structure import to_contract_units

HERE = Path(__file__).parent / "fixtures" / "rete"
DOSSIERS = ["a1", "b1", "b2", "b3", "b4", "b5", "r1"]


def _yaml(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _day(v):
    return v if isinstance(v, date) or v is None else date.fromisoformat(str(v))


def fake_facts(d: Dossier) -> dict[str, dict]:
    """extracted.yaml -> {hợp đồng chính: contract.facts} như facts.py trả: candidates[trường] = [{value, unit=uid,
    quote, norm?}]; uid = đơn vị cấp cao nhất (Điều) của đúng văn bản (part) chứa câu trích, như LLM thấy trong
    `Contract.units` (to_contract_units)."""
    out = {}
    for main, fields in (_yaml(d.root / "extracted.yaml") or {}).items():
        units_all = to_contract_units(bundle(d, main))
        cands = {}
        for key, items in fields.items():
            for it in items:
                units = [u for u in units_all if u.uid.startswith(f"p{it['part']}.") and quote_ok(u.text, it["quote"])]
                assert len(units) == 1, (main, key, it, [u.uid for u in units])
                uid = units[0].uid
                cands.setdefault(key, []).append({k: v for k, v in {"value": it["value"], "unit": uid,
                                                                     "quote": it["quote"], "norm": it.get("norm")}.items()
                                                  if v is not None})
        out[main] = {"candidates": cands}
    return out


def table(objs) -> dict:
    return {o.id: (o.type, _day(o.valid_from), _day(o.valid_to), dict(o.refs),
                   {k: (f.value, f.unit) for k, f in o.attrs.items()}) for o in objs}


def expected(did: str) -> dict:
    return {o["id"]: (o["type"], _day(o.get("valid_from")), _day(o.get("valid_to")), dict(o.get("refs") or {}),
                      {k: (a["value"], a.get("unit")) for k, a in (o.get("attrs") or {}).items()})
            for o in _yaml(HERE / did / "objects.yaml") or []}


@pytest.mark.parametrize("did", DOSSIERS)
def test_load_dossier(did):
    d = load_dossier(HERE / did / "dossier.yaml")
    raw = _yaml(HERE / did / "dossier.yaml")
    assert d.dossier_id == did and d.review_date == _day(raw["review_date"])
    assert [x.doc_id for x in d.documents] == [x["doc_id"] for x in raw["documents"]]


@pytest.mark.parametrize("did", DOSSIERS)
def test_objects_match_hand_written_table(did):
    d = load_dossier(HERE / did / "dossier.yaml")
    assert table(dossier_objects(d, fake_facts(d))) == expected(did)


@pytest.mark.parametrize("did", DOSSIERS)
def test_every_attribute_quote_is_verbatim_in_its_document(did):
    d = load_dossier(HERE / did / "dossier.yaml")
    texts = {x.doc_id: (d.root / x.file).read_text(encoding="utf-8") for x in d.documents}
    for o in dossier_objects(d, fake_facts(d)):
        for name, f in o.attrs.items():
            if f.quote:
                assert quote_ok(texts[o.id], f.quote), (o.id, name, f.quote)


def test_gap_between_contracts_needs_declared_continuous_employment():
    """Văn bản không nói NLĐ có làm tiếp trong khoảng trống không: không khai -> không đoán (thuộc tính vắng)."""
    d = load_dossier(HERE / "b3" / "dossier.yaml")
    unknown = replace(d, parties=tuple(replace(p, continuous_employment=None) for p in d.parties))
    objs = {o.id: o for o in dossier_objects(unknown, fake_facts(d))}
    assert "worked_after_expiry_days" not in objs["hd1_2022"].attrs
    contiguous = load_dossier(HERE / "b5" / "dossier.yaml")       # hai HĐ nối liền: 0 ngày, chắc chắn, không cần khai
    b5 = replace(contiguous, parties=tuple(replace(p, continuous_employment=None) for p in contiguous.parties))
    assert {o.id: o for o in dossier_objects(b5, fake_facts(b5))}["hd1_2022"].attrs["worked_after_expiry_days"].value == 0


def test_appendix_details_not_found_are_unknown_not_false():
    """Không tìm thấy điều khoản sửa / ngày hiệu lực trong phụ lục: thuộc tính vắng (UNKNOWN), không phải false —
    false sẽ thành vi phạm giả của Đ22.2 khi bộ dò bỏ sót."""
    d = load_dossier(HERE / "a1" / "dossier.yaml")
    facts = fake_facts(d)
    from rag.contracts import dossier as mod
    real = mod.find_amendments
    try:
        mod.find_amendments = lambda doc: []
        objs = {o.id: o for o in dossier_objects(d, facts)}
    finally:
        mod.find_amendments = real
    pl = objs["hd_2023_pl2"].attrs
    assert "states_target_clause" not in pl and "modifies_term" not in pl
    assert pl["states_valid_from"].value is True          # ngày hiệu lực vẫn có từ bước trích (effective_date)


def test_typed_objects_come_from_pack_declaration_only():
    """Hồ sơ thuê nhà: gói civil_lease không khai object_types -> không có đối tượng (cùng code với lao động)."""
    d = load_dossier(HERE / "r1" / "dossier.yaml")
    assert dossier_objects(d, fake_facts(d)) == []


def test_amending_another_clause_of_the_same_article_is_not_a_term_change():
    """Thời hạn ở Khoản 2 Điều 1; phụ lục sửa Khoản 3 Điều 1 (chức danh) -> không sửa thời hạn. LLM chỉ thấy uid cấp
    Điều, nên phải xét câu trích của trường có nằm trong khoản bị sửa không."""
    from rag.contracts import dossier as mod
    d = load_dossier(HERE / "a1" / "dossier.yaml")
    facts = fake_facts(d)
    real = mod.find_amendments

    def shifted(doc):
        return [dataclasses.replace(a, dst_uid="p0.d1.k3") if a.dst_uid == "p0.d1.k2" else a for a in real(doc)]
    try:
        mod.find_amendments = shifted
        objs = {o.id: o for o in dossier_objects(d, facts)}
    finally:
        mod.find_amendments = real
    assert objs["hd_2023_pl2"].attrs["modifies_term"].value is False


def test_real_flow_extracts_each_contract_bundle_with_the_llm():
    """Luồng thật: extract_dossier_facts gọi facts.py cho từng bộ (hợp đồng + phụ lục); câu trích bịa bị bỏ."""
    import json

    from rag.contracts.dossier import extract_dossier_facts

    class LLM:
        def __init__(self):
            self.calls = 0

        def complete(self, system, user):
            self.calls += 1
            units = json.loads(user)["units"]
            u = next((x for x in units if "Loại hợp đồng" in x["text"]), None)
            fields = {} if u is None else {
                "labor_kind": {"value": "Hợp đồng lao động xác định thời hạn", "unit": u["uid"],
                               "quote": "Loại hợp đồng: Hợp đồng lao động xác định thời hạn"},
                "job_title": {"value": "Giám đốc", "unit": u["uid"], "quote": "Chức danh chuyên môn: Giám đốc"}}
            return json.dumps({"type": "Hợp đồng lao động", "parties": [], "fields": fields}, ensure_ascii=False)

    d = load_dossier(HERE / "b1" / "dossier.yaml")
    llm = LLM()
    facts = extract_dossier_facts(llm, d)
    assert set(facts) == {"hd1_2022", "hd2_2023", "hd3_2024"} and llm.calls >= 3
    objs = dossier_objects(d, facts)
    assert all(o.attrs["kind"].value == "xac_dinh_thoi_han" for o in objs)
    assert all("job" not in o.attrs for o in objs)                    # "Giám đốc" không có trong văn bản: bỏ
