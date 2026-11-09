"""Shared document/content data models; independent of OCR and index backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from rag.models.common import (
    Approval,
    ChangeKind,
    Record,
    artifact_path,
    aware,
    checksum_value,
    nonempty,
    require,
)


@dataclass(frozen=True, kw_only=True)
class SourceRecord(Record):
    source_id: str
    source_uri: str
    display_name: str
    media_type: str
    raw_artifact: str
    raw_checksum: str
    collected_at: datetime
    document_id: str | None = None
    version_id: str | None = None

    def __post_init__(self) -> None:
        nonempty(self.source_id, self.source_uri, self.display_name, self.media_type)
        checksum_value(self.raw_checksum)
        artifact_path(self.raw_artifact)
        aware(self.collected_at)
        require(self.version_id is None or bool(self.document_id), "Version requires document ID")


@dataclass(frozen=True, kw_only=True)
class DocumentRecord(Record):
    document_id: str
    title: str
    document_type: str
    language: str
    created_at: datetime
    external_key: str | None = None
    issuer: str | None = None

    def __post_init__(self) -> None:
        nonempty(self.document_id, self.title, self.document_type, self.language)
        aware(self.created_at)


@dataclass(frozen=True, kw_only=True)
class VersionRecord(Record):
    version_id: str
    document_id: str
    change_kind: ChangeKind
    created_at: datetime
    label: str | None = None
    published_at: date | None = None
    declared_effective_from: date | None = None
    supersedes_version_ids: tuple[str, ...] = ()
    approval: Approval = "pending"

    def __post_init__(self) -> None:
        nonempty(self.version_id, self.document_id)
        aware(self.created_at)
        require(self.change_kind in ("initial", "full", "partial"), "Invalid change kind")
        require(self.approval in ("pending", "approved", "rejected"), "Invalid approval")
        require(self.version_id not in self.supersedes_version_ids, "Version cannot replace itself")
        require(self.change_kind != "initial" or not self.supersedes_version_ids,
                "Initial version cannot replace an existing version")


@dataclass(frozen=True, kw_only=True)
class ProcessingRecord(Record):
    processing_id: str
    version_id: str
    source_id: str
    parser_name: str
    parser_version: str
    normalization_config_id: str
    content_checksum: str
    created_at: datetime
    coverage: Literal["complete", "incomplete", "unknown"] = "unknown"
    ocr_engine: str | None = None
    ocr_config_id: str | None = None

    def __post_init__(self) -> None:
        nonempty(self.processing_id, self.version_id, self.source_id, self.parser_name,
                 self.parser_version, self.normalization_config_id)
        checksum_value(self.content_checksum)
        aware(self.created_at)
        require(self.coverage in ("complete", "incomplete", "unknown"), "Invalid coverage")


@dataclass(frozen=True, kw_only=True)
class ContentUnit(Record):
    unit_id: str
    document_id: str
    unit_key: str
    title: str

    def __post_init__(self) -> None:
        nonempty(self.unit_id, self.document_id, self.unit_key)


@dataclass(frozen=True, kw_only=True)
class UnitRevision(Record):
    unit_revision_id: str
    unit_id: str
    version_id: str
    processing_id: str
    block_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        nonempty(self.unit_revision_id, self.unit_id, self.version_id, self.processing_id)
        require(bool(self.block_ids) and len(set(self.block_ids)) == len(self.block_ids), "Invalid unit blocks")


@dataclass(frozen=True, kw_only=True)
class ApplicabilityRecord(Record):
    applicability_id: str
    unit_revision_id: str
    effective_from: date | None
    effective_to: date | None = None
    approval: Approval = "pending"
    replaces: tuple[str, ...] = ()
    decision_id: str | None = None

    def __post_init__(self) -> None:
        nonempty(self.applicability_id, self.unit_revision_id)
        require(self.approval in ("pending", "approved", "rejected"), "Invalid approval")
        require(self.effective_to is None or
                (self.effective_from is not None and self.effective_from < self.effective_to),
                "Invalid half-open effective interval")

    def applies_on(self, day: date) -> bool:
        return (self.approval == "approved" and self.effective_from is not None
                and self.effective_from <= day and (self.effective_to is None or day < self.effective_to))


@dataclass(frozen=True, kw_only=True)
class IdentityHint:
    document_id: str | None = None
    external_key: str | None = None
    issuer: str | None = None
    title: str | None = None


@dataclass(frozen=True, kw_only=True)
class UnitAssignment:
    """Explicit partition of extraction into COMPLETE replacement units.

    complete=True is a caller confirmation, not an OCR/LLM quality score.
    Amendment instructions alone are not a complete revised article.
    """
    unit_key: str
    title: str
    block_ids: tuple[str, ...]
    complete: bool = False

    def __post_init__(self) -> None:
        nonempty(self.unit_key, self.title)
        require(bool(self.block_ids) and len(set(self.block_ids)) == len(self.block_ids), "Invalid assigned blocks")
        require(type(self.complete) is bool, "Complete flag must be boolean")


@dataclass(frozen=True, kw_only=True)
class ChangeRequest:
    kind: ChangeKind
    effective_from: date | None = None
    supersedes_version_ids: tuple[str, ...] = ()
    unit_mapping: tuple[tuple[str, str], ...] = ()
    unit_assignments: tuple[UnitAssignment, ...] = ()

    def __post_init__(self) -> None:
        require(self.kind in ("initial", "full", "partial"), "Invalid change kind")
        require(self.kind != "partial" or bool(self.unit_mapping), "Partial change requires explicit mapping")


@dataclass(frozen=True, kw_only=True)
class QueryScope:
    mode: Literal["current", "as_of", "all_versions"] = "current"
    as_of: date | None = None
    document_ids: tuple[str, ...] = ()
    version_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(self.mode in ("current", "as_of", "all_versions"), "Invalid scope mode")
        require((self.mode == "as_of") == (self.as_of is not None), "Only as_of scope requires a date")


__all__ = [
    'SourceRecord',
    'DocumentRecord',
    'VersionRecord',
    'ProcessingRecord',
    'ContentUnit',
    'UnitRevision',
    'ApplicabilityRecord',
    'IdentityHint',
    'UnitAssignment',
    'ChangeRequest',
    'QueryScope',
]
