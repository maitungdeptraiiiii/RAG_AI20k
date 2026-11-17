import hashlib
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from rag.config import Settings
from tests.test_legal_service import make_service

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import legal_api  # noqa: E402
import server  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    for d in svc.store.documents():         # snapshot chỉ công bố khi checksum file text khớp
        svc.store.upsert_document(replace(d, raw_checksum=hashlib.sha256(Path(d.raw_text_path).read_bytes()).hexdigest()))
    svc.build_all()
    # một mục duyệt thật: thao tác vào Luật Doanh nghiệp (trong kho) được đưa ra duyệt
    from rag.legal.models import Address, ReviewItem
    op = next(o for o in svc.store.operations() if o.target == Address("148", "1"))
    svc.store.add_review_item(ReviewItem(f"op:{op.operation_id}", "operation", op.target_document_key, op.operation_id,
                                         None, ("operation.manual_check",), "open", svc.now(),
                                         {"source_excerpt": "5. Sửa đổi, bổ sung khoản 1 và khoản 2 Điều 148 như sau:"}))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LEGAL_DENSE", "0")
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(server, "get_pipeline", lambda: (NS(llm=None, retriever=None), settings))
    monkeypatch.setattr(legal_api.CONFIG, "legal_dir", lambda: tmp_path / "legal")
    monkeypatch.setattr(legal_api.CONFIG, "ocr_factory", None)
    legal_api.reset()
    yield TestClient(server.app), server.get_legal_service()       # đọc snapshot đang công bố
    legal_api.reset()


def url(review_id, suffix=""):
    return f"/api/legal/reviews/{quote(review_id, safe='')}{suffix}"


def wait_job(c, job_id, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = c.get(f"/api/legal/jobs/{job_id}").json()
        if job["state"] in ("done", "failed", "index_failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job chưa xong")


def test_list_open_reviews(client):
    c, _ = client
    items = c.get("/api/legal/reviews").json()["items"]
    assert items and all(i["status"] == "open" for i in items)
    assert all(i["title"] for i in items)


def test_detail_has_source_excerpt_and_operation(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    data = c.get(url(item.review_id)).json()
    assert data["source_excerpt"]
    assert data["operation"]["operation_id"] == item.operation_id
    assert c.get(url("op:none")).status_code == 404


def test_detail_shows_before_after_for_known_target(client):
    c, svc = client
    from rag.legal.models import Address, ReviewItem
    op = next(o for o in svc.store.operations() if o.target == Address("60", "3"))
    svc.store.add_review_item(ReviewItem(f"op:{op.operation_id}", "operation", op.target_document_key, op.operation_id,
                                         None, ("manual",), "open", svc.now(), {}))
    data = c.get(url(f"op:{op.operation_id}")).json()
    assert data["target_before"].startswith("3. Trường hợp chủ tọa")
    assert data["target_after"] == op.new_text


def test_decision_requires_note(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    r = c.post(url(item.review_id, "/decision"), json={"action": "approve", "reviewer": "Tùng", "note": ""})
    assert r.status_code == 400


def test_decision_is_queued_then_closes_item(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    r = c.post(url(item.review_id, "/decision"), json={"action": "reject", "reviewer": "Tùng", "note": "luật đích chưa có"})
    assert r.status_code == 202
    job = wait_job(c, r.json()["job_id"])
    assert job["state"] == "done" and job["kind"] == "review" and job["actor"] == "Tùng"
    assert item.review_id not in [i["review_id"] for i in c.get("/api/legal/reviews").json()["items"]]
    assert server.get_legal_service().store.review_item(item.review_id).status == "resolved"
    assert svc.store.review_item(item.review_id).status == "open"          # snapshot cũ không bị sửa tại chỗ


def test_decision_on_closed_returns_409(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    body = {"action": "reject", "reviewer": "Tùng", "note": "x"}
    assert wait_job(c, c.post(url(item.review_id, "/decision"), json=body).json()["job_id"])["state"] == "done"
    assert c.post(url(item.review_id, "/decision"), json=body).status_code == 409


def test_unknown_item_returns_404(client):
    c, _ = client
    assert c.post(url("op:none", "/decision"), json={"action": "reject", "reviewer": "T", "note": "x"}).status_code == 404


def test_bad_correction_fails_on_job_and_keeps_store(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    before = legal_api.get_backend().snapshots.current().snapshot_id
    r = c.post(url(item.review_id, "/decision"),
               json={"action": "correct", "reviewer": "T", "note": "x", "corrected_fields": {"source_document_key": "y"}})
    assert r.status_code == 202
    job = wait_job(c, r.json()["job_id"])
    assert job["state"] == "failed" and "source_document_key" in job["error"]
    assert legal_api.get_backend().snapshots.current().snapshot_id == before
    assert server.get_legal_service().store.review_item(item.review_id).status == "open"


def test_review_page_served(client):
    c, _ = client
    r = c.get("/review")
    assert r.status_code == 200 and "<title>" in r.text
