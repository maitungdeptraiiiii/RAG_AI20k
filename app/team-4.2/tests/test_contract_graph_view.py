"""ContractGraphView: cùng một bộ test cho bản bộ nhớ và bản Neo4j (Neo4j bỏ qua khi thiếu NEO4J_TEST_URI)."""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rag.bridge.facts_map import fact_ops
from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.oplog import OperationLog
from rag.contracts.graph.view import MemoryGraphView, Neo4jGraphView, open_view

T = datetime(2026, 11, 16, tzinfo=timezone.utc)
CID = "cv1"
DEMO = Path(__file__).resolve().parents[3] / "data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt"
FACTS = {"candidates": {"salary": [
    {"value": "15.000.000 đồng/tháng", "unit": "p0.d2", "quote": "15.000.000 đồng/tháng"},
    {"value": "17.000.000 đồng/tháng", "unit": "p2.d1",
     "quote": "được điều chỉnh từ 15.000.000 đồng/tháng lên 17.000.000 đồng/tháng"}]}}


def demo_build(cid=CID):
    log = OperationLog(cid)
    for o in fact_ops(FACTS, cid, at=T):
        log.add(o)
    b, _ = build_graph(cid, [PageText(1, DEMO.read_text(encoding="utf-8"))], log, file_checksum="x", built_at=T)
    assert b.problems == ()
    return b


@pytest.fixture(scope="module")
def memory_view():
    return MemoryGraphView(demo_build())


@pytest.fixture(scope="module", params=["memory", "neo4j"])
def view(request, memory_view):
    if request.param == "memory":
        yield memory_view
        return
    uri = os.environ.get("NEO4J_TEST_URI")
    if not uri:
        pytest.skip("cần NEO4J_TEST_URI")
    from rag.contracts.graph.neo4j_store import ContractGraphStore, GraphConfig
    store = ContractGraphStore(GraphConfig(uri, "neo4j", os.environ.get("NEO4J_TEST_PASSWORD", ""), "neo4j"))
    store.ensure_schema()
    store.publish(demo_build())
    try:
        yield Neo4jGraphView(store, CID)
    finally:
        store.delete(CID)
        store.close()


A2, A6, P2 = f"{CID}:p0.d2@1", f"{CID}:p0.d6@1", f"{CID}:p2.d1@1"


def test_node_shape(view):
    n = view.node(A2)
    assert n["node_type"] == "Unit" and n["uid"] == "p0.d2" and n["label"] == "Điều 2" and "contract_id" not in n and "build_id" not in n
    assert view.node(CID)["node_type"] == "Contract"


def test_neighbors_article6_refers_to_article2(view):
    hops = view.neighbors(A6, rel_types=["REFERS_TO"], direction="out")
    assert [h["node"]["node_id"] for h in hops] == [A2, f"{CID}:p1.pre@1"]     # Điều 2 và "Phụ lục 01"
    assert hops[0]["rel"] == "REFERS_TO" and hops[0]["dir"] == "out" and hops[0]["props"]["raw"] == "Điều 2"


def test_article2_has_incoming_amendment_with_date(view):
    hops = view.neighbors(A2, rel_types=["AMENDS"], direction="in")
    assert [(h["node"]["node_id"], h["dir"], h["props"]["valid_from"]) for h in hops] == [(P2, "in", "2025-07-01")]


def test_path_probation_unit_to_article2(view):
    src = view.search_units("thử việc")[0]["node_id"]
    assert src == A6
    p = view.path(src, A2, max_hops=3)
    assert [(h["rel"], h["dir"], h["node"]["node_id"]) for h in p] == [("REFERS_TO", "out", A2)]
    assert view.path(A2, A2) == []


def test_find_contract_facts(view):
    facts = view.find("ContractFact", name="base_salary_vnd")
    assert sorted(f["value"] for f in facts) == [15000000, 17000000]
    with pytest.raises(ValueError):
        view.find("Nope")


def test_same_answers_on_both_backends(view, memory_view):
    for nid in (A2, CID, P2):
        assert view.neighbors(nid) == memory_view.neighbors(nid)
    assert view.subgraph(A2, hops=1) == memory_view.subgraph(A2, hops=1)
    assert view.path(A6, P2, max_hops=4) == memory_view.path(A6, P2, max_hops=4)
    assert view.search_units("lương") == memory_view.search_units("lương")


def test_subgraph_hops_and_limit(view):
    g = view.subgraph(A2, hops=1)
    ids = {n["node_id"] for n in g["nodes"]}
    assert {A2, A6, P2} <= ids
    assert all(e["src"] in ids and e["dst"] in ids for e in g["edges"])
    small = view.subgraph(CID, hops=2, limit=5)
    assert len(small["nodes"]) == 5 and small["nodes"][0]["node_id"] == CID


def test_bad_rel_type_and_hops_raise(view):
    with pytest.raises(ValueError):
        view.neighbors(CID, rel_types=["DELETE"])
    with pytest.raises(ValueError):
        view.path(CID, A2, max_hops=9)


def test_foreign_and_missing_nodes(view):
    assert view.node("c2:p0.d1@1") is None and view.neighbors("c2:p0.d1@1") == []
    assert view.path(CID, "c2:p0.d1@1") is None
    assert view.subgraph("c2:p0.d1@1") == {"nodes": [], "edges": []}


def test_long_text_truncated():
    b = demo_build()
    big = MemoryGraphView(b)
    n = big.node(f"{CID}:p1.pre@1") or big.node(f"{CID}:p0.pre@1")
    assert len(n["text"]) <= 600 and n.get("truncated") is True


def test_empty_contract_view():
    b, _ = build_graph("c9", [PageText(1, "")], OperationLog("c9"), file_checksum="x", built_at=T)
    v = MemoryGraphView(b)
    assert v.search_units("lương") == [] and v.path("c9", "c9", max_hops=1) == []
    assert v.find("ContractFact") == []


def test_open_view_falls_back_to_memory():
    b = demo_build()
    assert open_view(b, {"published": False}, None).backend == "memory"
    assert open_view(b, {"published": True}, None).backend == "memory"


def test_search_units_matches_tail_of_long_unit():
    """Từ khoá nằm sau ký tự 600 vẫn tìm thấy; lời văn trả về dài hơn TEXT_LIMIT nhưng không quá UNIT_TEXT_LIMIT."""
    from rag.contracts.graph.view import TEXT_LIMIT, UNIT_TEXT_LIMIT
    filler = "Người lao động thực hiện công việc theo phân công. " * 30
    text = f"Điều 3. Điều kiện làm việc\n{filler}\nNgười sử dụng lao động cấp phát găng tay bảo hộ lao động miễn phí."
    assert len(text) > TEXT_LIMIT
    b, _ = build_graph("c8", [PageText(1, text)], OperationLog("c8"), file_checksum="x", built_at=T)
    v = MemoryGraphView(b)
    hits = v.search_units("găng tay bảo hộ")
    assert hits and "găng tay bảo hộ" in hits[0]["text"] and len(hits[0]["text"]) <= UNIT_TEXT_LIMIT
    assert all(len(n["text"]) <= TEXT_LIMIT for n in v.find("Unit") if "text" in n)
