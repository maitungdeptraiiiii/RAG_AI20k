"""Cây Điều / khoản / điểm của một phần hợp đồng, mã đơn vị ổn định theo cấu trúc."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from .doc import Assembled, PartSpec, Unit

_ARTICLE = re.compile(r"(?:Điều|ĐIỀU|Article|ARTICLE)\s+(\d+)([a-zđ]?)\s*[.:\-–]")
_ROMAN = re.compile(r"([IVXLC]+)\s*[.)]\s+\S")
_NUMERIC = re.compile(r"(?:Mục\s+)?(\d+)\s*[.)]\s+\S")
_CLAUSE = re.compile(r"(?:Khoản\s+)?(\d+)\s*[.)]\s+\S")
_CLAUSE_DOTTED = re.compile(r"(\d+)\.(\d+)\.?\s+\S")
_POINT = re.compile(r"([a-zđ])\s*[).]\s+\S")
_BLANK_LINES = re.compile(r"\n(?:[ \t]*\n)+")

_LETTERS = "abcdđeghiklmnopqrstuvxy"
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_STEP = 3          # số kế tiếp không vượt quá số trước + 3
_LETTER_STEP = 4   # điểm bỏ qua tối đa 3 chữ
_STYLES = (("dieu", 1), ("roman", 2), ("numeric", 2))  # kiểu, số tiêu đề tối thiểu
_DEPTH = {"article": 0, "clause": 1, "point": 2}


@dataclass(frozen=True)
class _Line:
    start: int  # vị trí ký tự khác trắng đầu tiên trong văn bản ghép
    text: str


@dataclass(frozen=True)
class _Head:
    start: int
    level: str
    uid: str
    parent_uid: str | None
    number: str
    label: str  # chưa có tiền tố phần


@dataclass
class _Top:
    head: _Head
    value: int
    suffix: str = ""


def _code(s: str) -> str:
    """Chữ đ trong mã viết là dd."""
    return s.replace("đ", "dd")


def _roman_to_int(s: str) -> int:
    total = 0
    for i, ch in enumerate(s):
        v = _ROMAN_VALUES[ch]
        total += -v if i + 1 < len(s) and _ROMAN_VALUES[s[i + 1]] > v else v
    return total


def _in_step(prev: int, n: int, step: int = _STEP) -> bool:
    """Số mới lớn hơn số trước và không vượt quá số trước + step (số trước 0 khi chưa có)."""
    return prev < n <= prev + step


def _lines(a: Assembled, start: int, end: int) -> Iterator[_Line]:
    pos = start
    for raw in a.text[start:end].split("\n"):
        s = raw.lstrip()
        if s:
            yield _Line(pos + len(raw) - len(s), s)
        pos += len(raw) + 1


def _trim(a: Assembled, cs: int, ce: int) -> tuple[int, int]:
    """Bỏ khoảng trắng hai đầu đoạn [cs, ce)."""
    while cs < ce and a.text[cs].isspace():
        cs += 1
    while ce > cs and a.text[ce - 1].isspace():
        ce -= 1
    return cs, ce


def _match_top(style: str, text: str) -> tuple[int, str, str] | None:
    """(giá trị số, số hiển thị, hậu tố) nếu dòng là tiêu đề cấp trên cùng của kiểu."""
    if style == "dieu":
        m = _ARTICLE.match(text)
        return (int(m.group(1)), m.group(1) + m.group(2), m.group(2)) if m else None
    if style == "roman":
        m = _ROMAN.match(text)
        return (_roman_to_int(m.group(1)), m.group(1), "") if m else None
    m = _NUMERIC.match(text)
    return (int(m.group(1)), m.group(1), "") if m else None


def _match_clause(style: str, text: str, parent_value: int) -> int | None:
    """Số khoản nếu dòng là khoản; kiểu numeric chỉ nhận dạng N.M."""
    m = _CLAUSE_DOTTED.match(text)
    if m:
        return int(m.group(2)) if int(m.group(1)) == parent_value else None
    if style == "numeric":
        return None
    m = _CLAUSE.match(text)
    return int(m.group(1)) if m else None


class _Scanner:
    """Duyệt các dòng một lượt, dựng tiêu đề theo một kiểu đánh số."""

    def __init__(self, part_id: str, style: str):
        self.pid = part_id
        self.style = style
        self.heads: list[_Head] = []
        self.gaps: list[str] = []
        self.top: _Top | None = None
        self.clause: _Head | None = None
        self.clause_no = 0
        self.letter_no = 0

    def feed(self, ln: _Line) -> None:
        if self._try_top(ln) or self.top is None:
            return
        if not self._try_clause(ln):
            self._try_point(ln)

    def _gap(self, prev_label: str, label: str) -> None:
        self.gaps.append(f"{self.pid}: sau {prev_label} là {label}")

    def _try_top(self, ln: _Line) -> bool:
        m = _match_top(self.style, ln.text)
        if not m:
            return False
        value, number, suffix = m
        prev = self.top
        prev_value = prev.value if prev else 0
        insert = bool(prev and suffix) and value == prev.value and suffix > prev.suffix
        if not (insert or _in_step(prev_value, value)):
            return False
        word = "Điều" if self.style == "dieu" else "Mục"
        head = _Head(ln.start, "article", f"{self.pid}.d{value}{_code(suffix)}", None,
                     number, f"{word} {number}")
        if prev and not insert and value > prev_value + 1:
            self._gap(prev.head.label, head.label)
        self.heads.append(head)
        self.top = _Top(head, value, suffix)
        self.clause, self.clause_no, self.letter_no = None, 0, 0
        return True

    def _try_clause(self, ln: _Line) -> bool:
        n = _match_clause(self.style, ln.text, self.top.value)
        if n is None or not _in_step(self.clause_no, n):
            return False
        art = self.top.head
        head = _Head(ln.start, "clause", f"{art.uid}.k{n}", art.uid, str(n), f"khoản {n} {art.label}")
        if self.clause and n > self.clause_no + 1:
            self._gap(self.clause.label, head.label)
        self.heads.append(head)
        self.clause, self.clause_no, self.letter_no = head, n, 0
        return True

    def _try_point(self, ln: _Line) -> bool:
        m = _POINT.match(ln.text)
        if not m or m.group(1) not in _LETTERS:
            return False
        letter = m.group(1)
        n = _LETTERS.index(letter) + 1
        if not _in_step(self.letter_no, n, _LETTER_STEP):
            return False
        parent = self.clause or self.top.head
        self.heads.append(_Head(ln.start, "point", f"{parent.uid}.{_code(letter)}", parent.uid,
                                letter, f"điểm {letter} {parent.label}"))
        self.letter_no = n
        return True


def _scan(lines: list[_Line], part_id: str, style: str) -> _Scanner:
    sc = _Scanner(part_id, style)
    for ln in lines:
        sc.feed(ln)
    return sc


def _make_unit(a: Assembled, part: PartSpec, cs: int, ce: int, *, uid: str, parent_uid: str | None,
               level: str, number: str, label: str) -> Unit:
    cs, ce = _trim(a, cs, ce)
    return Unit(uid, part.part_id, parent_uid, level, number, label, a.text[cs:ce], cs, ce,
                a.page_at(cs), a.page_at(max(ce - 1, cs)))


def _tree_units(a: Assembled, part: PartSpec, end: int, heads: list[_Head], prefix: str) -> list[Unit]:
    """Phần mở đầu và các đơn vị; văn bản mỗi đơn vị kéo đến tiêu đề kế tiếp cùng cấp hoặc cao hơn."""
    units: list[Unit] = []
    cs, ce = _trim(a, part.start, heads[0].start)
    if ce > cs:
        units.append(_make_unit(a, part, cs, ce, uid=f"{part.part_id}.pre", parent_uid=None,
                                level="preamble", number="", label=prefix + "Phần mở đầu"))
    for i, h in enumerate(heads):
        stop = next((x.start for x in heads[i + 1:] if _DEPTH[x.level] <= _DEPTH[h.level]), end)
        units.append(_make_unit(a, part, h.start, stop, uid=h.uid, parent_uid=h.parent_uid,
                                level=h.level, number=h.number, label=prefix + h.label))
    return units


def _paragraph_units(a: Assembled, part: PartSpec, end: int, prefix: str) -> list[Unit]:
    """Không có đánh số: tách đoạn theo dòng trống."""
    bounds, pos = [], part.start
    for m in _BLANK_LINES.finditer(a.text, part.start, end):
        bounds.append((pos, m.start()))
        pos = m.end()
    bounds.append((pos, end))
    units: list[Unit] = []
    for cs, ce in bounds:
        cs, ce = _trim(a, cs, ce)
        if ce > cs:
            i = len(units) + 1
            units.append(_make_unit(a, part, cs, ce, uid=f"{part.part_id}.o{i}", parent_uid=None,
                                    level="paragraph", number=str(i), label=f"{prefix}Đoạn {i}"))
    return units


def parse_part(a: Assembled, part: PartSpec, end: int, label_prefix: str) -> tuple[list[Unit], str, list[str]]:
    """Trả (đơn vị theo thứ tự cây, kiểu đánh số, danh sách chỗ đứt số) của phần [part.start, end)."""
    lines = list(_lines(a, part.start, end))
    for style, min_heads in _STYLES:
        sc = _scan(lines, part.part_id, style)
        if sum(h.level == "article" for h in sc.heads) >= min_heads:
            return _tree_units(a, part, end, sc.heads, label_prefix), style, sc.gaps
    return _paragraph_units(a, part, end, label_prefix), "paragraph", []
