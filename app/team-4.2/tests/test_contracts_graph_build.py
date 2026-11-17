import dataclasses
from datetime import datetime, timezone

from rag.contracts.doc import PageText
from rag.contracts.graph.build import GraphEdge, GraphNode, build_graph, validate
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


PII_PAGES = [PageText(1, "HỢP ĐỒNG THUÊ NHÀ\nBên A: Ông Nguyễn Văn A, CCCD số: 001203004567 Ngày cấp: 12/03/2021\n"
                         "Điện thoại: 0912345678\nNgày sinh: 01/02/1990\n\nĐiều 1. Đối tượng\nBên A cho thuê nhà.\n")]


def test_pii_never_reaches_value_nodes():
    b, doc = build_graph("c1", PII_PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    for n in b.nodes:
        if n.label == "Value":
            blob = " ".join(str(v) for v in n.props.values())
            assert "1203004567" not in blob and "912345678" not in blob, n
    assert not any("1203004567" in v.raw or "912345678" in v.raw for v in doc.values)
    assert b.problems == ()


def test_validate_flags_pii_in_any_string_property():
    b, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    leak = GraphNode("c1:p0.pre#v9", "Value", {"contract_id": "c1", "build_id": b.build_id,
                                               "kind": "duration", "raw": "001203004567 Ngày"})
    bad = dataclasses.replace(b, nodes=b.nodes + (leak,))
    assert any("c1:p0.pre#v9" in p and "raw" in p for p in validate(bad))
    unit = next(n for n in b.nodes if n.label == "Unit")
    refs = dataclasses.replace(unit, props={**unit.props, "unresolved_refs": ["gọi 0912345678"]})
    bad = dataclasses.replace(b, nodes=tuple(refs if n is unit else n for n in b.nodes))
    assert any("unresolved_refs" in p for p in validate(bad))
    edge = GraphEdge("REFERS_TO", "c1:p0.d1.k2@1", "c1:p0.d1.k1@1", {"raw": "CCCD 001203004567"})
    bad = dataclasses.replace(b, edges=b.edges + (edge,))
    assert any("REFERS_TO" in p and "raw" in p for p in validate(bad))


def test_huge_amount_is_encodable():
    pages = [PageText(1, "Điều 1. Giá\nGiá 99.999.999.999.999.999.999 tỷ đồng.")]
    b, _ = build_graph("c1", pages, OperationLog("c1"), file_checksum="x", built_at=T)
    v = next(n for n in b.nodes if n.label == "Value")
    assert v.props["amount"] == "99999999999999999999000000000" and b.problems == ()
    node = dataclasses.replace(v, props={**v.props, "amount": 2 ** 70})
    bad = dataclasses.replace(b, nodes=tuple(node if n is v else n for n in b.nodes))
    assert any("amount" in p for p in validate(bad))


# ── lớp khái niệm (spec 2026-11-14-contract-concept-check §10) ──
from rag.bridge.facts_map import party_ops  # noqa: E402
from rag.contracts.graph.oplog import machine_op  # noqa: E402


def _concept_op(concept="leave.annual", uid="p0.d1.k1", quote="Giá 30 triệu đồng", status="auto_accepted", slots=None):
    content = {"kind": "concept", "concept_id": concept, "slots_raw": {},
               "slots": slots if slots is not None else {"annual_leave": {"value": 12, "unit": "day"}},
               "catalog_version": "t", "found_by": "tagger"}
    return machine_op("c1", "ASSERT", concept, content, "llm", status, source_uid=uid, quote=(quote,), at=T)


def test_party_ops_from_facts():
    facts = {"parties": [{"name": "Công ty TNHH A", "role": "Người sử dụng lao động"},
                         {"name": "Nguyễn Văn An", "role": "Người lao động"}, {"name": "X", "role": "Người làm chứng"}]}
    ops = party_ops(facts, "c1", at=T)
    assert sorted(o.content["role"] for o in ops) == ["NLD", "NSDLD"]
    assert all(o.origin == "rule" and o.status == "auto_accepted" for o in ops)
    assert all("Nguyễn" not in str(o.content) and "Công ty" not in str(o.content) for o in ops)


def test_concept_instances_and_parties_in_graph():
    log = OperationLog("c1")
    for op in party_ops({"parties": [{"role": "Người lao động"}, {"role": "Người sử dụng lao động"}]}, "c1", at=T):
        log.add(op)
    good = _concept_op()
    log.add(good)
    log.add(_concept_op("wage.night_pay", status="rejected", slots={}))
    b, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)
    labels = {n.node_id: n.label for n in b.nodes}
    ci = f"c1:ci:{good.op_id}"
    assert labels[ci] == "ConceptInstance" and labels["c1:party:NLD"] == "Party"
    assert sum(1 for x in labels.values() if x == "ConceptInstance") == 1
    node = next(n for n in b.nodes if n.node_id == ci)
    assert node.props["concept_id"] == "leave.annual" and node.props["slot_annual_leave"] == 12
    assert node.props["slot_annual_leave_unit"] == "day"
    edges = {(e.type, e.src, e.dst) for e in b.edges}
    assert ("HAS_PARTY", "c1", "c1:party:NLD") in edges
    assert ("ABOUT", ci, "c1:p0.d1.k1@1") in edges
    assert ("HOLDER", ci, "c1:party:NLD") in edges
    assert b.problems == ()
    b2, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)
    assert b2.build_id == b.build_id


def test_concept_quote_is_masked():
    log = OperationLog("c1")
    log.add(_concept_op(quote="Bên A: Nguyễn Văn An, CCCD 001203004567"))
    b, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)
    node = next(n for n in b.nodes if n.label == "ConceptInstance")
    assert "001203004567" not in node.props["quote"]
    assert not any("còn PII" in p for p in b.problems)


def test_contract_fact_nodes_and_absent_checked():
    from rag.bridge.facts_map import fact_ops
    from rag.contracts.graph.oplog import machine_op
    log = OperationLog("c1")
    for o in fact_ops({"candidates": {"salary": [{"value": "30 triệu đồng", "unit": "p0.d1.k1",
                                                  "quote": "Giá 30 triệu đồng"}]}}, "c1", at=T):
        log.add(o)
    log.add(machine_op("c1", "ASSERT", "absent:x", {"kind": "concept_absent", "concept_id": "content.raise_policy"},
                       "llm", "auto_accepted", at=T))
    b, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)
    f = next(n for n in b.nodes if n.label == "ContractFact")
    assert f.props["name"] == "base_salary_vnd" and f.props["value"] == 30000000 and f.props["unit"] == "vnd"
    assert f.props["quote"] == "Giá 30 triệu đồng" and f.node_id == f"c1:fact:{f.props['op_id']}"
    assert any(e.type == "EVIDENCE" and e.src == f.node_id and e.dst == "c1:p0.d1.k1@1" for e in b.edges)
    assert any(e.type == "HAS_FACT" and e.src == "c1" and e.dst == f.node_id for e in b.edges)
    assert next(n for n in b.nodes if n.label == "Contract").props["absent_checked"] == ["content.raise_policy"]
    assert validate(b) == []
