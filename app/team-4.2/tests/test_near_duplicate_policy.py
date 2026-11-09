from dataclasses import replace
import json

import pytest

from rag.ingest.near_duplicate import BASELINE_CONFIG, DEFAULT_CONFIG, NearDuplicateDetector
from scripts.build_near_duplicate_fixture import DATASET, FEE, PREAMBLE, FOOTER, build_dataset, document, metadata
from scripts.eval_near_duplicate import comparison_document, evaluate


def source(name, *, body=FEE, meta=None, template=True, confidence=None):
    value = document(body, template=template, meta=meta, confidence=confidence)
    value["document_id"] = name
    return comparison_document(value)


def test_independent_scope_reduces_duplicate_queue_without_changing_lexical_score():
    a = source("a", meta=metadata())
    b = source("b", body=FEE.replace("100.000", "120.000"), meta=metadata("09/2026/QĐ", "Cơ quan B", "B"))
    before = NearDuplicateDetector().compare(a, b, config=BASELINE_CONFIG)
    after = NearDuplicateDetector().compare(a, b)
    assert before.issue is not None and after.issue is None
    assert before.similarity == after.similarity
    assert after.classification == "independent_template" and "numeric" in after.difference_types
    assert a.blocks[0].text == PREAMBLE + "\n" + FEE + "\n" + FOOTER


@pytest.mark.parametrize("unconfirmed", [True, False])
def test_missing_or_unconfirmed_scope_does_not_silently_dismiss_numeric_difference(unconfirmed):
    meta = metadata("09/2026/QĐ", "Cơ quan B", "B", confirmed=not unconfirmed)
    if not unconfirmed:
        meta["scope"] = {}
    result = NearDuplicateDetector().compare(source("a", meta=metadata()),
        source("b", body=FEE.replace("100.000", "120.000"), meta=meta))
    assert result.issue is not None and result.review_priority == "high"


@pytest.mark.parametrize("value", ["*", "toàn quốc", "all", "A/B", "A và B"])
def test_overlapping_or_universal_scope_is_not_treated_as_independent(value):
    result = NearDuplicateDetector().compare(source("a", meta=metadata(province=value)),
        source("b", meta=metadata("09/2026/QĐ", "Cơ quan B", "B")))
    assert result.issue is not None


def test_time_difference_is_not_independent_scope():
    left = metadata()
    right = metadata("09/2026/QĐ", "Cơ quan B", "A")
    left["scope"], right["scope"] = {"period": "2026"}, {"period": "2027"}
    result = NearDuplicateDetector().compare(source("a", meta=left), source("b", meta=right))
    assert result.issue is not None


def test_same_identity_important_short_change_is_reviewed_below_old_threshold():
    a = source("a", body="Phí 100.000 đồng", template=False, meta=metadata())
    b = source("b", body="Phí 250.000 đồng", template=False, meta=metadata())
    assert NearDuplicateDetector().compare(a, b, config=BASELINE_CONFIG).issue is None
    result = NearDuplicateDetector().compare(a, b)
    assert result.similarity < .85 and result.issue is not None and result.review_priority == "high"


def test_shared_document_id_overrides_inconsistent_metadata_scope():
    a = source("a", meta=metadata())
    b = source("b", meta=metadata("09/2026/QĐ", "Cơ quan B", "B"), body=FEE.replace("100.000", "120.000"))
    b = replace(b, document_id=a.document_id)
    result = NearDuplicateDetector().compare(a, b)
    assert result.issue is not None and result.review_priority == "high"


def test_boilerplate_similarity_has_low_priority_but_remains_review_when_identity_unknown():
    a = source("a", body="Điều 3. Trồng cây xanh tạo bóng mát cho công viên đô thị.")
    b = source("b", body="Điều 3. Chăm sóc trẻ em tại trường học bằng bữa ăn dinh dưỡng.")
    result = NearDuplicateDetector().compare(a, b)
    assert result.similarity > .85 and result.body_similarity < .85
    assert result.issue is not None and result.issue.severity == "info"
    assert result.routing_category == "boilerplate_similarity" and result.review_priority == "low"


def test_effectivity_clause_after_footer_is_not_discarded():
    text = FEE + "\n" + FOOTER + "\nCó hiệu lực từ 01/07/2026."
    a = source("a", body=text, template=False, meta=metadata())
    b = source("b", body=text.replace("01/07/2026", "01/01/2027"), template=False, meta=metadata())
    result = NearDuplicateDetector().compare(a, b)
    assert result.review_priority == "high" and "numeric" in result.difference_types


def test_ocr_uncertainty_never_demotes_numeric_change_to_low_priority():
    a = source("a", confidence=.5, meta=metadata())
    b = source("b", confidence=.5, meta=metadata(), body=FEE.replace("100.000", "120.000"))
    assert NearDuplicateDetector().compare(a, b).review_priority == "high"
    c = source("c", confidence=.5, meta=metadata(), body=FEE.replace("khách hàng", "khach hang"))
    result = NearDuplicateDetector().compare(a, c)
    assert result.review_priority == "low" and result.routing_category == "possible_ocr_difference"
    assert result.issue is not None


def test_metadata_provider_adapter_routes_confirmed_independent_sources(tmp_path):
    from rag.ingest.dedup import DedupResult
    from rag.ingest.interfaces import MaskConfig
    from rag.ingest.near_duplicate import ComparisonMetadata
    from rag.models import ChangeRequest, DocumentRecord, IdentityHint, MaskResult, SafeBlock
    from rag.versioning.repository import VersionRepository
    from rag.versioning.resolver import FullVersionResolver
    from scripts.demo_versioning import fake_ocr_bundle
    from dataclasses import fields
    from datetime import date, datetime, timezone
    from rag.models import Block

    repository = VersionRepository(tmp_path / "catalog.sqlite")
    repository.add_document(DocumentRecord(document_id="a", title="Policy", document_type="policy", language="vi",
                                            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    original, parsed = fake_ocr_bundle("v1", FEE, tmp_path, "v1")
    clear = DedupResult(matches=(), action="continue", existing_version_id=None, findings=())
    plan = FullVersionResolver().propose(parsed, hint=IdentityHint(document_id="a"), dedup=clear,
        change=ChangeRequest(kind="initial", effective_from=date(2026, 1, 1)), catalog=repository.snapshot())
    repository.commit(plan, parsed, original, approve=True)
    class FixtureMasker:
        def mask(self, blocks, *, config):
            return MaskResult(blocks=tuple(SafeBlock(**{f.name: getattr(b, f.name) for f in fields(Block)},
                                    masking_config_id="fixture") for b in blocks), findings=(), masking_config_id="fixture")
    provider = {"a": ComparisonMetadata(external_key="01/2026", issuer="Authority A", scope=(("province", "A"),), confirmed=True),
                "b": ComparisonMetadata(external_key="09/2026", issuer="Authority B", scope=(("province", "B"),), confirmed=True)}
    source_b, parsed_b = fake_ocr_bundle("v2", FEE.replace("100.000", "120.000"), tmp_path, "v2")
    before = repository.snapshot()
    detector = NearDuplicateDetector(masker=FixtureMasker(), mask_config=MaskConfig(detector_name="fixture", detector_version="1",
                                      pii_types=(), placeholder_policy_id="fixture"), metadata_provider=provider.__getitem__)
    result = detector.detect(source_b, parsed_b, hint=IdentityHint(document_id="b"), catalog=before)
    assert result.action == "continue" and not result.findings and repository.snapshot() == before


def test_evaluation_reports_fp_and_fn_per_split_without_claiming_perfection():
    report = evaluate(DATASET)
    assert report["synthetic"] is True
    for split in ("dev", "test"):
        old = report["policies"]["baseline"]["metrics"][split]
        new = report["policies"]["improved"]["metrics"][split]
        assert old["pairs"] == new["pairs"] == 12
        assert new["fp"] < old["fp"] and new["fn"] <= old["fn"]
        assert new["false_positive_ids"]  # preserve/report uncertain cases
    assert report["policies"]["baseline"]["config"]["threshold"] == report["policies"]["improved"]["config"]["threshold"]


def test_evaluation_rejects_source_identity_leakage(tmp_path):
    data = build_dataset()
    data["pairs"][-1]["left"]["document_id"] = data["pairs"][0]["left"]["document_id"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="leaks"):
        evaluate(path)
