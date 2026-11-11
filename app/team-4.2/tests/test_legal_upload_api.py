"""API upload văn bản pháp luật + duyệt qua hàng đợi ghi + CLI qua snapshot (spec §4.3–4.4, Task 8)."""

import sys
import threading
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from filelock import FileLock
from starlette.testclient import TestClient

from rag.config import Settings
from rag.legal.models import ReviewItem
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager
from rag.legal.store import LegalStore
from tests.test_legal_upload_flow import (DETAIL_43, HOUSING, KEY_UPLOADED, LAND, NOW, UPLOADED_V1, UPLOADED_V2,
                                          FakeVbplClient, _doc, _fixture_text, _normalized)

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import legal_api  # noqa: E402
import server  # noqa: E402

import rag.legal.__main__ as cli  # noqa: E402
from rag.legal.__main__ import main  # noqa: E402

TXT_43 = _fixture_text("luat_43_2024_QH15.txt")
TXT_UPLOADED_V2 = UPLOADED_V2
TXT_UPLOADED_V3 = UPLOADED_V1.replace("thử nghiệm.", "thử nghiệm, bản ba.")
RID = "discovery:manual-check"
TERMINAL = ("done", "failed", "index_failed")


# --- dựng môi trường --------------------------------------------------------------------------------


def seed(legal_dir: Path, *, review: bool = False) -> None:
    """Kho cũ (legal_dir/catalog.sqlite) -> SnapshotManager của server khởi tạo snapshot đầu từ nó."""
    files = legal_dir.parent / "files"
    files.mkdir(parents=True, exist_ok=True)
    land = files / "31.txt"
    land.write_text(_fixture_text("luat_31_2024_QH15.txt"), encoding="utf-8")
    raw = legal_dir / "raw"
    store = LegalStore(legal_dir / "catalog.sqlite")
    path, checksum = write_text(raw, LAND, _normalized(str(land)))
    store.upsert_document(_doc(LAND, "31/2024/QH15", "Luật Đất đai số 31/2024/QH15", date(2024, 1, 18),
                               path, checksum))
    path, checksum = write_text(raw, HOUSING, _fixture_text("luat_27_2023_QH15.txt"))
    store.upsert_document(_doc(HOUSING, "27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", date(2023, 11, 27),
                               path, checksum))
    path, checksum = write_text(raw, KEY_UPLOADED, UPLOADED_V1)
    store.upsert_document(_doc(KEY_UPLOADED, "99/2024/QH15", "Luật Thử nghiệm", date(2024, 1, 10), path,
                               checksum, text_source="file", content_verified={"by": "Bình", "at": NOW.isoformat()},
                               source_verified=False))
    LegalService(store, now=lambda: NOW).build_all()
    if review:      # mục duyệt không gắn thao tác: các lần dựng lại kho không tự đóng nó
        store.add_review_item(ReviewItem(RID, "discovery", LAND, None, None, ("discovery.manual_check",), "open", NOW,
                                         {}))


def _client(tmp_path, monkeypatch, *, review=False):
    seed(tmp_path / "legal", review=review)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LEGAL_DENSE", "0")
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(server, "get_pipeline", lambda: (NS(llm=None, retriever=None), settings))
    fake = FakeVbplClient({"171234": DETAIL_43})
    monkeypatch.setattr(legal_api.CONFIG, "client_factory", lambda: fake)
    # không gọi Settings.load() (nó nạp .env thật vào os.environ, làm bẩn các test sau)
    monkeypatch.setattr(legal_api.CONFIG, "legal_dir", lambda: tmp_path / "legal")
    monkeypatch.setattr(legal_api.CONFIG, "ocr_factory", None)
    legal_api.reset()
    return TestClient(server.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    yield _client(tmp_path, monkeypatch)
    legal_api.reset()


@pytest.fixture
def client_with_open_review(tmp_path, monkeypatch):
    yield _client(tmp_path, monkeypatch, review=True)
    legal_api.reset()


@pytest.fixture
def slow_index(monkeypatch):
    """Chỉ mục của mọi snapshot mới chờ tới khi test mở cổng (snapshot đầu dựng ngay)."""
    from rag.temporal import wiring

    gate = threading.Event()
    real = wiring.make_versioned_index
    first: list[str] = []

    def slow(*args, snapshot_id=None, **kw):
        if first and snapshot_id != first[0]:
            assert gate.wait(30), "slow_index: test không mở cổng"
        first.append(snapshot_id)
        return real(*args, snapshot_id=snapshot_id, **kw)

    monkeypatch.setattr(wiring, "make_versioned_index", slow)
    yield gate
    gate.set()


@pytest.fixture
def slow_build(monkeypatch):
    """Lần ghi upload dừng ở giữa lúc dựng staging tới khi test mở cổng."""
    from rag.legal.upload.flow import UploadService

    gate = threading.Event()
    real = UploadService.apply_to

    def slow(self, svc, upload_id):
        assert gate.wait(30), "slow_build: test không mở cổng"
        return real(self, svc, upload_id)

    monkeypatch.setattr(UploadService, "apply_to", slow)
    yield gate
    gate.set()


@pytest.fixture
def held_lock(tmp_path, monkeypatch):
    legal = tmp_path / "legal"
    SnapshotManager(legal)                       # khởi tạo snapshot đầu trước khi giữ khoá
    monkeypatch.setattr(cli, "_legal_dir", lambda: legal)
    lock = FileLock(legal / "write.lock")
    lock.acquire()
    yield lock
    lock.release()


# --- tiện ích HTTP -----------------------------------------------------------------------------------


def wait_job(client, job_id, state, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = client.get(f"/api/legal/jobs/{job_id}").json()
        if job["state"] in TERMINAL:
            assert job["state"] == state, job
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} chưa xong sau {timeout}s")


def wait_idle(client, timeout=180):
    assert legal_api.get_backend().worker.wait_idle(timeout)


def create(client, text, name="up.txt"):
    r = client.post("/api/legal/uploads", files={"file": (name, text.encode("utf-8"))})
    assert r.status_code == 201, r.text
    return r.json()


def upload_to_step3(client, text):
    d = create(client, text)
    uid = d["upload_id"]
    step = "replace" if d["duplicate"] else "confirm-text"
    assert client.post(f"/api/legal/uploads/{uid}/{step}", json={"by": "An"}).status_code == 200
    r = client.post(f"/api/legal/uploads/{uid}/confirm-understanding", json={"by": "An"})
    assert r.status_code == 200 and r.json()["state"] == "step3", r.text
    return uid


def submit(client, uid):
    r = client.post(f"/api/legal/uploads/{uid}/submit", json={"by": "An"})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def submit_upload(client, text):
    return submit(client, upload_to_step3(client, text))


# --- luồng upload -----------------------------------------------------------------------------------


def test_full_upload_flow_over_http(client):
    r = client.post("/api/legal/uploads", files={"file": ("43.txt", TXT_43.encode())}); uid = r.json()["upload_id"]
    assert client.post(f"/api/legal/uploads/{uid}/submit", json={"by": "An"}).status_code == 409   # nhảy bước
    client.post(f"/api/legal/uploads/{uid}/confirm-text", json={"by": "An"})
    client.post(f"/api/legal/uploads/{uid}/confirm-understanding", json={"by": "An"})
    job = client.post(f"/api/legal/uploads/{uid}/submit", json={"by": "An"}).json()["job_id"]
    wait_job(client, job, "done")
    d = client.get(f"/api/legal/uploads/{uid}").json()
    assert d["state"] == "published" and d["result"]["laws"]
    assert d["snapshot_id"] == legal_api.get_backend().snapshots.current().snapshot_id
    assert d["job"]["job_id"] == job and d["job"]["state"] == "done"
    laws = {law["document_key"]: law for law in d["result"]["laws"]}
    assert "luat:43/2024/QH15" in laws
    assert laws[LAND]["changed_provisions"] > 0 and laws[LAND]["review_url"] == f"/review?document={LAND}"
    assert set(laws[LAND]) == {"document_key", "title", "changed_provisions", "new_review_items", "review_url"}


def test_chat_uses_old_pair_until_index_ready(client, slow_index):
    before = server.get_temporal_qa().index.snapshot_id
    job = submit_upload(client, TXT_43)
    assert server.get_temporal_qa().index.snapshot_id == before        # đang dựng chỉ mục
    slow_index.set()
    wait_job(client, job, "done")
    assert server.get_temporal_qa().index.snapshot_id != before


def test_review_decision_is_queued(client_with_open_review):
    r = client_with_open_review.post(f"/api/legal/reviews/{RID}/decision",
                                     json={"action": "reject", "reviewer": "An", "note": "sai"})
    assert r.status_code == 202 and wait_job(client_with_open_review, r.json()["job_id"], "done")
    assert server.get_legal_service().store.review_item(RID).status == "resolved"


def test_review_decision_during_upload_build_is_not_lost(client_with_open_review, slow_build):
    job_u = submit_upload(client_with_open_review, TXT_43)
    job_r = client_with_open_review.post(f"/api/legal/reviews/{RID}/decision",
                                         json={"action": "reject", "reviewer": "An", "note": "sai"}).json()["job_id"]
    slow_build.set()
    wait_job(client_with_open_review, job_r, "done")
    assert server.get_legal_service().store.review_item(RID).status == "resolved"
    assert wait_job(client_with_open_review, job_u, "done")
    assert server.get_legal_service().store.document("luat:43/2024/QH15") is not None


def test_review_decision_prechecks(client_with_open_review):
    c = client_with_open_review
    body = {"action": "reject", "reviewer": "An", "note": "sai"}
    assert c.post(f"/api/legal/reviews/{RID}/decision", json={**body, "note": ""}).status_code == 400
    assert c.post("/api/legal/reviews/discovery:none/decision", json=body).status_code == 404
    wait_job(c, c.post(f"/api/legal/reviews/{RID}/decision", json=body).json()["job_id"], "done")
    assert c.post(f"/api/legal/reviews/{RID}/decision", json=body).status_code == 409


def test_concurrent_same_number_only_one_recorded(client):
    a, b = upload_to_step3(client, TXT_UPLOADED_V2), upload_to_step3(client, TXT_UPLOADED_V3)   # cùng số hiệu, bản trong kho là file
    ja, jb = submit(client, a), submit(client, b)
    wait_idle(client)
    states = {client.get(f"/api/legal/uploads/{a}").json()["state"], client.get(f"/api/legal/uploads/{b}").json()["state"]}
    assert states == {"published", "stale"}
    stale = a if client.get(f"/api/legal/uploads/{a}").json()["state"] == "stale" else b
    assert "Kho đã thay đổi" in client.get(f"/api/legal/uploads/{stale}").json()["error"]


# --- API phụ --------------------------------------------------------------------------------------


def test_list_hides_text_and_unknown_ids_404(client):
    uid = create(client, TXT_43, "43.txt")["upload_id"]
    rows = client.get("/api/legal/uploads").json()["uploads"]
    assert [r["upload_id"] for r in rows] == [uid] and "text" not in rows[0]
    assert client.get(f"/api/legal/uploads/{uid}").json()["text"]
    assert client.get("/api/legal/uploads/u20990101000000-abcdef").status_code == 404
    assert client.get("/api/legal/uploads/..%5Cx").status_code == 404
    assert client.post("/api/legal/uploads/u20990101000000-abcdef/cancel").status_code == 404
    assert client.get("/api/legal/jobs/nope").status_code == 404


def test_create_needs_file_or_url_and_bad_url_is_409(client):
    assert client.post("/api/legal/uploads", data={}).status_code == 400
    r = client.post("/api/legal/uploads", data={"url": "https://example.com/x"})
    assert r.status_code == 409 and "vbpl" in r.json()["error"]
    d = client.post("/api/legal/uploads", data={"url": "https://vbpl.vn/van-ban/chi-tiet/171234"}).json()
    assert d["origin"] == "url" and d["state"] == "step1"


def test_fields_and_relookup_return_preview(client):
    uid = create(client, TXT_43, "43.txt")["upload_id"]
    client.post(f"/api/legal/uploads/{uid}/confirm-text", json={"by": "An"})
    d = client.post(f"/api/legal/uploads/{uid}/fields", json={"values": {"issuer": "Quốc hội"}, "by": "An"}).json()
    assert d["fields"]["issuer"]["source"] == "user" and d["preview"]["kind"] == "amending"
    d = client.post(f"/api/legal/uploads/{uid}/relookup").json()
    assert d["preview"] is not None
    r = client.post(f"/api/legal/uploads/{uid}/fields", json={"values": {"bogus": "x"}, "by": "An"})
    assert r.status_code == 409


def test_cancel_and_retry_rules(client):
    uid = create(client, TXT_43, "43.txt")["upload_id"]
    assert client.post(f"/api/legal/uploads/{uid}/retry", json={"by": "An"}).status_code == 409   # chưa thất bại
    assert client.post(f"/api/legal/uploads/{uid}/cancel").json()["state"] == "cancelled"
    assert client.post(f"/api/legal/uploads/{uid}/confirm-text", json={"by": "An"}).status_code == 409


def test_failed_upload_can_be_retried(client, monkeypatch):
    from rag.legal.upload.flow import UploadService

    real = UploadService.apply_to
    calls = []

    def flaky(self, svc, upload_id):
        calls.append(upload_id)
        if len(calls) == 1:
            raise RuntimeError("lỗi tạm")
        return real(self, svc, upload_id)

    monkeypatch.setattr(UploadService, "apply_to", flaky)
    before = legal_api.get_backend().snapshots.current().snapshot_id
    uid = upload_to_step3(client, TXT_43)
    wait_job(client, submit(client, uid), "failed")
    d = client.get(f"/api/legal/uploads/{uid}").json()
    assert d["state"] == "failed" and "lỗi tạm" in d["error"]
    assert legal_api.get_backend().snapshots.current().snapshot_id == before        # kho không đổi
    r = client.post(f"/api/legal/uploads/{uid}/retry", json={"by": "Bình"})
    assert r.status_code == 202
    wait_job(client, r.json()["job_id"], "done")
    assert client.get(f"/api/legal/uploads/{uid}").json()["state"] == "published"


def test_index_failure_keeps_old_pair_and_reindex_recovers(client, monkeypatch):
    from rag.temporal import wiring

    before = server.get_temporal_qa().index.snapshot_id
    real = wiring.make_versioned_index
    fail = {"on": True}

    def maybe_fail(*args, **kw):
        if fail["on"]:
            raise RuntimeError("index boom")
        return real(*args, **kw)

    monkeypatch.setattr(wiring, "make_versioned_index", maybe_fail)
    uid = upload_to_step3(client, TXT_43)
    wait_job(client, submit(client, uid), "index_failed")
    d = client.get(f"/api/legal/uploads/{uid}").json()
    assert d["state"] == "published" and d["index_failed"] and d["job"]["state"] == "index_failed"
    assert server.get_temporal_qa().index.snapshot_id == before
    fail["on"] = False
    r = client.post(f"/api/legal/uploads/{uid}/retry", json={"by": "An"})
    assert r.status_code == 202
    wait_job(client, r.json()["job_id"], "done")
    assert server.get_temporal_qa().index.snapshot_id == d["snapshot_id"]
    assert client.get(f"/api/legal/uploads/{uid}").json()["index_failed"] is False
    assert client.post("/api/legal/reindex").status_code == 202


def test_pending_base_laws_grouped(client):
    wait_job(client, submit_upload(client, TXT_43), "done")
    groups = client.get("/api/legal/pending-base-laws").json()["laws"]
    numbers = {g["target_law_number"] for g in groups}
    assert "29/2023/QH15" in numbers and all(g["operations"] for g in groups)
    assert all(g["count"] == len(g["operations"]) for g in groups)


def test_page_image_of_uploaded_file(client, tmp_path):
    import fitz

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Luật số: 43/2024/QH15")
    data = pdf.tobytes()
    pdf.close()
    r = client.post("/api/legal/uploads", files={"file": ("43.pdf", data)})
    assert r.status_code == 201, r.text           # pdf không có Điều nào vẫn tạo bản nháp (cảnh báo cấu trúc)
    uid = r.json()["upload_id"]
    img = client.get(f"/api/legal/uploads/{uid}/page_image/1")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get(f"/api/legal/uploads/{uid}/page_image/9").status_code == 404


# --- CLI ---------------------------------------------------------------------------------------------


def test_cli_build_reports_lock(tmp_path, held_lock, capsys):
    assert main(["build"]) == 2 and "Đang có lần cập nhật kho khác" in capsys.readouterr().out


def test_cli_build_publishes_snapshot_and_report_reads_it(tmp_path, monkeypatch, capsys):
    seed(tmp_path / "legal")
    monkeypatch.setattr(cli, "_legal_dir", lambda: tmp_path / "legal")
    snaps = SnapshotManager(tmp_path / "legal")
    before = snaps.current().snapshot_id
    assert main(["build"]) == 0
    after = snaps.current()
    assert after.snapshot_id != before and after.reason == "cli:build"
    capsys.readouterr()
    assert main(["report"]) == 0
    assert LAND in capsys.readouterr().out


# --- review toàn nhánh: runtime BM25 trước, finalizing, đối soát bản nháp, seq, giới hạn upload, kho cũ ------------


def _bm25_first_factory(gate, calls):
    """make_runtime giả: dense=False dựng BM25 ngay; dense=True (Dense) chờ cổng `gate` (embed chậm)."""
    from legal_runtime import LegalRuntime
    from rag.index.embedder import HashEmbedder
    from rag.index.vector_index import VectorIndex
    from rag.temporal.index import VersionedIndex

    def factory(snaps):
        def make(sid, dense=True):
            calls.append((sid, dense))
            svc = snaps.service(sid)
            if dense:
                assert gate.wait(10), "Dense build chặn"
                idx = VersionedIndex(svc.store, dense=VectorIndex(HashEmbedder(dim=16)), snapshot_id=sid)
            else:
                idx = VersionedIndex(svc.store, snapshot_id=sid)
            idx.build()
            return LegalRuntime(sid, svc, idx, qa=object())
        return make
    return factory


@pytest.fixture
def legal_dir(tmp_path, monkeypatch):
    seed(tmp_path / "legal")
    monkeypatch.setattr(legal_api.CONFIG, "ocr_factory", None)
    monkeypatch.setattr(legal_api.CONFIG, "client_factory", lambda: FakeVbplClient({}))
    return tmp_path / "legal"


def test_first_runtime_is_bm25_then_same_snapshot_dense_upgrade(legal_dir, monkeypatch):
    monkeypatch.setenv("LEGAL_DENSE", "1")
    gate, calls = threading.Event(), []
    monkeypatch.setattr(legal_api.CONFIG, "make_runtime_for", _bm25_first_factory(gate, calls))
    backend = legal_api.LegalBackend(legal_dir)
    try:
        start = time.monotonic()
        holder, worker = backend.runtime()
        assert time.monotonic() - start < 5                  # không chờ Dense
        rt = holder.get()
        assert rt is not None and not rt.index.has_dense
        sid = rt.snapshot_id
        gate.set()
        assert worker.wait_idle(30)
        up = holder.get()
        assert up.index.has_dense and up.snapshot_id == sid == up.index.snapshot_id
        assert calls == [(sid, False), (sid, True)]
        assert [j.kind for j in worker.jobs()] == ["upgrade"]
    finally:
        gate.set()
        if backend.worker is not None:
            backend.worker.wait_idle(30)


def test_legal_dense_off_keeps_bm25_only_without_upgrade(legal_dir, monkeypatch):
    monkeypatch.setenv("LEGAL_DENSE", "0")
    gate, calls = threading.Event(), []
    gate.set()
    monkeypatch.setattr(legal_api.CONFIG, "make_runtime_for", _bm25_first_factory(gate, calls))
    backend = legal_api.LegalBackend(legal_dir)
    holder, worker = backend.runtime()
    assert worker.wait_idle(10)
    assert len(calls) == 1 and worker.jobs() == []


def test_job_view_reports_finalizing_until_draft_updated(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    backend = legal_api.get_backend()
    gate, entered = threading.Event(), threading.Event()
    real = backend.result

    def slow_result(sid, d):
        entered.set()
        assert gate.wait(60)
        return real(sid, d)

    monkeypatch.setattr(backend, "result", slow_result)
    other = create(client, TXT_UPLOADED_V2)["upload_id"]
    job = submit_upload(client, TXT_43)
    try:
        assert entered.wait(120)
        start = time.monotonic()
        view = client.get(f"/api/legal/jobs/{job}").json()
        assert view["state"] == "finalizing" and time.monotonic() - start < 3
        with ThreadPoolExecutor(1) as ex:                     # bước của bản nháp khác không chờ result()
            fut = ex.submit(lambda: client.post(f"/api/legal/uploads/{other}/replace", json={"by": "An"}))
            assert fut.result(timeout=5).status_code == 200
    finally:
        gate.set()
    wait_job(client, job, "done")
    uid = client.get(f"/api/legal/jobs/{job}").json()["ref"]
    d = client.get(f"/api/legal/uploads/{uid}").json()
    assert d["state"] == "published" and d["result"]["laws"]


def test_restart_reconciles_draft_whose_snapshot_was_published(legal_dir):
    from rag.legal.upload.drafts import INTERRUPTED, Draft, DraftStore

    snaps = SnapshotManager(legal_dir)
    ua, ub, uc = "u20261110090000-aaaaaa", "u20261110090000-bbbbbb", "u20261110090000-cccccc"
    sa = snaps.write(f"upload:{ua}", "An", lambda svc: None).snapshot.snapshot_id
    sc = snaps.write(f"upload:{uc}", "An", lambda svc: None).snapshot.snapshot_id
    drafts = DraftStore(legal_dir / "uploads")
    drafts.save(Draft(ua, NOW, "building", "file", "a.txt", "t", "c", [], {}, {}, False, sa, None))
    drafts.save(Draft(ub, NOW, "queued", "file", "b.txt", "t", "c", [], {}, {}, False, sa, None))
    # lần khởi động trước (code cũ) đã đánh dấu failed dù snapshot đã công bố
    drafts.save(Draft(uc, NOW, "failed", "file", "c.txt", "t", "c", [], {}, {}, False, sa, None, error=INTERRUPTED))
    backend = legal_api.LegalBackend(legal_dir)
    a, b, c = (backend.drafts.load(u) for u in (ua, ub, uc))
    assert (a.state, a.snapshot_id, a.error) == ("published", sa, None)
    assert (c.state, c.snapshot_id, c.error) == ("published", sc, None)
    assert b.state == "failed" and b.error == INTERRUPTED


def test_served_orders_by_seq_not_wall_clock(legal_dir):
    from datetime import datetime, timedelta, timezone

    backend = legal_api.LegalBackend(legal_dir)
    # bootstrap (đồng hồ thật) rồi đồng hồ lùi về trước nó
    times = iter([datetime(2020, 1, 1, tzinfo=timezone.utc) - timedelta(hours=i) for i in range(50)])
    backend.snapshots = SnapshotManager(legal_dir, now=lambda: next(times))
    first = backend.snapshots.current().snapshot_id
    second = backend.snapshots.write("cli:build", "t", lambda svc: None).snapshot.snapshot_id
    assert backend.snapshots.get(second).published_at < backend.snapshots.get(first).published_at
    backend.holder = NS(get=lambda: NS(snapshot_id=second))
    assert backend.served(first) is True
    backend.holder = NS(get=lambda: NS(snapshot_id=first))
    assert backend.served(second) is False


def test_upload_larger_than_cap_is_413_by_content_length(client, monkeypatch):
    assert legal_api.MAX_UPLOAD_BYTES == 50 * 1024 * 1024
    monkeypatch.setattr(legal_api, "MAX_UPLOAD_BYTES", 1000)
    r = client.post("/api/legal/uploads", files={"file": ("big.txt", b"x" * 5000)})
    assert r.status_code == 413 and "quá lớn" in r.json()["error"]
    assert legal_api.get_backend().drafts.list() == []


def test_upload_cap_enforced_while_reading_without_content_length(monkeypatch):
    import asyncio

    from starlette.requests import Request

    monkeypatch.setattr(legal_api, "MAX_UPLOAD_BYTES", 1000)
    msgs = [{"type": "http.request", "body": b"x" * 600, "more_body": True}] * 5
    msgs.append({"type": "http.request", "body": b"", "more_body": False})
    it = iter(msgs)

    async def receive():
        return next(it)

    scope = {"type": "http", "method": "POST", "path": "/api/legal/uploads", "query_string": b"",
             "headers": [(b"content-type", b"multipart/form-data; boundary=zz")]}
    resp = asyncio.run(legal_api.handle_create(Request(scope, receive)))
    assert resp.status_code == 413


def test_status_reports_legacy_catalog_written_after_bootstrap(client):
    import os

    st = client.get("/api/legal/status").json()
    assert st["legacy_warning"] is None and st["current_snapshot_id"]
    legal = legal_api.get_backend().snapshots.legal_dir
    store = LegalStore(legal / "catalog.sqlite")
    store.upsert_document(store.document(LAND))
    s = os.stat(legal / "catalog.sqlite")
    os.utime(legal / "catalog.sqlite", ns=(s.st_atime_ns, s.st_mtime_ns + 5_000_000_000))
    msg = client.get("/api/legal/status").json()["legacy_warning"]
    assert msg and "catalog.sqlite" in msg and "Hãy nạp lại" in msg
    assert client.get("/api/legal/uploads").json()["legacy_warning"] == msg
