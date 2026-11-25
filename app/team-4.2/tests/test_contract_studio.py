"""Real upload/verification/check endpoints with deterministic model fixtures."""
import json
import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

UI = Path(__file__).resolve().parents[1] / "ui"
sys.path.insert(0, str(UI))
import contracts_api as api
import contract_studio as studio
from tests.test_contracts_api import client, runtime, verify_all
from tests.test_bridge_check import ScriptLLM, PAGES


def events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


class ClassifyingScriptLLM(ScriptLLM):
    """ScriptLLM cộng bước nhận diện loại (D40: phân tích tự nhận diện loại rồi chọn gói): nhận ra hợp đồng lao động."""

    def complete(self, system, user):
        if system.startswith("Bạn đọc PHẦN ĐẦU"):
            unit = json.loads(user)["units"][0]
            return json.dumps({"kind": "labor_contract", "confidence": 0.95, "unit": unit["uid"],
                               "quote": unit["text"][:40]}, ensure_ascii=False)
        return super().complete(system, user)


@pytest.fixture
def studio_client(client, monkeypatch):
    monkeypatch.setattr(api.CONFIG, "llm_factory", ClassifyingScriptLLM)
    monkeypatch.setattr(api.CONFIG, "tag_llm", lambda *args: None)
    monkeypatch.setattr(api.CONFIG, "legal_graph", lambda: None)
    return TestClient(Starlette(routes=[*studio.routes, *api.routes]))


def upload(studio_client):
    return events(studio_client.post("/api/contract-studio/upload/stream", files={
        "file": ("sample.txt", PAGES[0].text.encode("utf-8"), "text/plain")}))


def test_upload_stream_and_read_only_snapshot(studio_client):
    stream = upload(studio_client)
    assert stream[-1]["type"] == "done"
    assert any(e["type"] == "structure" and e["units"] for e in stream)
    assert any(e["type"] == "fact_batch" for e in stream)
    numbered = [e for e in stream if "sequence" in e]
    assert [e["sequence"] for e in numbered] == list(range(1, len(numbered) + 1))
    assert len({e["run_id"] for e in stream}) == 1
    done = stream[-1]
    cid = done["card"]["contract_id"]
    nodes, edges = done["graph"]["nodes"], done["graph"]["edges"]
    assert any(n["node_type"] == "Unit" and n.get("text") for n in nodes)
    ids = {n["node_id"] for n in nodes}
    assert all(e["src"] in ids and e["dst"] in ids for e in edges)
    before = api.get(cid).oplog.to_json()
    assert studio_client.get(f"/api/contracts/{cid}/studio").json()["graph"] == done["graph"]
    assert api.get(cid).oplog.to_json() == before


def test_analysis_requires_verification_then_emits_actual_results(studio_client):
    cid = upload(studio_client)[-1]["card"]["contract_id"]
    path = f"/api/contracts/{cid}/studio/analyze/stream"
    denied = events(studio_client.post(path, json={}))
    assert denied[-1]["type"] == "error" and denied[-1]["status"] == 409
    verify_all(studio_client, cid)
    stream = events(studio_client.post(path, json={}))
    assert stream[-1]["type"] == "done", stream[-1]
    assert any(e["type"] == "concept" for e in stream)
    assert any(e["type"] == "graph" for e in stream)
    assert any(e["type"] == "evaluation" for e in stream)
    candidates = [e for e in stream if e["type"] == "legal_candidate"]
    resolutions = [e for e in stream if e["type"] == "legal_resolution"]
    assert candidates and len(candidates) == len(resolutions)
    assert all(e["decision"] == "unknown" for e in resolutions)
    assert stream[-1]["result"]["views"]
    assert studio_client.get(f"/api/contracts/{cid}/concept-check/last").json()["stale"] is False


def test_analysis_sends_user_facts_and_answering_a_question_makes_no_llm_call(studio_client, monkeypatch):
    cid = upload(studio_client)[-1]["card"]["contract_id"]
    assert upload_form(studio_client, cid)                         # thẻ có biểu mẫu dữ kiện người dùng từ gói
    verify_all(studio_client, cid)
    stream = events(studio_client.post(f"/api/contracts/{cid}/studio/analyze/stream", json={"user_facts": {}}))
    questions = stream[-1]["result"]["report"]["questions"]
    assert questions and all(q["options"] for q in questions)
    first = questions[0]
    llm = ClassifyingScriptLLM()
    monkeypatch.setattr(api.CONFIG, "llm_factory", lambda: llm)
    r = studio_client.post(f"/api/contracts/{cid}/concept-check/answer",
                           json={"answers": {first["fact"]: first["options"][0]["value"]}})
    assert r.status_code == 200 and llm.calls == []
    result = r.json()
    assert first["fact"] not in {q["fact"] for q in result["report"]["questions"]}
    assert result["views"] and studio_client.get(f"/api/contracts/{cid}/concept-check/last").json()["stale"] is False


def upload_form(studio_client, cid):
    return studio_client.get(f"/api/contracts/{cid}").json()["user_form"]


def test_bad_upload_is_terminal_error(studio_client):
    stream = events(studio_client.post("/api/contract-studio/upload/stream", files={"file": ("empty.txt", b"")}))
    assert stream[-1]["type"] == "error"
    assert not any(e["type"] == "done" for e in stream)


def test_missing_contract_is_not_replaced_with_example(studio_client):
    assert studio_client.get("/api/contracts/missing/studio").status_code == 404


@pytest.mark.parametrize("reason, expected", [("unknown_provision", "unknown"),
                                               ("no_longer_in_force", "excluded"),
                                               ("overlapping_versions", "unknown")])
def test_legal_filter_events_distinguish_missing_data_from_inactive_version(reason, expected):
    from datetime import date
    from rag.bridge.basis import AnchorLawBasis
    from rag.bridge.catalog import load_catalog

    class Graph:
        def text_at(self, pid, day):
            return {"in_force": False if reason != "overlapping_versions" else None, "reason": reason}

    emitted = []
    AnchorLawBasis(load_catalog(), Graph(), on_event=emitted.append).concept_basis("probation.pay", date(2025, 1, 2))
    assert emitted[0]["type"] == "legal_candidate"
    assert emitted[1]["type"] == "legal_resolution"
    assert emitted[1]["decision"] == expected


def test_studio_serves_built_assets_without_changing_existing_routes():
    import server
    client = TestClient(server.app)
    response = client.get("/contract-studio/")
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        import re
        src = re.search(r'src="([^"]+\.js)"', response.text)[1]
        assert src.startswith("/contract-studio/assets/")
        assert client.get(src).status_code == 200
    assert client.get("/contracts", follow_redirects=False).status_code == 307
    assert client.get("/contracts/ask").status_code == 200


def test_report_stream_generates_and_caches_structured_narrative(studio_client, monkeypatch):
    cid = upload(studio_client)[-1]["card"]["contract_id"]
    report_path = f"/api/contracts/{cid}/studio/report/stream"
    before = events(studio_client.post(report_path, json={}))
    assert before[-1]["type"] == "error" and before[-1]["status"] == 409

    verify_all(studio_client, cid)
    events(studio_client.post(f"/api/contracts/{cid}/studio/analyze/stream", json={}))

    class NarrativeLLM:
        def __init__(self):
            self.calls = 0

        def stream(self, system, user):
            self.calls += 1
            yield "## 1. Tóm tắt tổng quan\n"
            yield "Đã tổng hợp báo cáo chuẩn."

    fake = NarrativeLLM()
    monkeypatch.setattr(api.CONFIG, "llm_factory", lambda: fake)
    first = events(studio_client.post(report_path, json={}))
    assert first[-1]["type"] == "done"
    assert first[-1]["llm_used"] is True
    assert first[-1]["cached"] is False
    assert "## 1. Tóm tắt tổng quan" in first[-1]["markdown"]

    second = events(studio_client.post(report_path, json={}))
    assert second[-1]["type"] == "done"
    assert second[-1]["cached"] is True
    assert fake.calls == 1

    forced = events(studio_client.post(report_path, json={"force": True}))
    assert forced[-1]["type"] == "done"
    assert forced[-1]["cached"] is False
    assert fake.calls == 2
