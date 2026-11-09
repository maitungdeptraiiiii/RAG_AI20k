"""Shared document/content data models; independent of OCR and index backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from rag.models.common import (
    JSONValue,
    QualityStatus,
    Record,
    aware,
    canonical_json,
    nonempty,
    require,
)
from rag.models.content import TargetRef


@dataclass(frozen=True, kw_only=True)
class QualityIssue(Record):
    issue_id: str
    code: str
    severity: Literal["info", "warning", "error"]
    targets: tuple[TargetRef, ...]
    message: str
    safe_evidence: dict[str, JSONValue]
    detector_name: str
    detector_version: str
    config_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        nonempty(self.issue_id, self.code, self.detector_name, self.detector_version, self.config_id)
        require(bool(self.targets), "Issue requires targets")
        require(self.severity in ("info", "warning", "error"), "Invalid severity")
        aware(self.created_at)
        canonical_json(self.safe_evidence)


@dataclass(frozen=True, kw_only=True)
class QualityAssessment(Record):
    assessment_id: str
    target: TargetRef
    issue_ids: tuple[str, ...]
    status: QualityStatus
    policy_id: str
    assessed_at: datetime

    def __post_init__(self) -> None:
        nonempty(self.assessment_id, self.policy_id)
        require(self.status in ("pending", "passed", "needs_review", "rejected"), "Invalid quality status")
        aware(self.assessed_at)


@dataclass(frozen=True, kw_only=True)
class ReviewItem(Record):
    review_id: str
    issue_ids: tuple[str, ...]
    targets: tuple[TargetRef, ...]
    created_at: datetime
    status: Literal["open", "resolved"] = "open"
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        nonempty(self.review_id)
        aware(self.created_at)
        require(bool(self.issue_ids) and bool(self.targets), "Review needs issues and targets")
        require(self.status in ("open", "resolved"), "Invalid review status")
        require((self.status == "resolved") == (self.resolved_at is not None), "Invalid resolution timestamp")
        if self.resolved_at is not None:
            aware(self.resolved_at)


@dataclass(frozen=True, kw_only=True)
class ReviewDecision(Record):
    decision_id: str
    review_id: str
    action: Literal["accept", "reject", "keep_both", "link_existing", "confirm_replacement", "request_correction"]
    reviewer: str
    reason: str
    payload: dict[str, JSONValue]
    created_at: datetime

    def __post_init__(self) -> None:
        nonempty(self.decision_id, self.review_id, self.reviewer, self.reason)
        aware(self.created_at)
        require(self.action in ("accept", "reject", "keep_both", "link_existing", "confirm_replacement", "request_correction"),
                "Invalid review action")
        canonical_json(self.payload)
        if self.action == "link_existing":
            require(bool(self.payload.get("version_id")), "Link decision needs target version")
        if self.action == "confirm_replacement":
            require(bool(self.payload.get("unit_mapping") or self.payload.get("supersedes_version_ids"))
                    and bool(self.payload.get("effective_from")),
                    "Replacement needs targets/mapping and effective date")


__all__ = [
    'QualityIssue',
    'QualityAssessment',
    'ReviewItem',
    'ReviewDecision',
]
