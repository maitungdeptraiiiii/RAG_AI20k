from rag.contracts.doc import PageText, assemble
from rag.contracts.parts import detect_parts


def test_page_map():
    a = assemble([PageText(1, "Điều 1. A"), PageText(2, "Điều 2. B")])
    assert a.text == "Điều 1. A\n\nĐiều 2. B"
    assert a.page_at(0) == 1 and a.page_at(a.text.index("Điều 2")) == 2


def test_appendix_headings_start_parts():
    text = "HỢP ĐỒNG\nĐiều 1. A\n\nPHỤ LỤC 01\nĐiều 1. Giá\n\nPhụ lục 2: Bản vẽ\nNội dung"
    parts = detect_parts(text)
    assert [(p.part_id, p.kind, p.number) for p in parts] == [("p0", "main", None), ("p1", "appendix", 1), ("p2", "appendix", 2)]
    assert text[parts[1].start:].startswith("PHỤ LỤC 01")


def test_inline_mention_and_toc_are_not_parts():
    text = ("MỤC LỤC\nPHỤ LỤC\nĐiều 1. Bên A giao nhà theo Phụ lục 1 đính kèm.\n"
            "Điều 2. Các bên ký Phụ lục 1 cùng ngày.")
    assert [p.part_id for p in detect_parts(text)] == ["p0"]


def test_heading_at_offset_zero_keeps_p0():
    parts = detect_parts("PHỤ LỤC 1\nNội dung")
    assert [(p.part_id, p.start) for p in parts] == [("p0", 0), ("p1", 0)]


BODY_SENTENCES = ("HỢP ĐỒNG\nĐiều 1. Giá\nGiá thuê theo bảng.\nĐiều 2. Hiệu lực\nCó hiệu lực từ ngày ký.\n\n"
                  "Phụ lục 01 là phần không tách rời của hợp đồng này.\n"
                  "Điều 3. Điều khoản chung\nHai bên cam kết.\n\n"
                  "PHỤ LỤC kèm theo gồm 02 trang\nĐiều 4. Thi hành\nHai bên thi hành.\n")


def test_body_sentences_are_not_appendix_headings():
    assert [p.part_id for p in detect_parts(BODY_SENTENCES)] == ["p0"]
    from rag.contracts.structure import parse_contract
    doc = parse_contract([PageText(1, BODY_SENTENCES)])
    assert [u.label for u in doc.top_units()] == ["Phần mở đầu", "Điều 1", "Điều 2", "Điều 3", "Điều 4"]
    assert "Phụ lục 01 là phần không tách rời" in doc.unit("p0.d2").text


def test_real_uppercase_heading_still_detected():
    text = BODY_SENTENCES + "\nPHỤ LỤC 01\nBẢNG GIÁ\nĐiều 1. Giá thuê 5 triệu đồng.\n"
    parts = detect_parts(text)
    assert [(p.part_id, p.title, p.number) for p in parts] == [("p0", "", None), ("p1", "PHỤ LỤC 01", 1)]
    assert detect_parts("Điều 1. A\n\nPhụ lục 2: Bản vẽ mặt bằng\nNội dung")[1].number == 2


def test_user_part_heading_sentence_is_kept():
    from rag.contracts.doc import PartSpec
    from rag.contracts.structure import parse_contract
    text = "Điều 1. A\nx\nĐiều 2. B\ny\n\nPhụ lục 01 là phần không tách rời của hợp đồng này.\nĐiều 1. C\n"
    start = text.index("Phụ lục 01")
    title = "Phụ lục 01 là phần không tách rời của hợp đồng này."
    doc = parse_contract([PageText(1, text)], [PartSpec("p0", "main", "", 0, None),
                                               PartSpec("p1", "appendix", title, start, 1)])
    assert doc.unit("p1.pre") is not None and doc.unit("p1.pre").text == title
