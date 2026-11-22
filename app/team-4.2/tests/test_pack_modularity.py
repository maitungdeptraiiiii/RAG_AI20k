"""Cắm gói mới như module (checklist D38–D41): những gì quanh engine phải đọc từ gói, không viết cứng lao động."""
import pytest

from rag.bridge.catalog import load_catalog
from rag.bridge.facts_map import normalize_slot
from rag.rules.loader import load_pack, load_packs
from rag.rules.model import CatalogError, Slot
from rules_synth import concept, rule, write_pack

LOAN = load_packs(["civil_loan"])
RATE = Slot("interest_rate", "percent", "percent_per_year")


# ── D38: đơn vị của slot theo gói ──
@pytest.mark.parametrize("raw,expected", [
    ("30%/năm", (30.0, "percent_per_year")), ("30% / năm", (30.0, "percent_per_year")),
    ("18% một năm", (18.0, "percent_per_year")), ("2%/tháng", (2.0, "percent_per_month")),
    ("1,5% mỗi tháng", (1.5, "percent_per_month")),
])
def test_percent_slot_reads_period_declared_by_pack(raw, expected):
    f = normalize_slot(RATE, raw, LOAN.context)
    assert (f.value, f.unit) == expected


def test_percent_without_period_is_not_guessed_for_a_per_period_slot():
    """'30%' không ghi kỳ: không được đoán là theo năm (lệch 12 lần nếu là theo tháng) -> không chuẩn hóa được."""
    assert normalize_slot(RATE, "30%", LOAN.context) is None


def test_loan_rule_sees_violation_end_to_end_from_slot_text():
    from datetime import date
    from rag.rules.evaluator import evaluator_for
    from rag.rules.semantics import Fact
    f = normalize_slot(RATE, "30%/năm", LOAN.context)
    s = evaluator_for(LOAN, "network").session(day=date(2025, 3, 1), facts={"interest_rate": f,
                                                                             "special_law_applies": Fact(False)},
                                               present={"loan.interest_cap"}, evidence={})
    r = next(x for x in s.results() if (x.concept_id, x.rule_id) == ("loan.interest_cap", "r1"))
    assert (r.status, r.finding) == ("FAIL", "violation")
    monthly = normalize_slot(RATE, "2%/tháng", LOAN.context)                   # 24%/năm
    s.update({"interest_rate": monthly})
    assert next(x for x in s.results() if (x.concept_id, x.rule_id) == ("loan.interest_cap", "r1")).status == "FAIL"


def test_labor_percent_slots_unchanged():
    labor = load_catalog()
    slot = labor.concepts["wage.overtime_pay"].slots["ot_weekday_pct"]
    for ctx in (None, labor.context):
        f = normalize_slot(slot, "150%", ctx)
        assert (f.value, f.unit) == (150.0, "percent")


def test_loader_validates_unit_forms(tmp_path):
    write_pack(tmp_path, {"units": ["percent_per_year"], "unit_forms": {"percent_per_year": ["/năm"], "la": ["/x"]}},
               pack_id="uf")
    with pytest.raises(CatalogError) as e:
        load_pack("uf", root=tmp_path)
    assert any("'la'" in p for p in e.value.problems)
    write_pack(tmp_path, {"units": ["percent_per_year"], "unit_forms": {"percent_per_year": "/năm"}}, pack_id="uf2")
    with pytest.raises(CatalogError):
        load_pack("uf2", root=tmp_path)


# ── D39: dữ kiện cấp hợp đồng theo gói ──
LEASE_LIKE = {
    "units": ["vnd", "month", "day", "hour"],
    "conversions": {"hour": {"base": "hour", "factor": 1}, "day": {"base": "hour", "factor": 24},
                    "month": {"base": "hour", "factor": 720}},
    "document_facts": {
        "monthly_rent_vnd": {"unit": "vnd", "from": "rent", "parse": "money"},
        "lease_term": {"unit": "month", "from": "lease_term", "parse": "duration_to_unit"},
        "rent_kind": {"unit": None, "from": "rent_kind", "parse": "contains",
                      "contains": [["cố định", "fixed"], ["điều chỉnh", "adjustable"]]},
        "sign_date": None,
    },
    "extract_fields": [{"key": "rent", "label": "Giá thuê", "kind": "text", "hint": "số tiền thuê mỗi kỳ"},
                       {"key": "lease_term", "label": "Thời hạn thuê", "kind": "text", "hint": "số tháng / năm"},
                       {"key": "rent_kind", "label": "Giá thuê cố định hay điều chỉnh", "kind": "text"}],
}


def _lease_catalog(tmp_path):
    write_pack(tmp_path, LEASE_LIKE, [concept("lease.x", [rule("r1")])], pack_id="leasey")
    return load_packs(["leasey"], root=tmp_path)


def test_document_facts_filled_from_pack_declaration(tmp_path):
    from rag.bridge.facts_map import contract_facts
    cat = _lease_catalog(tmp_path)
    facts = {"candidates": {
        "rent": [{"value": "5.000.000 đồng/tháng", "unit": "p0.d2", "quote": "Giá thuê 5.000.000 đồng/tháng"}],
        "lease_term": [{"value": "2 năm", "unit": "p0.d3", "quote": "Thời hạn thuê 2 năm"}],
        "rent_kind": [{"value": "giá thuê cố định trong suốt thời hạn", "unit": "p0.d2", "quote": "q"}],
        "salary": [{"value": "15.000.000 đồng", "unit": "p0.d1", "quote": "q"}]}}       # trường của gói khác: bỏ
    out = contract_facts(facts, sign_date=None, ctx=cat.context)
    assert (out["monthly_rent_vnd"].value, out["monthly_rent_vnd"].unit) == (5000000, "vnd")
    assert (out["lease_term"].value, out["lease_term"].unit) == (24, "month")
    assert out["rent_kind"].value == "fixed" and "base_salary_vnd" not in out
    assert out["monthly_rent_vnd"].uid == "p0.d2" and out["monthly_rent_vnd"].quote.startswith("Giá thuê")


def test_fact_ops_follow_pack_declaration(tmp_path):
    from datetime import datetime
    from rag.bridge.facts_map import fact_ops
    cat = _lease_catalog(tmp_path)
    facts = {"candidates": {"rent": [{"value": "5.000.000 đồng", "unit": "p0.d2", "quote": "Giá thuê 5.000.000 đồng"}]}}
    ops = fact_ops(facts, "c1", at=datetime(2026, 1, 1), ctx=cat.context)
    assert [(o.content["name"], o.content["value"], o.content["unit"]) for o in ops] == [("monthly_rent_vnd", 5000000, "vnd")]


def test_labor_document_facts_declared_in_pack_and_unchanged():
    from rag.bridge.facts_map import contract_facts
    labor = load_catalog().context
    assert set(labor.document_specs) == {"contract_kind", "term_months", "base_salary_vnd", "has_probation",
                                         "probation_length", "probation_pay_pct", "job_level"}
    facts = {"candidates": {
        "labor_kind": [{"value": "Không xác định thời hạn", "unit": "p0.d1", "quote": "q"}],
        "term": [{"value": "12 tháng", "unit": "p0.d1", "quote": "q"}],
        "salary": [{"value": "điều chỉnh từ 15.000.000 đồng lên 17.000.000 đồng", "unit": "p1.d1",
                    "quote": "điều chỉnh từ 15.000.000 đồng lên 17.000.000 đồng"}],
        "probation_period": [{"value": "02 tháng", "unit": "p0.d2", "quote": "q"}],
        "probation_salary": [{"value": "85%", "unit": "p0.d2", "quote": "q"}],
        "job_level": [{"value": "Công việc khác", "unit": "p0.d1", "quote": "q"}]}}
    for ctx in (None, labor):
        out = contract_facts(facts, sign_date=None, ctx=ctx)
        got = {k: (v.value, v.unit) for k, v in out.items()}
        assert got == {"contract_kind": ("khong_xac_dinh_thoi_han", None), "term_months": (12, "month"),
                       "base_salary_vnd": (17000000, "vnd"), "has_probation": (True, None),
                       "probation_length": (2, "month"), "probation_pay_pct": (85.0, "percent"),
                       "job_level": ("cong_viec_khac", None)}


def test_extract_facts_asks_for_fields_of_the_selected_packs(tmp_path):
    import json
    from rag.contracts.facts import FACTS_PROMPT, extract_facts
    from test_bridge_check import contract
    cat = _lease_catalog(tmp_path)
    seen = []

    class LLM:
        def complete(self, system, user):
            if system.startswith(FACTS_PROMPT[:40]):
                seen.append([f["key"] for f in json.loads(user)["fields_wanted"]])
            return json.dumps({"type": "chưa rõ", "parties": [], "fields": {}})
    extract_facts(LLM(), contract(), extra_fields=cat.context.extract_fields)
    assert seen and all({"rent", "lease_term", "rent_kind"} <= set(keys) for keys in seen)


def test_loader_validates_document_fact_declarations(tmp_path):
    bad = {"document_facts": {"a": {"unit": "vnd", "from": "x", "parse": "doan_mo"},
                              "b": {"unit": None, "from": "y", "parse": "enum"},
                              "c": {"unit": None, "parse": "money"}},
           "units": ["vnd"], "extract_fields": [{"key": "x"}]}
    write_pack(tmp_path, bad, pack_id="badd")
    with pytest.raises(CatalogError) as e:
        load_pack("badd", root=tmp_path)
    text = "\n".join(e.value.problems)
    assert "doan_mo" in text and "'b'" in text and "'c'" in text and "extract_fields" in text


# ── Prompt theo gói: không viết cứng "hợp đồng lao động" ──
def test_document_label_comes_from_packs():
    assert load_catalog().context.document_label == "hợp đồng lao động"
    assert LOAN.context.document_label == "hợp đồng vay tài sản"              # gói lá (civil_loan), không phải gói cha
    assert load_packs(["civil_general"]).context.document_label == "hợp đồng dân sự"
    assert load_packs(["labor", "civil_loan"]).context.document_label == "hợp đồng"   # nhiều miền: nhãn chung


def test_prompts_render_label_and_labor_text_is_unchanged():
    from rag.bridge.recheck import RECHECK_PROMPT, recheck_prompt
    from rag.bridge.tagger import TAG_PROMPT, tag_prompt
    from rag.contracts.graph.agent import AGENT_PROMPT, agent_prompt
    labor = load_catalog().context
    for const, render in ((TAG_PROMPT, tag_prompt), (RECHECK_PROMPT, recheck_prompt), (AGENT_PROMPT, agent_prompt)):
        assert render(labor) == const
        loan = render(LOAN.context)
        assert "lao động" not in loan and "hợp đồng vay tài sản" in loan


def test_check_contract_sends_no_labor_wording_for_a_loan_contract():
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("exp_loan_case", pathlib.Path(__file__).with_name("pack_cases.py"))
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    llm, report = cases.run_loan_contract()
    assert llm.systems and not any("lao động" in s for s in llm.systems)
    r = next(x for x in report.results if (x.concept_id, x.rule_id) == ("loan.interest_cap", "r1"))
    assert (r.status, r.finding) == ("FAIL", "violation")
    assert r.facts_used["interest_rate"] == {"value": 30.0, "unit": "percent_per_year"}


# ── D40 (logic): vai trò các bên và bên giữ quyền theo gói ──
def _cases():
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("pack_cases_mod", pathlib.Path(__file__).with_name("pack_cases.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_party_roles_come_from_pack_roles():
    from datetime import datetime
    from rag.bridge.facts_map import party_ops
    at = datetime(2026, 1, 1)
    loan = {"parties": [{"name": "A", "role": "Bên cho vay"}, {"name": "B", "role": "Bên vay"}]}
    ops = party_ops(loan, "c1", at=at, roles=LOAN.roles)
    assert sorted((o.content["role"], o.content["label"]) for o in ops) == [("BEN_CHO_VAY", "Bên cho vay"),
                                                                           ("BEN_VAY", "Bên vay")]
    assert party_ops(loan, "c1", at=at) == []                                   # gói labor không có vai trò này
    labor = {"parties": [{"role": "Người sử dụng lao động"}, {"role": "Người lao động"}, {"role": "Công ty TNHH A"},
                         {"role": "Người làm chứng"}]}
    for roles in (None, load_catalog().roles):
        got = sorted({o.content["role"] for o in party_ops(labor, "c1", at=at, roles=roles)})
        assert got == ["NLD", "NSDLD"]


def test_loan_contract_graph_links_holder_to_pack_party():
    from rag.bridge.check import contract_view
    cases = _cases()
    _llm, _report, c = cases.run_loan_contract_with_contract()
    view, _, _, _ = contract_view(c, None, cases.AT)
    parties = {p["role"] for p in view.find("Party")}
    assert parties == {"BEN_CHO_VAY", "BEN_VAY"}
    ci = next(n for n in view.find("ConceptInstance") if n["concept_id"] == "loan.interest_cap")
    holders = [h["node"]["role"] for h in view.neighbors(ci["node_id"], rel_types=["HOLDER"], direction="out")]
    assert holders == ["BEN_VAY"]                    # trần lãi bảo vệ bên vay (sửa 23/11: bản đầu gán nhầm bên cho vay)


# ── D32: chọn gói theo loại hợp đồng ──
def test_packs_for_kind_uses_document_kinds_of_packs():
    from rag.rules.loader import packs_for_kind
    assert packs_for_kind("labor_contract") == ["labor"]
    assert packs_for_kind("loan_contract") == ["civil_loan"]
    assert packs_for_kind("civil_contract") == ["civil_general"]
    assert packs_for_kind("unknown") == [] and packs_for_kind("khong_co") == []


def test_unknown_kind_runs_no_pack_and_calls_no_llm():
    from rag.bridge.check import check_contract
    cases = _cases()

    class NoLLM:
        def complete(self, system, user):
            raise AssertionError("không được gọi LLM khi không có gói")
    report = check_contract(NoLLM(), cases.loan_contract(), at=cases.AT, document_kind="unknown")
    assert report.results == [] and report.catalog_version == "none"
    assert any("unknown" in w for w in report.warnings)


def test_kind_selects_the_pack_and_conflicts_with_explicit_packs():
    from rag.bridge.check import check_contract
    cases = _cases()
    llm = cases.ScriptedLoanLLM()
    report = check_contract(llm, cases.loan_contract(), at=cases.AT, document_kind="loan_contract",
                            user_facts={"special_law_applies": False})
    concepts = {r.concept_id for r in report.results}
    assert {"loan.interest_cap", "civil.unilateral_termination"} <= concepts
    assert all(c.startswith(("loan.", "civil.")) for c in concepts)          # không có khái niệm gói labor
    with pytest.raises(ValueError):
        check_contract(llm, cases.loan_contract(), at=cases.AT, document_kind="loan_contract", packs=["labor"])
