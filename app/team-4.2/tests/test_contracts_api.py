import importlib.util
import json
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from rag.legal.snapshots import SnapshotManager
from rag.temporal.index import VersionedIndex

ROOT = Path(__file__).resolve().parents[3]
UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import contracts_api  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
DEMO = ROOT / "data" / "team-4.2" / "contracts_demo" / "hop_dong_thue_nha_2023.txt"


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("seed", ROOT / "scripts" / "team-4.2" / "seed_legal_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    legal_dir = tmp_path_factory.mktemp("legal")
    sid = mod.seed(legal_dir, FIXTURES)
    service = SnapshotManager(legal_dir).service(sid)
    index = VersionedIndex(service.store, snapshot_id=sid)
    index.build()
    return SimpleNamespace(snapshot_id=sid, service=service, index=index)


class StageLLM:
    def complete(self, system, user):
        stage = system.split("\n", 1)[0].removeprefix("BƯỚC:").strip() if system.startswith("BƯỚC:") else "facts"
        p = json.loads(user)
        if stage == "facts":
            return json.dumps({"type": "Hợp đồng thuê nhà ở", "parties": [
                {"name": "A", "role": "Bên cho thuê", "unit": "u1", "quote": "BÊN CHO THUÊ (Bên A)"},
                {"name": "B", "role": "Bên thuê", "unit": "u1", "quote": "BÊN THUÊ (Bên B)"}],
                "sign_date": {"value": "2023-03-15", "unit": "u1", "quote": "Hôm nay, ngày 15 tháng 3 năm 2023"}},
                ensure_ascii=False)
        if stage == "find":
            u9 = next(u["uid"] for u in p["units"] if u["label"] == "Điều 9")
            return json.dumps({"findings": [{"unit": u9, "quote": "Bên A được quyền đơn phương chấm dứt hợp đồng",
                                             "group": "illegal", "severity": "critical", "disadvantaged": "Bên thuê",
                                             "explanation": "Đơn phương chấm dứt không báo trước.",
                                             "legal_question": "đơn phương chấm dứt hợp đồng thuê nhà ở",
                                             "law_hint": "Luật Nhà ở", "suggestion": "Báo trước 30 ngày."}]},
                              ensure_ascii=False)
        if stage == "verify":
            return json.dumps({"results": [{"id": f["id"], "supporting": [c["eid"] for c in f["candidates"]
                                                                          if "Nhà ở" in c["source_title"]]}
                                           for f in p["findings"]]}, ensure_ascii=False)
        if stage == "answer":
            return json.dumps({"answer": "Theo Điều 9 hợp đồng, Bên A được chấm dứt.", "legal_conclusion": False,
                               "law_ids": [], "units": []}, ensure_ascii=False)
        raise AssertionError(stage)


@pytest.fixture
def client(tmp_path, runtime):
    @contextmanager
    def lease():
        yield runtime

    contracts_api.CONFIG.root = tmp_path / "contracts"
    contracts_api.CONFIG.llm_factory = StageLLM
    contracts_api.CONFIG.lease = lease
    contracts_api.CONFIG.legacy_search = lambda q, k: []
    contracts_api.CONFIG.ocr_factory = lambda: None
    contracts_api.CONFIG.today = lambda: date(2026, 11, 11)
    contracts_api.reset()
    return TestClient(Starlette(routes=contracts_api.routes))


def upload(client, persist=False, name="hop_dong.txt", data=None):
    data = data if data is not None else DEMO.read_bytes()
    return client.post("/api/contracts", files={"file": (name, data)}, data={"persist": "1" if persist else "0"})


def test_upload_returns_card(client):
    r = upload(client)
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["sign_date"] == "2023-03-15" and card["sign_date_source"] == "text"
    assert [p["role"] for p in card["facts"]["parties"]] == ["Bên cho thuê", "Bên thuê"]
    assert card["coverage"] == {"reviewed": 13, "total": 13} and card["persist"] is False
    assert len(card["contract_id"]) >= 20


def test_session_upload_leaves_nothing_on_disk(client, tmp_path):
    upload(client)
    root = tmp_path / "contracts"
    assert not root.exists() or not any(root.iterdir())


def test_review_report_and_downloads(client):
    cid = upload(client).json()["contract_id"]
    assert client.post(f"/api/contracts/{cid}/party", json={"party": "Bên thuê"}).status_code == 200
    rep = client.post(f"/api/contracts/{cid}/run", json={"op": "review"}).json()
    f = rep["findings"][0]
    assert f["legal_status"] == "concluded" and f["evidence"][0]["store"] == "versioned"
    for fmt, magic in (("docx", b"PK"), ("pdf", b"%PDF")):
        dl = client.get(f"/api/contracts/{cid}/reports/{rep['rid']}.{fmt}")
        assert dl.status_code == 200 and dl.content[:4].startswith(magic)


def test_sign_date_edit_and_bad_date(client):
    cid = upload(client).json()["contract_id"]
    ok = client.post(f"/api/contracts/{cid}/sign-date", json={"date": "2023-04-01"}).json()
    assert ok["sign_date"] == "2023-04-01" and ok["sign_date_source"] == "user"
    assert client.post(f"/api/contracts/{cid}/sign-date", json={"date": "15/03/2023"}).status_code == 400


def test_save_then_list_and_delete(client, tmp_path):
    cid = upload(client).json()["contract_id"]
    client.post(f"/api/contracts/{cid}/save")
    assert (tmp_path / "contracts" / cid / "contract.json").is_file()
    listed = client.get(f"/api/contracts?ids={cid},khongton").json()["contracts"]
    assert [c["contract_id"] for c in listed] == [cid]
    assert client.delete(f"/api/contracts/{cid}").status_code == 200
    assert client.get(f"/api/contracts/{cid}").status_code == 404


def test_unknown_contract_is_404_with_message(client):
    r = client.get("/api/contracts/khongtontai")
    assert r.status_code == 404 and "hết phiên" in r.json()["error"]


def test_chat_with_contract_uses_contract_path(client):
    cid = upload(client).json()["contract_id"]
    out = contracts_api.chat_answer(cid, "Bên A có được chấm dứt không?", [])
    assert out["answer"].startswith("Theo Điều 9") and out["contract_id"] == cid


def test_bad_op_and_unsupported_file(client):
    cid = upload(client).json()["contract_id"]
    assert client.post(f"/api/contracts/{cid}/run", json={"op": "xoa"}).status_code == 400
    assert upload(client, name="a.exe", data=b"MZ").status_code == 400


def test_ai_failure_is_502(client):
    cid = upload(client).json()["contract_id"]

    class Broken:
        def complete(self, s, u):
            return "không phải JSON"

    contracts_api.CONFIG.llm_factory = Broken
    r = client.post(f"/api/contracts/{cid}/run", json={"op": "review"})
    assert r.status_code == 502 and "thử lại" in r.json()["error"]


def _server():
    spec = importlib.util.spec_from_file_location("contracts_route_server", UI / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _request(body):
    from starlette.requests import Request

    req = Request({"type": "http", "method": "POST", "headers": []})

    async def read():
        return body
    req.json = read
    return req


@pytest.mark.parametrize("stream", [False, True])
def test_server_routes_contract_questions_to_contract_path(monkeypatch, stream):
    import asyncio

    server = _server()
    seen = []
    monkeypatch.setattr(server.contracts_api, "chat_answer",
                        lambda cid, q, h: seen.append((cid, q)) or {"answer": "ok", "contract_id": cid})
    monkeypatch.setattr(server, "_sync_chat", lambda *a: (_ for _ in ()).throw(AssertionError("chat thường")))
    monkeypatch.setattr(server, "get_agent_pipeline", lambda: (_ for _ in ()).throw(AssertionError("Think")))

    async def go():
        resp = await server.handle_chat(_request({"query": "Hỏi?", "contract_id": "abc", "stream": stream}))
        assert resp.status_code == 200
        if stream:
            chunks = [c async for c in resp.body_iterator]
            assert '"contract_id": "abc"' in "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    asyncio.run(go())
    assert seen == [("abc", "Hỏi?")]


def test_server_registers_contract_routes():
    server = _server()
    paths = {getattr(r, "path", "") for r in server.app.routes}
    assert "/api/contracts" in paths and "/api/contracts/{cid}/run" in paths


@pytest.mark.parametrize("stream", [False, True])
def test_think_with_contract_uses_contract_agent(monkeypatch, stream):
    import asyncio

    server = _server()
    seen = []

    def fake_think(cid, q, h, stream=False):
        seen.append((cid, q, stream))
        done = {"answer": "ok", "contract_id": cid, "status": "answer"}
        return iter([{"type": "progress", "message": "Think"}, {"type": "done", **done}]) if stream else done
    monkeypatch.setattr(server.contracts_api, "chat_think", fake_think)
    monkeypatch.setattr(server.contracts_api, "chat_answer", lambda *a: (_ for _ in ()).throw(AssertionError("no")))
    monkeypatch.setattr(server, "get_agent_pipeline", lambda: (_ for _ in ()).throw(AssertionError("Think tự do")))

    async def go():
        resp = await server.handle_chat(_request({"query": "Hỏi?", "contract_id": "abc", "think": True,
                                                  "stream": stream}))
        assert resp.status_code == 200
        if stream:
            body = "".join([c if isinstance(c, str) else c.decode() async for c in resp.body_iterator])
            assert '"type": "progress"' in body and '"type": "done"' in body
    asyncio.run(go())
    assert seen == [("abc", "Hỏi?", stream)]
