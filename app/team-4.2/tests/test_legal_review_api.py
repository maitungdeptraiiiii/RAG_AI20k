import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from tests.test_legal_service import make_service

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import server  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    svc.build_all()
    monkeypatch.setattr(server, "get_legal_service", lambda: svc)
    return TestClient(server.app), svc


def url(review_id, suffix=""):
    return f"/api/legal/reviews/{quote(review_id, safe='')}{suffix}"


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


def test_approve_closes_and_rebuilds(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    r = c.post(url(item.review_id, "/decision"), json={"action": "reject", "reviewer": "Tùng", "note": "luật đích chưa có"})
    assert r.status_code == 200
    assert item.review_id not in [i["review_id"] for i in c.get("/api/legal/reviews").json()["items"]]


def test_decision_on_closed_returns_409(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    body = {"action": "reject", "reviewer": "Tùng", "note": "x"}
    assert c.post(url(item.review_id, "/decision"), json=body).status_code == 200
    assert c.post(url(item.review_id, "/decision"), json=body).status_code == 409


def test_bad_correction_returns_400(client):
    c, svc = client
    item = svc.store.review_items("open")[0]
    r = c.post(url(item.review_id, "/decision"),
               json={"action": "correct", "reviewer": "T", "note": "x", "corrected_fields": {"source_document_key": "y"}})
    assert r.status_code == 400


def test_review_page_served(client):
    c, _ = client
    r = c.get("/review")
    assert r.status_code == 200 and "<title>" in r.text
