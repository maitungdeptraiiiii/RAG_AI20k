"""H3/K1: nạp văn bản đã tải (bộ bổ sung, fetch-report.json) vào kho luật có phiên bản qua SnapshotManager.write
(snapshot mới, snapshot cũ giữ nguyên; tệp gốc phải đúng checksum)."""
import json
from datetime import date, datetime, timezone

import pytest

from rag.legal.keys import document_key
from rag.legal.models import LegalDocument
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager
from rag.legal.store import LegalStore
from rag.legal.supplement import import_supplement

NOW = datetime(2026, 11, 23, tzinfo=timezone.utc)
KEY = document_key("Luật", "99/2024/QH15")
KEY2 = document_key("Luật", "98/2025/QH15")
LAW = """Luật số: {n}
LUẬT
THỬ NGHIỆM
Điều 1. Phạm vi
Luật này quy định về thử nghiệm.
Điều 2. Hiệu lực thi hành
Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2025.
"""


@pytest.fixture
def mgr(tmp_path):
    path, checksum = write_text(tmp_path / "raw", KEY, LAW.format(n="99/2024/QH15"))
    store = LegalStore(tmp_path / "catalog.sqlite")
    store.upsert_document(LegalDocument(KEY, "1", "Luật thử nghiệm", "Luật", "99/2024/QH15", "Quốc hội",
                                        date(2024, 1, 1), None, None, None, False, str(path), checksum, NOW))
    LegalService(store, now=lambda: NOW).build_all()
    return SnapshotManager(tmp_path)


def report(tmp_path, *, key=KEY2, text=LAW.format(n="98/2025/QH15"), status="downloaded", checksum=None):
    path, real = write_text(tmp_path / "raw", key, text)
    doc = {"document_key": key, "vbpl_id": "2", "title": "Luật kiểm chứng", "doc_type": "Luật",
           "doc_number": key.split(":", 1)[1], "issuer": "Quốc hội", "issued_on": "2025-01-01",
           "vbpl_effective_from": "2025-08-01", "vbpl_effective_to": None, "eff_status": "Còn hiệu lực",
           "is_consolidated": False, "raw_text_path": str(path), "raw_checksum": checksum or real,
           "fetched_at": NOW.isoformat(), "discovered_via": "test-scope", "text_source": "vbpl"}
    p = tmp_path / "fetch-report.json"
    p.write_text(json.dumps({"documents": {key: {"status": status, "legal_document": doc}}}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def test_import_publishes_a_new_snapshot_and_keeps_the_parent(tmp_path, mgr):
    parent = mgr.current().snapshot_id
    res = import_supplement(mgr, report(tmp_path), actor="test")
    assert res.value == {"imported": [KEY2], "skipped": {}}
    assert res.snapshot.snapshot_id != parent and mgr.current().snapshot_id == res.snapshot.snapshot_id
    store = mgr.store()
    assert store.document(KEY2) is not None and store.latest_build(KEY2) is not None   # đã dựng phiên bản
    assert mgr.store(parent).document(KEY2) is None                                    # snapshot cũ không đổi


def test_wrong_checksum_or_not_downloaded_is_skipped_and_nothing_published(tmp_path, mgr):
    parent = mgr.current().snapshot_id
    with pytest.raises(ValueError, match="checksum"):
        import_supplement(mgr, report(tmp_path, checksum="0" * 64), actor="test")
    with pytest.raises(ValueError, match="failed"):
        import_supplement(mgr, report(tmp_path, status="failed"), actor="test")
    assert mgr.current().snapshot_id == parent


def test_document_already_in_the_store_is_not_reimported(tmp_path, mgr):
    import_supplement(mgr, report(tmp_path), actor="test")
    with pytest.raises(ValueError, match="already_present"):
        import_supplement(mgr, report(tmp_path), actor="test")
