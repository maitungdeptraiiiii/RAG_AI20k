"""Conversation retention, provenance, isolation and mode switches (no network)."""
import asyncio
import json

import httpx
import pytest

from rag.conversation import ConversationStore, ConversationBusy, conversation_context
from tests.test_think_routing import server  # fixture
from tests.test_agent import build_agent, FixtureLLM
from tests.test_condense import MockLLM
from rag.advanced.condense import QueryCondenser


def test_user_statements_outlive_recent_answers_and_preserve_corrections():
    history = [{"turn_id": "original", "query": "Ký hợp đồng ngày 15/06/2023.", "answer": ""}]
    history += [{"query": f"Câu hỏi phụ {i}", "answer": "Đáp án"} for i in range(10)]
    history += [{"turn_id": "correction", "query": "Tôi sửa: ký ngày 15/06/2022.", "answer": ""}]
    context = conversation_context(history)
    assert context["user_statements"][0]["turn_id"] == "original"
    assert context["user_statements"][-1]["turn_id"] == "correction"
    assert len(context["recent_turns"]) == 8
    assert not context["truncated"]


def test_numbered_reference_beyond_old_250_character_limit_reaches_condenser():
    model = MockLLM('{"standalone_query":"Phân tích điều kiện tại mục 2?"}')
    QueryCondenser(model).condense("Phân tích mục 2?", history=[{
        "query": "Các điều kiện là gì?", "answer": "Mở đầu. " * 100 + "2. Ngoại lệ cần kiểm chứng."}])
    payload = json.loads(model.calls[0][1])
    assert payload["conversation_context"]["recent_turns"][0]["assistant_context_unverified"].endswith(
        "2. Ngoại lệ cần kiểm chứng.")
    assert "không coi kết luận cũ" in model.calls[0][0]


def test_agent_all_roles_receive_old_facts_and_masked_reference_context():
    received = {}

    def hook(stage, payload, result):
        received[stage] = payload
        return result

    agent, _ = build_agent(FixtureLLM(hook))
    agent.baseline.mask_queries = True
    history = [{"query": "Người ký là chủ đầu tư, email demo@example.com.",
                "answer": "Mở đầu " * 80 + "2. Hãy xác định ngày ký hợp đồng."}]
    history += [{"query": f"Bổ sung {i}", "answer": ""} for i in range(4)]
    trace = agent.ask_debug("Ký ngày 15/06/2023, trường hợp đó cần hồ sơ gì?", history=history)
    assert trace.status == "answer"
    for stage in ("CONDENSE", "PLAN", "ASSESS", "COMPOSE", "VERIFY"):
        context = received[stage]["conversation_context"]
        assert "chủ đầu tư" in context["user_statements"][0]["text"]
        serialized = json.dumps(context, ensure_ascii=False)
        assert "demo@example.com" not in serialized
        assert "2. Hãy xác định ngày ký hợp đồng." in serialized


def test_store_isolation_rehydration_idempotency_and_busy_guard():
    store = ConversationStore(max_sessions=2)
    bootstrap = [{"query": "Dữ kiện cũ", "answer": "Đáp án cũ"}]
    assert store.begin("a", bootstrap)[0]["query"] == "Dữ kiện cũ"
    with pytest.raises(ConversationBusy):
        store.begin("a")
    store.remember("a", "t1", "Đính chính", {"answer": "Đã ghi nhận"})
    store.remember("a", "t1", "Đính chính", {"answer": "Đã ghi nhận lại"})
    store.release("a")
    assert store.begin("b") == []
    store.release("b")
    rows = store.begin("a", [{"query": "UI cũ không được ghi đè server", "answer": ""}])
    assert len(rows) == 2
    assert rows[-1]["answer"] == "Đã ghi nhận lại"
    store.release("a")


def test_bounds_and_expiry_report_loss_explicitly():
    rows = [{"query": f"Dữ kiện {i}", "answer": ""} for i in range(70)]
    assert conversation_context(rows)["truncated"]
    context = conversation_context([{"query": "A" * 8000, "answer": "B" * 17000}] * 5)
    assert context["truncated"]
    assert sum(len(s["text"]) for s in context["user_statements"]) <= 24000
    store = ConversationStore(ttl_seconds=-1)
    store.begin("a")
    store.remember("a", "t", "Cũ", {"answer": "Cũ"})
    store.release("a")
    assert store.begin("a", [{"query": "Khôi phục từ UI", "answer": ""}])[0]["query"] == "Khôi phục từ UI"


def test_long_assistant_answers_do_not_evict_older_user_statements():
    store = ConversationStore()
    store.begin("a", [{"query": f"Dữ kiện {i}", "answer": "A" * 16000} for i in range(40)])
    store.release("a")
    rows = store.begin("a")
    assert len(rows) == 40
    assert rows[0]["query"] == "Dữ kiện 0"
    assert conversation_context(rows)["assistant_history_truncated"]


@pytest.mark.parametrize("stream", [False, True])
def test_baseline_generation_receives_full_masked_context(stream):
    from tests.test_stream import _build_test_pipeline
    calls = []

    class Model:
        def complete(self, system, user):
            calls.append(user)
            if "giải nén ngữ cảnh" in system:
                return '{"standalone_query":"Thời giờ làm việc của người lao động?"}'
            return "Không quá 8 giờ [1]."

    pipeline = _build_test_pipeline(Model())
    history = [{"query": "Người lao động có email demo@example.com.",
                "answer": "Mở đầu " * 80 + "2. Thời giờ làm việc."}]
    if stream:
        result = list(pipeline.ask_stream("Giải thích mục 2?", history=history))[-1]
        assert result["answer"]
    else:
        assert pipeline.ask_debug("Giải thích mục 2?", history=history).answer.text
    assert "2. Thời giờ làm việc." in calls[-1]
    assert "demo@example.com" not in "\n".join(calls)


@pytest.mark.parametrize("stream", [False, True])
def test_http_failed_request_releases_session_without_remembering_error(server, monkeypatch, stream):
    def fail(*args):
        if stream:
            return iter([server._sse({"type": "error", "error": "test failure"})])
        raise RuntimeError("test failure")

    monkeypatch.setattr(server, "_sync_stream" if stream else "_sync_chat", fail)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            await client.post("/api/chat", json={"session_id": "failed", "query": "Câu lỗi", "stream": stream})
    asyncio.run(run())
    assert server._conversations.begin("failed") == []
    server._conversations.release("failed")


def test_json_disconnect_does_not_release_session_while_worker_is_running(server, monkeypatch):
    import threading
    from tests.test_think_routing import request_for
    started, stop = threading.Event(), threading.Event()

    def slow(*args):
        started.set()
        assert stop.wait(5)
        return {"answer": "done"}

    monkeypatch.setattr(server, "_sync_chat", slow)

    async def run():
        task = asyncio.create_task(server.handle_chat(request_for({"session_id": "cancel", "query": "Câu hỏi"})))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(ConversationBusy):
                server._conversations.begin("cancel")
        finally:
            stop.set()
        # Yield until the executor completion callback releases the lease.
        for _ in range(100):
            await asyncio.sleep(0.01)
            try:
                server._conversations.begin("cancel")
                server._conversations.release("cancel")
                break
            except ConversationBusy:
                continue
        else:
            pytest.fail("Cancelled worker leaked its session lease")
    asyncio.run(run())


@pytest.mark.parametrize("stream", [False, True])
def test_http_normal_think_normal_share_server_memory_and_date_stays_request_local(server, monkeypatch, stream):
    from datetime import date
    seen = []
    monkeypatch.setattr(server, "get_agent_pipeline", lambda as_of=None: object())

    def ask(query, as_of, state, history):
        seen.append((query, as_of, history))
        return {"answer": "Mở đầu " * 80 + "2. Điều kiện cần xem xét."}

    def agent_ask(query, state, history, as_of, backend):
        return ask(query, as_of, state, history)

    def events(query, as_of, state, history):
        yield server._sse({"type": "done", **ask(query, as_of, state, history)})

    def agent_events(query, state, history, as_of, backend):
        yield server._sse({"type": "done", **agent_ask(query, state, history, as_of, backend)})

    monkeypatch.setattr(server, "_sync_chat", ask)
    monkeypatch.setattr(server, "_sync_agent", agent_ask)
    monkeypatch.setattr(server, "_sync_stream", events)
    monkeypatch.setattr(server, "_sync_agent_stream", agent_events)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            messages = ["Tôi là chủ đầu tư, ký ngày 15/06/2023.", "Phân tích mục 2.",
                        "Tôi sửa: ký ngày 15/06/2022.", "Chuyển chủ đề: thời gian thử việc?"]
            for i, query in enumerate(messages):
                body = {"session_id": "shared", "turn_id": f"t{i}", "query": query,
                        "think": i in (1, 2), "stream": stream}
                if i == 1:
                    body["as_of"] = "2025-06-15"
                response = await client.post("/api/chat", json=body)
                assert response.status_code == 200
                data = (json.loads(response.text.split("data: ")[-1]) if stream else response.json())
                assert data["conversation"]["history_turns"] == i
            isolated = await client.post("/api/chat", json={"session_id": "other", "query": "Xin chào"})
            assert isolated.json()["conversation"]["history_turns"] == 0
    asyncio.run(run())
    assert seen[1][1] == date(2025, 6, 15)
    assert seen[2][1] is None
    assert seen[1][2][0]["answer"].endswith("2. Điều kiện cần xem xét.")
    assert seen[3][2][-1]["query"] == "Tôi sửa: ký ngày 15/06/2022."
    assert seen[4][2] == []
