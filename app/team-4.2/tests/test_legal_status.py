from dataclasses import replace
from datetime import date, datetime, timezone

from rag.legal.builder import build_versions
from rag.legal.effectivity import EffectivityInfo, parse_effectivity
from rag.legal.keys import document_key
from rag.legal.models import Address, AmendmentOperation, LegalDocument
from rag.legal.operations import operation_id_for
from rag.legal.status import demote_amended_directives
from rag.legal.structure import parse_structure

KEY = "luat:1/2020/QH14"
TEXT = ("Điều 5. Chung\n1. Do Bộ Kế hoạch và Đầu tư hướng dẫn.\n2. Khoản hai.\n"
        "Điều 9. Khác\n2. Khoản hai:\na) Gửi Bộ Kế hoạch và Đầu tư;\nb) Điểm b.\n"
        "Điều 10. Mười\n1. Khoản một.\n2. Khoản hai.\n"
        "Điều 17. Thẩm quyền\n4. Khoản bốn:\na) Điểm a;\nb) Điểm b;\nc) Điểm c;\nd) Điểm d.\n5. Khoản năm.")
EFF = EffectivityInfo(None, date(2021, 1, 1), (), (), None, ())


def doc(vbpl_from=date(2021, 1, 1), key_number="1/2020/QH14"):
    return LegalDocument(document_key("Luật", key_number), "1", "Luật X", "Luật", key_number, "Quốc hội",
                         date(2020, 6, 1), vbpl_from, None, None, False, "x.txt", "0" * 64,
                         datetime(2026, 1, 1, tzinfo=timezone.utc))


def op(op_type, target, new_text=None, *, effective=date(2023, 1, 1), seq=1, source="luat:9/2022/QH15",
       status="auto_accepted", parse="exact", old_phrase=None, reasons=(), key=KEY, source_article=None):
    return AmendmentOperation(operation_id_for(source, seq, op_type, target), source, date(2022, 6, 1), f"Điều {seq}",
                              Address(source_article or str(seq)), (0, 1), seq, key, "Luật X", op_type, target, None,
                              new_text, old_phrase, effective, parse, status, tuple(reasons))


def build(ops, *, text=TEXT, eff=EFF, d=None, default_dates=None):
    return build_versions(d or doc(), parse_structure(text, KEY), eff, ops, build_id="t", default_dates=default_dates)


def hist(versions, suffix):
    return [v for v in versions if v.provision_id == KEY + suffix]


def test_pending_point_flags_ancestors_not_siblings():
    p = op("REPLACE_POINT", Address("17", "4", "c"), "c) Mới.", status="pending")
    vs = build([p])
    for suffix in ("#d17.k4.c", "#d17.k4", "#d17"):
        h = hist(vs, suffix)
        assert [(v.valid_from, v.verification_status) for v in h] == [(date(2021, 1, 1), "verified"), (date(2023, 1, 1), "needs_review")]
        assert f"operation.pending:{p.operation_id}" in h[1].status_reasons
        assert h[0].text == h[1].text
    assert [v.verification_status for v in hist(vs, "#d17.k4.d")] == ["verified"]
    assert [v.verification_status for v in hist(vs, "#d17.k5")] == ["verified"]


def test_pending_without_date_uses_source_default():
    p = op("REPLACE_POINT", Address("17", "4", "c"), "c) Mới.", status="pending", effective=None)
    vs = build([p], default_dates={"luat:9/2022/QH15": date(2022, 3, 1)})
    assert [v.valid_from for v in hist(vs, "#d17.k4.c")] == [date(2021, 1, 1), date(2022, 3, 1)]


def test_pending_without_any_date_flags_from_start():
    p = op("REPLACE_POINT", Address("17", "4", "c"), "c) Mới.", status="pending", effective=None)
    vs = build([p])
    assert [v.verification_status for v in hist(vs, "#d17.k4.c")] == ["needs_review"]


def test_bulk_phrase_flags_all_occurrences():
    bulk = op("REPLACE_TEXT", None, "Bộ Tài chính", status="pending", parse="partial", old_phrase="Bộ Kế hoạch và Đầu tư",
              reasons=("operation.bulk_text_scope",))
    vs = build([bulk])
    for suffix in ("#d5.k1", "#d5", "#d9.k2.a", "#d9.k2", "#d9"):
        assert hist(vs, suffix)[-1].verification_status == "needs_review", suffix
    for suffix in ("#d5.k2", "#d9.k2.b", "#d10"):
        assert {v.verification_status for v in hist(vs, suffix)} == {"verified"}, suffix


def test_unscoped_failed_op_flags_whole_document():
    failed = op("UNSUPPORTED", None, status="pending", parse="failed", reasons=("operation.unparsed_header",))
    vs = build([failed])
    assert {v.verification_status for v in vs if v.valid_from >= date(2023, 1, 1)} == {"needs_review"}


def test_unsupported_appendix_without_target_flags_nothing():
    appendix = op("UNSUPPORTED", None, status="pending", parse="unsupported",
                  reasons=("operation.unsupported_table_or_appendix",))
    assert {v.verification_status for v in build([appendix])} == {"verified"}


def test_same_day_conflict():
    a = op("REPLACE_CLAUSE", Address("10", "2"), "2. Bản A.", effective=date(2025, 7, 1), source="luat:1/2025/QH15")
    b = op("REPLACE_CLAUSE", Address("10", "2"), "2. Bản B.", effective=date(2025, 7, 1), source="luat:2/2025/QH15")
    h = hist(build([a, b]), "#d10.k2")
    assert h[-1].valid_from == date(2025, 7, 1) and h[-1].verification_status == "conflicted"
    assert any(r.startswith("operation.conflict:") for r in h[-1].status_reasons)
    assert h[0].verification_status == "verified"


def test_same_source_same_day_is_not_conflict():
    a = op("REPLACE_POINT", Address("17", "4", "a"), "a) A.", seq=1)
    b = op("REPLACE_CLAUSE_LEAD_IN", Address("17", "4", part="lead_in"), "4. Lead mới:", seq=2)
    assert {v.verification_status for v in build([a, b])} == {"verified"}


def test_repeal_closes_document():
    rep = op("REPEAL_DOCUMENT", None, effective=date(2024, 8, 1))
    vs = build([rep])
    assert all(v.valid_to == date(2024, 8, 1) for v in vs)
    assert all(v.valid_from < date(2024, 8, 1) for v in vs)


def test_repeal_drops_versions_after_date():
    change = op("REPLACE_CLAUSE", Address("10", "2"), "2. Mới.", effective=date(2025, 1, 1), seq=2)
    rep = op("REPEAL_DOCUMENT", None, effective=date(2024, 8, 1))
    h = hist(build([change, rep]), "#d10.k2")
    assert [(v.valid_from, v.valid_to) for v in h] == [(date(2021, 1, 1), date(2024, 8, 1))]


def test_repeal_with_exception_note():
    rep = op("REPEAL_DOCUMENT", None, effective=date(2024, 8, 1), reasons=("note:transition_exception",))
    vs = build([rep])
    assert all("note:transition_exception" in v.notes and v.verification_status == "verified" for v in vs)


def test_transition_note_on_created_versions():
    change = op("REPLACE_CLAUSE", Address("10", "2"), "2. Mới.", reasons=("note:transition:luat:9/2022/QH15#d11",))
    h = hist(build([change]), "#d10.k2")
    assert h[0].notes == () and h[1].notes == ("note:transition:luat:9/2022/QH15#d11",)


def test_vbpl_mismatch_flags_when_unexplained():
    vs = build([], d=doc(vbpl_from=date(2025, 7, 1)))
    assert {v.verification_status for v in vs} == {"needs_review"}
    assert all("effectivity.vbpl_mismatch" in v.status_reasons for v in vs)
    text = TEXT + "\nĐiều 30. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025."
    provs = parse_structure(text, KEY)
    amend = op("REPLACE_ARTICLE", Address("30"), "Điều 30. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2024.",
               effective=date(2024, 7, 1))
    vs2 = build_versions(doc(vbpl_from=date(2025, 1, 1)), provs, parse_effectivity(provs), [amend], build_id="t")
    assert {v.verification_status for v in vs2} == {"verified"}
    assert all("note:vbpl_effective_from_outdated" in v.notes for v in vs2 if v.valid_from == date(2024, 7, 1))


def test_amended_amending_law_demotes():
    a_key = "luat:03/2022/QH15"
    a7 = op("REPLACE_CLAUSE", Address("60", "3"), "3. X.", source=a_key, seq=7, key="luat:59/2020/QH14", source_article="7")
    a9 = op("REPLACE_ARTICLE", Address("55"), "Điều 55. X", source=a_key, seq=9, key="luat:x", source_article="9")
    b = op("REPLACE_CLAUSE", Address("7", "3"), "3. Sửa chỉ dẫn.", source="luat:22/2023/QH15", key=a_key)
    out = {o.operation_id: o for o in demote_amended_directives([a7, a9, b], directive_articles={a_key: {"7", "9"}})}
    assert out[a7.operation_id].review_status == "pending"
    assert any(r == f"operation.source_amended:{b.operation_id}" for r in out[a7.operation_id].status_reasons)
    assert out[a9.operation_id].review_status == "auto_accepted"
    assert out[b.operation_id] == b
