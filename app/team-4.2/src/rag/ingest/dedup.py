"""Functional interfaces and handoff data; protocols do not implement backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TYPE_CHECKING
from rag.models.common import require
from rag.models.content import TargetRef
from rag.models.document import IdentityHint, SourceRecord
from rag.models.quality import QualityIssue
from rag.models.results import ParseResult


if TYPE_CHECKING:
    from rag.versioning.interfaces import CatalogView


@dataclass(frozen=True, kw_only=True)
class DedupConfig:
    algorithm: str
    algorithm_version: str
    threshold: float
    fingerprint_config_id: str

    def __post_init__(self) -> None:
        from rag.models.common import require
        require(0 <= self.threshold <= 1, "Invalid dedup threshold")


@dataclass(frozen=True, kw_only=True)
class DedupMatch:
    candidate_version_id: str
    kind: Literal["exact_artifact", "same_content_candidate", "near_duplicate"]
    similarity: float | None
    targets: tuple[TargetRef, ...]
    explanation: str


@dataclass(frozen=True, kw_only=True)
class DedupResult:
    matches: tuple[DedupMatch, ...]
    action: Literal["link_existing", "continue", "review"]
    existing_version_id: str | None
    findings: tuple[QualityIssue, ...]


class DedupDetector(Protocol):
    def detect(self, source: SourceRecord, parsed: ParseResult, *, hint: IdentityHint,
               catalog: CatalogView, config: DedupConfig) -> DedupResult: ...


__all__ = [
    'DedupConfig',
    'DedupMatch',
    'DedupResult',
    'DedupDetector',
]
