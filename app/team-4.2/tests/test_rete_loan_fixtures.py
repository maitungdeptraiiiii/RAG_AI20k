"""Hợp đồng vay mẫu (tests/fixtures/rete/loan): parser đọc được, câu trích có thật, engine khớp nhãn đúng (gold).

Dữ kiện lấy từ facts.yaml qua đúng các bộ đọc của luồng thật (contract_facts, normalize_slot, user_fact_set) nên
lỗi đọc đơn vị / dữ kiện cấp hợp đồng cũng làm test hỏng."""
from datetime import date
from pathlib import Path

import pytest
import yaml

from rag.bridge.check import user_fact_set
from rag.bridge.facts_map import contract_facts, normalize_slot
from rag.contracts.amendments import find_amendments
from rag.contracts.doc import PageText
from rag.contracts.structure import parse_contract
from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_packs

HERE = Path(__file__).parent / "fixtures" / "rete" / "loan"
FACTS = yaml.safe_load((HERE / "facts.yaml").read_text(encoding="utf-8"))
GOLD = yaml.safe_load((HERE / "gold.yaml").read_text(encoding="utf-8"))
LOAN = load_packs(["civil_loan"])


def _norm(s: str) -> str:
    return " ".join(s.split())


def _text(doc: str) -> str:
    return (HERE / f"{doc}.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("doc", sorted(FACTS))
def test_parser_reads_articles_and_no_spurious_amendments(doc):
    parsed = parse_contract([PageText(1, _text(doc))])
    assert parsed.report.counts["article"] >= 4, parsed.report.counts
    assert find_amendments(parsed) == []


@pytest.mark.parametrize("doc", sorted(FACTS))
def test_every_quote_is_in_the_contract(doc):
    text, spec = _norm(_text(doc)), FACTS[doc]
    quotes = [q for _, q in spec["document"].values()]
    quotes += [q for slots in spec["slots"].values() for _, q in slots.values()]
    for q in quotes:
        assert _norm(q) in text, (doc, q)


def _session(doc: str, kind: str):
    spec = FACTS[doc]
    day = spec["sign_date"] if isinstance(spec["sign_date"], date) else date.fromisoformat(str(spec["sign_date"]))
    candidates = {k: [{"value": v, "unit": "p0.d1", "quote": q}] for k, (v, q) in spec["document"].items()}
    facts = dict(contract_facts({"candidates": candidates}, sign_date=day, ctx=LOAN.context))
    for cid, slots in spec["slots"].items():
        for name, (raw, _q) in slots.items():
            f = normalize_slot(LOAN.concepts[cid].slots[name], raw, LOAN.context)
            assert f is not None, (doc, cid, name, raw)
            facts[name] = f
    facts.update(user_fact_set(spec.get("user_facts") or {}, LOAN.context))
    return evaluator_for(LOAN, kind).session(day=day, facts=facts, present=set(spec["slots"]), evidence={})


@pytest.mark.parametrize("kind", ["reference", "network"])
@pytest.mark.parametrize("item", GOLD["expected"], ids=lambda e: f"{e['object']}:{e['rule']}")
def test_engine_matches_gold(item, kind):
    results = {f"{r.concept_id}/{r.rule_id}": r for r in _session(item["object"], kind).results()}
    got = results[item["rule"]]
    want = item["periods"][0]
    assert got.status == want["status"], (item["object"], item["rule"], got.status, got.reasons, got.facts_used)
    if "finding" in want:
        assert got.finding == want["finding"]


def test_gold_basis_quotes_are_verbatim_in_the_corpus():
    from legal_corpus import law_text
    for item in GOLD["expected"]:
        text = law_text(item["basis"]["pid"])
        if text is None:
            pytest.skip("kho luật cục bộ không có " + item["basis"]["pid"])
        assert _norm(item["basis"]["quote"]) in _norm(text), item
