"""PDF document parser with page-number cleaning and cross-page sentence stitching."""

from io import BytesIO
import re
from pypdf import PdfReader

from .chunker import normalize_text
from .models import ParseError, TextUnit


def parse_pdf(data: bytes) -> list[TextUnit]:
    """Extract TextUnits from PDF bytes with noise-filtering and cross-page merging.
    
    Filters out standalone page numbers at page headers/footers.
    If a sentence crosses over a page boundary without terminating punctuation,
    it is merged cleanly while tracking the full page span in `pages`.
    """
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("PDF_ENCRYPTED", "PDF được mã hóa; hãy tải bản không có mật khẩu.")

        raw_pages: list[tuple[int, list[str]]] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]

            # Strip standalone header/footer page numbers (e.g. "2", "  8  ")
            if lines and re.match(r"^\d{1,4}$", lines[0]):
                lines = lines[1:]
            if lines and re.match(r"^\d{1,4}$", lines[-1]):
                lines = lines[:-1]

            if lines:
                raw_pages.append((index, lines))

    except ParseError:
        raise
    except Exception:
        raise ParseError("PDF_PARSE_ERROR", "Không đọc được PDF; tệp có thể bị hỏng.") from None

    if not raw_pages:
        raise ParseError("PDF_NO_TEXT", "PDF không có văn bản trích xuất được; chưa hỗ trợ OCR.")

    units: list[TextUnit] = []
    current_lines: list[str] = []
    current_pages: list[int] = []

    for page_num, lines in raw_pages:
        if not current_lines:
            current_lines = list(lines)
            current_pages = [page_num]
            continue

        # Check if the previous page ended without sentence-ending punctuation
        last_line = current_lines[-1]
        first_line = lines[0]

        # Conditions to stitch across page boundary:
        # 1. Last line does NOT end with sentence terminator: '.', '!', '?', ':'
        # 2. First line of next page does NOT start a new major heading ('Chương', 'Điều', 'Phần')
        is_sentence_cut = not re.search(r"[.!?:]\s*$", last_line)
        is_new_section = bool(re.match(r"^(?:Chương|Điều|Phần|Mục)\s+\d+", first_line, re.IGNORECASE))

        if is_sentence_cut and not is_new_section:
            # Check for trailing hyphenation (e.g. "chính-" and "thức")
            if last_line.endswith("-"):
                current_lines[-1] = last_line[:-1] + lines[0]
                current_lines.extend(lines[1:])
            else:
                current_lines.extend(lines)
            if page_num not in current_pages:
                current_pages.append(page_num)
        else:
            # Finalize previous unit
            unit_text = normalize_text("\n".join(current_lines))
            if unit_text:
                units.append(TextUnit(
                    text=unit_text,
                    page=current_pages[0],
                    pages=tuple(current_pages),
                ))
            current_lines = list(lines)
            current_pages = [page_num]

    if current_lines:
        unit_text = normalize_text("\n".join(current_lines))
        if unit_text:
            units.append(TextUnit(
                text=unit_text,
                page=current_pages[0],
                pages=tuple(current_pages),
            ))

    if not units:
        raise ParseError("PDF_NO_TEXT", "PDF không có văn bản trích xuất được; chưa hỗ trợ OCR.")

    return units
