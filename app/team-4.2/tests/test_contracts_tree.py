from rag.contracts.doc import PageText, PartSpec, assemble
from rag.contracts.tree import parse_part


def parse(text):
    a = assemble([PageText(1, text)])
    return parse_part(a, PartSpec("p0", "main", "", 0, None), len(a.text), "")


CONTRACT = """HỢP ĐỒNG THUÊ NHÀ
Bên A:
1. Ông Nguyễn Văn A
2. Bà Trần Thị B
Điều 1. Đối tượng
Bên A cho Bên B thuê nhà.
Điều 2. Giá thuê
1. Giá thuê là 30.000.000 đồng/tháng.
2. Thanh toán:
a) trước ngày 5 hằng tháng;
đ) bằng chuyển khoản.
Điều 4. Chấm dứt
4.1. Bên A được chấm dứt theo khoản 1 Điều 2.
4.2. Điều 5 của Hợp đồng gốc được sửa đổi như sau: bỏ."""


def test_tree_ids_labels_levels():
    units, style, gaps = parse(CONTRACT)
    assert style == "dieu"
    assert [u.uid for u in units] == ["p0.pre", "p0.d1", "p0.d2", "p0.d2.k1", "p0.d2.k2", "p0.d2.k2.a",
                                       "p0.d2.k2.dd", "p0.d4", "p0.d4.k1", "p0.d4.k2"]
    u = {x.uid: x for x in units}
    assert u["p0.d2.k2.a"].label == "điểm a khoản 2 Điều 2" and u["p0.d2.k2.a"].parent_uid == "p0.d2.k2"
    assert u["p0.d4.k1"].label == "khoản 1 Điều 4"
    assert "2. Bà Trần Thị B" in u["p0.pre"].text          # danh sách trong phần mở đầu không thành Mục
    assert u["p0.d2"].text.startswith("Điều 2.") and "đ) bằng chuyển khoản." in u["p0.d2"].text
    assert gaps == ["p0: sau Điều 2 là Điều 4"]


def test_body_line_starting_with_dieu_is_not_a_heading():
    units, _, _ = parse(CONTRACT)
    assert "p0.d5" not in {x.uid for x in units}


def test_roman_numeric_and_paragraph_fallbacks():
    assert [u.label for u in parse("I. Chung\nNội dung\nII. Giá\nNội dung")[0]] == ["Mục I", "Mục II"]
    assert [u.uid for u in parse("HỢP ĐỒNG\n1. Đối tượng\nA\n2. Giá\nB")[0]] == ["p0.pre", "p0.d1", "p0.d2"]
    units, style, _ = parse("Bên A bán xe.\n\nGiá 20 triệu.")
    assert style == "paragraph" and [u.label for u in units] == ["Đoạn 1", "Đoạn 2"]


def test_article_style_variants():
    assert [u.uid for u in parse("ĐIỀU 1: A\nx\nArticle 2. B\ny")[0]] == ["p0.d1", "p0.d2"]


# --- Kiểm thử bổ sung theo các quyết định của controller ---

def test_offsets_pages_numbers_and_prefix():
    a = assemble([PageText(3, "PHỤ LỤC 1\nĐiều 1. A\n1. x\nĐiều 2. B"), PageText(4, "2. y\na) z")])
    units, style, gaps = parse_part(a, PartSpec("p1", "appendix", "PHỤ LỤC 1", 0, 1), len(a.text),
                                    "Phụ lục 1 — ")
    assert style == "dieu" and gaps == []
    for u in units:
        assert u.text == a.text[u.char_start:u.char_end] and u.text == u.text.rstrip()
    u = {x.uid: x for x in units}
    assert u["p1.pre"].label == "Phụ lục 1 — Phần mở đầu" and u["p1.pre"].number == ""
    assert u["p1.d2.k2"].label == "Phụ lục 1 — khoản 2 Điều 2" and u["p1.d2.k2"].number == "2"
    assert u["p1.d2.k2.a"].label == "Phụ lục 1 — điểm a khoản 2 Điều 2"
    assert (u["p1.d2"].page_start, u["p1.d2"].page_end) == (3, 4)
    assert u["p1.d2"].number == "2" and u["p1.d2.k2.a"].number == "a"


def test_clause_gap_and_points_directly_under_article():
    units, _, gaps = parse("Điều 1. A\na) x\nb) y\nĐiều 2. B\n1. m\n3. n")
    u = {x.uid: x for x in units}
    assert u["p0.d1.a"].parent_uid == "p0.d1" and u["p0.d1.a"].label == "điểm a Điều 1"
    assert gaps == ["p0: sau khoản 1 Điều 2 là khoản 3 Điều 2"]


def test_roman_clauses_share_counter_and_numeric_needs_dotted():
    units, style, _ = parse("I. Chung\n1. a\nI.x\n1.2. b\nII. Giá\n2.1. c\n2. d")
    assert style == "roman"
    assert [x.uid for x in units] == ["p0.d1", "p0.d1.k1", "p0.d1.k2", "p0.d2", "p0.d2.k1", "p0.d2.k2"]
    assert units[3].number == "II"
    units, style, _ = parse("1. Đối tượng\n1.1. A\n2. Giá\n2.1. B\n3.2. C")
    assert style == "numeric"
    assert [x.uid for x in units] == ["p0.d1", "p0.d1.k1", "p0.d2", "p0.d2.k1"]
    assert units[2].label == "Mục 2"


def test_point_skip_limit_and_paragraph_ids():
    units, _, _ = parse("Điều 1. A\n1. x\na) p\nđ) q\nk) r\nĐiều 2. B")
    assert [x.uid for x in units if x.level == "point"] == ["p0.d1.k1.a", "p0.d1.k1.dd"]
    units, _, _ = parse("  Một.\n\n \nHai.\n")
    assert [(x.uid, x.number, x.text) for x in units] == [("p0.o1", "1", "Một."), ("p0.o2", "2", "Hai.")]


def test_single_article_is_enough_for_dieu_style():
    units, style, _ = parse("Điều 1. A")
    assert style == "dieu" and [(u.uid, u.label) for u in units] == [("p0.d1", "Điều 1")]
    units, style, _ = parse("HĐ\nĐiều 1. A\n1. Giá thuê 10 triệu.\n2. B")
    assert style == "dieu"
    assert [u.uid for u in units] == ["p0.pre", "p0.d1", "p0.d1.k1", "p0.d1.k2"]
