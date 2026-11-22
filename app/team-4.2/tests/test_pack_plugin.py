"""D41: một loại hợp đồng mới cắm vào chỉ bằng YAML (pack.yaml + concepts.yaml), chạy qua toàn bộ check_contract.

Gói `thue_thu` dưới đây là gói GIẢ dựng trong thư mục tạm (rule không phải luật thật): mục đích là chứng minh không cần
sửa file code nào để một loại hợp đồng mới có dữ kiện cấp hợp đồng, slot có đơn vị theo kỳ, vai trò các bên, prompt,
đồ thị và kết quả rule. Nếu test này hỏng sau một thay đổi, nghĩa là có chỗ lại viết cứng cho một miền."""
import json
from datetime import date, datetime, timezone

import pytest

from rag.bridge.check import check_contract, contract_view
from rag.contracts.doc import PageText
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units
from rag.rules.loader import load_packs
from rules_synth import write_pack

AT = datetime(2026, 11, 14, 9, 0)
TEXT = ("Bên A: ông Trần Văn B, là Bên cho thuê. Bên B: bà Lê Thị C, là Bên thuê. Ký ngày 02 tháng 01 năm 2025.\n"
        "Điều 1. Thời hạn thuê là 2 năm.\n"
        "Điều 2. Giá thuê được tăng tối đa 12%/năm.")
PACK = {
    "document_kinds": ["lease_trial"], "document_labels": {"lease_trial": "hợp đồng thuê thử"},
    "units": ["hour", "day", "month", "percent_per_year", "percent_per_month"],
    "conversions": {"hour": {"base": "hour", "factor": 1}, "day": {"base": "hour", "factor": 24},
                    "month": {"base": "hour", "factor": 720},
                    "percent_per_year": {"base": "percent_per_year", "factor": 1},
                    "percent_per_month": {"base": "percent_per_year", "factor": 12}},
    "unit_forms": {"percent_per_year": ["/năm", "một năm"], "percent_per_month": ["/tháng"]},
    "document_facts": {"lease_term_months": {"unit": "month", "from": "lease_term", "parse": "duration_to_unit"},
                       "sign_date": None},
    "extract_fields": [{"key": "lease_term", "label": "Thời hạn thuê", "kind": "text", "hint": "số tháng hoặc năm"}],
}
ROLES = [{"id": "CHO_THUE", "label": "Bên cho thuê"}, {"id": "THUE", "label": "Bên thuê"}]


def _concept(cid, rules, slots=None):
    return {"id": cid, "label": cid, "scope": "core", "phase": "P0", "holder": "THUE", "counterparty": "CHO_THUE",
            "applies_to": ["THUE"], "describe": "d", "phrasing": ["a", "b", "c"], "slots": slots or {},
            "anchors": [{"pid": "x:1/2025#d1", "role": "basis"}], "rules": rules}


CONCEPTS = {"version": "t", "law_values_valid_from": "2020-01-01", "roles": ROLES, "concepts": [
    _concept("thue.thoi_han", [{"id": "r1", "mode": "threshold", "derogation": "mandatory", "on_silence": "none",
                                "law": {"min_term": {"value": 6, "unit": "month"}},
                                "check": {"fact": "lease_term_months", "op": "gte", "law": "min_term"},
                                "outcome": {"legality": "illegal"}}]),
    _concept("thue.tang_gia", [{"id": "r1", "mode": "threshold", "derogation": "mandatory", "on_silence": "none",
                                "law": {"max_raise": {"value": 10, "unit": "percent_per_year"}},
                                "check": {"fact": "raise_rate", "op": "lte", "law": "max_raise"},
                                "outcome": {"legality": "illegal"}}],
             slots={"raise_rate": {"kind": "percent", "unit": "percent_per_year"}}),
]}


class LeaseLLM:
    def __init__(self):
        self.systems, self.wanted = [], []

    def complete(self, system, user):
        payload = json.loads(user)
        self.systems.append(system)
        if "fields_wanted" in payload:
            self.wanted.append({f["key"] for f in payload["fields_wanted"]})
            return json.dumps({"type": "Hợp đồng thuê",
                               "parties": [{"name": "B", "role": "Bên cho thuê", "unit": "p0.pre", "quote": "là Bên cho thuê"},
                                           {"name": "C", "role": "Bên thuê", "unit": "p0.pre", "quote": "là Bên thuê"}],
                               "sign_date": {"value": "2025-01-02", "unit": "p0.pre", "quote": "Ký ngày 02 tháng 01 năm 2025"},
                               "fields": {"lease_term": {"value": "2 năm", "unit": "p0.d1", "quote": "Thời hạn thuê là 2 năm"}}},
                              ensure_ascii=False)
        uids = [u["uid"] for u in payload.get("units") or []]
        items = []
        if "p0.d1" in uids:
            items.append({"concept": "thue.thoi_han", "uid": "p0.d1", "quote": "Thời hạn thuê là 2 năm"})
        if "p0.d2" in uids:
            items.append({"concept": "thue.tang_gia", "uid": "p0.d2", "quote": "Giá thuê được tăng tối đa 12%/năm",
                          "slots": {"raise_rate": "12%/năm"}})
        return json.dumps({"items": items}, ensure_ascii=False)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("plugin")
    write_pack(root, PACK, CONCEPTS, pack_id="thue_thu")
    catalog = load_packs(["thue_thu"], root=root)
    pages = [PageText(1, TEXT)]
    doc = parse_contract(pages)
    units = to_contract_units(doc)
    contract = Contract("c1", "thue.txt", False, datetime(2026, 11, 14, tzinfo=timezone.utc),
                        "\n".join(u.text for u in units), list(units), len(units), doc=doc, page_texts=list(pages),
                        file_checksum="x")
    llm = LeaseLLM()
    report = check_contract(llm, contract, at=AT, catalog=catalog)
    return llm, report, contract


def test_prompts_use_the_new_pack_label_and_ask_its_fields(run):
    llm, _report, _c = run
    assert llm.systems and not any("lao động" in s for s in llm.systems)
    assert any("hợp đồng thuê thử" in s for s in llm.systems)
    assert llm.wanted and all("lease_term" in w for w in llm.wanted)


def test_document_fact_and_period_slot_reach_the_rules(run):
    _llm, report, _c = run
    by = {r.concept_id: r for r in report.results}
    assert report.day == date(2025, 1, 2)
    term = by["thue.thoi_han"]
    assert (term.status, term.facts_used["lease_term_months"]) == ("PASS", {"value": 24, "unit": "month"})
    raise_ = by["thue.tang_gia"]
    assert (raise_.status, raise_.finding) == ("FAIL", "violation")
    assert raise_.facts_used["raise_rate"] == {"value": 12.0, "unit": "percent_per_year"}


def test_graph_has_pack_parties_and_holder_edges(run):
    _llm, _report, contract = run
    view, _, _, _ = contract_view(contract, None, AT)
    assert {p["role"] for p in view.find("Party")} == {"CHO_THUE", "THUE"}
    for ci in view.find("ConceptInstance"):
        holders = [h["node"]["role"] for h in view.neighbors(ci["node_id"], rel_types=["HOLDER"], direction="out")]
        assert holders == ["THUE"], ci["concept_id"]
