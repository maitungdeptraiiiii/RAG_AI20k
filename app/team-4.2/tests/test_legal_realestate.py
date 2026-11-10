"""Kỳ vọng trên văn bản thật nhóm bất động sản (crawl từ vbpl.vn ngày 09/11/2026, lưu ở fixtures/legal/realestate).

Chuỗi pháp lý được kiểm:
- Luật 43/2024/QH15 sửa Điều hiệu lực của Luật Đất đai 31/2024, Luật Nhà ở 27/2023, Luật KDBĐS 29/2023 -> các luật
  này có hiệu lực từ 01/8/2024 (vbpl vẫn ghi 01/01/2025 cho Luật Đất đai).
- Luật Đất đai 2024: Điều 190 và Điều 248 có hiệu lực sớm từ 01/4/2024; khoản 9 Điều 60 hiệu lực theo sự kiện.
- Luật cũ (Đất đai 2013, Nhà ở 2014, KDBĐS 2014) hết hiệu lực đúng ngày luật mới có hiệu lực (01/8/2024).
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.legal.models import Address
from rag.legal.service import LegalService
from rag.legal.store import LegalStore, decode
from rag.legal.models import LegalDocument

FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
LAND, LAND_OLD = "luat:31/2024/QH15", "luat:45/2013/QH13"
HOUSING, HOUSING_OLD = "luat:27/2023/QH15", "luat:65/2014/QH13"
BIZ, BIZ_OLD = "luat:29/2023/QH15", "luat:66/2014/QH13"
AMEND = "luat:43/2024/QH15"


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    store = LegalStore(tmp_path_factory.mktemp("realestate") / "catalog.sqlite")
    for row in json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8")):
        row["raw_text_path"] = str(FIXTURES / row["raw_text_path"])
        store.upsert_document(decode(LegalDocument, row))
    service = LegalService(store, now=lambda: NOW)
    service.build_all()
    return service


def in_force(svc, family, day):
    keys = {d.document_key for d in svc.store.law_family(family)}
    return [d.document_key for d in svc.store.laws_in_force(day) if d.document_key in keys]


@pytest.mark.parametrize("family,old,new", [
    ("Luật Nhà ở", HOUSING_OLD, HOUSING),
    ("Luật Kinh doanh bất động sản", BIZ_OLD, BIZ),
])
def test_housing_and_real_estate_business_switch_on_2024_08_01(svc, family, old, new):
    assert in_force(svc, family, date(2023, 6, 15)) == [old]
    assert in_force(svc, family, date(2024, 7, 31)) == [old]
    assert in_force(svc, family, date(2024, 8, 1)) == [new]
    assert in_force(svc, family, date(2025, 6, 15)) == [new]


def test_land_law_start_date_from_text_not_vbpl(svc):
    versions = svc.store.versions(LAND)
    starts = {v.valid_from for v in versions if v.kind == "article"}
    assert min(starts) == date(2024, 4, 1)                                    # Điều 190, 248
    assert {v.valid_from for v in versions if v.provision_id in (f"{LAND}#d190", f"{LAND}#d248")} == {date(2024, 4, 1)}
    assert {v.valid_from for v in versions if v.provision_id == f"{LAND}#d1"} == {date(2024, 8, 1)}
    assert svc.store.document(LAND).vbpl_effective_from == date(2025, 1, 1)  # vbpl chưa cập nhật sửa đổi của 43/2024


def test_old_laws_end_when_new_ones_start(svc):
    for old in (LAND_OLD, HOUSING_OLD, BIZ_OLD):
        versions = svc.store.versions(old)
        assert all(v.valid_to is not None and v.valid_to <= date(2024, 8, 1) for v in versions), old
        last = {}
        for v in versions:
            last[v.provision_id] = max(last.get(v.provision_id, v.valid_to), v.valid_to)
        assert set(last.values()) == {date(2024, 8, 1)}, old
    # Luật 03/2022/QH15 (Điều 4) sửa khoản 1 Điều 23 Luật Nhà ở 2014 từ 01/3/2022
    k1 = svc.store.provision_history(f"{HOUSING_OLD}#d23.k1")
    texts = [v.text for v in k1]
    changed_on = [v.valid_from for prev, v in zip(k1, k1[1:]) if v.text != prev.text]
    assert changed_on == [date(2022, 3, 1)] and len(set(texts)) == 2
    assert k1[-1].valid_to == date(2024, 8, 1)
    # Luật Nhà ở 2023 nêu rõ 65/2014 "đã được sửa đổi, bổ sung theo Luật số 40/2019/QH14, 61/2020, 62/2020, 64/2020
    # và 03/2022" — 4 luật đầu chưa có trong kho, nên từ 2019 không được coi là đã xác minh
    assert k1[0].valid_from == date(2015, 7, 1) and k1[0].verification_status == "verified"
    later = [v for v in k1 if v.valid_from >= date(2019, 1, 1)]
    assert later and all(v.verification_status == "needs_review" for v in later)
    assert "operation.missing_amending_law:40/2019/QH14" in later[0].status_reasons
    # 31/07/2024: Luật Đất đai 2013 vẫn hiệu lực, Luật Đất đai 2024 mới có Điều 190, 248 hiệu lực
    assert in_force(svc, "Luật Đất đai", date(2024, 7, 31)) == [LAND, LAND_OLD]
    assert in_force(svc, "Luật Đất đai", date(2024, 8, 1)) == [LAND]


def test_43_2024_operations(svc):
    ops = svc.store.operations(source_key=AMEND)
    targets = {o.target_document_key for o in ops if o.review_status == "auto_accepted"}
    assert {LAND, HOUSING, BIZ} <= targets
    lead = next(o for o in ops if o.target == Address("260", "4", part="lead_in"))
    assert lead.review_status == "auto_accepted"
    credit = next(o for o in ops if o.target_law_name and "tổ chức tín dụng" in o.target_law_name)
    assert credit.review_status == "pending" and "operation.target_law_not_found" in credit.status_reasons


def test_amended_clause_starts_amended_with_the_law(svc):
    h = svc.store.provision_history(f"{LAND}#d260.k4")
    assert [v.valid_from for v in h] == [date(2024, 8, 1)]  # luật bắt đầu cùng ngày với sửa đổi: chỉ bản đã sửa
    assert h[0].text.startswith("4. ") and h[0].verification_status == "verified"


def test_conditional_unit_flagged(svc):
    (v,) = svc.store.provision_history(f"{LAND}#d60.k9")
    assert v.verification_status == "needs_review" and "effectivity.conditional_unit" in v.status_reasons


def test_no_verified_version_from_unsupported(svc):
    unsupported = {o.operation_id for o in svc.store.operations() if o.operation_type == "UNSUPPORTED"}
    for key in (LAND, HOUSING, BIZ, LAND_OLD, HOUSING_OLD, BIZ_OLD):
        for v in svc.store.versions(key):
            assert not (v.verification_status == "verified" and set(v.source_operations) & unsupported)
