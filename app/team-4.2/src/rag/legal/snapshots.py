"""Snapshot kho luật: mọi lần ghi dựng một bản sao đầy đủ (staging), kiểm tra, rồi công bố nguyên khối bằng cách
đổi con trỏ `CURRENT`. Người đọc không bao giờ thấy kho dựng dở.

Bố cục trong `legal_dir`:
- `CURRENT`                          một dòng: snapshot_id đang công bố (ghi bằng file tạm + `os.replace`)
- `write.lock`                       khoá ghi toàn kho (một người ghi tại một thời điểm)
- `snapshots/index.sqlite`           metadata các snapshot (bảng `snapshots`)
- `snapshots/<id>/catalog.sqlite`    kho của từng snapshot
- `raw/`                             text nguồn theo nội dung, dùng chung mọi snapshot (không sao chép)
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generic, Literal, TypeVar

from filelock import FileLock, Timeout

from rag.legal.service import LegalService
from rag.legal.store import LegalStore

T = TypeVar("T")
SnapshotStatus = Literal["building", "validated", "published", "failed"]

_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (seq INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id TEXT UNIQUE NOT NULL,
    parent_id TEXT, status TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
    published_at TEXT, error TEXT, removed_at TEXT);
"""
_COLUMNS = "snapshot_id, parent_id, status, reason, actor, created_at, published_at, error"
_FAILED_RETENTION = timedelta(days=7)
_BOOTSTRAP_LOCK_TIMEOUT = 60.0


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str            # "s" + yyyymmddHHMMSS + "-" + 6 hex
    parent_id: str | None
    status: SnapshotStatus
    reason: str                 # "bootstrap" | "upload:<upload_id>" | "review:<review_id>" | "cli:build" | "cli:crawl"
    actor: str
    created_at: datetime
    published_at: datetime | None
    error: str | None
    catalog_path: Path          # legal_dir/snapshots/<id>/catalog.sqlite


@dataclass(frozen=True)
class WriteResult(Generic[T]):
    snapshot: Snapshot
    value: T


class WriteLockedError(RuntimeError):
    def __init__(self, message: str = "Đang có lần cập nhật kho khác") -> None:
        super().__init__(message)


class SnapshotValidationError(RuntimeError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("Kho dựng không hợp lệ: " + "; ".join(problems))
        self.problems = list(problems)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _copy_sqlite(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    s, d = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SnapshotManager:
    def __init__(self, legal_dir: Path, *, now: Callable[[], datetime] = _utcnow,
                 service_factory: Callable[[LegalStore], LegalService] = LegalService,
                 lock_timeout: float = 0.0) -> None:
        self.legal_dir = Path(legal_dir)
        self.now = now
        self.service_factory = service_factory
        self.lock_timeout = lock_timeout
        self._snapshots_dir = self.legal_dir / "snapshots"
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._index = self._snapshots_dir / "index.sqlite"
        self._pointer = self.legal_dir / "CURRENT"
        self._lock_path = self.legal_dir / "write.lock"
        with self._db() as c:
            c.executescript(_INDEX_SCHEMA)
        if not self._pointer.exists():
            self._bootstrap()

    # --- index -------------------------------------------------------------------------

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._index, timeout=30)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _catalog(self, snapshot_id: str) -> Path:
        return self._snapshots_dir / snapshot_id / "catalog.sqlite"

    def _row(self, row: tuple) -> Snapshot:
        sid, parent, status, reason, actor, created, published, error = row
        return Snapshot(sid, parent, status, reason, actor, datetime.fromisoformat(created),
                        datetime.fromisoformat(published) if published else None, error, self._catalog(sid))

    def _new_id(self) -> str:
        return "s" + self.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)

    def _insert(self, snapshot_id: str, parent_id: str | None, status: SnapshotStatus, reason: str, actor: str) -> None:
        with self._db() as c:
            c.execute(f"INSERT INTO snapshots ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
                      (snapshot_id, parent_id, status, reason, actor, self.now().isoformat()))

    def _set_status(self, snapshot_id: str, status: SnapshotStatus, *, error: str | None = None,
                    published_at: datetime | None = None) -> None:
        with self._db() as c:
            c.execute("UPDATE snapshots SET status=?, error=COALESCE(?, error), "
                      "published_at=COALESCE(?, published_at) WHERE snapshot_id=?",
                      (status, error, published_at.isoformat() if published_at else None, snapshot_id))

    def _write_pointer(self, snapshot_id: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.legal_dir, prefix="CURRENT.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(snapshot_id + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._pointer)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _bootstrap(self) -> None:
        lock = FileLock(self._lock_path, timeout=max(self.lock_timeout, _BOOTSTRAP_LOCK_TIMEOUT))
        with lock:
            if self._pointer.exists():          # một tiến trình khác vừa khởi tạo
                return
            sid = self._new_id()
            path = self._catalog(sid)
            legacy = self.legal_dir / "catalog.sqlite"
            if legacy.exists():
                _copy_sqlite(legacy, path)
            LegalStore(path)                    # bảo đảm schema (kho rỗng nếu không có kho cũ)
            self._insert(sid, None, "building", "bootstrap", "system")
            now = self.now()
            self._set_status(sid, "published", published_at=now)
            self._write_pointer(sid)

    # --- đọc ---------------------------------------------------------------------------

    def current(self) -> Snapshot:
        return self.get(self._pointer.read_text(encoding="utf-8").strip())

    def get(self, snapshot_id: str) -> Snapshot:
        with self._db() as c:
            row = c.execute(f"SELECT {_COLUMNS} FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return self._row(row)

    def list(self) -> list[Snapshot]:
        with self._db() as c:
            rows = c.execute(f"SELECT {_COLUMNS} FROM snapshots ORDER BY seq DESC").fetchall()
        return [self._row(r) for r in rows]

    def store(self, snapshot_id: str | None = None) -> LegalStore:
        snap = self.get(snapshot_id) if snapshot_id is not None else self.current()
        return LegalStore(snap.catalog_path)

    def service(self, snapshot_id: str | None = None) -> LegalService:
        return self.service_factory(self.store(snapshot_id))

    # --- ghi ---------------------------------------------------------------------------

    def write(self, reason: str, actor: str, fn: Callable[[LegalService], T], *,
              progress: Callable[[str, int, int], None] | None = None) -> WriteResult[T]:
        lock = FileLock(self._lock_path, timeout=self.lock_timeout)
        try:
            lock.acquire()
        except Timeout:
            raise WriteLockedError() from None
        try:
            parent = self.current()
            sid = self._new_id()
            path = self._catalog(sid)
            self._insert(sid, parent.snapshot_id, "building", reason, actor)
            try:
                _copy_sqlite(parent.catalog_path, path)
                svc = self.service_factory(LegalStore(path))
                try:
                    value = fn(svc)
                except (ValueError, KeyError):
                    self._discard(sid)          # lỗi nghiệp vụ: không giữ staging
                    raise
                svc.build_all(progress)
                problems = self.validate(svc)
                if problems:
                    raise SnapshotValidationError(problems)
                self._set_status(sid, "validated")
                # dòng index trước, con trỏ sau: lỗi khi đổi con trỏ -> `failed` bên dưới, CURRENT không đổi
                self._set_status(sid, "published", published_at=self.now())
                self._write_pointer(sid)
            except BaseException as exc:
                if self._exists(sid):
                    self._set_status(sid, "failed", error=f"{type(exc).__name__}: {exc}")
                raise
            return WriteResult(self.get(sid), value)
        finally:
            lock.release()

    def _exists(self, snapshot_id: str) -> bool:
        with self._db() as c:
            return c.execute("SELECT 1 FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone() is not None

    def _discard(self, snapshot_id: str) -> None:
        shutil.rmtree(self._snapshots_dir / snapshot_id, ignore_errors=True)
        with self._db() as c:
            c.execute("DELETE FROM snapshots WHERE snapshot_id=?", (snapshot_id,))

    @contextmanager
    def scratch(self) -> Iterator[LegalService]:
        root = self.legal_dir / "scratch"
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=root))
        try:
            path = folder / "catalog.sqlite"
            _copy_sqlite(self.current().catalog_path, path)
            yield self.service_factory(LegalStore(path))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def mark_interrupted(self) -> list[str]:
        """Snapshot `building`/`validated` còn sót (tiến trình chết giữa chừng) -> `failed`.
        Bỏ qua nếu đang có người ghi: staging của họ vẫn đang chạy."""
        lock = FileLock(self._lock_path, timeout=0)
        try:
            lock.acquire()
        except Timeout:
            return []
        try:
            with self._db() as c:
                ids = [r[0] for r in c.execute("SELECT snapshot_id FROM snapshots WHERE status IN "
                                               "('building', 'validated') ORDER BY seq").fetchall()]
                c.executemany("UPDATE snapshots SET status='failed', error=? WHERE snapshot_id=?",
                              [("bị dừng giữa chừng", i) for i in ids])
            return ids
        finally:
            lock.release()

    def cleanup(self, keep: int = 3, in_use: Collection[str] = ()) -> list[str]:
        """Xoá thư mục snapshot `published` cũ hơn `keep` bản mới nhất và staging `failed` cũ hơn 7 ngày,
        trừ snapshot đang công bố và `in_use`. Dòng index được giữ (lịch sử), đánh dấu `removed_at`."""
        protected = {self.current().snapshot_id, *in_use}
        with self._db() as c:
            removed_ids = {r[0] for r in c.execute("SELECT snapshot_id FROM snapshots "
                                                   "WHERE removed_at IS NOT NULL").fetchall()}
        snaps = self.list()
        published = [s for s in snaps if s.status == "published"]
        cutoff = self.now() - _FAILED_RETENTION
        victims = published[keep:] + [s for s in snaps if s.status == "failed" and s.created_at < cutoff]
        removed = []
        for s in victims:
            if s.snapshot_id in protected or s.snapshot_id in removed_ids:
                continue
            folder = self._snapshots_dir / s.snapshot_id
            try:
                if folder.exists():
                    shutil.rmtree(folder)
            except OSError:
                continue                        # còn người đọc giữ file (Windows): thử lại lần sau
            with self._db() as c:
                c.execute("UPDATE snapshots SET removed_at=? WHERE snapshot_id=?",
                          (self.now().isoformat(), s.snapshot_id))
            removed.append(s.snapshot_id)
        return removed

    # --- kiểm tra ----------------------------------------------------------------------

    def validate(self, service: LegalService) -> list[str]:
        store = service.store
        docs = store.documents()
        keys = {d.document_key for d in docs}
        problems: list[str] = []
        text_ok: set[str] = set()
        for d in docs:
            path = Path(d.raw_text_path)
            if not path.is_file():
                problems.append(f"{d.document_key}: không thấy file text {path}")
            elif _sha256(path) != d.raw_checksum:
                problems.append(f"{d.document_key}: checksum file text không khớp ({path})")
            else:
                text_ok.add(d.document_key)
        for d in docs:
            if d.is_consolidated:
                continue
            run = store.latest_build(d.document_key)
            if run is None:
                problems.append(f"{d.document_key}: chưa có bản dựng")
                continue
            if d.document_key not in text_ok:
                continue
            try:
                expected = service.build_inputs(d.document_key)
            except Exception as exc:            # noqa: BLE001 - báo như một vấn đề, không làm hỏng validate
                problems.append(f"{d.document_key}: không tính được inputs ({type(exc).__name__}: {exc})")
                continue
            if run.inputs_checksum != expected:
                problems.append(f"{d.document_key}: bản dựng mới nhất không khớp thao tác hiện tại")
        for op in store.operations():
            if op.review_status in ("auto_accepted", "approved") and op.target_document_key \
                    and op.target_document_key not in keys:
                problems.append(f"thao tác {op.operation_id}: luật đích {op.target_document_key} không có trong kho")
        return problems


__all__ = ["Snapshot", "SnapshotManager", "SnapshotStatus", "SnapshotValidationError", "WriteLockedError",
           "WriteResult"]
