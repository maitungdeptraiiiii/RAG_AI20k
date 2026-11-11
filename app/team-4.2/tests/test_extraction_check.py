"""Kiểm tra trích xuất (kế hoạch tuần 1, Task 2): font TCVN3/VNI vỡ dấu + get_text(sort=True)."""

import pytest

from rag.ingest.extraction_check import check_text, is_bad_chars
from rag.ingest.loaders import FlaggedPage, OCRPage, load_pdf, load_source
from rag.ingest.ocr import OCRPageResult

ARIAL = "C:/Windows/Fonts/arial.ttf"
pytestmark_pdf = pytest.mark.skipif(not __import__("os").path.exists(ARIAL), reason="cần font Arial để vẽ tiếng Việt")

TCVN3 = "§iÒu 5. Ph¹m vi ®iÒu chØnh. Ng­êi lao ®éng cã quyÒn ®­îc nghØ h»ng n¨m theo quy ®Þnh cña Bé luËt nµy."
VNI = "Ñieàu 5. Phaïm vi ñieàu chænh. Ngöôøi lao ñoäng coù quyeàn ñöôïc nghæ haèng naêm theo quy ñònh cuûa Boä luaät naøy."
UNICODE = "Điều 5. Phạm vi điều chỉnh. Người lao động có quyền được nghỉ hằng năm theo quy định của Bộ luật này."


@pytest.mark.parametrize("text", [TCVN3, VNI, "Điều 5 " + "�" * 3 + " nội dung đủ dài ở đây", "Điều 5\x01\x02\x03 nội dung đủ dài"])
def test_bad_chars_detected(text):
    bad, detail = is_bad_chars(text)
    assert bad and detail


@pytest.mark.parametrize("text", [
    UNICODE,
    "Nhiệt độ 25°C ± 2°C; « trích dẫn » © 2026; § 3 — mức phạt từ 5.000.000 đồng " + UNICODE,
    "Ông Lê Văn Tý, bà Hà Thị Ánh, trẻ em Tôn Thất Ý: ã ỹ õ ũ à á ù ú ò ó ì í è é ý " * 3,
])
def test_correct_vietnamese_is_not_flagged(text):
    assert is_bad_chars(text) == (False, "")


def test_check_text_kinds():
    assert [i.kind for i in check_text("   ", 3)] == ["empty"]
    assert [i.kind for i in check_text(TCVN3, 2)] == ["bad_chars"] and check_text(UNICODE) == []


# --- loader / pipeline ----------------------------------------------------------------------

def _pdf(path, pages):
    """Mỗi phần tử là list dòng của một trang. Arial có đủ chữ tiếng Việt Unicode lẫn ký tự Latin-1 của TCVN3/VNI."""
    import fitz

    doc = fitz.open()
    for lines in pages:
        page = doc.new_page()
        for i, line in enumerate(lines):
            page.insert_text((40, 60 + 18 * i), line, fontsize=9, fontname="arial", fontfile=ARIAL)
    doc.save(path)
    return path


class _FakeOCR:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def ocr_image(self, image):
        self.calls += 1
        return OCRPageResult(UNICODE, (), {"engine": "fake", "cost": 0.001})


@pytestmark_pdf
def test_pdf_without_ocr_flags_legacy_font_page_but_keeps_text(tmp_path):
    path = _pdf(tmp_path / "cu.pdf", [[UNICODE[:60], UNICODE[60:]], [TCVN3[:60], TCVN3[60:]]])
    pages = load_pdf(path)
    assert type(pages[0]).__name__ == "Page"
    assert isinstance(pages[1], FlaggedPage) and pages[1].extraction_issues[0].kind == "bad_chars"
    assert "®iÒu" in pages[1].text                         # không mất nội dung, chỉ gắn cờ


@pytestmark_pdf
def test_pdf_with_ocr_rereads_only_legacy_font_page(tmp_path):
    path = _pdf(tmp_path / "cu.pdf", [[UNICODE[:60], UNICODE[60:]], [TCVN3[:60], TCVN3[60:]]])
    ocr = _FakeOCR()
    pages = load_pdf(path, ocr=ocr)
    assert ocr.calls == 1                                  # trang Unicode đúng không bị OCR
    assert isinstance(pages[1], OCRPage) and pages[1].ocr_meta["reason"] == "bad_chars"
    assert pages[1].text == UNICODE


def test_docx_and_txt_with_legacy_encoding_are_flagged(tmp_path):
    import docx

    d = docx.Document()
    d.add_paragraph(TCVN3)
    d.save(tmp_path / "cu.docx")
    (tmp_path / "cu.txt").write_text(VNI, encoding="utf-8")
    assert isinstance(load_source(tmp_path / "cu.docx")[0], FlaggedPage)
    assert isinstance(load_source(tmp_path / "cu.txt")[0], FlaggedPage)


def _pipeline(ocr=None):
    from rag.index.bm25_index import BM25Index
    from rag.index.embedder import HashEmbedder
    from rag.index.store import ChunkStore
    from rag.index.vector_index import VectorIndex
    from rag.pipeline import RAGPipeline
    from rag.retrieve.hybrid import HybridRetriever

    class NoLLM:
        model_id = "none"

        def complete(self, system, user):
            raise AssertionError

    return RAGPipeline(ChunkStore(), HybridRetriever(BM25Index(), VectorIndex(HashEmbedder(dim=64))), NoLLM(), ocr=ocr)


@pytestmark_pdf
def test_pipeline_reports_bad_chars_for_review_or_as_resolved_by_ocr(tmp_path):
    path = _pdf(tmp_path / "cu.pdf", [[UNICODE[:60], UNICODE[60:]], [TCVN3[:60], TCVN3[60:]]])
    flagged = _pipeline().ingest(path)
    (issue,) = flagged.quality_issues
    assert (issue["type"], issue["severity"], issue["location"]) == ("extraction.bad_chars", "warning", "page:2")
    assert flagged.needs_review

    fixed = _pipeline(_FakeOCR()).ingest(path)
    (issue,) = fixed.quality_issues
    assert (issue["type"], issue["severity"]) == ("extraction.bad_chars", "info") and "OCR" in issue["detail"]
    assert not fixed.needs_review and fixed.ocr_pages == [2]


def test_pdf_text_follows_visual_order_with_sort(tmp_path):
    """Dòng được ghi vào file theo thứ tự ngược (dưới trước, trên sau) -> sort=True đọc lại đúng từ trên xuống."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 200), "Dong thu ba o duoi cung cua trang.")
    page.insert_text((40, 120), "Dong thu hai o giua trang van ban.")
    page.insert_text((40, 60), "Dieu 1. Dong dau tien o tren cung.")
    doc.save(tmp_path / "order.pdf")
    text = load_pdf(tmp_path / "order.pdf")[0].text
    assert text.index("Dieu 1.") < text.index("Dong thu hai") < text.index("Dong thu ba")
