"""Review temporal conditions beyond the single confirmed-date implementation.

No date arithmetic, transitional-law interpretation or suspension scheduling is
attempted. Regexes flag evidence to review; absence of a flag is not proof that
every effective-date condition has been understood, especially after poor OCR.
"""

from __future__ import annotations

from datetime import date
import re

from rag.models.results import ParseResult
from rag.versioning.amendment_guard import source_text

_ANCHOR = re.compile(r"hiệu\s+lực(?:\s+thi\s+hành)?|áp\s+dụng")
_DATE = re.compile(
    r"(?<!\d)(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,4}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{4}"
    r"|ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})(?!\d)"
)
_RELATIVE = re.compile(
    r"(?:hiệu\s+lực|áp\s+dụng).{0,70}?"
    r"(?:sau\s+(?:\d+|[a-zà-ỹđ\s]{1,35})\s+(?:ngày|tháng|năm)\b"
    r"|(?:kể\s+)?từ\s+ngày\s+(?:ký|ban\s+hành|công\s+bố))"
)
_TRANSITION = (
    re.compile(r"(?:quy\s+định|điều\s+khoản|xử\s+lý)\s+chuyển\s+tiếp"),
    re.compile(r"(?:hồ\s+sơ|hợp\s+đồng|giao\s+dịch|thủ\s+tục).{0,120}?trước.{0,160}?(?:tiếp\s+tục|vẫn).{0,50}?áp\s+dụng"),
    re.compile(r"(?:tiếp\s+tục|vẫn).{0,40}?áp\s+dụng.{0,70}?(?:quy\s+định|văn\s+bản).{0,20}?cũ"),
)
_SUSPENSION = (
    re.compile(r"đình\s+chỉ\s+(?:việc\s+)?(?:thi\s+hành|áp\s+dụng|hiệu\s+lực)"),
    re.compile(r"đình\s+chỉ\s+(?:từ\s+(?:ngày|\d)|điều\s+\d|khoản\s+\d)"),
    re.compile(r"(?:tạm\s+ngừng|tạm\s+ngưng|ngưng|ngừng)\s+(?:thi\s+hành|áp\s+dụng|hiệu\s+lực)"),
)
_CONDITIONAL = re.compile(
    r"(?:hiệu\s+lực|áp\s+dụng)\s+(?:(?:kể\s+)?từ\s+|cho\s+đến\s+|sau\s+)?"
    r"(?:khi\b|thời\s+điểm\b)|(?:hiệu\s+lực|áp\s+dụng).{0,35}?phụ\s+thuộc"
)
_UNIT_EXCEPTION = re.compile(
    r"(?:riêng|ngoại\s+trừ|trừ)\s+(?:các\s+)?(?:điều|khoản|điểm)\b.{0,100}?"
    r"(?:hiệu\s+lực|áp\s+dụng|từ\s+(?:ngày\s+)?\d)"
)


def _parse_explicit_date(value: str) -> date:
    numbers = [int(number) for number in re.findall(r"\d+", value)]
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        return date(*numbers)
    day, month, year = numbers
    return date(year, month, day)


def unsupported_effectivity_reasons(parsed: ParseResult, *, effective_from: date | None) -> tuple[str, ...]:
    """Return fixed, non-PII reasons; never guess an effective date.

    Only date expressions following an effectiveness/applicability anchor are
    considered. Signature dates or ordinary deadlines alone are not effective
    dates. Multiple mentions of the SAME date are supported; distinct dates or
    a contradiction with caller metadata require review.
    """
    text = re.sub(r"\s+", " ", source_text(parsed.blocks))
    reasons = []
    if _RELATIVE.search(text):
        reasons.append("effectivity.relative_date: relative effective dates require a verified explicit date and resolved source conditions")
    if any(pattern.search(text) for pattern in _TRANSITION):
        reasons.append("effectivity.transition: transitional or grandfathering conditions are not supported by date-only selection")
    if any(pattern.search(text) for pattern in _SUSPENSION):
        reasons.append("effectivity.suspension: suspension/temporary interruption requires a separate temporal operation")
    if _CONDITIONAL.search(text):
        reasons.append("effectivity.conditional: effectiveness depends on an event/condition not represented by the current request")
    if _ANCHOR.search(text) and _UNIT_EXCEPTION.search(text):
        reasons.append("effectivity.unit_exception: source declares a unit-specific effectiveness exception that requires separate confirmation")
    explicit_dates = set()
    anchors = list(_ANCHOR.finditer(text))
    for index, anchor in enumerate(anchors):
        end = min(anchor.end() + 90, anchors[index + 1].start() if index + 1 < len(anchors) else len(text))
        window = text[anchor.end():end]
        match = _DATE.search(window)
        if match is None:
            continue
        # Don't reach across a new sentence to accidentally use an unrelated date.
        if re.search(r"[.!?;]", window[:match.start()]):
            continue
        try:
            explicit_dates.add(_parse_explicit_date(match.group()))
        except ValueError:
            reasons.append("effectivity.invalid_date: source contains an invalid or ambiguous explicit effective date")
    if len(explicit_dates) > 1:
        reasons.append("effectivity.multiple_dates: source contains distinct effective dates; a single request date is insufficient")
    if effective_from is not None and any(day != effective_from for day in explicit_dates):
        reasons.append("effectivity.date_mismatch: caller effective date contradicts an explicit source effective date")
    return tuple(dict.fromkeys(reasons))
