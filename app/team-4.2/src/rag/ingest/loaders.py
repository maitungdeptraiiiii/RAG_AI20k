"""Parsing PDF / DOCX / URL / TXT -> list[Page] — TV1.

    load_pdf(path)   PyMuPDF, mỗi trang một Page (page đánh số từ 1); doc_id = hash bytes file
    load_docx(path)  python-docx, đoạn văn + bảng theo thứ tự; một Page (page=None); doc_id = hash bytes file
    load_url(url)    trafilatura lấy nội dung chính; một Page (page=None); doc_id = hash text
    load_text(path)  file text UTF-8; một Page (page=None); doc_id = hash text
    load_source(x)   tự chọn loader theo URL / đuôi file

Text được chuẩn hoá NFC và dọn khoảng trắng. Trang rỗng (thường là PDF scan, không có lớp text)
vẫn giữ lại nhưng ghi cảnh báo; chunker sẽ bỏ qua trang rỗng. PDF scan cần OCR — ngoài phạm vi
baseline (Law_RAG dùng OCR cho trường hợp này).
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

from rag.schema import Page, make_doc_id, nfc

log = logging.getLogger(__name__)

_SPACES_RE = re.compile(r"[ \t ​]+")
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")

PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
TEXT_SUFFIXES = {".txt", ".md", ".text"}


class UnsupportedSourceError(ValueError):
    pass


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


def load_pdf(path: Path | str, *, source: str | None = None) -> list[Page]:
    import fitz  # PyMuPDF

    path = Path(path)
    data = path.read_bytes()
    with fitz.open(stream=data, filetype="pdf") as doc:
        texts = [page.get_text("text") for page in doc]
    return pages_from_texts(make_doc_id(data), source or path.name, texts)


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
    return [Page(make_doc_id(data), name, None, text)]


def load_text(path: Path | str, *, source: str | None = None) -> list[Page]:
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise UnsupportedSourceError(f"{path.name}: file text phải mã hoá UTF-8") from e
    return _single_page(text, source or path.name)


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


def load_source(value: str | Path, *, source: str | None = None) -> list[Page]:
    """Chọn loader theo URL hoặc đuôi file. `source` để đặt tên hiển thị (vd. tên file upload)."""
    if isinstance(value, str) and is_url(value):
        return load_url(value)
    path = Path(value)
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return load_pdf(path, source=source)
    if suffix in DOCX_SUFFIXES:
        return load_docx(path, source=source)
    if suffix in TEXT_SUFFIXES:
        return load_text(path, source=source)
    raise UnsupportedSourceError(
        f"Không hỗ trợ loại file {suffix!r} (chỉ PDF, DOCX, TXT/MD hoặc URL)"
    )


__all__ = [
    "UnsupportedSourceError",
    "clean_text",
    "is_url",
    "load_docx",
    "load_pdf",
    "load_source",
    "load_text",
    "load_url",
    "pages_from_texts",
]
