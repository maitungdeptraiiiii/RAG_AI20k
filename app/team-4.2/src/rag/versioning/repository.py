"""SQLite catalog for standalone initial/full/partial versions, before chunk/index.

This is NOT CatalogRepository.stage/activate: a catalog commit does not claim
an index exists. Future pipeline integration must publish a generation only
after quality, chunking and actual backend activation.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator
from rag.ingest.checksum import canonical_checksum
from rag.models.common import canonical_json, require
from rag.models.content import Block
from rag.models.document import (
    ApplicabilityRecord,
    ContentUnit,
    DocumentRecord,
    IdentityHint,
    ProcessingRecord,
    SourceRecord,
    UnitRevision,
    UnitAssignment,
    VersionRecord,
)
from rag.models.results import ParseResult
from rag.models.serialization import from_json
from rag.versioning.interfaces import VersionPlan
from rag.versioning.amendment_guard import amendment_fragment_reasons
from rag.versioning.effectivity_guard import unsupported_effectivity_reasons


class ConcurrentUpdateError(RuntimeError):
    """Re-read the catalog and re-plan; the old plan must not overwrite changes."""


@dataclass(frozen=True, kw_only=True)
class VersionCatalog:
    """Detached in-memory read snapshot implementing CatalogView."""
    revision: int
    document_records: tuple[DocumentRecord, ...] = ()
    version_records: tuple[VersionRecord, ...] = ()
    unit_records: tuple[ContentUnit, ...] = ()
    revision_records: tuple[UnitRevision, ...] = ()
    applicability_records: tuple[ApplicabilityRecord, ...] = ()
    processing_records: tuple[ProcessingRecord, ...] = ()
    block_records: tuple[Block, ...] = ()
    source_records: tuple[SourceRecord, ...] = ()

    def documents(self, hint: IdentityHint) -> tuple[DocumentRecord, ...]:
        return tuple(d for d in self.document_records
                     if (hint.document_id is None or d.document_id == hint.document_id)
                     and (hint.external_key is None or d.external_key == hint.external_key)
                     and (hint.issuer is None or d.issuer == hint.issuer)
                     and (hint.title is None or d.title == hint.title))

    def versions(self, document_id: str) -> tuple[VersionRecord, ...]:
        return tuple(v for v in self.version_records if v.document_id == document_id)

    def units(self, document_id: str) -> tuple[ContentUnit, ...]:
        return tuple(u for u in self.unit_records if u.document_id == document_id)

    def revisions(self, unit_id: str) -> tuple[UnitRevision, ...]:
        return tuple(r for r in self.revision_records if r.unit_id == unit_id)

    def applicability(self, document_id: str) -> tuple[ApplicabilityRecord, ...]:
        unit_ids = {u.unit_id for u in self.units(document_id)}
        revision_ids = {r.unit_revision_id for r in self.revision_records if r.unit_id in unit_ids}
        return tuple(a for a in self.applicability_records if a.unit_revision_id in revision_ids)

    def processing(self, version_id: str) -> tuple[ProcessingRecord, ...]:
        return tuple(p for p in self.processing_records if p.version_id == version_id)

    def blocks(self, processing_id: str) -> tuple[Block, ...]:
        return tuple(sorted((b for b in self.block_records if b.processing_id == processing_id), key=lambda b: b.order))

    def sources(self, document_id: str) -> tuple[SourceRecord, ...]:
        return tuple(s for s in self.source_records if s.document_id == document_id)


@dataclass(frozen=True, kw_only=True)
class VersionCommit:
    status: str
    document_id: str
    version_id: str
    catalog_revision: int


_MODELS = {
    "document": DocumentRecord, "version": VersionRecord, "unit": ContentUnit,
    "unit_revision": UnitRevision, "applicability": ApplicabilityRecord,
    "processing": ProcessingRecord, "block": Block, "source": SourceRecord,
}


class VersionRepository:
    def __init__(self, database: str | Path) -> None:
        require(str(database) != ":memory:", "Use a persistent SQLite path")
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection(write=True) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS w02_version_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL)")
            conn.execute("INSERT OR IGNORE INTO w02_version_meta VALUES (1, 0)")
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_version_entities (
                kind TEXT NOT NULL, entity_id TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(kind, entity_id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_version_commits (
                plan_id TEXT PRIMARY KEY, request_checksum TEXT NOT NULL, payload TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_version_audit (
                revision INTEGER NOT NULL, plan_id TEXT NOT NULL, applicability_id TEXT NOT NULL,
                previous_payload TEXT, proposed_payload TEXT NOT NULL)""")

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _insert(conn, kind: str, entity_id: str, record) -> None:
        conn.execute("INSERT INTO w02_version_entities VALUES (?, ?, ?)", (kind, entity_id, canonical_json(record)))

    @staticmethod
    def _snapshot(conn) -> VersionCatalog:
        groups = {kind: [] for kind in _MODELS}
        for row in conn.execute("SELECT * FROM w02_version_entities ORDER BY rowid"):
            groups[row["kind"]].append(from_json(_MODELS[row["kind"]], row["payload"]))
        return VersionCatalog(
            revision=conn.execute("SELECT revision FROM w02_version_meta WHERE singleton=1").fetchone()[0],
            document_records=tuple(groups["document"]), version_records=tuple(groups["version"]),
            unit_records=tuple(groups["unit"]), revision_records=tuple(groups["unit_revision"]),
            applicability_records=tuple(groups["applicability"]), processing_records=tuple(groups["processing"]),
            block_records=tuple(groups["block"]), source_records=tuple(groups["source"]))

    def snapshot(self) -> VersionCatalog:
        with self._connection() as conn:
            return self._snapshot(conn)

    def add_document(self, document: DocumentRecord) -> None:
        with self._connection(write=True) as conn:
            existing = conn.execute("SELECT payload FROM w02_version_entities WHERE kind='document' AND entity_id=?",
                                    (document.document_id,)).fetchone()
            if existing:
                require(existing["payload"] == canonical_json(document), "Document ID already has different metadata")
                return
            self._insert(conn, "document", document.document_id, document)
            conn.execute("UPDATE w02_version_meta SET revision=revision+1 WHERE singleton=1")

    def commit(self, plan: VersionPlan, parsed: ParseResult, source: SourceRecord, *,
               approve: bool = False) -> VersionCommit:
        with self._connection(write=True) as conn:
            return self._commit_in_transaction(conn, plan, parsed, source, approve=approve)

    def _commit_in_transaction(self, conn: sqlite3.Connection, plan: VersionPlan, parsed: ParseResult, source: SourceRecord, *,
               approve: bool = False) -> VersionCommit:
        """Commit an explicitly confirmed version plan atomically, without indexes.

        Repeating the SAME plan/request is idempotent. A different stale plan
        raises ConcurrentUpdateError; caller must re-read and re-propose.
        """
        require(approve, "Explicit approval is required to commit a version plan")
        require(plan.action in ("create", "link_existing") and not plan.required_review_ids and not plan.review_reasons,
                "Plan still needs review or has unsupported action")
        require(not parsed.findings and parsed.processing.coverage == "complete" and bool(parsed.blocks),
                "Only complete extraction without unresolved findings can commit")
        require(source.source_id == parsed.processing.source_id, "Source does not match extraction")
        require(source.document_id in (None, plan.document_id), "Source belongs to another document")
        require(source.version_id in (None, plan.candidate_version.version_id), "Source version differs from plan")
        request_checksum = canonical_checksum({"plan": plan, "parsed": parsed, "source": source})
        previous = conn.execute("SELECT * FROM w02_version_commits WHERE plan_id=?", (plan.plan_id,)).fetchone()
        if previous:
            require(previous["request_checksum"] == request_checksum, "Plan ID reused with different request")
            return from_json(VersionCommit, previous["payload"])
        catalog = self._snapshot(conn)
        if catalog.revision != plan.base_catalog_revision:
            raise ConcurrentUpdateError("Catalog changed; read a new snapshot and re-plan")
        require(bool(catalog.documents(IdentityHint(document_id=plan.document_id))), "Document does not exist")
        require(plan.candidate_version.document_id == plan.document_id and plan.candidate_version.approval == "approved",
                "Version identity/approval does not match plan")

        if plan.action == "create":
            self._validate_create(plan, parsed, catalog)
            version = plan.candidate_version
            self._insert(conn, "version", version.version_id, version)
            self._insert(conn, "processing", parsed.processing.processing_id, parsed.processing)
            for block in parsed.blocks:
                self._insert(conn, "block", block.block_id, block)
            for unit in plan.candidate_units:
                self._insert(conn, "unit", unit.unit_id, unit)
            for revision in plan.candidate_unit_revisions:
                self._insert(conn, "unit_revision", revision.unit_revision_id, revision)
            for change in plan.applicability_changes:
                new = change.proposed
                conn.execute("INSERT INTO w02_version_audit VALUES (?, ?, ?, ?, ?)",
                             (catalog.revision + 1, plan.plan_id, new.applicability_id,
                              canonical_json(change.previous) if change.previous else None, canonical_json(new)))
                if change.previous is None:
                    self._insert(conn, "applicability", new.applicability_id, new)
                else:
                    conn.execute("UPDATE w02_version_entities SET payload=? WHERE kind='applicability' AND entity_id=?",
                                 (canonical_json(new), new.applicability_id))
        else:
            from rag.versioning.resolver import _same_extraction
            target = next((v for v in catalog.versions(plan.document_id)
                           if v.version_id == plan.candidate_version.version_id), None)
            require(target == plan.candidate_version, "Duplicate target differs from stored version")
            require(any(_same_extraction(parsed.processing, p) for p in catalog.processing(target.version_id)),
                    "Duplicate content/config differs from stored version")
            require(not (plan.candidate_units or plan.candidate_unit_revisions or plan.applicability_changes),
                    "Duplicate plan cannot modify timeline or units")

        bound_source = replace(source, document_id=plan.document_id, version_id=plan.candidate_version.version_id)
        stored_source = conn.execute("SELECT payload FROM w02_version_entities WHERE kind='source' AND entity_id=?",
                                     (source.source_id,)).fetchone()
        if stored_source:
            require(stored_source["payload"] == canonical_json(bound_source), "Source ID already exists with different data")
        else:
            self._insert(conn, "source", bound_source.source_id, bound_source)
        result = VersionCommit(status="created" if plan.action == "create" else "duplicate",
                               document_id=plan.document_id, version_id=plan.candidate_version.version_id,
                               catalog_revision=catalog.revision + 1)
        conn.execute("UPDATE w02_version_meta SET revision=? WHERE singleton=1", (result.catalog_revision,))
        conn.execute("INSERT INTO w02_version_commits VALUES (?, ?, ?)",
                     (plan.plan_id, request_checksum, canonical_json(result)))
        return result

    @staticmethod
    def _validate_create(plan: VersionPlan, parsed: ParseResult, catalog: VersionCatalog) -> None:
        version = plan.candidate_version
        require(version.version_id == parsed.processing.version_id, "Version differs from extraction")
        require(version.change_kind in ("initial", "full", "partial") and version.declared_effective_from is not None,
                "A dated initial/full/partial version is required")
        effectivity_reasons = unsupported_effectivity_reasons(parsed, effective_from=version.declared_effective_from)
        require(not effectivity_reasons, "; ".join(effectivity_reasons))
        require(all(v.version_id != version.version_id for v in catalog.version_records), "Version ID already exists")
        old_versions = catalog.versions(plan.document_id)
        old_units = catalog.units(plan.document_id)
        units = (*old_units, *plan.candidate_units)
        require(bool(units) and all(u.document_id == plan.document_id for u in units), "Unit belongs to another document")
        require(len({u.unit_id for u in units}) == len(units)
                and len({u.unit_key for u in units}) == len(units), "Duplicate unit identity/key")
        require(not any(u.unit_key == "__whole_document__" for u in units) or len(units) == 1,
                "Whole-document and article units cannot be mixed without migration")
        revisions = plan.candidate_unit_revisions
        require(bool(revisions) and len({r.unit_id for r in revisions}) == len(revisions)
                and len({r.unit_revision_id for r in revisions}) == len(revisions), "Expected one revision per incoming unit")
        by_unit = {u.unit_id: u for u in units}
        by_block = {b.block_id: b for b in parsed.blocks}
        assigned = [bid for r in revisions for bid in r.block_ids]
        require(len(assigned) == len(set(assigned)) and set(assigned) == set(by_block),
                "Unit revisions must contain all extraction blocks exactly once")
        for revision in revisions:
            require(revision.unit_id in by_unit and revision.version_id == version.version_id
                    and revision.processing_id == parsed.processing.processing_id, "Unit revision identity mismatch")
            require(revision.block_ids == tuple(sorted(revision.block_ids, key=lambda bid: by_block[bid].order)),
                    "Unit revision blocks must be in reading order")
        require({u.unit_id for u in plan.candidate_units} <= {r.unit_id for r in revisions}, "Unused new unit")
        changes = plan.applicability_changes
        require(len({c.proposed.applicability_id for c in changes}) == len(changes), "Duplicate applicability updates")
        new_records = [c.proposed for c in changes if c.previous is None]
        require(len(new_records) == len(revisions) and
                {a.unit_revision_id for a in new_records} == {r.unit_revision_id for r in revisions},
                "Each new revision requires exactly one applicability record")
        day = version.declared_effective_from
        require(all(a.effective_from == day and a.effective_to is None and a.approval == "approved" for a in new_records),
                "Invalid new effective interval")
        existing_records = catalog.applicability(plan.document_id)
        active = {a.applicability_id: a for a in existing_records if a.applies_on(day)}
        closing = [c for c in changes if c.previous is not None]
        old_revisions = {r.unit_revision_id: r for r in catalog.revision_records}
        if version.change_kind == "partial":
            require(not plan.candidate_units and all(by_unit[r.unit_id].unit_key != "__whole_document__" for r in revisions),
                    "Partial update can only replace existing article units")
            touched = {r.unit_id for r in revisions}
            expected = {aid: a for aid, a in active.items() if old_revisions[a.unit_revision_id].unit_id in touched}
            require(len(expected) == len(touched) and
                    {old_revisions[a.unit_revision_id].unit_id for a in expected.values()} == touched,
                    "Partial targets must each have one active revision")
        else:
            expected = active
        require({c.previous.applicability_id for c in closing} == set(expected), "Must close precisely the affected active scope")
        require(len({old_revisions[a.unit_revision_id].unit_id for a in expected.values()}) == len(expected),
                "Affected active scope is ambiguous")
        assignments = tuple(UnitAssignment(unit_key=by_unit[r.unit_id].unit_key, title=by_unit[r.unit_id].title,
                                           block_ids=r.block_ids, complete=True) for r in revisions)
        previous_blocks = {}
        for app in expected.values():
            old_revision = old_revisions[app.unit_revision_id]
            old_blocks = {b.block_id: b for b in catalog.blocks(old_revision.processing_id)}
            previous_blocks[by_unit[old_revision.unit_id].unit_key] = tuple(old_blocks[bid] for bid in old_revision.block_ids)
        fragment_reasons = amendment_fragment_reasons(parsed, assignments=assignments, previous_blocks=previous_blocks)
        require(not fragment_reasons, "; ".join(fragment_reasons))
        for change in closing:
            require(active.get(change.previous.applicability_id) == change.previous
                    and change.proposed == replace(change.previous, effective_to=day), "Invalid timeline amendment")
        for new in new_records:
            revision = next(r for r in revisions if r.unit_revision_id == new.unit_revision_id)
            replaced_ids = {a.unit_revision_id for a in expected.values()
                            if old_revisions[a.unit_revision_id].unit_id == revision.unit_id}
            require(set(new.replaces) == replaced_ids and len(new.replaces) == len(replaced_ids), "Replacement links mismatch")
        if version.change_kind == "initial":
            require(not old_versions and not version.supersedes_version_ids, "Initial version already exists")
        else:
            require(bool(expected), "No active version to replace")
            require(all(v.declared_effective_from is not None and v.declared_effective_from < day
                        for v in old_versions if v.approval == "approved"), "Backdated/future branch needs review")
            revision_versions = {r.unit_revision_id: r.version_id for r in catalog.revision_records}
            require(len(set(version.supersedes_version_ids)) == len(version.supersedes_version_ids) and
                    set(version.supersedes_version_ids) == {revision_versions[a.unit_revision_id] for a in expected.values()},
                    "Replacement version IDs mismatch")
