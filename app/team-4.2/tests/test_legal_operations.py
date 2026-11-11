from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.legal.directives import parse_directives
from rag.legal.effectivity import EffectivityInfo, RepealStatement, parse_effectivity
from rag.legal.keys import document_key
from rag.legal.models import Address, LegalDocument
from rag.legal.operations import build_operations, operation_id_for, repeal_operations
from rag.legal.structure import index_provisions, parse_structure

FIXTURES = Path(__file__).parent / "fixtures" / "legal"
BASE = "luat:59/2020/QH14"
AMEND = "luat:03/2022/QH15"


def doc(doc_type, number, title, issued):
    return LegalDocument(document_key(doc_type, number), "1", title, doc_type, number, "Quốc hội", issued,
                         None, None, None, False, "x.txt", "0" * 64, datetime(2026, 1, 1, tzinfo=timezone.utc))


BASE_DOC = doc("Luật", "59/2020/QH14", "Luật Doanh nghiệp số 59/2020/QH14", date(2020, 6, 17))
AMEND_DOC = doc("Luật", "03/2022/QH15", "Luật sửa đổi, bổ sung ... số 03/2022/QH15", date(2022, 1, 11))


@pytest.fixture(scope="module")
def setup():
    base = parse_structure((FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8"), BASE)
    amend = parse_structure((FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8"), AMEND)
    return {"indexes": {BASE: index_provisions(base)}, "directives": parse_directives(amend),
            "effectivity": parse_effectivity(amend)}


def run(setup, directives=None, effectivity=None):
    return build_operations(AMEND_DOC, directives if directives is not None else setup["directives"],
                            effectivity or setup["effectivity"], documents=[BASE_DOC, AMEND_DOC],
                            indexes=setup["indexes"])


def test_real_enterprise_ops_auto_accepted(setup):
    ops = [o for o in run(setup) if o.target_document_key == BASE]
    assert len(ops) == 10
    assert {o.review_status for o in ops} == {"auto_accepted"}
    assert {o.effective_from for o in ops} == {date(2022, 3, 1)}
    assert all(o.parse_status == "exact" and o.source_issued_on == date(2022, 1, 11) for o in ops)


def test_unknown_target_law_pending(setup):
    ops = [o for o in run(setup) if o.target_law_name == "Luật Đầu tư công"]
    assert ops and all(o.review_status == "pending" for o in ops)
    assert all("operation.target_law_not_found" in o.status_reasons for o in ops)


def test_label_mismatch_pending(setup):
    ds = [replace(d, new_text="4. " + d.new_text[3:]) if d.target == Address("60", "3") else d
          for d in setup["directives"]]
    op = next(o for o in run(setup, ds) if o.target == Address("60", "3"))
    assert op.review_status == "pending" and "operation.label_mismatch" in op.status_reasons


def test_missing_target_pending(setup):
    ds = [replace(d, target=Address("60", "9")) if d.target == Address("60", "3") else d for d in setup["directives"]]
    op = next(o for o in run(setup, ds) if o.target == Address("60", "9"))
    assert op.review_status == "pending" and "operation.target_missing" in op.status_reasons


def test_flags_make_everything_pending(setup):
    eff = replace(setup["effectivity"], flags=("effectivity.relative_date: x",))
    ops = run(setup, effectivity=eff)
    assert {o.review_status for o in ops} == {"pending"}
    assert all("effectivity.relative_date: x" in o.status_reasons for o in ops)


def test_operation_id_deterministic(setup):
    assert [o.operation_id for o in run(setup)] == [o.operation_id for o in run(setup)]
    assert operation_id_for(AMEND, 1, "REPLACE_CLAUSE", Address("60", "3")) != operation_id_for(AMEND, 2, "REPLACE_CLAUSE", Address("60", "3"))


def test_transition_note_attached(setup):
    ops = run(setup)
    assert all(f"note:transition:{AMEND}#d11" in o.status_reasons for o in ops)


def test_replace_text_requires_unique_phrase(setup):
    d = next(d for d in setup["directives"] if d.target == Address("60", "3"))
    unique = replace(d, operation_type="REPLACE_TEXT", old_phrase="tham dự họp ký", new_text="X")
    repeated = replace(d, operation_type="REPLACE_TEXT", old_phrase="biên bản", new_text="X")
    a, b = run(setup, [unique, replace(repeated, sequence=999)])
    assert a.review_status == "auto_accepted"
    assert b.review_status == "pending" and "operation.phrase_not_unique" in b.status_reasons


def test_insert_requires_anchor_and_new_unit(setup):
    d = next(d for d in setup["directives"] if d.target == Address("60", "3"))
    good = replace(d, operation_type="INSERT_CLAUSE", target=Address("60", "3a"), anchor=Address("60", "3"),
                   new_text="3a. Nội dung mới.")
    exists = replace(good, target=Address("60", "2"), new_text="2. X", sequence=998)
    ops = run(setup, [good, exists])
    assert ops[0].review_status == "auto_accepted"
    assert ops[1].review_status == "pending" and "operation.target_exists" in ops[1].status_reasons


def test_repeal_operation():
    old = doc("Luật", "65/2014/QH13", "Luật Nhà ở số 65/2014/QH13", date(2014, 11, 25))
    new = doc("Luật", "27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", date(2023, 11, 27))
    info = EffectivityInfo("198", date(2024, 8, 1), (), (RepealStatement("Luật Nhà ở", "65/2014/QH13", date(2024, 8, 1), False, (0, 10)),), None, ())
    (op,) = repeal_operations(new, info, documents=[old, new])
    assert (op.operation_type, op.target_document_key, op.review_status) == ("REPEAL_DOCUMENT", "luat:65/2014/QH13", "auto_accepted")
    assert op.effective_from == date(2024, 8, 1) and op.target is None
    exc = replace(info, repeals=(replace(info.repeals[0], has_exception=True),))
    (op2,) = repeal_operations(new, exc, documents=[old, new])
    assert op2.review_status == "auto_accepted" and "note:transition_exception" in op2.status_reasons


def test_lead_in_target_accepts_clause_without_points(setup):
    d = next(d for d in setup["directives"] if d.target == Address("60", "3"))
    lead = replace(d, operation_type="REPLACE_CLAUSE_LEAD_IN", target=Address("60", "3", part="lead_in"),
                   new_text="3. Đoạn đầu mới.")
    (o,) = run(setup, [lead])
    assert o.review_status == "auto_accepted", o.status_reasons
