"""Unit tests for the Parsing & Chunking module conforming to `rag.schema`."""

import json
from pathlib import Path
import unicodedata
import pytest

from rag.chunk import (
    Chunk,
    Page,
    ParseError,
    chunk_document,
    load_pdf,
    load_text,
    make_chunk_id,
    make_chunks,
    make_doc_id,
    normalize_text,
    parse_pdf,
    parse_web,
)
from rag.schema import GoldRef


def test_normalize_text():
    raw = "  Tiếng   Việt   chuẩn   NFC\x00  \n\n  Dòng thứ  hai  "
    clean = normalize_text(raw)
    assert clean == "Tiếng Việt chuẩn NFC\nDòng thứ hai"
    assert unicodedata.is_normalized("NFC", clean)


def test_parse_web_plain_text():
    sample_text = "Nội dung điều 1 của quy định nội bộ."
    pages = parse_web(sample_text.encode("utf-8"), source="noibo.txt", media_type="text/plain")
    assert len(pages) == 1
    p = pages[0]
    assert isinstance(p, Page)
    assert p.page is None
    assert p.source == "noibo.txt"
    assert p.text == sample_text
    assert p.doc_id == make_doc_id(sample_text)
    assert not p.is_empty


def test_parse_web_html():
    html = b"""
    <html>
        <head><title>Test HTML</title></head>
        <body>
            <nav>Menu item</nav>
            <h1>Dieu 1. Test</h1>
            <p>Noi dung bai viet huong dan.</p>
        </body>
    </html>
    """
    pages = parse_web(html, source="https://example.com/test")
    assert len(pages) == 1
    p = pages[0]
    assert p.page is None
    assert "Dieu 1. Test" in p.text
    assert "Noi dung bai viet huong dan." in p.text
    assert "Menu item" not in p.text  # stripped nav boilerplate


def test_chunk_web_document():
    doc_id = "web_doc_1"
    text = "Câu một nói về chính sách. Câu hai nói về bảo hiểm y tế. Câu ba nói về lương bổng."
    page = Page(doc_id=doc_id, source="https://lab.rag/policy", page=None, text=text)

    chunks = chunk_document([page], size=80, overlap=20)
    assert len(chunks) >= 1
    for i, c in enumerate(chunks):
        assert isinstance(c, Chunk)
        assert c.chunk_id == make_chunk_id(doc_id, i)
        assert c.doc_id == doc_id
        assert c.source == "https://lab.rag/policy"
        assert c.page_start is None
        assert c.page_end is None
        assert not c.covers_page(1)


def test_chunk_paged_document_and_section_detection():
    doc_id = "pdf_doc_1"
    p1 = Page(
        doc_id=doc_id,
        source="luat.pdf",
        page=1,
        text="Điều 1. Phạm vi điều chỉnh\nLuật này quy định về hoạt động điện lực.",
    )
    p2 = Page(
        doc_id=doc_id,
        source="luat.pdf",
        page=2,
        text="Điều 2. Đối tượng áp dụng\nÁp dụng đối với mọi cơ quan, tổ chức, cá nhân tại Việt Nam.",
    )

    chunks = chunk_document([p1, p2], size=500, overlap=50)
    assert len(chunks) >= 1

    # Check first chunk
    c0 = chunks[0]
    assert c0.doc_id == doc_id
    assert c0.chunk_id == "pdf_doc_1:0000"
    assert c0.page_start is not None
    assert c0.page_end is not None
    assert c0.page_start <= c0.page_end
    assert c0.section == "Điều 1. Phạm vi điều chỉnh"
    assert c0.covers_page(1)


def test_cross_page_sentence_stitching():
    doc_id = "pdf_stitch"
    # Page 1 sentence is incomplete (no terminating punct)
    p1 = Page(
        doc_id=doc_id,
        source="doc.pdf",
        page=1,
        text="Quy định này áp dụng đối với các cơ sở kinh doanh",
    )
    # Page 2 sentence continues
    p2 = Page(
        doc_id=doc_id,
        source="doc.pdf",
        page=2,
        text="hoạt động trong lĩnh vực năng lượng tái tạo.",
    )

    chunks = chunk_document([p1, p2], size=1000, overlap=100)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.page_start == 1
    assert c.page_end == 2
    assert c.covers_page(1)
    assert c.covers_page(2)
    assert "các cơ sở kinh doanh hoạt động trong lĩnh vực" in c.text


def test_chunk_gold_ref_compatibility():
    doc_id = "pdf_gold"
    p = Page(
        doc_id=doc_id,
        source="luat_doanh_nghiep.pdf",
        page=5,
        text="Điều 15. Các hành vi bị nghiêm cấm trong quản lý doanh nghiệp.",
    )
    chunks = chunk_document([p], size=500, overlap=50)
    assert len(chunks) == 1
    chunk = chunks[0]

    gold_page = GoldRef(source="luat_doanh_nghiep.pdf", page=5)
    assert gold_page.matches(chunk)

    gold_diff_page = GoldRef(source="luat_doanh_nghiep.pdf", page=6)
    assert not gold_diff_page.matches(chunk)

    gold_section = GoldRef(source="luat_doanh_nghiep.pdf", section="Điều 15. Các hành vi bị nghiêm cấm trong quản lý doanh nghiệp.")
    assert gold_section.matches(chunk)


def test_chunk_json_roundtrip():
    doc_id = "pdf_json"
    p = Page(doc_id=doc_id, source="test.pdf", page=1, text="Nội dung kiểm tra JSON.")
    chunks = chunk_document([p])
    c = chunks[0]

    serialized = json.dumps(c.to_dict())
    deserialized = Chunk.from_dict(json.loads(serialized))
    assert deserialized == c


def test_invalid_overlap_raises():
    p = Page("d", "s.pdf", 1, "text")
    with pytest.raises(ValueError):
        chunk_document([p], size=500, overlap=500)
    with pytest.raises(ValueError):
        chunk_document([p], size=500, overlap=-10)

