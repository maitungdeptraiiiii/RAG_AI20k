"""Tách phần sau chữ ký của một văn bản (phụ lục, danh mục, biểu mẫu) từ raw text.

Chỉ đọc raw text; không đổi kết quả của `parse_structure` (lời văn điều khoản trong kho giữ nguyên).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rag.legal.structure import ARTICLE_RE

_SIGNATURE = re.compile(r"^(?:Nơi\s+nhận\s*:|TM\.\s|KT\.\s|TUQ\.\s|BỘ\s+TRƯỞNG\b|THỦ\s+TƯỚNG\b|CHỦ\s+TỊCH\s+QUỐC\s+HỘI\b|"
                        r"CHỦ\s+TỊCH\s+NƯỚC\b|CHÁNH\s+ÁN\b|VIỆN\s+TRƯỞNG\b)")
_APPENDIX_HEAD = re.compile(r"^(?:PHỤ\s+LỤC|Phụ\s+lục)(?:\s+(?:số\s+)?(?P<number>[IVXLC]+|\d+))?\s*[.:]?\s*(?P<rest>.*)$")
_FLAT_HEAD = re.compile(r"^(?:(?:MẪU|Mẫu)\s+(?:số\s+)?(?P<number>\d+\S*)|DANH\s+MỤC\b)")
_BLANKS = re.compile(r"\.{5,}|…{3,}")


@dataclass(frozen=True)
class AppendixPart:
    number: str                 # nhãn trong văn bản ("I", "01"); rỗng nếu không ghi
    title: str
    kind: str                   # list / form / other
    text: str
    span: tuple[int, int]


def _kind(title: str, body: str) -> str:
    lines = body.split("\n")
    if any(ARTICLE_RE.match(l.strip()) for l in lines) or sum(1 for l in lines if _BLANKS.search(l)) >= 3:
        return "form"
    if re.search(r"DANH\s+MỤC", title, re.IGNORECASE):
        return "list"
    return "other"


def split_appendices(text: str) -> tuple[int | None, list[AppendixPart]]:
    """(vị trí kết thúc phần thân, các phụ lục). Vị trí là None khi văn bản không có khối chữ ký / phần sau thân."""
    text = unicodedata.normalize("NFC", text)
    lines = text.split("\n")
    starts, pos = [], 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1
    seen: set[str] = set()
    body_end: int | None = None                       # chỉ số dòng đầu tiên ngoài phần thân
    for i, raw in enumerate(lines):
        line = raw.strip()
        m = ARTICLE_RE.match(line)
        if m:
            if m.group(1) in seen:                    # Điều lặp số: đã sang biểu mẫu
                body_end = i
                break
            seen.add(m.group(1))
        elif seen and _SIGNATURE.match(line):
            body_end = i
            break
    if body_end is None:
        return None, []
    heads: list[tuple[int, str]] = []                 # (dòng, số)
    for i in range(body_end, len(lines)):
        m = _APPENDIX_HEAD.match(lines[i].strip())
        if m and len(lines[i]) <= 200 and not m.group("rest").rstrip().endswith((".", ";", ",")):
            heads.append((i, m.group("number") or ""))
    if not heads:
        for i in range(body_end, len(lines)):
            m = _FLAT_HEAD.match(lines[i].strip())
            if m:
                heads.append((i, m.groupdict().get("number") or ""))
    parts = []
    for n, (i, number) in enumerate(heads):
        end_line = heads[n + 1][0] - 1 if n + 1 < len(heads) else len(lines) - 1
        while end_line > i and not lines[end_line].strip():
            end_line -= 1
        start = starts[i] + len(lines[i]) - len(lines[i].lstrip())
        end = starts[end_line] + len(lines[end_line].rstrip())
        body = text[start:end]
        nxt = next((l.strip() for l in lines[i + 1:end_line + 1] if l.strip()), "")
        head = lines[i].strip()
        title = f"{head} - {nxt}" if nxt and nxt == nxt.upper() and len(nxt) <= 200 else head
        parts.append(AppendixPart(number, title, _kind(title, body), body, (start, end)))
    return starts[body_end], parts


__all__ = ["AppendixPart", "split_appendices"]
