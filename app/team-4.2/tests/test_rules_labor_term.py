"""Điều 20.2 BLLĐ 45/2019 trong gói `labor`: loại HĐ hiệu lực (dữ kiện suy ra), giới hạn số lần ký và bốn ngoại lệ."""
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from rag.bridge.catalog import load_catalog
from rag.rules.evaluator import evaluator_for
from rag.rules.semantics import Fact

CAT = load_catalog()
DAY = date(2025, 3, 1)
XDTH, KXDTH = "xac_dinh_thoi_han", "khong_xac_dinh_thoi_han"
EXC = {"r3_state_director": "is_state_enterprise_director", "r3_elderly": "is_elderly_employee",
       "r3_foreign": "is_foreign_employee", "r3_union_leader": "is_union_leader_in_term"}
NO_EXC = {fact: Fact(False) for fact in EXC.values()}
LAW_TEXT = sorted((Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "legal" / "raw"
                   / "bo-luat_45_2019_QH14").glob("*.txt"))


def run(facts, present=("content.term",)):
    """Kết quả content.term/* theo rule id; hai evaluator phải cho kết quả giống hệt nhau."""
    dumps = {}
    for kind in ("reference", "network"):
        session = evaluator_for(CAT, kind).session(day=DAY, facts=dict(facts), present=set(present), evidence={})
        dumps[kind] = {f"{r.concept_id}/{r.rule_id}": r for r in session.results()}
    assert (json.dumps({k: asdict(v) for k, v in dumps["reference"].items()}, default=str, sort_keys=True)
            == json.dumps({k: asdict(v) for k, v in dumps["network"].items()}, default=str, sort_keys=True))
    return {k.split("/", 1)[1]: v for k, v in dumps["reference"].items() if k.startswith("content.term/")}


def expired(kind=XDTH, days=None, signed=None):
    facts = {"contract_kind": Fact(kind)}
    if days is not None:
        facts["worked_after_expiry_days"] = Fact(days, "day")
    if signed is not None:
        facts["new_contract_signed"] = Fact(signed)
    return facts


def test_effective_kind_boundary_30_days():
    for days in (20, 30):                                    # còn trong thời hạn ký (Đ20.2.a): vẫn xác định thời hạn
        assert run(expired(days=days, signed=False))["r4"].status == "NOT_APPLICABLE", days
    r4 = run(expired(days=31, signed=False))["r4"]           # quá 30 ngày chưa ký mới (Đ20.2.b): thành không xác định
    assert (r4.status, r4.finding) == ("FAIL", "violation")
    assert r4.facts_used["contract_kind_effective"] == {"value": KXDTH, "unit": None, "derived_by": "d20k2b"}
    assert r4.legality == "unknown" and r4.employee_impact == "neutral"
    assert run(expired(kind=KXDTH, days=45, signed=False))["r4"].status == "PASS"


def test_new_contract_signed_blocks_conversion():
    assert run(expired(days=45, signed=True))["r4"].status == "NOT_APPLICABLE"


def test_missing_inputs_are_unknown_not_violation():
    r4 = run(expired())["r4"]
    assert (r4.status, r4.finding) == ("UNKNOWN", "needs_facts")
    assert r4.missing_facts == ("worked_after_expiry_days", "new_contract_signed")
    assert "contract_kind_effective" not in r4.missing_facts and "derived_unknown:contract_kind_effective" in r4.reasons
    assert run(expired(days=45))["r4"].missing_facts == ("new_contract_signed",)
    assert run(expired(days=10))["r4"].status == "NOT_APPLICABLE"      # ≤ 30 ngày thì không cần biết đã ký mới chưa
    assert run(expired(signed=False))["r4"].missing_facts == ("worked_after_expiry_days",)
    for days in (None, 10, 31):
        for signed in (None, False, True):
            assert run(expired(days=days, signed=signed))["r4"].status != "FAIL" or (days, signed) == (31, False)


def test_limit_on_fixed_term_signings():
    base = {"contract_kind": Fact(XDTH), **NO_EXC}
    assert run({**base, "fixed_term_contract_count": Fact(2)})["r3"].status == "PASS"
    r3 = run({**base, "fixed_term_contract_count": Fact(3)})["r3"]
    assert (r3.status, r3.finding, r3.legality) == ("FAIL", "violation", "illegal")
    assert r3.law_values["max_fixed_term_contracts"]["value"] == 2
    assert run(base)["r3"].status == "UNKNOWN"
    assert run({"contract_kind": Fact(KXDTH), "fixed_term_contract_count": Fact(5), **NO_EXC})["r3"].status \
        == "NOT_APPLICABLE"
    assert run({"fixed_term_contract_count": Fact(3), **NO_EXC})["r3"].status == "UNKNOWN"   # chưa biết loại HĐ


def test_each_exception_overrides_limit():
    base = {"contract_kind": Fact(XDTH), "fixed_term_contract_count": Fact(3)}
    for rule_id, fact in EXC.items():
        out = run({**base, **NO_EXC, fact: Fact(True)})
        assert out["r3"].status == "NOT_APPLICABLE" and out["r3"].reasons == (f"overridden_by:content.term/{rule_id}",)
        assert out[rule_id].status == "PASS"
        assert all(out[o].status == "NOT_APPLICABLE" for o in EXC if o != rule_id)
    assert run({**base, **NO_EXC})["r3"].status == "FAIL"
    missing_one = {k: v for k, v in NO_EXC.items() if k != "is_elderly_employee"}
    r3 = run({**base, **missing_one})["r3"]
    assert (r3.status, r3.finding, r3.legality) == ("UNKNOWN", "needs_facts", None)
    assert r3.missing_facts == ("is_elderly_employee",) and "exception_unknown:content.term/r3_elderly" in r3.reasons
    both = run({**base, **NO_EXC, "is_elderly_employee": Fact(True), "is_foreign_employee": Fact(True)})["r3"]
    assert both.reasons == ("overridden_by:content.term/r3_elderly", "overridden_by:content.term/r3_foreign")


@pytest.mark.skipif(not LAW_TEXT, reason="không có kho luật cục bộ")
def test_phase3_rules_pinned_by_law_text():
    text = LAW_TEXT[0].read_text(encoding="utf-8")
    for phrase in ("không quá 36 tháng", "Trong thời hạn 30 ngày kể từ ngày hợp đồng lao động hết hạn",
                   "cũng chỉ được ký thêm 01 lần", "giám đốc trong doanh nghiệp có vốn nhà nước",
                   "khoản 1 Điều 149", "khoản 2 Điều 151", "khoản 4 Điều 177"):
        assert phrase in text, phrase
    term = CAT.concepts["content.term"]
    rules = {r.id: r for r in term.rules}
    assert rules["r2"].law["max_term"] == {"value": 36, "unit": "month"}
    assert rules["r3"].law["max_fixed_term_contracts"]["value"] == 1 + 1     # hợp đồng đầu + "01 lần" ký thêm
    derived = CAT.context.derived["contract_kind_effective"]
    exception = next(d for d in derived.definitions if d.id == "d20k2b")
    assert {"fact": "worked_after_expiry_days", "op": "gt", "value": 30, "unit": "day"} in exception.when["all"]
    assert {r.exception_of for r in term.rules if r.id in EXC} == {"content.term/r3"}


def test_user_answers_get_default_units_from_the_pack():
    """Trả lời `worked_after_expiry_days` bằng một con số (không đơn vị) vẫn được hiểu là ngày."""
    from rag.bridge.check import user_fact_set
    facts = user_fact_set({"worked_after_expiry_days": 45, "new_contract_signed": False, "contract_kind": XDTH})
    assert (facts["worked_after_expiry_days"].value, facts["worked_after_expiry_days"].unit) == (45, "day")
    assert facts["new_contract_signed"].unit is None
    assert run(facts)["r4"].status == "FAIL"


def test_limit_checked_even_when_term_clause_not_recognized():
    """Số lần ký là dữ kiện người dùng cung cấp: không phụ thuộc điều khoản thời hạn có được nhận ra hay không."""
    facts = {"contract_kind": Fact(XDTH), "fixed_term_contract_count": Fact(3), **NO_EXC}
    r3 = run(facts, present=())["r3"]
    assert (r3.status, r3.finding) == ("FAIL", "violation")
    assert run({"contract_kind": Fact(XDTH), **NO_EXC}, present=())["r3"].status == "PASS"   # chưa có dữ kiện: như cũ



@pytest.mark.parametrize("pid", ["nghi-dinh:38/2022/NĐ-CP", "nghi-dinh:74/2024/NĐ-CP", "nghi-dinh:293/2025/NĐ-CP"])
def test_minimum_wage_periods_match_decree_text(pid):
    """Mức lương tối thiểu vùng trong gói labor phải đúng bảng "Vùng I ... IV" của nghị định nguồn (kho ứng dụng)."""
    import re
    from legal_corpus import law_text
    text = law_text(pid)
    if text is None:
        pytest.skip("kho luật cục bộ không có " + pid)
    rule = CAT.concepts["wage.minimum_regional"].rules[0]
    period = next(p for p in rule.law["min_wage"]["periods"] if p["source"] == pid)
    for region, value in period["values"].items():
        m = re.search(rf"^Vùng {region}\s*\n\s*([\d.]+)", text, re.MULTILINE)
        assert m, (pid, region)
        assert int(m.group(1).replace(".", "")) == value, (pid, region, m.group(1), value)
