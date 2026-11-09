"""Unsupported time conditions cannot be bypassed by supplying a single date."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import unicodedata

import pytest

from scripts.demo_versioning import fake_ocr_bundle
from rag.ingest.dedup import DedupResult
from rag.models import ChangeRequest, DocumentRecord, IdentityHint, QueryScope, ReviewDecision, TableData, UnitAssignment
from rag.quality.review_queue import ReviewBlockedError, SQLiteReviewService
from rag.versioning.articles import ArticleVersionResolver
from rag.versioning.effectivity_guard import unsupported_effectivity_reasons
from rag.versioning.repository import VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver

DAY = date(2026, 7, 1)
OLD = "Điều 5. Phí dịch vụ\n1. Phí cá nhân 100.000 đồng.\n2. Phí doanh nghiệp 200.000 đồng.\n3. Nộp phí trước ngày 10."
NEW = OLD.replace("200.000", "250.000")
CLEAR = DedupResult(matches=(), action="continue", existing_version_id=None, findings=())
HINT = IdentityHint(document_id="policy")


def assigned(parsed):
    return UnitAssignment(unit_key="article:5", title="Điều 5. Phí dịch vụ", complete=True,
                          block_ids=tuple(b.block_id for b in parsed.blocks))


def changed(repository, parsed):
    old = repository.snapshot().revision_records[0]
    return ChangeRequest(kind="partial", effective_from=DAY, supersedes_version_ids=("v1",),
                         unit_mapping=((old.unit_revision_id, "article:5"),), unit_assignments=(assigned(parsed),))


@pytest.fixture
def repository(tmp_path):
    repo = VersionRepository(tmp_path / "catalog.sqlite")
    repo.add_document(DocumentRecord(document_id="policy", title="Policy", document_type="policy", language="vi",
                                      created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    source, parsed = fake_ocr_bundle("v1", OLD, tmp_path, "v1")
    change = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1), unit_assignments=(assigned(parsed),))
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=repo.snapshot())
    repo.commit(plan, parsed, source, approve=True)
    return repo


CASES = [
    ("Điều 1, 2 có hiệu lực từ 01/07/2026. Điều 3 có hiệu lực từ 01/01/2027.", "multiple_dates"),
    ("Văn bản có hiệu lực từ 01/07/2026; riêng Điều 3 từ 01/01/2027.", "unit_exception"),
    ("Văn bản có hiệu lực sau 45 ngày kể từ ngày ký.", "relative_date"),
    ("Văn bản có hiệu lực sau bốn mươi lăm ngày kể từ ngày ký.", "relative_date"),
    ("Văn bản có hiệu lực kể từ ngày ký.", "relative_date"),
    ("Quy định chuyển tiếp: Hồ sơ nộp trước 01/07/2026 tiếp tục áp dụng quy định cũ.", "transition"),
    ("Hợp đồng ký trước 01/07/2026 vẫn áp dụng văn bản cũ.", "transition"),
    ("Điều 5 bị đình chỉ thi hành từ 01/07/2026 đến hết 30/09/2026.", "suspension"),
    ("Điều 5 bị đình chỉ từ 01/07/2026 đến hết 30/09/2026.", "suspension"),
    ("Tạm ngưng hiệu lực của Điều 5.", "suspension"),
    ("Văn bản có hiệu lực khi nghị định hướng dẫn được ban hành.", "conditional"),
    ("Quy định áp dụng kể từ khi hoàn tất thủ tục đăng ký.", "conditional"),
    ("Quy định có hiệu lực từ 01/01/2027.", "date_mismatch"),
    ("Quy định có hiệu lực từ ngày 31/02/2026.", "invalid_date"),
    ("Quy định có hiệu lực từ ngày 0101/01/2026.", "invalid_date"),
]


@pytest.mark.parametrize(("rule", "code"), CASES)
def test_supported_date_field_does_not_override_unsupported_source(repository, tmp_path, rule, code):
    before = repository.snapshot()
    source, parsed = fake_ocr_bundle("v2", NEW + "\n" + rule, tmp_path, "v2")
    change = changed(repository, parsed)
    for resolver in (FullVersionResolver(), ArticleVersionResolver()):
        plan = resolver.propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=before)
        assert plan.action == "review"
        assert "effectivity." + code in " ".join(plan.review_reasons)
        assert plan.applicability_changes == ()
        with pytest.raises(ValueError):
            repository.commit(plan, parsed, source, approve=True)
    assert repository.snapshot() == before


@pytest.mark.parametrize("rule", [
    "Văn bản có hiệu lực từ 01/07/2026.",
    "Văn bản có hiệu lực từ ngày 01 tháng 07 năm 2026.",
    "Văn bản có hiệu lực từ 2026-07-01.",
    "Điều 1 có hiệu lực từ 01/07/2026; Điều 2 có hiệu lực từ 01/07/2026.",
    "Ký ngày 01/01/2026. Văn bản có hiệu lực từ 01/07/2026.",
    "Hồ sơ nộp ngày 01/03/2026. Thanh toán chậm nhất ngày 10/03/2026.",
])
def test_supported_explicit_date_and_unrelated_dates_are_not_blocked(tmp_path, rule):
    _, parsed = fake_ocr_bundle("v2", NEW + "\n" + rule, tmp_path, "v2")
    assert unsupported_effectivity_reasons(parsed, effective_from=DAY) == ()


def test_normal_single_date_update_still_commits(repository, tmp_path):
    source, parsed = fake_ocr_bundle("v2", NEW + "\nVăn bản có hiệu lực từ 01/07/2026.", tmp_path, "v2")
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=changed(repository, parsed), dedup=CLEAR,
                                         catalog=repository.snapshot())
    repository.commit(plan, parsed, source, approve=True)
    selection = UnitScopeResolver().resolve_units(QueryScope(mode="as_of", as_of=DAY), catalog=repository.snapshot())
    assert selection.units[0].revision.version_id == "v2"


def test_metadata_correction_in_review_cannot_bypass_relative_date(repository, tmp_path):
    now = datetime.now(timezone.utc)
    queue = SQLiteReviewService(repository, now=lambda: now)
    before = repository.snapshot()
    source, parsed = fake_ocr_bundle("v2", NEW + "\nCó hiệu lực sau 45 ngày kể từ ngày ký.", tmp_path, "v2")
    change = changed(repository, parsed)
    plan = FullVersionResolver().propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=before)
    item = queue.enqueue_version(plan, parsed, source, hint=HINT, change=change, dedup=CLEAR)
    chosen = ReviewDecision(decision_id="confirm", review_id=item.review_id, action="confirm_replacement", reviewer="fixture",
                            reason="Attempt to fill a single date", created_at=now + timedelta(minutes=1),
                            payload={"effective_from": DAY.isoformat(), "supersedes_version_ids": ["v1"]})
    with pytest.raises(ReviewBlockedError, match="relative_date"):
        queue.resolve(item.review_id, chosen, expected_revision=0)
    assert repository.snapshot() == before
    assert queue.get(item.review_id).item.status == "open"
    assert queue.get(item.review_id).decision is None


def test_repository_rechecks_temporal_source_even_if_create_plan_is_forged(repository, tmp_path):
    source, good = fake_ocr_bundle("v2", NEW, tmp_path, "v2")
    plan = FullVersionResolver().propose(good, hint=HINT, change=changed(repository, good), dedup=CLEAR, catalog=repository.snapshot())
    before = repository.snapshot()
    bad = replace(good, blocks=(replace(good.blocks[0], text=NEW + "\nĐiều 5 bị đình chỉ thi hành."),))
    with pytest.raises(ValueError, match="effectivity.suspension"):
        repository.commit(plan, bad, source, approve=True)
    assert repository.snapshot() == before


def test_whole_document_and_initial_paths_are_guarded(repository, tmp_path):
    _, parsed = fake_ocr_bundle("v2", "Có hiệu lực sau 45 ngày kể từ ngày ký.", tmp_path, "v2")
    for kind in ("initial", "full"):
        change = ChangeRequest(kind=kind, effective_from=DAY, supersedes_version_ids=("v1",) if kind == "full" else ())
        plan = FullVersionResolver().propose(parsed, hint=HINT, change=change, dedup=CLEAR, catalog=repository.snapshot())
        assert plan.action == "review" and "relative_date" in " ".join(plan.review_reasons)


def test_unicode_table_and_cross_block_rules_are_detected(tmp_path):
    _, parsed = fake_ocr_bundle("v2", "Có hiệu lực", tmp_path, "v2")
    other = replace(parsed.blocks[0], block_id="b-second", order=1,
                    text=unicodedata.normalize("NFD", "sau 45 ngày kể từ ngày ký."))
    assert any("relative_date" in reason for reason in unsupported_effectivity_reasons(
        replace(parsed, blocks=(parsed.blocks[0], other)), effective_from=DAY))
    table = TableData(headers=(("Hiệu lực",),), rows=(("Có hiệu lực sau 45 ngày kể từ ngày ký.",),), column_units=(None,))
    table_parsed = replace(parsed, blocks=(replace(parsed.blocks[0], kind="table", table=table, text=""),))
    assert any("relative_date" in reason for reason in unsupported_effectivity_reasons(table_parsed, effective_from=DAY))


def test_guard_messages_do_not_copy_raw_source(tmp_path):
    _, parsed = fake_ocr_bundle("v2", "Có hiệu lực sau 45 ngày kể từ ngày ký. secret@example.com", tmp_path, "v2")
    assert "secret@example.com" not in " ".join(unsupported_effectivity_reasons(parsed, effective_from=DAY))
