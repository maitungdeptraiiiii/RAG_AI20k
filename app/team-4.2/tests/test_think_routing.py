"""Think is an explicit per-request opt-in, including JSON and SSE routes."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from starlette.requests import Request


@pytest.fixture
def server():
    path = Path(__file__).resolve().parent.parent / "ui" / "server.py"
    spec = importlib.util.spec_from_file_location("think_test_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request_for(body):
    request = Request({"type": "http", "method": "POST", "headers": []})

    async def read_body():
        return body

    request.json = read_body
    return request


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("think", [None, False, True])
def test_selects_only_requested_backend(server, monkeypatch, stream, think):
    baseline, agent = object(), object()
    baseline_factory = Mock(return_value=(baseline, None))
    agent_factory = Mock(return_value=agent)
    monkeypatch.setattr(server, "get_pipeline", baseline_factory)
    monkeypatch.setattr(server, "get_agent_pipeline", agent_factory)
    executed = []
    history = [{"query": "Câu trước", "answer": "Đáp án trước"}]

    def ask(query, pipeline, received_history):
        executed.append((query, pipeline, received_history))
        return {"answer": "ok"}

    def events(query, pipeline, received_history):
        ask(query, pipeline, received_history)
        yield 'data: {"type": "done", "answer": "ok"}\n\n'

    monkeypatch.setattr(server, "_sync_ask", ask)
    monkeypatch.setattr(server, "_sync_stream", events)
    body = {"query": "Câu hỏi", "history": history, "stream": stream}
    if think is not None:
        body["think"] = think

    async def run():
        response = await server.handle_chat(request_for(body))
        assert response.status_code == 200
        if stream:
            chunks = [chunk async for chunk in response.body_iterator]
            assert len(chunks) == 1
        else:
            assert json.loads(response.body)["answer"] == "ok"

    asyncio.run(run())
    assert executed == [("Câu hỏi", agent if think else baseline, history)]
    assert baseline_factory.call_count == (0 if think else 1)
    assert agent_factory.call_count == (1 if think else 0)


@pytest.mark.parametrize("stream", [False, True])
def test_unavailable_agent_does_not_fall_back_or_initialize_baseline(server, monkeypatch, stream):
    baseline_factory = Mock(side_effect=AssertionError("Baseline must not run"))
    monkeypatch.setattr(server, "get_pipeline", baseline_factory)
    monkeypatch.setattr(server, "get_agent_pipeline", lambda: None)
    response = asyncio.run(server.handle_chat(request_for({
        "query": "Câu hỏi", "think": True, "stream": stream,
    })))
    assert response.status_code == 503
    assert json.loads(response.body)["code"] == "agent_unavailable"
    baseline_factory.assert_not_called()


@pytest.mark.parametrize("think", ["false", "true", 0, 1, None, [], {}])
def test_think_requires_json_boolean(server, monkeypatch, think):
    baseline_factory = Mock(side_effect=AssertionError("Invalid request"))
    agent_factory = Mock(side_effect=AssertionError("Invalid request"))
    monkeypatch.setattr(server, "get_pipeline", baseline_factory)
    monkeypatch.setattr(server, "get_agent_pipeline", agent_factory)
    response = asyncio.run(server.handle_chat(request_for({"query": "Câu hỏi", "think": think})))
    assert response.status_code == 400
    baseline_factory.assert_not_called()
    agent_factory.assert_not_called()


def test_agent_initialization_error_is_sanitized(server, monkeypatch):
    monkeypatch.setattr(server, "get_agent_pipeline", Mock(side_effect=RuntimeError("secret-sample-value")))
    response = asyncio.run(server.handle_chat(request_for({"query": "Câu hỏi", "think": True})))
    assert response.status_code == 503
    assert "secret-sample-value" not in response.body.decode()
    assert json.loads(response.body)["code"] == "agent_initialization_failed"
