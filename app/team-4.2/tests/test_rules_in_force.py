"""Luật chưa có hiệu lực khi ký hợp đồng (hạn chế 7.23, M.8, N.6): mỗi rule biết ngày luật của nó có hiệu lực và cách
áp cho hợp đồng ký trước ngày đó, khai trong concepts.yaml (`in_force`), đọc từ điều khoản chuyển tiếp của từng luật:

- `apply`: luật mới áp cả cho hợp đồng cũ (BLLĐ 45/2019 Đ220.2);
- `conforming_only`: hợp đồng cũ phù hợp luật mới thì áp luật mới, khác thì áp luật cũ (BLDS 91/2015 Đ688.1, Luật BVQLNTD
  19/2023 Đ80.1) -> rule có thể PASS, không thể FAIL theo luật mới;
- `skip`: không soát (Luật Nhà ở không có quy định chuyển tiếp cho nội dung hợp đồng thuê; luật không hồi tố)."""
from datetime import date

import pytest

from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_packs
from rag.rules.model import CatalogError
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

LOAN = load_packs(["civil_loan"])
LEASE = load_packs(["civil_lease"])


def results(cat, day, facts, present=()):
    out = {}
    for kind in ("reference", "network"):
        s = evaluator_for(cat, kind).session(day=day, facts=facts, present=set(present), evidence={})
        out[kind] = {f"{r.concept_id}/{r.rule_id}": r for r in s.results()}
    assert out["reference"] == out["network"]
    return out["reference"]


def _rule(cat, key):
    cid, rid = key.split("/")
    return next(r for r in cat.concepts[cid].rules if r.id == rid)


def test_merged_catalog_keeps_each_pack_date():
    assert (_rule(LOAN, "civil.unilateral_termination/r1").in_force_from, _rule(LOAN, "civil.unilateral_termination/r1")
            .earlier_contracts) == (date(2017, 1, 1), "conforming_only")
    assert _rule(LOAN, "loan.lender_early_recall/r1").in_force_from == date(2017, 1, 1)
    cap = _rule(LOAN, "loan.interest_cap/r1")              # có kỳ giá trị: kỳ tự quyết, không nhận in_force của gói
    assert (cap.in_force_from, cap.earlier_contracts) == (None, "apply")
    labor = load_packs(["labor"])
    assert all(r.earlier_contracts == "apply" for c in labor.concepts.values() for r in c.rules)


def test_violation_of_blds2015_rule_before_2017_is_not_judged_by_new_law():
    facts = {"lender_may_recall_early_without_consent": Fact(True), "recall_only_on_misuse": Fact(False)}
    old = results(LOAN, date(2012, 5, 1), facts, present=("loan.lender_early_recall",))["loan.lender_early_recall/r1"]
    assert old.status == "NOT_APPLICABLE"
    assert {"law_not_in_force:2017-01-01", "earlier_law_governs"} <= set(old.reasons)
    new = results(LOAN, date(2018, 5, 1), facts, present=("loan.lender_early_recall",))["loan.lender_early_recall/r1"]
    assert new.status == "FAIL"


def test_conforming_old_contract_still_passes():
    facts = {"lender_may_recall_early_without_consent": Fact(False), "recall_only_on_misuse": Fact(False)}
    r = results(LOAN, date(2012, 5, 1), facts, present=("loan.lender_early_recall",))["loan.lender_early_recall/r1"]
    assert r.status == "PASS"


def test_period_rule_keeps_old_period():
    facts = {"interest_rate": Fact(15, "percent_per_year"), "special_law_applies": Fact(False)}
    r = results(LOAN, date(2012, 5, 1), facts, present=("loan.interest_cap",))["loan.interest_cap/r1"]
    assert (r.status, r.law_values["max_interest"]["value"]) == ("FAIL", 13.5)


def test_skip_pack_does_not_review_contract_signed_before_law():
    old = results(LEASE, date(2014, 3, 1), {})["lease.content_property/r1"]
    assert old.status == "NOT_APPLICABLE" and "law_not_in_force:2015-07-01" in old.reasons
    assert results(LEASE, date(2016, 3, 1), {})["lease.content_property/r1"].status == "FAIL"


def test_lease_blds_concepts_follow_blds_date():
    assert _rule(LEASE, "lease.quiet_enjoyment/r1").in_force_from == date(2017, 1, 1)
    assert _rule(LEASE, "lease.quiet_enjoyment/r1").earlier_contracts == "conforming_only"


def _synth(tmp_path, in_force=None, concept_in_force=None):
    c = concept("x.a", [rule("r1", check={"fact": "flag", "op": "eq", "value": False})],
                slots={"flag": {"kind": "bool", "unit": None}})
    if concept_in_force is not None:
        c["in_force"] = concept_in_force
    body = {"version": "t", "law_values_valid_from": "2021-01-01", "roles": [
        {"id": "NLD", "label": "a"}, {"id": "NSDLD", "label": "b"}], "concepts": [c]}
    if in_force is not None:
        body["in_force"] = in_force
    pid = write_pack(tmp_path, {}, body)
    return load_packs([pid], root=tmp_path)


def test_default_is_skip_from_law_values_valid_from(tmp_path):
    r = _rule(_synth(tmp_path), "x.a/r1")
    assert (r.in_force_from, r.earlier_contracts) == (date(2021, 1, 1), "skip")


def test_apply_evaluates_old_contract_as_before(tmp_path):
    cat = _synth(tmp_path, in_force={"earlier_contracts": "apply"})
    r = results(cat, date(2019, 1, 1), {"flag": Fact(True)}, present=("x.a",))["x.a/r1"]
    assert r.status == "FAIL" and not any(x.startswith("law_not_in_force") for x in r.reasons)


def test_concept_overrides_pack(tmp_path):
    cat = _synth(tmp_path, in_force={"earlier_contracts": "apply"},
                 concept_in_force={"from": "2023-01-01", "earlier_contracts": "skip"})
    r = _rule(cat, "x.a/r1")
    assert (r.in_force_from, r.earlier_contracts) == (date(2023, 1, 1), "skip")


@pytest.mark.parametrize("bad", [{"earlier_contracts": "maybe"}, {"from": "not-a-date"}, "2020-01-01",
                                 {"from": "2020-01-01", "extra": 1}])
def test_bad_in_force_is_catalog_error(tmp_path, bad):
    with pytest.raises(CatalogError):
        _synth(tmp_path, in_force=bad)


class _SignedLLM:
    """LLM giả của hợp đồng vay mẫu nhưng ngày ký đổi được (None = hợp đồng không ghi ngày ký)."""

    def __init__(self, sign: str | None):
        import pack_cases
        self.inner, self.sign = pack_cases.ScriptedLoanLLM(), sign

    def complete(self, system, user):
        import json
        out = json.loads(self.inner.complete(system, user))
        if "sign_date" in out:
            if self.sign is None:
                out.pop("sign_date")
            else:
                out["sign_date"]["value"] = self.sign
        return json.dumps(out, ensure_ascii=False)


def _run(sign):
    import pack_cases
    from rag.bridge.check import check_contract
    return check_contract(_SignedLLM(sign), pack_cases.loan_contract(), at=pack_cases.AT, packs=["civil_loan"],
                          user_facts={"special_law_applies": False})


def test_report_warns_rules_skipped():
    from rag.bridge.check import in_force_warnings
    from rag.rules.semantics import RuleResult

    def res(cid, *reasons):
        return RuleResult(cid, "r1", "NOT_APPLICABLE", "ok", None, None, {}, {}, (), (), reasons)
    out = in_force_warnings([res("a.x", "law_not_in_force:2017-01-01", "earlier_law_governs"),
                             res("b.y", "law_not_in_force:2015-07-01"), res("c.z", "not_applicable")], date(2012, 5, 1))
    assert len(out) == 1 and "2 rule" in out[0] and "trước ngày luật có hiệu lực" in out[0]
    assert "a.x" in out[0] and "b.y" not in out[0]
    assert in_force_warnings([res("c.z", "not_applicable")], date(2012, 5, 1)) == []


def test_old_loan_contract_flow_keeps_period_cap():
    report = _run("2012-05-01")
    cap = next(r for r in report.results if r.concept_id == "loan.interest_cap")
    assert (cap.status, cap.law_values["max_interest"]["value"]) == ("FAIL", 13.5)


def test_no_sign_date_does_not_block():
    report = _run(None)
    assert not any(x.startswith("law_not_in_force") for r in report.results for x in r.reasons)
    assert not any("trước ngày luật có hiệu lực" in w for w in report.warnings)
