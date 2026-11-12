from datetime import datetime, timezone

import pytest

import rag.contracts.graph.build as build_mod
from rag.contracts.doc import PageText
from rag.contracts.graph.neo4j_store import GraphUnavailable
from rag.contracts.graph.oplog import OperationLog
from rag.contracts.graph.service import ContractGraphService, GraphBusy

T = datetime(2026, 11, 12, tzinfo=timezone.utc)
PAGES = [PageText(1, "Bên A: Công ty X\nĐiều 1. Giá\n1. Giá 30 triệu đồng.\n2. Thanh toán theo khoản 1 Điều này.")]


class FakeStore:
    def __init__(self, fail=False, exc=None):
        self.published, self.fail, self.exc = [], fail, exc

    def publish(self, build):
        if self.exc:
            raise self.exc
        if self.fail:
            raise GraphUnavailable("Không kết nối được Neo4j")
        self.published.append(build)


def run(svc):
    return svc.rebuild("c1", PAGES, OperationLog("c1"), file_checksum="x", now=T)


def test_disabled_still_parses():
    doc, st = run(ContractGraphService(None))
    assert doc.units and st["enabled"] is False and st["published"] is False


def test_publishes_valid_build():
    store = FakeStore()
    _, st = run(ContractGraphService(store))
    assert len(store.published) == 1 and st["published"] is True and st["error"] is None
    assert st["build_id"] == store.published[0].build_id


def test_invalid_build_not_published(monkeypatch):
    monkeypatch.setattr(build_mod, "validate", lambda b: ["x"])
    store = FakeStore()
    _, st = run(ContractGraphService(store))
    assert store.published == [] and st["problems"] == ["x"] and st["published"] is False


def test_store_down_is_reported_not_raised():
    _, st = run(ContractGraphService(FakeStore(fail=True)))
    assert st["error"] == "Không kết nối được Neo4j" and st["published"] is False


def test_unexpected_store_error_is_reported():
    _, st = run(ContractGraphService(FakeStore(exc=ValueError("boom"))))
    assert st["error"] == "Lỗi khi ghi đồ thị: ValueError" and st["published"] is False


def test_second_writer_is_refused():
    svc = ContractGraphService(None)
    with svc.writing("c1"):
        with pytest.raises(GraphBusy):
            svc.writing("c1").__enter__()
        with svc.writing("c2"):
            pass
    with svc.writing("c1"):
        pass


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_store_down_backs_off_for_30_seconds():
    store, clock = FakeStore(fail=True), Clock()
    calls = []
    orig = store.publish
    store.publish = lambda b: (calls.append(b), orig(b))
    svc = ContractGraphService(store, clock=clock)
    _, st = run(svc)
    assert len(calls) == 1 and st["error"] == "Không kết nối được Neo4j"
    clock.t += 10
    doc, st = run(svc)
    assert len(calls) == 1 and doc.units
    assert st["error"] == "Neo4j tạm không khả dụng — sẽ thử lại sau" and st["published"] is False
    clock.t += 21
    store.fail = False
    _, st = run(svc)
    assert len(calls) == 2 and st["published"] is True and st["error"] is None
