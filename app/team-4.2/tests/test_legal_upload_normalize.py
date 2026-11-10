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


@pytest.mark.parametrize("name,key,width", [
    ("luat_43_2024_QH15.txt", "luat:43/2024/QH15", 70),
    ("luat_43_2024_QH15.txt", "luat:43/2024/QH15", 95),
    ("luat_31_2024_QH15.txt", "luat:31/2024/QH15", 80),
    ("luat_43_2024_QH15.txt", "luat:43/2024/QH15", 60),
    ("luat_29_2023_QH15.txt", "luat:29/2023/QH15", 75),
])
def test_pdf_wrapped_text_parses_to_same_articles_and_directives(name, key, width):
    real = (FIXTURES / name).read_text(encoding="utf-8")
    norm = normalize_legal_text(pages_of(wrap_like_pdf(real, width=width)))
    a = [p.provision_id for p in parse_structure(norm, key) if p.kind == "article"]
    b = [p.provision_id for p in parse_structure(real, key) if p.kind == "article"]
    assert a == b and a
    da = [(d.source_locator, d.operation_type) for d in parse_directives(parse_structure(norm, key))]
    db = [(d.source_locator, d.operation_type) for d in parse_directives(parse_structure(real, key))]
    assert da == db


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
