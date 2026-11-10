import sys
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from rag.temporal.answer import ContextItem, TemporalAnswer
from rag.temporal.models import LegalTimeline, TimeAnchor, TransitionRule
from rag.temporal.qa import TemporalResult
from types import SimpleNamespace as NS
from rag.config import Settings

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import legal_api  # noqa: E402
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
    monkeypatch.setattr(server, "lease_temporal_qa", lambda: nullcontext(qa))
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

    monkeypatch.setattr(legal_api, "get_backend", boom)
    monkeypatch.setattr(server, "get_pipeline", lambda: (object(), None))
    monkeypatch.setattr(server, "_sync_ask", lambda q, p, m, h=None: {"query": q, "answer": "cũ", "refused": False})
    r = TestClient(server.app).post("/api/chat", json={"query": "Hỏi?"})
    assert r.status_code == 200 and r.json()["answer"] == "cũ"
    assert server.get_temporal_qa() is None


def test_chat_without_runtime_falls_back_to_old_pipeline(monkeypatch):
    # kho mới khởi tạo được nhưng chưa có cặp (snapshot, chỉ mục) dùng được -> pipeline cũ
    holder = NS(get=lambda: None, lease=lambda: nullcontext(None))
    monkeypatch.setattr(server, "_legal_holder", lambda: holder)
    monkeypatch.setattr(server, "get_pipeline", lambda: (object(), None))
    monkeypatch.setattr(server, "_sync_ask", lambda q, p, m, h=None: {"query": q, "answer": "cũ", "refused": False})
    assert TestClient(server.app).post("/api/chat", json={"query": "Hỏi?"}).json()["answer"] == "cũ"


def test_chat_leases_runtime_for_whole_request(monkeypatch):
    # cặp (snapshot, chỉ mục) được giữ suốt request: lease mở trước khi hỏi, đóng sau khi trả lời
    events = []
    qa = FakeQA()
    real_ask = qa.ask

    def ask(*a, **kw):
        events.append("ask")
        return real_ask(*a, **kw)

    qa.ask = ask

    @contextmanager
    def lease():
        events.append("lease")
        yield qa
        events.append("release")

    monkeypatch.setattr(server, "lease_temporal_qa", lease)
    assert TestClient(server.app).post("/api/chat", json={"query": "Hỏi?"}).status_code == 200
    assert events == ["lease", "ask", "release"]


def test_temporal_qa_is_resolved_off_the_event_loop(monkeypatch):
    # review I3: dựng/kiểm tra chỉ mục không được chạy trên event loop
    import asyncio
    seen = []
    qa = FakeQA()

    @contextmanager
    def fake_lease():
        try:
            asyncio.get_running_loop()
            seen.append("on_loop")
        except RuntimeError:
            seen.append("worker")
        yield qa

    monkeypatch.setattr(server, "lease_temporal_qa", fake_lease)
    TestClient(server.app).post("/api/chat", json={"query": "Hỏi?"})
    assert seen == ["worker"] and qa.calls


def test_make_runtime_shares_one_dense_index(monkeypatch, tmp_path):
    # LEGAL_DENSE != 0: mọi snapshot dùng chung MỘT VectorIndex mở một lần; LEGAL_DENSE=0: chỉ BM25
    from rag.index.embedder import HashEmbedder
    from rag.index.vector_index import VectorIndex
    from rag.legal.snapshots import SnapshotManager
    import rag.temporal.wiring as wiring

    opened = []

    def fake_open(index_dir, embedder, **kw):
        opened.append(index_dir)
        return VectorIndex(embedder)

    monkeypatch.setattr(VectorIndex, "open_qdrant", staticmethod(fake_open))
    monkeypatch.setattr(wiring, "legal_embedder", lambda s: HashEmbedder(16))
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(server, "get_pipeline", lambda: (NS(llm=None, retriever=None), settings))
    monkeypatch.setattr(server, "_legal_dense", None)
    snaps = SnapshotManager(tmp_path / "legal")
    sid = snaps.current().snapshot_id
    make_runtime = server.make_legal_runtime_factory(snaps)
    monkeypatch.delenv("LEGAL_DENSE", raising=False)
    a, b = make_runtime(sid), make_runtime(sid)
    assert len(opened) == 1 and a.index.dense is b.index.dense is not None
    assert a.snapshot_id == a.index.snapshot_id == sid and a.qa.index is a.index and a.qa.service is a.service
    monkeypatch.setenv("LEGAL_DENSE", "0")
    assert make_runtime(sid).index.dense is None
