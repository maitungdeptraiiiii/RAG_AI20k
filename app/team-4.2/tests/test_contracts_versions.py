"""Phiên bản phụ lục: nối vào bản sao, bản cha nguyên vẹn, đối chiếu kết quả."""
from copy import deepcopy
from datetime import date

from rag.bridge.check import check_contract, report_json
from rag.contracts.doc import PageText
from rag.contracts.facts import extract_part_facts
from rag.contracts.graph.oplog import human_op
from rag.contracts.store import _dump
from rag.contracts.versions import (append_appendix, compare_results, copy_for_version, effective_date,
                                    reopen_changed_fields)

from tests.versions_helpers import APPENDIX_TEXT, AT, AppendixLLM, base_contract

PAGE = [PageText(1, APPENDIX_TEXT)]


def checked_parent():
    c = base_contract()
    check_contract(AppendixLLM(), c, at=AT)
    return c


def test_append_appendix_keeps_old_units_and_parent():
    parent = checked_parent()
    frozen = _dump(parent)
    v = copy_for_version(parent, "v" * 24, AT)
    assert v.lineage == {"family_id": "c" * 24, "version": 2, "parent_id": "c" * 24, "status": "draft", "linked": []}
    assert v.persist is False and v.concept_check is None
    assert [(o.op_id, o.status) for o in v.oplog.all()] == [(o.op_id, o.status) for o in parent.oplog.all()]
    assert {o.contract_id for o in v.oplog.all()} == {"v" * 24}
    assert append_appendix(v, PAGE, b"pl", "PHỤ LỤC HỢP ĐỒNG SỐ 01", AT) == "p1"
    old = [(u.uid, u.text.strip()) for u in parent.units]
    assert [(u.uid, u.text.strip()) for u in v.units if u.uid.startswith("p0.")] == old
    assert any(u.uid.startswith("p1.") for u in v.units)
    assert [p.page for p in v.page_texts] == [1, 2] and v.file_checksum != parent.file_checksum
    assert effective_date(v, "p1") == date(2025, 6, 1)
    assert _dump(parent) == frozen


def test_reopen_changed_fields_drops_only_those_answers():
    v = copy_for_version(checked_parent(), "v" * 24, AT)
    for target in ("fact:salary", "fact:labor_kind", "sign_date"):
        v.oplog.add(human_op(v.contract_id, "SET_FIELD", target, {"action": "set", "value": "x"}, "u", at=AT))
    reopen_changed_fields(v, ["salary", "sign_date"])
    human = {o.target for o in v.oplog.active() if o.origin == "human" and o.op_type == "SET_FIELD"}
    assert human == {"fact:labor_kind", "sign_date"}


def test_compare_results():
    r = {"concept_id": "a", "rule_id": "r1", "object": None, "status": "FAIL", "finding": "violation", "law_values": {},
         "facts_used": {"s": {"value": 1, "unit": "vnd", "uid": "p0.d1"}}, "evidence": ()}
    moved = r | {"evidence": ({"uid": "p1.d1"},), "facts_used": {"s": {"value": 1, "unit": "vnd", "uid": "p1.d1"}}}
    assert compare_results([r], [moved]) == {"changed": [], "added": [], "removed": [], "unchanged": 1}
    assert compare_results([r], [r | {"status": "PASS", "finding": "ok"}])["changed"][0]["key"] == "a/r1@"
    raised = r | {"facts_used": {"s": {"value": 2, "unit": "vnd"}}}
    assert len(compare_results([r], [raised])["changed"]) == 1
    assert compare_results([r], [])["removed"] == [r] and compare_results([], [r])["added"] == [r]


def run_appendix(llm, page=PAGE):
    parent = checked_parent()
    v = copy_for_version(parent, "v" * 24, AT)
    append_appendix(v, page, b"pl", "PHỤ LỤC HỢP ĐỒNG SỐ 01", AT)
    extract_part_facts(llm, v, "p1")
    new = [u.uid for u in v.units if u.uid.startswith("p1.")]
    day = date(2025, 7, 1)
    after = report_json(check_contract(llm, v, at=AT, only_units=new, day=day))["results"]
    before = report_json(check_contract(None, deepcopy(parent), at=AT, rules_only=True, day=day))["results"]
    return compare_results(before, after), after


def test_salary_appendix_changes_only_salary_rules():
    diff, after = run_appendix(AppendixLLM())
    keys = {c["key"] for c in diff["changed"]}
    assert keys and all("base_salary_vnd" in c["after"]["facts_used"] for c in diff["changed"])
    assert "leave.annual/r1@" not in keys and diff["added"] == [] and diff["removed"] == []
    assert not any("CONFLICT" in str(x["reasons"]).upper() for x in after)


def test_appendix_repeating_old_salary_changes_nothing():
    class Same(AppendixLLM):
        salary = "15.000.000 đồng/tháng"
        quote = "mức lương chính là 15.000.000 đồng/tháng"

    page = [PageText(1, APPENDIX_TEXT.replace("17.000.000", "15.000.000"))]
    diff, after = run_appendix(Same(), page)
    assert diff["changed"] == [] and diff["added"] == [] and diff["removed"] == []
