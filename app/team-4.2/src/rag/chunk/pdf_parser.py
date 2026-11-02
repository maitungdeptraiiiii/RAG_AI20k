"""PDF document parser producing `list[Page]` compliant with `rag.schema`.

Extracts per-page text, removes standalone header/footer page numbers,
and flags empty/scanned pages. Supports PyMuPDF (fitz) with automatic
fallback to pypdf.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

from rag.schema import Page, make_doc_id, nfc
from .models import ParseError


def _strip_page_numbers(lines: list[str]) -> list[str]:
    """Strip standalone page numbers from header or footer lines."""
    if not lines:
        return lines
    # Check top line (header page number, e.g. "1", " 24 ")
    if lines and re.match(r"^\d{1,4}$", lines[0]):
        lines = lines[1:]
    # Check bottom line (footer page number)
    if lines and re.match(r"^\d{1,4}$", lines[-1]):
        lines = lines[:-1]
    return lines


def _extract_with_fitz(data: bytes) -> list[tuple[int, str]]:
    """Extract page texts using PyMuPDF (fitz)."""
    import fitz  # type: ignore

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ParseError("PDF_PARSE_ERROR", f"Không đọc được PDF bằng PyMuPDF: {exc}") from exc

    if doc.is_encrypted:
        raise ParseError("PDF_ENCRYPTED", "PDF được mã hóa; hãy tải bản không có mật khẩu.")

    pages: list[tuple[int, str]] = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text() or ""
        pages.append((page_idx + 1, text))
    return pages


def _extract_with_pypdf(data: bytes) -> list[tuple[int, str]]:
    """Extract page texts using pypdf fallback."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise ParseError("PDF_PARSE_ERROR", f"Không đọc được PDF bằng pypdf: {exc}") from exc

    if reader.is_encrypted:
        raise ParseError("PDF_ENCRYPTED", "PDF được mã hóa; hãy tải bản không có mật khẩu.")

    pages: list[tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((idx, text))
    return pages


def parse_pdf(
    data: bytes,
    source: str = "document.pdf",
    doc_id: str | None = None,
) -> list[Page]:
    """Parse PDF bytes into a list of schema `Page` objects.

    Args:
        data: Raw PDF file bytes.
        source: Filename, path, or identifier for citations.
        doc_id: Unique document hash (defaults to `make_doc_id(data)`).

    Returns:
        A list of `Page` objects (1-indexed), normalized to NFC.

    Raises:
        ParseError: If file is encrypted, corrupt, or contains no extractable text.
    """
    if not data:
        raise ParseError("PDF_EMPTY_DATA", "Dữ liệu PDF rỗng.")

    computed_doc_id = doc_id or make_doc_id(data)
    clean_source = nfc(source.strip() or "document.pdf")

    # Try PyMuPDF first, fallback to pypdf
    raw_pages: list[tuple[int, str]]
    try:
        raw_pages = _extract_with_fitz(data)
    except ImportError:
        raw_pages = _extract_with_pypdf(data)

    if not raw_pages:
        raise ParseError("PDF_NO_PAGES", "Tài liệu PDF không có trang nào.")

    pages: list[Page] = []
    non_empty_count = 0

    for page_num, raw_text in raw_pages:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        lines = _strip_page_numbers(lines)
        page_text = nfc("\n".join(lines).strip())

        if page_text:
            non_empty_count += 1

        pages.append(
            Page(
                doc_id=computed_doc_id,
                source=clean_source,
                page=page_num,
                text=page_text,
            )
        )

    if non_empty_count == 0:
        raise ParseError(
            "PDF_NO_TEXT",
            "PDF không có văn bản trích xuất được; có thể là PDF scan (chưa hỗ trợ OCR).",
        )

    return pages


def load_pdf(path: Path | str, doc_id: str | None = None) -> list[Page]:
    """Read a local PDF file and parse it into `list[Page]`."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ParseError("FILE_NOT_FOUND", f"Không tìm thấy tệp PDF: {file_path}")

    data = file_path.read_bytes()
    return parse_pdf(data, source=file_path.name, doc_id=doc_id)
