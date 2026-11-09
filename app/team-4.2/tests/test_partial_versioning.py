from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib

import pytest

from rag.versioning.articles import legal_article_assignments
from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupResult
from scripts.demo_partial_versioning import run_demo
from rag.models.content import Block, Locator
from rag.models.document import ChangeRequest, DocumentRecord, IdentityHint, ProcessingRecord, QueryScope, SourceRecord, UnitAssignment
from rag.models.results import ParseResult
from rag.versioning.repository import ConcurrentUpdateError, VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
JULY = date(2026, 7, 1)


def bundle(version, articles=(1, 2, 3), *, suffix=""):
    source_id, processing_id = f"s-{version}{suffix}", f"p-{version}{suffix}"
    texts = tuple(f"Điều {n}. Quy định\nNội dung Điều {n} của {version}." for n in articles)
    source = SourceRecord(source_id=source_id, source_uri="demo://articles", display_name="articles.txt", media_type="text/plain",
                          raw_artifact="raw/articles.txt", raw_checksum=hashlib.sha256("\n".join(texts).encode()).hexdigest(), collected_at=NOW)
    processing = ProcessingRecord(processing_id=processing_id, version_id=version, source_id=source_id,
                                  parser_name="fake", parser_version="1", normalization_config_id="nfc-v1",
                                  content_checksum=canonical_checksum(texts), coverage="complete", created_at=NOW)
    blocks = tuple(Block(block_id=f"{processing_id}:{i}", processing_id=processing_id, version_id=version,
                         order=i, kind="paragraph", text=text, origin="native",
                         locator=Locator(source_id=source_id, page=i + 1)) for i, text in enumerate(texts))
    return source, ParseResult(processing=processing, blocks=blocks)


def plan(repo, parsed, change, duplicate=None):
    return FullVersionResolver().propose(parsed, hint=IdentityHint(document_id="doc"), change=change, catalog=repo.snapshot(),
                                         dedup=DedupResult(matches=(), action="link_existing" if duplicate else "continue",
                                                           existing_version_id=duplicate, findings=()))


def import_initial(repo):
    source, parsed = bundle("v1")
    change = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1),
                           unit_assignments=legal_article_assignments(parsed, confirm_complete=True))
    result = plan(repo, parsed, change)
    repo.commit(result, parsed, source, approve=True)


@pytest.fixture
def repository(tmp_path):
    repo = VersionRepository(tmp_path / "catalog.sqlite")
    repo.add_document(DocumentRecord(document_id="doc", title="Policy", document_type="policy", language="vi", created_at=NOW))
    import_initial(repo)
    return repo


def revision(repo, key, version):
    catalog = repo.snapshot()
    unit = next(u for u in catalog.units("doc") if u.unit_key == f"article:{key}")
    return next(r for r in catalog.revisions(unit.unit_id) if r.version_id == version)


def partial(repo, version="v2", articles=(3,), *, day=JULY, old_version="v1", suffix=""):
    source, parsed = bundle(version, articles, suffix=suffix)
    mapping = tuple((revision(repo, n, old_version).unit_revision_id, f"article:{n}") for n in articles)
    change = ChangeRequest(kind="partial", effective_from=day, supersedes_version_ids=(old_version,),
                           unit_mapping=mapping, unit_assignments=legal_article_assignments(parsed, confirm_complete=True))
    return source, parsed, change


def selected(repo, day):
    result = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=day), catalog=repo.snapshot())
    return {item.unit.unit_key: item for item in result.units}


def test_partial_preserves_unaffected_articles_boundary_and_restart(repository):
    original = repository.snapshot()
    source, parsed, change = partial(repository)
    proposed = plan(repository, parsed, change)
    assert proposed.action == "create"
    assert proposed.candidate_units == ()
    assert len(proposed.candidate_unit_revisions) == 1
    repository.commit(proposed, parsed, source, approve=True)
    before, after = selected(repository, date(2026, 6, 30)), selected(repository, JULY)
    assert [before[f"article:{n}"].revision.version_id for n in (1, 2, 3)] == ["v1"] * 3
    assert [after[f"article:{n}"].revision.version_id for n in (1, 2, 3)] == ["v1", "v1", "v2"]
    assert after["article:3"].blocks[0].locator.source_id == source.source_id
    for n in (1, 2):
        old = next(a for a in original.applicability_records if a.unit_revision_id == revision(repository, n, "v1").unit_revision_id)
        assert old in repository.snapshot().applicability_records
    assert VersionRepository(repository.database).snapshot() == repository.snapshot()


def test_multiple_revised_articles_and_future_effect(repository):
    source, parsed, change = partial(repository, articles=(1, 3), day=date(2027, 1, 1))
    repository.commit(plan(repository, parsed, change), parsed, source, approve=True)
    assert {item.revision.version_id for item in selected(repository, date(2026, 11, 6)).values()} == {"v1"}
    after = selected(repository, date(2027, 1, 1))
    assert [after[f"article:{n}"].revision.version_id for n in (1, 2, 3)] == ["v2", "v1", "v2"]


def test_later_amendment_can_target_still_active_article_from_older_version(repository):
    source, parsed, change = partial(repository)
    repository.commit(plan(repository, parsed, change), parsed, source, approve=True)
    source, parsed, change = partial(repository, "v3", (2,), day=date(2026, 8, 1))
    repository.commit(plan(repository, parsed, change), parsed, source, approve=True)
    after = selected(repository, date(2026, 8, 1))
    assert [after[f"article:{n}"].revision.version_id for n in (1, 2, 3)] == ["v1", "v3", "v2"]


def test_full_replacement_after_partial_closes_mixed_sources_and_keeps_history(repository):
    source, parsed, change = partial(repository)
    repository.commit(plan(repository, parsed, change), parsed, source, approve=True)
    source, parsed = bundle("v3", (1, 2))  # full new version omits old article 3
    change = ChangeRequest(kind="full", effective_from=date(2027, 1, 1), supersedes_version_ids=("v1", "v2"),
                           unit_assignments=legal_article_assignments(parsed, confirm_complete=True))
    repository.commit(plan(repository, parsed, change), parsed, source, approve=True)
    after = selected(repository, date(2027, 1, 1))
    assert set(after) == {"article:1", "article:2"}
    assert {item.revision.version_id for item in after.values()} == {"v3"}
    assert len(selected(repository, date(2026, 8, 1))) == 3


def test_duplicate_partial_does_not_close_unchanged_articles_again(repository):
    source, parsed, change = partial(repository)
    repository.commit(plan(repository, parsed, change), parsed, source, approve=True)
    before = repository.snapshot()
    source, parsed, change = partial(repository, suffix="-again")
    duplicate = plan(repository, parsed, change, duplicate="v2")
    assert repository.commit(duplicate, parsed, source, approve=True).status == "duplicate"
    after = repository.snapshot()
    assert after.applicability_records == before.applicability_records
    assert after.revision_records == before.revision_records
    assert len(after.source_records) == len(before.source_records) + 1


@pytest.mark.parametrize("variant", ["unknown", "wrong-unit", "duplicate-old", "missing", "incomplete", "unassigned", "wrong-version"])
def test_invalid_partial_mapping_is_reviewed(repository, variant):
    source, parsed, change = partial(repository)
    if variant == "unknown":
        change = replace(change, unit_mapping=(("missing", "article:3"),))
    elif variant == "wrong-unit":
        change = replace(change, unit_mapping=((revision(repository, 1, "v1").unit_revision_id, "article:3"),))
    elif variant == "duplicate-old":
        change = replace(change, unit_mapping=change.unit_mapping * 2)
    elif variant == "missing":
        change = replace(change, unit_assignments=())
    elif variant == "incomplete":
        change = replace(change, unit_assignments=tuple(replace(a, complete=False) for a in change.unit_assignments))
    elif variant == "unassigned":
        change = replace(change, unit_assignments=tuple(replace(a, block_ids=("unknown-block",)) for a in change.unit_assignments))
    else:
        change = replace(change, supersedes_version_ids=("other-document-version",))
    proposed = plan(repository, parsed, change)
    assert proposed.action == "review"
    assert proposed.review_reasons
    with pytest.raises(ValueError):
        repository.commit(proposed, parsed, source, approve=True)


def test_inactive_revision_cannot_be_replaced_twice(repository):
    source, parsed, change = partial(repository)
    repository.commit(plan(repository, parsed, change), parsed, source, approve=True)
    source, parsed, change = partial(repository, "v3", day=date(2026, 8, 1))
    assert plan(repository, parsed, change).action == "review"


def test_repo_rejects_tampered_plan_that_closes_unaffected_article(repository):
    source, parsed, change = partial(repository)
    proposed = plan(repository, parsed, change)
    old = next(a for a in repository.snapshot().applicability_records
               if a.unit_revision_id == revision(repository, 1, "v1").unit_revision_id)
    closing = next(c for c in proposed.applicability_changes if c.previous is not None)
    altered = replace(closing, previous=old, proposed=replace(old, effective_to=JULY))
    proposed = replace(proposed, applicability_changes=(altered, *[c for c in proposed.applicability_changes if c.previous is None]))
    before = repository.snapshot()
    with pytest.raises(ValueError, match="affected active scope"):
        repository.commit(proposed, parsed, source, approve=True)
    assert repository.snapshot() == before


def test_partial_failure_rolls_back_all_timeline_changes(repository):
    source, parsed, change = partial(repository)
    proposed = plan(repository, parsed, change)
    before = repository.snapshot()
    source = replace(source, source_id=before.source_records[0].source_id)
    parsed = replace(parsed, processing=replace(parsed.processing, source_id=source.source_id),
                     blocks=tuple(replace(b, locator=replace(b.locator, source_id=source.source_id)) for b in parsed.blocks))
    with pytest.raises(ValueError, match="Source ID"):
        repository.commit(proposed, parsed, source, approve=True)
    assert repository.snapshot() == before


def test_stale_partial_plan_cannot_overwrite_new_version(repository):
    source, parsed, change = partial(repository)
    stale = plan(repository, parsed, change)
    other_source, other_parsed, other_change = partial(repository, "v-other", (2,))
    repository.commit(plan(repository, other_parsed, other_change), other_parsed, other_source, approve=True)
    with pytest.raises(ConcurrentUpdateError):
        repository.commit(stale, parsed, source, approve=True)


def test_article_helper_does_not_drop_preamble_or_merge_multiple_headings():
    _, parsed = bundle("v1")
    assignments = legal_article_assignments(parsed)
    assert not assignments[0].complete
    assert [a.unit_key for a in assignments] == ["article:1", "article:2", "article:3"]
    for text in ("Lời mở đầu", "Điều 1. A\nĐiều 2. B"):
        altered = replace(parsed, blocks=(replace(parsed.blocks[0], text=text),))
        with pytest.raises(ValueError):
            legal_article_assignments(altered)


def test_existing_whole_document_requires_migration(tmp_path):
    repo = VersionRepository(tmp_path / "legacy.sqlite")
    repo.add_document(DocumentRecord(document_id="doc", title="Policy", document_type="policy", language="vi", created_at=NOW))
    source, parsed = bundle("v1")
    change = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1))
    repo.commit(plan(repo, parsed, change), parsed, source, approve=True)
    source, parsed = bundle("v2", (3,))
    change = ChangeRequest(kind="partial", effective_from=JULY, supersedes_version_ids=("v1",),
                           unit_mapping=((repo.snapshot().revision_records[0].unit_revision_id, "article:3"),),
                           unit_assignments=legal_article_assignments(parsed, confirm_complete=True))
    proposed = plan(repo, parsed, change)
    assert proposed.action == "review" and "migration" in proposed.review_reasons[0]


def test_partial_demo_repeat_and_restart(tmp_path):
    first = run_demo(tmp_path / "partial.sqlite")
    second = run_demo(tmp_path / "partial.sqlite")
    assert first["restart_preserved"] and second["restart_preserved"]
    assert [a["version"] for a in first["from_2026_07_01"]] == ["v1", "v1", "v2"]
    assert second["imports"] == ["duplicate", "duplicate"]
