"""Rule xuyên văn bản của gói labor (D26): Đ20.2.c đếm HĐ xác định thời hạn, Đ20.2.b theo từng HĐ, Đ22.2 phụ lục
sửa thời hạn, Đ25 thử việc một lần cho một công việc. Hồ sơ dựng tay theo kịch bản b1–b5, a1 của checklist."""
import json
from dataclasses import asdict
from datetime import date

from rag.bridge.catalog import load_catalog
from rag.rules.evaluator import evaluator_for
from rag.rules.objects import ObjectChanges, WorkingObject
from rag.rules.semantics import Fact

CAT = load_catalog()
DAY = date(2025, 3, 1)
XDTH, KXDTH = "xac_dinh_thoi_han", "khong_xac_dinh_thoi_han"
NO_EXC = {k: Fact(False) for k in ("is_state_enterprise_director", "is_elderly_employee", "is_foreign_employee",
                                   "is_union_leader_in_term")}


def contract(cid, kind=XDTH, start=date(2020, 1, 1), end=None, employee="E1", **attrs):
    values = {"kind": Fact(kind), "worked_after_expiry_days": Fact(0, "day"), **{
        k: v if isinstance(v, Fact) else Fact(v, "day" if k == "worked_after_expiry_days" else None)
        for k, v in attrs.items()}}
    return WorkingObject(cid, "Contract", values, start, end, {"employee": employee})


def amendment(aid, contract_id, modifies_term, start=date(2021, 1, 1)):
    return WorkingObject(aid, "Amendment", {"modifies_term": Fact(modifies_term)}, start, None, {"contract": contract_id})


def run(objects, facts=None):
    out = {}
    for kind in ("reference", "network"):
        s = evaluator_for(CAT, kind).session(day=DAY, facts=dict(facts or {}), present=set(), evidence={},
                                             objects=objects)
        out[kind] = {(f"{r.concept_id}/{r.rule_id}", r.object): r for r in s.results()}
    assert json.dumps({str(k): asdict(v) for k, v in out["reference"].items()}, default=str, sort_keys=True) == \
        json.dumps({str(k): asdict(v) for k, v in out["network"].items()}, default=str, sort_keys=True)
    return out["reference"]


def test_flat_contract_without_objects_is_unchanged():
    out = run([], {"contract_kind": Fact(XDTH)})
    for key in ("content.term/r5", "content.term/r6", "content.term/r7", "probation.once/r2"):
        r = out[(key, None)]
        assert (r.status, r.reasons) == ("NOT_APPLICABLE", ("no_objects",)), key


def test_b1_third_fixed_term_contract_violates_art_20_2_c():
    b1 = [contract("h1", end=date(2021, 1, 1)), contract("h2", start=date(2021, 1, 2), end=date(2022, 1, 1)),
          contract("h3", start=date(2022, 1, 2))]
    r = run(b1, NO_EXC)[("content.term/r5", "employee=E1")]
    assert (r.status, r.finding, r.legality) == ("FAIL", "violation", "illegal") and "count:3..3" in r.reasons
    assert run(b1[:2], NO_EXC)[("content.term/r5", "employee=E1")].status == "PASS"


def test_b2_exception_and_unknown_exception():
    b1 = [contract(f"h{i}", start=date(2020 + i, 1, 1)) for i in range(3)]
    assert run(b1, {**NO_EXC, "is_elderly_employee": Fact(True)})[("content.term/r5", "employee=E1")].status \
        == "NOT_APPLICABLE"
    r = run(b1)[("content.term/r5", "employee=E1")]                         # chưa biết ngoại lệ nào
    assert (r.status, r.finding) == ("UNKNOWN", "needs_facts")


def test_b3_expired_contract_still_working_converts_per_contract():
    b3 = [contract("h1", end=date(2024, 12, 31), worked_after_expiry_days=45, new_contract_signed=False)]
    r = run(b3)[("content.term/r6", "employee=E1")]
    assert (r.status, r.finding) == ("FAIL", "violation") and r.legality == "unknown"
    late = [contract("h1", end=date(2024, 12, 31), worked_after_expiry_days=20, new_contract_signed=False)]
    assert run(late)[("content.term/r6", "employee=E1")].status == "PASS"
    unknown = [contract("h1", end=date(2024, 12, 31), worked_after_expiry_days=45)]
    assert run(unknown)[("content.term/r6", "employee=E1")].status == "UNKNOWN"


def test_b4_adding_a_missing_contract_updates_the_count_incrementally():
    b3 = [contract("h1", end=date(2022, 1, 1)), contract("h2", start=date(2022, 1, 2))]
    for kind in ("reference", "network"):
        s = evaluator_for(CAT, kind).session(day=DAY, facts=dict(NO_EXC), present=set(), evidence={}, objects=b3)
        assert next(r for r in s.results() if r.rule_id == "r5").status == "PASS"
        diff = s.update({}, objects=ObjectChanges(added=(contract("h0", start=date(2019, 1, 1), end=date(2019, 12, 31)),)))
        change = next(c for c in diff.changes if c.rule_id == "r5")
        assert (change.object, change.before.status, change.after.status) == ("employee=E1", "PASS", "FAIL")
        diff = s.update({}, objects=ObjectChanges(removed=("h0",)))
        assert next(c for c in diff.changes if c.rule_id == "r5").after.status == "PASS"


def test_b5_probation_twice_for_the_same_job_art_25():
    same = [contract("h1", has_probation=True, job="ke_toan", end=date(2022, 1, 1)),
            contract("h2", start=date(2022, 1, 2), has_probation=True, job="ke_toan")]
    r = run(same)[("probation.once/r2", "employee=E1,job=ke_toan")]
    assert (r.status, r.finding) == ("FAIL", "violation")
    other = [same[0], contract("h2", start=date(2022, 1, 2), has_probation=True, job="ban_hang")]
    out = run(other)
    assert out[("probation.once/r2", "employee=E1,job=ke_toan")].status == "PASS"
    assert out[("probation.once/r2", "employee=E1,job=ban_hang")].status == "PASS"


def test_a1_amendment_must_not_change_the_term_art_22_2():
    a1 = [contract("h1", kind=KXDTH), amendment("p1", "h1", False), amendment("p2", "h1", True)]
    r = run(a1)[("content.term/r7", "contract=h1")]
    assert (r.status, r.finding, r.legality) == ("FAIL", "violation", "illegal")
    ok = [contract("h1", kind=KXDTH), amendment("p1", "h1", False)]
    assert run(ok)[("content.term/r7", "contract=h1")].status == "PASS"
    future = [contract("h1", kind=KXDTH), amendment("p2", "h1", True, start=date(2026, 1, 1))]
    assert run(future)[("content.term/r7", "contract=h1")].status == "PASS"           # chưa hiệu lực ngày soát
