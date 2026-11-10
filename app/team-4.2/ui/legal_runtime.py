"""Cặp (snapshot kho luật, chỉ mục) mà chat dùng, và hàng đợi ghi duy nhất vào kho.

- `LegalRuntime`: một cặp dựng từ CÙNG một snapshot (service + chỉ mục + TemporalQA).
- `RuntimeHolder`: giữ runtime hiện tại; đổi sang runtime mới bằng một phép gán duy nhất, chỉ khi snapshot của nó mới
  hơn (theo `published_at`) — không bao giờ lùi. Mỗi request chat `lease()` một runtime và dùng nó đến hết; snapshot
  của runtime còn lease không bị dọn.
- `WriteWorker`: một luồng daemon chạy FIFO mọi lần ghi (upload / quyết định duyệt / dựng lại chỉ mục):
  `snapshots.write` (staging -> kiểm tra -> công bố) -> dựng chỉ mục cho snapshot vừa công bố -> `holder.offer`.
  Chỉ mục lỗi -> `index_failed`: kho đã công bố nhưng chat giữ cặp cũ.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Literal

from rag.legal.service import LegalService
from rag.legal.snapshots import Snapshot, SnapshotManager
from rag.temporal.index import VersionedIndex
from rag.temporal.qa import TemporalQA

log = logging.getLogger(__name__)

JobState = Literal["queued", "building", "validating", "publishing", "indexing", "done", "failed", "index_failed"]
JobKind = Literal["upload", "review", "reindex"]
_TERMINAL = ("done", "failed", "index_failed")


@dataclass(eq=False)
class LegalRuntime:
    snapshot_id: str
    service: LegalService
    index: VersionedIndex
    qa: TemporalQA
    leases: int = 0


class RuntimeHolder:
    """Khởi tạo: dựng runtime cho snapshot đang công bố (lỗi -> `get()` trả None cho tới khi có runtime hợp lệ)."""

    def __init__(self, snapshots: SnapshotManager, make_runtime: Callable[[str], LegalRuntime]) -> None:
        self._snapshots = snapshots
        self._make_runtime = make_runtime
        self._lock = threading.Lock()          # bảo vệ _current/_current_snap/leases/_leased
        self._offer_lock = threading.Lock()    # mỗi lần chỉ một offer so sánh + gán
        self._current: LegalRuntime | None = None
        self._current_snap: Snapshot | None = None
        self._leased: dict[int, LegalRuntime] = {}     # runtime còn lease > 0 (kể cả đã bị thay)
        try:
            self.offer(make_runtime(snapshots.current().snapshot_id))
        except Exception:                      # noqa: BLE001 - chat sẽ báo chưa sẵn sàng; "dựng lại chỉ mục" sửa được
            log.exception("Không dựng được chỉ mục cho snapshot đang công bố")

    def get(self) -> LegalRuntime | None:
        return self._current

    @contextmanager
    def lease(self) -> Iterator[LegalRuntime | None]:
        with self._lock:
            rt = self._current
            if rt is not None:
                rt.leases += 1
                self._leased[id(rt)] = rt
        try:
            yield rt
        finally:
            if rt is not None:
                with self._lock:
                    rt.leases -= 1
                    if rt.leases <= 0:
                        self._leased.pop(id(rt), None)

    def _newer(self, cand: Snapshot, cur: Snapshot) -> bool:
        if cand.published_at != cur.published_at:
            return cand.published_at > cur.published_at
        # cùng thời điểm (độ phân giải đồng hồ): thứ tự tạo trong index; các lần ghi nối tiếp nhau dưới khoá ghi
        order = [s.snapshot_id for s in self._snapshots.list()]
        return order.index(cand.snapshot_id) < order.index(cur.snapshot_id)

    def offer(self, rt: LegalRuntime) -> bool:
        """Nhận `rt` làm runtime hiện tại nếu cặp nhất quán và snapshot của nó công bố sau snapshot hiện tại."""
        if getattr(rt.index, "snapshot_id", None) != rt.snapshot_id:
            log.error("Bỏ runtime: chỉ mục %s không khớp snapshot %s", getattr(rt.index, "snapshot_id", None),
                      rt.snapshot_id)
            return False
        with self._offer_lock:
            try:
                cand = self._snapshots.get(rt.snapshot_id)
            except KeyError:
                return False
            if cand.status != "published" or cand.published_at is None:
                return False
            cur, cur_snap = self._current, self._current_snap
            if cur is not None and cur_snap is not None:
                if cur.snapshot_id == rt.snapshot_id or not self._newer(cand, cur_snap):
                    return False
            with self._lock:
                self._current_snap = cand
                self._current = rt             # phép gán duy nhất mà chat nhìn thấy
            return True

    def in_use(self) -> set[str]:
        with self._lock:
            ids = {rt.snapshot_id for rt in self._leased.values()}
            if self._current is not None:
                ids.add(self._current.snapshot_id)
        return ids


@dataclass
class Job:
    job_id: str
    kind: JobKind
    ref: str                       # upload_id | review_id
    actor: str
    state: JobState
    progress: dict | None
    snapshot_id: str | None
    error: str | None
    result: dict | None            # kết quả cho UI (Task 8 định nghĩa nội dung)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class WriteWorker:
    """Một luồng daemon, FIFO. Khởi tạo đánh dấu `failed` các staging còn sót do tiến trình trước chết giữa chừng.
    `job()`/`jobs()` trả bản sao (đọc nhất quán, không bị luồng ghi sửa dở)."""

    def __init__(self, snapshots: SnapshotManager, holder: RuntimeHolder, *,
                 make_runtime: Callable[[str], LegalRuntime],
                 on_upload_done: Callable[[Job], None] | None = None) -> None:
        self._snapshots = snapshots
        self._holder = holder
        self._make_runtime = make_runtime
        self._on_upload_done = on_upload_done
        self._cond = threading.Condition()
        self._jobs: dict[str, Job] = {}
        self._queue: deque[tuple[Job, Callable[[LegalService], Any] | None]] = deque()
        self._busy = False
        try:
            interrupted = snapshots.mark_interrupted()
            if interrupted:
                log.warning("Snapshot bị dừng giữa chừng -> failed: %s", interrupted)
        except Exception:                      # noqa: BLE001
            log.exception("Không đánh dấu được snapshot bị dừng giữa chừng")
        self._thread = threading.Thread(target=self._run, name="legal-write-worker", daemon=True)
        self._thread.start()

    # --- API ---------------------------------------------------------------------------

    def submit(self, kind: str, ref: str, actor: str, fn: Callable[[LegalService], Any]) -> Job:
        if kind not in ("upload", "review"):
            raise ValueError(f"Loại việc ghi không hợp lệ: {kind}")
        return self._enqueue(kind, ref, actor, fn)

    def reindex(self) -> Job:
        """Dựng chỉ mục cho snapshot published mới nhất (vd. sau `index_failed`)."""
        return self._enqueue("reindex", "", "system", None)

    def job(self, job_id: str) -> Job:
        with self._cond:
            return replace(self._jobs[job_id])

    def jobs(self) -> list[Job]:
        with self._cond:
            return [replace(j) for j in self._jobs.values()]

    def wait_idle(self, timeout: float) -> bool:
        if threading.current_thread() is self._thread:
            raise RuntimeError("wait_idle không được gọi từ luồng ghi (vd. trong on_upload_done): sẽ tự chờ chính nó")
        with self._cond:
            return self._cond.wait_for(lambda: not self._queue and not self._busy, timeout)

    # --- nội bộ ------------------------------------------------------------------------

    def _enqueue(self, kind: str, ref: str, actor: str, fn: Callable[[LegalService], Any] | None) -> Job:
        job = Job(uuid.uuid4().hex, kind, ref, actor, "queued", None, None, None, None)  # type: ignore[arg-type]
        with self._cond:
            self._jobs[job.job_id] = job
            self._queue.append((job, fn))
            self._cond.notify_all()
            return replace(job)

    def _update(self, job: Job, **fields: Any) -> None:
        with self._cond:
            for name, value in fields.items():
                setattr(job, name, value)

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: bool(self._queue))
                job, fn = self._queue.popleft()
                self._busy = True
            try:
                self._process(job, fn)
            except BaseException as exc:       # noqa: BLE001 - luồng ghi không bao giờ chết
                log.exception("Việc ghi %s lỗi ngoài dự kiến", job.job_id)
                if job.state not in _TERMINAL:
                    self._update(job, state="failed", error=_describe(exc))
            finally:
                if job.state not in _TERMINAL:     # phòng hờ: callback chỉ thấy trạng thái cuối
                    self._update(job, state="failed", error=job.error or "kết thúc không rõ trạng thái")
                self._after(job)
                with self._cond:
                    self._busy = False
                    self._cond.notify_all()

    def _process(self, job: Job, fn: Callable[[LegalService], Any] | None) -> None:
        if job.kind == "reindex":
            self._update(job, snapshot_id=self._snapshots.current().snapshot_id)
        else:
            self._write(job, fn)
        if job.state != "failed":
            self._index(job)

    def _after(self, job: Job) -> None:
        """Chạy trên luồng ghi khi việc đã ở trạng thái cuối, TRƯỚC khi worker rảnh (nên `wait_idle` trả True nghĩa
        là callback đã chạy xong). Callback không được gọi `wait_idle` (bị chặn bằng RuntimeError)."""
        if job.kind == "upload" and self._on_upload_done is not None:
            try:
                self._on_upload_done(replace(job))
            except BaseException:              # noqa: BLE001
                log.exception("on_upload_done lỗi cho việc %s", job.job_id)
        try:
            self._snapshots.cleanup(in_use=self._holder.in_use())
        except BaseException:                  # noqa: BLE001
            log.exception("Dọn snapshot cũ lỗi")

    def _write(self, job: Job, fn: Callable[[LegalService], Any] | None) -> None:
        assert fn is not None
        self._update(job, state="building")

        def progress(stage: str, i: int, n: int) -> None:
            fields: dict[str, Any] = {"progress": {"stage": stage, "done": i, "total": n}}
            if stage == "build" and i >= n:
                fields["state"] = "validating"     # dựng xong luật cuối -> SnapshotManager kiểm tra rồi công bố
            self._update(job, **fields)

        try:
            res = self._snapshots.write(f"{job.kind}:{job.ref}", job.actor, fn, progress=progress)
        except BaseException as exc:           # noqa: BLE001
            self._update(job, state="failed", error=_describe(exc))
            return
        # SnapshotManager.write kiểm tra + công bố trong một lời gọi, không báo riêng giai đoạn "publishing"
        self._update(job, snapshot_id=res.snapshot.snapshot_id, result={"value": res.value})

    def _index(self, job: Job) -> None:
        sid = job.snapshot_id
        assert sid is not None
        self._update(job, state="indexing")
        try:
            rt = self._make_runtime(sid)
            if rt.snapshot_id != sid or getattr(rt.index, "snapshot_id", None) != sid:
                raise RuntimeError(f"Runtime dựng ra không khớp snapshot {sid}")
        except BaseException as exc:           # noqa: BLE001 - kho đã công bố; chat giữ cặp cũ
            self._update(job, state="index_failed", error=_describe(exc))
            return
        if not self._holder.offer(rt):
            log.info("Chỉ mục snapshot %s không được dùng: chat đang dùng snapshot mới hơn", sid)
        self._update(job, state="done")


__all__ = ["Job", "JobState", "LegalRuntime", "RuntimeHolder", "WriteWorker"]
