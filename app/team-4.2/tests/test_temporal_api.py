import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from rag.temporal.answer import ContextItem, TemporalAnswer
from rag.temporal.models import LegalTimeline, TimeAnchor, TransitionRule
from rag.temporal.qa import TemporalResult

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import server  # noqa: E402

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


class FakeQA:
    def __init__(self):
        self.calls = []

    def ask(self, question, *, calendar_date=None, mask_state=None):
        self.calls.append((question, calendar_date))
        a = TimeAnchor("signing", date(2023, 6, 15), date(2023, 6, 15), "day", "question", "ký ngày 15/06/2023", None, 0.9)
        items = [ContextItem(1, "versioned", "luat:65/2014/QH13", "Luật Nhà ở số 65/2014/QH13", "luat:65/2014/QH13#d23",
                             "Chương II > Điều 23", "Điều 23. Điều kiện ...", date(2015, 7, 1), date(2022, 3, 1), "verified",
                             "verified", ("luat:03/2022/QH15",), ("signing",), "c1"),
                 ContextItem(2, "legacy", None, "bo_luat_dan_su_2015.txt", None, "Điều 117", "Điều 117. ...", None, None,
                             "unversioned", None, (), (), "c2")]
        rule = TransitionRule("luat:27/2023/QH15#d198", "luat:27/2023/QH15", "Điều 198", "Điều 198. ...",
                              "luat:65/2014/QH13", "luat:27/2023/QH15", date(2024, 8, 1), ("signing", "evaluation"))
        ans = TemporalAnswer("Theo [1] và [2] thì ...", [{"issue": "x", "citations": [1], "certainty": "qualified"}],
                             [{"rule_id": rule.rule_id, "assessment": "undetermined"}], ["Ngày bàn giao nhà?"],
                             "qualified", ["certainty.transition_unresolved"])
        return TemporalResult(LegalTimeline((a,), a, ("timeline.calendar_conflict:signing",), NOW), items, [rule], ans,
                              "log1", {"phone": 1}, True)


@pytest.fixture
def client(monkeypatch):
    qa = FakeQA()
    monkeypatch.setattr(server, "get_temporal_qa", lambda: qa)
    return TestClient(server.app), qa


def test_chat_returns_timeline_and_statuses(client):
    c, qa = client
    data = c.post("/api/chat", json={"query": "Ký ngày 15/06/2023 thì sao?", "as_of": "2023-06-15", "session_id": "s"}).json()
    assert qa.calls[0][1] == date(2023, 6, 15)
    assert data["timeline"]["anchors"][0] == {"role": "signing", "start": "2023-06-15", "end": "2023-06-15",
                                              "precision": "day", "source": "question", "evidence": "ký ngày 15/06/2023",
                                              "relative_expression": None, "confidence": 0.9, "matched_text": None}
    assert data["timeline"]["warnings"] == ["timeline.calendar_conflict:signing"]
    s1, s2 = data["sources"]
    assert (s1["store"], s1["document_status"], s1["provision_status"], s1["valid_from"], s1["valid_to"]) == (
        "versioned", "verified", "verified", "2015-07-01", "2022-03-01")
    assert s1["provenance"] == ["luat:03/2022/QH15"] and s1["source"] == "luat:65/2014/QH13"
    assert (s2["store"], s2["document_status"]) == ("legacy", "unversioned")
    assert data["certainty"] == "qualified" and data["downgrade_reasons"] == ["certainty.transition_unresolved"]
    assert data["transition_rules"][0]["source_article"] == "Điều 198"
    assert data["transition_assessments"][0]["assessment"] == "undetermined"
    assert data["follow_up_questions"] == ["Ngày bàn giao nhà?"] and data["log_id"] == "log1"


def test_old_fields_still_present(client):
    c, _ = client
    data = c.post("/api/chat", json={"query": "Hỏi?"}).json()
    for key in ("query", "answer", "refused", "citations", "sources", "trace", "query_pii"):
        assert key in data
    assert [x["n"] for x in data["citations"]] == [1, 2]


@pytest.mark.parametrize("bad", ["2023-02-30", "15/06/2023", "abc"])
def test_invalid_as_of_400(client, bad):
    c, qa = client
    r = c.post("/api/chat", json={"query": "Hỏi?", "as_of": bad})
    assert r.status_code == 400 and qa.calls == []


def test_temporal_init_failure_falls_back_to_old_pipeline(monkeypatch):
    # review I4: kho mới lỗi khởi tạo -> chat vẫn chạy trên pipeline cũ, không 500
    def boom():
        raise RuntimeError("catalog hỏng")

    monkeypatch.setattr(server, "_temporal_qa", None)
    monkeypatch.setattr(server, "_temporal_failed_at", None, raising=False)
    monkeypatch.setattr(server, "_build_temporal_qa", boom)
    monkeypatch.setattr(server, "get_pipeline", lambda: (object(), None))
    monkeypatch.setattr(server, "_sync_ask", lambda q, p, m: {"query": q, "answer": "cũ", "refused": False})
    r = TestClient(server.app).post("/api/chat", json={"query": "Hỏi?"})
    assert r.status_code == 200 and r.json()["answer"] == "cũ"


def test_temporal_qa_is_resolved_off_the_event_loop(monkeypatch):
    # review I3: dựng/kiểm tra chỉ mục không được chạy trên event loop
    import asyncio
    seen = []
    qa = FakeQA()

    def fake_get():
        try:
            asyncio.get_running_loop()
            seen.append("on_loop")
        except RuntimeError:
            seen.append("worker")
        return qa

    monkeypatch.setattr(server, "get_temporal_qa", fake_get)
    TestClient(server.app).post("/api/chat", json={"query": "Hỏi?"})
    assert seen == ["worker"] and qa.calls


def test_build_starts_bm25_then_swaps_to_dense_index(monkeypatch, tmp_path):
    # hybrid mặc định: trả lời ngay bằng BM25 + rerank, Dense dựng ở luồng nền rồi đổi chỉ mục
    from dataclasses import replace
    from types import SimpleNamespace as NS

    import rag.temporal.wiring as wiring
    from rag.config import Settings
    from rag.legal.store import LegalStore

    built = []

    class Idx:
        def __init__(self, dense):
            self.dense, self.chunks = dense, {}

        def build(self):
            built.append(self.dense)
            return 0

    monkeypatch.setattr(wiring, "make_versioned_index", lambda s, llm, store, embedder=None, **kw: Idx(embedder))
    monkeypatch.setattr(wiring, "legal_embedder", lambda s: "EMB")
    settings = replace(Settings.load(), data_dir=tmp_path)
    monkeypatch.setattr(server, "get_pipeline", lambda: (NS(llm=None, retriever=None), settings))
    monkeypatch.setattr(server, "get_legal_service", lambda: NS(store=LegalStore(tmp_path / "c.sqlite")))
    monkeypatch.delenv("LEGAL_DENSE", raising=False)
    started = []
    real_thread = server.threading.Thread

    class SyncThread(real_thread):
        def start(self):
            started.append(self.name)
            self.run()

    monkeypatch.setattr(server.threading, "Thread", SyncThread)
    qa = server._build_temporal_qa()
    assert built == [None, "EMB"] and started == ["legal-dense"] and qa.index.dense == "EMB"

    built.clear()
    monkeypatch.setenv("LEGAL_DENSE", "0")
    qa = server._build_temporal_qa()
    assert built == [None] and qa.index.dense is None
