import os
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


def test_store_of_removed_snapshot_raises_without_recreating(tmp_path, mgr_with_law):
    boot = mgr_with_law.current().snapshot_id
    for _ in range(2):
        mgr_with_law.write("cli:build", "t", lambda s: None)
    assert boot in mgr_with_law.cleanup(keep=1)
    with pytest.raises(FileNotFoundError):
        mgr_with_law.store(boot)
    with pytest.raises(FileNotFoundError):
        mgr_with_law.service(boot)
    assert not (tmp_path / "snapshots" / boot).exists()


def test_store_of_missing_catalog_raises(tmp_path, mgr_with_law):
    snap = mgr_with_law.write("cli:build", "t", lambda s: None).snapshot
    parent = mgr_with_law.get(snap.parent_id)
    parent.catalog_path.unlink()
    with pytest.raises(FileNotFoundError):
        mgr_with_law.store(parent.snapshot_id)
    assert not parent.catalog_path.exists()
    with pytest.raises(KeyError):
        mgr_with_law.store("s00000000000000-000000")


def test_publish_retries_pointer_replace_on_permission_error(tmp_path, mgr_with_law, monkeypatch):
    import rag.legal.snapshots as snapshots
    real, calls = os.replace, []

    def flaky(src, dst):
        if Path(dst).name == "CURRENT":
            calls.append(1)
            if len(calls) <= 3:
                raise PermissionError(13, "file in use")      # người đọc đang mở CURRENT (Windows)
        return real(src, dst)

    monkeypatch.setattr(snapshots.os, "replace", flaky)
    res = mgr_with_law.write("cli:build", "t", lambda s: None)
    assert len(calls) == 4 and res.snapshot.status == "published"
    assert mgr_with_law.current().snapshot_id == res.snapshot.snapshot_id
    assert not list(tmp_path.glob("CURRENT.*.tmp"))


def test_publish_gives_up_after_persistent_permission_error(tmp_path, mgr_with_law, monkeypatch):
    import rag.legal.snapshots as snapshots
    before = mgr_with_law.current().snapshot_id
    real = os.replace

    def always(src, dst):
        if Path(dst).name == "CURRENT":
            raise PermissionError(13, "file in use")
        return real(src, dst)

    monkeypatch.setattr(snapshots, "_RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(snapshots.os, "replace", always)
    with pytest.raises(PermissionError):
        mgr_with_law.write("cli:build", "t", lambda s: None)
    assert mgr_with_law.current().snapshot_id == before and mgr_with_law.list()[0].status == "failed"
    assert not list(tmp_path.glob("CURRENT.*.tmp"))


def test_current_retries_pointer_read_on_permission_error(tmp_path, mgr_with_law, monkeypatch):
    expected = mgr_with_law.current().snapshot_id
    real, calls = Path.read_text, []

    def flaky(self, *a, **kw):
        if self.name == "CURRENT":
            calls.append(1)
            if len(calls) <= 2:
                raise PermissionError(13, "being replaced")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert mgr_with_law.current().snapshot_id == expected and len(calls) == 3


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


# --- kho crawl cũ: file text CRLF + "\n" cuối, checksum tính trên text (crawl.save_detail cũ) ---------------------


@pytest.fixture
def legacy_crlf_catalog(tmp_path):
    """Như crawl.save_detail cũ: `path.write_text(text + "\n")` ở chế độ text trên Windows (CRLF), checksum = sha256(text)."""
    import hashlib

    legacy_file = tmp_path / "raw" / "luat_99_2024_QH15.txt"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_bytes((LAW_TEXT + "\n").replace("\n", "\r\n").encode("utf-8"))
    checksum = hashlib.sha256(LAW_TEXT.encode("utf-8")).hexdigest()
    store = LegalStore(tmp_path / "catalog.sqlite")
    store.upsert_document(_doc(KEY, "99/2024/QH15", "Luật thử nghiệm", date(2024, 1, 1), legacy_file, checksum))
    LegalService(store, now=lambda: NOW).build_all()
    return legacy_file


def test_legacy_crlf_store_is_migrated_and_writable(tmp_path, legacy_crlf_catalog):
    original = legacy_crlf_catalog.read_bytes()
    mgr = SnapshotManager(tmp_path)
    snaps = mgr.list()
    assert [s.reason for s in reversed(snaps)] == ["bootstrap", "migration"]
    boot, mig = snaps[1], snaps[0]
    assert mgr.current().snapshot_id == mig.snapshot_id and mig.parent_id == boot.snapshot_id
    # snapshot đã công bố không bị sửa tại chỗ: bootstrap vẫn trỏ file cũ
    assert mgr.store(boot.snapshot_id).document(KEY).raw_text_path == str(legacy_crlf_catalog)
    doc = mgr.store().document(KEY)
    assert Path(doc.raw_text_path) != legacy_crlf_catalog and Path(doc.raw_text_path).read_bytes() == \
        LAW_TEXT.encode("utf-8")
    res = mgr.write("cli:build", "t", add_second_law)               # trước đây: validate lỗi checksum
    assert res.snapshot.status == "published"
    assert legacy_crlf_catalog.read_bytes() == original             # file cũ còn nguyên
    assert len(SnapshotManager(tmp_path).list()) == 3                # idempotent: không migration lần nữa


def test_unfixable_text_mismatch_is_logged_not_migrated(tmp_path, legacy_crlf_catalog, caplog):
    legacy_crlf_catalog.write_bytes(b"noi dung khac\r\n")
    with caplog.at_level("ERROR"):
        mgr = SnapshotManager(tmp_path)
    assert [s.reason for s in mgr.list()] == ["bootstrap"]
    assert any(KEY in r.getMessage() for r in caplog.records if r.levelname == "ERROR")


# --- kho cũ được ghi sau khi kho có phiên bản đã khởi tạo ------------------------------------------------------


def test_legacy_catalog_populated_after_bootstrap_is_reported(tmp_path, caplog):
    mgr = SnapshotManager(tmp_path)                                 # bootstrap rỗng: chưa có kho cũ
    assert mgr.legacy_catalog_warning() is None
    path, checksum = write_text(tmp_path / "raw", KEY, LAW_TEXT)    # sau đó crawler cũ ghi vào kho cũ
    LegalStore(tmp_path / "catalog.sqlite").upsert_document(
        _doc(KEY, "99/2024/QH15", "Luật thử nghiệm", date(2024, 1, 1), path, checksum))
    with caplog.at_level("WARNING"):
        mgr2 = SnapshotManager(tmp_path)
    msg = mgr2.legacy_catalog_warning()
    assert msg and "catalog.sqlite" in msg and "1 văn bản" in msg
    assert any("catalog.sqlite" in r.getMessage() for r in caplog.records if r.levelno >= 30)
    assert mgr2.store().documents() == []                           # không tự nhập âm thầm


def test_legacy_catalog_modified_after_bootstrap_is_reported(tmp_path, small_legacy_catalog):
    mgr = SnapshotManager(tmp_path)
    assert mgr.legacy_catalog_warning() is None                      # đã nhập lúc bootstrap
    st = os.stat(tmp_path / "catalog.sqlite")
    LegalStore(tmp_path / "catalog.sqlite").upsert_document(other_doc())
    os.utime(tmp_path / "catalog.sqlite", ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert "2 văn bản" in SnapshotManager(tmp_path).legacy_catalog_warning()


def test_legacy_catalog_without_bootstrap_record_compares_creation_time(tmp_path, small_legacy_catalog):
    mgr = SnapshotManager(tmp_path, now=lambda: datetime(2020, 1, 1, tzinfo=timezone.utc))
    with sqlite3.connect(tmp_path / "snapshots" / "index.sqlite") as c:   # index của phiên bản code trước
        c.execute("DELETE FROM meta")
    assert mgr.legacy_catalog_warning() is not None                 # kho cũ sửa sau 2020 (thời điểm khởi tạo)


# --- thứ tự snapshot theo seq, không theo đồng hồ ---------------------------------------------------------------


def test_snapshot_seq_increases_even_when_clock_goes_back(tmp_path, small_legacy_catalog):
    times = iter([NOW + timedelta(hours=5 - i) for i in range(20)])      # đồng hồ lùi dần
    mgr = SnapshotManager(tmp_path, now=lambda: next(times))
    a = mgr.current()
    b = mgr.write("cli:build", "t", lambda svc: None).snapshot
    assert b.published_at < a.published_at and b.seq > a.seq
    assert mgr.get(b.snapshot_id).seq == b.seq and mgr.list()[0].seq == b.seq
