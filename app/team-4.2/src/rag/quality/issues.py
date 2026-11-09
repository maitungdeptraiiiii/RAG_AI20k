"""QualityIssue — finding chung của các detector chất lượng dữ liệu tuần 2.

Trường theo kế hoạch W02-02a: ``type``, ``severity``, ``location``, ``detail``, ``detector``.
Khi Nhóm 1 đưa ``QualityIssue`` vào ``schema.py``, chỉ cần đổi import ở đây.

Quy ước an toàn: ``detail`` và ``location`` KHÔNG được chứa giá trị PII gốc. Detector
chạy trên dữ liệu đã mask, và finding PII chỉ ghi loại + placeholder.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Severity = Literal["info", "warning", "error"]

# Mã issue dùng chung với data/team-4.2/fixtures/labels.jsonl
PII_DETECTED = "pii.detected"
NUMERIC_CONFLICT = "numeric.conflict"
NUMERIC_INVALID_LOCALE = "numeric.invalid_locale"
NUMERIC_SUM_MISMATCH = "numeric.sum_mismatch"
TABLE_MISSING_UNIT = "table.missing_unit"
TABLE_MISSING_PERIOD = "table.missing_period"
TABLE_INVALID_PERIOD = "table.invalid_period"
TABLE_TYPE_MISMATCH = "table.type_mismatch"
OCR_LOW_CONFIDENCE = "ocr.low_confidence"
OCR_TRUNCATED = "ocr.truncated"
OCR_EMPTY = "ocr.empty"
EXTRACTION_BAD_CHARS = "extraction.bad_chars"   # font TCVN3/VNI vỡ dấu, U+FFFD, ký tự điều khiển
DATE_INVALID = "date.invalid"
DATE_RANGE_INVALID = "date.range_invalid"

REVIEW_SEVERITIES: frozenset[str] = frozenset({"warning", "error"})


@dataclass(frozen=True)
class QualityIssue:
    type: str
    severity: Severity
    location: str          # vd. "table:0/row:2/col:Mức phạt" — không chứa giá trị PII
    detail: str
    detector: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def needs_review(self) -> bool:
        return self.severity in REVIEW_SEVERITIES


__all__ = [
    "DATE_INVALID",
    "DATE_RANGE_INVALID",
    "NUMERIC_CONFLICT",
    "NUMERIC_INVALID_LOCALE",
    "NUMERIC_SUM_MISMATCH",
    "PII_DETECTED",
    "QualityIssue",
    "Severity",
    "TABLE_INVALID_PERIOD",
    "TABLE_MISSING_PERIOD",
    "TABLE_MISSING_UNIT",
    "TABLE_TYPE_MISMATCH",
]
