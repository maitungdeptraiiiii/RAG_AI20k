from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from rag.ingest.dedup import DedupResult
from scripts.demo_versioning import run_demo
from rag.models.content import Block, Locator, TableData
from rag.models.document import ApplicabilityRecord, ChangeRequest, DocumentRecord, IdentityHint, ProcessingRecord, QueryScope, SourceRecord
from rag.models.results import ParseResult
from rag.models.serialization import from_json
from rag.models.common import canonical_json
from rag.versioning.repository import ConcurrentUpdateError, VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver


NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
INITIAL = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1))
FULL = ChangeRequest(kind="full", effective_from=date(2026, 7, 1), supersedes_version_ids=("v1",))


@pytest.fixture
def repository(tmp_path):
    result = VersionRepository(tmp_path / "catalog.sqlite")
    result.add_document(DocumentRecord(document_id="doc-a", title="Phí", document_type="policy", language="vi", created_at=NOW))
    return result


def bundle(version="v1", *, suffix="", content="100.000 đồng"):
    source_id, processing_id = f"s-{version}{suffix}", f"p-{version}{suffix}"
    source = SourceRecord(source_id=source_id, source_uri="demo://input", display_name="input.txt", media_type="text/plain",
                          raw_artifact="raw/input.txt", raw_checksum="a" * 64, collected_at=NOW)
    processing = ProcessingRecord(processing_id=processing_id, version_id=version, source_id=source_id,
                                  parser_name="fake", parser_version="1", normalization_config_id="nfc-v1",
                                  content_checksum=("a" if content == "100.000 đồng" else "b") * 64,
                                  coverage="complete", created_at=NOW)
    block = Block(block_id=f"{processing_id}:0", processing_id=processing_id, version_id=version, order=0,
                  kind="paragraph", text=content, origin="native", locator=Locator(source_id=source_id, page=1))
    return source, ParseResult(processing=processing, blocks=(block,))


def propose(repository, parsed, change, *, duplicate=None, action=None):
    return FullVersionResolver().propose(parsed, hint=IdentityHint(document_id="doc-a"), change=change,
                                         dedup=DedupResult(matches=(), action=action or ("link_existing" if duplicate else "continue"),
                                                           existing_version_id=duplicate, findings=()), catalog=repository.snapshot())


def import_version(repository, version="v1", *, change=INITIAL, suffix="", content="100.000 đồng"):
    source, parsed = bundle(version, suffix=suffix, content=content)
    plan = propose(repository, parsed, change)
    return repository.commit(plan, parsed, source, approve=True)


def selected(repository, day, **filters):
    return UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=day, **filters), catalog=repository.snapshot())


def test_full_replacement_boundary_history_and_restart(repository):
    import_version(repository)
    old_snapshot = repository.snapshot()
    import_version(repository, "v2", change=FULL, content="120.000 đồng")
    assert selected(repository, date(2025, 12, 31)).units == ()
    assert selected(repository, date(2026, 6, 30)).units[0].revision.version_id == "v1"
    assert selected(repository, date(2026, 7, 1)).units[0].revision.version_id == "v2"
    assert selected(repository, date(2026, 8, 1)).units[0].blocks[0].text == "120.000 đồng"
    history = UnitScopeResolver().resolve_units(QueryScope(mode="all_versions"), catalog=repository.snapshot())
    assert [u.revision.version_id for u in history.units] == ["v1", "v2"]
    restarted = VersionRepository(repository.database)
    assert restarted.snapshot() == repository.snapshot()
    assert old_snapshot.applicability_records[0].effective_to is None  # detached snapshot


def test_future_version_does_not_take_effect_early(repository):
    import_version(repository)
    import_version(repository, "v2", change=replace(FULL, effective_from=date(2027, 1, 1)), content="120.000 đồng")
    assert selected(repository, date(2026, 11, 6)).units[0].revision.version_id == "v1"
    assert selected(repository, date(2027, 1, 1)).units[0].revision.version_id == "v2"


def test_current_scope_uses_injected_clock_and_filters(repository):
    import_version(repository)
    import_version(repository, "v2", change=FULL, content="120.000 đồng")
    clock = SimpleNamespace(today=lambda timezone: date(2026, 3, 1))
    result = UnitScopeResolver().resolve_units(QueryScope(), catalog=repository.snapshot(), clock=clock)
    assert result.resolved_date == date(2026, 3, 1)
    assert result.units[0].revision.version_id == "v1"
    assert selected(repository, date(2026, 8, 1), version_ids=("v1",)).units == ()
    assert selected(repository, date(2026, 8, 1), document_ids=("other",)).units == ()


def test_plan_commit_idempotent_and_explicit_approval_required(repository):
    source, parsed = bundle()
    plan = propose(repository, parsed, INITIAL)
    with pytest.raises(ValueError, match="approval"):
        repository.commit(plan, parsed, source)
    first = repository.commit(plan, parsed, source, approve=True)
    assert repository.commit(plan, parsed, source, approve=True) == first
    assert len(repository.snapshot().versions("doc-a")) == 1
    assert len(repository.snapshot().sources("doc-a")) == 1
    with pytest.raises(ValueError, match="different request"):
        repository.commit(plan, parsed, replace(source, display_name="changed"), approve=True)


def test_duplicate_old_upload_preserves_current_and_records_source(repository):
    import_version(repository)
    import_version(repository, "v2", change=FULL, content="120.000 đồng")
    source, parsed = bundle("v1", suffix="-upload-again")
    plan = propose(repository, parsed, INITIAL, duplicate="v1")
    result = repository.commit(plan, parsed, source, approve=True)
    assert result.status == "duplicate"
    snapshot = repository.snapshot()
    assert len(snapshot.versions("doc-a")) == 2
    assert len(snapshot.processing_records) == 2  # no new extraction/chunk work stored
    assert len(snapshot.sources("doc-a")) == 3
    assert selected(repository, date(2026, 8, 1)).units[0].revision.version_id == "v2"


def test_duplicate_with_changed_metadata_or_content_rejected(repository):
    import_version(repository)
    _, parsed = bundle("v1", suffix="-again")
    with pytest.raises(ValueError, match="metadata"):
        propose(repository, parsed, replace(INITIAL, effective_from=date(2026, 2, 1)), duplicate="v1")
    _, changed = bundle("v1", suffix="-changed", content="120.000 đồng")
    with pytest.raises(ValueError, match="extraction/config"):
        propose(repository, changed, INITIAL, duplicate="v1")


@pytest.mark.parametrize("change", [
    ChangeRequest(kind="initial"),
    ChangeRequest(kind="full", effective_from=date(2026, 7, 1)),
    ChangeRequest(kind="full", effective_from=date(2026, 7, 1), supersedes_version_ids=("other-doc-version",)),
    ChangeRequest(kind="full", effective_from=date(2025, 7, 1), supersedes_version_ids=("v1",)),
    ChangeRequest(kind="full", effective_from=date(2026, 1, 1), supersedes_version_ids=("v1",)),
    ChangeRequest(kind="partial", effective_from=date(2026, 7, 1), unit_mapping=(("u1", "u2"),)),
])
def test_uncertain_or_unsupported_change_requires_review(repository, change):
    import_version(repository)
    source, parsed = bundle("v2")
    plan = propose(repository, parsed, change)
    assert plan.action == "review"
    assert plan.review_reasons
    with pytest.raises(ValueError):
        repository.commit(plan, parsed, source, approve=True)
    assert len(repository.snapshot().versions("doc-a")) == 1


def test_incomplete_extraction_or_detector_review_cannot_publish(repository):
    source, parsed = bundle()
    parsed = replace(parsed, processing=replace(parsed.processing, coverage="incomplete"))
    assert propose(repository, parsed, INITIAL).action == "review"
    _, good = bundle()
    assert propose(repository, good, INITIAL, action="review").action == "review"


def test_stale_plan_cannot_overwrite_another_writer(repository):
    source, parsed = bundle()
    plan = propose(repository, parsed, INITIAL)
    another = VersionRepository(repository.database)
    another.add_document(DocumentRecord(document_id="doc-b", title="Other", document_type="policy", language="vi", created_at=NOW))
    with pytest.raises(ConcurrentUpdateError):
        repository.commit(plan, parsed, source, approve=True)
    assert repository.snapshot().versions("doc-a") == ()


def test_failed_commit_rolls_back_closed_interval_and_inserted_version(repository):
    import_version(repository)
    before = repository.snapshot()
    source, parsed = bundle("v2", content="120.000 đồng")
    plan = propose(repository, parsed, FULL)
    # Collision at source insertion occurs after all version/timeline writes.
    source = replace(source, source_id=before.source_records[0].source_id)
    parsed = replace(parsed, processing=replace(parsed.processing, source_id=source.source_id),
                     blocks=tuple(replace(b, locator=replace(b.locator, source_id=source.source_id)) for b in parsed.blocks))
    with pytest.raises(ValueError, match="Source ID"):
        repository.commit(plan, parsed, source, approve=True)
    assert repository.snapshot() == before


def test_cross_document_source_and_tampered_plan_rejected(repository):
    source, parsed = bundle()
    plan = propose(repository, parsed, INITIAL)
    with pytest.raises(ValueError, match="another document"):
        repository.commit(plan, parsed, replace(source, document_id="doc-b"), approve=True)
    revision = replace(plan.candidate_unit_revisions[0], block_ids=("missing",))
    with pytest.raises(ValueError, match="all extraction blocks"):
        repository.commit(replace(plan, candidate_unit_revisions=(revision,)), parsed, source, approve=True)
    assert repository.snapshot().versions("doc-a") == ()


def test_ambiguous_temporal_scope_does_not_select_arbitrarily(repository):
    import_version(repository)
    snapshot = repository.snapshot()
    first = snapshot.applicability_records[0]
    ambiguous = replace(first, applicability_id="conflicting-record")
    snapshot = replace(snapshot, applicability_records=(first, ambiguous))
    result = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=date(2026, 3, 1)), catalog=snapshot)
    assert result.units == ()
    assert result.ambiguous_unit_ids == (snapshot.unit_records[0].unit_id,)


def test_unapproved_versions_not_selected_even_in_history(repository):
    import_version(repository)
    snapshot = repository.snapshot()
    snapshot = replace(snapshot, version_records=(replace(snapshot.version_records[0], approval="pending"),))
    assert UnitScopeResolver().resolve_units(QueryScope(mode="all_versions"), catalog=snapshot).units == ()


def test_nested_table_serialization_preserves_shape_and_unknown_confidence():
    _, parsed = bundle()
    table = TableData(headers=(("Phí", "Đơn vị"),), rows=(("120.000", "đồng"),), column_units=("đồng", None))
    block = replace(parsed.blocks[0], kind="table", table=table, ocr_confidence=None,
                    locator=Locator(source_id=parsed.processing.source_id, page=2, bbox=(.1, .2, .8, .9)))
    assert from_json(Block, canonical_json(block)) == block
    with pytest.raises(ValueError):
        from_json(Block, canonical_json({**block.__dict__, "schema_version": "unknown"}))


def test_demo_is_repeatable_and_reopens_database(tmp_path):
    first = run_demo(tmp_path / "demo.sqlite")
    again = run_demo(tmp_path / "demo.sqlite")
    assert first["restart_preserved"] and again["restart_preserved"]
    assert first["history_version_count"] == again["history_version_count"] == 2
    assert [item["status"] for item in again["imports"]] == ["duplicate", "duplicate"]


def test_three_versions_keep_each_historical_interval(repository):
    import_version(repository)
    import_version(repository, "v2", change=FULL, content="120.000 đồng")
    import_version(repository, "v3", content="130.000 đồng",
                   change=ChangeRequest(kind="full", effective_from=date(2027, 1, 1), supersedes_version_ids=("v2",)))
    for day, expected in ((date(2026, 3, 1), "v1"), (date(2026, 8, 1), "v2"), (date(2027, 1, 1), "v3")):
        assert selected(repository, day).units[0].revision.version_id == expected


def test_backdated_upload_does_not_destroy_scheduled_version(repository):
    import_version(repository)
    import_version(repository, "v2", change=replace(FULL, effective_from=date(2027, 1, 1)), content="120.000 đồng")
    _, parsed = bundle("v-between")
    plan = propose(repository, parsed, FULL)
    assert plan.action == "review"
    assert selected(repository, date(2027, 1, 1)).units[0].revision.version_id == "v2"
