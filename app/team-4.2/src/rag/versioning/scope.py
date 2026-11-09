"""Version planning and temporal selection; no OCR or index activation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from rag.models.common import require
from rag.models.content import Block
from rag.models.document import (
    ApplicabilityRecord,
    ContentUnit,
    IdentityHint,
    QueryScope,
    UnitRevision,
)
from rag.versioning.interfaces import CatalogView, Clock


@dataclass(frozen=True, kw_only=True)
class SelectedUnit:
    unit: ContentUnit
    revision: UnitRevision
    applicability: ApplicabilityRecord
    blocks: tuple[Block, ...]


@dataclass(frozen=True, kw_only=True)
class UnitSelection:
    """Pre-chunk extraction selection; not a quality-cleared retrieval scope."""
    catalog_revision: int
    resolved_date: date | None
    units: tuple[SelectedUnit, ...]
    ambiguous_unit_ids: tuple[str, ...] = ()


class SystemClock:
    def today(self, timezone: str) -> date:
        return datetime.now(ZoneInfo(timezone)).date()


class UnitScopeResolver:
    def __init__(self, timezone: str = "Asia/Ho_Chi_Minh") -> None:
        self.timezone = timezone

    def resolve_units(self, scope: QueryScope, *, catalog: CatalogView,
                      clock: Clock | None = None) -> UnitSelection:
        day = ((clock or SystemClock()).today(self.timezone) if scope.mode == "current"
               else scope.as_of if scope.mode == "as_of" else None)
        selected, ambiguous = [], []
        for document in catalog.documents(IdentityHint()):
            if scope.document_ids and document.document_id not in scope.document_ids:
                continue
            approved = {v.version_id for v in catalog.versions(document.document_id) if v.approval == "approved"}
            applicability = catalog.applicability(document.document_id)
            for unit in catalog.units(document.document_id):
                revisions = {r.unit_revision_id: r for r in catalog.revisions(unit.unit_id) if r.version_id in approved}
                candidates = [a for a in applicability if a.unit_revision_id in revisions and a.approval == "approved"
                              and (scope.mode == "all_versions" or a.applies_on(day))]
                if scope.mode != "all_versions" and len(candidates) > 1:
                    ambiguous.append(unit.unit_id)
                    continue
                for item in candidates:
                    revision = revisions[item.unit_revision_id]
                    if scope.version_ids and revision.version_id not in scope.version_ids:
                        continue
                    by_id = {b.block_id: b for b in catalog.blocks(revision.processing_id)}
                    require(all(bid in by_id for bid in revision.block_ids), "Catalog has missing source blocks")
                    selected.append(SelectedUnit(unit=unit, revision=revision, applicability=item,
                                                 blocks=tuple(by_id[bid] for bid in revision.block_ids)))
        return UnitSelection(catalog_revision=catalog.revision, resolved_date=day, units=tuple(selected),
                             ambiguous_unit_ids=tuple(ambiguous))


__all__ = [
    'SelectedUnit',
    'UnitSelection',
    'SystemClock',
    'UnitScopeResolver',
]
