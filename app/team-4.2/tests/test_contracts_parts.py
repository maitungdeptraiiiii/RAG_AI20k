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
