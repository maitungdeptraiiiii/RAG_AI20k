"""Hợp đồng mẫu của các gói xây theo luật (23/11): người tiêu dùng, thương mại. Cùng cách kiểm như
tests/test_rete_lease_fixtures.py nhưng chung cho mọi gói trong SUITES: gói chọn theo loại hợp đồng, rule khớp bản liệt kê,
parser đọc được hợp đồng, câu trích có thật, engine khớp nhãn đúng (gold, viết trước khi chạy engine), không báo FAIL ngoài
gold, câu căn cứ của gold có nguyên văn trong kho luật.

Dữ kiện lấy từ facts.yaml qua đúng các bộ đọc của luồng thật (contract_facts, normalize_slot, user_fact_set)."""
from datetime import date
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from rag.bridge.check import user_fact_set
from rag.bridge.facts_map import contract_facts, normalize_slot
from rag.contracts.amendments import find_amendments
from rag.contracts.doc import PageText
from rag.contracts.structure import parse_contract
from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_packs, packs_for_kind

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "rete"
# thư mục mẫu -> (gói, loại văn bản, bản liệt kê)
SUITES = {"consumer": ("consumer", "consumer_contract", "consumer.yaml"),
          "commercial": ("commercial", "commercial_sale_contract", "commercial.yaml")}


def _norm(s: str) -> str:
    return " ".join(s.split())


@lru_cache(maxsize=None)
def _data(suite: str):
    here = FIXTURES / suite
    facts = yaml.safe_load((here / "facts.yaml").read_text(encoding="utf-8"))
    gold = yaml.safe_load((here / "gold.yaml").read_text(encoding="utf-8"))
    return here, facts, gold, load_packs([SUITES[suite][0]])


def _docs():
    return [(s, d) for s in SUITES for d in sorted(_data(s)[1])]


def _gold():
    return [(s, e) for s in SUITES for e in _data(s)[2]["expected"]]


@pytest.mark.parametrize("suite", sorted(SUITES))
def test_pack_is_chosen_by_its_document_kind(suite):
    pack, kind, _ = SUITES[suite]
    assert packs_for_kind(kind) == [pack]
    assert all(pack not in packs_for_kind(k) for k in ("labor_contract", "loan_contract", "lease_contract"))


@pytest.mark.parametrize("suite", sorted(SUITES))
def test_every_inventory_rule_reference_exists_in_the_pack(suite):
    pack, _, inv = SUITES[suite]
    cat = _data(suite)[3]
    refs = [str(e["yaml_rule"]).split()[0] for e in yaml.safe_load((ROOT / "docs" / "rule_inventory" / inv).read_text(encoding="utf-8"))
            if str(e["yaml_rule"]).startswith(pack + ".")]
    assert refs
    for ref in refs:
        cid, rid = ref.split("/")
        assert rid in {r.id for r in cat.concepts[cid].rules}, ref


@pytest.mark.parametrize("suite,doc", _docs())
def test_parser_reads_articles_and_no_spurious_amendments(suite, doc):
    parsed = parse_contract([PageText(1, (_data(suite)[0] / f"{doc}.txt").read_text(encoding="utf-8"))])
    assert parsed.report.counts["article"] >= 4, parsed.report.counts
    assert find_amendments(parsed) == []


@pytest.mark.parametrize("suite,doc", _docs())
def test_every_quote_is_in_the_contract(suite, doc):
    here, facts, _, _ = _data(suite)
    text, spec = _norm((here / f"{doc}.txt").read_text(encoding="utf-8")), facts[doc]
    quotes = [q for _, q in (spec.get("document") or {}).values()]
    quotes += [q for slots in spec["slots"].values() for _, q in (slots or {}).values()]
    quotes += list((spec.get("present_quotes") or {}).values())
    for q in quotes:
        assert _norm(q) in text, (doc, q)


def _session(suite: str, doc: str, kind: str):
    _, facts_all, _, cat = _data(suite)
    spec = facts_all[doc]
    day = spec["sign_date"] if isinstance(spec["sign_date"], date) else date.fromisoformat(str(spec["sign_date"]))
    candidates = {k: [{"value": v, "unit": "p0.d1", "quote": q}] for k, (v, q) in (spec.get("document") or {}).items()}
    facts = dict(contract_facts({"candidates": candidates}, sign_date=day, ctx=cat.context))
    for cid, slots in spec["slots"].items():
        for name, (raw, _q) in (slots or {}).items():
            f = normalize_slot(cat.concepts[cid].slots[name], raw, cat.context)
            assert f is not None, (doc, cid, name, raw)
            facts[name] = f
    facts.update(user_fact_set(spec.get("user_facts") or {}, cat.context))
    return evaluator_for(cat, kind).session(day=day, facts=facts, present=set(spec["slots"]), evidence={})


@pytest.mark.parametrize("kind", ["reference", "network"])
@pytest.mark.parametrize("suite,item", _gold(), ids=lambda x: x if isinstance(x, str) else f"{x['object']}:{x['rule']}")
def test_engine_matches_gold(suite, item, kind):
    results = {f"{r.concept_id}/{r.rule_id}": r for r in _session(suite, item["object"], kind).results()}
    got, want = results[item["rule"]], item["periods"][0]
    assert got.status == want["status"], (item["object"], item["rule"], got.status, got.reasons, got.missing_facts)
    if "finding" in want:
        assert got.finding == want["finding"]


@pytest.mark.parametrize("suite,doc", _docs())
def test_no_unexpected_violations_outside_gold(suite, doc):
    """Mọi FAIL engine báo trên hợp đồng mẫu đều có trong gold (không báo sai vi phạm)."""
    labeled = {(e["object"], e["rule"]) for e in _data(suite)[2]["expected"]}
    for r in _session(suite, doc, "network").results():
        if r.status == "FAIL":
            assert (doc, f"{r.concept_id}/{r.rule_id}") in labeled, (doc, r.concept_id, r.rule_id, r.reasons)


@pytest.mark.parametrize("suite,item", _gold(), ids=lambda x: x if isinstance(x, str) else f"{x['object']}:{x['rule']}")
def test_gold_basis_quotes_are_verbatim_in_the_corpus(suite, item):
    from legal_corpus import law_text
    text = law_text(item["basis"]["pid"])
    if text is None:
        pytest.skip("kho luật cục bộ không có " + item["basis"]["pid"])
    assert _norm(item["basis"]["quote"]) in _norm(text), item


def test_consumer_pack_overlays_other_packs_without_clashes():
    """Gói người tiêu dùng chồng lên gói khác (packs=[...]) khi một bên là người tiêu dùng."""
    both = load_packs(["civil_lease", "consumer"])
    assert {"lease.landlord_termination", "consumer.unilateral_change", "civil.late_payment_interest_cap"} <= set(both.concepts)
    assert {"BEN_THUE", "NGUOI_TIEU_DUNG"} <= set(both.roles)
