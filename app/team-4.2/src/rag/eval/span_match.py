"""W02-04 — chấm "trúng Điều" theo VỊ TRÍ văn bản, dùng chung cho mọi chiến lược chunk.

Cách chấm mặc định (`GoldRef.matches`) so `section` của chunk với `section` gold. Chunk cố định cắt ngang Điều nên
không có `section` — so như vậy sẽ luôn trượt, không công bằng. Ở đây: định vị từng chunk trong văn bản gốc (đã gộp
khoảng trắng), định vị từng Điều (dòng mở đầu "Điều N." trong văn bản gốc), chunk "trúng" Điều nếu hai khoảng chồng
nhau. Chunk theo cấu trúc nằm gọn trong một Điều nên kết quả trùng với cách chấm cũ.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from rag.schema import Chunk

_HEADING = re.compile(r"^\s*Điều\s+(\d+[a-zđ]?)\s*[.:]", re.IGNORECASE)
_GOLD = re.compile(r"Điều\s+(\d+[a-zđ]?)\s*[.:]", re.IGNORECASE)
_PROBE = 80


def gold_article(section: str | None) -> str | None:
    m = _GOLD.search((section or "").rsplit(" > ", 1)[-1])
    return m.group(1).lower() if m else None


def _normalize(raw: str) -> tuple[str, list[int]]:
    """Gộp khoảng trắng thành một dấu cách; trả văn bản chuẩn hoá và vị trí chuẩn hoá của từng ký tự gốc."""
    raw = unicodedata.normalize("NFC", raw)
    out: list[str] = []
    to_norm: list[int] = []
    space = True
    for c in raw:
        to_norm.append(len(out))            # vị trí TRƯỚC khi thêm: ký tự gốc này nằm ở đâu trong văn bản chuẩn hoá
        if c.isspace():
            if not space:
                out.append(" ")
            space = True
        else:
            out.append(c)
            space = False
    return "".join(out), to_norm


def _norm_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


class ArticleIndex:
    """Khoảng ký tự của từng Điều và từng chunk của MỘT văn bản (cùng hệ toạ độ đã chuẩn hoá)."""

    def __init__(self, raw: str, chunks: Sequence[Chunk]) -> None:
        self.norm, to_norm = _normalize(raw)
        starts: list[tuple[str, int]] = []
        pos = 0
        for line in unicodedata.normalize("NFC", raw).split("\n"):
            m = _HEADING.match(line)
            if m:
                starts.append((m.group(1).lower(), to_norm[pos] if pos < len(to_norm) else len(self.norm)))
            pos += len(line) + 1
        self.articles: dict[str, tuple[int, int]] = {}
        for i, (label, start) in enumerate(starts):
            end = starts[i + 1][1] if i + 1 < len(starts) else len(self.norm)
            self.articles.setdefault(label, (start, end))
        self.chunks: dict[str, tuple[int, int]] = {}
        cursor = 0
        for c in chunks:
            text = _norm_text(c.text)
            if not text:
                continue
            head, tail = text[:_PROBE], text[-_PROBE:]
            start = self.norm.find(head, cursor)
            if start < 0:
                start = self.norm.find(head)
            if start < 0:
                continue
            end = self.norm.find(tail, start)
            end = start + len(text) if end < 0 else end + len(tail)
            self.chunks[c.chunk_id] = (start, end)
            cursor = start + 1

    def covers(self, chunk_id: str, article: str | None) -> bool:
        span, art = self.chunks.get(chunk_id), self.articles.get((article or "").lower())
        return bool(span and art and span[0] < art[1] and art[0] < span[1])


__all__ = ["ArticleIndex", "gold_article"]
