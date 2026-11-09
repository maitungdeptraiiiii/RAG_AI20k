"""Hồi quy cho các lỗi do review độc lập tìm ra (C4, C5, I2, I3, I4, I5) — mỗi lỗi từng tạo ra phiên bản sai mà
vẫn `verified`, hoặc trạng thái không gỡ được."""

from dataclasses import replace
from datetime import date

import pytest

from rag.legal.builder import build_versions
from rag.legal.effectivity import EffectivityInfo, RepealStatement, parse_effectivity
from rag.legal.models import Address, AmendmentOperation, DocumentRelation, LegalDocument, ReviewDecision, ReviewItem
from rag.legal.operations import repeal_operations
from rag.legal.service import LegalService
from rag.legal.store import LegalStore
from rag.legal.structure import parse_structure
from tests.test_legal_builder import FAKE, fake_build, op
from tests.test_legal_builder import doc as bdoc
from tests.test_legal_service import BASE, FIXTURES, NOW, _review_for, doc, make_service, op_k3


@pytest.fixture
def service(tmp_path):
    svc = make_service(tmp_path)
    svc.build_all()
    return svc


# --- C5 (dữ liệu): bãi bỏ một phần + luật sửa đổi đã biết ---------------------------------------

def test_partial_repeal_becomes_pending_delete_and_amenders_noted():
    old = bdoc("31/2024/QH15", "Luật Đất đai số 31/2024/QH15", date(2024, 1, 18))
    new = bdoc("9/2026/QH16", "Luật Khác số 9/2026/QH16", date(2026, 1, 1))
    info = EffectivityInfo("9", date(2026, 7, 1), (), (
        RepealStatement("Luật Đất đai", "31/2024/QH15", date(2026, 7, 1), False, (0, 10), units=(Address("248", "3"),)),
        RepealStatement("Luật Đất đai", "31/2024/QH15", date(2026, 7, 1), False, (0, 10), amended_by=("43/2024/QH15",)),
    ), None, ())
    partial, whole = repeal_operations(new, info, documents=[old, new])
    assert (partial.operation_type, partial.target, partial.review_status) == ("DELETE_CLAUSE", Address("248", "3"), "pending")
    assert "operation.partial_repeal" in partial.status_reasons
    assert whole.operation_type == "REPEAL_DOCUMENT" and "note:amended_by:43/2024/QH15" in whole.status_reasons


# --- C4: thao tác được duyệt nhưng không áp dụng được không được im lặng thành verified --------------

def test_approved_unscoped_op_is_apply_failed_not_silently_verified():
    bulk = op("REPLACE_TEXT", None, "Y", old_phrase="Khoản năm", status="approved")
    unsupported = op("UNSUPPORTED", Address("17"), status="approved", seq=2)
    after = [v for v in fake_build([bulk, unsupported]) if v.valid_from >= date(2023, 1, 1)]
    assert after and all(v.verification_status == "needs_review" for v in after)
    assert any(r.startswith("operation.apply_failed") for v in after for r in v.status_reasons)


def _bulk_item(svc):
    bulk = AmendmentOperation("bulk1", "luat:03/2022/QH15", date(2022, 1, 11), "Điều 7 > 9", Address("7", "9"), (0, 1),
                              900, BASE, "Luật Doanh nghiệp", "REPLACE_TEXT", None, None, "Y", "biên bản",
                              date(2022, 3, 1), "partial", "pending", ("operation.bulk_text_scope",))
    svc.store.add_operations([bulk])
    item = ReviewItem("op:bulk1", "operation", BASE, "bulk1", None, ("operation.bulk_text_scope",), "open", NOW, {})
    svc.store.add_review_item(item)
    return item


def test_approve_rejects_unactionable_operation(service):
    item = _bulk_item(service)
    with pytest.raises(ValueError):
        service.decide(ReviewDecision(item.review_id, "approve", "Tùng", "đồng ý", {}, NOW))
    assert service.store.review_item(item.review_id).status == "open"
    assert service.store.operation("bulk1").review_status == "pending"


# --- C3 ở luật gốc: ngày riêng không xác định được đơn vị ---------------------------------------

def test_unresolved_base_effectivity_date_flags_versions():
    text = ("Điều 1. A\nNội dung.\nĐiều 3. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.\n"
            "2. Các quy định về đấu giá tại Luật này có hiệu lực từ ngày 01/7/2025.")
    provisions = parse_structure(text, FAKE)
    d = bdoc("1/2020/QH14", "Luật X", date(2024, 1, 1), date(2025, 1, 1))
    versions = build_versions(d, provisions, parse_effectivity(provisions), [], build_id="t")
    assert {v.verification_status for v in versions} == {"needs_review"}


# --- I4: sửa sai phải được kiểm tra trước khi ghi ---------------------------------------------------

def test_correct_validates_fields_before_writing(service):
    item = _review_for(service, op_k3(service))
    bad = [{"effective_from": ""}, {"target": {"clause": "3"}}, {"target_document_key": "luat:khong/co"},
           {"operation_type": "XOA_HET"}, {"new_text": "9. sai nhãn"}]
    for fields in bad:
        with pytest.raises(ValueError):
            service.decide(ReviewDecision(item.review_id, "correct", "Tùng", "sửa", fields, NOW))
    assert service.store.review_item(item.review_id).status == "open"
    service.store.operations()                                   # kho vẫn đọc được
    assert op_k3(service).review_status == "auto_accepted"


# --- I2: lập lại thao tác phải loại thao tác máy đã biến mất ----------------------------------------

def test_replan_retires_vanished_machine_ops(service):
    ghost = replace(op_k3(service), operation_id="ghost", sequence=777, target=Address("61", "1"), new_text="1. Ma.")
    service.store.add_operations([ghost])
    service.plan_operations("luat:03/2022/QH15")
    g = service.store.operation("ghost")
    assert g.review_status == "rejected" and g.reviewer == "system"
    assert "operation.superseded_by_replan" in (g.review_note or "")


def test_replan_keeps_vanished_human_op_but_opens_review(service):
    ghost = replace(op_k3(service), operation_id="ghost2", sequence=778, target=Address("61", "1"), new_text="1. Ma.")
    service.store.add_operations([ghost])
    service.store.set_review("ghost2", "approved", "Tùng", "đã duyệt", NOW)
    service.plan_operations("luat:03/2022/QH15")
    assert service.store.operation("ghost2").review_status == "approved"
    item = service.store.review_item("op:ghost2")
    assert item.status == "open" and "operation.missing_after_replan" in item.reasons


# --- I3: mục duyệt mở lại / VBHN đã chấp nhận / hạ cấp ---------------------------------------------

def test_system_resolved_item_reopens_when_pending_again(service):
    o = op_k3(service)
    rid = f"op:{o.operation_id}"
    service.store.add_review_item(ReviewItem(rid, "operation", BASE, o.operation_id, None, ("x",), "open", NOW, {}))
    service.store.resolve_review(ReviewDecision(rid, "approve", "system", "đánh giá lại", {}, NOW))
    service.store.add_review_item(ReviewItem(rid, "operation", BASE, o.operation_id, None, ("y",), "open", NOW, {}))
    assert service.store.review_item(rid).status == "open"


def _vbhn_service(tmp_path):
    svc = make_service(tmp_path)
    text = (FIXTURES / "vbhn_sample.txt").read_text(encoding="utf-8").replace("đúng hạn", "đúng thời hạn")
    path = tmp_path / "vbhn.txt"
    path.write_text(text, encoding="utf-8")
    svc.store.upsert_document(LegalDocument("vbhn:10/VBHN-VPQH", "9", "Luật Doanh nghiệp", "Văn bản hợp nhất",
                                            "10/VBHN-VPQH", "VPQH", date(2022, 5, 1), None, None, None, True,
                                            str(path), "e" * 64, NOW))
    svc.store.add_relation(DocumentRelation("vbhn:10/VBHN-VPQH", BASE, "HOP_NHAT", "x", "confirmed"))
    svc.build_all()
    return svc


def _d50(svc):
    return next(v for v in svc.store.provisions_as_of(BASE, date(2022, 3, 1)) if v.provision_id == f"{BASE}#d50")


def test_vbhn_mismatch_flow_and_accepted_mismatch_not_reflagged(tmp_path):
    svc = _vbhn_service(tmp_path)
    assert _d50(svc).verification_status == "conflicted"
    item = svc.store.review_item("vbhn:vbhn:10/VBHN-VPQH:50")
    assert item is not None and item.status == "open"
    svc.decide(ReviewDecision(item.review_id, "approve", "Tùng", "VBHN in lỗi, bản dựng đúng", {}, NOW))
    assert _d50(svc).verification_status == "verified"
    svc.build_all()
    assert _d50(svc).verification_status == "verified"
    assert svc.store.review_item(item.review_id).status == "resolved"


def test_demotion_skips_reviewed_ops_and_opens_review(service):
    a = op_k3(service)                                       # thao tác của 03/2022 Điều 7
    b = AmendmentOperation("amend-a", "luat:22/2023/QH15", date(2023, 6, 1), "Điều 1", Address("1"), (0, 1), 1,
                           "luat:03/2022/QH15", None, "REPLACE_CLAUSE", Address("7", "3"), None, "3. Sửa chỉ dẫn.",
                           None, date(2023, 7, 1), "exact", "approved", ())
    service.store.add_operations([b])
    service.build_law(BASE)
    item = service.store.review_item(f"op:{a.operation_id}")
    assert item is not None and item.status == "open"
    assert any(r.startswith("operation.source_amended") for r in item.reasons)
    service.store.set_review(a.operation_id, "approved", "Tùng", "chỉ dẫn vẫn đúng", NOW)
    service.build_law(BASE)
    h = service.store.provision_history(f"{BASE}#d60.k3")
    assert h[-1].verification_status == "verified"


# --- C5 (dựng): luật sửa đổi đã biết nhưng thiếu, trạng thái vbpl "một phần", effTo không có bãi bỏ ------

def test_missing_amending_law_flags_versions(tmp_path):
    files = {
        "old": "Điều 1. Phạm vi\nLuật cũ.\nĐiều 9. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2015.",
        "new": ("Điều 1. Phạm vi\nLuật mới.\nĐiều 198. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.\n"
                "2. Luật Nhà ở số 65/2014/QH13 đã được sửa đổi, bổ sung một số điều theo Luật số 40/2019/QH14 hết hiệu lực "
                "kể từ ngày Luật này có hiệu lực thi hành."),
    }
    for name, text in files.items():
        (tmp_path / f"{name}.txt").write_text(text, encoding="utf-8")
    store = LegalStore(tmp_path / "c.sqlite")
    store.upsert_document(replace(doc("65/2014/QH13", "Luật Nhà ở số 65/2014/QH13", date(2014, 11, 25), tmp_path / "old.txt",
                                      date(2015, 7, 1)), eff_status="Hết hiệu lực toàn bộ"))   # như vbpl thật
    store.upsert_document(doc("27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", date(2023, 11, 27), tmp_path / "new.txt", date(2024, 8, 1)))
    LegalService(store, now=lambda: NOW).build_all()
    h = store.provision_history("luat:65/2014/QH13#d1")
    assert [(v.valid_from, v.verification_status) for v in h] == [
        (date(2015, 7, 1), "verified"), (date(2019, 1, 1), "needs_review")]
    assert "operation.missing_amending_law:40/2019/QH14" in h[1].status_reasons


def test_vbpl_partial_status_without_amendments_and_effto_without_repeal(tmp_path):
    (tmp_path / "a.txt").write_text("Điều 1. A\nNội dung.\nĐiều 2. Hiệu lực thi hành\n"
                                    "Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2020.", encoding="utf-8")
    store = LegalStore(tmp_path / "c.sqlite")
    base = replace(doc("5/2019/QH14", "Luật A số 5/2019/QH14", date(2019, 6, 1), tmp_path / "a.txt", date(2020, 1, 1)),
                   eff_status="Hết hiệu lực một phần")
    store.upsert_document(base)
    LegalService(store, now=lambda: NOW).build_all()
    assert {v.verification_status for v in store.versions(base.document_key)} == {"needs_review"}
    store.upsert_document(replace(base, eff_status="Hết hiệu lực toàn bộ", vbpl_effective_to=date(2023, 1, 1)))
    LegalService(store, now=lambda: NOW).build_all()
    reasons = {r for v in store.versions(base.document_key) for r in v.status_reasons}
    assert "effectivity.vbpl_effective_to_without_repeal" in reasons
