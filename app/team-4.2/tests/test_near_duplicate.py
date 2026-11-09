from dataclasses import fields, replace
from datetime import date, datetime, timedelta, timezone
import re
import unicodedata

import pytest

from rag.ingest.near_duplicate import ComparisonDocument, DEFAULT_CONFIG, NearDuplicateDetector
from rag.ingest.dedup import DedupResult
from rag.ingest.interfaces import MaskConfig
from scripts.demo_versioning import fake_ocr_bundle
from rag.models.common import canonical_json
from rag.models.content import Block, Locator, SafeBlock, TableData
from rag.models.document import ChangeRequest, DocumentRecord, IdentityHint
from rag.models.quality import ReviewDecision
from rag.models.results import MaskResult
from rag.quality.review_queue import SQLiteReviewService
from rag.versioning.repository import VersionRepository
from rag.versioning.resolver import FullVersionResolver

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
TEXT = ("Điều 3. Mức phí dịch vụ áp dụng cho khách hàng cá nhân là 100.000 đồng mỗi tháng. "
        "Mức phí đã bao gồm thuế và được thanh toán vào ngày đầu tiên của tháng tiếp theo.")


def document(name, text=TEXT, *, coverage="complete", table=None):
    block = SafeBlock(block_id=f"b-{name}", processing_id=f"p-{name}", version_id=f"v-{name}",
                       order=0, kind="table" if table else "paragraph", text=text, origin="native",
                       locator=Locator(source_id=f"s-{name}", page=3), table=table, masking_config_id="mask-v1")
    return ComparisonDocument(document_id=f"d-{name}", version_id=f"v-{name}", processing_id=f"p-{name}",
                              blocks=(block,), masking_config_id="mask-v1", coverage=coverage)


def detector():
    return NearDuplicateDetector(now=lambda: NOW)


def test_number_change_preserved_in_diff_with_both_source_locations():
    result = detector().compare(document("a"), document("b", TEXT.replace("100.000", "120.000")))
    assert result.classification == "near_duplicate" and result.similarity >= .85
    changes = result.issue.safe_evidence["changes"]
    assert any(c["left"] == "100.000" and c["right"] == "120.000" for c in changes)
    assert changes[0]["left_targets"][0]["locator"]["page"] == 3
    assert {t.source_id for t in result.issue.targets} == {"s-a", "s-b"}


def test_added_negation_is_reviewed_not_treated_as_identical():
    result = detector().compare(document("a"), document("b", TEXT.replace("đã bao gồm", "không bao gồm")))
    assert result.classification == "near_duplicate"
    assert "không" in canonical_json(result.issue.safe_evidence["changes"])


def test_unicode_whitespace_case_normalization_only_yields_candidate():
    altered = unicodedata.normalize("NFD", TEXT.upper()).replace(" ", "  \n")
    result = detector().compare(document("a"), document("b", altered))
    assert result.similarity == 1 and result.classification == "same_content_candidate"
    assert result.issue.code == "dedup.same_content_candidate"


def test_unrelated_and_empty_content_have_no_duplicate_finding():
    result = detector().compare(document("a"), document("b", "Cây xanh hấp thụ ánh sáng để quang hợp."))
    assert result.classification == "different" and result.issue is None
    for text in ("", " \n "):
        empty = detector().compare(document("a"), document("b", text))
        assert empty.classification == "not_comparable" and empty.similarity is None


def test_threshold_is_inclusive_and_part_of_issue_identity():
    a, b = document("a"), document("b", TEXT.replace("100.000", "120.000"))
    score = detector().compare(a, b).similarity
    assert detector().compare(a, b, config=replace(DEFAULT_CONFIG, threshold=score)).issue is not None
    assert detector().compare(a, b, config=replace(DEFAULT_CONFIG, threshold=score + .00001)).issue is None
    first = detector().compare(a, b).issue
    second = detector().compare(a, b, config=replace(DEFAULT_CONFIG, threshold=.8)).issue
    assert first.issue_id != second.issue_id


def test_pair_order_is_stable_and_self_comparison_skipped():
    a, b = document("a"), document("b", TEXT.replace("100.000", "120.000"))
    assert detector().compare(a, b) == detector().compare(b, a)
    assert detector().compare(a, a).classification == "self"
    changed = replace(a, blocks=(replace(a.blocks[0], text="different"),))
    with pytest.raises(ValueError, match="Processing ID"):
        detector().compare(a, changed)
    assert len(detector().scan((a, b, a))) == 1


def test_tables_are_compared_even_when_text_projection_is_empty():
    table = TableData(headers=(("Tên dịch vụ", "Mức phí"),), rows=(("Hỗ trợ khách hàng", "100.000"),),
                      column_units=(None, "đồng"), notes=("Đã gồm thuế",), period="2026")
    other = replace(table, rows=(("Hỗ trợ khách hàng", "120.000"),))
    result = detector().compare(document("a", "", table=table), document("b", "", table=other))
    assert result.classification == "near_duplicate"
    assert "120.000" in canonical_json(result.issue.safe_evidence["changes"])


def test_table_units_are_not_discarded_or_auto_converted():
    table = TableData(headers=(("Mức phí",),), rows=(("100.000",),), column_units=("đồng",))
    result = detector().compare(document("a", "", table=table), document("b", "", table=replace(table, column_units=("triệu đồng",))))
    assert result.classification == "near_duplicate"
    assert "triệu" in canonical_json(result.issue.safe_evidence["changes"])


def test_raw_blocks_and_inconsistent_masking_policies_rejected():
    safe = document("a")
    raw = Block(**{f.name: getattr(safe.blocks[0], f.name) for f in fields(Block)})
    with pytest.raises(ValueError, match="SafeBlocks"):
        replace(safe, blocks=(raw,))
    other = document("b")
    other = replace(other, masking_config_id="mask-v2", blocks=(replace(other.blocks[0], masking_config_id="mask-v2"),))
    with pytest.raises(ValueError, match="same masking"):
        detector().compare(safe, other)


def test_visual_and_incomplete_extraction_limitations_are_explicit():
    a = document("a", coverage="incomplete")
    a = replace(a, blocks=(replace(a.blocks[0], image_artifact="images/page3.png"),))
    result = detector().compare(a, document("b"))
    assert "extraction_coverage_not_complete" in result.issue.safe_evidence["warnings"]
    assert "visual_or_flow_structure_not_fully_compared" in result.issue.safe_evidence["warnings"]


def test_free_text_locator_metadata_does_not_leak_to_evidence():
    a = document("a")
    a = replace(a, blocks=(replace(a.blocks[0], locator=replace(a.blocks[0].locator,
                             heading_path=("secret@example.com",), sheet="secret@example.com", table_id="secret@example.com")),))
    result = detector().compare(a, document("b", TEXT.replace("100.000", "120.000")))
    assert "secret@example.com" not in canonical_json(result.issue)


class FakeMasker:
    """Fixture-only masker, not a production PII implementation."""
    def __init__(self):
        self.calls = 0

    def mask(self, blocks, *, config):
        self.calls += 1
        safe = []
        for block in blocks:
            values = {f.name: getattr(block, f.name) for f in fields(Block)}
            values["text"] = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]+", "[EMAIL]", block.text)
            safe.append(SafeBlock(**values, masking_config_id="mask-v1"))
        return MaskResult(blocks=tuple(safe), findings=(), masking_config_id="mask-v1")


def setup_catalog(tmp_path):
    repository = VersionRepository(tmp_path / "catalog.sqlite")
    repository.add_document(DocumentRecord(document_id="doc", title="Policy", document_type="policy", language="vi", created_at=NOW))
    source, parsed = fake_ocr_bundle("v1", TEXT + " Liên hệ old@example.com.", tmp_path, "v1")
    clear = DedupResult(matches=(), action="continue", existing_version_id=None, findings=())
    plan = FullVersionResolver().propose(parsed, hint=IdentityHint(document_id="doc"), dedup=clear,
                                         change=ChangeRequest(kind="initial", effective_from=date(2026, 1, 1)), catalog=repository.snapshot())
    repository.commit(plan, parsed, source, approve=True)
    return repository


def configured_detector(masker):
    return NearDuplicateDetector(masker=masker,
        mask_config=MaskConfig(detector_name="fake", detector_version="1", pii_types=("email",), placeholder_policy_id="v1"),
        now=lambda: NOW)


def test_catalog_adapter_masks_both_sources_and_enqueues_without_mutating_versions(tmp_path):
    repository = setup_catalog(tmp_path)
    before = repository.snapshot()
    source, parsed = fake_ocr_bundle("v2", TEXT.replace("100.000", "120.000") + " Liên hệ new@example.com.", tmp_path, "v2")
    masker = FakeMasker()
    result = configured_detector(masker).detect(source, parsed, hint=IdentityHint(document_id="doc"), catalog=before)
    assert masker.calls == 2
    assert result.action == "review" and result.existing_version_id is None
    assert result.matches[0].kind == "near_duplicate"
    assert "old@example.com" not in canonical_json(result)
    assert "new@example.com" not in canonical_json(result)
    queue = SQLiteReviewService(repository, now=lambda: NOW)
    item = queue.enqueue(result.findings)[0]
    again = queue.enqueue(result.findings)[0]
    assert item.review_id == again.review_id
    assert repository.snapshot() == before
    chosen = ReviewDecision(decision_id="keep-both", review_id=item.review_id, action="keep_both", reviewer="Khánh",
                            reason="Need separate source verification", payload={}, created_at=NOW + timedelta(minutes=1))
    queue.resolve(item.review_id, chosen, expected_revision=0)
    assert repository.snapshot() == before  # decision never deletes or silently merges sources


def test_mask_collision_never_becomes_automatic_exact_dedup(tmp_path):
    repository = setup_catalog(tmp_path)
    source, parsed = fake_ocr_bundle("v2", TEXT + " Liên hệ different@example.com.", tmp_path, "v2")
    result = configured_detector(FakeMasker()).detect(source, parsed, hint=IdentityHint(document_id="doc"), catalog=repository.snapshot())
    assert result.matches[0].kind == "same_content_candidate"
    assert result.action == "review" and result.existing_version_id is None


def test_detect_requires_masker_and_rejects_changed_provenance(tmp_path):
    repository = setup_catalog(tmp_path)
    source, parsed = fake_ocr_bundle("v2", TEXT, tmp_path, "v2")
    with pytest.raises(ValueError, match="PIIMasker"):
        detector().detect(source, parsed, hint=IdentityHint(), catalog=repository.snapshot())
    mask = FakeMasker().mask(parsed.blocks, config=None)
    bad = replace(mask, blocks=(replace(mask.blocks[0], locator=replace(mask.blocks[0].locator, page=99)),))
    with pytest.raises(ValueError, match="provenance"):
        ComparisonDocument.from_parse(parsed, bad, document_id="doc")


def test_repeated_scan_with_new_timestamp_has_same_review_identity(tmp_path):
    first = detector().compare(document("a"), document("b", TEXT.replace("100.000", "120.000")))
    second = NearDuplicateDetector(now=lambda: NOW + timedelta(hours=1)).compare(document("a"), document("b", TEXT.replace("100.000", "120.000")))
    assert first.issue.issue_id == second.issue.issue_id
    queue = SQLiteReviewService(VersionRepository(tmp_path / "catalog.sqlite"), now=lambda: NOW)
    queue.enqueue((first.issue,))
    queue.enqueue((second.issue,))
    assert len(queue.list_items()) == 1


def test_unsupported_algorithm_not_silently_accepted():
    with pytest.raises(ValueError, match="Unsupported"):
        detector().compare(document("a"), document("b"), config=replace(DEFAULT_CONFIG, algorithm="something-else"))


def test_evidence_excerpt_limits_do_not_truncate_similarity_input():
    common = "Nội dung chung áp dụng cho tất cả khách hàng. " * 100
    addition = "Điều kiện bổ sung phải kiểm tra rõ ràng. " * 10
    result = detector().compare(document("a", common), document("b", common + addition))
    assert result.issue is not None
    assert result.issue.safe_evidence["right_token_count"] > result.issue.safe_evidence["left_token_count"]
    assert any(change["excerpt_truncated"] for change in result.issue.safe_evidence["changes"])


def test_reordering_source_block_container_preserves_finding_identity():
    a = document("a")
    block2 = replace(a.blocks[0], block_id="b-a2", order=1, text="Thông tin bổ sung.")
    a = replace(a, blocks=(a.blocks[0], block2))
    reordered = replace(a, blocks=tuple(reversed(a.blocks)))
    assert detector().compare(a, document("b")) == detector().compare(reordered, document("b"))
