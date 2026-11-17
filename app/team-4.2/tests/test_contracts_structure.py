from rag.contracts.doc import PageText
from rag.contracts.structure import parse_contract, to_contract_units


def long_contract(n=60):
    return "\n".join(f"Điều {i}. Nội dung {i}\n1. Khoản một.\n2. Khoản hai." for i in range(1, n + 1))


def test_sixty_articles_nothing_dropped():
    doc = parse_contract([PageText(1, long_contract())])
    assert doc.report.counts == {"article": 60, "clause": 120, "point": 0}
    assert len(to_contract_units(doc)) == 60


def test_appendix_units_do_not_collide():
    text = "Điều 1. A\nx\nĐiều 2. B\ny\n\nPHỤ LỤC 1\nĐiều 1. Giá\nz\nĐiều 2. Lịch\nw"
    doc = parse_contract([PageText(None, text)])
    labels = [u.label for u in to_contract_units(doc)]
    assert labels == ["Điều 1", "Điều 2", "Phụ lục 1 — Điều 1", "Phụ lục 1 — Điều 2"]
    assert len({u.uid for u in doc.units}) == len(doc.units)


def test_report_warnings_gaps_and_thin_pages():
    pages = [PageText(i, "Điều %d. " % i + "chữ " * 300) for i in (1, 2)] + [PageText(3, "Điều 4. x")] \
            + [PageText(4, "Điều 5. " + "chữ " * 300)]
    r = parse_contract(pages).report
    assert r.warn_pages == [3]
    assert any("trang 3" in w.lower() for w in r.warnings) and any("Điều 4" in w for w in r.warnings)


def test_values_attached_to_leaf_units():
    doc = parse_contract([PageText(1, "Điều 3. Đặt cọc\n1. Tiền cọc 90 triệu đồng.\n2. Hoàn trả trong 30 ngày.")])
    assert [(v.uid, v.kind) for v in doc.values] == [("p0.d3.k1", "money"), ("p0.d3.k2", "duration")]
    assert doc.values[0].vid == "p0.d3.k1#v1"


def test_values_overlapping_pii_are_dropped():
    from rag.contracts.values import extract_values
    text = "Điều 1. Thanh toán\nChuyển vào số tài khoản 1234567890 đồng thời báo 30 ngày."
    assert any(v.raw.startswith("1234567890") for v in extract_values(text))
    doc = parse_contract([PageText(1, text)])
    assert [(v.vid, v.raw) for v in doc.values] == [("p0.d1#v1", "30 ngày")]


LEAD_IN = ("Điều 1. Đối tượng\nBên A cho bên B thuê nhà.\n"
           "Điều 2. Giá thuê là 10.000.000 đồng/tháng, theo Phụ lục 1 và khoản 1 Điều 1.\n"
           "1. Thanh toán trước ngày 5 hằng tháng, phạt 5%.\n2. Phạt chậm theo khoản 1 Điều này.\n"
           "Điều 3. Hiệu lực\n1. Có hiệu lực 12 tháng.\n\nPHỤ LỤC 01\nDanh mục tài sản kèm theo hợp đồng\n"
           "Điều 1. Tủ lạnh\n")


def test_article_lead_in_values_and_xrefs_are_kept():
    doc = parse_contract([PageText(1, LEAD_IN)])
    d2 = doc.unit("p0.d2")
    got = [(v.vid, v.raw) for v in doc.values if v.uid == "p0.d2"]
    assert got == [("p0.d2#v1", "10.000.000 đồng")]
    v = next(v for v in doc.values if v.uid == "p0.d2")
    assert d2.text[v.start:v.end] == v.raw
    assert [(v.vid, v.raw) for v in doc.values if v.uid == "p0.d2.k1"] == [("p0.d2.k1#v1", "5%")]
    refs = {(x.from_uid, x.raw, x.to_uid) for x in doc.xrefs}
    assert ("p0.d2", "Phụ lục 1", "p1.pre") in refs
    assert ("p0.d2", "khoản 1 Điều 1", None) in refs or ("p0.d2", "Điều 1", "p0.d1") in refs
    assert ("p0.d2.k2", "khoản 1 Điều này", "p0.d2.k1") in refs
    # khoản của điều không bị quét hai lần qua điều cha
    assert not any(x.from_uid == "p0.d2" and "Điều này" in x.raw for x in doc.xrefs)


def test_many_thin_pages_collapse_into_one_warning():
    body = "Điều %d. " + "chữ " * 300
    pages = [PageText(i, body % i if i % 2 else "x") for i in range(1, 12)]
    r = parse_contract(pages).report
    assert r.warn_pages == [2, 4, 6, 8, 10]
    page_lines = [w for w in r.warnings if w.startswith("Trang")]
    assert page_lines == ["Trang 2, 4, 6, … có thể chứa nội dung chưa đọc được"]
