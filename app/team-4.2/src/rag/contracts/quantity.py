"""Giá trị số có kiểu (spec 2026-11-23-typed-value-reading-design.md).

LLM đọc cụm chữ ra dạng có kiểu (thời hạn = danh sách phần, tiền, tỉ lệ); ở đây chỉ:
- kiểm dạng có kiểu hợp lệ;
- cộng / quy đổi (code tính, không để LLM tính);
- kiểm căn cứ: mỗi số LLM trả phải có trong câu trích, viết bằng chữ số hoặc bằng chữ (bộ đọc số tiếng Việt theo
  ngữ pháp đóng), cho phép nhân nghìn / triệu / tỷ ("5tr", "100 triệu").
Không có mẫu theo cách viết: cách viết mới không cần sửa ở đây.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

# ── bộ đọc số bằng chữ ──
_DIGITS = {"không": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "lăm": 5, "nhăm": 5,
           "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9}
_AFTER_TENS_ONLY = {"mốt": {"mươi"}, "tư": {"mươi"}, "lăm": {"mươi", "mười"}, "nhăm": {"mươi", "mười"}}
_SCALES = {"nghìn": 10**3, "ngàn": 10**3, "triệu": 10**6, "tỷ": 10**9, "tỉ": 10**9}
_WORDS = set(_DIGITS) | set(_SCALES) | {"mười", "mươi", "trăm", "lẻ", "linh", "phẩy", "rưỡi"}


def _int_words(words: list[str]) -> int | None:
    total, group, pend, last_scale, prev = 0, 0, None, None, None
    for w in words:
        if w in _DIGITS:
            if pend is not None or (w in _AFTER_TENS_ONLY and prev not in _AFTER_TENS_ONLY[w]):
                return None
            pend = _DIGITS[w]
        elif w == "mười":
            if pend is not None or group % 100 >= 10:
                return None
            group += 10
        elif w == "mươi":
            if pend is None or pend < 2 or group % 100 >= 10:
                return None
            group, pend = group + pend * 10, None
        elif w == "trăm":
            if pend is None or group:
                return None
            group, pend = pend * 100, None
        elif w in ("lẻ", "linh"):
            if prev != "trăm":
                return None
        elif w in _SCALES:
            if pend is not None:
                group, pend = group + pend, None
            if not group:
                return None
            s = _SCALES[w]
            total = (total + group) * s if last_scale is not None and s > last_scale else total + group * s
            group, last_scale = 0, s
        elif w == "rưỡi":
            if prev not in _SCALES:
                return None
            total += last_scale // 2
        else:
            return None
        prev = w
    if prev is None or prev in ("lẻ", "linh"):
        return None
    return total + group + (pend or 0)


def read_vi_number(words: list[str]) -> Decimal | int | None:
    """Số viết bằng chữ ("hai mươi bốn", "một trăm triệu", "một phẩy năm") -> giá trị; không phải số -> None."""
    words = [unicodedata.normalize("NFC", w).casefold() for w in words]
    if "phẩy" in words:
        i = words.index("phẩy")
        whole, frac = _int_words(words[:i]), words[i + 1:]
        if whole is None or not frac or any(w not in _DIGITS or w in _AFTER_TENS_ONLY for w in frac):
            return None
        return whole + Decimal("0." + "".join(str(_DIGITS[w]) for w in frac))
    return _int_words(words)


# ── quét số trong chữ ──
_DATE = re.compile(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")
_DIGIT_TOKEN = re.compile(r"\d[\d.,]*\d|\d")
_WORD = re.compile(r"\w+")
_GROUPED = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def _digit_values(token: str) -> set[Decimal]:
    """Mọi cách đọc một cụm chữ số: phân cách nghìn ('.' hoặc ','), hoặc phần lẻ (một dấu)."""
    out = set()
    if _GROUPED.fullmatch(token) or token.isdigit():
        out.add(Decimal(re.sub(r"[.,]", "", token)))
    seps = re.findall(r"[.,]", token)
    if len(seps) == 1:
        out.add(Decimal(token.replace(",", ".")))
    return out


def numbers_in(text: str) -> set[Decimal]:
    """Mọi giá trị số có mặt trong chữ (chữ số và chữ; ngày tháng không tính). Rộng: mọi cách đọc có thể."""
    text = unicodedata.normalize("NFC", text or "")
    out: set[Decimal] = set()
    for tok in _DIGIT_TOKEN.findall(_DATE.sub(" ", text)):
        out |= _digit_values(tok)
    run: list[str] = []
    for w in [*_WORD.findall(text.casefold()), ""]:
        if w in _WORDS:
            run.append(w)
            continue
        for i in range(len(run)):
            for j in range(i + 1, len(run) + 1):
                v = read_vi_number(run[i:j])
                if v is not None:
                    out.add(Decimal(v))
        run = []
    return out


_MULTIPLIERS = (1, 10**3, 10**6, 10**9)


def grounded(value: Any, text: str) -> bool:
    """`value` có trong `text` (chữ số hoặc chữ), cho phép nhân nghìn / triệu / tỷ."""
    v = to_number(value)
    if v is None:
        return False
    return any(n * m == v for n in numbers_in(text) for m in _MULTIPLIERS)


def to_number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def plain(d: Decimal) -> int | float:
    return int(d) if d == d.to_integral_value() else float(d)


# ── dạng có kiểu ──
DURATION_UNITS = frozenset({"hour", "day", "workday", "week", "month", "year"})
PERIODS = frozenset({"day", "month", "year"})


def duration_parts(norm: Any) -> list[tuple[Decimal, str]] | None:
    """{"parts": [{"n", "unit"}]} -> [(n, unit)] đúng như LLM đọc (để kiểm căn cứ từng số). Hỏng -> None."""
    parts = norm.get("parts") if isinstance(norm, dict) else None
    if not isinstance(parts, list) or not parts:
        return None
    out = []
    for p in parts:
        n = to_number(p.get("n")) if isinstance(p, dict) else None
        unit = p.get("unit") if isinstance(p, dict) else None
        if n is None or n < 0 or unit not in DURATION_UNITS:
            return None
        out.append((n, unit))
    return out


def sum_duration(parts: list[tuple[Decimal, str]], to_unit: str | None, units) -> tuple[Any, str] | None:
    """Năm quy về 12 tháng (như bộ đọc cũ). Một phần -> giữ đơn vị của nó; nhiều phần -> cộng sau khi quy về
    `to_unit` (không quy được, vd. ngày làm việc -> None)."""
    parts = [(n * 12, "month") if unit == "year" else (n, unit) for n, unit in parts]
    if len(parts) == 1:
        return plain(parts[0][0]), parts[0][1]
    if to_unit is None or units is None:
        return None
    total = Decimal(0)
    for n, unit in parts:
        v = units.convert(float(n), unit, to_unit)
        if v is None:
            return None
        total += Decimal(str(v))
    return plain(total), to_unit


def money_value(norm: Any) -> tuple[Decimal, str] | None:
    if not isinstance(norm, dict):
        return None
    amount, cur = to_number(norm.get("amount")), str(norm.get("currency") or "").strip().upper()
    if amount is None or amount < 0 or cur not in ("VND", "USD"):
        return None
    return amount, cur


def percent_value(norm: Any) -> tuple[Decimal, str | None] | None:
    if not isinstance(norm, dict):
        return None
    v, per = to_number(norm.get("value")), norm.get("per")
    if v is None or v < 0 or (per is not None and per not in PERIODS):
        return None
    return v, per


__all__ = ["DURATION_UNITS", "PERIODS", "duration_parts", "grounded", "money_value", "numbers_in", "percent_value",
           "plain", "read_vi_number", "sum_duration", "to_number"]
