"""Regression for model-generated evaluation-date boilerplate, JSON and SSE."""
import asyncio
import json

import httpx
import pytest

from rag.generate.style import present_answer, PRESENTATION_VERSION
from rag.conversation import conversation_context
from tests.test_think_routing import server

USER_SAMPLE = (
    "Mốc 10/11/2026 là ngày muốn đánh giá pháp luật, nhưng ngữ cảnh không cung cấp "
    "căn cứ đã xác minh phiên bản có hiệu lực tại mốc đó. Do đó, các nhận định pháp lý "
    "trên chỉ giới hạn ở nội dung tài liệu tham khảo được cung cấp.")
LEGAL = "Trách nhiệm cụ thể phụ thuộc vào thương tích và hoàn cảnh của vụ việc. [1]"


def test_exact_user_report_keeps_plain_uncertainty_without_internal_date():
    presented = present_answer(LEGAL + "\n\n" + USER_SAMPLE)
    assert LEGAL in presented.text
    assert "10/11/2026" not in presented.text
    assert "Mốc" not in presented.text and "ngữ cảnh" not in presented.text
    assert "chưa đủ căn cứ" in presented.text
    assert presented.qualified
    assert presented.suppressed_sentences == 2
    assert present_answer(presented.text).text == presented.text


@pytest.mark.parametrize("text", [
    "Hợp đồng được ký ngày 15/06/2023, tranh chấp phát sinh ngày 15/09/2025. [1]",
    "Luật có hiệu lực từ ngày 01/08/2024. [1]",
    "Mốc 01/08/2024 là ngày Luật Nhà ở có hiệu lực, thay thế phiên bản trước. [1]",
    "Thời hiệu khởi kiện được tính từ ngày quyền và lợi ích bị xâm phạm. [1]",
    "Sự việc xảy ra ngày nào?",
    "Nếu hành vi gây thương tích thì có thể phải bồi thường. [1]",
])
def test_substantive_dates_questions_and_legal_claims_are_unchanged(text):
    assert present_answer(text).text == text
    assert present_answer(text).suppressed_sentences == 0


def test_history_does_not_reinject_old_boilerplate_or_change_user_facts():
    context = conversation_context([{"query": "Tôi ký hợp đồng ngày 10/11/2026.",
                                     "answer": LEGAL + "\n\n" + USER_SAMPLE}])
    assert "10/11/2026" in context["user_statements"][0]["text"]
    answer = context["recent_turns"][0]["assistant_context_unverified"]
    assert LEGAL in answer and "Mốc 10/11/2026" not in answer


@pytest.mark.parametrize("heading", ["**Mốc pháp lý đang sử dụng**", "### Ngày đánh giá: 10/11/2026",
                                   "Mốc đánh giá: 2026-11-10"])
def test_model_generated_metadata_headings_are_not_shown(heading):
    assert present_answer(heading + "\n\n" + LEGAL).text == LEGAL


def test_normal_http_emits_first_token_before_backend_finishes(server, monkeypatch):
    from tests.test_think_routing import request_for
    finished = False

    def events(*args):
        nonlocal finished
        yield server._sse({"type": "token", "delta": "Xin "})
        yield server._sse({"type": "token", "delta": "chào."})
        finished = True
        yield server._sse({"type": "done", "answer": "Xin chào."})

    monkeypatch.setattr(server, "_sync_stream", events)

    async def run():
        response = await server.handle_chat(request_for({"query": "Chào", "stream": True}))
        first = await anext(response.body_iterator)
        assert json.loads(first[6:]) == {"type": "token", "delta": "Xin "}
        assert not finished
        rest = [frame async for frame in response.body_iterator]
        assert finished and json.loads(rest[-1][6:])["type"] == "done"
    asyncio.run(run())


@pytest.mark.parametrize("think", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_http_filters_final_answer_and_preserves_think_verified_emission(server, monkeypatch, think, stream):
    monkeypatch.setattr(server, "get_agent_pipeline", lambda as_of=None: object())

    def answer(*args):
        return {"answer": LEGAL + "\n\n" + USER_SAMPLE, "certainty": "firm",
                "issues": [{"certainty": "firm"}],
                "citations": [{"n": 1}], "sources": [{"n": 1}],
                "timeline": {"primary": {"start": "2026-11-10"}}}

    def events(*args):
        yield server._sse({"type": "progress", "stage": "prepare"})
        yield server._sse({"type": "token", "delta": LEGAL + "\n\nMốc 10/"})
        yield server._sse({"type": "token", "delta": USER_SAMPLE[10:]})
        yield server._sse({"type": "done", **answer()})

    monkeypatch.setattr(server, "_sync_chat", answer)
    monkeypatch.setattr(server, "_sync_agent", answer)
    monkeypatch.setattr(server, "_sync_stream", events)
    monkeypatch.setattr(server, "_sync_agent_stream", events)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            response = await client.post("/api/chat", json={"query": "Đánh người có bị xử lý không?",
                "session_id": "presentation", "stream": stream, "think": think})
            assert response.status_code == 200
            if stream:
                frames = [json.loads(frame[6:]) for frame in response.text.strip().split("\n\n")]
                tokens = "".join(frame["delta"] for frame in frames if frame["type"] == "token")
                data = frames[-1]
                assert frames[0]["type"] == "progress"
                assert data["type"] == "done"
                if think:
                    assert tokens == data["answer"]
                    assert "Mốc" not in tokens and "10/11/2026" not in tokens
                else:
                    # Normal mode now streams provider deltas immediately;
                    # the final response still runs presentation cleanup.
                    assert len([frame for frame in frames if frame["type"] == "token"]) == 2
                    assert LEGAL in tokens
            else:
                data = response.json()
            assert LEGAL in data["answer"] and "Mốc" not in data["answer"]
            assert data["certainty"] == "qualified"
            assert data["issues"][0]["certainty"] == "qualified"
            assert data["trace"]["presentation"]["version"] == PRESENTATION_VERSION
            assert data["citations"] == [{"n": 1}]
            assert data["timeline"]["primary"]["start"] == "2026-11-10"
            history = server._conversations.begin("presentation")
            assert history[-1]["answer"] == data["answer"]
            server._conversations.release("presentation")
    asyncio.run(run())
