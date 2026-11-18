"""Text2Cypher cho agent: kiểm câu truy vấn trước khi chạy (không cần Neo4j) và chạy thật trên Neo4j (bỏ qua khi
thiếu NEO4J_TEST_URI)."""
import os

import pytest

from rag.bridge.catalog import load_catalog
from rag.contracts.graph.cypher import check_cypher, clean_rows
from rag.contracts.graph.tools import call_tool, make_tools
from rag.contracts.graph.view import MemoryGraphView, Neo4jGraphView
from tests.test_contract_graph_view import CID, demo_build

CAT = load_catalog()
OK = [
    "MATCH (u:Unit {contract_id: $cid}) RETURN count(u) AS n",
    "MATCH (c:Contract {contract_id: $cid})-[:HAS_PART]->(p:Part)-[:HAS_UNIT]->(u:Unit) RETURN p.title, count(u)",
    "MATCH (a:Unit {contract_id: $cid})-[e:AMENDS]->(b:Unit) RETURN a.label, b.label, e.valid_from ORDER BY e.valid_from",
    "MATCH (u:Unit {contract_id: $cid}) WHERE u.text CONTAINS 'xóa bỏ' RETURN u.label",       # chữ trong chuỗi
    "// đếm điều khoản, không DELETE gì cả\nMATCH (u:Unit {contract_id: $cid}) RETURN count(u)",
    "MATCH (u:Unit {contract_id: $cid}) OPTIONAL MATCH (u)-[:HAS_VALUE]->(v:Value) RETURN u.label, collect(v.raw)",
    # biến neo gián tiếp (cùng mẫu liền với nút có $cid), và biến được WITH mang theo nguyên tên
    "MATCH (c:Contract {contract_id: $cid})-[:HAS_PART]->(main:Part {kind: 'main'}) "
    "OPTIONAL MATCH (main)-[:HAS_UNIT]->(u:Unit) RETURN count(u)",
    "MATCH (c:Contract {contract_id: $cid}) WITH c, 1 AS x OPTIONAL MATCH (c)-[:HAS_PART]->(p:Part) RETURN count(p)",
]
BAD = {
    "MATCH (u:Unit {contract_id: $cid}) DETACH DELETE u": "ghi",
    "CREATE (n:Unit {contract_id: $cid}) RETURN n": "ghi",
    "MATCH (u:Unit {contract_id: $cid}) SET u.text = 'x' RETURN u": "ghi",
    "CALL db.labels() YIELD label RETURN label": "CALL",
    "MATCH (u:Unit {contract_id: $cid}) CALL apoc.help('x') YIELD name RETURN name": "CALL",
    "LOAD CSV FROM 'file:///x' AS r RETURN r": "LOAD",
    "MATCH (u:Unit) RETURN u.text": "$cid",
    "MATCH (u:Unit {contract_id: $cid}), (m:Unit) RETURN m.text": "dấu phẩy",
    "MATCH (u:Unit {contract_id: $cid}) MATCH (m:Unit) WHERE u.contract_id = $cid RETURN m.text": "$cid",
    "MATCH (u:Unit {contract_id: $cid}) RETURN COUNT { (m:Unit) } AS n": "truy vấn con",
    "MATCH (u:Unit {contract_id: $cid}) RETURN [(m:Unit) | m.text] AS t": "truy vấn con",
    "MATCH (u:Unit {contract_id: 'c2'}) RETURN u": "contract_id",
    "MATCH (p:Provision {contract_id: $cid}) RETURN p": "Provision",
    "MATCH (u:Unit {contract_id: $cid})-[:CHANGED_BY]->(x) RETURN x": "CHANGED_BY",
    "MATCH (u:Unit {contract_id: $cid}) RETURN u UNION MATCH (m:LawDoc) RETURN m AS u": "LawDoc",
    "MATCH (u:Unit {contract_id: $cid})": "RETURN",
}


@pytest.mark.parametrize("query", OK)
def test_allowed_queries(query):
    assert check_cypher(query) is None


@pytest.mark.parametrize("query,why", BAD.items())
def test_rejected_queries(query, why):
    problem = check_cypher(query)
    assert problem is not None and why.casefold() in problem.casefold(), problem


def test_clean_rows_rejects_foreign_contract_and_hides_ids():
    rows = [{"u": {"contract_id": "cv1", "build_id": "b1", "label": "Điều 2"}, "n": 3}]
    assert clean_rows(rows, "cv1") == [{"u": {"label": "Điều 2"}, "n": 3}]
    with pytest.raises(ValueError):
        clean_rows([{"u": {"contract_id": "c2", "label": "x"}}], "cv1")


def test_tool_absent_on_memory_backend():
    tools = make_tools(MemoryGraphView(demo_build()), catalog=CAT, day=None, sign_date=None)
    assert "cypher_query" not in tools


@pytest.fixture(scope="module")
def neo4j_tools():
    uri = os.environ.get("NEO4J_TEST_URI")
    if not uri:
        pytest.skip("cần NEO4J_TEST_URI")
    from rag.contracts.graph.neo4j_store import ContractGraphStore, GraphConfig
    store = ContractGraphStore(GraphConfig(uri, "neo4j", os.environ.get("NEO4J_TEST_PASSWORD", ""), "neo4j"))
    store.ensure_schema()
    store.publish(demo_build())
    store.publish(demo_build("cv2"))
    try:
        yield make_tools(Neo4jGraphView(store, CID), catalog=CAT, day=None, sign_date=None)
    finally:
        store.delete(CID)
        store.delete("cv2")
        store.close()


def test_cypher_counts_match_memory(neo4j_tools):
    memory = MemoryGraphView(demo_build())
    out = call_tool(neo4j_tools, "cypher_query", {"query": "MATCH (u:Unit {contract_id: $cid}) RETURN count(u) AS n"})
    assert out["rows"] == [{"n": len(memory.find("Unit"))}] and out["truncated"] is False


def test_cypher_lists_amendments(neo4j_tools):
    out = call_tool(neo4j_tools, "cypher_query", {"query": (
        "MATCH (a:Unit {contract_id: $cid})-[e:AMENDS]->(b:Unit) RETURN a.label AS src, b.label AS dst, "
        "e.valid_from AS valid_from")})
    assert [(r["dst"], r["valid_from"]) for r in out["rows"]] == [("Điều 2", "2025-07-01")]


def test_cypher_returns_nodes_without_ids(neo4j_tools):
    out = call_tool(neo4j_tools, "cypher_query", {"query": "MATCH (u:Unit {contract_id: $cid, uid: 'p0.d2'}) RETURN u"})
    assert out["rows"][0]["u"]["label"] == "Điều 2" and "contract_id" not in out["rows"][0]["u"]


def test_cypher_row_limit(neo4j_tools):
    out = call_tool(neo4j_tools, "cypher_query", {"query": "MATCH (n:CGNode {contract_id: $cid}) RETURN n.node_id AS id"})
    assert len(out["rows"]) <= 50 and out["truncated"] is True


def test_cypher_syntax_error_is_returned_for_retry(neo4j_tools):
    out = call_tool(neo4j_tools, "cypher_query", {"query": "MATCH (u:Unit {contract_id: $cid}) RETURN u.label ORDER"})
    assert "error" in out and "Cypher" in out["error"]


def test_cypher_cannot_see_other_contract(neo4j_tools):
    out = call_tool(neo4j_tools, "cypher_query", {"query": "MATCH (u:Unit {contract_id: $cid}) RETURN count(u) AS n"})
    other = call_tool(neo4j_tools, "cypher_query", {"query": "MATCH (u:Unit {contract_id: 'cv2'}) RETURN count(u) AS n"})
    assert out["rows"][0]["n"] > 0 and "error" in other


def test_bound_variable_after_with_is_not_trusted():
    q = "MATCH (u:Unit {contract_id: $cid}) WITH count(u) AS c MATCH (u)-[:HAS_VALUE]->(v) RETURN v.raw"
    assert "$cid" in check_cypher(q)
    renamed = "MATCH (u:Unit {contract_id: $cid}) WITH u AS w MATCH (u)-[:HAS_VALUE]->(v) RETURN v.raw"
    assert "$cid" in check_cypher(renamed)
