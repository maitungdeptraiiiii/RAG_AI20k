"""Functional interfaces and handoff data; protocols do not implement backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol, Sequence, TYPE_CHECKING
from rag.ingest.dedup import DedupResult
from rag.models.common import require
from rag.models.content import SafeBlock, TargetRef
from rag.models.document import ChangeRequest, IdentityHint, SourceRecord
from rag.models.quality import QualityIssue, ReviewDecision, ReviewItem
from rag.models.results import ParseResult
from rag.versioning.interfaces import VersionPlan


if TYPE_CHECKING:
    from rag.quality.review_queue import ReviewDetails


@dataclass(frozen=True, kw_only=True)
class ValidationConfig:
    rules_version: str
    quality_policy_id: str


class QualityValidator(Protocol):
    def validate(self, blocks: Sequence[SafeBlock], *, config: ValidationConfig) -> tuple[QualityIssue, ...]: ...


@dataclass(frozen=True, kw_only=True)
class NumericContext:
    metric_key: str | None = None
    unit: str | None = None
    currency: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    dimensions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, kw_only=True)
class NumericFact:
    fact_id: str
    target: TargetRef
    raw_value: str
    value: Decimal | None
    context: NumericContext
    verified: bool = False


@dataclass(frozen=True, kw_only=True)
class NumericConfig:
    locale: str
    unit_conversion_version: str
    tolerance: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        from rag.models.common import require
        require(self.tolerance.is_finite() and self.tolerance >= 0, "Invalid numeric tolerance")


@dataclass(frozen=True, kw_only=True)
class NumericComparison:
    relation: Literal["equal", "different", "incomparable", "invalid"]
    left_value: Decimal | None
    right_value: Decimal | None
    canonical_unit: str | None
    reason: str


class NumericNormalizer(Protocol):
    def extract(self, blocks: Sequence[SafeBlock], *, config: NumericConfig) -> tuple[NumericFact, ...]: ...
    def compare(self, left: NumericFact, right: NumericFact, *, config: NumericConfig) -> NumericComparison: ...


@dataclass(frozen=True, kw_only=True)
class ConflictConfig:
    metric_mapping_version: str
    numeric_config: NumericConfig


class ConflictDetector(Protocol):
    def detect(self, candidate: Sequence[NumericFact], existing: Sequence[NumericFact], *,
               numeric: NumericNormalizer, config: ConflictConfig) -> tuple[QualityIssue, ...]: ...


class ReviewService(Protocol):
    def enqueue(self, issues: Sequence[QualityIssue]) -> tuple[ReviewItem, ...]: ...
    def enqueue_version(self, plan: VersionPlan, parsed: ParseResult, source: SourceRecord, *,
                        hint: IdentityHint, change: ChangeRequest, dedup: DedupResult) -> ReviewItem: ...
    def get(self, review_id: str) -> ReviewDetails: ...
    def list_items(self, *, status: Literal["open", "resolved"] | None = "open",
                   limit: int = 100, offset: int = 0) -> tuple[ReviewDetails, ...]: ...
    def resolve(self, review_id: str, decision: ReviewDecision, *, expected_revision: int) -> ReviewItem: ...


__all__ = [
    'ValidationConfig',
    'QualityValidator',
    'NumericContext',
    'NumericFact',
    'NumericConfig',
    'NumericComparison',
    'NumericNormalizer',
    'ConflictConfig',
    'ConflictDetector',
    'ReviewService',
]
