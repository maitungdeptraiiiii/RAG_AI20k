"""Snapshot kho luật: mọi lần ghi dựng một bản sao đầy đủ (staging), kiểm tra, rồi công bố nguyên khối bằng cách
đổi con trỏ `CURRENT`. Người đọc không bao giờ thấy kho dựng dở.

Bố cục trong `legal_dir`:
- `CURRENT`                          một dòng: snapshot_id đang công bố (ghi bằng file tạm + `os.replace`)
- `write.lock`                       khoá ghi toàn kho (một người ghi tại một thời điểm)
- `snapshots/index.sqlite`           metadata các snapshot (bảng `snapshots`)
- `snapshots/<id>/catalog.sqlite`    kho của từng snapshot
- `raw/`                             text nguồn theo nội dung, dùng chung mọi snapshot (không sao chép)
- `catalog.sqlite`                   kho cũ (trước snapshot): chỉ đọc, sao chép một lần khi bootstrap

Khởi tạo: bootstrap (nếu chưa có CURRENT) -> chuyển đổi file text của kho crawl cũ (snapshot `migration` nếu cần)
-> cảnh báo nếu kho cũ có dữ liệu chưa được nhập (`legacy_catalog_warning`).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generic, Literal, TypeVar

from filelock import FileLock, Timeout

from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.store import LegalStore

log = logging.getLogger(__name__)

T = TypeVar("T")
SnapshotStatus = Literal["building", "validated", "published", "failed"]

_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (seq INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id TEXT UNIQUE NOT NULL,
    parent_id TEXT, status TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
    published_at TEXT, error TEXT, removed_at TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
_COLUMNS = "snapshot_id, parent_id, status, reason, actor, created_at, published_at, error"
_SELECT = _COLUMNS + ", seq"
_LEGACY_MTIME = "legacy_catalog_mtime_ns"     # mtime kho cũ lúc bootstrap ("" = lúc đó chưa có kho cũ)
_FAILED_RETENTION = timedelta(days=7)
_BOOTSTRAP_LOCK_TIMEOUT = 60.0
# Windows: open() không có FILE_SHARE_DELETE -> os.replace vào CURRENT lỗi PermissionError khi có người đang đọc nó,
# và đọc CURRENT có thể lỗi đúng lúc đang thay. Thử lại ngắn (~1s tổng).
_RETRY_DELAYS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.4)


def _retry_on_permission(action: Callable[[], T]) -> T:
    for delay in _RETRY_DELAYS:
        try:
            return action()
        except PermissionError:
            time.sleep(delay)
    return action()


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
    seq: int = 0                # thứ tự tạo trong index, tăng dần (không phụ thuộc đồng hồ): so "mới hơn" bằng seq


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


def _legacy_text_fix(path: Path, checksum: str) -> str | None:
    """Text đúng checksum của một file crawl cũ (ghi `text + "\\n"` ở chế độ text: CRLF trên Windows và một "\\n"
    cuối), hoặc None nếu không khôi phục được."""
    text = path.read_text(encoding="utf-8")         # newline phổ dụng: CRLF -> LF
    for cand in ((text[:-1],) if text.endswith("\n") else ()) + (text,):
        if hashlib.sha256(cand.encode("utf-8")).hexdigest() == checksum:
            return cand
    return None


def _count_documents(catalog: Path) -> int | None:
    """Số văn bản trong một kho sqlite, mở CHỈ ĐỌC (không đổi file / mtime). Lỗi -> None."""
    try:
        conn = sqlite3.connect(catalog.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return None


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
        self._migrate_legacy_text()
        warning = self.legacy_catalog_warning()
        if warning:
            log.warning("KHO LUẬT CŨ CHƯA ĐƯỢC NHẬP: %s", warning)

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
        sid, parent, status, reason, actor, created, published, error, seq = row
        return Snapshot(sid, parent, status, reason, actor, datetime.fromisoformat(created),
                        datetime.fromisoformat(published) if published else None, error, self._catalog(sid), seq)

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
            _retry_on_permission(lambda: os.replace(tmp, self._pointer))
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
            mtime = ""
            if legacy.exists():
                mtime = str(legacy.stat().st_mtime_ns)
                _copy_sqlite(legacy, path)
            with self._db() as c:
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (_LEGACY_MTIME, mtime))
            LegalStore(path)                    # bảo đảm schema (kho rỗng nếu không có kho cũ)
            self._insert(sid, None, "building", "bootstrap", "system")
            now = self.now()
            self._set_status(sid, "published", published_at=now)
            self._write_pointer(sid)

    # --- đọc ---------------------------------------------------------------------------

    def current(self) -> Snapshot:
        return self.get(_retry_on_permission(lambda: self._pointer.read_text(encoding="utf-8")).strip())

    def get(self, snapshot_id: str) -> Snapshot:
        with self._db() as c:
            row = c.execute(f"SELECT {_SELECT} FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return self._row(row)

    def list(self) -> list[Snapshot]:
        with self._db() as c:
            rows = c.execute(f"SELECT {_SELECT} FROM snapshots ORDER BY seq DESC").fetchall()
        return [self._row(r) for r in rows]

    def store(self, snapshot_id: str | None = None) -> LegalStore:
        """Kho của snapshot (mặc định: đang công bố). Không bao giờ tạo kho: snapshot đã dọn hoặc mất file ->
        `FileNotFoundError` (thay vì một kho rỗng khiến chat trả lời "không có dữ liệu"); id lạ -> `KeyError`."""
        snap = self.get(snapshot_id) if snapshot_id is not None else self.current()
        with self._db() as c:
            removed = c.execute("SELECT removed_at FROM snapshots WHERE snapshot_id=?", (snap.snapshot_id,)).fetchone()
        if removed and removed[0]:
            raise FileNotFoundError(f"Snapshot {snap.snapshot_id} đã được dọn lúc {removed[0]}")
        if not snap.catalog_path.is_file():
            raise FileNotFoundError(f"Snapshot {snap.snapshot_id} không còn file kho: {snap.catalog_path}")
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
            return self._write_locked(reason, actor, fn, progress)
        finally:
            lock.release()

    def _write_locked(self, reason: str, actor: str, fn: Callable[[LegalService], T],
                      progress: Callable[[str, int, int], None] | None) -> WriteResult[T]:
        """Thân của `write`: người gọi đang giữ khoá ghi."""
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
                self._discard(sid)              # lỗi nghiệp vụ: không giữ staging
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

    # --- kho cũ ------------------------------------------------------------------------

    def _legacy_text_fixes(self, store: LegalStore) -> tuple[dict[str, str], list[str]]:
        """(document_key -> text đúng checksum, các văn bản lệch checksum không khôi phục được)."""
        fixes: dict[str, str] = {}
        broken: list[str] = []
        for d in store.documents():
            path = Path(d.raw_text_path)
            try:
                if not path.is_file() or _sha256(path) == d.raw_checksum:
                    continue                    # thiếu file: validate báo; khớp: không cần chuyển
                text = _legacy_text_fix(path, d.raw_checksum)
            except (OSError, UnicodeDecodeError):
                text = None
            if text is None:
                broken.append(f"{d.document_key} ({path})")
            else:
                fixes[d.document_key] = text
        return fixes, broken

    def _migrate_legacy_text(self) -> Snapshot | None:
        """Kho crawl cũ: file text ghi `text + "\\n"` ở chế độ text (CRLF trên Windows) nhưng checksum tính trên `text`
        -> mọi lần ghi sau đều lỗi validate. Ghi lại text đúng checksum bằng `rawfiles.write_text` (file mới, đánh địa
        chỉ theo nội dung; file cũ giữ nguyên) rồi công bố snapshot `migration` trỏ tới file mới, qua đúng luồng
        staging -> build_all -> validate -> publish. Không sửa snapshot đã công bố tại chỗ. Idempotent: không còn file
        lệch -> không làm gì. Còn file lệch không khôi phục được -> log lỗi, không chuyển (validate sẽ báo)."""
        try:
            fixes, broken = self._legacy_text_fixes(self.store())
        except Exception:                       # noqa: BLE001 - khởi tạo không được hỏng vì chuyển đổi
            log.exception("Không kiểm tra được file text của snapshot đang công bố")
            return None
        if broken:
            log.error("File text lệch checksum, KHÔNG tự sửa được (mọi lần ghi kho sẽ lỗi kiểm tra cho tới khi nạp lại "
                      "các văn bản này): %s", "; ".join(broken))
            return None
        if not fixes:
            return None
        lock = FileLock(self._lock_path, timeout=max(self.lock_timeout, _BOOTSTRAP_LOCK_TIMEOUT))
        try:
            lock.acquire()
        except Timeout:
            log.warning("Đang có lần ghi kho khác: hoãn chuyển đổi file text kho crawl cũ tới lần khởi động sau")
            return None
        try:
            fixes, broken = self._legacy_text_fixes(self.store())    # kiểm lại dưới khoá (tiến trình khác vừa làm?)
            if broken or not fixes:
                return None
            raw_dir = self.legal_dir / "raw"

            def apply(svc: LegalService) -> list[str]:
                for key, text in fixes.items():
                    doc = svc.store.document(key)
                    path, checksum = write_text(raw_dir, key, text)
                    if checksum != doc.raw_checksum:
                        raise RuntimeError(f"{key}: checksum sau chuyển đổi không khớp")
                    svc.store.upsert_document(replace(doc, raw_text_path=str(path)))
                return sorted(fixes)

            res = self._write_locked("migration", "system", apply, None)
            log.warning("Đã chuyển đổi file text của %d văn bản kho crawl cũ (snapshot %s): %s",
                        len(res.value), res.snapshot.snapshot_id, ", ".join(res.value))
            return res.snapshot
        except Exception:                       # noqa: BLE001
            log.exception("Chuyển đổi file text kho crawl cũ lỗi; snapshot đang công bố không đổi")
            return None
        finally:
            lock.release()

    def _meta(self, key: str) -> str | None:
        with self._db() as c:
            row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def legacy_catalog_warning(self) -> str | None:
        """Kho cũ `legal_dir/catalog.sqlite` có văn bản mà kho có phiên bản chưa nhập (kho cũ được ghi sau lần
        bootstrap, hoặc bootstrap rỗng trong khi kho cũ có dữ liệu). Không tự nhập: trả lời nhắn cho người dùng."""
        legacy = self.legal_dir / "catalog.sqlite"
        if not legacy.is_file():
            return None
        n = _count_documents(legacy)
        if not n:
            return None
        mtime = legacy.stat().st_mtime_ns
        recorded = self._meta(_LEGACY_MTIME)
        if recorded is not None:                # bootstrap đã ghi mtime kho cũ lúc sao chép
            changed = recorded == "" or mtime > int(recorded)
        else:                                   # index của phiên bản code trước: so với thời điểm bootstrap
            with self._db() as c:
                row = c.execute("SELECT created_at FROM snapshots WHERE reason='bootstrap' ORDER BY seq "
                                "LIMIT 1").fetchone()
            changed = row is None or mtime / 1e9 > datetime.fromisoformat(row[0]).timestamp()
        if not changed:
            try:
                cur = self.current()
                changed = cur.reason == "bootstrap" and not LegalStore(cur.catalog_path).documents()
            except Exception:                   # noqa: BLE001
                changed = False
        if not changed:
            return None
        return (f"Kho luật cũ ({legacy}) có {n} văn bản và đã được ghi sau khi kho luật có phiên bản được khởi tạo; "
                f"các thay đổi đó KHÔNG có trong kho đang dùng (chat, /review, upload). Hãy nạp lại các văn bản cần "
                f"thiết bằng lệnh `python -m rag.legal crawl` hoặc trang Upload → \"Văn bản pháp luật\", rồi đổi tên "
                f"hoặc chuyển file catalog.sqlite cũ đi chỗ khác để tắt cảnh báo này.")

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
