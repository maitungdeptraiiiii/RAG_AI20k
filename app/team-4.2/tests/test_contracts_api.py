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
    # server.py (nạp lúc thu thập test ở file khác) gán các nguồn trỏ về pipeline thật -> đặt lại hết
    contracts_api.CONFIG.document_source = None
    contracts_api.CONFIG.agent_baseline = None
    contracts_api.CONFIG.agent_config = None
    contracts_api.CONFIG.graph = None          # đồ thị của server dựng pipeline thật + nạp .env
    contracts_api.reset()
    return TestClient(Starlette(routes=contracts_api.routes))


def upload(client, persist=False, name="hop_dong.txt", data=None):
    data = data if data is not None else DEMO.read_bytes()
    return client.post("/api/contracts", files={"file": (name, data)}, data={"persist": "1" if persist else "0"})


def verify_all(client, cid, **overrides):
    """Trả lời mọi dữ kiện bắt buộc chưa xác minh (bên = lựa chọn đầu, giá trị máy đọc được thì xác nhận) để soát được."""
    card = client.get(f"/api/contracts/{cid}").json()
    answers = {}
    for f in card["verification"]["fields"]:
        if f["key"] in overrides:
            answers[f["key"]] = {"action": "set", "value": overrides[f["key"]]}
        elif not f["required"] or f["status"] in ("confirmed", "corrected", "unknown"):
            continue
        elif f["status"] == "found":
            answers[f["key"]] = {"action": "confirm"}
        elif f["options"]:
            answers[f["key"]] = {"action": "set", "value": f["options"][0]}
        else:
            answers[f["key"]] = {"action": "set", "value": "2023-03-15" if f["kind"] == "date" else "Hợp đồng dịch vụ"}
    r = client.post(f"/api/contracts/{cid}/facts", json={"answers": answers})
    assert r.status_code == 200, r.text
    assert r.json()["verification"]["complete"] is True
    return r.json()


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
    verify_all(client, cid)
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
    verify_all(client, cid)

    class Broken:
        def complete(self, s, u):
            return "không phải JSON"

    contracts_api.CONFIG.llm_factory = Broken
    r = client.post(f"/api/contracts/{cid}/run", json={"op": "review"})
    assert r.status_code == 502 and "thử lại" in r.json()["error"]


def _server():
    """Nạp server.py để test định tuyến — rồi khôi phục cấu hình dùng chung mà server ghi đè lúc import
    (legal_api.CONFIG / contracts_api.CONFIG), để không làm bẩn các file test chạy sau."""
    import legal_api

    saved = [(ns, dict(vars(ns))) for ns in (legal_api.CONFIG, contracts_api.CONFIG)]
    spec = importlib.util.spec_from_file_location("contracts_route_server", UI / "server.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        for ns, values in saved:
            vars(ns).clear()
            vars(ns).update(values)
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


def test_contract_think_uses_shorter_rounds_and_longer_deadline(client, monkeypatch):
    from rag.agent import AgentConfig
    import rag.contracts.agent_view as av

    cid = upload(client).json()["contract_id"]
    seen = {}

    def fake(c, baseline, config, runtime, chunks, search, q, h, stream=False):
        seen["config"] = config
        return {"answer": "ok", "status": "answer", "contract_id": c.contract_id}
    monkeypatch.setattr(av, "run_contract_agent", fake)
    retriever = SimpleNamespace(chunks={}, retrieve=lambda q, k: SimpleNamespace(hits=[]))
    contracts_api.CONFIG.agent_baseline = lambda: SimpleNamespace(retriever=retriever)
    contracts_api.CONFIG.agent_config = lambda: AgentConfig(max_rounds=3, deadline_s=180.0)
    contracts_api.chat_think(cid, "Hỏi?", [])
    assert seen["config"].max_rounds == 2 and seen["config"].deadline_s == 300.0


def test_importing_server_does_not_load_env_into_process():
    import os

    before = dict(os.environ)
    _server()
    assert dict(os.environ) == before


def test_server_graph_service_does_not_build_pipeline(monkeypatch):
    server = _server()
    loaded = []

    def no_pipeline():
        raise AssertionError("không được dựng pipeline chỉ để đọc cấu hình đồ thị")
    monkeypatch.setattr(server, "get_pipeline", no_pipeline)
    monkeypatch.setattr(server, "Settings", SimpleNamespace(load=lambda: loaded.append(1)))
    monkeypatch.delenv("CONTRACT_GRAPH", raising=False)
    svc = server._contract_graph_service()
    assert svc.store is None and loaded == [1]


def test_client_fixture_does_not_use_server_graph(client):
    assert contracts_api.CONFIG.graph is None


# --- concept-check ---------------------------------------------------------------------------

def _stub_check(monkeypatch, seen):
    from datetime import date as _d
    from rag.bridge.check import CheckReport

    def fake(llm, contract, **kw):
        seen.update(kw)
        return CheckReport(contract.contract_id, _d(2026, 11, 11), "v", [], {}, [], ["w"], {})
    monkeypatch.setattr(contracts_api, "check_contract", fake)
    contracts_api.CONFIG.tag_llm = lambda model, temp: None
    contracts_api.CONFIG.legal_graph = lambda: None


def test_concept_check_returns_report_and_markdown(client, monkeypatch):
    seen = {}
    _stub_check(monkeypatch, seen)
    cid = upload(client).json()["contract_id"]
    r = client.post(f"/api/contracts/{cid}/concept-check", json={"user_facts": {"wage_region": "I"}})
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["contract_id"] == cid
    assert body["report"]["warnings"] == ["w"]
    assert isinstance(body["markdown"], str)
    assert body["labels"] == {}
    assert seen["user_facts"] == {"wage_region": "I"}


def test_concept_check_unknown_fact_is_400(client):
    contracts_api.CONFIG.tag_llm = lambda model, temp: None
    contracts_api.CONFIG.legal_graph = lambda: None
    cid = upload(client).json()["contract_id"]
    contracts_api.get(cid).facts["document_kind"] = "lease_contract"      # có gói thì dữ kiện người dùng mới được kiểm
    r = client.post(f"/api/contracts/{cid}/concept-check", json={"user_facts": {"abc": 1}})
    assert r.status_code == 400


def test_concept_check_gone_is_404(client):
    r = client.post("/api/contracts/nope/concept-check", json={})
    assert r.status_code == 404
    assert r.json()["error"] == contracts_api.GONE


def test_concept_check_rebuilds_graph(client, monkeypatch):
    _stub_check(monkeypatch, {})
    calls = []
    monkeypatch.setattr(contracts_api, "_rebuild", lambda c, now: calls.append(c.contract_id))
    cid = upload(client).json()["contract_id"]
    calls.clear()
    assert client.post(f"/api/contracts/{cid}/concept-check", json={}).status_code == 200
    assert calls == [cid]


def test_concept_check_result_is_saved_and_viewable_again(client, monkeypatch):
    _stub_check(monkeypatch, {})
    cid = upload(client).json()["contract_id"]
    assert client.get(f"/api/contracts/{cid}").json()["last_check"] is None
    assert client.get(f"/api/contracts/{cid}/concept-check/last").status_code == 400     # chưa kiểm tra
    ran = client.post(f"/api/contracts/{cid}/concept-check", json={}).json()
    card = client.get(f"/api/contracts/{cid}").json()
    assert card["last_check"]["stale"] is False and card["last_check"]["checked_at"]
    saved = client.get(f"/api/contracts/{cid}/concept-check/last")
    assert saved.status_code == 200
    body = saved.json()
    assert body["report"] == ran["report"] and body["views"] == ran["views"] and body["markdown"] == ran["markdown"]
    assert body["stale"] is False and body["checked_at"] == card["last_check"]["checked_at"]


def test_saved_concept_check_is_stale_after_facts_change(client, monkeypatch):
    _stub_check(monkeypatch, {})
    cid = upload(client).json()["contract_id"]
    client.post(f"/api/contracts/{cid}/concept-check", json={})
    c = contracts_api.store().get(cid)
    c.facts = {**c.facts, "__changed__": {"value": 1}}
    contracts_api.store().update(c)
    assert client.get(f"/api/contracts/{cid}/concept-check/last").json()["stale"] is True
    assert client.get(f"/api/contracts/{cid}").json()["last_check"]["stale"] is True


def test_last_concept_check_gone_is_404(client):
    assert client.get("/api/contracts/nope/concept-check/last").status_code == 404


def _sse_events(text):
    return [json.loads(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


def test_stream_emits_events_then_done(client, monkeypatch):
    from datetime import date as _d
    from rag.bridge.check import CheckReport

    def fake(llm, contract, on_event=None, **kw):
        on_event({"type": "stage", "stage": "facts", "status": "start"})
        on_event({"type": "progress", "stage": "tag", "done": 1, "total": 2})
        on_event({"type": "partial", "results": []})
        return CheckReport(contract.contract_id, _d(2026, 11, 11), "v", [], {}, [], [], {})
    monkeypatch.setattr(contracts_api, "check_contract", fake)
    contracts_api.CONFIG.tag_llm = lambda model, temp: None
    contracts_api.CONFIG.legal_graph = lambda: None
    cid = upload(client).json()["contract_id"]
    r = client.post(f"/api/contracts/{cid}/concept-check/stream", json={})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(r.text)
    assert [e["type"] for e in events] == ["stage", "progress", "partial", "done"]
    assert events[2]["views"] == []
    assert events[-1]["report"]["contract_id"] == cid and "views" in events[-1] and "markdown" in events[-1]


def test_stream_unknown_fact_error_event(client):
    contracts_api.CONFIG.tag_llm = lambda model, temp: None
    contracts_api.CONFIG.legal_graph = lambda: None
    cid = upload(client).json()["contract_id"]
    contracts_api.get(cid).facts["document_kind"] = "lease_contract"
    events = _sse_events(client.post(f"/api/contracts/{cid}/concept-check/stream",
                                     json={"user_facts": {"abc": 1}}).text)
    assert events[-1]["type"] == "error" and events[-1]["status"] == 400


def test_stream_gone(client):
    events = _sse_events(client.post("/api/contracts/nope/concept-check/stream", json={}).text)
    assert events == [{"type": "error", "error": contracts_api.GONE, "status": 404}]


class _FakeAgent:
    def __init__(self, law=()):
        self.law, self.seen = list(law), {}

    def ask(self, question, history=None, on_step=None):
        from rag.contracts.graph.agent import GraphAnswer
        self.seen.update(question=question, history=history)
        on_step({"type": "step", "n": 1, "tool": "find_concept", "thought": "t", "args": {}, "result": "{}"})
        return GraphAnswer("Đáp", [{"node_id": "n1", "label": "Điều 1"}], self.law, "answer", ["w"], [], {"steps": 1})


class _ConceptPathAgent:
    """Đường đi đi qua một nút Khái niệm; agent có gọi check_concept cho khái niệm đó."""
    def ask(self, question, history=None, on_step=None):
        from rag.contracts.graph.agent import GraphAnswer
        path = [{"node_id": "ci", "node_type": "ConceptInstance", "label": "probation.pay", "concept_id": "probation.pay"},
                {"node_id": "u6", "node_type": "Unit", "label": "Điều 6",
                 "edge": {"verified": True, "rel": "ABOUT", "dir": "out", "props": {}}}]
        trace = [{"tool": "check_concept", "args": {"concept_id": "probation.pay"}, "error": None}]
        unused = [{"node_id": "ci2", "node_type": "ConceptInstance", "label": "x", "concept_id": "probation.duration"}]
        return GraphAnswer("Đáp", path, [], "answer", [], trace, {"steps": 1}, unused)


def test_ask_path_links_concept_to_law_graph(client, monkeypatch):
    class Legal:
        def text_at(self, pid, day):
            return {"in_force": True, "text": "Lời văn " + pid, "citation": {"label": pid.split("#")[1], "doc_title": "BLLĐ"}}
    _stub_agent(monkeypatch, _ConceptPathAgent(), legal=Legal())
    cid = upload(client).json()["contract_id"]
    done = _sse_events(client.post(f"/api/contracts/{cid}/ask/stream", json={"question": "q"}).text)[-1]
    ci, unit = done["path"]
    concept = contracts_api.load_catalog().concepts["probation.pay"]
    assert ci["concept_label"] == concept.label
    assert [l["pid"] for l in ci["law_links"]] == [a["pid"] for a in concept.anchors]
    assert all(l["read_by_agent"] and l["in_force"] for l in ci["law_links"])
    assert "law_links" not in unit and unit["edge"]["rel"] == "ABOUT"
    assert done["seen_unused"][0]["concept_label"] == contracts_api.load_catalog().concepts["probation.duration"].label


def _stub_agent(monkeypatch, agent, legal=None):
    from datetime import date as _d
    contracts_api.CONFIG.legal_graph = lambda: legal
    monkeypatch.setattr(contracts_api, "_open_agent", lambda c, catalog, legal_, facts: (agent, _d(2025, 1, 2), []))


def test_ask_stream_steps_then_done(client, monkeypatch):
    agent = _FakeAgent()
    _stub_agent(monkeypatch, agent)
    cid = upload(client).json()["contract_id"]
    hist = [{"query": "a", "answer": "b"}]
    r = client.post(f"/api/contracts/{cid}/ask/stream", json={"question": " Hỏi? ", "history": hist})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(r.text)
    assert [e["type"] for e in events] == ["step", "done"]
    done = events[-1]
    assert done["answer"] == "Đáp" and done["confidence"] == "answer" and done["path"][0]["label"] == "Điều 1"
    assert done["warnings"] == ["w"] and agent.seen == {"question": "Hỏi?", "history": hist}


def test_ask_law_without_legal_graph(client, monkeypatch):
    _stub_agent(monkeypatch, _FakeAgent(law=["bo-luat:45/2019/QH14#d26"]))
    cid = upload(client).json()["contract_id"]
    done = _sse_events(client.post(f"/api/contracts/{cid}/ask/stream", json={"question": "q"}).text)[-1]
    assert done["law"] == [{"pid": "bo-luat:45/2019/QH14#d26", "citation": None, "text": None, "in_force": None,
                            "source_url": None, "valid_from": None, "valid_to": None, "note": None}]


def test_ask_law_with_legal_graph(client, monkeypatch):
    class Legal:
        def text_at(self, pid, day):
            return {"in_force": True, "text": "Lời văn", "citation": {
                "label": "điều 26", "doc_title": "BLLĐ", "source_url": "https://vbpl.vn/x", "valid_from": "2021-01-01"}}
    _stub_agent(monkeypatch, _FakeAgent(law=["p1"]), legal=Legal())
    cid = upload(client).json()["contract_id"]
    done = _sse_events(client.post(f"/api/contracts/{cid}/ask/stream", json={"question": "q"}).text)[-1]
    assert done["law"] == [{"pid": "p1", "citation": "Điều 26 — BLLĐ", "text": "Lời văn", "in_force": True,
                            "source_url": "https://vbpl.vn/x", "valid_from": "2021-01-01", "valid_to": None, "note": None}]


def test_ask_without_concept_check_is_409(client):
    contracts_api.CONFIG.legal_graph = lambda: None
    cid = upload(client).json()["contract_id"]
    events = _sse_events(client.post(f"/api/contracts/{cid}/ask/stream", json={"question": "q"}).text)
    assert events == [{"type": "error", "error": contracts_api.NEEDS_CHECK, "status": 409}]


def test_ask_empty_question_is_400(client, monkeypatch):
    _stub_agent(monkeypatch, _FakeAgent())
    cid = upload(client).json()["contract_id"]
    events = _sse_events(client.post(f"/api/contracts/{cid}/ask/stream", json={"question": "  "}).text)
    assert events[-1]["type"] == "error" and events[-1]["status"] == 400


def test_ask_gone(client):
    events = _sse_events(client.post("/api/contracts/nope/ask/stream", json={"question": "q"}).text)
    assert events == [{"type": "error", "error": contracts_api.GONE, "status": 404}]


def test_ask_law_includes_anchors_of_checked_concepts(client, monkeypatch):
    from rag.bridge.catalog import load_catalog
    from rag.contracts.graph.agent import GraphAnswer

    class Agent:
        def ask(self, question, history=None, on_step=None):
            trace = [{"tool": "check_concept", "args": {"concept_id": "probation.pay"}, "result": "{}"},
                     {"tool": "check_concept", "args": {"concept_id": "probation.pay"}, "result": '{"error": "x"}'}]
            return GraphAnswer("Đúng luật", [], ["extra"], "answer", [], trace, {})
    _stub_agent(monkeypatch, Agent())
    want = [a["pid"] for a in load_catalog().concepts["probation.pay"].anchors]
    cid = upload(client).json()["contract_id"]
    done = _sse_events(client.post(f"/api/contracts/{cid}/ask/stream", json={"question": "q"}).text)[-1]
    assert want and [x["pid"] for x in done["law"]] == ["extra", *want]


def test_card_counts_concepts(client):
    from datetime import datetime, timezone
    from rag.contracts.graph.oplog import machine_op
    cid = upload(client).json()["contract_id"]
    assert client.get(f"/api/contracts/{cid}").json()["concepts"] == 0
    c = contracts_api.get(cid)
    at = datetime(2026, 11, 17, tzinfo=timezone.utc)
    for concept, uid in (("probation.pay", "u1"), ("probation.pay", "u2"), ("work.hours", "u1")):
        c.oplog.add(machine_op(cid, "ASSERT", f"concept:{concept}", {"kind": "concept", "concept_id": concept,
                               "slots": {}}, "llm", "auto_accepted", source_uid=uid, at=at))
    assert client.get(f"/api/contracts/{cid}").json()["concepts"] == 2


# --- D40: gói luật theo loại hợp đồng đi suốt luồng ------------------------------------------

def test_catalog_for_picks_pack_by_kind_and_legacy_is_labor(client):
    cid = upload(client).json()["contract_id"]
    c = contracts_api.get(cid)
    c.facts = {k: v for k, v in (c.facts or {}).items() if k != "document_kind"}
    assert "probation.pay" in contracts_api.catalog_for(c).concepts           # chưa có loại: labor như cũ
    c.facts["document_kind"] = "lease_contract"
    cat = contracts_api.catalog_for(c)
    assert any(k.startswith("lease.") for k in cat.concepts) and "probation.pay" not in cat.concepts


def test_catalog_for_unknown_kind_raises_not_labor(client):
    cid = upload(client).json()["contract_id"]
    c = contracts_api.get(cid)
    c.facts = {**(c.facts or {}), "document_kind": "unknown"}
    with pytest.raises(ValueError, match="không có gói"):
        contracts_api.catalog_for(c)


class _ClassifyLLM:
    """Chỉ trả lời bước nhận diện loại; số lần gọi để kiểm 'nhận diện một lần'."""
    def __init__(self, kind):
        self.kind, self.calls = kind, 0

    def complete(self, system, user):
        self.calls += system.startswith("Bạn đọc PHẦN ĐẦU")      # chỉ đếm bước nhận diện loại (trích dữ kiện cũng dùng llm này)
        return json.dumps({"kind": self.kind, "confidence": 0.9, "unit": "u1", "quote": "BÊN CHO THUÊ (Bên A)"},
                          ensure_ascii=False)


def _upload_without_kind(client):
    cid = upload(client).json()["contract_id"]
    c = contracts_api.get(cid)
    c.facts = {k: v for k, v in (c.facts or {}).items() if k != "document_kind"}
    return cid, c


def test_concept_check_classifies_once_then_passes_concrete_kind(client, monkeypatch):
    seen = {}
    _stub_check(monkeypatch, seen)
    llm = _ClassifyLLM("lease_contract")
    contracts_api.CONFIG.llm_factory = lambda: llm
    cid, c = _upload_without_kind(client)
    assert client.post(f"/api/contracts/{cid}/concept-check", json={}).status_code == 200
    assert seen["document_kind"] == "lease_contract" and "catalog" not in seen and c.facts["document_kind"] == "lease_contract"
    assert llm.calls == 1
    assert client.post(f"/api/contracts/{cid}/concept-check", json={}).status_code == 200
    assert llm.calls == 1                      # loại đã lưu: không nhận diện lại


def test_concept_check_unknown_classification_is_not_stored(client, monkeypatch):
    seen = {}
    _stub_check(monkeypatch, seen)
    contracts_api.CONFIG.llm_factory = lambda: _ClassifyLLM("unknown")
    cid, c = _upload_without_kind(client)
    assert client.post(f"/api/contracts/{cid}/concept-check", json={}).status_code == 200
    assert seen["document_kind"] == "unknown" and "document_kind" not in c.facts


def test_concept_check_legacy_none_kind_uses_labor_catalog(client, monkeypatch):
    seen = {}
    _stub_check(monkeypatch, seen)
    cid, c = _upload_without_kind(client)
    contracts_api.concept_check(cid, {}, document_kind=None)
    assert "document_kind" not in seen and "probation.pay" in seen["catalog"].concepts


def test_ask_on_contract_of_unknown_kind_is_400(client):
    cid = upload(client).json()["contract_id"]
    contracts_api.get(cid).facts = {**(contracts_api.get(cid).facts or {}), "document_kind": "unknown"}
    contracts_api.CONFIG.legal_graph = lambda: None
    r = client.post(f"/api/contracts/{cid}/ask/stream", json={"question": "q"})
    last = _sse_events(r.text)[-1]
    assert last["type"] == "error" and last["status"] == 400 and "không có gói" in last["error"]
