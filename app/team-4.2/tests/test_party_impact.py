"""D33 (spec bản 3 §5.2, G10): từ vựng kết quả trung tính. YAML mới ghi `outcome.party_impact`; bộ nạp vẫn nhận
`employee_impact` cũ (đổi thành `party_impact`); `RuleResult.outcome` mang nguyên outcome của rule (dict) khi finding
được báo, `RuleResult.party_impact` đọc từ đó; `employee_impact` giữ làm tên tương thích (cùng giá trị)."""
import copy

import pytest

from rag.rules.exceptions import Override, finalize
from rag.rules.loader import PACKS_ROOT, load_packs
from rag.rules.model import CatalogError
from test_rules_loader import BASE, _load
from test_rules_semantics import F, ev, mk_rule

NEW = {"legality": "illegal", "party_impact": "unfavorable"}
CHECK = {"fact": "base_salary_vnd", "op": "gte", "value": 5000000, "unit": "vnd"}


def _with_outcome(outcome):
    d = copy.deepcopy(BASE)
    d["concepts"][0]["rules"][0]["outcome"] = outcome
    return d


def test_loader_reads_party_impact(tmp_path):
    cat = _load(tmp_path, _with_outcome(dict(NEW)))
    assert cat.concepts["x.a"].rules[0].outcome == NEW


def test_loader_maps_old_employee_impact_to_party_impact(tmp_path):
    cat = _load(tmp_path, _with_outcome({"legality": "illegal", "employee_impact": "neutral"}))
    assert cat.concepts["x.a"].rules[0].outcome == {"legality": "illegal", "party_impact": "neutral"}


def test_loader_rejects_both_names_disagreeing(tmp_path):
    with pytest.raises(CatalogError) as e:
        _load(tmp_path, _with_outcome({"legality": "illegal", "party_impact": "neutral", "employee_impact": "unfavorable"}))
    assert any("party_impact" in p and "employee_impact" in p for p in e.value.problems)


def test_violation_carries_outcome_and_party_impact():
    r = ev(mk_rule(on_silence="hidden_right", check=CHECK, outcome=dict(NEW)), {"base_salary_vnd": F(4000000, "vnd")})
    assert (r.status, r.finding) == ("FAIL", "violation")
    assert (r.outcome, r.party_impact, r.legality, r.employee_impact) == (NEW, "unfavorable", "illegal", "unfavorable")


def test_unreported_finding_has_empty_outcome():
    r = ev(mk_rule(on_silence="hidden_right", check=CHECK, outcome=dict(NEW)), {"base_salary_vnd": F(6000000, "vnd")})
    assert (r.status, r.finding) == ("PASS", "ok")
    assert (r.outcome, r.party_impact, r.legality, r.employee_impact) == ({}, None, None, None)


@pytest.mark.parametrize("applies, status", [("T", "NOT_APPLICABLE"), ("U", "UNKNOWN")])
def test_exception_clears_outcome(applies, status):
    base = ev(mk_rule(on_silence="hidden_right", check=CHECK, outcome=dict(NEW)), {"base_salary_vnd": F(4000000, "vnd")})
    out = finalize(base, [Override("c/e", applies, ("m",))])
    assert out.status == status and (out.outcome, out.party_impact, out.employee_impact) == ({}, None, None)


def test_real_packs_use_party_impact_only():
    for d in ("labor", "civil_general", "civil_loan", "civil_lease"):
        assert "employee_impact" not in (PACKS_ROOT / d / "concepts.yaml").read_text(encoding="utf-8"), d
    cat = load_packs(["labor", "civil_loan", "civil_lease"])
    outcomes = [r.outcome for c in cat.concepts.values() for r in c.rules if r.outcome]
    assert outcomes and all("party_impact" in o and "employee_impact" not in o for o in outcomes)
