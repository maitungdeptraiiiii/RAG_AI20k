import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from filelock import FileLock

from rag.legal.keys import document_key
from rag.legal.models import LegalDocument
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager, SnapshotValidationError, WriteLockedError
from rag.legal.store import LegalStore

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
KEY = document_key("Luật", "99/2024/QH15")
KEY2 = document_key("Luật", "98/2025/QH15")
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
LAW2_TEXT = LAW_TEXT.replace("99/2024/QH15", "98/2025/QH15").replace("THỬ NGHIỆM", "KIỂM CHỨNG") \
    .replace("năm 2024", "năm 2025")


def _doc(key, number, title, issued, path, checksum):
    return LegalDocument(key, "1", title, "Luật", number, "Quốc hội", issued, None, None, None, False, str(path),
                         checksum, NOW)


@pytest.fixture
def small_legacy_catalog(tmp_path):
    """Kho cũ một văn bản ở legal_dir/catalog.sqlite, đã dựng; trả về build_id của bản dựng cũ."""
    path, checksum = write_text(tmp_path / "raw", KEY, LAW_TEXT)
    store = LegalStore(tmp_path / "catalog.sqlite")
    store.upsert_document(_doc(KEY, "99/2024/QH15", "Luật thử nghiệm", date(2024, 1, 1), path, checksum))
    LegalService(store, now=lambda: NOW).build_all()
    return store.latest_build(KEY).build_id


@pytest.fixture
def mgr_with_law(tmp_path, small_legacy_catalog):
    return SnapshotManager(tmp_path)


def add_second_law(svc: LegalService) -> None:
    raw = svc.store.path.parents[2] / "raw"         # legal_dir/snapshots/<id>/catalog.sqlite -> legal_dir/raw
    path, checksum = write_text(raw, KEY2, LAW2_TEXT)
    svc.store.upsert_document(_doc(KEY2, "98/2025/QH15", "Luật kiểm chứng", date(2025, 1, 1), path, checksum))


def other_doc() -> LegalDocument:
    return _doc(KEY2, "98/2025/QH15", "Luật kiểm chứng", date(2025, 1, 1), "x", "f" * 64)


def test_bootstrap_copies_legacy_catalog_without_rebuild(tmp_path, small_legacy_catalog, monkeypatch):
    calls = []
    monkeypatch.setattr(LegalService, "build_all", lambda self, progress=None: calls.append(1))
    mgr = SnapshotManager(tmp_path)
    snap = mgr.current()
    assert snap.status == "published" and snap.reason == "bootstrap" and snap.parent_id is None
    assert snap.catalog_path == tmp_path / "snapshots" / snap.snapshot_id / "catalog.sqlite"
    assert [d.document_key for d in mgr.store().documents()] == [KEY]
    assert mgr.store().latest_build(KEY).build_id == small_legacy_catalog
    assert (tmp_path / "CURRENT").read_text(encoding="utf-8").strip() == snap.snapshot_id
    assert calls == []
    assert SnapshotManager(tmp_path).current().snapshot_id == snap.snapshot_id   # không bootstrap lại


def test_bootstrap_without_legacy_is_empty(tmp_path):
    mgr = SnapshotManager(tmp_path)
    assert mgr.current().reason == "bootstrap" and mgr.store().documents() == []
    assert mgr.current().snapshot_id.startswith("s") and len(mgr.current().snapshot_id) == 1 + 14 + 1 + 6


def test_write_publishes_new_snapshot_and_keeps_parent(tmp_path, mgr_with_law):
    before = mgr_with_law.current()
    res = mgr_with_law.write("cli:build", "test", lambda svc: "ok")
    assert res.value == "ok" and res.snapshot.status == "published" and res.snapshot.parent_id == before.snapshot_id
    assert res.snapshot.published_at is not None and res.snapshot.actor == "test"
    assert mgr_with_law.current().snapshot_id == res.snapshot.snapshot_id
    assert mgr_with_law.get(before.snapshot_id).catalog_path.exists()
    assert [s.snapshot_id for s in mgr_with_law.list()] == [res.snapshot.snapshot_id, before.snapshot_id]
    assert mgr_with_law.validate(mgr_with_law.service()) == []


def test_write_builds_staging_and_reports_progress(tmp_path, mgr_with_law):
    before = mgr_with_law.current()
    seen = []
    res = mgr_with_law.write("upload:u1", "test", add_second_law, progress=lambda *a: seen.append(a))
    assert ("build", 2, 2) in seen
    assert mgr_with_law.store().latest_build(KEY2) is not None
    assert mgr_with_law.store(before.snapshot_id).document(KEY2) is None      # snapshot cũ không bị chạm tới
    assert res.snapshot.reason == "upload:u1"


def test_failure_during_build_keeps_current(tmp_path, mgr_with_law, monkeypatch):
    before = mgr_with_law.current()
    original = LegalService.build_law
    calls = []

    def boom_on_second_call(self, key):
        calls.append(key)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return original(self, key)

    monkeypatch.setattr(LegalService, "build_law", boom_on_second_call)      # lỗi ở luật thứ 2
    with pytest.raises(RuntimeError):
        mgr_with_law.write("upload:u1", "test", add_second_law)
    assert mgr_with_law.current().snapshot_id == before.snapshot_id
    assert mgr_with_law.list()[0].status == "failed" and "boom" in mgr_with_law.list()[0].error
    assert mgr_with_law.list()[0].catalog_path.exists()                       # giữ staging để xem lỗi


def test_validation_failure_is_not_published(tmp_path, mgr_with_law):
    before = mgr_with_law.current()
    with pytest.raises(SnapshotValidationError) as err:
        mgr_with_law.write("upload:u1", "t", lambda svc: Path(svc.store.document(KEY).raw_text_path).write_text("x"))
    assert err.value.problems
    assert mgr_with_law.current().snapshot_id == before.snapshot_id
    assert mgr_with_law.list()[0].status == "failed"


def test_validate_detects_stale_build_and_dangling_target(tmp_path, mgr_with_law):
    with mgr_with_law.scratch() as svc:
        assert mgr_with_law.validate(svc) == []
        doc = svc.store.document(KEY)
        svc.store.upsert_document(replace(doc, source_verified=False))       # inputs đổi mà chưa dựng lại
        problems = mgr_with_law.validate(svc)
        assert any(KEY in p for p in problems)


def test_business_error_discards_staging(tmp_path, mgr_with_law):
    n = len(mgr_with_law.list())
    dirs = set((tmp_path / "snapshots").iterdir())
    with pytest.raises(ValueError):
        mgr_with_law.write("review:r1", "t", lambda svc: (_ for _ in ()).throw(ValueError("x")))
    assert len(mgr_with_law.list()) == n
    assert set((tmp_path / "snapshots").iterdir()) == dirs


def test_second_writer_gets_locked_error(tmp_path, mgr_with_law):
    other = FileLock(tmp_path / "write.lock"); other.acquire()
    try:
        with pytest.raises(WriteLockedError):
            SnapshotManager(tmp_path).write("cli:build", "t", lambda s: None)
    finally:
        other.release()


def test_mark_interrupted(tmp_path, mgr_with_law):
    conn = sqlite3.connect(tmp_path / "snapshots" / "index.sqlite")
    try:
        with conn:
            conn.execute("INSERT INTO snapshots (snapshot_id, parent_id, status, reason, actor, created_at) "
                         "VALUES ('s20261110000000-abcdef', NULL, 'building', 'cli:build', 't', ?)", (NOW.isoformat(),))
    finally:
        conn.close()
    assert mgr_with_law.mark_interrupted() == ["s20261110000000-abcdef"]
    assert mgr_with_law.list()[0].status == "failed" and mgr_with_law.list()[0].error
    assert mgr_with_law.mark_interrupted() == []


def test_cleanup_keeps_three_current_and_in_use(tmp_path, mgr_with_law):
    boot = mgr_with_law.current().snapshot_id
    ids = [mgr_with_law.write("cli:build", "t", lambda s: None).snapshot.snapshot_id for _ in range(5)]
    removed = mgr_with_law.cleanup(keep=3, in_use={ids[0]})
    assert ids[0] not in removed and ids[1] in removed and all(i not in removed for i in ids[2:])
    assert boot in removed
    assert not (tmp_path / "snapshots" / ids[1]).exists() and (tmp_path / "snapshots" / ids[0]).exists()
    assert mgr_with_law.cleanup(keep=3, in_use={ids[0]}) == []


def test_cleanup_removes_old_failed_staging(tmp_path, small_legacy_catalog):
    clock = [NOW]
    mgr = SnapshotManager(tmp_path, now=lambda: clock[0])
    with pytest.raises(RuntimeError):
        mgr.write("cli:build", "t", lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    failed = mgr.list()[0].snapshot_id
    assert mgr.cleanup() == []
    clock[0] = NOW + timedelta(days=8)
    assert mgr.cleanup() == [failed]


def test_scratch_does_not_touch_current(tmp_path, mgr_with_law):
    with mgr_with_law.scratch() as svc:
        svc.store.upsert_document(other_doc())
        scratch_dir = svc.store.path.parent
    assert other_doc().document_key not in {d.document_key for d in mgr_with_law.store().documents()}
    assert not scratch_dir.exists()
