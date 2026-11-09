"""Explicit article-level initial/full/partial version plans.

Partial mapping is (OLD unit_revision_id, NEW assignment.unit_key). Incoming
blocks must contain the complete revised article, not just amendment directions.
Whole-document catalogs require explicit migration; they are not silently split.
"""

from __future__ import annotations

import re, unicodedata
from dataclasses import replace
from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupResult
from rag.models.common import require
from rag.models.document import (
    ApplicabilityRecord,
    ChangeRequest,
    ContentUnit,
    IdentityHint,
    UnitAssignment,
    UnitRevision,
    VersionRecord,
)
from rag.models.results import ParseResult
from rag.versioning.interfaces import ApplicabilityChange, CatalogView, VersionPlan
from rag.versioning.resolver import _same_extraction, _uuid
from rag.versioning.amendment_guard import amendment_fragment_reasons
from rag.versioning.effectivity_guard import unsupported_effectivity_reasons


def legal_article_assignments(parsed: ParseResult, *, confirm_complete: bool = False) -> tuple[UnitAssignment, ...]:
    """Group already separated blocks under explicit 'Điều N.'/'Điều N:' headings.

    Unassigned preamble/duplicate headings raise instead of dropping source text.
    Returns incomplete assignments unless caller explicitly confirms full text.
    This helper is not an OCR parser or legal amendment interpreter.
    """
    groups: list[tuple[str, str, list[str]]] = []
    for block in sorted(parsed.blocks, key=lambda b: b.order):
        text = unicodedata.normalize("NFC", block.text).strip()
        matches = list(re.finditer(r"(?m)^Điều\s+(\d+[a-zA-ZđĐ]?)\s*[.:]\s*([^\n]*)", text))
        require(len(matches) <= 1, "Split multiple article headings into blocks before assigning units")
        if matches:
            match = matches[0]
            require(match.start() == 0, "Unassigned text before article heading")
            key = f"article:{match.group(1).lower()}"
            require(all(key != old[0] for old in groups), "Duplicate article heading; confirm boundaries manually")
            groups.append((key, match.group(0), [block.block_id]))
        else:
            require(bool(groups), "Preamble/unheaded blocks require explicit unit assignments")
            groups[-1][2].append(block.block_id)
    require(bool(groups), "No article headings found")
    return tuple(UnitAssignment(unit_key=key, title=title, block_ids=tuple(ids), complete=confirm_complete)
                 for key, title, ids in groups)


class ArticleVersionResolver:
    def propose(self, parsed: ParseResult, *, hint: IdentityHint, dedup: DedupResult,
                change: ChangeRequest, catalog: CatalogView) -> VersionPlan:
        require(bool(hint.document_id), "Confirmed document_id is required")
        documents = catalog.documents(hint)
        require(len(documents) == 1, "Create/confirm the document before planning its version")
        document_id = documents[0].document_id
        candidate = VersionRecord(version_id=parsed.processing.version_id, document_id=document_id,
                                  change_kind=change.kind, created_at=parsed.processing.created_at,
                                  declared_effective_from=change.effective_from,
                                  supersedes_version_ids=change.supersedes_version_ids)

        def review(reason):
            return VersionPlan(plan_id=_uuid(), base_catalog_revision=catalog.revision,
                               document_id=document_id, candidate_version=candidate, candidate_units=(),
                               candidate_unit_revisions=(), applicability_changes=(), required_review_ids=(),
                               action="review", review_reasons=(reason,))

        assignments = change.unit_assignments
        fragment_reasons = amendment_fragment_reasons(parsed, assignments=assignments)
        if fragment_reasons:
            return review("; ".join(fragment_reasons))
        effectivity_reasons = unsupported_effectivity_reasons(parsed, effective_from=change.effective_from)
        if effectivity_reasons:
            return review("; ".join(effectivity_reasons))
        if change.effective_from is None:
            return review("Effective date is unknown")
        if not parsed.blocks or parsed.processing.coverage != "complete" or parsed.findings or dedup.findings or dedup.action == "review":
            return review("Extraction/dedup is incomplete or requires review")
        if not assignments or any(not item.complete for item in assignments):
            return review("Complete revised text and explicit assignments are required for every incoming unit")
        keys = [a.unit_key for a in assignments]
        assigned_ids = [bid for a in assignments for bid in a.block_ids]
        if (len(set(keys)) != len(keys) or len(set(assigned_ids)) != len(assigned_ids)
                or set(assigned_ids) != {b.block_id for b in parsed.blocks}):
            return review("Assignments must cover all extraction blocks exactly once with unique unit keys")
        by_block = {b.block_id: b for b in parsed.blocks}
        if any(tuple(sorted(a.block_ids, key=lambda bid: by_block[bid].order)) != a.block_ids for a in assignments):
            return review("Assignment blocks must be in reading order")
        if len(set(change.supersedes_version_ids)) != len(change.supersedes_version_ids):
            return review("Replacement version IDs are duplicated")

        versions = catalog.versions(document_id)
        old_units = catalog.units(document_id)
        if any(u.unit_key == "__whole_document__" for u in old_units):
            return review("Whole-document catalog needs an explicit article migration before partial updates")
        if "__whole_document__" in keys:
            return review("Article assignments cannot use the reserved whole-document key")
        by_key = {u.unit_key: u for u in old_units}

        if dedup.action == "link_existing":
            target = next((v for v in versions if v.version_id == dedup.existing_version_id), None)
            require(target is not None and target.approval == "approved", "Duplicate target must belong to this document")
            require((target.change_kind, target.declared_effective_from, target.supersedes_version_ids) ==
                    (change.kind, change.effective_from, change.supersedes_version_ids), "Duplicate metadata mismatch")
            require(any(_same_extraction(parsed.processing, p) for p in catalog.processing(target.version_id)),
                    "Duplicate extraction/config mismatch")
            stored_revisions = [r for u in old_units for r in catalog.revisions(u.unit_id) if r.version_id == target.version_id]
            stored_layout = {}
            for revision in stored_revisions:
                unit = next(u for u in old_units if u.unit_id == revision.unit_id)
                old_blocks = {b.block_id: b for b in catalog.blocks(revision.processing_id)}
                stored_layout[unit.unit_key] = tuple(old_blocks[bid].order for bid in revision.block_ids)
            require(stored_layout == {a.unit_key: tuple(by_block[bid].order for bid in a.block_ids) for a in assignments},
                    "Duplicate unit partition differs from stored version")
            if change.kind == "partial":
                stored_mapping = {(old_id, next(u.unit_key for u in old_units if u.unit_id == r.unit_id))
                                  for r in stored_revisions for app in catalog.applicability(document_id)
                                  if app.unit_revision_id == r.unit_revision_id for old_id in app.replaces}
                require(set(change.unit_mapping) == stored_mapping and len(change.unit_mapping) == len(stored_mapping),
                        "Duplicate replacement mapping differs from stored version")
            return VersionPlan(plan_id=_uuid(), base_catalog_revision=catalog.revision, document_id=document_id,
                               candidate_version=target, candidate_units=(), candidate_unit_revisions=(),
                               applicability_changes=(), required_review_ids=(), action="link_existing")

        require(all(v.version_id != candidate.version_id for v in versions), "Version ID already exists")
        day = change.effective_from
        all_revisions = {r.unit_revision_id: r for u in old_units for r in catalog.revisions(u.unit_id)}
        active = [a for a in catalog.applicability(document_id) if a.applies_on(day)]
        if change.kind == "initial":
            if versions or change.supersedes_version_ids or change.unit_mapping:
                return review("Initial article version cannot replace existing content")
            closing = []
        else:
            if any(v.declared_effective_from is None or v.declared_effective_from >= day
                   for v in versions if v.approval == "approved"):
                return review("Backdated/simultaneous/scheduled-branch changes require timeline reconciliation")
            if change.kind == "partial":
                mapping = change.unit_mapping
                if (len({old for old, _ in mapping}) != len(mapping)
                        or len({key for _, key in mapping}) != len(mapping)
                        or {key for _, key in mapping} != set(keys)):
                    return review("Partial mapping must be one-to-one and cover exactly the revised units")
                closing = []
                for old_id, key in mapping:
                    unit = by_key.get(key)
                    revision = all_revisions.get(old_id)
                    unit_active = [a for a in active if all_revisions[a.unit_revision_id].unit_id == unit.unit_id] if unit else []
                    if unit is None or revision is None or revision.unit_id != unit.unit_id or len(unit_active) != 1 or unit_active[0].unit_revision_id != old_id:
                        return review("Partial target must be the unique active revision of the same document/unit")
                    closing.extend(unit_active)
            else:
                if change.unit_mapping:
                    return review("Full replacement does not accept a partial mapping")
                closing = active
                if len({all_revisions[a.unit_revision_id].unit_id for a in closing}) != len(closing):
                    return review("Active article scope is ambiguous")
            targets = {all_revisions[a.unit_revision_id].version_id for a in closing}
            if not closing or targets != set(change.supersedes_version_ids):
                return review("Replacement version IDs must match the affected active revisions")

        previous_blocks = {}
        for old_app in closing:
            old_revision = all_revisions[old_app.unit_revision_id]
            old_unit = next(u for u in old_units if u.unit_id == old_revision.unit_id)
            old_blocks = {b.block_id: b for b in catalog.blocks(old_revision.processing_id)}
            previous_blocks[old_unit.unit_key] = tuple(old_blocks[bid] for bid in old_revision.block_ids)
        fragment_reasons = amendment_fragment_reasons(parsed, assignments=assignments, previous_blocks=previous_blocks)
        if fragment_reasons:
            return review("; ".join(fragment_reasons))

        changes = [ApplicabilityChange(previous=a, proposed=replace(a, effective_to=day),
                                       reason="Confirmed article replacement") for a in closing]
        created_units, created_revisions = [], []
        for assignment in assignments:
            unit = by_key.get(assignment.unit_key)
            if unit is None:
                unit = ContentUnit(unit_id=_uuid(), document_id=document_id, unit_key=assignment.unit_key, title=assignment.title)
                created_units.append(unit)
            revision = UnitRevision(unit_revision_id=canonical_checksum({"unit": unit.unit_id,
                                    "version": candidate.version_id, "processing": parsed.processing.processing_id,
                                    "blocks": assignment.block_ids}), unit_id=unit.unit_id,
                                    version_id=candidate.version_id, processing_id=parsed.processing.processing_id,
                                    block_ids=assignment.block_ids)
            created_revisions.append(revision)
            replaces = tuple(a.unit_revision_id for a in closing if all_revisions[a.unit_revision_id].unit_id == unit.unit_id)
            changes.append(ApplicabilityChange(previous=None, proposed=ApplicabilityRecord(
                applicability_id=_uuid(), unit_revision_id=revision.unit_revision_id,
                effective_from=day, approval="approved", replaces=replaces), reason="Confirmed complete article text"))
        return VersionPlan(plan_id=_uuid(), base_catalog_revision=catalog.revision, document_id=document_id,
                           candidate_version=replace(candidate, approval="approved"), candidate_units=tuple(created_units),
                           candidate_unit_revisions=tuple(created_revisions), applicability_changes=tuple(changes),
                           required_review_ids=(), action="create")
