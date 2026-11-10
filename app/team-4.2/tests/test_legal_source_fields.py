from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from rag.legal.keys import document_key
from rag.legal.models import LegalDocument
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.store import LegalStore, decode, encode

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
KEY = document_key("Luật", "99/2024/QH15")
LAW_TEXT = """Luật số: 99/2024/QH15
LUẬT
THỬ NGHIỆM
Điều 1. Phạm vi
Luật này quy định về thử nghiệm.
Điều 2. Đối tượng
Luật này áp dụng cho mọi tổ chức.
Điều 3. Hiệu lực thi hành
Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.
"""


def test_old_payload_without_new_fields_decodes_with_defaults():
    old = {"document_key": KEY, "vbpl_id": "1", "title": "t", "doc_type": "Luật", "doc_number": "99/2024/QH15",
           "issuer": None, "issued_on": "2024-01-01", "vbpl_effective_from": None, "vbpl_effective_to": None,
           "eff_status": None, "is_consolidated": False, "raw_text_path": "x", "raw_checksum": "f" * 64,
           "fetched_at": NOW.isoformat(), "discovered_via": None}
    doc = decode(LegalDocument, old)
    assert doc.text_source == "vbpl" and doc.source_verified is True and doc.field_sources == {}
    assert doc.content_verified is None and doc.source_checked_at is None and doc.metadata_conflicts == ()


def test_new_fields_round_trip():
    doc = LegalDocument(KEY, "1", "t", "Luật", "99/2024/QH15", None, None, None, None, None, False, "x", "f" * 64, NOW,
                        text_source="file", content_verified={"by": "a", "at": "2026-11-10"}, source_verified=False,
                        source_checked_at=NOW, field_sources={"title": {"source": "text", "at": "z", "detail": "d"}},
                        metadata_conflicts=("c",))
    assert decode(LegalDocument, encode(doc)) == doc


def test_content_path_is_immutable_per_checksum(tmp_path):
    p1, c1 = write_text(tmp_path, "luat:43/2024/QH15", "A\n")
    p2, c2 = write_text(tmp_path, "luat:43/2024/QH15", "B\n")
    assert p1 != p2 and p1.read_text(encoding="utf-8") == "A\n"
    assert write_text(tmp_path, "luat:43/2024/QH15", "A\n") == (p1, c1)
    assert p1 == tmp_path / "luat_43_2024_QH15" / f"{c1}.txt"


@pytest.fixture
def svc_with_doc(tmp_path):
    def make(**overrides):
        path, checksum = write_text(tmp_path / "raw", KEY, LAW_TEXT)
        store = LegalStore(tmp_path / "legal" / "catalog.sqlite")
        d = LegalDocument(KEY, "1", "Luật thử nghiệm", "Luật", "99/2024/QH15", "Quốc hội", date(2024, 1, 1), None, None,
                          None, False, str(path), checksum, NOW)
        store.upsert_document(replace(d, **overrides))
        return LegalService(store, now=lambda: NOW)
    return make


def test_unverified_source_flags_every_version(svc_with_doc):
    svc = svc_with_doc(source_verified=False)
    svc.build_all()
    vs = svc.store.versions(KEY)
    assert vs and all("source.no_vbpl_metadata" in v.status_reasons for v in vs)
    assert all(v.verification_status == "needs_review" for v in vs)


def test_metadata_conflict_flags_every_version(svc_with_doc):
    svc = svc_with_doc(metadata_conflicts=("ngày hiệu lực kế thừa 01/01/2025 khác điều hiệu lực 01/8/2024",))
    svc.build_all()
    vs = svc.store.versions(KEY)
    assert vs and all("source.inherited_metadata_conflict" in v.status_reasons for v in vs)


def test_verified_source_unchanged(svc_with_doc):
    svc = svc_with_doc()
    svc.build_all()
    vs = svc.store.versions(KEY)
    assert vs and not any(r.startswith("source.") for v in vs for r in v.status_reasons)


def test_build_all_reports_progress(svc_with_doc):
    seen = []
    svc_with_doc().build_all(progress=lambda stage, i, n: seen.append((stage, i, n)))
    assert ("plan", 1, 1) in seen and ("build", 1, 1) in seen
