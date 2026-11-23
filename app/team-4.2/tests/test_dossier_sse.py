"""E3: route SSE chạy kịch bản hồ sơ."""
import json
import sys
from pathlib import Path

from starlette.applications import Starlette
from starlette.testclient import TestClient

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import contracts_api  # noqa: E402


def _client():
    return TestClient(Starlette(routes=contracts_api.routes))


def _events(text):
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


def test_sse_streams_scenario_and_ends_with_done():
    r = _client().post("/api/rules/dossiers/a1/scenario/stream", json={})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r.text)
    assert events[0]["type"] == "step" and events[-1]["type"] == "done"
    assert any(e["type"] == "evaluation_diff" for e in events) and any(e["type"] == "explain" for e in events)


def test_sse_unknown_dossier_is_error_event_then_closes():
    events = _events(_client().post("/api/rules/dossiers/khong_co/scenario/stream", json={}).text)
    assert events[-1]["type"] == "error" and events[-1]["status"] == 400 and "không có" in events[-1]["error"]


def test_sse_evaluator_choice_and_bad_value():
    ok = _events(_client().post("/api/rules/dossiers/b1/scenario/stream", json={"evaluator": "reference"}).text)
    assert ok[-1]["type"] == "done"
    bad = _events(_client().post("/api/rules/dossiers/b1/scenario/stream", json={"evaluator": "x"}).text)
    assert bad[-1]["type"] == "error" and bad[-1]["status"] == 400


def test_list_dossiers_endpoint():
    body = _client().get("/api/rules/dossiers").json()
    assert {"a1", "b1"} <= {d["dossier_id"] for d in body["dossiers"]}
