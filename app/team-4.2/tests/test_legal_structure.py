from pathlib import Path

import pytest

from rag.legal.structure import index_provisions, parse_structure

FIXTURES = Path(__file__).parent / "fixtures" / "legal"
LAW = "luat:59/2020/QH14"
AMEND = "luat:03/2022/QH15"


@pytest.fixture(scope="module")
def law_text():
    return (FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def law(law_text):
    return parse_structure(law_text, LAW)


@pytest.fixture(scope="module")
def amend():
    return parse_structure((FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8"), AMEND)


def _children(provisions, parent_id, kind):
    return [p.address.point or p.address.clause for p in provisions if p.parent_id == parent_id and p.kind == kind]


def test_real_law_has_218_articles(law):
    assert sum(p.kind == "article" for p in law) == 218
    idx = index_provisions(law)
    assert idx[f"{LAW}#d60.title"].text == "Biên bản họp Hội đồng thành viên"


def test_clause_points_and_lead_in(law):
    idx = index_provisions(law)
    assert _children(law, f"{LAW}#d60.k2", "point") == ["a", "b", "c", "d", "đ", "e", "g"]
    assert idx[f"{LAW}#d60.k2.lead"].text.startswith("2. Biên bản họp Hội đồng thành viên phải thông qua")
    assert idx[f"{LAW}#d60.k3"].text.startswith("3. Trường hợp chủ tọa")
    assert f"{LAW}#d60.k3.lead" not in idx          # khoản không có điểm thì không có đoạn mở đầu riêng


def test_heading_path(law):
    idx = index_provisions(law)
    assert idx[f"{LAW}#d1"].heading_path[0].startswith("Chương I")


def test_suffix_units():
    ps = parse_structure("Điều 33a. Tên\n1. A\n5a. B\nb1) C", "luat:1/2020/QH14")
    idx = index_provisions(ps)
    assert "luat:1/2020/QH14#d33a" in idx and "luat:1/2020/QH14#d33a.k5a" in idx
    assert idx["luat:1/2020/QH14#d33a.k5a.b1"].parent_id == "luat:1/2020/QH14#d33a.k5a"


def test_inline_article_reference_not_heading():
    ps = parse_structure("Điều 5. X\n1. Theo quy định tại Điều 7 của Luật này.\nĐiều 6. Y", "luat:1/2020/QH14")
    assert [p.address.article for p in ps if p.kind == "article"] == ["5", "6"]


def test_body_line_starting_with_phan_is_not_heading(law):
    idx = index_provisions(law)
    assert all("Phần vốn góp" not in h for p in law for h in p.heading_path)
    assert idx[f"{LAW}#d1"].heading_path == idx[f"{LAW}#d2"].heading_path


def test_quoted_block_is_not_structure(amend):
    assert [p.address.article for p in amend if p.kind == "article"] == [str(i) for i in range(1, 12)]
    idx = index_provisions(amend)
    assert "3. Trường hợp chủ tọa" in idx[f"{AMEND}#d7.k3"].text
    assert _children(amend, f"{AMEND}#d7.k3", "point") == ["a", "b"]
    synthetic = parse_structure(
        'Điều 2. Sửa đổi Luật X\n1. Bổ sung Điều 10a vào sau Điều 10 như sau:\n'
        '"Điều 10a. Khen thưởng đột xuất\n1. Nội dung.\n2. Nội dung khác.”.\n2. Bãi bỏ Điều 11.', "luat:9/2026/QH16")
    assert [p.address.article for p in synthetic if p.kind == "article"] == ["2"]
    assert _children(synthetic, "luat:9/2026/QH16#d2", "clause") == ["1", "2"]


def test_spans_cover_text(law_text, law):
    for p in law:
        assert law_text[p.span[0]:p.span[1]].strip() == p.text.strip(), p.provision_id
