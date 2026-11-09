"""Version planning and temporal selection; no OCR or index activation."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupResult
from rag.models.common import require
from rag.models.document import (
    ApplicabilityRecord,
    ChangeRequest,
    ContentUnit,
    IdentityHint,
    UnitRevision,
    VersionRecord,
)
from rag.models.results import ParseResult
from rag.versioning.interfaces import ApplicabilityChange, CatalogView, VersionPlan
from rag.versioning.amendment_guard import amendment_fragment_reasons
from rag.versioning.effectivity_guard import unsupported_effectivity_reasons


def _uuid() -> str:
    return str(uuid4())


def _same_extraction(left, right) -> bool:
    return (left.content_checksum, left.parser_name, left.parser_version,
            left.normalization_config_id, left.ocr_engine, left.ocr_config_id, left.coverage) == (
                right.content_checksum, right.parser_name, right.parser_version,
                right.normalization_config_id, right.ocr_engine, right.ocr_config_id, right.coverage)


class FullVersionResolver:
    """Backwards-compatible planner. Caller supplies identity/change.

    Without assignments, initial/full imports keep the whole-document behavior.
    Explicit assignments/partial requests delegate to ArticleVersionResolver.
    """

    def propose(self, parsed: ParseResult, *, hint: IdentityHint, dedup: DedupResult,
                change: ChangeRequest, catalog: CatalogView) -> VersionPlan:
        if change.unit_assignments or change.kind == "partial":
            from rag.versioning.articles import ArticleVersionResolver
            return ArticleVersionResolver().propose(parsed, hint=hint, dedup=dedup, change=change, catalog=catalog)
        require(bool(hint.document_id), "Confirmed document_id is required")
        documents = catalog.documents(hint)
        require(len(documents) == 1 and documents[0].document_id == hint.document_id,
                "Create/confirm the document before planning its version")
        document_id = documents[0].document_id
        existing = catalog.versions(document_id)
        candidate = VersionRecord(
            version_id=parsed.processing.version_id, document_id=document_id,
            change_kind=change.kind, created_at=parsed.processing.created_at,
            declared_effective_from=change.effective_from,
            supersedes_version_ids=change.supersedes_version_ids,
        )

        def review(reason: str) -> VersionPlan:
            return VersionPlan(plan_id=_uuid(), base_catalog_revision=catalog.revision,
                               document_id=document_id, candidate_version=candidate,
                               candidate_units=(), candidate_unit_revisions=(), applicability_changes=(),
                               required_review_ids=(), action="review", review_reasons=(reason,))

        fragment_reasons = amendment_fragment_reasons(parsed)
        if fragment_reasons:
            return review("; ".join(fragment_reasons))
        effectivity_reasons = unsupported_effectivity_reasons(parsed, effective_from=change.effective_from)
        if effectivity_reasons:
            return review("; ".join(effectivity_reasons))
        if change.effective_from is None:
            return review("Effective date is unknown")
        if parsed.processing.coverage != "complete" or not parsed.blocks:
            return review("Extraction is empty or not confirmed complete")
        if parsed.findings or dedup.findings or dedup.action == "review":
            return review("Extraction/dedup findings require review before version approval")

        if dedup.action == "link_existing":
            target = next((v for v in existing if v.version_id == dedup.existing_version_id), None)
            require(target is not None, "Duplicate must reference a version of the same document")
            require(target.approval == "approved", "Cannot reuse an unapproved version")
            require((target.change_kind, target.declared_effective_from, target.supersedes_version_ids) ==
                    (change.kind, change.effective_from, change.supersedes_version_ids),
                    "Duplicate metadata does not match existing version")
            require(any(_same_extraction(parsed.processing, p) for p in catalog.processing(target.version_id)),
                    "Duplicate extraction/config does not match existing version")
            return VersionPlan(plan_id=_uuid(), base_catalog_revision=catalog.revision,
                               document_id=document_id, candidate_version=target,
                               candidate_units=(), candidate_unit_revisions=(), applicability_changes=(),
                               required_review_ids=(), action="link_existing")

        require(all(v.version_id != candidate.version_id for v in existing),
                "Version ID already exists; reuse explicitly or allocate a new version ID")
        require(len(set(change.supersedes_version_ids)) == len(change.supersedes_version_ids),
                "Duplicate replacement targets")
        applicability = catalog.applicability(document_id)
        changes = []
        replaced = []
        if change.kind == "initial":
            if existing:
                return review("Document already has versions; an explicit replacement relationship is needed")
        else:
            if not existing or not change.supersedes_version_ids:
                return review("Full replacement requires an existing version and explicit replacement targets")
            by_version = {v.version_id: v for v in existing}
            if any(vid not in by_version or by_version[vid].approval != "approved"
                   for vid in change.supersedes_version_ids):
                return review("Replacement target is missing, belongs to another document, or is unapproved")
            # This milestone models a strictly chronological whole-document chain.
            # Backdated insertions/future branches need timeline reconciliation.
            approved_dates = [v.declared_effective_from for v in existing if v.approval == "approved"]
            if any(day is None or day >= change.effective_from for day in approved_dates):
                return review("Backdated, simultaneous or scheduled-branch insertion needs timeline reconciliation")
            active = [a for a in applicability if a.applies_on(change.effective_from)]
            if not active:
                return review("No approved version is active at the replacement date")
            revision_versions = {r.unit_revision_id: r.version_id
                                 for unit in catalog.units(document_id) for r in catalog.revisions(unit.unit_id)}
            active_versions = {revision_versions[a.unit_revision_id] for a in active}
            if active_versions != set(change.supersedes_version_ids):
                return review("Replacement targets do not match the active document scope")
            for previous in active:
                changes.append(ApplicabilityChange(
                    previous=previous, proposed=replace(previous, effective_to=change.effective_from),
                    reason="Confirmed full replacement at the new effective date"))
                replaced.append(previous.unit_revision_id)

        units = catalog.units(document_id)
        if units and (len(units) != 1 or units[0].unit_key != "__whole_document__"):
            return review("Existing article-level units require a more detailed replacement plan")
        unit = units[0] if units else ContentUnit(unit_id=_uuid(), document_id=document_id,
                                                 unit_key="__whole_document__", title=documents[0].title)
        ordered = tuple(b.block_id for b in sorted(parsed.blocks, key=lambda b: b.order))
        revision = UnitRevision(
            unit_revision_id=canonical_checksum({"unit": unit.unit_id, "version": candidate.version_id,
                                                "processing": parsed.processing.processing_id, "blocks": ordered}),
            unit_id=unit.unit_id, version_id=candidate.version_id,
            processing_id=parsed.processing.processing_id, block_ids=ordered)
        changes.append(ApplicabilityChange(previous=None, proposed=ApplicabilityRecord(
            applicability_id=_uuid(), unit_revision_id=revision.unit_revision_id,
            effective_from=change.effective_from, approval="approved", replaces=tuple(replaced)),
            reason="Confirmed initial/full version"))
        return VersionPlan(plan_id=_uuid(), base_catalog_revision=catalog.revision,
                           document_id=document_id, candidate_version=replace(candidate, approval="approved"),
                           candidate_units=() if units else (unit,), candidate_unit_revisions=(revision,),
                           applicability_changes=tuple(changes), required_review_ids=(), action="create")


__all__ = [
    '_uuid',
    '_same_extraction',
    'FullVersionResolver',
]
