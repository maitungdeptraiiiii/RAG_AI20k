from datetime import date, datetime, timezone
from pathlib import Path

from rag.legal.keys import document_key
from rag.legal.models import Address, LegalDocument
from rag.legal.structure import index_provisions, parse_structure
from rag.legal.targets import law_name, locate, resolve_target_law

FIXTURES = Path(__file__).parent / "fixtures" / "legal"


def doc(doc_type, number, title, issued, consolidated=False):
    return LegalDocument(document_key(doc_type, number), "1", title, doc_type, number, "Quốc hội", issued,
                         None, None, None, consolidated, "x.txt", "0" * 64, datetime(2026, 1, 1, tzinfo=timezone.utc))


DOCS = [
    doc("Luật", "68/2014/QH13", "Luật Doanh nghiệp số 68/2014/QH13", date(2014, 11, 26)),
    doc("Luật", "59/2020/QH14", "Luật Doanh nghiệp số 59/2020/QH14", date(2020, 6, 17)),
    doc("Nghị quyết", "91/2015/QH13", "Nghị quyết số 91/2015/QH13 Về chương trình giám sát", date(2015, 6, 18)),
    doc("Bộ luật", "91/2015/QH13", "Bộ luật Dân sự số 91/2015/QH13", date(2015, 11, 24)),
    doc("Văn bản hợp nhất", "10/VBHN-VPQH", "Luật Doanh nghiệp", date(2022, 5, 1), consolidated=True),
]


def test_law_name_normalizes():
    assert law_name("Luật Doanh nghiệp số 59/2020/QH14") == "luật doanh nghiệp"
    assert law_name("Luật Nhà ở 2014") == "luật nhà ở"
    assert law_name("Bộ luật  Dân sự") == "bộ luật dân sự"


def test_resolve_latest_before_amendment():
    assert resolve_target_law("Luật Doanh nghiệp", None, before=date(2022, 1, 11), documents=DOCS) == ("luat:59/2020/QH14", ())
    assert resolve_target_law("Luật Doanh nghiệp", None, before=date(2018, 1, 1), documents=DOCS) == ("luat:68/2014/QH13", ())


def test_resolve_by_number_ignores_resolution_collision():
    assert resolve_target_law("Bộ luật Dân sự", "91/2015/QH13", before=date(2020, 1, 1), documents=DOCS) == ("bo-luat:91/2015/QH13", ())


def test_resolve_missing():
    assert resolve_target_law("Luật Đầu tư công", None, before=date(2022, 1, 1), documents=DOCS) == (None, ("operation.target_law_not_found",))


def test_resolve_number_name_mismatch():
    assert resolve_target_law("Luật Nhà ở", "59/2020/QH14", before=date(2022, 1, 1), documents=DOCS) == (None, ("operation.target_law_mismatch",))


def test_locate_parts():
    text = (FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8")
    idx = index_provisions(parse_structure(text, "luat:59/2020/QH14"))
    title = locate(idx, "luat:59/2020/QH14", Address("49", part="title"))
    assert title.kind == "article_title" and title.address.article == "49"
    lead = locate(idx, "luat:59/2020/QH14", Address("49", "1", part="lead_in"))
    assert lead.kind == "clause_lead_in" and lead.text.startswith("1. ")
    assert locate(idx, "luat:59/2020/QH14", Address("60", "2", "e")).kind == "point"
    assert locate(idx, "luat:59/2020/QH14", Address("999")) is None
