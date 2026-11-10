from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.legal.builder import applicable, build_versions
from rag.legal.directives import parse_directives
from rag.legal.effectivity import EffectivityInfo, parse_effectivity
from rag.legal.keys import document_key
from rag.legal.models import Address, AmendmentOperation, LegalDocument
from rag.legal.operations import build_operations, operation_id_for
from rag.legal.structure import index_provisions, parse_structure

FIXTURES = Path(__file__).parent / "fixtures" / "legal"
BASE = "luat:59/2020/QH14"
AMEND = "luat:03/2022/QH15"
FAKE = "luat:1/2020/QH14"


def doc(number, title, issued, vbpl_from=None):
    return LegalDocument(document_key("Luật", number), "1", title, "Luật", number, "Quốc hội", issued, vbpl_from,
                         None, None, False, "x.txt", "0" * 64, datetime(2026, 1, 1, tzinfo=timezone.utc))


def op(op_type, target, new_text=None, *, effective=date(2023, 1, 1), anchor=None, seq=1, source="luat:9/2022/QH15",
       status="auto_accepted", key=FAKE, old_phrase=None):
    return AmendmentOperation(operation_id_for(source, seq, op_type, target), source, date(2022, 6, 1), f"Điều {seq}",
                              Address(str(seq)), (0, 1), seq, key, "Luật X", op_type, target, anchor, new_text,
                              old_phrase, effective, "exact", status)


@pytest.fixture(scope="module")
def real():
    base_doc = doc("59/2020/QH14", "Luật Doanh nghiệp số 59/2020/QH14", date(2020, 6, 17), date(2021, 1, 1))
    amend_doc = doc("03/2022/QH15", "Luật sửa đổi số 03/2022/QH15", date(2022, 1, 11))
    base = parse_structure((FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8"), BASE)
    amend = parse_structure((FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8"), AMEND)
    ops = build_operations(amend_doc, parse_directives(amend), parse_effectivity(amend),
                           documents=[base_doc, amend_doc], indexes={BASE: index_provisions(base)})
    ops = [o for o in ops if o.target_document_key == BASE]
    versions = build_versions(base_doc, base, parse_effectivity(base), ops, build_id="b1")
    return base_doc, base, ops, versions


def history(versions, pid):
    return [v for v in versions if v.provision_id == pid]


FAKE_TEXT = ("Điều 17. Thẩm quyền\n4. Khoản bốn:\na) Điểm a;\nb) Điểm b;\nc) Điểm c;\nd) Điểm d.\n"
             "5. Khoản năm.\n6. Khoản sáu.\nĐiều 18. Khác\nNội dung.")
FAKE_EFF = EffectivityInfo(None, date(2021, 1, 1), (), (), None, ())


def fake_build(ops, text=FAKE_TEXT, eff=FAKE_EFF):
    d = doc("1/2020/QH14", "Luật X số 1/2020/QH14", date(2020, 6, 1), date(2021, 1, 1))
    return build_versions(d, parse_structure(text, FAKE), eff, ops, build_id="t")


def test_real_clause_changes_on_effective_date(real):
    *_, versions = real
    k3 = history(versions, f"{BASE}#d60.k3")
    assert [(v.valid_from, v.valid_to) for v in k3] == [(date(2021, 1, 1), date(2022, 3, 1)), (date(2022, 3, 1), None)]
    assert k3[1].text.startswith("3. Trường hợp chủ tọa, người ghi biên bản từ chối ký")
    assert k3[0].text != k3[1].text
    assert len(k3[1].source_operations) == 1
    assert [v.valid_from for v in history(versions, f"{BASE}#d60")] == [date(2021, 1, 1), date(2022, 3, 1)]
    assert [(v.valid_from, v.valid_to) for v in history(versions, f"{BASE}#d61")] == [(date(2021, 1, 1), None)]


def test_title_change_only_title_leaf(real):
    *_, versions = real
    assert len(history(versions, f"{BASE}#d50.title")) == 2
    assert history(versions, f"{BASE}#d50.title")[1].text == "Nghĩa vụ của thành viên công ty"
    assert all(len(history(versions, f"{BASE}#d50.k{k}")) == 1 for k in ("1", "2"))


def test_insert_clause_order():
    versions = fake_build([op("INSERT_CLAUSE", Address("17", "5a"), "5a. Khoản năm a.", anchor=Address("17", "5"))])
    art = [v for v in history(versions, f"{FAKE}#d17") if v.valid_from == date(2023, 1, 1)][0]
    lines = [l.split(".")[0] for l in art.text.split("\n") if l[:1].isdigit()]
    assert lines == ["4", "5", "5a", "6"]
    assert [v.valid_from for v in history(versions, f"{FAKE}#d17.k5a")] == [date(2023, 1, 1)]


def test_delete_point_closes_version():
    versions = fake_build([op("DELETE_POINT", Address("17", "4", "d"))])
    assert [(v.valid_from, v.valid_to) for v in history(versions, f"{FAKE}#d17.k4.d")] == [(date(2021, 1, 1), date(2023, 1, 1))]
    assert "d) Điểm d." not in history(versions, f"{FAKE}#d17.k4")[-1].text


def test_replace_text_in_unit():
    versions = fake_build([op("REPLACE_TEXT", Address("17", "5"), "Khoản 5 mới", old_phrase="Khoản năm")])
    assert history(versions, f"{FAKE}#d17.k5")[-1].text == "5. Khoản 5 mới."


def test_replace_clause_with_points():
    versions = fake_build([op("REPLACE_CLAUSE", Address("17", "4"), "4. Khoản bốn mới:\na) X;\nb) Y.")])
    assert history(versions, f"{FAKE}#d17.k4.c")[-1].valid_to == date(2023, 1, 1)
    assert history(versions, f"{FAKE}#d17.k4.a")[-1].text == "a) X;"
    assert history(versions, f"{FAKE}#d17.k4.lead")[-1].text == "4. Khoản bốn mới:"


def test_non_applicable_ops_ignored():
    pending = op("DELETE_POINT", Address("17", "4", "d"), status="pending")
    no_date = op("DELETE_POINT", Address("17", "4", "c"), effective=None, seq=2)
    assert not applicable(pending) and not applicable(no_date)
    versions = fake_build([pending, no_date])
    for p in "cd":   # nội dung không đổi; việc tách phiên bản để gắn cờ là của Task 8
        h = history(versions, f"{FAKE}#d17.k4.{p}")
        assert len({v.text for v in h}) == 1 and h[-1].valid_to is None


def test_no_overlapping_intervals(real):
    *_, versions = real
    by_pid = {}
    for v in versions:
        by_pid.setdefault(v.provision_id, []).append(v)
    for vs in by_pid.values():
        for a, b in zip(vs, vs[1:]):
            assert a.valid_to == b.valid_from
            assert a.valid_from < a.valid_to


def test_deterministic(real):
    base_doc, base, ops, versions = real
    again = build_versions(base_doc, base, parse_effectivity(base), list(reversed(ops)), build_id="b1")
    assert again == versions


def test_effectivity_article_amended_rebuilds():
    text = "Điều 1. Phạm vi\nNội dung.\nĐiều 9. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025."
    provisions = parse_structure(text, FAKE)
    amend = op("REPLACE_ARTICLE", Address("9"),
               "Điều 9. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.",
               effective=date(2024, 8, 1))
    d = doc("1/2020/QH14", "Luật X", date(2024, 1, 18), date(2025, 1, 1))
    versions = build_versions(d, provisions, parse_effectivity(provisions), [amend], build_id="t")
    assert {v.valid_from for v in versions} == {date(2024, 8, 1)}
    assert "01 tháng 8 năm 2024" in history(versions, f"{FAKE}#d9")[0].text


def test_conditional_unit_needs_review():
    text = ("Điều 60. A\n9. Khoản chín.\n10. Khoản mười.\nĐiều 252. Hiệu lực thi hành\n"
            "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.\n"
            "Khoản 9 Điều 60 của Luật này có hiệu lực thi hành từ ngày Nghị quyết số 61/2022/QH15 hết hiệu lực.")
    provisions = parse_structure(text, FAKE)
    d = doc("1/2020/QH14", "Luật X", date(2024, 1, 18), date(2025, 1, 1))
    versions = build_versions(d, provisions, parse_effectivity(provisions), [], build_id="t")
    k9 = history(versions, f"{FAKE}#d60.k9")
    assert k9[0].verification_status == "needs_review" and "effectivity.conditional_unit" in k9[0].status_reasons
    assert history(versions, f"{FAKE}#d60.k10")[0].verification_status == "verified"


def test_lead_in_of_clause_without_points_replaces_first_paragraph():
    # Luật 43/2024/QH15 sửa "khổ đầu khoản 4 Điều 260" — khoản 4 gồm hai đoạn, không có điểm
    text = "Điều 260. Chuyển tiếp\n4. Đoạn đầu cũ.\nĐoạn thứ hai giữ nguyên.\n5. Khoản năm."
    o = op("REPLACE_CLAUSE_LEAD_IN", Address("260", "4", part="lead_in"), "4. Đoạn đầu mới.")
    k4 = history(fake_build([o], text=text), f"{FAKE}#d260.k4")
    assert k4[-1].text == "4. Đoạn đầu mới.\nĐoạn thứ hai giữ nguyên."
