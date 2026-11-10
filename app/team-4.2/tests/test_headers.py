"""W02-02c — bỏ header/footer/số trang; quan trọng nhất: KHÔNG xoá nội dung văn bản luật."""

import pytest

from rag.ingest.headers import is_furniture, strip_page_furniture, strip_running_lines
from rag.ingest.loaders import load_pdf


@pytest.mark.parametrize("line", [
    "131", "- 192 -", "· 44 ·", "•44•", "Trang 22", "Trang 3/10", "Page 3 of 10", "3/10",
    "数学试题第 2 页 (共 6 页)", "http://www.cet-journal.com", "© 2007 WILEY-VCH Verlag GmbH",
    "CÔNG BÁO/Số 123 + 124/Ngày 15-02-2024", "Tập 61, Số 4B (2025): 128-138", "## 12",
])
def test_furniture_patterns(line):
    assert is_furniture(line)


@pytest.mark.parametrize("line", [
    "Điều 12. Phạm vi điều chỉnh",
    "Chương II",
    "1. Người lao động có quyền:",
    "Hình 5. Phổ EDX của chitosan (A), biochar (B) và chitosan-biochar (C)",   # (C) không phải bản quyền
    "ý a), b), c), d) ở mỗi câu hỏi, học sinh ©",                              # © rác của OCR
    "https://doi.org/10.1002/jsfa.1780",                                       # trích dẫn, không phải footer
    "Mức phạt tiền từ 5.000.000 đồng đến 10.000.000 đồng",
    "<table><tr><td>131</td></tr></table>",
    "| 131 | 20 |",
])
def test_content_lines_are_never_furniture(line):
    assert not is_furniture(line)


def test_only_edge_lines_are_removed():
    body = "\n".join(f"Dòng nội dung {i}" for i in range(10))
    text = f"Trang 5\n{body[:40]}\n131\n{body[40:]}\n- 6 -"
    cleaned, removed = strip_page_furniture(text)
    assert removed == ["Trang 5", "- 6 -"]
    assert "\n131\n" in cleaned                     # số giữa trang (vd. số liệu) không đụng tới


def test_running_header_across_pages_with_changing_numbers():
    pages = [f"TẠP CHÍ LUẬT HỌC SỐ {n}\nĐiều {n}. Nội dung điều {n}.\nNội dung tiếp.\nTrang {n}" for n in range(1, 6)]
    cleaned, running = strip_running_lines(pages)
    assert running == ["trang #", "tạp chí luật học số #"]
    assert cleaned[2] == "Điều 3. Nội dung điều 3.\nNội dung tiếp."


def test_running_lines_need_enough_pages_and_never_drop_articles():
    assert strip_running_lines(["Đầu\nA\nCuối", "Đầu\nB\nCuối"]) == (["Đầu\nA\nCuối", "Đầu\nB\nCuối"], [])
    pages = [f"Điều {n}. Hiệu lực\nNội dung {n}" for n in range(5)]   # cùng chữ ký 'điều #. hiệu lực'
    assert strip_running_lines(pages)[1] == []


def test_load_pdf_removes_cong_bao_header_and_page_numbers(tmp_path):
    import fitz

    doc = fitz.open()
    for n in range(1, 5):
        page = doc.new_page()
        y = 60
        for line in (f"CONG BAO/So {100 + n}/Ngay 15-02-2024", f"Dieu {n}. Quy dinh so {n}",
                     f"Noi dung chi tiet cua dieu luat so {n} nay.", f"- {n} -"):
            page.insert_text((72, y), line)
            y += 20
    path = tmp_path / "cb.pdf"
    doc.save(path)
    pages = load_pdf(path)
    assert [p.text for p in pages][1] == "Dieu 2. Quy dinh so 2\nNoi dung chi tiet cua dieu luat so 2 nay."
    raw = load_pdf(path, strip_headers=False)
    assert raw[1].text.startswith("CONG BAO/So 102") and raw[1].text.endswith("- 2 -")
