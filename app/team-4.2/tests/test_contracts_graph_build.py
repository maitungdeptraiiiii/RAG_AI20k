import dataclasses
from datetime import datetime, timezone

from rag.contracts.doc import PageText
from rag.contracts.graph.build import GraphEdge, build_graph, validate
from rag.contracts.graph.oplog import OperationLog, human_op

T = datetime(2026, 11, 12, tzinfo=timezone.utc)
PAGES = [PageText(1, "Bên A: Nguyễn Văn An, CCCD 001203004567\nĐiều 1. Giá\n1. Giá 30 triệu đồng.\n"
                     "2. Thanh toán theo khoản 1 Điều này.")]


def test_deterministic_ids_and_content():
    b1, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    b2, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T.replace(year=2027))
    assert b1.build_id == b2.build_id and b1.nodes == b2.nodes
    ids = {n.node_id for n in b1.nodes}
    assert {"c1", "c1:p0", "c1:p0.d1@1", "c1:p0.d1.k1@1", "c1:p0.d1.k1#v1"} <= ids
    assert GraphEdge("REFERS_TO", "c1:p0.d1.k2@1", "c1:p0.d1.k1@1", {"raw": "khoản 1 Điều này"}) in b1.edges
    assert validate(b1) == []


def test_text_is_masked_amounts_are_not():
    b, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    texts = " ".join(str(n.props.get("text", "")) for n in b.nodes)
    assert "001203004567" not in texts and "[HD_" in texts and "30 triệu đồng" in texts


def test_field_ops_change_build_and_contract_props():
    log = OperationLog("c1")
    log.add(human_op("c1", "SET_FIELD", "sign_date", {"value": "2023-03-15"}, "Tùng", at=T))
    b, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)
    base, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    assert b.build_id != base.build_id
    assert next(n for n in b.nodes if n.node_id == "c1").props["sign_date"] == "2023-03-15"


def test_validate_catches_bad_edges_and_foreign_nodes():
    b, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    bad = dataclasses.replace(b, edges=b.edges + (GraphEdge("HAS_VALUE", "c1", "c1:p0", {}),))
    assert any("HAS_VALUE" in p for p in validate(bad))
    foreign = dataclasses.replace(b, nodes=b.nodes + (dataclasses.replace(b.nodes[0], node_id="c2", props={**b.nodes[0].props, "contract_id": "c2"}),))
    assert any("c2" in p for p in validate(foreign))
