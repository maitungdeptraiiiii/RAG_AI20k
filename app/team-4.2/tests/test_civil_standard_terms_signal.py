"""Gói dân sự chung: dấu hiệu "hợp đồng theo mẫu" / "điều kiện giao dịch chung" do LLM trích từ hợp đồng; chỉ hỏi người dùng
khi hợp đồng không có dấu hiệu nào (trước đây luôn hỏi vì hai dữ kiện chỉ nhập tay)."""
from datetime import date

import pytest

from rag.bridge.facts_map import contract_facts
from rag.rules.evaluator import make_evaluator
from rag.rules.loader import load_packs
from rag.rules.questions import next_questions
from rag.rules.semantics import Fact

CONCEPT = "civil.standard_terms_exemption"
DAY = date(2025, 12, 2)


@pytest.fixture(scope="module")
def catalog():
    return load_packs(["civil_lease"])


def candidate(text):
    return {"value": text, "unit": "p0.d1", "quote": text}


def test_pack_asks_llm_for_both_signals_and_derives_the_facts(catalog):
    keys = {f["key"] for f in catalog.context.extract_fields}
    assert {"adhesion_signal", "general_conditions_signal"} <= keys
    assert {"is_adhesion_contract", "uses_general_conditions"} <= set(catalog.context.document_specs)


def test_signal_found_in_contract_sets_the_fact_true(catalog):
    facts = contract_facts({"candidates": {"adhesion_signal": [candidate("Đây là hợp đồng mẫu do Bên A soạn sẵn.")]}},
                           sign_date=DAY, ctx=catalog.context)
    assert facts["is_adhesion_contract"].value is True
    assert "uses_general_conditions" not in facts          # không có dấu hiệu: để trống, không suy ra "không"


def test_no_signal_leaves_both_facts_unset(catalog):
    facts = contract_facts({"candidates": {}}, sign_date=DAY, ctx=catalog.context)
    assert "is_adhesion_contract" not in facts and "uses_general_conditions" not in facts


def questions_for(catalog, facts):
    session = make_evaluator(["civil_lease"]).session(
        day=DAY, facts={"one_sided_standard_term": Fact(True, None, "contract"), **facts}, present={CONCEPT}, evidence={})
    return {q.fact for q in next_questions(catalog, session)}


def test_asks_both_when_contract_has_no_signal(catalog):
    assert questions_for(catalog, {}) == {"is_adhesion_contract", "uses_general_conditions"}


def test_does_not_ask_what_the_contract_already_says(catalog):
    found = contract_facts({"candidates": {"adhesion_signal": [candidate("hợp đồng mẫu")]}},
                           sign_date=DAY, ctx=catalog.context)
    asked = questions_for(catalog, {k: v for k, v in found.items() if k == "is_adhesion_contract"})
    assert "is_adhesion_contract" not in asked and "uses_general_conditions" in asked
