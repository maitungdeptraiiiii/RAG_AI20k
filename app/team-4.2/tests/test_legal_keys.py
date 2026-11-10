import re
from pathlib import Path

import pytest

from rag.legal.keys import document_key, parse_provision_id, provision_id, unit_sort_key
from rag.legal.models import Address

FIXTURES = Path(__file__).parent / "fixtures" / "legal"


def test_document_key_prefixes_type():
    assert document_key("Luật", "59/2020/QH14") == "luat:59/2020/QH14"
    assert document_key("Bộ luật", "91/2015/QH13") == "bo-luat:91/2015/QH13"
    assert document_key("Nghị quyết", "91/2015/QH13") == "nghi-quyet:91/2015/QH13"
    assert document_key("Văn bản hợp nhất", "43/VBHN-VPQH") == "vbhn:43/VBHN-VPQH"
    assert document_key("Luật", " 59 / 2020 / qh14 ") == "luat:59/2020/QH14"


@pytest.mark.parametrize("address,kind,suffix", [
    (Address("60"), "article", "#d60"),
    (Address("49", part="title"), "article_title", "#d49.title"),
    (Address("60", "2"), "clause", "#d60.k2"),
    (Address("49", "1", part="lead_in"), "clause_lead_in", "#d49.k1.lead"),
    (Address("60", "2", "e"), "point", "#d60.k2.e"),
    (Address("33a", "5a", "g1"), "point", "#d33a.k5a.g1"),
])
def test_provision_id_roundtrip(address, kind, suffix):
    pid = provision_id("luat:59/2020/QH14", address, kind)
    assert pid == "luat:59/2020/QH14" + suffix
    assert parse_provision_id(pid) == ("luat:59/2020/QH14", address, kind)


def test_unit_sort_key_vietnamese_order():
    assert sorted(["e", "đ", "d", "g1", "g", "a"], key=unit_sort_key) == ["a", "d", "đ", "e", "g", "g1"]
    assert sorted(["5a", "6", "5", "10"], key=unit_sort_key) == ["5", "5a", "6", "10"]


def test_fixtures_present():
    law = (FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8")
    amend = (FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8")
    assert len(re.findall(r"(?m)^Điều \d+[a-zđ]?\. ", law)) == 218
    assert "Điều 7. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp" in amend
