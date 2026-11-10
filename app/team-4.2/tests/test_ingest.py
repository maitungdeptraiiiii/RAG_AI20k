import json
import tempfile
import unicodedata
from pathlib import Path

import pytest

from rag.index.store import ChunkStore
from rag.ingest.chunker import chunk_document
from rag.ingest.loaders import (
    TablePage,
    UnsupportedSourceError,
    clean_text,
    load_docx,
    load_source,
    load_text,
    load_url,
    pages_from_texts,
)
from rag.schema import Page

# --- loaders ------------------------------------------------------------------------

def test_clean_text_nfc_spaces_and_blank_lines():
    raw = unicodedata.normalize("NFD", "Điều  1.\t Phạm vi \r\n\r\n\r\n\r\nNội dung")
    assert clean_text(raw) == "Điều 1. Phạm vi\n\nNội dung"


def test_pages_from_texts_numbers_from_one_and_keeps_empty_pages():
    pages = pages_from_texts("d", "a.pdf", ["trang một", "   ", "trang ba"])
    assert [p.page for p in pages] == [1, 2, 3]
    assert pages[1].is_empty


def test_load_text_and_doc_id_stable():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "luat.txt"
        path.write_text("Điều 1. Phạm vi\nNội dung.", encoding="utf-8")
        a, b = load_text(path), load_text(path)
        assert a[0].doc_id == b[0].doc_id and a[0].page is None and a[0].source == "luat.txt"
        path.write_bytes("xin chào".encode("cp1258", errors="ignore") + b"\xff")
        with pytest.raises(UnsupportedSourceError):
            load_text(path)


def test_load_url_with_fake_fetcher():
    pages = load_url("https://x.vn/a", fetch=lambda u: "<html>", extract=lambda h: "Nội dung chính")
    assert pages[0].source == "https://x.vn/a" and pages[0].text == "Nội dung chính"
    with pytest.raises(UnsupportedSourceError):
        load_url("https://x.vn/a", fetch=lambda u: None, extract=lambda h: "x")
    with pytest.raises(UnsupportedSourceError):
        load_url("https://x.vn/a", fetch=lambda u: "<html>", extract=lambda h: "  ")


def test_load_source_rejects_unknown_type():
    with pytest.raises(UnsupportedSourceError):
        load_source("tai_lieu.doc")


def _write_docx(path: Path) -> None:
    import docx

    doc = docx.Document()
    for line in [
        "Chương I",
        "NHỮNG QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về đất đai.",
    ]:
        doc.add_paragraph(line)
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Loại đất", "Thời hạn"
    table.cell(1, 0).text, table.cell(1, 1).text = "Đất nông nghiệp", "50 năm"
    doc.add_paragraph("Điều 2. Đối tượng áp dụng")
    doc.add_paragraph("Cơ quan nhà nước.")
    doc.save(path)


def test_load_docx_paragraphs_tables_and_chunking():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "luat.docx"
        _write_docx(path)
        all_pages = load_source(path, source="Luật đất đai.docx")
        again = load_docx(path)
    # trang 0 = thân văn bản (giữ bảng tại chỗ); các trang sau = TablePage có cấu trúc (W02-02b)
    pages = [p for p in all_pages if not isinstance(p, TablePage)]
    tables = [p.table for p in all_pages if isinstance(p, TablePage)]
    assert len(pages) == 1 and pages[0].page is None and pages[0].source == "Luật đất đai.docx"
    assert len(tables) == 1 and tables[0].headers == (("Loại đất", "Thời hạn"),)
    assert tables[0].rows == (("Đất nông nghiệp", "50 năm"),)
    assert pages[0].doc_id == again[0].doc_id
    assert "Loại đất | Thời hạn\nĐất nông nghiệp | 50 năm" in pages[0].text
    # bảng nằm đúng vị trí giữa Điều 1 và Điều 2
    assert pages[0].text.index("Điều 1.") < pages[0].text.index("Loại đất") < pages[0].text.index("Điều 2.")

    chunks = chunk_document(pages, max_syllables=300)
    assert len(chunks) == 2
    assert chunks[0].section == "Chương I NHỮNG QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh"
    assert "Đất nông nghiệp | 50 năm" in chunks[0].text
    assert chunks[1].text.startswith("Điều 2.") and chunks[1].page_start is None


def test_load_docx_rejects_corrupt_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "hong.docx"
        path.write_bytes(b"khong phai docx")
        with pytest.raises(UnsupportedSourceError):
            load_docx(path)


# --- chunker ------------------------------------------------------------------------

def _pages(*texts, doc_id="d", source="a.pdf"):
    return [Page(doc_id, source, i, t) for i, t in enumerate(texts, start=1)]


def test_chunk_ids_metadata_and_size_limit():
    para = " ".join(["từ"] * 40) + "."
    chunks = chunk_document(_pages("\n\n".join([para] * 10)), max_syllables=100)
    assert [c.chunk_id for c in chunks] == [f"d:{i:04d}" for i in range(len(chunks))]
    assert all(len(c.text.split()) <= 100 for c in chunks)
    assert all(c.source == "a.pdf" and c.page_start == 1 for c in chunks)


def test_overlap_one_paragraph():
    paras = [f"đoạn {i} " + " ".join(["x"] * 30) + "." for i in range(4)]
    chunks = chunk_document(_pages("\n\n".join(paras)), max_syllables=70)
    assert len(chunks) >= 2
    assert chunks[0].text.split("\n")[-1] == chunks[1].text.split("\n")[0]   # đoạn cuối chunk trước lặp lại


def test_chunk_spanning_pages_keeps_page_range():
    chunks = chunk_document(_pages("Câu đầu ở trang một.", "Câu tiếp ở trang hai."), max_syllables=300)
    assert len(chunks) == 1 and (chunks[0].page_start, chunks[0].page_end) == (1, 2)


def test_pdf_line_wrap_is_merged_into_one_paragraph():
    chunks = chunk_document(_pages("Người lao động có quyền\nđược nghỉ hằng năm.\n1. Khoản một."), max_syllables=300)
    assert chunks[0].text.split("\n") == ["Người lao động có quyền được nghỉ hằng năm.", "1. Khoản một."]


def test_legal_headings_set_section_and_split_articles():
    text = (
        "Chương I\nNHỮNG QUY ĐỊNH CHUNG\n"
        "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về đất đai.\n"
        "Điều 2. Đối tượng áp dụng\nCơ quan nhà nước.\n"
        "Chương II\nQUYỀN CỦA NHÀ NƯỚC\n"
        "Điều 3. Sở hữu\nĐất đai thuộc sở hữu toàn dân."
    )
    chunks = chunk_document(_pages(text), max_syllables=300)
    assert len(chunks) == 3
    assert chunks[0].section == "Chương I NHỮNG QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh"
    assert chunks[0].text.startswith("Điều 1.")
    assert chunks[2].section.startswith("Chương II QUYỀN CỦA NHÀ NƯỚC > Điều 3.")
    assert "Điều 2" not in chunks[2].text   # không overlap qua ranh giới Điều


def test_long_paragraph_is_split_and_empty_pages_skipped():
    long = " ".join(["chữ"] * 250)
    chunks = chunk_document(_pages("", long, "   "), max_syllables=100)
    assert len(chunks) == 3 and all(c.page_start == 2 for c in chunks)


def test_url_pages_have_no_page_numbers():
    chunks = chunk_document([Page("u", "https://x.vn", None, "Nội dung trang web.")])
    assert chunks[0].page_start is None and chunks[0].page_end is None


def test_chunker_input_validation():
    assert chunk_document([]) == []
    with pytest.raises(ValueError):
        chunk_document([Page("a", "x", 1, "t"), Page("b", "x", 2, "t")])


# --- ChunkStore ---------------------------------------------------------------------

def test_chunk_store_dedupes_by_doc_and_persists():
    chunks = chunk_document(_pages("Điều 1. A.\nNội dung.", "Điều 2. B.\nNội dung."))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "processed" / "chunks.jsonl"
        store = ChunkStore(path)
        assert store.add(chunks) == len(chunks)
        assert store.add(chunks) == 0                  # ingest lại không nhân đôi
        reopened = ChunkStore(path)
        assert [c.chunk_id for c in reopened.all()] == [c.chunk_id for c in chunks]
        assert reopened.has_doc("d") and reopened.docs()[0].n_chunks == len(chunks)
        assert len(path.read_text(encoding="utf-8").strip().splitlines()) == len(chunks)
        assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["doc_id"] == "d"
