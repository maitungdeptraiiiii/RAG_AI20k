from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from rag.legal.keys import document_key
from rag.legal.models import (Address, AmendmentOperation, BuildRun, DocumentRelation, LegalDocument, ProvisionVersion,
                              ReviewDecision, ReviewItem)
from rag.legal.store import LegalStore

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


def doc(number, title, issued, consolidated=False):
    return LegalDocument(document_key("Luật", number), "1", title, "Luật", number, "Quốc hội", issued, None, None,
                         "Còn hiệu lực", consolidated, "raw/x.txt", "a" * 64, NOW, discovered_via="seed")


def op(oid="op1", status="pending"):
    return AmendmentOperation(oid, "luat:03/2022/QH15", date(2022, 1, 11), "Điều 7 > 3 > b", Address("7", "3", "b"),
                              (10, 20), 4, "luat:59/2020/QH14", "Luật Doanh nghiệp", "REPLACE_CLAUSE", Address("60", "3"),
                              None, "3. Mới.", None, date(2022, 3, 1), "exact", status, ("note:x",))


def ver(pid, start, end, build="b1", key="luat:59/2020/QH14", status="verified"):
    return ProvisionVersion(f"{key}#{pid}", key, "clause", f"text {start}", start, end, status, (), (), ("op1",), build)


def run(build_id, key="luat:59/2020/QH14"):
    return BuildRun(build_id, key, ("op1",), "c" * 40, NOW, "legal-v1")


@pytest.fixture
def store(tmp_path):
    return LegalStore(tmp_path / "catalog.sqlite")


def test_documents_roundtrip(store):
    d = doc("59/2020/QH14", "Luật Doanh nghiệp số 59/2020/QH14", date(2020, 6, 17))
    store.upsert_document(d)
    store.upsert_document(replace(d, eff_status="Hết hiệu lực một phần"))
    assert store.document(d.document_key).eff_status == "Hết hiệu lực một phần"
    assert store.documents() == [replace(d, eff_status="Hết hiệu lực một phần")]
    assert store.document("luat:none") is None


def test_relations_both_directions(store):
    rel = DocumentRelation("luat:03/2022/QH15", "luat:59/2020/QH14", "SUA_DOI_BO_SUNG", "Điều 7", "confirmed")
    store.add_relation(rel)
    store.add_relation(replace(rel, evidence="Điều 7 (sửa)"))
    assert store.relations("luat:59/2020/QH14") == [replace(rel, evidence="Điều 7 (sửa)")]
    assert store.relations("luat:03/2022/QH15") == [replace(rel, evidence="Điều 7 (sửa)")]


def test_add_operations_idempotent(store):
    assert store.add_operations([op()]) == 1
    assert store.add_operations([op()]) == 0
    assert store.operations(target_key="luat:59/2020/QH14") == [op()]
    assert store.operations(source_key="luat:x") == []


def test_operations_immutable_and_superseded(store):
    store.add_operations([op()])
    new = replace(op("op2", "approved"), new_text="3. Đã sửa.", supersedes_operation_id="op1")
    store.supersede_operation("op1", new, "Tùng", "sai ngày", NOW)
    assert [o.operation_id for o in store.operations()] == ["op2"]
    both = {o.operation_id: o for o in store.operations(include_rejected=True)}
    assert both["op1"].review_status == "rejected" and both["op1"].new_text == "3. Mới."
    assert both["op1"].reviewer == "Tùng" and both["op2"].supersedes_operation_id == "op1"


def test_set_review_changes_only_review_fields(store):
    store.add_operations([op()])
    store.set_review("op1", "approved", "Tùng", "ok", NOW)
    (o,) = store.operations()
    assert (o.review_status, o.reviewer, o.review_note, o.reviewed_at) == ("approved", "Tùng", "ok", NOW)
    assert replace(o, review_status="pending", reviewer=None, review_note=None, reviewed_at=None) == op()


def test_as_of_half_open(store):
    store.save_build(run("b1"), [ver("d60.k3", date(2021, 1, 1), date(2022, 3, 1)), ver("d60.k3", date(2022, 3, 1), None)])
    (a,) = store.provisions_as_of("luat:59/2020/QH14", date(2022, 2, 28))
    (b,) = store.provisions_as_of("luat:59/2020/QH14", date(2022, 3, 1))
    assert a.valid_from == date(2021, 1, 1) and b.valid_from == date(2022, 3, 1)
    assert store.provisions_as_of("luat:59/2020/QH14", date(2020, 1, 1)) == []
    assert [v.valid_from for v in store.provision_history("luat:59/2020/QH14#d60.k3")] == [date(2021, 1, 1), date(2022, 3, 1)]


def test_latest_build_wins_old_kept(store):
    store.save_build(run("b1"), [ver("d1", date(2021, 1, 1), None, "b1")])
    store.save_build(run("b2"), [ver("d1", date(2021, 1, 1), None, "b2", status="needs_review")])
    assert store.latest_build("luat:59/2020/QH14").build_id == "b2"
    assert store.provisions_as_of("luat:59/2020/QH14", date(2022, 1, 1))[0].verification_status == "needs_review"
    assert store.provisions_as_of("luat:59/2020/QH14", date(2022, 1, 1), build_id="b1")[0].build_id == "b1"
    assert [b.build_id for b in store.builds("luat:59/2020/QH14")] == ["b1", "b2"]
    store.save_build(run("b1"), [ver("d1", date(2021, 1, 1), None, "b1")])          # dựng lại cùng đầu vào
    assert store.latest_build("luat:59/2020/QH14").build_id == "b1"


def test_laws_in_force_and_family(store):
    old = doc("65/2014/QH13", "Luật Nhà ở số 65/2014/QH13", date(2014, 11, 25))
    new = doc("27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", date(2023, 11, 27))
    vbhn = doc("01/VBHN-VPQH", "Luật Nhà ở", date(2025, 1, 1), consolidated=True)
    for d in (old, new, vbhn):
        store.upsert_document(d)
    store.save_build(run("o", old.document_key), [ver("d1", date(2015, 7, 1), date(2024, 8, 1), "o", old.document_key)])
    store.save_build(run("n", new.document_key), [ver("d1", date(2024, 8, 1), None, "n", new.document_key)])
    assert [d.document_key for d in store.laws_in_force(date(2023, 6, 15))] == [old.document_key]
    assert [d.document_key for d in store.laws_in_force(date(2025, 6, 15))] == [new.document_key]
    assert [d.document_key for d in store.law_family("Luật Nhà ở")] == [old.document_key, new.document_key]


def test_review_item_dedup_and_resolve(store):
    item = ReviewItem("r1", "operation", "luat:59/2020/QH14", "op1", None, ("operation.label_mismatch",), "open", NOW,
                      {"source_excerpt": "x"})
    store.add_review_item(item)
    store.add_review_item(replace(item, review_id="r2"))
    assert [i.review_id for i in store.review_items()] == ["r1"]
    assert store.review_item("r1").payload == {"source_excerpt": "x"}
    store.resolve_review(ReviewDecision("r1", "approve", "Tùng", "đúng", {}, NOW))
    assert store.review_items("open") == []
    assert store.review_item("r1").status == "resolved"
    assert store.decisions("r1")[0].reviewer == "Tùng"


def test_persists_across_instances(tmp_path):
    path = tmp_path / "catalog.sqlite"
    LegalStore(path).add_operations([op()])
    assert LegalStore(path).operations() == [op()]
