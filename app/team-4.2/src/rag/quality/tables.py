"""Đọc CSV có cấu trúc mà không làm mất cell/header/note.

Đây là lõi tạm độc lập. Adapter của Nhóm 1 sẽ chuyển ``ParsedTable`` thành
``TableData``/``Block`` có Locator và provenance đầy đủ.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


@dataclass(frozen=True)
class ParsedTable:
    """Bảng nguồn: cell luôn giữ dạng chuỗi, kể cả khi trông như số."""

    headers: tuple[tuple[str, ...], ...]
    rows: tuple[tuple[str, ...], ...]
    notes: tuple[tuple[str, ...], ...]
    source_name: str

    def column_index(self, header: str) -> int:
        """Tìm cột trong hàng header cuối; không đoán tên cột gần đúng."""
        if not self.headers:
            raise KeyError("Bảng không có header")
        try:
            return self.headers[-1].index(header)
        except ValueError as error:
            raise KeyError(f"Không có cột {header!r}") from error


def parse_csv(path: str | Path, *, header_rows: int = 1, note_prefixes: tuple[str, ...] = ("Ghi chú",)) -> ParsedTable:
    """Đọc UTF-8 CSV, giữ nguyên cell rỗng, header nhiều tầng và ghi chú.

    ``header_rows`` là quyết định parser/config, không suy luận tự động để tránh
    nhầm hàng dữ liệu thành header. Một dòng bắt đầu bằng ``Ghi chú`` được tách
    khỏi rows nhưng vẫn được giữ nguyên trong ``notes``.
    """
    if header_rows < 1:
        raise ValueError("header_rows phải >= 1")
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        # Không trim: whitespace trong cell cũng là một phần của nguồn/provenance.
        cells = [tuple(cell for cell in row) for row in csv.reader(handle)]
    if len(cells) < header_rows:
        raise ValueError(f"{source}: không đủ {header_rows} hàng header")
    width = max((len(row) for row in cells), default=0)
    normalized = [row + ("",) * (width - len(row)) for row in cells]
    headers = tuple(normalized[:header_rows])
    rows: list[tuple[str, ...]] = []
    notes: list[tuple[str, ...]] = []
    for row in normalized[header_rows:]:
        if row and row[0] in note_prefixes:
            notes.append(row)
        else:
            rows.append(row)
    return ParsedTable(headers=headers, rows=tuple(rows), notes=tuple(notes), source_name=source.name)


def parse_xlsx(path: str | Path, *, header_rows: int = 1, note_prefixes: tuple[str, ...] = ("Ghi chú",)) -> ParsedTable:
    """Đọc sheet đầu của XLSX bằng thư viện chuẩn, không ép cell số sang float.

    Formula được giữ thành chuỗi ``=...``; định dạng hiển thị Excel không được
    suy diễn thành đơn vị/số vì phần đó cần config parser có provenance.
    """
    source = Path(path)
    with ZipFile(source) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(node.itertext()) for node in root.findall("{*}si")]
        sheets = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml"))
        if not sheets:
            raise ValueError(f"{source}: không có worksheet")
        root = ElementTree.fromstring(archive.read(sheets[0]))
    rows: list[tuple[str, ...]] = []
    for row in root.findall(".//{*}sheetData/{*}row"):
        values: dict[int, str] = {}
        for cell in row.findall("{*}c"):
            ref = cell.get("r", "A1")
            letters = "".join(char for char in ref if char.isalpha())
            column = 0
            for char in letters:
                column = column * 26 + ord(char.upper()) - ord("A") + 1
            cell_type = cell.get("t")
            formula = cell.find("{*}f")
            value = cell.findtext("{*}v", default="")
            if formula is not None:
                text = f"={formula.text or ''}"
            elif cell_type == "s" and value.isdigit() and int(value) < len(shared_strings):
                text = shared_strings[int(value)]
            elif cell_type == "inlineStr":
                text = "".join(cell.find("{*}is").itertext()) if cell.find("{*}is") is not None else ""
            else:
                text = value
            values[column - 1] = text
        rows.append(tuple(values.get(index, "") for index in range(max(values, default=-1) + 1)))
    return _from_rows(rows, source.name, header_rows=header_rows, note_prefixes=note_prefixes)


def _from_rows(cells: list[tuple[str, ...]], source_name: str, *, header_rows: int, note_prefixes: tuple[str, ...]) -> ParsedTable:
    """Áp dụng chung rule preservation sau khi reader đã trả cell nguồn."""
    if header_rows < 1:
        raise ValueError("header_rows phải >= 1")
    if len(cells) < header_rows:
        raise ValueError(f"{source_name}: không đủ {header_rows} hàng header")
    width = max((len(row) for row in cells), default=0)
    normalized = [row + ("",) * (width - len(row)) for row in cells]
    headers = tuple(normalized[:header_rows])
    rows: list[tuple[str, ...]] = []
    notes: list[tuple[str, ...]] = []
    for row in normalized[header_rows:]:
        if row and row[0] in note_prefixes:
            notes.append(row)
        else:
            rows.append(row)
    return ParsedTable(headers=headers, rows=tuple(rows), notes=tuple(notes), source_name=source_name)
