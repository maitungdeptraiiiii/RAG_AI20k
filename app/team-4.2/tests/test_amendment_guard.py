"""An amendment fragment must not retire a complete article's other clauses."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib

import pytest

from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupResult
from rag.models import (
    Block, ChangeRequest, DocumentRecord, IdentityHint, Locator, ParseResult,
    ProcessingRecord, QueryScope, ReviewDecision, SourceRecord, UnitAssignment,
)
from rag.quality.review_queue import ReviewBlockedError, SQLiteReviewService
from rag.versioning.amendment_guard import amendment_fragment_reasons
from rag.versioning.articles import ArticleVersionResolver
from rag.versioning.repository import VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
DAY = date(2026, 7, 1)
OLD = ("Điều 5. Phí dịch vụ\n"
       "1. Khách hàng cá nhân trả 100.000 đồng/tháng.\n"
       "2. Khách hàng doanh nghiệp trả 200.000 đồng/tháng.\n"
       "3. Thanh toán trước ngày 10 hằng tháng.")
NEW = OLD.replace("200.000", "250.000")
CLEAR = DedupResult(matches=(), action="continue", existing_version_id=None, findings=())
HINT = IdentityHint(document_id="policy")


def bundle(text, version="v2"):
    source = SourceRecord(source_id=f"s-{version}", source_uri="fixture://policy", display_name="policy.txt",
                          media_type="text/plain", raw_artifact=f"raw/{version}.txt", collected_at=NOW,
                          raw_checksum=hashlib.sha256(text.encode()).hexdigest())
    processing = ProcessingRecord(processing_id=f"p-{version}", version_id=version, source_id=source.source_id,
                                  parser_name="fixture", parser_version="1", normalization_config_id="nfc-v1",
                                  content_checksum=canonical_checksum(text), coverage="complete", created_at=NOW)
    block = Block(block_id=f"b-{version}", processing_id=processing.processing_id, version_id=version,
                  order=0, kind="paragraph", text=text, origin="native", locator=Locator(source_id=source.source_id, page=1))
    return source, ParseResult(processing=processing, blocks=(block,))


def assignment(parsed):
    return UnitAssignment(unit_key="article:5", title="Điều 5. Phí dịch vụ",
                          block_ids=tuple(b.block_id for b in parsed.blocks), complete=True)


@pytest.fixture
def repository(tmp_path):
    repo = VersionRepository(tmp_path / "catalog.sqlite")
    repo.add_document(DocumentRecord(document_id="policy", title="Policy", document_type="policy", language="vi", created_at=NOW))
    source, parsed = bundle(OLD, "v1")
    change = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1), unit_assignments=(assignment(parsed),))
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=repo.snapshot())
    repo.commit(plan, parsed, source, approve=True)
    return repo


def request(repo, parsed):
    old = repo.snapshot().revision_records[0]
    return ChangeRequest(kind="partial", effective_from=DAY, supersedes_version_ids=("v1",),
                         unit_mapping=((old.unit_revision_id, "article:5"),), unit_assignments=(assignment(parsed),))


@pytest.mark.parametrize("text", [
    "Sửa đổi khoản 2 Điều 5 như sau:\n“2. Doanh nghiệp trả 250.000 đồng.”",
    "Sửa đổi, bổ sung điểm a khoản 2 Điều 5 như sau: a) Mức phí mới.",
    "Bổ sung khoản 4 vào Điều 7: 4. Quy định bổ sung.",
    "Thay cụm từ “200.000 đồng” bằng “250.000 đồng” tại khoản 2 Điều 5.",
    "Khoản 2 Điều 5 được sửa đổi như sau: 2. Mức phí mới.",
    "Điều 5. Phí dịch vụ\nKhoản 2 Điều 5 sửa đổi như sau: 2. Phí mới.",
    "Bãi bỏ điểm a khoản 2 Điều 5.",
    "SỬA ĐỔI\n KHOẢN\n2 ĐIỀU 5 như sau: Nội dung mới.",
    "2. Doanh nghiệp trả 250.000 đồng/tháng.",
    "a) Doanh nghiệp trả mức phí mới.",
])
def test_fragment_is_reviewed_even_when_marked_complete(repository, text):
    before = repository.snapshot()
    source, parsed = bundle(text)
    change = request(repository, parsed)
    for planner in (FullVersionResolver(), ArticleVersionResolver()):
        plan = planner.propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=before)
        assert plan.action == "review"
        assert "amendment.fragment" in " ".join(plan.review_reasons)
        assert plan.applicability_changes == ()
        with pytest.raises(ValueError):
            repository.commit(plan, parsed, source, approve=True)
    assert repository.snapshot() == before


def test_disguised_fragment_with_article_heading_cannot_drop_other_clauses(repository):
    source, parsed = bundle("Điều 5. Phí dịch vụ\n2. Doanh nghiệp trả 250.000 đồng/tháng.")
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=request(repository, parsed),
                                         dedup=CLEAR, catalog=repository.snapshot())
    assert plan.action == "review" and "missing_clauses" in " ".join(plan.review_reasons)
    selection = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=DAY), catalog=repository.snapshot())
    assert selection.units[0].blocks[0].text == OLD
    assert selection.units[0].applicability.effective_to is None


def test_complete_revised_article_preserves_all_clauses(repository):
    source, parsed = bundle(NEW)
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=request(repository, parsed),
                                         dedup=CLEAR, catalog=repository.snapshot())
    assert plan.action == "create"
    repository.commit(plan, parsed, source, approve=True)
    selection = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=DAY), catalog=repository.snapshot())
    assert selection.units[0].blocks[0].text == NEW
    assert "100.000" in selection.units[0].blocks[0].text and "ngày 10" in selection.units[0].blocks[0].text


def test_subunit_cross_reference_without_amendment_is_allowed():
    _, parsed = bundle("Điều 5. Phí dịch vụ\nMức phí áp dụng theo khoản 2 Điều 7 của quy định này.")
    assert amendment_fragment_reasons(parsed, assignments=(assignment(parsed),)) == ()


def test_repository_rechecks_fragment_even_with_forged_create_plan(repository):
    _, good = bundle(NEW)
    plan = FullVersionResolver().propose(good, hint=HINT, change=request(repository, good),
                                         dedup=CLEAR, catalog=repository.snapshot())
    before = repository.snapshot()
    source, bad = bundle("Điều 5. Phí dịch vụ\nSửa đổi khoản 2 Điều 5 như sau: 2. Phí mới.")
    with pytest.raises(ValueError, match="amendment.fragment"):
        repository.commit(plan, bad, source, approve=True)
    assert repository.snapshot() == before


def test_legacy_full_replacement_path_also_rejects_fragment(repository):
    _, parsed = bundle("Sửa đổi khoản 2 Điều 5 như sau: 2. Mức phí mới.")
    plan = FullVersionResolver().propose(parsed, hint=HINT, dedup=CLEAR, catalog=repository.snapshot(),
        change=ChangeRequest(kind="full", effective_from=DAY, supersedes_version_ids=("v1",)))
    assert plan.action == "review" and "amendment.fragment" in " ".join(plan.review_reasons)


def test_review_cannot_bypass_guard_by_setting_complete_true(repository):
    queue = SQLiteReviewService(repository, now=lambda: NOW)
    before = repository.snapshot()
    source, parsed = bundle("Sửa đổi khoản 2 Điều 5 như sau: 2. Mức phí mới.")
    change = request(repository, parsed)
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=before)
    item = queue.enqueue_version(plan, parsed, source, hint=HINT, change=change, dedup=CLEAR)
    decision = ReviewDecision(decision_id="confirm", review_id=item.review_id, action="confirm_replacement", reviewer="fixture",
                              reason="Attempt to mark fragment complete", created_at=NOW + timedelta(minutes=1),
                              payload={"effective_from": DAY.isoformat(), "supersedes_version_ids": ["v1"],
                                       "unit_assignments": [{"unit_key": "article:5", "title": "Điều 5",
                                                              "block_ids": ["b-v2"], "complete": True}]})
    with pytest.raises(ReviewBlockedError, match="amendment.fragment"):
        queue.resolve(item.review_id, decision, expected_revision=0)
    assert queue.get(item.review_id).item.status == "open"
    assert queue.get(item.review_id).decision is None
    assert repository.snapshot() == before


def test_directives_split_across_blocks_are_detected():
    _, parsed = bundle("Sửa đổi")
    first = parsed.blocks[0]
    second = replace(first, block_id="b-v2:1", order=1, text="khoản 2 Điều 5 như sau: Nội dung mới.")
    parsed = replace(parsed, blocks=(first, second))
    assert amendment_fragment_reasons(parsed)


def test_missing_point_in_unchanged_clause_is_not_hidden_by_other_clause_labels():
    old = ("Điều 5. Phí\n1. Cá nhân:\na) Trả phí cơ bản.\nb) Trả phụ phí.\n"
           "2. Doanh nghiệp:\na) Trả phí doanh nghiệp.\nb) Trả phụ phí doanh nghiệp.")
    text = old.replace("b) Trả phụ phí doanh nghiệp.\n", "").replace("b) Trả phụ phí doanh nghiệp.", "")
    _, parsed = bundle(text)
    _, previous = bundle(old, "v1")
    reasons = amendment_fragment_reasons(parsed, assignments=(assignment(parsed),), previous_blocks={"article:5": previous.blocks})
    assert any("missing_points" in reason for reason in reasons)


def test_directive_inside_structured_table_is_not_missed():
    from rag.models import TableData
    _, parsed = bundle("Điều 5. Phí")
    table = TableData(headers=(("Thay đổi",),), rows=(("Sửa đổi khoản 2 Điều 5 như sau",),), column_units=(None,))
    parsed = replace(parsed, blocks=(replace(parsed.blocks[0], kind="table", table=table),))
    assert amendment_fragment_reasons(parsed)
