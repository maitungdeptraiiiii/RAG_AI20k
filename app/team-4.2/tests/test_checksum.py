"""File reuse must never treat unfinished/incompatible processing as complete."""

from dataclasses import replace
from decimal import Decimal
import hashlib
import sqlite3
import unicodedata

import pytest

from rag.ingest.checksum import canonical_checksum, file_checksum
from rag.ingest.checksum_registry import ChecksumRegistry, CompletionReceipt


CONFIG = {"parser": "pdf-v1", "ocr": "test-v1", "mask": "v1", "chunk": "structural-v1", "index": "embed-v1"}
META = {"effective_from": "2026-07-01", "change_kind": "full", "supersedes": ["v1"]}


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.7\nsynthetic fixture; no OCR required for byte hashing")
    return path


@pytest.fixture
def registry(tmp_path):
    return ChecksumRegistry(tmp_path / "w02" / "checks.sqlite")


def check(registry, source, **overrides):
    request = dict(document_id="doc-a", version_metadata=META, processing_config=CONFIG)
    request.update(overrides)
    return registry.check_file(source, **request)


def receipt(**overrides):
    return replace(CompletionReceipt(document_id="doc-a", version_id="v2", chunk_set_id="set-v2", generation_id="gen-1"),
                   **overrides)


def test_sha256_matches_reference_for_multiblock_file(tmp_path):
    data = bytes(range(256)) * 9000
    path = tmp_path / "large.pdf"
    path.write_bytes(data)
    assert file_checksum(path) == hashlib.sha256(data).hexdigest()


def test_same_bytes_ignore_name_but_changes_detected(source, tmp_path):
    copy = tmp_path / "renamed.pdf"
    copy.write_bytes(source.read_bytes())
    assert file_checksum(copy) == file_checksum(source)
    copy.write_bytes(copy.read_bytes() + b"!")
    assert file_checksum(copy) != file_checksum(source)


def test_canonical_hash_preserves_structure_numbers_and_unicode():
    assert canonical_checksum({"a": "tiếng Việt", "b": Decimal("1.25")}) == canonical_checksum(
        {"b": Decimal("1.25"), "a": unicodedata.normalize("NFD", "tiếng Việt")})
    assert canonical_checksum(["Điều 1", "Điều 2"]) != canonical_checksum(["Điều 2", "Điều 1"])
    assert canonical_checksum("Mức phí 100") != canonical_checksum("Mức phí 120")
    assert canonical_checksum("Điều") != canonical_checksum("điều")


def test_unfinished_check_is_not_reusable(registry, source):
    first = check(registry, source)
    second = check(registry, source)
    assert first.status == second.status == "new"
    assert first.check_id != second.check_id


def test_completed_result_reused_after_restart_and_rename(registry, source, tmp_path):
    first = check(registry, source)
    registry.mark_completed(first.check_id, receipt())
    renamed = tmp_path / "renamed.pdf"
    renamed.write_bytes(source.read_bytes())
    restarted = ChecksumRegistry(registry.database)
    again = check(restarted, renamed)
    assert again.status == "reusable"
    assert again.receipt == receipt()
    assert again.reusable_check_id == first.check_id
    third = check(restarted, source)
    assert third.status == "reusable"
    with sqlite3.connect(registry.database) as conn:
        assert conn.execute("SELECT count(*) FROM w02_file_checks").fetchone()[0] == 3


@pytest.mark.parametrize("overrides", [
    {"document_id": "doc-other"},
    {"document_id": None},
    {"version_metadata": {**META, "effective_from": "2027-01-01"}},
    {"version_metadata": {**META, "supersedes": ["different"]}},
    {"processing_config": {**CONFIG, "chunk": "fixed-v1"}},
    {"processing_config": {**CONFIG, "mask": "v2"}},
])
def test_metadata_identity_and_config_must_match(registry, source, overrides):
    first = check(registry, source)
    registry.mark_completed(first.check_id, receipt())
    assert check(registry, source, **overrides).status == "new"


def test_unconfirmed_identity_can_be_confirmed_on_completion(registry, source):
    first = check(registry, source, document_id=None)
    registry.mark_completed(first.check_id, receipt())
    assert check(registry, source, document_id=None).status == "new"
    assert check(registry, source, document_id="doc-a").status == "reusable"


def test_failed_attempt_is_not_reused_and_retry_can_finish(registry, source):
    first = check(registry, source)
    registry.mark_failed(first.check_id)
    registry.mark_failed(first.check_id)
    with pytest.raises(ValueError):
        registry.mark_completed(first.check_id, receipt())
    retry = check(registry, source)
    assert retry.status == "new"
    registry.mark_completed(retry.check_id, receipt())
    assert check(registry, source).status == "reusable"


def test_completion_is_idempotent_and_conflicting_completion_rejected(registry, source):
    first = check(registry, source)
    registry.mark_completed(first.check_id, receipt())
    registry.mark_completed(first.check_id, receipt())
    with pytest.raises(ValueError):
        registry.mark_completed(first.check_id, receipt(version_id="wrong"))
    with pytest.raises(ValueError):
        registry.mark_failed(first.check_id)


def test_wrong_document_and_changed_file_cannot_complete(registry, source):
    first = check(registry, source)
    with pytest.raises(ValueError):
        registry.mark_completed(first.check_id, receipt(document_id="doc-b"))
    source.write_bytes(b"modified while ingesting")
    with pytest.raises(ValueError):
        registry.mark_completed(first.check_id, receipt())


def test_withdrawn_generation_cannot_be_reused(registry, source):
    first = check(registry, source)
    registry.mark_completed(first.check_id, receipt())
    assert registry.invalidate_generation("gen-1") == 1
    assert check(registry, source).status == "new"


def test_invalid_calls_do_not_produce_reuse(registry, source):
    with pytest.raises(ValueError):
        check(registry, source, processing_config={})
    with pytest.raises(ValueError):
        check(registry, source, version_metadata=None)
    with pytest.raises(ValueError):
        registry.mark_completed("unknown", receipt())
    with pytest.raises(FileNotFoundError):
        check(registry, source.parent / "missing.pdf")


def test_checksum_rejects_ambiguous_json_keys_and_nan():
    with pytest.raises(ValueError):
        canonical_checksum({"é": 1, unicodedata.normalize("NFD", "é"): 2})
    with pytest.raises(ValueError):
        canonical_checksum({"score": float("nan")})
