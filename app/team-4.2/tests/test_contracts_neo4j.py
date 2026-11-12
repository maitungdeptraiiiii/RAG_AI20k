import os
from datetime import datetime, timezone

import pytest

from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.oplog import OperationLog
from rag.contracts.graph.neo4j_store import ContractGraphStore, GraphConfig, graph_config_from_env


def test_env_config():
    assert graph_config_from_env({}) is None
    with pytest.raises(ValueError):
        graph_config_from_env({"CONTRACT_GRAPH": "1"})
    c = graph_config_from_env({"CONTRACT_GRAPH": "1", "NEO4J_PASSWORD": "p"})
    assert (c.uri, c.user, c.database) == ("bolt://localhost:7687", "neo4j", "neo4j")


needs_neo4j = pytest.mark.skipif(not os.environ.get("NEO4J_TEST_URI"), reason="cần NEO4J_TEST_URI")


@pytest.fixture
def neo4j_store():
    cfg = GraphConfig(os.environ["NEO4J_TEST_URI"], "neo4j",
                      os.environ.get("NEO4J_TEST_PASSWORD", ""), "neo4j")
    store = ContractGraphStore(cfg)
    store.ensure_schema()
    try:
        yield store
    finally:
        for cid in ("cA", "cB"):
            store.delete(cid)
        store.close()


@pytest.fixture
def build_for():
    def make(cid, text):
        b, _ = build_graph(cid, [PageText(1, text)], OperationLog(cid), file_checksum="x",
                           built_at=datetime(2026, 11, 12, tzinfo=timezone.utc))
        return b
    return make


@needs_neo4j
def test_publish_replaces_and_isolates(neo4j_store, build_for):
    neo4j_store.publish(build_for("cA", "Điều 1. A\nĐiều 2. B"))
    neo4j_store.publish(build_for("cB", "Điều 1. X"))
    neo4j_store.publish(build_for("cA", "Điều 1. A"))
    rows = neo4j_store.run("MATCH (n:CGNode {contract_id:'cA'}) RETURN n.node_id AS id")
    ids = {r["id"] for r in rows}
    assert "cA:p0.d2@1" not in ids and not any(i.startswith("cB") for i in ids)
    assert neo4j_store.current_build_id("cB") is not None


def test_driver_has_short_timeouts(monkeypatch):
    import neo4j

    seen = {}

    class FakeDriver:
        def close(self):
            pass

    def fake_driver(uri, **kw):
        seen.update(kw, uri=uri)
        return FakeDriver()
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", fake_driver)
    ContractGraphStore(GraphConfig("bolt://127.0.0.1:7699", "neo4j", "pw", "neo4j"))
    assert seen["max_transaction_retry_time"] <= 2
    assert seen["connection_timeout"] <= 3 and seen["connection_acquisition_timeout"] <= 3
