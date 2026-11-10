import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.index.embedder import HashEmbedder
from rag.index.vector_index import VectorIndex
from rag.legal.keys import document_key
from rag.legal.models import LegalDocument
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager
from rag.legal.store import LegalStore
from rag.schema import Chunk
from rag.temporal.index import VersionedIndex

UI = Path(__file__).resolve().parents[1] / "ui"
SRC = Path(__file__).resolve().parents[1] / "src"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
from legal_runtime import LegalRuntime, RuntimeHolder, WriteWorker  # noqa: E402

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def law_text(number: str, title: str, year: int) -> str:
    return (f"Luật số: {number}\nLUẬT\n{title.upper()}\n"
            f"Điều 1. Phạm vi\nLuật này quy định về {title.lower()}.\n"
            f"Điều 2. Đối tượng\nLuật này áp dụng cho mọi tổ chức.\n"
            f"Điều 3. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 8 năm {year}.\n")


def _doc(key, number, title, issued, path, checksum):
    return LegalDocument(key, "1", title, "Luật", number, "Quốc hội", issued, None, None, None, False, str(path),
                         checksum, NOW)


def law_adder(number: str, title: str, year: int):
    key = document_key("Luật", number)

    def fn(svc: LegalService) -> str:
        raw = svc.store.path.parents[2] / "raw"     # legal_dir/snapshots/<id>/catalog.sqlite -> legal_dir/raw
        path, checksum = write_text(raw, key, law_text(number, title, year))
        svc.store.upsert_document(_doc(key, number, title, date(year, 1, 1), path, checksum))
        return key
    return fn


add_law = law_adder("98/2025/QH15", "Kiểm chứng", 2025)
add_law_a = law_adder("97/2025/QH15", "Thử A", 2025)
add_law_b = law_adder("96/2025/QH15", "Thử B", 2025)


def add_law_n(i: int):
    return law_adder(f"{10 + i}/2025/QH15", f"Thử số {i}", 2025)


def add_law_that_breaks_build(svc: LegalService) -> None:
    key = document_key("Luật", "95/2025/QH15")
    svc.store.upsert_document(_doc(key, "95/2025/QH15", "Luật hỏng", date(2025, 1, 1),
                                   svc.store.path.parent / "missing.txt", "0" * 64))


def seed_legacy(legal_dir: Path) -> None:
    key = document_key("Luật", "99/2024/QH15")
    path, checksum = write_text(legal_dir / "raw", key, law_text("99/2024/QH15", "Thử nghiệm", 2024))
    store = LegalStore(legal_dir / "catalog.sqlite")
    store.upsert_document(_doc(key, "99/2024/QH15", "Luật thử nghiệm", date(2024, 1, 1), path, checksum))
    LegalService(store, now=lambda: NOW).build_all()


class Env:
    def __init__(self, legal_dir: Path) -> None:
        self.legal_dir = legal_dir
        self._fail_next = False
        self._slow = 0.0
        self.index_calls: list[str] = []
        self.done: list[tuple[str, str]] = []
        self.snapshots = SnapshotManager(legal_dir)
        self.holder = RuntimeHolder(self.snapshots, self.make_runtime)
        self.worker = WriteWorker(self.snapshots, self.holder, make_runtime=self.make_runtime,
                                  on_upload_done=lambda job: self.done.append((job.job_id, job.state)))

    def fail_next_index(self) -> None:
        self._fail_next = True

    def slow_index(self, seconds: float) -> None:
        self._slow = seconds

    def make_runtime(self, snapshot_id: str) -> LegalRuntime:
        self.index_calls.append(snapshot_id)
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("index boom")
        time.sleep(self._slow)
        svc = self.snapshots.service(snapshot_id)
        index = VersionedIndex(svc.store, snapshot_id=snapshot_id)
        index.build()
        return LegalRuntime(snapshot_id, svc, index, qa=object())


@pytest.fixture
def env_factory(tmp_path):
    def make(*, crash_during_build: bool = False, reuse: Env | None = None) -> Env:
        if reuse is not None:
            return Env(reuse.legal_dir)
        legal_dir = tmp_path / "legal"
        legal_dir.mkdir()
        seed_legacy(legal_dir)
        env = Env(legal_dir)
        if crash_during_build:          # tiến trình chết thật giữa lúc dựng staging
            script = ("import os, sys\nfrom pathlib import Path\nfrom rag.legal.snapshots import SnapshotManager\n"
                      "SnapshotManager(Path(sys.argv[1])).write('upload:crash', 'An', lambda svc: os._exit(3))\n")
            proc = subprocess.run([sys.executable, "-c", script, str(legal_dir)],
                                  env={**os.environ, "PYTHONPATH": str(SRC)}, timeout=60)
            assert proc.returncode == 3
            assert env.snapshots.list()[0].status == "building"
        return env
    return make


@pytest.fixture
def env(env_factory):
    return env_factory()


# --- VersionedIndex gắn snapshot -------------------------------------------------------------

def test_versioned_index_shares_dense_and_records_snapshot(env):
    first = env.snapshots.current().snapshot_id
    second = env.snapshots.write("cli:build", "t", add_law).snapshot.snapshot_id
    dense = VectorIndex(HashEmbedder(dim=64))
    old = VersionedIndex(env.snapshots.store(first), dense=dense, snapshot_id=first)
    new = VersionedIndex(env.snapshots.store(second), dense=dense, snapshot_id=second)
    old.build()
    n_old = len(dense)
    new.build()
    assert old.snapshot_id == first and new.snapshot_id == second
    assert old.has_dense and new.has_dense and len(dense) > n_old       # cùng một vector store, chỉ thêm
    key2 = document_key("Luật", "98/2025/QH15")
    hits_old = old.search("kiểm chứng", date(2025, 9, 1), date(2025, 9, 1), k=50)
    hits_new = new.search("kiểm chứng", date(2025, 9, 1), date(2025, 9, 1), k=50)
    assert hits_old and all(c.document_key != key2 for c, _ in hits_old)  # không trộn chunk snapshot khác
    assert any(c.document_key == key2 for c, _ in hits_new)


def test_versioned_index_defaults_unchanged(env):
    idx = VersionedIndex(env.snapshots.store())
    assert idx.snapshot_id is None
    idx.build()
    assert not idx.has_dense


# --- Brief ----------------------------------------------------------------------------------

def test_publish_then_switch_after_index(env):
    old = env.holder.get().snapshot_id
    job = env.worker.submit("upload", "u1", "An", add_law)
    assert env.worker.wait_idle(10)
    j = env.worker.job(job.job_id)
    assert j.state == "done" and env.holder.get().snapshot_id != old
    assert env.holder.get().snapshot_id == j.snapshot_id == env.snapshots.current().snapshot_id
    assert env.holder.get().index.snapshot_id == j.snapshot_id
    assert j.progress and j.progress["stage"] == "build"
    assert env.snapshots.get(j.snapshot_id).reason == "upload:u1" and env.snapshots.get(j.snapshot_id).actor == "An"
    assert env.done == [(job.job_id, "done")]


def test_build_failure_keeps_runtime(env):
    old = env.holder.get()
    job = env.worker.submit("upload", "u1", "An", add_law_that_breaks_build)
    env.worker.wait_idle(10)
    j = env.worker.job(job.job_id)
    assert j.state == "failed" and env.holder.get() is old
    assert j.error and env.snapshots.current().snapshot_id == old.snapshot_id
    assert env.done == [(job.job_id, "failed")]


def test_index_failure_keeps_pair(env):
    env.fail_next_index()
    old = env.holder.get()
    job = env.worker.submit("upload", "u1", "An", add_law)
    env.worker.wait_idle(10)
    j = env.worker.job(job.job_id)
    assert j.state == "index_failed" and env.snapshots.current().snapshot_id == j.snapshot_id
    assert env.holder.get() is old and old.index.snapshot_id == old.snapshot_id
    assert "index boom" in j.error


def test_reindex_after_index_failure_switches(env):
    env.fail_next_index()
    job = env.worker.submit("upload", "u1", "An", add_law)
    env.worker.wait_idle(10)
    re = env.worker.reindex()
    assert re.kind == "reindex" and re.state == "queued"
    assert env.worker.wait_idle(10)
    r = env.worker.job(re.job_id)
    assert r.state == "done" and r.snapshot_id == env.worker.job(job.job_id).snapshot_id
    assert env.holder.get().snapshot_id == r.snapshot_id


def test_two_uploads_while_indexing_never_mix_or_go_back(env):
    env.slow_index(seconds=0.5)
    a = env.worker.submit("upload", "u1", "An", add_law_a)
    b = env.worker.submit("upload", "u2", "Bình", add_law_b)
    seen: list[str] = []
    violations: list[str] = []
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            rt = env.holder.get()
            if rt is None or rt.index.snapshot_id != rt.snapshot_id:
                violations.append(f"cặp lệch: {rt and rt.snapshot_id} / {rt and rt.index.snapshot_id}")
            elif not seen or seen[-1] != rt.snapshot_id:
                seen.append(rt.snapshot_id)
            time.sleep(0.005)

    t = threading.Thread(target=watch)
    t.start()
    try:
        assert env.worker.wait_idle(20)
    finally:
        stop.set()
        t.join()
    assert violations == []
    assert len(seen) >= 2
    rt = env.holder.get()
    assert rt.snapshot_id == env.worker.job(b.job_id).snapshot_id and rt.index.snapshot_id == rt.snapshot_id
    order = [s.snapshot_id for s in reversed(env.snapshots.list())]       # cũ -> mới
    assert [order.index(s) for s in seen] == sorted(order.index(s) for s in seen)   # không bao giờ lùi
    assert env.worker.job(a.job_id).state == "done"


def test_lease_survives_switch_and_cleanup(env):
    with env.holder.lease() as rt:
        assert rt.leases == 1
        for i in range(5):
            env.worker.submit("upload", f"u{i}", "An", add_law_n(i))
        env.worker.wait_idle(30)
        assert rt.snapshot_id in env.holder.in_use()
        assert rt.service.store.documents() is not None          # file snapshot còn đọc được
        assert env.holder.get() is not rt
    assert rt.leases == 0
    assert env.holder.in_use() == {env.holder.get().snapshot_id}
    env.worker.submit("upload", "u9", "An", add_law_n(9))
    env.worker.wait_idle(30)
    with pytest.raises(FileNotFoundError):                         # hết lease -> được dọn
        env.snapshots.store(rt.snapshot_id)


def test_restart_marks_interrupted(env_factory):
    env = env_factory(crash_during_build=True)
    env2 = env_factory(reuse=env)
    assert env2.snapshots.list()[0].status == "failed"


# --- Thêm ------------------------------------------------------------------------------------

def test_offer_never_goes_backwards(env):
    first = env.holder.get()
    old_rt = env.make_runtime(first.snapshot_id)
    env.worker.submit("upload", "u1", "An", add_law)
    env.worker.wait_idle(10)
    newer = env.holder.get()
    assert newer is not first
    assert env.holder.offer(old_rt) is False                      # cũ hơn
    assert env.holder.offer(env.make_runtime(newer.snapshot_id)) is False   # bằng
    assert env.holder.get() is newer


def test_offer_rejects_mismatched_pair(env):
    sid = env.snapshots.write("cli:build", "t", add_law).snapshot.snapshot_id
    rt = env.make_runtime(sid)
    rt.index.snapshot_id = env.holder.get().snapshot_id          # chỉ mục của snapshot khác
    assert env.holder.offer(rt) is False


def test_worker_survives_errors_and_runs_fifo(env):
    def boom(svc):
        raise RuntimeError("fn boom")
    jobs = [env.worker.submit("review", "r1", "An", lambda svc: (_ for _ in ()).throw(ValueError("bad"))),
            env.worker.submit("review", "r2", "An", boom),
            env.worker.submit("upload", "u1", "An", add_law)]
    assert env.worker.wait_idle(10)
    states = [env.worker.job(j.job_id).state for j in jobs]
    assert states == ["failed", "failed", "done"]
    assert "bad" in env.worker.job(jobs[0].job_id).error
    assert [j.job_id for j in env.worker.jobs()] == [j.job_id for j in jobs]
    assert env.done == [(jobs[2].job_id, "done")]                  # on_upload_done chỉ cho upload
    with pytest.raises(KeyError):
        env.worker.job("nope")


def test_on_upload_done_error_does_not_kill_worker(env):
    env.worker._on_upload_done = lambda job: (_ for _ in ()).throw(RuntimeError("cb"))
    a = env.worker.submit("upload", "u1", "An", add_law_a)
    b = env.worker.submit("upload", "u2", "An", add_law_b)
    assert env.worker.wait_idle(10)
    assert env.worker.job(a.job_id).state == "done" and env.worker.job(b.job_id).state == "done"


def test_unexpected_error_gives_terminal_state_to_callback(env):
    def broken_index(job):
        raise RuntimeError("trước try của _index")
    env.worker._index = broken_index
    job = env.worker.submit("upload", "u1", "An", add_law)
    assert env.worker.wait_idle(10)
    assert env.done == [(job.job_id, "failed")]
    assert "trước try" in env.worker.job(job.job_id).error


def test_wait_idle_from_callback_is_refused_not_deadlocked(env):
    errors = []

    def cb(job):
        try:
            env.worker.wait_idle(5)
        except RuntimeError as exc:
            errors.append(exc)
    env.worker._on_upload_done = cb
    start = time.monotonic()
    env.worker.submit("upload", "u1", "An", add_law)
    assert env.worker.wait_idle(10) and time.monotonic() - start < 4
    assert len(errors) == 1


def test_shared_dense_search_while_other_index_builds(env):
    first = env.snapshots.current().snapshot_id
    dense = VectorIndex(HashEmbedder(dim=16))
    old = VersionedIndex(env.snapshots.store(first), dense=dense, snapshot_id=first)
    old.build()
    errors: list[BaseException] = []
    stop = threading.Event()

    def search_loop():
        while not stop.is_set():
            try:
                old.search("phạm vi", date(2025, 9, 1), date(2025, 9, 1), k=5)
            except BaseException as exc:    # noqa: BLE001
                errors.append(exc)
                return

    threads = [threading.Thread(target=search_loop) for _ in range(3)]
    for t in threads:
        t.start()
    try:
        for i in range(400):                # nhiều lần thêm chunk mới vào vector store dùng chung
            dense.build([Chunk(f"x{i}-{j}", "d", "t", None, None, "s", f"nội dung {i} {j}") for j in range(10)])
    finally:
        stop.set()
        for t in threads:
            t.join()
    assert errors == []
    assert len(dense) >= 400 * 10


def test_holder_without_runtime_when_initial_index_fails(tmp_path):
    seed_legacy(tmp_path)
    snaps = SnapshotManager(tmp_path)

    def broken(sid):
        raise RuntimeError("no index")
    holder = RuntimeHolder(snaps, broken)
    assert holder.get() is None and holder.in_use() == set()
    with holder.lease() as rt:
        assert rt is None
