"""Trích giá trị hợp đồng bằng quy tắc: tiền, tỉ lệ, ngày, thời hạn."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Kind = Literal["money", "percent", "date", "duration"]


@dataclass(frozen=True)
class RawValue:
    kind: Kind
    raw: str
    norm: dict
    start: int
    end: int


# nhóm nghìn nhất quán: toàn dấu "." hoặc toàn dấu cách (không xuống dòng), hoặc số trơn
_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?: \d{3})+(?:,\d+)?|\d+(?:,\d+)?"

# ngày: "ngày D tháng M năm Y" hoặc D/M/Y, D-M-Y
DATE_RE = re.compile(
    r"(?<![\d/-])(?:ngày[ \t]+(\d{1,2})[ \t]+tháng[ \t]+(\d{1,2}),?[ \t]+năm[ \t]+(\d{4})"
    r"|(\d{1,2})[/-](\d{1,2})[/-](\d{4}))(?![\d/-])",
    re.IGNORECASE,
)
# tiền: số + (triệu|tỷ) + (đồng|VNĐ|USD) — cần có ít nhất đơn vị hoặc bội số; không nối qua dòng
MONEY_RE = re.compile(
    rf"(?<![\d.,])(?P<num>{_NUM})[ \t]*"
    r"(?:(?P<scale>triệu|tỷ)(?:[ \t]*(?P<cur1>đồng|vnđ|vnd|usd))?|(?P<cur2>đồng|vnđ|vnd|usd))(?!\w)",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"(?<![\d.,])\d+(?:,\d+)?[ \t]*%")
DURATION_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)*)[ \t]*(ngày|tuần|tháng|năm|giờ)\b", re.IGNORECASE)
_MAX_DURATION_DIGITS = 6

_SCALE = {"triệu": 10**6, "tỷ": 10**9}


def _to_decimal(num: str) -> Decimal:
    # "." hoặc dấu cách là phân cách nghìn, "," là phần lẻ
    return Decimal(re.sub(r"[. ]", "", num).replace(",", "."))


def _id_like(num: str) -> bool:
    """Dãy số kiểu mã / điện thoại: số 0 đứng đầu và dài hơn 2 chữ số ("05 ngày" vẫn nhận)."""
    digits = re.sub(r"\D", "", num.split(",")[0])
    return digits.startswith("0") and len(digits) > 2


def _free(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    return all(span[1] <= a or span[0] >= b for a, b in taken)


def extract_values(text: str) -> list[RawValue]:
    """Quét ngày -> tiền -> tỉ lệ -> thời hạn; vùng đã chiếm thì bỏ qua; sắp theo start."""
    out: list[RawValue] = []
    taken: list[tuple[int, int]] = []

    def add(kind: Kind, m: re.Match, norm: dict) -> None:
        out.append(RawValue(kind, m.group(0), norm, m.start(), m.end()))
        taken.append((m.start(), m.end()))

    for m in DATE_RE.finditer(text):
        d, mo, y = (m.group(1), m.group(2), m.group(3)) if m.group(1) else m.group(4, 5, 6)
        try:
            iso = date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            taken.append(m.span())  # ngày không hợp lệ: bỏ giá trị nhưng vẫn giữ chỗ
            continue
        add("date", m, {"iso": iso})

    for m in MONEY_RE.finditer(text):
        if not _free(m.span(), taken) or _id_like(m["num"]):
            continue
        amount = _to_decimal(m["num"]) * _SCALE.get((m["scale"] or "").lower(), 1)
        cur = (m["cur1"] or m["cur2"] or "").lower()
        add("money", m, {"amount": int(amount), "currency": "USD" if cur == "usd" else "VND"})

    for m in PERCENT_RE.finditer(text):
        if _free(m.span(), taken):
            add("percent", m, {"percent": float(m.group(0).rstrip("% \t").replace(",", "."))})

    for m in DURATION_RE.finditer(text):
        n = m.group(1)
        if (_free(m.span(), taken) and n.isdigit()  # bỏ số lẻ / có nhóm nghìn
                and len(n) <= _MAX_DURATION_DIGITS and not _id_like(n)):
            add("duration", m, {"n": int(m.group(1)), "unit": m.group(2).lower()})

    return sorted(out, key=lambda v: v.start)
