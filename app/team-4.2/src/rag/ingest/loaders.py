"""Parsing PDF / DOCX / URL / TXT -> list[Page] — TV1.

    load_pdf(path)   PyMuPDF, mỗi trang một Page (page đánh số từ 1); doc_id = hash bytes file
    load_docx(path)  python-docx, đoạn văn + bảng theo thứ tự; một Page (page=None); doc_id = hash bytes file
    load_url(url)    trafilatura lấy nội dung chính; một Page (page=None); doc_id = hash text
    load_text(path)  file text UTF-8; một Page (page=None); doc_id = hash text
    load_table(path) CSV/TSV/XLSX: mỗi bảng (sheet) một TablePage; doc_id = hash bytes file
    load_image(path) PNG/JPG/TIFF/WebP: OCR một trang (cần ``ocr``); doc_id = hash bytes file
    load_source(x)   tự chọn loader theo URL / đuôi file

DOCX và CSV/XLSX trả thêm ``TablePage`` (Page + ParsedTable) cho từng bảng; pipeline chunk các
trang này bằng ``chunk_tables`` (lặp header + đơn vị ở mọi chunk) thay vì chunker văn bản.

OCR (W02-02c, truyền ``ocr=GeminiOCREngine(...)``): PDF xét TỪNG TRANG — trang có text layer dùng
luôn, trang gần như không có text (< ``MIN_TEXT_CHARS``) được render ảnh rồi OCR thành ``OCRPage``
(giữ số trang cho citation, mang mã issue chất lượng); bảng HTML trong output OCR thành ``TablePage``.
Không truyền ``ocr`` thì như baseline: trang scan rỗng + cảnh báo, file ảnh bị từ chối.

Text được chuẩn hoá NFC và dọn khoảng trắng.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

from dataclasses import dataclass, field, replace
from typing import Any

from collections import Counter

from rag.ingest.extraction_check import PageIssue, check_text
from rag.ingest.tables import TABLE_SUFFIXES, ParsedTable, docx_tables, load_tables, table_markdown
from rag.schema import Page, make_doc_id, nfc

log = logging.getLogger(__name__)

_SPACES_RE = re.compile(r"[ \t ​]+")
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")

PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
TEXT_SUFFIXES = {".txt", ".md", ".text"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
MIN_TEXT_CHARS = 20        # trang PDF có ít ký tự hơn coi là trang scan -> OCR


class UnsupportedSourceError(ValueError):
    pass


@dataclass(frozen=True)
class TablePage(Page):
    """Một bảng có cấu trúc; ``text`` = Markdown của cả bảng (để xem/đếm), chunk bằng ``table``."""

    table: ParsedTable | None = None


def table_pages(doc_id: str, source: str, tables: Sequence[ParsedTable]) -> list[TablePage]:
    return [TablePage(doc_id, source, t.page, table_markdown(t), table=t) for t in tables]


@dataclass(frozen=True)
class OCRPage(Page):
    """Trang có text do OCR sinh (không phải text layer gốc). ``ocr_issues`` -> QualityIssue ở pipeline."""

    ocr_engine: str = ""
    ocr_issues: tuple[str, ...] = ()
    ocr_meta: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class FlaggedPage(Page):
    """Trang có text nhưng text đáng ngờ (vd. font TCVN3/VNI vỡ dấu) và không OCR lại được.
    Vẫn giữ text (không mất nội dung) nhưng pipeline gắn QualityIssue -> review, không im lặng."""

    extraction_issues: tuple[PageIssue, ...] = ()


def _flag_bad_chars(page: Page) -> Page:
    issues = [i for i in check_text(page.text, page.page) if i.kind == "bad_chars"]
    if not issues:
        return page
    log.warning("%s trang %s: %s", page.source, page.page or "-", issues[0].detail)
    return FlaggedPage(page.doc_id, page.source, page.page, page.text, extraction_issues=tuple(issues))


def _ocr_page_image(image, *, doc_id: str, source: str, page: int, ocr, n_tables: int,
                    reason: PageIssue | None = None) -> list[Page]:
    """OCR một ảnh trang -> [OCRPage, *TablePage]. ``reason``: vì sao trang này phải OCR."""
    from rag.ingest.ocr import split_ocr_markdown

    result = ocr.ocr_image(image)
    text, tables = split_ocr_markdown(nfc(result.text), source_name=source, page=page, first_index=n_tables)
    meta = {k: v for k, v in result.meta.items() if k != "image_sha256"}
    meta["reason"] = reason.kind if reason else "image"
    if reason is not None and reason.kind == "bad_chars":
        meta["reason_detail"] = reason.detail
    out: list[Page] = [OCRPage(doc_id, source, page, clean_text(text), ocr_engine=getattr(ocr, "name", "ocr"),
                               ocr_issues=result.issues, ocr_meta=meta)]
    out += table_pages(doc_id, source, tables)
    return out


def clean_text(text: str) -> str:
    """NFC, gộp khoảng trắng trong dòng, bỏ khoảng trắng đầu/cuối dòng, tối đa 1 dòng trống liền nhau."""
    text = nfc(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    return _MANY_NEWLINES_RE.sub("\n\n", "\n".join(lines)).strip()


def pages_from_texts(doc_id: str, source: str, texts: Sequence[str]) -> list[Page]:
    """Tạo Page cho từng trang (đánh số từ 1) và cảnh báo trang rỗng."""
    pages = [Page(doc_id, source, i, clean_text(t)) for i, t in enumerate(texts, start=1)]
    empty = [p.page for p in pages if p.is_empty]
    if empty:
        log.warning(
            "%s: %d/%d trang không có text (có thể là PDF scan, cần OCR): %s",
            source, len(empty), len(pages), empty[:20],
        )
    return pages


def strip_headers_footers(pages: list[Page], source: str) -> list[Page]:
    """Bỏ số trang / header / footer ở mép mỗi trang văn bản (không đụng TablePage), rồi bỏ dòng mép
    lặp lại trên ≥ 50 % trang. Xem rag/ingest/headers.py."""
    from rag.ingest.headers import strip_page_furniture, strip_running_lines

    idx = [i for i, p in enumerate(pages) if not isinstance(p, TablePage) and p.text]
    if not idx:
        return pages
    # tầng 2 (lặp qua trang) chạy trên text gốc, khi số trang còn giữ vị trí mép; rồi tới tầng 1 (mẫu)
    texts, running = strip_running_lines([pages[i].text for i in idx])
    per_page = [strip_page_furniture(text) for text in texts]
    out = list(pages)
    for i, (text, removed) in zip(idx, per_page):
        cleaned = clean_text(text)
        if isinstance(pages[i], OCRPage):
            meta = {**pages[i].ocr_meta, "header_footer_removed": removed}
            out[i] = replace(pages[i], text=cleaned, ocr_meta=meta)
        else:
            out[i] = replace(pages[i], text=cleaned)
    n_pattern = sum(len(removed) for _, removed in per_page)
    if n_pattern or running:
        log.info("%s: bỏ %d dòng số trang/header/footer theo mẫu; header/footer chạy qua trang: %s",
                 source, n_pattern, running[:5])
    return out


def load_pdf(path: Path | str, *, source: str | None = None, ocr=None, strip_headers: bool = True) -> list[Page]:
    import fitz  # PyMuPDF

    path = Path(path)
    data = path.read_bytes()
    doc_id, name = make_doc_id(data), source or path.name
    with fitz.open(stream=data, filetype="pdf") as doc:
        # sort=True: sắp khối text theo vị trí trên trang (trên xuống, trái sang) thay vì thứ tự lưu trong file
        texts = [page.get_text("text", sort=True) for page in doc]
        if ocr is None:
            pages = [_flag_bad_chars(p) for p in pages_from_texts(doc_id, name, texts)]
            return strip_headers_footers(pages, name) if strip_headers else pages
        from rag.ingest.ocr import render_pdf_page

        pages: list[Page] = []
        n_tables = 0
        for i, (pdf_page, text) in enumerate(zip(doc, texts), start=1):
            issues = check_text(text, i)
            if not issues:
                pages.append(Page(doc_id, name, i, clean_text(text)))
                continue
            # trang scan (empty) hoặc font cũ vỡ dấu (bad_chars): đọc lại từ ẢNH trang
            got = _ocr_page_image(render_pdf_page(pdf_page), doc_id=doc_id, source=name, page=i, ocr=ocr,
                                  n_tables=n_tables, reason=issues[0])
            n_tables += sum(isinstance(p, TablePage) for p in got)
            pages.extend(got)
    reasons = Counter(p.ocr_meta.get("reason") for p in pages if isinstance(p, OCRPage))
    if reasons:
        log.info("%s: OCR %d/%d trang (%s)", name, sum(reasons.values()), len(texts), dict(reasons))
    return strip_headers_footers(pages, name) if strip_headers else pages


def load_image(path: Path | str, *, source: str | None = None, ocr=None) -> list[Page]:
    """Ảnh một trang tài liệu -> OCR. Không có engine OCR thì từ chối rõ ràng."""
    from PIL import Image, ImageOps

    path = Path(path)
    name = source or path.name
    if ocr is None:
        raise UnsupportedSourceError(f"{name}: file ảnh cần OCR — đặt OCR_ENGINE=gemini trong .env")
    data = path.read_bytes()
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    except OSError as e:
        raise UnsupportedSourceError(f"{name}: không đọc được ảnh ({e})") from e
    pages = _ocr_page_image(image, doc_id=make_doc_id(data), source=name, page=1, ocr=ocr, n_tables=0)
    return strip_headers_footers(pages, name)


def _docx_blocks(doc) -> list[str]:
    """Đoạn văn và bảng theo đúng thứ tự trong thân văn bản. Mỗi hàng bảng thành một dòng
    "ô | ô | ...", ô gộp (merged) chỉ lấy một lần."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks: list[str] = []
    for item in doc.iter_inner_content():
        if isinstance(item, Paragraph):
            blocks.append(item.text)
        elif isinstance(item, Table):
            for row in item.rows:
                cells: list[str] = []
                seen: set[int] = set()
                for cell in row.cells:
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    text = " ".join(cell.text.split())
                    if text:
                        cells.append(text)
                if cells:
                    blocks.append(" | ".join(cells))
            blocks.append("")   # dòng trống sau bảng: không gộp với đoạn kế tiếp
    return blocks


def load_docx(path: Path | str, *, source: str | None = None) -> list[Page]:
    """DOCX không có khái niệm trang cố định -> một Page (page=None); doc_id = hash bytes file.
    Mỗi paragraph Word là một dòng, nên chunker vẫn nhận ra heading Chương/Điều như với PDF."""
    import docx  # python-docx
    from docx.opc.exceptions import PackageNotFoundError

    path = Path(path)
    data = path.read_bytes()
    try:
        doc = docx.Document(io.BytesIO(data))
    except (PackageNotFoundError, KeyError, ValueError, zipfile.BadZipFile) as e:
        raise UnsupportedSourceError(f"{path.name}: không đọc được file DOCX ({e})") from e
    text = clean_text("\n".join(_docx_blocks(doc)))
    name = source or path.name
    if not text:
        log.warning("%s: tài liệu rỗng", name)
    doc_id = make_doc_id(data)
    # Thân văn bản vẫn giữ bảng tại chỗ (ngữ cảnh Điều); bảng có cấu trúc đi kèm thành TablePage.
    body = _flag_bad_chars(Page(doc_id, name, None, text))   # DOCX gõ bằng font .VnTime/VNI-Times
    return [body, *table_pages(doc_id, name, docx_tables(doc, name))]


def load_table(path: Path | str, *, source: str | None = None, header_rows: int = 1) -> list[Page]:
    """CSV/TSV/XLSX -> TablePage cho từng bảng/sheet."""
    path = Path(path)
    data = path.read_bytes()
    name = source or path.name
    try:
        tables = load_tables(path, header_rows=header_rows)
    except (ValueError, KeyError, zipfile.BadZipFile) as e:
        raise UnsupportedSourceError(f"{name}: không đọc được bảng ({e})") from e
    tables = [replace(t, source_name=name) for t in tables]
    if not tables:
        log.warning("%s: không có bảng nào có dữ liệu", name)
    return list(table_pages(make_doc_id(data), name, tables))


def load_text(path: Path | str, *, source: str | None = None) -> list[Page]:
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise UnsupportedSourceError(f"{path.name}: file text phải mã hoá UTF-8") from e
    return [_flag_bad_chars(p) for p in _single_page(text, source or path.name)]


def load_url(
    url: str,
    *,
    fetch: Callable[[str], str | None] | None = None,
    extract: Callable[[str], str | None] | None = None,
) -> list[Page]:
    """`fetch`/`extract` cho phép thay trafilatura khi test."""
    if fetch is None or extract is None:
        import trafilatura

        fetch = fetch or trafilatura.fetch_url
        extract = extract or (
            lambda html: trafilatura.extract(
                html, output_format="txt", include_comments=False, include_tables=True
            )
        )
    html = fetch(url)
    if not html:
        raise UnsupportedSourceError(f"Không tải được URL: {url}")
    text = extract(html)
    if not text or not text.strip():
        raise UnsupportedSourceError(f"Không trích được nội dung chính từ URL: {url}")
    return _single_page(text, url)


def _single_page(text: str, source: str) -> list[Page]:
    text = clean_text(text)
    if not text:
        log.warning("%s: tài liệu rỗng", source)
    return [Page(make_doc_id(text), source, None, text)]


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def load_source(value: str | Path, *, source: str | None = None, ocr=None) -> list[Page]:
    """Chọn loader theo URL hoặc đuôi file. `source` để đặt tên hiển thị (vd. tên file upload).
    `ocr`: engine OCR (vd. GeminiOCREngine) cho trang PDF scan và file ảnh; None = không OCR."""
    if isinstance(value, str) and is_url(value):
        return load_url(value)
    path = Path(value)
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return load_pdf(path, source=source, ocr=ocr)
    if suffix in DOCX_SUFFIXES:
        return load_docx(path, source=source)
    if suffix in TEXT_SUFFIXES:
        return load_text(path, source=source)
    if suffix in TABLE_SUFFIXES:
        return load_table(path, source=source)
    if suffix in IMAGE_SUFFIXES:
        return load_image(path, source=source, ocr=ocr)
    raise UnsupportedSourceError(
        f"Không hỗ trợ loại file {suffix!r} (chỉ PDF, DOCX, TXT/MD, CSV/XLSX, ảnh hoặc URL)"
    )


__all__ = [
    "FlaggedPage",
    "IMAGE_SUFFIXES",
    "OCRPage",
    "TablePage",
    "UnsupportedSourceError",
    "clean_text",
    "is_url",
    "load_docx",
    "load_image",
    "load_pdf",
    "load_source",
    "load_table",
    "table_pages",
    "load_text",
    "load_url",
    "pages_from_texts",
]
