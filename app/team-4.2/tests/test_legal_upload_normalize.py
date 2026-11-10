import textwrap
from pathlib import Path

import pytest

from rag.legal.directives import parse_directives
from rag.legal.structure import parse_structure
from rag.legal.upload.normalize import check_structure, normalize_legal_text

FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
KEY = "luat:43/2024/QH15"


def wrap_like_pdf(text, width=70, header="LUẬT SỬA ĐỔI MỘT SỐ ĐIỀU", per_page=40):
    """Ngắt từng dòng ở `width` ký tự, rồi chèn header + "Trang N" vào mỗi trang `per_page` dòng."""
    lines = []
    for raw in text.split("\n"):
        lines += textwrap.wrap(raw, width=width, break_long_words=False) or [""]
    pages = []
    for n, i in enumerate(range(0, len(lines), per_page), 1):
        pages.append([header, *lines[i:i + per_page], f"Trang {n}"])
    return pages


def pages_of(pages):
    return ["\n".join(p) for p in pages]


def _ids_and_directives(text):
    provs = parse_structure(text, KEY)
    return ([p.provision_id for p in provs if p.kind == "article"],
            [(d.source_locator, d.operation_type) for d in parse_directives(provs)])


REAL_FILES = sorted(FIXTURES.glob("luat_*.txt"))


def _key_of(path):
    _, num, year, kind = path.stem.split("_")
    return f"luat:{num}/{year}/{kind}"


def _all_ids(text, key):
    return [(p.provision_id, p.kind) for p in parse_structure(text, key)]


@pytest.mark.parametrize("width", [60, 70, 80, 95])
@pytest.mark.parametrize("path", REAL_FILES, ids=lambda p: p.stem)
def test_pdf_wrapped_text_round_trips_every_real_fixture(path, width):
    key = _key_of(path)
    real = path.read_text(encoding="utf-8")
    norm = normalize_legal_text(pages_of(wrap_like_pdf(real, width=width)))
    assert _all_ids(norm, key) == _all_ids(real, key)
    da = [(d.source_locator, d.operation_type) for d in parse_directives(parse_structure(norm, key))]
    db = [(d.source_locator, d.operation_type) for d in parse_directives(parse_structure(real, key))]
    assert da == db


def test_fixture_glob_covers_all_eight():
    assert len(REAL_FILES) == 8


def test_real_43_has_directives():
    real = (FIXTURES / "luat_43_2024_QH15.txt").read_text(encoding="utf-8")
    assert _ids_and_directives(real)[1]


def test_repeated_headers_and_page_numbers_removed():
    norm = normalize_legal_text(["LUẬT X\nĐiều 1. A\n1", "LUẬT X\nĐiều 2. B\n2", "LUẬT X\nĐiều 3. C\n3"])
    assert "LUẬT X" not in norm and norm.splitlines() == ["Điều 1. A", "Điều 2. B", "Điều 3. C"]


def test_reference_to_article_mid_sentence_is_not_split():
    norm = normalize_legal_text(["1. Theo quy định tại\nĐiều 5 của Luật này thì ..."])
    assert norm == "1. Theo quy định tại Điều 5 của Luật này thì ..."


def test_single_paragraph_is_split_after_sentence_end():
    norm = normalize_legal_text(["1. Trong Luật này: a) Một; b) Hai. 2. Khác."])
    assert norm.splitlines() == ["1. Trong Luật này:", "a) Một;", "b) Hai.", "2. Khác."]


def test_quoted_units_stay_on_own_lines():
    norm = normalize_legal_text(["1. Sửa đổi khoản 2 Điều 5 như sau:\n“2. Nội dung\nmới.”\n2. Bổ sung Điều 6 như sau:\n“Điều 6. Mới”"])
    assert norm.splitlines() == ["1. Sửa đổi khoản 2 Điều 5 như sau:", "“2. Nội dung mới.”",
                                 "2. Bổ sung Điều 6 như sau:", "“Điều 6. Mới”"]


def test_structure_check_gap_and_effectivity():
    sc = check_structure("Điều 1. A\nĐiều 2. B\nĐiều 4. Hiệu lực thi hành\nLuật này có hiệu lực từ ngày 01 tháng 7 năm 2025.", "luat:1/2025/QH15")
    assert sc.n_articles == 3 and sc.gaps == (("2", "4"),) and sc.has_effectivity_article


def test_inserted_article_labels_are_not_gaps():
    assert check_structure("Điều 5. A\nĐiều 5a. B\nĐiều 6. C", "k").gaps == ()


def test_wrapped_article_reference_at_line_start_is_not_a_unit():
    assert normalize_legal_text(["1. Nội dung quy định tại\nĐiều 5.\nTiếp theo..."]) == \
        "1. Nội dung quy định tại Điều 5. Tiếp theo..."
    assert normalize_legal_text(["1. Theo quy định tại\nĐiều 5, Điều 6 của Luật này."]) == \
        "1. Theo quy định tại Điều 5, Điều 6 của Luật này."


def test_wrapped_chapter_or_section_reference_is_not_a_heading():
    assert normalize_legal_text(["1. Các quy định tại\nChương II của Luật này được áp dụng."]) == \
        "1. Các quy định tại Chương II của Luật này được áp dụng."
    assert normalize_legal_text(["1. Các quy định tại\nMục 3 và Mục 4 được áp dụng."]) == \
        "1. Các quy định tại Mục 3 và Mục 4 được áp dụng."


def test_long_unbreakable_token_does_not_break_round_trip():
    path = FIXTURES / "luat_45_2013_QH13.txt"
    key = _key_of(path)
    real = path.read_text(encoding="utf-8") + "\n" + "x" * 400
    norm = normalize_legal_text(pages_of(wrap_like_pdf(real, width=70)))
    assert _all_ids(norm, key) == _all_ids(real, key)


def test_real_headings_still_split():
    body = [f"{n}. " + "Nội dung dài của khoản " * 6 + "." for n in range(1, 6)]
    src = ["Chương I", "QUY ĐỊNH CHUNG", "Điều 1. A", *body, "Mục 2. Khác"]
    assert normalize_legal_text(["\n".join(src)]).splitlines() == src
