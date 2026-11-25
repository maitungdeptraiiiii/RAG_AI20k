"""Quy tắc liên hợp đồng giữa hai phiên bản: đúng ví dụ bổ sung hợp đồng bị sót (hồ sơ mẫu b4)."""
from datetime import date

from rag.contracts.doc import PageText
from rag.contracts.dossier import bundle, load_dossier
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units
from rag.contracts.version_cross import cross_check

from tests.test_dossier_objects import HERE, fake_facts
from tests.versions_helpers import AT


def contracts():
    d = load_dossier(HERE / "b4" / "dossier.yaml")
    facts = fake_facts(d)
    out = {}
    for x in d.documents:
        pages = [PageText(1, (d.root / x.file).read_text(encoding="utf-8"))]
        doc = parse_contract(pages)
        units = to_contract_units(doc)
        out[x.doc_id] = Contract(x.doc_id, x.file, False, AT, pages[0].text, units, len(units), doc=doc,
                                 page_texts=pages, facts={**facts[x.doc_id], "document_kind": x.kind})
    return d, out


def test_adding_the_missed_contract_changes_exactly_two_conclusions():
    d, c = contracts()
    base = [c["hd1_2022"], c["hd2_2023"]]
    out = cross_check(base, [*base, c["hd_sot_2023"]], day=date(2023, 6, 1), continuous_employment=True,
                      user_facts=dict(d.user_facts))
    assert out["supported"] and out["note"] is None and out["day"] == "2023-06-01"
    got = {x["key"]: (x["before"]["status"], x["after"]["status"]) for x in out["compare"]["changed"]}
    assert got == {"content.term/r6@employee=party1": ("FAIL", "PASS"),
                   "content.term/r5@employee=party1": ("PASS", "FAIL")}
    assert out["recomputed"] == 3 and out["total"] == 55
    assert all(r["object"] for r in out["results"])


def test_kind_without_cross_rules_says_so():
    d, c = contracts()
    lease = [c["hd1_2022"], c["hd2_2023"]]
    for x in lease:
        x.facts["document_kind"] = "lease_contract"
    out = cross_check(lease[:1], lease, day=date(2023, 6, 1), continuous_employment=None, user_facts={})
    assert out["supported"] is False and out["results"] == [] and "Không có quy tắc liên văn bản" in out["note"]
