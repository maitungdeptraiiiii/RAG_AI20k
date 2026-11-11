import os
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.legal.keys import document_key
from rag.legal.models import Address, LegalDocument, ReviewDecision
from rag.legal.service import LegalService, ReviewClosedError
from rag.legal.store import LegalStore

FIXTURES = Path(__file__).parent / "fixtures" / "legal"
PROJECT = Path(__file__).resolve().parents[1]
BASE = "luat:59/2020/QH14"
NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


def doc(number, title, issued, path, vbpl_from=None):
    return LegalDocument(document_key("Luật", number), "1", title, "Luật", number, "Quốc hội", issued, vbpl_from, None,
                         "Hết hiệu lực một phần", False, str(path), "f" * 64, NOW)


def make_service(tmp_path) -> LegalService:
    store = LegalStore(tmp_path / "legal" / "catalog.sqlite")
    store.upsert_document(doc("59/2020/QH14", "Luật Doanh nghiệp số 59/2020/QH14", date(2020, 6, 17),
                              FIXTURES / "luat_59_2020_QH14.txt", date(2021, 1, 1)))
    store.upsert_document(doc("03/2022/QH15", "Luật sửa đổi, bổ sung một số điều của Luật Đầu tư công, ... số 03/2022/QH15",
                              date(2022, 1, 11), FIXTURES / "luat_03_2022_QH15.txt", date(2022, 3, 1)))
    return LegalService(store, now=lambda: NOW)


@pytest.fixture
def service(tmp_path):
    svc = make_service(tmp_path)
    svc.build_all()
    return svc


def k3(svc, day, **kw):
    return next(v for v in svc.store.provisions_as_of(BASE, day, **kw) if v.provision_id == f"{BASE}#d60.k3")


def op_k3(svc):
    return next(o for o in svc.store.operations() if o.target == Address("60", "3"))


def test_build_all_real_enterprise(service):
    assert "người ghi biên bản từ chối ký biên bản họp thì biên bản này có hiệu lực nếu được tất cả thành viên khác" in k3(service, date(2022, 2, 28)).text
    new = k3(service, date(2022, 3, 1))
    assert new.valid_from == date(2022, 3, 1) and new.text != k3(service, date(2022, 2, 28)).text
    d60 = [v for v in service.store.versions(BASE) if v.provision_id.startswith(f"{BASE}#d60")]
    assert d60 and {v.verification_status for v in d60} == {"verified"}
    # thao tác vào luật ngoài kho (Luật Đầu tư công...) không ảnh hưởng phiên bản nào -> không làm ngập hàng đợi
    open_items = service.store.review_items("open")
    assert not any(i.payload.get("target_law_name") == "Luật Đầu tư công" for i in open_items)
    pending_out_of_corpus = [o for o in service.store.operations() if o.target_law_name == "Luật Đầu tư công"]
    assert pending_out_of_corpus and all(o.review_status == "pending" for o in pending_out_of_corpus)


def test_build_idempotent(service):
    first = service.store.latest_build(BASE).build_id
    n_items = len(service.store.review_items(None))
    service.build_all()
    assert service.store.latest_build(BASE).build_id == first
    assert len(service.store.review_items(None)) == n_items


def _review_for(svc, op):
    from rag.legal.models import ReviewItem
    item = ReviewItem(f"op:{op.operation_id}", "operation", BASE, op.operation_id, None, ("manual",), "open", NOW, {})
    svc.store.add_review_item(item)
    return item


def test_reject_then_rebuild(service):
    old_build = service.store.latest_build(BASE).build_id
    item = _review_for(service, op_k3(service))
    run = service.decide(ReviewDecision(item.review_id, "reject", "Tùng", "parse sai", {}, NOW))
    assert run.build_id != old_build
    assert len(service.store.provision_history(f"{BASE}#d60.k3")) == 1
    assert len(service.store.provision_history(f"{BASE}#d60.k3", build_id=old_build)) == 2


def test_correct_creates_superseding_op(service):
    old = op_k3(service)
    item = _review_for(service, old)
    service.decide(ReviewDecision(item.review_id, "correct", "Tùng", "ngày đúng là 01/07/2022",
                                  {"effective_from": "2022-07-01"}, NOW))
    ops = {o.operation_id: o for o in service.store.operations(include_rejected=True)}
    assert ops[old.operation_id].review_status == "rejected"
    new = next(o for o in ops.values() if o.supersedes_operation_id == old.operation_id)
    assert new.review_status == "approved" and new.effective_from == date(2022, 7, 1)
    assert [v.valid_from for v in service.store.provision_history(f"{BASE}#d60.k3")] == [date(2021, 1, 1), date(2022, 7, 1)]


def test_correct_rejects_unknown_field(service):
    item = _review_for(service, op_k3(service))
    with pytest.raises(ValueError):
        service.decide(ReviewDecision(item.review_id, "correct", "Tùng", "x", {"source_document_key": "x"}, NOW))


def test_empty_note_rejected(service):
    item = _review_for(service, op_k3(service))
    with pytest.raises(ValueError):
        service.decide(ReviewDecision(item.review_id, "approve", "Tùng", "  ", {}, NOW))


def test_decision_on_closed_review(service):
    item = _review_for(service, op_k3(service))
    service.decide(ReviewDecision(item.review_id, "approve", "Tùng", "ok", {}, NOW))
    with pytest.raises(ReviewClosedError):
        service.decide(ReviewDecision(item.review_id, "approve", "Tùng", "ok", {}, NOW))


def test_report_counts(service):
    rep = service.report()
    assert rep["operations"][("exact", "auto_accepted")] >= 10
    assert rep["versions"][BASE]["verified"] > 0
    assert rep["open_reviews"] == len(service.store.review_items("open"))


def test_cli_show(tmp_path):
    make_service(tmp_path).build_all()
    env = {**os.environ, "DATA_DIR": str(tmp_path), "PYTHONPATH": str(PROJECT / "src"), "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "-m", "rag.legal", "show", BASE, "--as-of", "2022-03-01", "--provision", "d60.k3"],
                         cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert "verified" in out.stdout and "2022-03-01" in out.stdout


def test_repeal_follows_amended_effective_date(tmp_path):
    """Đất đai 2013 hết hiệu lực "kể từ ngày Luật này có hiệu lực" của Đất đai 2024; 43/2024 sửa ngày đó thành
    01/8/2024 -> Đất đai 2013 phải kết thúc 01/8/2024, không phải 01/01/2025 (không có 5 tháng hai luật cùng hiệu lực)."""
    files = {
        "old": "Điều 1. Phạm vi\nLuật cũ.\nĐiều 212. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2014.",
        "new": ("Điều 1. Phạm vi\nLuật mới.\nĐiều 252. Hiệu lực thi hành\n"
                "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.\n"
                "2. Luật Đất đai số 45/2013/QH13 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành."),
        "amend": ("Điều 1. Sửa đổi, bổ sung một số điều của Luật Đất đai số 31/2024/QH15\n"
                  "1. Sửa đổi, bổ sung khoản 1 Điều 252 như sau:\n"
                  '"1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.".\n'
                  "Điều 5. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024."),
    }
    for name, text in files.items():
        (tmp_path / f"{name}.txt").write_text(text, encoding="utf-8")
    store = LegalStore(tmp_path / "legal" / "catalog.sqlite")
    store.upsert_document(doc("45/2013/QH13", "Luật Đất đai số 45/2013/QH13", date(2013, 11, 29), tmp_path / "old.txt", date(2014, 7, 1)))
    store.upsert_document(doc("31/2024/QH15", "Luật Đất đai số 31/2024/QH15", date(2024, 1, 18), tmp_path / "new.txt", date(2025, 1, 1)))
    store.upsert_document(doc("43/2024/QH15", "Luật sửa đổi Luật Đất đai số 43/2024/QH15", date(2024, 6, 29), tmp_path / "amend.txt", date(2024, 8, 1)))
    LegalService(store, now=lambda: NOW).build_all()
    old_end = {v.valid_to for v in store.versions("luat:45/2013/QH13")}
    assert old_end == {date(2024, 8, 1)}
    assert min(v.valid_from for v in store.versions("luat:31/2024/QH15")) == date(2024, 8, 1)
    family = {d.document_key for d in store.law_family("Luật Đất đai")}
    assert [d.document_key for d in store.laws_in_force(date(2024, 9, 1)) if d.document_key in family] == ["luat:31/2024/QH15"]
    assert [d.document_key for d in store.laws_in_force(date(2024, 7, 31)) if d.document_key in family] == ["luat:45/2013/QH13"]


def test_replan_refreshes_machine_judgement_but_keeps_human_decisions(service):
    target = op_k3(service)
    stale = replace(target, review_status="pending", status_reasons=("operation.label_mismatch",))
    other = next(o for o in service.store.operations() if o.target == Address("148", "1"))
    with service.store._conn() as c:                         # giả lập kết quả của parser cũ / quyết định cũ
        from rag.legal.store import _dump
        c.execute("UPDATE operations SET review_status='pending', payload=? WHERE operation_id=?",
                  (_dump(stale), stale.operation_id))
    service.store.set_review(other.operation_id, "rejected", "Tùng", "người duyệt từ chối", NOW)
    from rag.legal.models import ReviewItem
    service.store.add_review_item(ReviewItem(f"op:{stale.operation_id}", "operation", BASE, stale.operation_id, None,
                                             ("operation.label_mismatch",), "open", NOW, {}))
    service.plan_operations("luat:03/2022/QH15")
    assert service.store.operation(stale.operation_id).review_status == "auto_accepted"
    assert service.store.operation(other.operation_id).review_status == "rejected"
    assert service.store.review_item(f"op:{stale.operation_id}").status == "resolved"
    assert service.store.decisions(f"op:{stale.operation_id}")[0].reviewer == "system"
