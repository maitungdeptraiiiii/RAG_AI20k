from datetime import date, datetime, timezone
from pathlib import Path

from rag.contracts.amendments import find_amendments
from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph, validate
from rag.contracts.graph.oplog import OperationLog
from rag.contracts.structure import parse_contract

T = datetime(2026, 11, 16, tzinfo=timezone.utc)
DEMO = Path(__file__).resolve().parents[3] / "data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt"


def demo_pages():
    return [PageText(1, DEMO.read_text(encoding="utf-8"))]


def test_demo_appendix2_amends_article2():
    b, _ = build_graph("c1", demo_pages(), OperationLog("c1"), file_checksum="x", built_at=T)
    am = [e for e in b.edges if e.type == "AMENDS"]
    assert len(am) == 1
    e = am[0]
    assert (e.src, e.dst) == ("c1:p2.d1@1", "c1:p0.d2@1")
    assert e.props["kind"] == "modify" and e.props["valid_from"] == "2025-07-01"
    assert "Sửa đổi Điều 2" in e.props["raw"]
    assert validate(b) == []


def test_find_amendments_on_doc():
    doc = parse_contract(demo_pages())
    assert [(a.src_uid, a.dst_uid, a.kind, a.valid_from) for a in find_amendments(doc)] == [
        ("p2.d1", "p0.d2", "modify", date(2025, 7, 1))]


SYN = ("Điều 1. Lương\nLương 10.000.000 đồng.\nĐiều 2. Phép\nNghỉ 12 ngày.\n"
       "PHỤ LỤC 1\nĐiều 1. Nội dung\n{body}\n")


def _amends(body):
    b, _ = build_graph("c1", [PageText(1, SYN.format(body=body))], OperationLog("c1"), file_checksum="x", built_at=T)
    return b, [e for e in b.edges if e.type == "AMENDS"]


def test_appendix_without_effective_date_gives_null_and_note():
    b, am = _amends("Sửa đổi Điều 1 Hợp đồng lao động: lương lên 12.000.000 đồng.")
    assert len(am) == 1 and am[0].props["valid_from"] is None
    assert any("không rõ ngày hiệu lực" in n for n in b.record()["notes"])


def test_supplement_kind():
    _, am = _amends("Bổ sung Điều 2 Hợp đồng lao động: thêm 2 ngày phép.")
    assert [e.props["kind"] for e in am] == ["supplement"]


def test_reference_without_amend_verb_is_not_amends():
    _, am = _amends("Căn cứ Điều 1 Hợp đồng lao động, hai bên cam kết.")
    assert am == []
