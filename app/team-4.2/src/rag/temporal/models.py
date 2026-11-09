"""Mô hình dòng thời gian pháp lý và quy định chuyển tiếp cho hỏi đáp theo mốc (phần 2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

Role = Literal["signing", "contract_effective", "performance", "discovery", "dispute", "evaluation", "unspecified"]
Precision = Literal["day", "month", "year", "range", "relative_unresolved"]
AnchorSource = Literal["calendar", "question", "default"]
ROLES: tuple[str, ...] = ("signing", "contract_effective", "performance", "discovery", "dispute", "evaluation",
                          "unspecified")
VN_TZ = timezone(timedelta(hours=7))          # Asia/Ho_Chi_Minh (không đổi giờ mùa hè)


def local_today(asked_at: datetime) -> date:
    return (asked_at if asked_at.tzinfo else asked_at.replace(tzinfo=timezone.utc)).astimezone(VN_TZ).date()


@dataclass(frozen=True)
class TimeAnchor:
    role: Role
    start: date | None                 # khoảng đóng [start, end]
    end: date | None
    precision: Precision
    source: AnchorSource
    evidence: str | None
    relative_expression: str | None
    confidence: float


@dataclass(frozen=True)
class LegalTimeline:
    anchors: tuple[TimeAnchor, ...]
    primary: TimeAnchor
    warnings: tuple[str, ...]
    asked_at: datetime


@dataclass(frozen=True)
class TransitionRule:
    """Giao diện tối thiểu cho quy định chuyển tiếp: nội dung là văn bản gốc (phương án a); sau này một bộ máy quy
    tắc (phương án b) có thể đọc cùng cấu trúc này."""

    rule_id: str
    source_document_key: str
    source_article: str
    text: str
    old_law_key: str | None
    new_law_key: str | None
    new_law_effective_from: date | None
    related_roles: tuple[str, ...]


__all__ = ["AnchorSource", "LegalTimeline", "Precision", "ROLES", "Role", "TimeAnchor", "TransitionRule", "VN_TZ",
           "local_today"]
