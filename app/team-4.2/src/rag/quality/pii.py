"""Mask PII quyết định được cho text/bảng trước embedding hay log.

Kết quả không chứa PII gốc hoặc mapping đảo ngược. Adapter contract sau này chỉ
được đưa ``masked_text`` và ``safe_findings`` sang SafeBlock/QualityIssue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


EMAIL_RE = re.compile(r"(?<![\w.@+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.@+-])")
PHONE_RE = re.compile(r"(?<!\d)(?:\+84|84|0)(?:[ .-]?\d){8,10}(?!\d)")


@dataclass(frozen=True)
class SafePIIFinding:
    """Chứng cứ an toàn: chỉ loại và thứ tự occurrence, không có giá trị gốc."""

    code: str
    entity_type: str
    occurrence: int


@dataclass(frozen=True)
class MaskedText:
    masked_text: str
    safe_findings: tuple[SafePIIFinding, ...]


def mask_text(text: str) -> MaskedText:
    """Mask email/số điện thoại bằng placeholder ổn định trong từng text."""
    findings: list[SafePIIFinding] = []
    counters = {"email": 0, "phone": 0}
    matches = [(match.start(), match.end(), "email") for match in EMAIL_RE.finditer(text)]
    matches.extend((match.start(), match.end(), "phone") for match in PHONE_RE.finditer(text))
    matches.sort()
    pieces: list[str] = []
    cursor = 0
    for start, end, kind in matches:
        if start < cursor:  # một regex đã bao trùm match khác
            continue
        counters[kind] += 1
        pieces.extend((text[cursor:start], f"[{kind.upper()}_{counters[kind]}]"))
        findings.append(SafePIIFinding(code="pii.detected", entity_type=kind, occurrence=counters[kind]))
        cursor = end
    pieces.append(text[cursor:])
    return MaskedText(masked_text="".join(pieces), safe_findings=tuple(findings))


def mask_cells(cells: tuple[tuple[str, ...], ...]) -> tuple[tuple[tuple[str, ...], ...], tuple[SafePIIFinding, ...]]:
    """Mask toàn bộ cell; finding không tiết lộ nội dung hay tọa độ có PII."""
    findings: list[SafePIIFinding] = []
    masked_rows: list[tuple[str, ...]] = []
    for row in cells:
        masked_row: list[str] = []
        for cell in row:
            result = mask_text(cell)
            masked_row.append(result.masked_text)
            findings.extend(result.safe_findings)
        masked_rows.append(tuple(masked_row))
    return tuple(masked_rows), tuple(findings)
