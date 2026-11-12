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
