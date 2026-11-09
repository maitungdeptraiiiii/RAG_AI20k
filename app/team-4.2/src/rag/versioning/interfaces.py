"""Functional interfaces and handoff data; protocols do not implement backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol, Sequence
from rag.ingest.dedup import DedupResult
from rag.models.common import JSONValue
from rag.models.content import Block, ChunkV2
from rag.models.document import (
    ApplicabilityRecord,
    ChangeRequest,
    ContentUnit,
    DocumentRecord,
    IdentityHint,
    ProcessingRecord,
    QueryScope,
    SourceRecord,
    UnitRevision,
    VersionRecord,
)
from rag.models.quality import QualityAssessment, QualityIssue
from rag.models.results import ParseResult, ResolvedScope


class CatalogView(Protocol):
    """Read-only snapshot; implementations return immutable/detached records."""
    @property
    def revision(self) -> int: ...
    def documents(self, hint: IdentityHint) -> tuple[DocumentRecord, ...]: ...
    def versions(self, document_id: str) -> tuple[VersionRecord, ...]: ...
    def units(self, document_id: str) -> tuple[ContentUnit, ...]: ...
    def revisions(self, unit_id: str) -> tuple[UnitRevision, ...]: ...
    def applicability(self, document_id: str) -> tuple[ApplicabilityRecord, ...]: ...
    def processing(self, version_id: str) -> tuple[ProcessingRecord, ...]: ...
    def blocks(self, processing_id: str) -> tuple[Block, ...]: ...
    def sources(self, document_id: str) -> tuple[SourceRecord, ...]: ...


@dataclass(frozen=True, kw_only=True)
class ApplicabilityChange:
    previous: ApplicabilityRecord | None
    proposed: ApplicabilityRecord
    reason: str


@dataclass(frozen=True, kw_only=True)
class VersionPlan:
    plan_id: str
    base_catalog_revision: int
    document_id: str
    candidate_version: VersionRecord
    candidate_units: tuple[ContentUnit, ...]
    candidate_unit_revisions: tuple[UnitRevision, ...]
    applicability_changes: tuple[ApplicabilityChange, ...]
    required_review_ids: tuple[str, ...]
    action: Literal["link_existing", "create", "review"]
    review_reasons: tuple[str, ...] = ()


class VersionResolver(Protocol):
    def propose(self, parsed: ParseResult, *, hint: IdentityHint, dedup: DedupResult,
                change: ChangeRequest, catalog: CatalogView) -> VersionPlan: ...


class CatalogSnapshot(CatalogView, Protocol):
    @property
    def generation_id(self) -> str: ...
    def chunks(self) -> tuple[ChunkV2, ...]: ...
    def assessments(self) -> tuple[QualityAssessment, ...]: ...


class Clock(Protocol):
    def today(self, timezone: str) -> date: ...


class ScopeResolver(Protocol):
    def resolve(self, scope: QueryScope, *, snapshot: CatalogSnapshot, clock: Clock) -> ResolvedScope: ...


@dataclass(frozen=True, kw_only=True)
class StagedGeneration:
    generation_id: str
    base_catalog_revision: int
    selected_chunk_ids: tuple[str, ...]
    index_signature: dict[str, JSONValue]
    manifest_checksum: str


@dataclass(frozen=True, kw_only=True)
class IndexReceipt:
    generation_id: str
    index_signature: dict[str, JSONValue]
    manifest_checksum: str
    completed_backends: tuple[str, ...]
    ready_at: datetime


class CatalogRepository(Protocol):
    def snapshot(self) -> CatalogView: ...
    def record_source(self, source: SourceRecord) -> None: ...
    def stage(self, plan: VersionPlan, processing: ProcessingRecord, blocks: Sequence[Block],
              findings: Sequence[QualityIssue], chunks: Sequence[ChunkV2], *,
              expected_revision: int) -> StagedGeneration: ...
    def activate(self, generation_id: str, receipt: IndexReceipt, *,
                 expected_revision: int) -> CatalogSnapshot: ...
    def abort(self, generation_id: str, safe_error: str) -> None: ...


class GenerationIndexer(Protocol):
    def build_generation(self, staged: StagedGeneration) -> IndexReceipt: ...


__all__ = [
    'CatalogView',
    'ApplicabilityChange',
    'VersionPlan',
    'VersionResolver',
    'CatalogSnapshot',
    'Clock',
    'ScopeResolver',
    'StagedGeneration',
    'IndexReceipt',
    'CatalogRepository',
    'GenerationIndexer',
]
