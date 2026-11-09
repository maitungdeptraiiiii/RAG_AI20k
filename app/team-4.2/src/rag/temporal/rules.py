"""Trích mốc thời gian từ câu hỏi bằng quy tắc: ngày, tháng, năm, khoảng, cụm tương đối, và vai trò theo từ khoá gần
mốc. Không đoán: ngày không hợp lệ bị bỏ, cụm tương đối không quy được thành khoảng thì ghi `relative_unresolved`."""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, datetime

from rag.temporal.models import Precision, Role, TimeAnchor, local_today

ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "signing": ("ký kết", "giao kết", "ký", "mua", "đặt cọc"),
    "contract_effective": ("hợp đồng có hiệu lực",),
    "performance": ("thực hiện", "bàn giao", "thanh toán", "giao nhà"),
    "discovery": ("phát hiện",),
    "dispute": ("tranh chấp", "khởi kiện", "kiện"),
    "evaluation": ("hiện nay", "bây giờ", "hiện tại", "theo luật", "áp dụng"),
}
_INTRINSIC_EVALUATION = ("hiện nay", "bây giờ", "hiện tại", "hôm nay")
_RELATIVE = ("cuối năm ngoái", "đầu năm ngoái", "cuối năm nay", "đầu năm nay", "năm ngoái", "năm trước", "năm nay",
             "tháng trước", "tháng này", "hiện nay", "hiện tại", "bây giờ", "hôm nay")
_D = r"(?<![\d/])(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})(?![\d/])"
_D_LONG = r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})"
_M = r"tháng\s+(\d{1,2})\s*(?:/|năm\s+)\s*(\d{4})(?![\d/])"
_Y = r"năm\s+(\d{4})(?![\d/])"
_POINT = rf"(?:{_D_LONG}|{_D}|{_M}|{_Y})"
_RANGE = re.compile(rf"từ\s+(?:ngày\s+)?(?P<a>{_POINT})\s+(?:đến|tới)\s+(?:ngày\s+)?(?P<b>{_POINT})", re.IGNORECASE)
_LAW_NAME_BEFORE = re.compile(r"(?:Bộ\s+luật|Luật|Nghị\s+quyết|Nghị\s+định|Thông\s+tư)\s+[A-ZĐÀ-Ỹ][^\s,.;]*"
                              r"(?:\s+[^\s,.;]+){0,6}\s+$")
_BEFORE, _AFTER = 40, 25


def _parse_point(text: str) -> tuple[date, date, Precision] | None:
    for pattern, kind in ((_D_LONG, "day"), (_D, "day"), (_M, "month"), (_Y, "year")):
        m = re.fullmatch(pattern, text.strip(), re.IGNORECASE)
        if not m:
            continue
        try:
            nums = [int(g) for g in m.groups()]
            if kind == "day":
                d = date(nums[2], nums[1], nums[0])
                return d, d, "day"
            if kind == "month":
                month, year = nums
                return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), "month"
            return date(nums[0], 1, 1), date(nums[0], 12, 31), "year"
        except ValueError:
            return None
    return None


def resolve_relative(expr: str, asked_at: datetime) -> tuple[date | None, date | None, Precision]:
    today = local_today(asked_at)
    y = today.year
    e = re.sub(r"\s+", " ", expr.casefold()).strip()
    table: dict[str, tuple[date, date, Precision]] = {
        "năm nay": (date(y, 1, 1), date(y, 12, 31), "year"),
        "năm ngoái": (date(y - 1, 1, 1), date(y - 1, 12, 31), "year"),
        "năm trước": (date(y - 1, 1, 1), date(y - 1, 12, 31), "year"),
        "cuối năm ngoái": (date(y - 1, 10, 1), date(y - 1, 12, 31), "range"),
        "đầu năm ngoái": (date(y - 1, 1, 1), date(y - 1, 3, 31), "range"),
        "cuối năm nay": (date(y, 10, 1), date(y, 12, 31), "range"),
        "đầu năm nay": (date(y, 1, 1), date(y, 3, 31), "range"),
    }
    if e in table:
        return table[e]
    if e in ("hiện nay", "hiện tại", "bây giờ", "hôm nay"):
        return today, today, "day"
    if e in ("tháng này", "tháng trước"):
        month, year = (today.month, y) if e == "tháng này" else ((today.month - 1) or 12, y if today.month > 1 else y - 1)
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), "month"
    return None, None, "relative_unresolved"


def _role(text: str, start: int, end: int, fallback: Role = "unspecified") -> tuple[Role, int, int]:
    """Từ khoá vai trò gần nhất phía trước (ưu tiên), không có thì phía sau. Trả (role, ev_start, ev_end)."""
    low = text.casefold()
    lo = max(0, start - _BEFORE)
    cut = max(low.rfind(c, lo, start) for c in ",;.")       # không vượt qua dấu câu
    lo = cut + 1 if cut >= 0 else lo
    before = low[lo:start]
    best: tuple[int, str, str] | None = None
    for role, words in ROLE_KEYWORDS.items():
        for w in words:
            for m in re.finditer(rf"(?<!\w){re.escape(w)}(?!\w)", before):
                pos = lo + m.start()
                if best is None or pos > best[0]:
                    best = (pos, role, w)
    if best is not None:
        return best[1], best[0], end  # type: ignore[return-value]
    after = low[end:end + _AFTER]
    stop = min((i for i in (after.find(c) for c in ",;.") if i >= 0), default=len(after))
    after = after[:stop]
    nearest: tuple[int, str, str] | None = None
    for role, words in ROLE_KEYWORDS.items():
        for w in words:
            m = re.search(rf"(?<!\w){re.escape(w)}(?!\w)", after)
            if m and (nearest is None or m.start() < nearest[0]):
                nearest = (m.start(), role, w)
    if nearest is not None:
        return nearest[1], start, end + nearest[0] + len(nearest[2])  # type: ignore[return-value]
    return fallback, start, end


def extract_rule_anchors(question: str, *, asked_at: datetime) -> list[TimeAnchor]:
    text = unicodedata.normalize("NFC", question)
    found: list[tuple[int, int, date | None, date | None, Precision, str | None]] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    for m in _RANGE.finditer(text):
        a, b = _parse_point(m.group("a")), _parse_point(m.group("b"))
        if a and b and a[0] <= b[1]:
            found.append((m.start(), m.end(), a[0], b[1], "range", None))
            taken.append((m.start(), m.end()))
    for pattern in (_D_LONG, _D, _M, _Y):
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if not free(m.start(), m.end()):
                continue
            if pattern == _Y and _LAW_NAME_BEFORE.search(text[:m.start()]):
                continue                                   # "Bộ luật Dân sự năm 2015" là tên luật, không phải mốc
            taken.append((m.start(), m.end()))
            parsed = _parse_point(m.group(0))
            if parsed:
                found.append((m.start(), m.end(), parsed[0], parsed[1], parsed[2], None))
    low = text.casefold()
    for phrase in _RELATIVE:
        for m in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", low):
            if not free(m.start(), m.end()):
                continue
            taken.append((m.start(), m.end()))
            start, end, precision = resolve_relative(phrase, asked_at)
            found.append((m.start(), m.end(), start, end, precision, text[m.start():m.end()]))

    anchors = []
    for s, e, start, end, precision, rel in sorted(found):
        fallback: Role = "evaluation" if rel and rel.casefold() in _INTRINSIC_EVALUATION else "unspecified"
        role, ev_s, ev_e = _role(text, s, e, fallback)
        if rel and rel.casefold() in _INTRINSIC_EVALUATION:
            role, ev_s, ev_e = "evaluation", s, e
        anchors.append(TimeAnchor(role, start, end, precision, "question", text[ev_s:ev_e].strip(), rel,
                                  0.9 if role != "unspecified" else 0.6, text[s:e]))
    return anchors


__all__ = ["ROLE_KEYWORDS", "extract_rule_anchors", "resolve_relative"]
