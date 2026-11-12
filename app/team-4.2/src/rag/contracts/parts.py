"""Nhận diện các phần của hợp đồng: hợp đồng chính và phụ lục."""
from __future__ import annotations

import re

from .doc import PartSpec

_LOWER = re.compile(r"^Phụ lục\s+(số\s+)?\d+\b")
_TOC_MARK = re.compile(r"^(MỤC LỤC|DANH MỤC)", re.IGNORECASE)


def detect_parts(text: str) -> list[PartSpec]:
    """Luôn có p0 (main, start=0); mỗi tiêu đề phụ lục mở một phần mới."""
    lines: list[tuple[int, str]] = []
    pos = 0
    for ln in text.split("\n"):
        lines.append((pos, ln))
        pos += len(ln) + 1

    parts = [PartSpec("p0", "main", "", 0, None)]
    for i, (off, raw) in enumerate(lines):
        line = raw.strip()
        if not line or len(line) > 100 or raw[:1].isspace():
            continue
        if line.startswith("PHỤ LỤC"):
            pass
        elif _LOWER.match(line):
            if i > 0 and lines[i - 1][1].strip():
                continue
        else:
            continue
        m = re.search(r"\d+", line)
        number = int(m.group()) if m else None
        # mục lục: ngay sau dòng "MỤC LỤC", hoặc không số mà các dòng sau toàn ngắn
        prev = next((l.strip() for _, l in reversed(lines[:i]) if l.strip()), "")
        if _TOC_MARK.match(prev):
            continue
        if number is None:
            nxt = [l.strip() for _, l in lines[i + 1:] if l.strip()][:3]
            if not any(len(l) > 20 for l in nxt):
                continue
        parts.append(PartSpec(f"p{len(parts)}", "appendix", line, off, number))
    return parts
