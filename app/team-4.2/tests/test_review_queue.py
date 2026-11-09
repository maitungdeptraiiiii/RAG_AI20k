from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from rag.ingest.dedup import DedupResult
from rag.versioning.articles import legal_article_assignments
from scripts.demo_review_queue import run_demo
from rag.models.content import Block, Locator, TargetRef
from rag.models.document import ChangeRequest, DocumentRecord, IdentityHint, ProcessingRecord, QueryScope, SourceRecord
from rag.models.quality import QualityIssue, ReviewDecision
from rag.models.results import ParseResult
from rag.quality.review_queue import ReviewBlockedError, SQLiteReviewService
from rag.versioning.repository import ConcurrentUpdateError, VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
CLEAR = DedupResult(matches=(), action="continue", existing_version_id=None, findings=())
HINT = IdentityHint(document_id="doc")


def issue(issue_id="i1", **overrides):
    return replace(QualityIssue(issue_id=issue_id, code="dedup.near", severity="warning",
                                targets=(TargetRef(source_id="src-1"), TargetRef(source_id="src-2")),
                                message="Possible duplicate", safe_evidence={"score": .95, "nested": {"masked": ["[EMAIL]", None]}},
                                detector_name="fake", detector_version="1", config_id="c1", created_at=NOW), **overrides)


@pytest.fixture
def repository(tmp_path):
    result = VersionRepository(tmp_path / "catalog.sqlite")
    result.add_document(DocumentRecord(document_id="doc", title="Policy", document_type="policy", language="vi", created_at=NOW))
    return result


@pytest.fixture
def queue(repository):
    return SQLiteReviewService(repository, now=lambda: NOW)


def decision(review_id, action="reject", *, payload=None, decision_id="d1"):
    return ReviewDecision(decision_id=decision_id, review_id=review_id, action=action, reviewer="Khánh",
                          reason="Checked fixture source", payload=payload or {}, created_at=NOW + timedelta(minutes=1))


def bundle(version):
    source = SourceRecord(source_id=f"s-{version}", source_uri="demo://source", display_name="source.txt", media_type="text/plain",
                          raw_artifact=f"raw/{version}.txt", raw_checksum=("a" if version == "v1" else "b") * 64,
                          collected_at=NOW)
    processing = ProcessingRecord(processing_id=f"p-{version}", version_id=version, source_id=source.source_id,
                                  parser_name="fake", parser_version="1", normalization_config_id="n1",
                                  content_checksum=("a" if version == "v1" else "b") * 64, coverage="complete", created_at=NOW)
    block = Block(block_id=f"b-{version}", processing_id=processing.processing_id, version_id=version,
                  order=0, kind="paragraph", text=f"Synthetic source {version}: private extraction",
                  origin="native", locator=Locator(source_id=source.source_id, page=1))
    return source, ParseResult(processing=processing, blocks=(block,))


def enqueue_pending(repository, queue, *, findings=()):
    planner = FullVersionResolver()
    source, parsed = bundle("v1")
    initial = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1))
    plan = planner.propose(parsed, hint=HINT, change=initial, dedup=CLEAR, catalog=repository.snapshot())
    repository.commit(plan, parsed, source, approve=True)
    source, parsed = bundle("v2")
    parsed = replace(parsed, findings=findings)
    change = ChangeRequest(kind="full", supersedes_version_ids=("v1",))
    plan = planner.propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=repository.snapshot())
    item = queue.enqueue_version(plan, parsed, source, hint=HINT, change=change, dedup=CLEAR)
    return item, source, parsed, change, plan


def correction(item, **overrides):
    payload = {"effective_from": "2026-07-01", "supersedes_version_ids": ["v1"]}
    payload.update(overrides)
    return decision(item.review_id, "confirm_replacement", payload=payload)


def test_enqueue_details_restart_and_detector_retry_do_not_duplicate(repository, queue):
    first = queue.enqueue((issue(), issue()))
    assert len(first) == 1
    again = queue.enqueue((issue(created_at=NOW + timedelta(hours=1)),))
    assert again == first
    restarted = SQLiteReviewService(VersionRepository(repository.database))
    details = restarted.get(first[0].review_id)
    assert details.revision == 0 and details.issues[0] == issue()
    assert len(restarted.list_items()) == 1
    assert len(details.item.targets) == 2


def test_changed_evidence_or_config_requires_new_issue_id(queue):
    queue.enqueue((issue(),))
    with pytest.raises(ValueError, match="changed evidence/config"):
        queue.enqueue((issue(config_id="changed"),))
    assert len(queue.list_items()) == 1
    queue.enqueue((issue("i2", config_id="changed"),))
    assert len(queue.list_items()) == 2


@pytest.mark.parametrize("action", ["accept", "reject", "keep_both", "request_correction"])
def test_generic_actions_record_reason_and_do_not_modify_catalog(repository, queue, action):
    item = queue.enqueue((issue(),))[0]
    before = repository.snapshot()
    chosen = decision(item.review_id, action)
    resolved = queue.resolve(item.review_id, chosen, expected_revision=0)
    details = queue.get(item.review_id)
    assert resolved.status == "resolved" and details.revision == 1
    assert details.decision == chosen and details.application is None
    assert repository.snapshot() == before
    assert queue.list_items() == () and len(queue.list_items(status="resolved")) == 1
    # Rerun the detector after resolution: do not reopen the old issue.
    assert queue.enqueue((issue(),))[0].status == "resolved"


def test_resolution_retry_is_idempotent_and_two_reviewers_cannot_overwrite(repository, queue):
    item = queue.enqueue((issue(),))[0]
    chosen = decision(item.review_id)
    resolved = queue.resolve(item.review_id, chosen, expected_revision=0)
    assert queue.resolve(item.review_id, chosen, expected_revision=0) == resolved
    second = SQLiteReviewService(VersionRepository(repository.database))
    with pytest.raises(ConcurrentUpdateError):
        second.resolve(item.review_id, decision(item.review_id, "keep_both", decision_id="d2"), expected_revision=0)
    with pytest.raises(ValueError, match="different data"):
        queue.resolve(item.review_id, replace(chosen, reason="Changed reason"), expected_revision=0)
    assert queue.get(item.review_id).decision == chosen


def test_pagination_filters_before_limit(queue):
    items = queue.enqueue(tuple(issue(f"i{n}") for n in range(4)))
    queue.resolve(items[0].review_id, decision(items[0].review_id), expected_revision=0)
    assert [d.item.review_id for d in queue.list_items(limit=2)] == [items[1].review_id, items[2].review_id]
    assert len(queue.list_items(status=None)) == 4
    assert len(queue.list_items(offset=2, limit=2)) == 1
    with pytest.raises(ValueError):
        queue.list_items(limit=0)


def test_missing_date_correction_replans_and_persists_version_atomically(repository, queue):
    item, source, parsed, change, plan = enqueue_pending(repository, queue)
    assert queue.enqueue_version(plan, parsed, source, hint=HINT, change=change, dedup=CLEAR) == item
    before = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=date(2026, 8, 1)), catalog=repository.snapshot())
    assert before.units[0].revision.version_id == "v1"
    assert len(repository.snapshot().versions("doc")) == 1
    # Public details contain safe metadata only, not stored pending source text.
    assert "private extraction" not in repr(queue.get(item.review_id))
    queue.resolve(item.review_id, correction(item), expected_revision=0)
    restarted = VersionRepository(repository.database)
    after = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=date(2026, 8, 1)), catalog=restarted.snapshot())
    assert after.units[0].revision.version_id == "v2"
    assert after.units[0].applicability.decision_id == "d1"
    details = SQLiteReviewService(restarted).get(item.review_id)
    assert details.item.status == "resolved" and details.application.version_id == "v2"


def test_bad_date_or_unknown_decision_fields_do_not_close_review(repository, queue):
    item, *_ = enqueue_pending(repository, queue)
    for changes in ({"effective_from": "bad-date"}, {"unexpected": "value"}, {"effective_from": "2025-01-01"}):
        with pytest.raises(ValueError):
            queue.resolve(item.review_id, correction(item, **changes), expected_revision=0)
    assert queue.get(item.review_id).item.status == "open"
    assert len(repository.snapshot().versions("doc")) == 1


def test_accept_without_fix_does_not_force_version_approval(repository, queue):
    item, *_ = enqueue_pending(repository, queue)
    with pytest.raises(ReviewBlockedError, match="Effective date"):
        queue.resolve(item.review_id, decision(item.review_id, "accept"), expected_revision=0)
    assert queue.get(item.review_id).revision == 0


def test_rejection_keeps_pending_input_out_of_catalog(repository, queue):
    item, *_ = enqueue_pending(repository, queue)
    queue.resolve(item.review_id, decision(item.review_id, "reject"), expected_revision=0)
    assert len(repository.snapshot().versions("doc")) == 1
    assert queue.get(item.review_id).application is None


def test_finding_is_not_silently_removed_by_metadata_confirmation(repository, queue):
    item, *_ = enqueue_pending(repository, queue, findings=(issue(code="ocr.low_confidence"),))
    with pytest.raises(ReviewBlockedError):
        queue.resolve(item.review_id, correction(item), expected_revision=0)
    assert len(queue.get(item.review_id).issues) == 2
    assert queue.get(item.review_id).item.status == "open"


def test_catalog_changed_since_enqueue_requires_valid_replacement_targets(repository, queue):
    item, *_ = enqueue_pending(repository, queue)
    source, parsed = bundle("v-other")
    change = ChangeRequest(kind="full", effective_from=date(2026, 6, 1), supersedes_version_ids=("v1",))
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=repository.snapshot())
    repository.commit(plan, parsed, source, approve=True)
    with pytest.raises(ReviewBlockedError, match="active"):
        queue.resolve(item.review_id, correction(item), expected_revision=0)
    assert queue.get(item.review_id).item.status == "open"
    assert len(repository.snapshot().versions("doc")) == 2
    queue.resolve(item.review_id, correction(item, supersedes_version_ids=["v-other"]), expected_revision=0)
    assert len(repository.snapshot().versions("doc")) == 3


def test_error_after_version_write_rolls_back_catalog_and_queue(repository, queue, monkeypatch):
    item, *_ = enqueue_pending(repository, queue)
    before = repository.snapshot()
    original = queue._apply_version
    def fail_after_write(*args):
        original(*args)
        raise RuntimeError("simulated decision persistence failure")
    monkeypatch.setattr(queue, "_apply_version", fail_after_write)
    with pytest.raises(RuntimeError):
        queue.resolve(item.review_id, correction(item), expected_revision=0)
    assert repository.snapshot() == before
    assert queue.get(item.review_id).revision == 0
    assert queue.get(item.review_id).decision is None
    monkeypatch.setattr(queue, "_apply_version", original)
    assert queue.resolve(item.review_id, correction(item), expected_revision=0).status == "resolved"


def test_invalid_reference_and_unlinked_version_action_are_rejected(queue):
    item = queue.enqueue((issue(),))[0]
    with pytest.raises(ValueError, match="another review"):
        queue.resolve(item.review_id, decision("other"), expected_revision=0)
    with pytest.raises(ValueError, match="linked version"):
        queue.resolve(item.review_id, decision(item.review_id, "link_existing", payload={"version_id": "v1"}), expected_revision=0)
    with pytest.raises(KeyError):
        queue.get("missing")


def test_pending_input_cannot_be_changed_under_same_processing_id(repository, queue):
    item, source, parsed, change, plan = enqueue_pending(repository, queue)
    altered = replace(parsed, blocks=(replace(parsed.blocks[0], text="different extraction"),))
    with pytest.raises(ValueError, match="Pending input changed"):
        queue.enqueue_version(plan, altered, source, hint=HINT, change=change, dedup=CLEAR)
    assert queue.get(item.review_id).item.status == "open"


def test_demo_restarts_and_reruns_without_duplicate_decisions(tmp_path):
    first = run_demo(tmp_path / "review.sqlite")
    second = run_demo(tmp_path / "review.sqlite")
    assert first["review_id"] == second["review_id"]
    assert first["restart_preserved"] and second["restart_preserved"]
    assert first["open_reviews"] == 0 and second["review_revision"] == 1


def test_review_can_apply_partial_article_replacement(repository, queue):
    source, parsed = bundle("v1")
    first = replace(parsed.blocks[0], text="Điều 1. Đối tượng\nNội dung giữ nguyên.")
    second = replace(first, block_id="b-v1:1", order=1, text="Điều 2. Mức phí\nPhí cũ.")
    parsed = replace(parsed, blocks=(first, second))
    initial = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1),
                           unit_assignments=legal_article_assignments(parsed, confirm_complete=True))
    planner = FullVersionResolver()
    initial_plan = planner.propose(parsed, hint=HINT, change=initial, dedup=CLEAR, catalog=repository.snapshot())
    repository.commit(initial_plan, parsed, source, approve=True)
    catalog = repository.snapshot()
    article = next(u for u in catalog.units("doc") if u.unit_key == "article:2")
    old = catalog.revisions(article.unit_id)[0]
    source, parsed = bundle("v2")
    parsed = replace(parsed, blocks=(replace(parsed.blocks[0], text="Điều 2. Mức phí\nPhí mới."),))
    partial = ChangeRequest(kind="partial", supersedes_version_ids=("v1",),
                           unit_mapping=((old.unit_revision_id, "article:2"),),
                           unit_assignments=legal_article_assignments(parsed, confirm_complete=True))
    pending = planner.propose(parsed, hint=HINT, change=partial, dedup=CLEAR, catalog=repository.snapshot())
    item = queue.enqueue_version(pending, parsed, source, hint=HINT, change=partial, dedup=CLEAR)
    chosen = decision(item.review_id, "confirm_replacement", payload={"effective_from": "2026-07-01",
                        "unit_mapping": [[old.unit_revision_id, "article:2"]]})
    queue.resolve(item.review_id, chosen, expected_revision=0)
    selected = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=date(2026, 8, 1)), catalog=repository.snapshot())
    assert [(u.unit.unit_key, u.revision.version_id) for u in selected.units] == [("article:1", "v1"), ("article:2", "v2")]


def test_review_can_link_confirmed_duplicate_without_new_version(repository, queue):
    source, parsed = bundle("v1")
    initial = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1))
    planner = FullVersionResolver()
    repository.commit(planner.propose(parsed, hint=HINT, change=initial, dedup=CLEAR, catalog=repository.snapshot()),
                      parsed, source, approve=True)
    source_copy = replace(source, source_id="s-copy", display_name="copy.txt")
    processing = replace(parsed.processing, processing_id="p-copy", version_id="v-copy", source_id="s-copy")
    parsed_copy = replace(parsed, processing=processing, blocks=(replace(parsed.blocks[0], block_id="b-copy",
                          processing_id="p-copy", version_id="v-copy", locator=Locator(source_id="s-copy", page=1)),))
    unknown = ChangeRequest(kind="initial")
    pending = planner.propose(parsed_copy, hint=HINT, change=unknown, dedup=CLEAR, catalog=repository.snapshot())
    item = queue.enqueue_version(pending, parsed_copy, source_copy, hint=HINT, change=unknown, dedup=CLEAR)
    chosen = decision(item.review_id, "link_existing", payload={"version_id": "v1", "effective_from": "2026-01-01"})
    queue.resolve(item.review_id, chosen, expected_revision=0)
    assert queue.get(item.review_id).application.status == "duplicate"
    assert len(repository.snapshot().versions("doc")) == 1
    assert len(repository.snapshot().sources("doc")) == 2


def test_decision_id_cannot_be_reused_for_another_review(queue):
    first, second = queue.enqueue((issue("i1"), issue("i2")))
    queue.resolve(first.review_id, decision(first.review_id), expected_revision=0)
    with pytest.raises(ValueError, match="different data"):
        queue.resolve(second.review_id, decision(second.review_id), expected_revision=0)
    assert queue.get(second.review_id).item.status == "open"
