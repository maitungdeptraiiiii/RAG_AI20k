"""Kiểu dữ liệu dùng chung của đồ thị hợp đồng: trang, phần, đơn vị, giá trị, tham chiếu."""
from __future__ import annotations

import bisect
import unicodedata
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PageText:
    page: int | None
    text: str
    kind: str = "Page"


@dataclass(frozen=True)
class Assembled:
    text: str
    page_starts: list[tuple[int, int | None]]

    def page_at(self, offset: int) -> int | None:
        """Trang chứa ký tự ở vị trí offset."""
        offs = [o for o, _ in self.page_starts]
        i = bisect.bisect_right(offs, offset) - 1
        return self.page_starts[i][1] if i >= 0 else None


def assemble(pages: list[PageText]) -> Assembled:
    """Nối các trang bằng dòng trống, chuẩn hóa NFC và xuống dòng."""
    parts: list[str] = []
    starts: list[tuple[int, int | None]] = []
    pos = 0
    for i, p in enumerate(pages):
        t = unicodedata.normalize("NFC", p.text.replace("\r\n", "\n"))
        if i:
            pos += 2
        starts.append((pos, p.page))
        parts.append(t)
        pos += len(t)
    return Assembled("\n\n".join(parts), starts)


@dataclass(frozen=True)
class PartSpec:
    part_id: str
    kind: Literal["main", "appendix"]
    title: str
    start: int
    number: int | None


@dataclass(frozen=True)
class Unit:
    uid: str
    part_id: str
    parent_uid: str | None
    level: Literal["preamble", "article", "clause", "point", "paragraph"]
    number: str
    label: str
    text: str
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    version: int = 1


def own_texts(units: list[Unit]) -> dict[str, str]:
    """Văn bản riêng của mỗi đơn vị: đơn vị có con chỉ giữ đoạn dẫn trước con đầu tiên."""
    first: dict[str, int] = {}
    for u in units:
        if u.parent_uid:
            first[u.parent_uid] = min(first.get(u.parent_uid, u.char_start), u.char_start)
    return {u.uid: u.text[:max(0, first[u.uid] - u.char_start)] if u.uid in first else u.text
            for u in units}


@dataclass(frozen=True)
class Value:
    vid: str  # f"{uid}#v{i}", i từ 1 trong đơn vị
    uid: str
    kind: str
    raw: str
    norm: dict
    start: int
    end: int


@dataclass(frozen=True)
class CrossRef:
    from_uid: str
    to_uid: str | None
    raw: str
    kind: Literal["internal", "appendix", "external_law", "missing"]


@dataclass(frozen=True)
class ParseReport:
    styles: dict[str, str]
    counts: dict[str, int]
    gaps: list[str]
    unstructured_ratio: float
    warn_pages: list[int]
    warnings: list[str]


_TOP_LEVELS = ("preamble", "article", "paragraph")


@dataclass(frozen=True)
class ContractDoc:
    parts: list[PartSpec]
    units: list[Unit]
    values: list[Value]
    xrefs: list[CrossRef]
    report: ParseReport

    def unit(self, uid: str) -> Unit | None:
        return next((u for u in self.units if u.uid == uid), None)

    def children(self, uid: str) -> list[Unit]:
        """Con trực tiếp theo thứ tự."""
        return [u for u in self.units if u.parent_uid == uid]

    def top_units(self) -> list[Unit]:
        """Đơn vị cấp cao nhất (mở đầu, điều, đoạn) của mọi phần."""
        return [u for u in self.units if u.level in _TOP_LEVELS]
