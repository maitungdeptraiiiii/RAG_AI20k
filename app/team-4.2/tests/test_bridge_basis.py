from datetime import date

from rag.bridge.basis import AnchorLawBasis
from rag.bridge.catalog import load_catalog
from rag.legal.graph.query import GraphNotPublished

CAT = load_catalog()
DAY = date(2025, 3, 1)


class FakeGraph:
    def __init__(self, fail=None):
        self.fail, self.calls = fail, []

    def text_at(self, pid, day):
        self.calls.append((pid, day))
        if self.fail:
            raise self.fail
        return {"in_force": True, "text": f"lời văn {pid}", "citation": {"provision_id": pid}}


def test_basis_with_graph():
    b = AnchorLawBasis(CAT, FakeGraph()).concept_basis("leave.annual", DAY)
    assert b["concept_id"] == "leave.annual" and b["day"] == "2025-03-01"
    assert b["anchors"][0]["pid"] == "bo-luat:45/2019/QH14#d113.k1"
    assert b["anchors"][0]["provision"]["text"].startswith("lời văn")
    assert b["problems"] == []


def test_basis_graph_unpublished_or_missing():
    for graph in (FakeGraph(GraphNotPublished("x")), FakeGraph(ConnectionError("down")), None):
        b = AnchorLawBasis(CAT, graph).concept_basis("leave.annual", DAY)
        assert b["problems"] == ["basis_unavailable"]
        assert all(a["provision"] is None for a in b["anchors"]) and len(b["anchors"]) == 4


def test_basis_unknown_concept():
    b = AnchorLawBasis(CAT, None).concept_basis("nope", DAY)
    assert b["anchors"] == [] and b["problems"] == ["unknown_concept"]
