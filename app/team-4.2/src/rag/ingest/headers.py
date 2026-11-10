"""Bỏ header / footer / số trang khỏi text trang (OCR hoặc text layer PDF) — W02-02c A1.

Header/footer lọt vào chunk gây hai lỗi: (1) chunk chứa rác "Trang 22", "Tạp chí ... Tập 61" làm
nhiễu BM25/embedding; (2) số trang bị đọc nhầm thành số liệu ("131" đứng một mình cuối trang).
Prompt OCR ``v1`` bắt chép "toàn bộ" (đã benchmark, không đổi), nên lọc ở bước sau, xác định được.

Hai tầng, chỉ xét VÙNG MÉP (``EDGE`` dòng không rỗng đầu và cuối trang):

    strip_page_furniture(text)       1 trang: dòng khớp mẫu số trang / URL / bản quyền / "CÔNG BÁO/Số"
    strip_running_lines(texts)       nhiều trang: dòng mép lặp lại (chữ số chuẩn hoá) trên ≥ 50 % trang

An toàn hơn đầy đủ: KHÔNG bỏ dòng mở đầu Phần/Chương/Mục/Điều/Khoản, dòng chứa bảng (``<``/``|``),
dòng dài > ``MAX_LEN`` ký tự. Thà để lọt header còn hơn xoá mất một dòng nội dung luật.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

EDGE = 3
MAX_LEN = 120

_PROTECTED_RE = re.compile(r"^\W*(phần|chương|mục|điều|khoản|điểm)\s+[\dIVXLCDM]+", re.IGNORECASE)

_FURNITURE: tuple[re.Pattern[str], ...] = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"^[\s\-–—·•|]*\d{1,4}[\s\-–—·•|]*$",                         # 131 · - 192 - · · 44 ·
    r"^[\s\-–—]*(trang|page|tr\.)\s*\d{1,4}(\s*(/|trên|of)\s*\d{1,4})?[\s\-–—]*$",   # Trang 22 · Page 3 of 10
    r"^\d{1,4}\s*/\s*\d{1,4}$",                                   # 3/10
    r"^.{0,40}第\s*\d+\s*页\s*[（(]?\s*共\s*\d+\s*页\s*[)）]?.{0,20}$",   # 第 2 页（共 6 页）
    r"^\s*(https?://|www\.)(?!(dx\.)?doi\.org)\S+\s*$",           # dòng chỉ có URL (trừ DOI: thường là trích dẫn)
    # bản quyền: © / (c) PHẢI kèm năm ("© 2007 WILEY"); "(C)" trong chú thích hình hay ký tự © rác của OCR không tính
    r"^.{0,40}((©|\(c\))\s*(19|20)\d{2}|copyright|all rights reserved|bản quyền|版权所有).{0,80}$",
    r"^\s*công\s*báo\s*/\s*số\s*[\d+\s]+(/\s*ngày\s*[\d\-/.]+)?\s*$",   # CÔNG BÁO/Số 123 + 124/Ngày 15-02-2024
    r"^.{0,60}\b(tập|vol\.?|volume)\s*\d+\s*,\s*(số|no\.?)\s*\w+.{0,40}$",   # Tập 61, Số 4B (2025): 128-138
))


def _protected(line: str) -> bool:
    s = line.strip()
    return len(s) > MAX_LEN or "<" in s or "|" in s or bool(_PROTECTED_RE.match(s))


def _edge_indexes(lines: Sequence[str], edge: int = EDGE) -> list[int]:
    filled = [i for i, line in enumerate(lines) if line.strip()]
    return sorted(set(filled[:edge] + filled[-edge:]))


def _plain(line: str) -> str:
    """Bỏ ký hiệu Markdown (#, **) để so mẫu trên nội dung."""
    return re.sub(r"^\s{0,3}#{1,6}\s+|\*\*|__", "", line).strip()


def is_furniture(line: str) -> bool:
    s = _plain(line)
    return bool(s) and not _protected(s) and any(p.match(s) for p in _FURNITURE)


def strip_page_furniture(text: str, *, edge: int = EDGE) -> tuple[str, list[str]]:
    """Bỏ dòng mép khớp mẫu header/footer. Trả (text, các dòng đã bỏ)."""
    lines = text.split("\n")
    drop = {i for i in _edge_indexes(lines, edge) if is_furniture(lines[i])}
    return "\n".join(l for i, l in enumerate(lines) if i not in drop), [lines[i].strip() for i in sorted(drop)]


def _signature(line: str) -> str:
    """Chuẩn hoá để so lặp: hoa thường, chữ số -> '#', gộp khoảng trắng ('Trang 3' ≡ 'Trang 4')."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", _plain(line).casefold())).strip()


def strip_running_lines(texts: Sequence[str], *, edge: int = EDGE, min_pages: int = 3,
                        min_ratio: float = 0.5) -> tuple[list[str], list[str]]:
    """Header/footer chạy của tài liệu nhiều trang: dòng mép có cùng chữ ký trên ≥ ``min_ratio``
    số trang (và ≥ ``min_pages`` trang). Trả (texts, các chữ ký đã bỏ)."""
    if len(texts) < min_pages:
        return list(texts), []
    split = [t.split("\n") for t in texts]

    def zones(lines: list[str]) -> tuple[list[int], list[int]]:
        # vùng mép tối đa 1/3 số dòng: trang ngắn không bị coi cả trang là "mép";
        # chia vùng trên MỌI dòng rồi mới loại dòng được bảo vệ (không để vùng trượt vào giữa trang)
        filled = [i for i, line in enumerate(lines) if line.strip()]
        k = min(edge, len(filled) // 3)
        top, bottom = (filled[:k], filled[-k:]) if k else ([], [])
        keep = lambda ids: [i for i in ids if not _protected(_plain(lines[i]))]  # noqa: E731
        return keep(top), keep(bottom)

    top_seen: Counter[str] = Counter()
    bottom_seen: Counter[str] = Counter()
    for lines in split:
        top, bottom = zones(lines)
        top_seen.update({_signature(lines[i]) for i in top})
        bottom_seen.update({_signature(lines[i]) for i in bottom})
    threshold = max(min_pages, min_ratio * len(texts))
    run_top = {s for s, n in top_seen.items() if s and n >= threshold}
    run_bottom = {s for s, n in bottom_seen.items() if s and n >= threshold}
    if not run_top and not run_bottom:
        return list(texts), []
    out = []
    for lines in split:
        top, bottom = zones(lines)
        drop = {i for i in top if _signature(lines[i]) in run_top} | \
               {i for i in bottom if _signature(lines[i]) in run_bottom}
        out.append("\n".join(l for i, l in enumerate(lines) if i not in drop))
    return out, sorted(run_top | run_bottom)


__all__ = ["EDGE", "is_furniture", "strip_page_furniture", "strip_running_lines"]
