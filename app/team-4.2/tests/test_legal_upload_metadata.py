from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from rag.ingest.vbpl import VbplError
from rag.legal.models import LegalDocument
from rag.legal.upload.metadata import (REJECT_TYPE_MESSAGE, FieldValue, header_fields, inherit_fields,
                                       is_consolidated, lookup_vbpl, merge_fields, metadata_conflicts,
                                       parse_vbpl_url, type_problem, vbpl_fields)

FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
REAL_43_2024 = (FIXTURES / "luat_43_2024_QH15.txt").read_text(encoding="utf-8")
NOW = datetime(2026, 11, 10, 9, 0)
KEY = "luat:31/2024/QH15"

TEXT_EFFECTIVE_2024_08_01 = """QUỐC HỘI
Số: 31/2024/QH15
Hà Nội, ngày 18 tháng 1 năm 2024
LUẬT
ĐẤT ĐAI
Điều 1. Phạm vi
Nội dung.
Điều 2. Hiệu lực thi hành
Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.
"""

DETAIL_43 = {"id": 171234, "title": "Luật 43/2024/QH15", "docNum": "43/2024/QH15", "docType": {"name": "Luật"},
             "agencyName": "Quốc hội", "issueDate": "2024-06-29T00:00:00", "effFrom": "2024-08-01T00:00:00",
             "effStatus": {"name": "Còn hiệu lực"}}


class FakeClient:
    def __init__(self, items, detail):
        self.items, self._detail = items, detail

    def search_by_number(self, number):
        return self.items

    def detail(self, doc_id):
        return self._detail


class FailingClient:
    def search_by_number(self, number):
        raise VbplError("down")


def doc(**kw):
    base = dict(document_key=KEY, vbpl_id="1", title="t", doc_type="Luật", doc_number="31/2024/QH15", issuer=None,
                issued_on=None, vbpl_effective_from=None, vbpl_effective_to=None, eff_status=None,
                is_consolidated=False, raw_text_path="x", raw_checksum="c", fetched_at=NOW)
    base.update(kw)
    return LegalDocument(**base)


def test_parse_vbpl_url():
    assert parse_vbpl_url("https://vbpl.vn/van-ban/chi-tiet/171234?x=1") == "171234"
    assert parse_vbpl_url("https://vbpl.vn/van-ban/khac/1") is None
    assert parse_vbpl_url("https://example.com/van-ban/chi-tiet/1") is None


def test_header_fields_from_real_amending_law():
    # fixture header thực sự ghi "Ngày 29 tháng 6 năm 2024"
    f = header_fields(REAL_43_2024, NOW)
    assert f["doc_type"].value == "Luật" and f["doc_number"].value == "43/2024/QH15"
    assert f["issued_on"].value == date(2024, 6, 29) and f["issued_on"].source == "text"
    assert f["issuer"].value == "Quốc hội"
    assert f["title"].value.startswith("SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU")


def test_vbpl_wins_over_text_and_keeps_source():
    m = merge_fields(header_fields(REAL_43_2024, NOW), vbpl_fields(DETAIL_43, NOW))
    assert m["vbpl_id"].source == "vbpl" and m["doc_number"].source == "vbpl"
    assert m["vbpl_id"].value == "171234" and m["vbpl_effective_from"].value == date(2024, 8, 1)
    assert m["eff_status"].value == "Còn hiệu lực"


def test_merge_keeps_earlier_when_later_none():
    a = {"title": FieldValue("A", "text", NOW)}
    b = {"title": FieldValue(None, "vbpl", NOW)}
    assert merge_fields(a, b)["title"].source == "text"


def test_lookup_failure_returns_none():
    assert lookup_vbpl(FailingClient(), "Luật", "43/2024/QH15") is None


def test_lookup_filters_type_and_picks_detail():
    detail = {**DETAIL_43, "documentContent": {"content": "x"}}
    items = [{"id": 1, "docNum": "43/2024/QH15", "docType": "Nghị quyết"},
             {"id": 171234, "docNum": "43/2024/QH15", "docType": {"name": "Luật"}}]
    assert lookup_vbpl(FakeClient(items, detail), "Luật", "43/2024/QH15") == detail
    assert lookup_vbpl(FakeClient(items[:1], detail), "Luật", "43/2024/QH15") is None


def test_inherited_fields_marked_and_conflict_detected():
    old = doc(vbpl_id="99", vbpl_effective_from=date(2025, 1, 1), eff_status="Còn hiệu lực")
    f = inherit_fields(header_fields(TEXT_EFFECTIVE_2024_08_01, NOW), old, NOW)
    assert f["vbpl_id"].source == "inherited" and f["vbpl_id"].value == "99"
    assert f["vbpl_id"].detail.startswith("bản trước: ")
    assert f["doc_number"].source == "text"
    assert metadata_conflicts(f, TEXT_EFFECTIVE_2024_08_01, KEY) == (
        "Ngày hiệu lực kế thừa 01/01/2025 khác ngày đọc từ điều hiệu lực 01/08/2024",)


def test_no_conflict_when_not_inherited():
    f = merge_fields(header_fields(TEXT_EFFECTIVE_2024_08_01, NOW),
                     {"vbpl_effective_from": FieldValue(date(2025, 1, 1), "user", NOW, "ai đó")})
    assert metadata_conflicts(f, TEXT_EFFECTIVE_2024_08_01, KEY) == ()


@pytest.mark.parametrize("t,n,ok", [("Luật", "43/2024/QH15", True), ("Nghị định", "10/2023/NĐ-CP", False),
                                    ("Văn bản hợp nhất", "01/VBHN-VPQH", True),
                                    ("Văn bản hợp nhất", "05/VBHN-BTP", False)])
def test_type_problem(t, n, ok):
    assert (type_problem(t, n) is None) == ok
    if not ok:
        assert type_problem(t, n) == REJECT_TYPE_MESSAGE


def test_is_consolidated():
    assert is_consolidated("Văn bản hợp nhất", "01/VBHN-VPQH") and not is_consolidated("Luật", "43/2024/QH15")
