"""Bảng CSV / XLSX / DOCX -> ParsedTable -> Chunk có cấu trúc — W02-02b.

    load_csv_tables(path)    encoding UTF-8 / UTF-8-BOM / UTF-16 / cp1258, delimiter tự dò (, ; tab |)
    load_xlsx_tables(path)   mọi sheet, bỏ hàng trống, ô gộp (mergeCells) điền lại giá trị ô gốc
    docx_tables(doc)         bảng trong DOCX có cấu trúc (header lặp tblHeader, caption, dòng đơn vị)
    chunk_tables(...)        Markdown table, LẶP LẠI caption + đơn vị + header ở mọi chunk,
                             bảng dài cắt theo nhóm hàng, ghi "Hàng a–b/N"; section = "table:<i>"

Cell luôn giữ dạng chuỗi (không ép float). Dòng "Đơn vị: ..." / "Đơn vị tính: ..." và caption
("Bảng ...", "Phụ lục ...") phía trên bảng, cùng dòng "Ghi chú ..." phía dưới, được tách riêng
nhưng không bị mất.

``row_range`` và ``table_id`` hiện nằm trong ``Chunk.section`` ("table:<i>") và dòng "Hàng a–b/N"
của text, vì ``Chunk`` chưa có trường riêng; khi Nhóm 1 mở rộng schema (W02-02a) chỉ cần điền thêm.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

from rag.schema import Chunk, make_chunk_id, nfc

CSV_SUFFIXES = {".csv", ".tsv"}
XLSX_SUFFIXES = {".xlsx", ".xlsm"}
TABLE_SUFFIXES = CSV_SUFFIXES | XLSX_SUFFIXES

NOTE_PREFIXES: tuple[str, ...] = ("Ghi chú", "Chú thích", "Nguồn", "Lưu ý")
_UNIT_RE = re.compile(r"^\s*\(?\s*Đơn\s*vị(?:\s*tính)?\s*[:：]\s*(?P<unit>.+?)\s*\)?\s*$", re.IGNORECASE)
_CAPTION_RE = re.compile(r"^\s*(Bảng|Biểu|Phụ\s*lục|Danh\s*mục)\b", re.IGNORECASE)

DEFAULT_MAX_ROWS = 25


@dataclass(frozen=True)
class ParsedTable:
    """Bảng nguồn: cell luôn giữ dạng chuỗi, kể cả khi trông như số."""

    headers: tuple[tuple[str, ...], ...]
    rows: tuple[tuple[str, ...], ...]
    notes: tuple[tuple[str, ...], ...]
    source_name: str
    caption: str | None = None
    unit: str | None = None          # từ dòng "Đơn vị: ..." quanh bảng
    sheet: str | None = None         # tên sheet XLSX
    index: int = 0                   # thứ tự bảng trong tài liệu -> "table:<index>"
    page: int | None = None          # trang nguồn (bảng OCR từ PDF scan/ảnh) -> citation trang

    @property
    def table_id(self) -> str:
        return f"table:{self.index}"

    @property
    def width(self) -> int:
        return max((len(r) for r in (*self.headers, *self.rows)), default=0)

    def column_labels(self) -> tuple[str, ...]:
        """Header nhiều tầng -> một nhãn mỗi cột, vd. 'Thực tế áp dụng / Áp dụng'.

        Tầng trên bị để trống (do ô gộp ngang) được điền tiếp từ ô bên trái.
        """
        levels: list[list[str]] = []
        for header in self.headers:
            filled: list[str] = []
            last = ""
            for i in range(self.width):
                cell = header[i].strip() if i < len(header) else ""
                if cell:
                    last = cell
                elif header is not self.headers[-1]:
                    cell = last
                filled.append(cell)
            levels.append(filled)
        labels: list[str] = []
        for i in range(self.width):
            parts: list[str] = []
            for level in levels:
                if level[i] and (not parts or parts[-1] != level[i]):
                    parts.append(level[i])
            labels.append(" / ".join(parts) or f"Cột {i + 1}")
        return tuple(labels)

    def column_index(self, header: str) -> int:
        """Tìm cột trong hàng header cuối; không đoán tên cột gần đúng."""
        if not self.headers:
            raise KeyError("Bảng không có header")
        try:
            return self.headers[-1].index(header)
        except ValueError as error:
            raise KeyError(f"Không có cột {header!r}") from error

    def find_column(self, *names: str) -> int | None:
        """Cột đầu tiên có nhãn (không phân biệt hoa thường) chứa một trong ``names``."""
        labels = [label.casefold() for label in self.column_labels()]
        for name in names:
            for i, label in enumerate(labels):
                if name.casefold() in label:
                    return i
        return None


# ---------------------------------------------------------------------------
# Tách caption / đơn vị / header / ghi chú
# ---------------------------------------------------------------------------


def _non_empty(row: Sequence[str]) -> list[str]:
    return [c for c in row if c.strip()]


def _single_value(row: Sequence[str]) -> str | None:
    """Giá trị duy nhất của hàng nếu hàng chỉ có 1 ô, hoặc mọi ô giống nhau (ô gộp ngang đã điền lại)."""
    values = {c.strip() for c in row if c.strip()}
    return values.pop() if len(values) == 1 else None


def _from_rows(
    cells: list[tuple[str, ...]],
    source_name: str,
    *,
    header_rows: int,
    note_prefixes: tuple[str, ...] = NOTE_PREFIXES,
    caption: str | None = None,
    unit: str | None = None,
    sheet: str | None = None,
    index: int = 0,
) -> ParsedTable:
    """Rule chung sau khi reader đã trả cell nguồn (không trim nội dung cell)."""
    if header_rows < 1:
        raise ValueError("header_rows phải >= 1")
    rows = [tuple(nfc(c) for c in row) for row in cells if _non_empty(row)]   # bỏ hàng trống
    # Dòng chỉ có 1 ô ở đầu bảng: caption hoặc "Đơn vị: ..."
    captions: list[str] = [caption] if caption else []
    multi_column = any(_single_value(r) is None for r in rows)   # bảng 1 cột: không có preamble
    while multi_column and rows and _single_value(rows[0]) is not None and len(rows) > header_rows:
        text = _single_value(rows[0]) or ""
        m = _UNIT_RE.match(text)
        if m:
            unit = unit or m.group("unit")
        elif _CAPTION_RE.match(text) or not captions:
            captions.append(text)
        else:
            break
        rows.pop(0)
    if len(rows) < header_rows:
        raise ValueError(f"{source_name}: không đủ {header_rows} hàng header")
    width = max((len(r) for r in rows), default=0)
    normalized = [r + ("",) * (width - len(r)) for r in rows]
    headers = tuple(normalized[:header_rows])
    body: list[tuple[str, ...]] = []
    notes: list[tuple[str, ...]] = []
    for row in normalized[header_rows:]:
        first = row[0].strip() if row else ""
        single = _single_value(row)
        m = _UNIT_RE.match(single) if single and first else None
        if m:
            unit = unit or m.group("unit")
            notes.append(row)
        elif first.startswith(note_prefixes):
            notes.append(row)
        else:
            body.append(row)
    return ParsedTable(
        headers=headers, rows=tuple(body), notes=tuple(notes), source_name=source_name,
        caption=" — ".join(captions) or None, unit=unit, sheet=sheet, index=index,
    )


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1258")   # Windows tiếng Việt; nhận mọi byte nên đặt cuối


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def parse_csv(
    path: str | Path,
    *,
    header_rows: int = 1,
    note_prefixes: tuple[str, ...] = NOTE_PREFIXES,
    delimiter: str | None = None,
) -> ParsedTable:
    """Đọc một bảng CSV, giữ nguyên cell rỗng, header nhiều tầng và ghi chú.

    ``header_rows`` là quyết định của caller/config, không suy luận tự động để tránh
    nhầm hàng dữ liệu thành header.
    """
    source = Path(path)
    text = _decode(source.read_bytes())
    delim = delimiter or _sniff_delimiter(text)
    cells = [tuple(row) for row in csv.reader(io.StringIO(text, newline=""), delimiter=delim)]
    return _from_rows(cells, source.name, header_rows=header_rows, note_prefixes=note_prefixes)


def load_csv_tables(path: str | Path, *, header_rows: int = 1) -> list[ParsedTable]:
    return [parse_csv(path, header_rows=header_rows)]


# ---------------------------------------------------------------------------
# XLSX (thư viện chuẩn, không cần openpyxl)
# ---------------------------------------------------------------------------

_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - ord("A") + 1
    return n - 1


def _parse_ref(ref: str) -> tuple[int, int]:
    m = _REF_RE.match(ref.upper().replace("$", ""))
    if not m:
        raise ValueError(f"Ô không hợp lệ: {ref}")
    return int(m.group(2)) - 1, _col_index(m.group(1))


def _sheet_paths(archive: ZipFile) -> list[tuple[str, str]]:
    """[(tên sheet, đường dẫn xml)] theo thứ tự trong workbook."""
    names = archive.namelist()
    if "xl/workbook.xml" not in names:
        return [(PurePosixPath(n).stem, n) for n in sorted(n for n in names if n.startswith("xl/worksheets/sheet"))]
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels")):
            target = rel.get("Target", "")
            target = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            rels[rel.get("Id", "")] = target
    out: list[tuple[str, str]] = []
    for sheet in workbook.iter():
        if not sheet.tag.endswith("}sheet"):
            continue
        rid = next((v for k, v in sheet.attrib.items() if k.endswith("}id")), None)
        path = rels.get(rid or "")
        if path and path in names:
            out.append((sheet.get("name", PurePosixPath(path).stem), path))
    return out


def _read_sheet(xml: bytes, shared: list[str]) -> list[tuple[str, ...]]:
    root = ElementTree.fromstring(xml)
    grid: dict[tuple[int, int], str] = {}
    for row in root.findall(".//{*}sheetData/{*}row"):
        r_default = int(row.get("r", "0")) - 1
        for c_pos, cell in enumerate(row.findall("{*}c")):
            ref = cell.get("r")
            r, c = _parse_ref(ref) if ref else (r_default, c_pos)
            cell_type = cell.get("t")
            formula = cell.find("{*}f")
            value = cell.findtext("{*}v", default="")
            if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                text = shared[int(value)]
            elif cell_type == "inlineStr":
                node = cell.find("{*}is")
                text = "".join(node.itertext()) if node is not None else ""
            elif formula is not None and not value:
                text = f"={formula.text or ''}"     # công thức chưa có giá trị cache
            else:
                text = value
            grid[(r, c)] = text
    # ô gộp: điền giá trị ô trên-trái vào cả vùng
    for merge in root.findall(".//{*}mergeCells/{*}mergeCell"):
        start, _, end = merge.get("ref", "").partition(":")
        if not end:
            continue
        (r0, c0), (r1, c1) = _parse_ref(start), _parse_ref(end)
        value = grid.get((r0, c0), "")
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                grid[(r, c)] = value
    if not grid:
        return []
    n_rows = max(r for r, _ in grid) + 1
    n_cols = max(c for _, c in grid) + 1
    return [tuple(grid.get((r, c), "") for c in range(n_cols)) for r in range(n_rows)]


def load_xlsx_tables(path: str | Path, *, header_rows: int = 1) -> list[ParsedTable]:
    """Mỗi sheet có dữ liệu là một bảng; sheet trống bị bỏ qua."""
    source = Path(path)
    with ZipFile(source) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(si.itertext()) for si in root.findall("{*}si")]
        sheets = _sheet_paths(archive)
        if not sheets:
            raise ValueError(f"{source}: không có worksheet")
        tables: list[ParsedTable] = []
        for name, sheet_path in sheets:
            cells = _read_sheet(archive.read(sheet_path), shared)
            if not any(_non_empty(r) for r in cells):
                continue
            tables.append(_from_rows(cells, source.name, header_rows=header_rows, sheet=name, index=len(tables)))
    return tables


def parse_xlsx(path: str | Path, *, header_rows: int = 1, note_prefixes: tuple[str, ...] = NOTE_PREFIXES) -> ParsedTable:
    """Tương thích ngược: chỉ trả sheet đầu tiên."""
    tables = load_xlsx_tables(path, header_rows=header_rows)
    if not tables:
        raise ValueError(f"{path}: không có sheet có dữ liệu")
    return tables[0]


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _docx_header_rows(table) -> int:
    """Số hàng đầu được đánh dấu 'lặp header' (w:tblHeader); mặc định 1."""
    n = 0
    for row in table.rows:
        tr_pr = row._tr.trPr
        if tr_pr is not None and any(child.tag.endswith("}tblHeader") for child in tr_pr):
            n += 1
        else:
            break
    return max(n, 1)


def docx_tables(doc, source_name: str) -> list[ParsedTable]:
    """Bảng trong DOCX theo thứ tự; ô gộp ngang được python-docx lặp lại -> header không bị lệch cột.

    Caption = đoạn ngay trước bảng nếu bắt đầu bằng 'Bảng/Phụ lục/...';
    đơn vị = đoạn 'Đơn vị: ...' ngay trước hoặc ngay sau bảng.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    items = list(doc.iter_inner_content())
    tables: list[ParsedTable] = []
    for pos, item in enumerate(items):
        if not isinstance(item, Table):
            continue
        cells = [tuple(" ".join(cell.text.split()) for cell in row.cells) for row in item.rows]
        caption = unit = None
        before = [p.text.strip() for p in items[max(0, pos - 2):pos] if isinstance(p, Paragraph) and p.text.strip()]
        after = items[pos + 1] if pos + 1 < len(items) else None
        for text in before:
            m = _UNIT_RE.match(text)
            if m:
                unit = m.group("unit")
            elif _CAPTION_RE.match(text):
                caption = text
        if isinstance(after, Paragraph):
            m = _UNIT_RE.match(after.text.strip())
            if m and unit is None:
                unit = m.group("unit")
        if not any(_non_empty(r) for r in cells):
            continue
        header_rows = min(_docx_header_rows(item), len(cells))
        tables.append(_from_rows(cells, source_name, header_rows=header_rows,
                                 caption=caption, unit=unit, index=len(tables)))
    return tables


def load_docx_tables(path: str | Path) -> list[ParsedTable]:
    import docx

    source = Path(path)
    return docx_tables(docx.Document(str(source)), source.name)


def load_tables(path: str | Path, *, header_rows: int = 1) -> list[ParsedTable]:
    suffix = Path(path).suffix.lower()
    if suffix in CSV_SUFFIXES:
        return load_csv_tables(path, header_rows=header_rows)
    if suffix in XLSX_SUFFIXES:
        return load_xlsx_tables(path, header_rows=header_rows)
    if suffix == ".docx":
        return load_docx_tables(path)
    raise ValueError(f"Không hỗ trợ bảng từ {suffix!r}")


# ---------------------------------------------------------------------------
# Biểu diễn + chunking
# ---------------------------------------------------------------------------


def _md_cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def table_preamble(table: ParsedTable) -> list[str]:
    lines: list[str] = []
    if table.caption:
        lines.append(f"Bảng: {table.caption}")
    if table.sheet:
        lines.append(f"Sheet: {table.sheet}")
    if table.unit:
        lines.append(f"Đơn vị: {table.unit}")
    return lines


def table_markdown(table: ParsedTable, rows: Sequence[tuple[str, ...]] | None = None) -> str:
    """Markdown của bảng (hoặc một nhóm hàng), luôn kèm caption, đơn vị, header và ghi chú."""
    labels = table.column_labels()
    body = table.rows if rows is None else rows
    lines = table_preamble(table)
    lines.append("| " + " | ".join(_md_cell(label) for label in labels) + " |")
    lines.append("|" + "---|" * len(labels))
    for row in body:
        padded = tuple(row) + ("",) * (len(labels) - len(row))
        lines.append("| " + " | ".join(_md_cell(c) for c in padded[: len(labels)]) + " |")
    for note in table.notes:
        text = " ".join(c.strip() for c in note if c.strip())
        if text:
            lines.append(text)
    return nfc("\n".join(lines))


def chunk_tables(
    tables: Sequence[ParsedTable],
    *,
    doc_id: str,
    source: str,
    start_index: int = 0,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_syllables: int | None = None,
) -> list[Chunk]:
    """Mỗi chunk = một nhóm hàng liên tiếp + caption/đơn vị/header/ghi chú lặp lại.

    Cắt khi đủ ``max_rows`` hàng hoặc vượt ``max_syllables`` âm tiết (nếu có). Không bao giờ
    cắt giữa một hàng. ``section`` = ``table:<i>`` để gold eval trỏ ổn định theo bảng.
    """
    if max_rows < 1:
        raise ValueError("max_rows phải >= 1")
    from rag.ingest.chunker import count_syllables

    chunks: list[Chunk] = []
    for table in tables:
        groups: list[list[tuple[str, ...]]] = []
        current: list[tuple[str, ...]] = []
        for row in table.rows:
            candidate = [*current, row]
            too_long = max_syllables is not None and current and \
                count_syllables(table_markdown(table, candidate)) > max_syllables
            if current and (len(current) >= max_rows or too_long):
                groups.append(current)
                candidate = [row]
            current = candidate
        groups.append(current)        # bảng không có hàng dữ liệu vẫn ra 1 chunk header
        n_rows = len(table.rows)
        first = 1
        for group in groups:
            text = table_markdown(table, group)
            if len(groups) > 1:
                text += f"\n(Hàng {first}–{first + len(group) - 1}/{n_rows})"
            first += len(group)
            chunks.append(Chunk(
                chunk_id=make_chunk_id(doc_id, start_index + len(chunks)),
                doc_id=doc_id, source=source, page_start=table.page, page_end=table.page,
                section=table.table_id, text=text,
            ))
    return chunks


def mask_table(table: ParsedTable, state=None) -> tuple[ParsedTable, tuple]:
    """Mask PII trong caption, header, hàng và ghi chú. Cột có header gợi ý PII bị mask nguyên ô."""
    from rag.quality.pii import MaskState, column_pii_type, mask_cells, mask_text

    state = state or MaskState()
    prefix = f"{table.table_id}/"
    column_types = {i: kind for i, label in enumerate(table.column_labels()) if (kind := column_pii_type(label))}
    rows, f_rows = mask_cells(table.rows, column_types=column_types, state=state, location_prefix=prefix)
    headers, f_head = mask_cells(table.headers, state=state, location_prefix=f"{prefix}header/")
    notes, f_notes = mask_cells(table.notes, state=state, location_prefix=f"{prefix}note/")
    caption = table.caption
    f_cap: tuple = ()
    if caption:
        result = mask_text(caption, state=state, location=f"{prefix}caption")
        caption, f_cap = result.masked_text, result.safe_findings
    masked = replace(table, headers=headers, rows=rows, notes=notes, caption=caption)
    return masked, (*f_cap, *f_head, *f_rows, *f_notes)


__all__ = [
    "CSV_SUFFIXES",
    "TABLE_SUFFIXES",
    "XLSX_SUFFIXES",
    "ParsedTable",
    "chunk_tables",
    "docx_tables",
    "load_csv_tables",
    "load_docx_tables",
    "load_tables",
    "load_xlsx_tables",
    "mask_table",
    "parse_csv",
    "parse_xlsx",
    "table_markdown",
]
