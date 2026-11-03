"""Chunking: list[Page] -> list[Chunk] — TV1.

Quy tắc (theo phan_cong_sprint1.md):
- Gom đoạn văn đến khoảng `max_syllables` âm tiết (mặc định 300), overlap 1 đoạn với chunk trước.
- Giữ `page_start` / `page_end` khi chunk vắt qua trang.
- `section` = heading gần nhất, dạng "Chương II > Mục 1 > Điều 5. Tên điều".
- `chunk_id` = make_chunk_id(doc_id, i): ingest lại cùng tài liệu ra cùng id, không nhân đôi.

Với văn bản luật (tham khảo Law_RAG/upload_pipeline.py):
- Dòng "Phần/Chương/Mục ..." chỉ cập nhật `section`, không thành đoạn riêng.
- Dòng "Điều N." bắt đầu chunk mới (không overlap qua ranh giới Điều) và nằm trong text chunk.
- Khoản "1." và điểm "a)" luôn bắt đầu đoạn mới.
Tài liệu thường (không có heading luật) thì `section` = None, chỉ gom theo độ dài.

PDF hay ngắt dòng giữa câu: dòng bắt đầu bằng chữ thường, nối tiếp dòng trước chưa kết thúc câu,
được gộp vào cùng đoạn (kể cả khi đoạn vắt qua trang).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from rag.schema import Chunk, Page, make_chunk_id

PART_RE = re.compile(r"^Phần\s+(thứ\s+)?\S+", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^Chương\s+[IVXLCDM\d]+\b", re.IGNORECASE)
SECTION_RE = re.compile(r"^(Tiểu mục|Mục)\s+\d+\b", re.IGNORECASE)
ARTICLE_RE = re.compile(r"^Điều\s+\d+[a-zđ]?\s*[.:]", re.IGNORECASE)
LIST_ITEM_RE = re.compile(r"^(\d+[a-z]?[.)]|[a-zđ][.)])\s+", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[.:;!?…\"”)\]]$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")

_LEVELS = {"part": 0, "chapter": 1, "section": 2, "article": 3}


@dataclass
class _Para:
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None
    boundary: bool          # bắt đầu Điều / Chương mới -> phải mở chunk mới

    @property
    def size(self) -> int:
        return len(self.text.split())


def count_syllables(text: str) -> int:
    return len(text.split())


def _heading_level(line: str) -> str | None:
    if ARTICLE_RE.match(line):
        return "article"
    if SECTION_RE.match(line):
        return "section"
    if CHAPTER_RE.match(line):
        return "chapter"
    if PART_RE.match(line) and len(line.split()) <= 12:
        return "part"
    return None


def _is_title_line(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and line == line.upper() and len(line.split()) <= 20


def _paragraphs(pages: Sequence[Page]) -> list[_Para]:
    stack: list[str | None] = [None] * len(_LEVELS)
    paras: list[_Para] = []
    pending_boundary = False

    def section() -> str | None:
        parts = [s for s in stack if s]
        return " > ".join(parts) if parts else None

    for page in pages:
        if page.is_empty:
            continue
        lines = [ln.strip() for ln in page.text.split("\n")]
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            if not line:
                # dòng trống: đoạn sau là đoạn mới -> chèn mốc rỗng để không gộp nối tiếp
                if paras and paras[-1].text:
                    paras.append(_Para("", page.page, page.page, section(), False))
                continue

            level = _heading_level(line)
            if level in ("part", "chapter", "section"):
                # "Chương I" + dòng tiêu đề viết HOA ở dòng sau -> gộp
                if i < len(lines) and lines[i] and _is_title_line(lines[i]) and not _heading_level(lines[i]):
                    line = f"{line} {lines[i]}"
                    i += 1
                lv = _LEVELS[level]
                stack[lv] = line
                for deeper in range(lv + 1, len(stack)):
                    stack[deeper] = None
                pending_boundary = True
                continue
            if level == "article":
                stack[_LEVELS["article"]] = line
                paras.append(_Para(line, page.page, page.page, section(), True))
                pending_boundary = False
                continue

            prev = paras[-1] if paras else None
            continues = (
                prev is not None
                and prev.text
                and not SENTENCE_END_RE.search(prev.text)
                and not LIST_ITEM_RE.match(line)
                and line[:1].islower()
            )
            if continues:
                prev.text = f"{prev.text} {line}"
                prev.page_end = page.page
            else:
                paras.append(_Para(line, page.page, page.page, section(), pending_boundary))
                pending_boundary = False

    return [p for p in paras if p.text]


def _split_long(para: _Para, max_syllables: int) -> list[_Para]:
    """Đoạn dài hơn giới hạn: tách theo câu, câu quá dài thì cắt theo cửa sổ âm tiết."""
    if para.size <= max_syllables:
        return [para]
    pieces: list[str] = []
    current: list[str] = []
    for sentence in SENTENCE_SPLIT_RE.split(para.text):
        words = sentence.split()
        if len(words) > max_syllables:
            if current:
                pieces.append(" ".join(current))
                current = []
            for start in range(0, len(words), max_syllables):
                pieces.append(" ".join(words[start : start + max_syllables]))
            continue
        if current and len(current) + len(words) > max_syllables:
            pieces.append(" ".join(current))
            current = []
        current.extend(words)
    if current:
        pieces.append(" ".join(current))
    return [
        _Para(text, para.page_start, para.page_end, para.section, para.boundary and i == 0)
        for i, text in enumerate(pieces)
    ]


def chunk_document(
    pages: Sequence[Page], *, max_syllables: int = 300, overlap: bool = True
) -> list[Chunk]:
    if max_syllables < 1:
        raise ValueError("max_syllables phải >= 1")
    if not pages:
        return []
    doc_ids = {p.doc_id for p in pages}
    if len(doc_ids) != 1:
        raise ValueError(f"Các Page phải cùng doc_id, nhận {sorted(doc_ids)}")
    doc_id, source = pages[0].doc_id, pages[0].source

    paras = [piece for p in _paragraphs(pages) for piece in _split_long(p, max_syllables)]

    groups: list[tuple[list[_Para], int]] = []   # (đoạn, số đoạn overlap ở đầu)
    current: list[_Para] = []
    n_overlap = 0
    size = 0
    for para in paras:
        if current and (para.boundary or size + para.size > max_syllables):
            groups.append((current, n_overlap))
            last = current[-1]
            if overlap and not para.boundary and last.size + para.size <= max_syllables:
                current, n_overlap, size = [last], 1, last.size
            else:
                current, n_overlap, size = [], 0, 0
        current.append(para)
        size += para.size
    if current and len(current) > n_overlap:
        groups.append((current, n_overlap))

    chunks: list[Chunk] = []
    for i, (group, n_ov) in enumerate(groups):
        pages_in = [p for para in group for p in (para.page_start, para.page_end) if p is not None]
        chunks.append(
            Chunk(
                chunk_id=make_chunk_id(doc_id, i),
                doc_id=doc_id,
                source=source,
                page_start=min(pages_in) if pages_in else None,
                page_end=max(pages_in) if pages_in else None,
                section=group[n_ov].section,
                text="\n".join(para.text for para in group),
            )
        )
    return chunks


__all__ = ["chunk_document", "count_syllables"]
