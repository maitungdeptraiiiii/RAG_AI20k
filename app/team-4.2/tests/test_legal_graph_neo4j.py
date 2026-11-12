"""Đồ thị luật trên Neo4j thật: công bố bằng con trỏ và lớp truy vấn. Bỏ qua khi thiếu NEO4J_TEST_URI.

Chạy: NEO4J_TEST_URI=bolt://localhost:7687 NEO4J_TEST_PASSWORD=... pytest tests/test_legal_graph_neo4j.py
Dùng không gian tên riêng ("test-legal") nên không đụng đồ thị đang công bố.
"""
import os
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from rag.contracts.graph.neo4j_store import GraphConfig
from rag.legal.graph.build import build_legal_graph, validate
from rag.legal.graph.neo4j_store import LegalGraphStore, legal_graph_config_from_env
from rag.legal.graph.query import GraphNotPublished, LegalGraph
from rag.legal.graph.service import graph_status, sync_legal_graph
from rag.legal.keys import document_key
from rag.legal.models import DocumentRelation, LegalDocument
from rag.legal.service import LegalService
from rag.legal.store import LegalStore

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
CODE, GUIDE, OLD, NEW = "bo-luat:45/2019/QH14", "nghi-dinh:145/2020/NĐ-CP", "nghi-dinh:74/2024/NĐ-CP", "nghi-dinh:293/2025/NĐ-CP"

TEXTS = {
    CODE: "Điều 1. Phạm vi điều chỉnh\nBộ luật này quy định tiêu chuẩn lao động.\n"
          "Điều 21. Nội dung hợp đồng lao động\n1. Hợp đồng phải có nội dung chủ yếu.\n"
          "4. Chính phủ quy định chi tiết khoản 1 Điều này.\n"
          "Điều 25. Thời gian thử việc\n1. Không quá 180 ngày đối với công việc của người quản lý doanh nghiệp.\n"
          "2. Không quá 60 ngày theo quy định tại Điều 21 của Bộ luật này.\n"
          "Điều 220. Hiệu lực thi hành\nBộ luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.\n",
    GUIDE: "NGHỊ ĐỊNH\nCăn cứ Bộ luật Lao động ngày 20 tháng 11 năm 2019;\n"
           "Điều 1. Phạm vi điều chỉnh\nNghị định này quy định chi tiết:\n1. Quản lý lao động theo khoản 4 Điều 21.\n"
           "Điều 2. Hiệu lực thi hành\nNghị định này có hiệu lực thi hành từ ngày 01 tháng 02 năm 2021.\n"
           "Nơi nhận:\n- Như trên;\nPhụ lục I\nDANH MỤC CÔNG VIỆC\n1. Phiên dịch.\n",
    OLD: "Điều 1. Mức lương\nVùng I: 4.960.000 đồng/tháng.\nĐiều 2. Hiệu lực thi hành\n"
         "Nghị định này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2024.\n",
    NEW: "Điều 1. Mức lương\nVùng I: 5.310.000 đồng/tháng.\nĐiều 2. Hiệu lực thi hành\n"
         "1. Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.\n"
         "2. Nghị định số 74/2024/NĐ-CP ngày 30 tháng 6 năm 2024 của Chính phủ hết hiệu lực kể từ ngày Nghị định này "
         "có hiệu lực thi hành.\n",
}
META = {
    CODE: ("Bộ luật", "45/2019/QH14", "Bộ luật Lao động số 45/2019/QH14", date(2019, 11, 20), date(2021, 1, 1)),
    GUIDE: ("Nghị định", "145/2020/NĐ-CP", "Nghị định số 145/2020/NĐ-CP Quy định chi tiết và hướng dẫn thi hành một số "
            "điều của Bộ luật Lao động", date(2020, 12, 14), date(2021, 2, 1)),
    OLD: ("Nghị định", "74/2024/NĐ-CP", "Nghị định số 74/2024/NĐ-CP Quy định mức lương tối thiểu", date(2024, 6, 30), date(2024, 7, 1)),
    NEW: ("Nghị định", "293/2025/NĐ-CP", "Nghị định số 293/2025/NĐ-CP Quy định mức lương tối thiểu", date(2025, 11, 10), date(2026, 1, 1)),
}


class FakeManager:
    """Đủ giao diện của SnapshotManager cho service: current() và store()."""

    def __init__(self, store, snapshot_id):
        self._store, self.snapshot_id = store, snapshot_id

    def current(self):
        return self

    def store(self, snapshot_id=None):
        return self._store


@pytest.fixture(scope="module")
def legal_store(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lg")
    store = LegalStore(tmp / "catalog.sqlite")
    for key, text in TEXTS.items():
        path = tmp / f"{key.replace(':', '_').replace('/', '_')}.txt"
        path.write_text(text, encoding="utf-8")
        kind, number, title, issued, eff = META[key]
        assert document_key(kind, number) == key
        store.upsert_document(LegalDocument(key, "1", title, kind, number, None, issued, eff, None, "Còn hiệu lực", False,
                                            str(path), "f" * 64, NOW))
    store.add_relation(DocumentRelation(NEW, OLD, "THAY_THE", "hết hiệu lực: Nghị định số 74/2024/NĐ-CP", "confirmed"))
    LegalService(store, now=lambda: NOW).build_all()
    return store


@pytest.fixture(scope="module")
def graph_store():
    uri = os.environ.get("NEO4J_TEST_URI")
    if not uri:
        pytest.skip("Cần NEO4J_TEST_URI để chạy kiểm thử Neo4j thật")
    store = LegalGraphStore(GraphConfig(uri, os.environ.get("NEO4J_TEST_USER", "neo4j"),
                                        os.environ.get("NEO4J_TEST_PASSWORD", ""), "neo4j"), name="test-legal")
    store.clear()
    yield store
    store.clear()
    store.close()


def test_env_config():
    assert legal_graph_config_from_env({}) is None
    assert legal_graph_config_from_env({"LEGAL_GRAPH": "1", "NEO4J_PASSWORD": "p"}).uri == "bolt://localhost:7687"
    with pytest.raises(ValueError):
        legal_graph_config_from_env({"LEGAL_GRAPH": "1"})


def test_sync_disabled_and_status_without_store(legal_store):
    manager = FakeManager(legal_store, "t-a")
    assert sync_legal_graph(manager, None) == {"status": "disabled"}
    assert graph_status(manager, None)["stale"] is True


def test_publish_switches_pointer_and_survives_interruption(legal_store, graph_store):
    with pytest.raises(GraphNotPublished):
        LegalGraph(graph_store).text_at(f"{CODE}#d25", date(2025, 3, 1))
    a = build_legal_graph(legal_store, "t-a")
    assert validate(a, legal_store) == []
    graph_store.publish(a, batch=7)
    assert graph_store.current()["current_build"] == a.build_id
    count = "MATCH (n:LGNode {graph: 'test-legal'}) RETURN n.build_id AS b, count(*) AS c"
    assert graph_store.run(count) == [{"b": a.build_id, "c": len(a.nodes)}]
    edges = graph_store.run("MATCH (:LGNode {graph: 'test-legal'})-[e]->() RETURN count(e) AS c")[0]["c"]
    assert edges == len(a.edges)

    b = build_legal_graph(legal_store, "t-b")

    def boom():
        raise RuntimeError("ngắt giữa chừng")

    with pytest.raises(RuntimeError):
        graph_store.publish(b, before_switch=boom)
    assert graph_store.current()["current_build"] == a.build_id         # người đọc vẫn thấy build cũ nguyên vẹn
    assert LegalGraph(graph_store).text_at(f"{CODE}#d25.k1", date(2025, 3, 1))["in_force"]

    graph_store.publish(b)                                              # dọn phần dở dang rồi công bố lại
    assert graph_store.current()["snapshot_id"] == "t-b"
    assert graph_store.run(count) == [{"b": b.build_id, "c": len(b.nodes)}]
    manager = FakeManager(legal_store, "t-b")
    assert sync_legal_graph(manager, graph_store)["status"] == "up_to_date"
    assert graph_status(manager, graph_store)["stale"] is False
    assert graph_status(FakeManager(legal_store, "t-c"), graph_store)["stale"] is True


def test_queries(legal_store, graph_store):
    graph_store.publish(build_legal_graph(legal_store, "t-b"))
    g = LegalGraph(graph_store)

    got = g.text_at(f"{CODE}#d25.k1", date(2025, 3, 1))
    assert got["in_force"] and "180 ngày" in got["text"]
    assert got["citation"] | {} == got["citation"] and got["citation"]["doc_number"] == "45/2019/QH14"
    assert got["citation"]["label"] == "khoản 1 Điều 25" and got["citation"]["valid_from"] == "2021-01-01"
    assert g.text_at(f"{CODE}#d25", date(2025, 3, 1))["title"] == "Thời gian thử việc"
    assert g.text_at(f"{CODE}#d25.k1", date(2020, 6, 1))["reason"] == "not_yet_in_force"
    assert g.text_at(f"{CODE}#d999", date(2025, 3, 1))["reason"] == "unknown_provision"
    gone = g.text_at(f"{OLD}#d1", date(2026, 2, 1))                    # nghị định đã bị thay thế
    assert (gone["in_force"], gone["reason"], gone["until"]) == (False, "no_longer_in_force", "2026-01-01")

    for day, number in [(date(2025, 1, 1), "74/2024/NĐ-CP"), (date(2026, 2, 1), "293/2025/NĐ-CP")]:
        for start in (OLD, NEW):
            assert [d["document"]["doc_number"] for d in g.applicable(start, day)] == [number]
    assert g.applicable(OLD, date(2024, 1, 1)) == []

    guidance = g.guidance(f"{CODE}#d21", date(2025, 3, 1))              # hỏi ở cấp Điều, nghị định hướng dẫn khoản 4
    assert [(x["target"], x["citation"]["provision_id"]) for x in guidance] == [(f"{CODE}#d21.k4", f"{GUIDE}#d1.k1")]
    assert g.guidance(f"{CODE}#d21.k4", date(2021, 1, 15)) == []        # nghị định chưa có hiệu lực

    out = g.references(f"{CODE}#d25", date(2025, 3, 1))
    assert [(r["source"], r["target"], r["kind"]) for r in out] == [(f"{CODE}#d25.k2", f"{CODE}#d21", "cite")]
    incoming = {r["citation"]["provision_id"] for r in g.references(f"{CODE}#d21", date(2025, 3, 1), "in")}
    assert incoming == {f"{CODE}#d25.k2", f"{GUIDE}#d1.k1", f"{CODE}#d21.k4"}

    changes = g.changes(f"{OLD}#d1", date(2024, 1, 1), date(2026, 6, 1))
    assert [(c["citation"]["valid_from"], c["citation"]["valid_to"]) for c in changes] == [("2024-07-01", "2026-01-01")]

    appendices = g.appendices(GUIDE)
    assert [(a["number"], a["kind"]) for a in appendices] == [("I", "list")] and "Phiên dịch" in appendices[0]["text"]
    assert g.status()["snapshot_id"] == "t-b"
