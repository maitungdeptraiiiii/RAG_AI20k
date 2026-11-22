"""Gói dân sự: civil_general + civil_loan (BLDS 91/2015/QH13 Đ401, 428, 463–471), `kind`, `packs=` ở check_contract."""
from datetime import date
from pathlib import Path

import pytest

from rag.rules.evaluator import evaluator_for, make_evaluator
from rag.rules.loader import load_packs
from rag.rules.model import CatalogError
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

DAY = date(2025, 3, 1)
LAW = sorted((Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "legal" / "raw"
              / "bo-luat_91_2015_QH13").glob("*.txt"))
LOAN = load_packs(["civil_loan"])


def results(facts, present=("loan.interest_cap",), kinds=("reference", "network"), cat=LOAN):
    out = {}
    for kind in kinds:
        s = evaluator_for(cat, kind).session(day=DAY, facts=facts, present=set(present), evidence={})
        out[kind] = {f"{r.concept_id}/{r.rule_id}": r for r in s.results()}
    assert out["reference"] == out["network"]
    return out["reference"]


def test_civil_loan_extends_civil_general_and_loads_both_concept_sets():
    assert {"loan.interest_cap", "civil.unilateral_termination"} <= set(LOAN.concepts)
    assert LOAN.context.units.convert(2, "percent_per_month", "percent_per_year") == 24
    assert LOAN.context.units.convert(1, "year", "month") == 12
    assert "special_law_applies" in load_packs(["civil_general"]).context.questions
    assert load_packs(["civil_general"]).concepts.keys() == {"civil.unilateral_termination"}


def test_civil_and_labor_load_together_without_clashes():
    both = load_packs(["labor", "civil_loan"])
    civil = load_packs(["civil_loan"]).concepts
    assert len(both.concepts) == 40 + len(civil) and both.context.units.convert(1, "month", "day") == 30
    assert both.context.units.convert(24, "percent_per_month", "percent_per_year") == 288


@pytest.mark.parametrize("rate,status", [(Fact(15, "percent_per_year"), "PASS"), (Fact(20, "percent_per_year"), "PASS"),
                                         (Fact(24, "percent_per_year"), "FAIL"), (Fact(1.5, "percent_per_month"), "PASS"),
                                         (Fact(2, "percent_per_month"), "FAIL")])
def test_interest_cap_20_percent_per_year_with_unit_conversion(rate, status):
    r = results({"interest_rate": rate, "special_law_applies": Fact(False)})["loan.interest_cap/r1"]
    assert (r.status, r.law_values["max_interest"]["value"]) == (status, 20)
    if status == "FAIL":
        assert (r.finding, r.legality) == ("violation", "illegal")


def test_interest_cap_unknown_without_rate_or_unit_and_never_violation():
    assert results({"special_law_applies": Fact(False)})["loan.interest_cap/r1"].status == "UNKNOWN"
    no_unit = results({"interest_rate": Fact(30), "special_law_applies": Fact(False)})["loan.interest_cap/r1"]
    assert no_unit.status == "UNKNOWN"                                        # không đơn vị: không so được, không thành vi phạm


def test_specialized_law_exception_overrides_cap_and_unknown_downgrades():
    high = {"interest_rate": Fact(30, "percent_per_year")}
    out = results({**high, "special_law_applies": Fact(True)})
    assert out["loan.interest_cap/r1"].status == "NOT_APPLICABLE"
    assert out["loan.interest_cap/r1"].reasons == ("overridden_by:loan.interest_cap/r1_special_law",)
    assert out["loan.interest_cap/r1_special_law"].status == "PASS"
    unknown = results(high)["loan.interest_cap/r1"]                           # chưa biết có luật chuyên ngành không
    assert (unknown.status, unknown.finding) == ("UNKNOWN", "needs_facts") and unknown.missing_facts == ("special_law_applies",)
    assert results({**high, "special_law_applies": Fact(False)})["loan.interest_cap/r1"].status == "FAIL"


def test_unilateral_termination_requires_notice_art_428_2():
    ok = results({"terminates_without_notice": Fact(False)}, ("civil.unilateral_termination",))
    assert ok["civil.unilateral_termination/r1"].status == "PASS"
    bad = results({"terminates_without_notice": Fact(True)}, ("civil.unilateral_termination",))
    assert bad["civil.unilateral_termination/r1"].status == "FAIL"


def test_make_evaluator_accepts_packs_and_unknown_pack_is_error():
    ev = make_evaluator(["civil_loan"], "network")
    s = ev.session(day=DAY, facts={"interest_rate": Fact(30, "percent_per_year"), "special_law_applies": Fact(False)},
                   present={"loan.interest_cap"}, evidence={})
    assert any(r.rule_id == "r1" and r.status == "FAIL" for r in s.results())
    with pytest.raises(CatalogError):
        make_evaluator(["khong_co_goi"])


@pytest.mark.skipif(not LAW, reason="không có kho luật cục bộ")
def test_civil_rules_pinned_by_law_text():
    text = LAW[0].read_text(encoding="utf-8")
    for phrase in ("không được vượt quá 20%/năm của khoản tiền vay", "trừ trường hợp luật khác có liên quan quy định khác",
                   "phải thông báo ngay cho bên kia biết về việc chấm dứt hợp đồng"):
        assert phrase in text, phrase
    rules = {f"{c.id}/{r.id}": r for c in LOAN.concepts.values() for r in c.rules}
    periods = rules["loan.interest_cap/r1"].law["max_interest"]["periods"]
    assert [(p["valid_from"], p["value"]) for p in periods] == [("2010-12-01", 13.5), ("2017-01-01", 20)]
    from legal_corpus import law_text
    nq = law_text("nghi-quyet:01/2019/NQ-HĐTP")
    if nq is not None:
        assert "tương ứng với mức 150% lãi suất cơ bản là 13,5%/năm" in nq
        assert "không được vượt quá 150% mức lãi suất quy định tại khoản 1 Điều 468" in nq
    old = law_text("bo-luat:33/2005/QH11")
    if old is not None:
        assert "không được vượt quá 150% của lãi suất cơ bản" in old


# ── `kind` của concept (spec §5.5): concept phải có slot thuộc các loại mà kind yêu cầu (không ép tên slot: tên là khóa dữ kiện) ──
KIND_PACK = {"concept_kinds": {"rate_cap": {"slot_kinds": ["percent"]}}, "units": ["percent"], "conversions": {}}


def _kind_catalog(tmp_path, kind, slots):
    c = concept("c.k", [rule("r1")], slots=slots)
    if kind is not None:
        c["kind"] = kind
    write_pack(tmp_path, KIND_PACK, [c], pack_id="kp")
    return load_packs(["kp"], root=tmp_path)


def test_concept_kind_loaded_and_slots_must_match_kind(tmp_path):
    cat = _kind_catalog(tmp_path, "rate_cap", {"any_name": {"kind": "percent", "unit": "percent"}, "extra": {"kind": "bool", "unit": None}})
    assert cat.concepts["c.k"].kind == "rate_cap"
    assert _kind_catalog(tmp_path, None, {}).concepts["c.k"].kind is None
    for kind, slots, needle in (("la", {}, "'la'"), ("rate_cap", {}, "percent"),
                                ("rate_cap", {"x": {"kind": "bool", "unit": None}}, "percent")):
        with pytest.raises(CatalogError) as e:
            _kind_catalog(tmp_path, kind, slots)
        assert any(needle in p for p in e.value.problems), e.value.problems
    assert LOAN.concepts["loan.interest_cap"].kind == "rate_cap"


# ── `packs=` ở check_contract / ask_contract_graph (spec §7) ──
def test_resolve_catalog_packs_default_and_conflicts():
    from rag.bridge.catalog import load_catalog, resolve_catalog
    assert resolve_catalog(None, None).version == load_catalog().version
    assert resolve_catalog(None, ["labor"]).version == load_catalog().version
    assert "loan.interest_cap" in resolve_catalog(None, ["civil_loan"]).concepts
    explicit = load_catalog()
    assert resolve_catalog(explicit, None) is explicit
    with pytest.raises(ValueError):
        resolve_catalog(explicit, ["civil_loan"])


def test_check_contract_rejects_unknown_pack_before_any_llm_call():
    from rag.bridge.check import check_contract
    from test_bridge_check import AT, ScriptLLM, contract
    llm = ScriptLLM()
    with pytest.raises(CatalogError):
        check_contract(llm, contract(), at=AT, packs=["khong_co_goi"])
    assert llm.calls == []


def test_check_contract_with_packs_labor_matches_default():
    from rag.bridge.check import check_contract
    from test_bridge_check import AT, ScriptLLM, contract
    a = check_contract(ScriptLLM(), contract(), at=AT)
    b = check_contract(ScriptLLM(), contract(), at=AT, packs=["labor"])
    assert [(r.concept_id, r.rule_id, r.status) for r in a.results] == [(r.concept_id, r.rule_id, r.status) for r in b.results]


# ── Gói vay đầy đủ hơn (23/11): BLDS 2005/2015, NQ 01/2019/NQ-HĐTP, Luật Các TCTD 2024 ──
def _loan(facts, present, day=DAY):
    out = {}
    for kind in ("reference", "network"):
        s = evaluator_for(LOAN, kind).session(day=day, facts=facts, present=set(present), evidence={})
        out[kind] = {f"{r.concept_id}/{r.rule_id}": r for r in s.results()}
    assert out["reference"] == out["network"]
    return out["reference"]


@pytest.mark.parametrize("day,rate,status", [
    (date(2016, 6, 1), 12, "PASS"), (date(2016, 6, 1), 15, "FAIL"),           # BLDS 2005: 150% × 9% = 13,5%/năm
    (date(2017, 1, 1), 15, "PASS"), (date(2017, 1, 1), 24, "FAIL"),           # BLDS 2015: 20%/năm
    (date(2009, 6, 1), 30, "UNKNOWN")])                                        # trước 01/12/2010: chưa có giá trị
def test_interest_cap_depends_on_sign_date(day, rate, status):
    r = _loan({"interest_rate": Fact(rate, "percent_per_year"), "special_law_applies": Fact(False)},
              ["loan.interest_cap"], day)["loan.interest_cap/r1"]
    assert r.status == status


@pytest.mark.parametrize("rate,status", [(27, "PASS"), (30, "PASS"), (36, "FAIL")])
def test_overdue_principal_interest_cap_150_percent_of_468(rate, status):
    r = _loan({"overdue_rate": Fact(rate, "percent_per_year")}, ["loan.overdue_interest_cap"])
    assert r["loan.overdue_interest_cap/r1"].status == status


@pytest.mark.parametrize("rate,status", [(10, "PASS"), (24, "FAIL")])
def test_late_payment_interest_cap_art_357(rate, status):
    r = _loan({"late_interest_rate": Fact(rate, "percent_per_year")}, ["loan.late_interest_cap"])
    assert r["loan.late_interest_cap/r1"].status == status


def test_lender_early_recall_prohibited_unless_tied_to_misuse():
    bad = _loan({"lender_may_recall_early_without_consent": Fact(True), "recall_only_on_misuse": Fact(False)},
                ["loan.lender_early_recall"])
    assert bad["loan.lender_early_recall/r1"].status == "FAIL"
    ok = _loan({"lender_may_recall_early_without_consent": Fact(True), "recall_only_on_misuse": Fact(True)},
               ["loan.lender_early_recall"])
    assert ok["loan.lender_early_recall/r1"].status == "NOT_APPLICABLE"
    unknown = _loan({"lender_may_recall_early_without_consent": Fact(True)}, ["loan.lender_early_recall"])
    assert unknown["loan.lender_early_recall/r1"].status == "UNKNOWN"
    assert _loan({}, ["loan.lender_early_recall"])["loan.lender_early_recall/r1"].status == "PASS"   # không có hạn chế


def test_borrower_may_repay_interest_free_term_loan_any_time():
    barred = {"borrower_barred_from_early_repayment": Fact(True)}
    r = _loan({**barred, "has_interest": Fact("khong_lai")}, ["loan.borrower_early_repayment"])
    assert r["loan.borrower_early_repayment/r1"].status == "FAIL"
    r = _loan({**barred, "has_interest": Fact("co_lai")}, ["loan.borrower_early_repayment"])
    assert r["loan.borrower_early_repayment/r1"].status == "NOT_APPLICABLE"
    r = _loan(barred, ["loan.borrower_early_repayment"])
    assert r["loan.borrower_early_repayment/r1"].status == "UNKNOWN"


def test_loan_document_facts_from_extraction():
    from rag.bridge.facts_map import contract_facts
    facts = {"candidates": {
        "value": [{"value": "100.000.000 đồng", "unit": "p0.d1", "quote": "vay 100.000.000 đồng"}],
        "term": [{"value": "12 tháng", "unit": "p0.d2", "quote": "thời hạn vay 12 tháng"}],
        "loan_interest": [{"value": "Khoản vay không có lãi", "unit": "p0.d3", "quote": "không có lãi"}]}}
    out = contract_facts(facts, sign_date=None, ctx=LOAN.context)
    assert (out["loan_amount_vnd"].value, out["loan_amount_vnd"].unit) == (100000000, "vnd")
    assert (out["loan_term_months"].value, out["loan_term_months"].unit) == (12, "month")
    assert out["has_interest"].value == "khong_lai"
    assert "loan_interest" in {f["key"] for f in LOAN.context.extract_fields}


def test_loan_pack_has_at_least_five_concepts_with_rules():
    loan_only = {cid: c for cid, c in LOAN.concepts.items() if cid.startswith("loan.")}
    assert len(loan_only) >= 5 and all(c.rules for c in loan_only.values())
