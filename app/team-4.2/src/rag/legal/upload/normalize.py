"""Text trích từ PDF/DOCX -> dạng một đơn vị một dòng như crawler vbpl tạo ra (`parse_structure` dựa vào ranh giới dòng).

Các bước: NFC + bỏ khoảng trắng thừa; bỏ dòng lặp ở đầu/cuối trang (tiêu đề, "Trang N", số trang trơn); ghép dòng bị
ngắt giữa câu; tách mỗi Điều / Chương / Mục / Phần / khoản / điểm ra một dòng — chỉ ở đầu dòng gốc hoặc ngay sau dấu
kết câu, nên tham chiếu giữa câu như "tại Điều 5 của Luật này" không bị tách. Đoạn trích dẫn “…” của luật sửa đổi cũng
được giữ mỗi đơn vị một dòng (dòng có thể mở đầu bằng dấu mở trích dẫn).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from rag.legal.effectivity import parse_effectivity
from rag.legal.structure import ARTICLE_RE, parse_structure

_Q = r"[\"“]?"
_ROMAN = r"[IVXLCDM]+[A-Za-z]?"
_ARTICLE = _Q + r"Điều\s+\d+[a-zđ]?\s*[.:]"
_CHAPTER = _Q + r"Chương\s+(?:" + _ROMAN + r"|\d+[a-z]?)\b"
_SECTION = _Q + r"Mục\s+\d+[a-z]?\b"
_PART = _Q + r"Phần\s+(?:thứ\s+\S+|" + _ROMAN + r"|\d+)\b"
_CLAUSE = _Q + r"\d{1,3}[a-zđ]?\.\s+\S"
_POINT = _Q + r"[a-zđ]\d?\)\s+\S"

_HEADING_START = re.compile("^(?:" + "|".join((_ARTICLE, _CHAPTER, _SECTION, _PART)) + ")")
_ITEM_START = re.compile("^(?:" + "|".join((_CLAUSE, _POINT)) + ")")
_MID_START = "(?:" + "|".join((_ARTICLE, _CLAUSE, _POINT, _CHAPTER + r"\s+[A-ZĐ]", _SECTION + r"\s+[A-ZĐ0-9]")) + ")"
_MID_SPLIT = re.compile(r"(?<=[.;:!?”\"])\s+(?=" + _MID_START + ")")
_TERMINATOR = re.compile(r"[.;:!?…”\"]$")
_PAGE_NO = re.compile(r"^(?:[-–—]\s*)?(?:(?:trang|page)\s+)?\d{1,4}(?:\s*(?:/|of|trên)\s*\d{1,4})?(?:\s*[-–—])?$", re.IGNORECASE)
_EDGE = 3


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", line).replace("\xa0", " ")).strip()


def _edge_indexes(lines: list[str]) -> set[int]:
    idx = [i for i, l in enumerate(lines) if l]
    return set(idx[:_EDGE]) | set(idx[-_EDGE:])


def _shape(line: str) -> str:
    return re.sub(r"\d+", "#", line).casefold()


def _strip_pages(pages: Sequence[str]) -> list[str]:
    cleaned = [[_clean(l) for l in page.split("\n")] for page in pages]
    counts: dict[str, int] = {}
    for lines in cleaned:
        for key in {_shape(lines[i]) for i in _edge_indexes(lines)}:
            counts[key] = counts.get(key, 0) + 1
    out: list[str] = []
    n = len(cleaned)
    for lines in cleaned:
        edge = _edge_indexes(lines)
        for i, line in enumerate(lines):
            if not line:
                continue
            if i in edge:
                if _PAGE_NO.match(line):
                    continue
                if (counts[_shape(line)] >= 2 and counts[_shape(line)] * 2 >= n
                        and not _HEADING_START.match(line) and not _ITEM_START.match(line)):
                    continue
            out.append(line)
    return out


def _joins(prev: str, prev_filled: bool, line: str) -> bool:
    """Dòng `line` (đã làm sạch) có nối vào dòng `prev` không (False: bắt đầu dòng mới). `prev_filled`: dòng vật lý
    trước không còn chỗ cho từ đầu của `line` (độ rộng dòng của tài liệu), tức là bị ngắt vì hết chỗ chứ không phải hết đoạn."""
    if _HEADING_START.match(line):
        return False
    heading = bool(_HEADING_START.match(prev))
    terminated = bool(_TERMINATOR.search(prev))
    if _ITEM_START.match(line):
        return not (terminated or heading)
    if prev_filled:
        return True
    if not (line[:1].isupper() or line[:1] in "\"“"):
        return True                                     # chữ thường/số tiếp theo: câu đang dở
    return not terminated and not heading


def normalize_legal_text(pages: Sequence[str]) -> str:
    lines = _strip_pages(pages)
    width = max((len(l) for l in lines), default=0)
    merged: list[str] = []
    prev_len = 0
    for line in lines:
        if merged and _joins(merged[-1], prev_len + 1 + len(line.split(" ", 1)[0]) > width, line):
            merged[-1] = f"{merged[-1]} {line}"
        else:
            merged.append(line)
        prev_len = len(line)
    out: list[str] = []
    for line in merged:
        out += [part.strip() for part in _MID_SPLIT.split(line) if part.strip()]
    return "\n".join(out)


@dataclass(frozen=True)
class StructureCheck:
    n_articles: int
    gaps: tuple[tuple[str, str], ...]
    has_effectivity_article: bool


def check_structure(text: str, key: str) -> StructureCheck:
    provisions = parse_structure(text, key)
    labels = [p.address.article for p in provisions if p.kind == "article"]
    numbers = [int(a) for a in labels if a.isdigit()]
    gaps = tuple((str(a), str(b)) for a, b in zip(numbers, numbers[1:]) if b != a + 1)
    return StructureCheck(len(labels), gaps, parse_effectivity(provisions).article is not None)


__all__ = ["StructureCheck", "check_structure", "normalize_legal_text"]
