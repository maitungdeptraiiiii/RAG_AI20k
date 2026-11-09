from dataclasses import replace
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
import json

import pytest

from rag.ingest.interfaces import OCRPageInput, OCRRegion, OCRResult, ChunkerV2, DocumentParserV2
from rag.models.common import canonical_json
from rag.models.content import Block, ChunkV2, Locator, SafeBlock, TableData, TargetRef
from rag.models.document import ApplicabilityRecord, ChangeRequest, ProcessingRecord, QueryScope, SourceRecord
from rag.models.results import MaskResult, ParseResult


NOW = datetime(2026, 11, 6, 12, tzinfo=timezone(timedelta(hours=7)))


def block(**overrides):
    return replace(Block(block_id="b1", processing_id="p1", version_id="v1", order=0,
                         kind="paragraph", text="Mức phí 120.000 đồng", origin="ocr",
                         locator=Locator(source_id="s1", page=2), ocr_confidence=.95), **overrides)


def test_serialization_keeps_decimal_exact_and_timestamps_in_utc():
    value = json.loads(canonical_json({"at": NOW, "day": date(2026, 7, 1), "number": Decimal("123456789.123456789")}))
    assert value == {"at": "2026-11-06T05:00:00Z", "day": "2026-07-01", "number": "123456789.123456789"}


def test_source_has_schema_tag_and_rejects_naive_time():
    source = SourceRecord(source_id="s1", source_uri="input.pdf", display_name="input.pdf", media_type="application/pdf",
                          raw_artifact="raw/input.pdf", raw_checksum="a" * 64, collected_at=NOW)
    assert source.to_dict()["schema_version"] == "w02.v1"
    with pytest.raises(ValueError):
        replace(source, collected_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        replace(source, raw_artifact="../input.pdf")
    with pytest.raises(ValueError):
        replace(source, raw_artifact="C:\\input.pdf")


@pytest.mark.parametrize("kwargs", [
    {"page": 0}, {"bbox": (0.9, .1, .2, .4)}, {"row_start": 1},
    {"column_start": 2, "column_end": 1},
])
def test_locator_rejects_invalid_coordinates(kwargs):
    with pytest.raises(ValueError):
        Locator(source_id="s1", **kwargs)


def test_block_requires_structure_and_confidence():
    assert block().ocr_confidence == .95
    assert block(ocr_confidence=None).ocr_confidence is None
    with pytest.raises(ValueError):
        block(ocr_confidence=1.1)
    with pytest.raises(ValueError):
        block(kind="table")
    with pytest.raises(ValueError):
        block(kind="image")
    with pytest.raises(ValueError):
        TableData(headers=(("a", "b"),), rows=(("1",),), column_units=(None, None))


def test_parse_result_cannot_mix_sources_or_versions():
    processing = ProcessingRecord(processing_id="p1", version_id="v1", source_id="s1",
                                  parser_name="pdf", parser_version="1", normalization_config_id="n1",
                                  content_checksum="a" * 64, created_at=NOW)
    ParseResult(processing=processing, blocks=(block(),))
    with pytest.raises(ValueError):
        ParseResult(processing=processing, blocks=(block(version_id="v2"),))
    with pytest.raises(ValueError):
        ParseResult(processing=processing, blocks=(block(), block()))


def test_safe_blocks_must_have_matching_mask_policy():
    safe = SafeBlock(block_id="b1", processing_id="p1", version_id="v1", order=0,
                     kind="paragraph", text="Email [EMAIL]", origin="native", locator=Locator(source_id="s1"),
                     masking_config_id="mask-1")
    MaskResult(blocks=(safe,), findings=(), masking_config_id="mask-1")
    with pytest.raises(ValueError):
        MaskResult(blocks=(safe,), findings=(), masking_config_id="mask-2")
    with pytest.raises(ValueError):
        MaskResult(blocks=(block(),), findings=(), masking_config_id="mask-1")


def test_effective_interval_is_half_open_and_pending_is_not_current():
    record = ApplicabilityRecord(applicability_id="a1", unit_revision_id="u1-v1", effective_from=date(2026, 1, 1),
                                 effective_to=date(2026, 7, 1), approval="approved")
    assert record.applies_on(date(2026, 6, 30))
    assert not record.applies_on(date(2026, 7, 1))
    assert not replace(record, approval="pending").applies_on(date(2026, 3, 1))
    assert not replace(record, effective_from=None, effective_to=None).applies_on(date(2026, 3, 1))
    with pytest.raises(ValueError):
        replace(record, effective_to=date(2025, 1, 1))


def test_scopes_and_partial_change_require_explicit_context():
    QueryScope(mode="as_of", as_of=date(2026, 3, 1))
    with pytest.raises(ValueError):
        QueryScope(mode="as_of")
    with pytest.raises(ValueError):
        QueryScope(mode="current", as_of=date(2026, 3, 1))
    with pytest.raises(ValueError):
        ChangeRequest(kind="partial")
    with pytest.raises(ValueError):
        TargetRef()


def test_new_chunk_set_is_legacy_doc_id_not_logical_document():
    chunk = ChunkV2(chunk_id="set:0", document_id="doc", version_id="v2", processing_id="p",
                    unit_revision_id="u-v2", chunk_set_id="set", block_ids=("b1",),
                    locators=(Locator(source_id="s1", page=2),), source="input.pdf", text="Mức phí 120.000 đồng",
                    language="vi", kind="paragraph", masking_config_id="mask1", quality_assessment_id="qa1",
                    page_start=2, page_end=2)
    assert chunk.doc_id == "set"
    assert chunk.index_text == chunk.text
    assert chunk.to_dict()["version_id"] == "v2"


def test_ocr_contract_preserves_unknown_confidence_and_provenance():
    page = OCRPageInput(source_id="s1", page=2, image_artifact="images/page2.png", width=100, height=200)
    region = OCRRegion(text="Điều 2", bbox=(.1, .1, .9, .2), order=0, confidence=None, kind="heading")
    result = OCRResult(regions=(region,), engine_name="fake", engine_version="1", cost_usd=Decimal("0"), elapsed_ms=1)
    assert result.regions[0].confidence is None
    assert page.page == 2
    assert ChunkerV2 and DocumentParserV2
