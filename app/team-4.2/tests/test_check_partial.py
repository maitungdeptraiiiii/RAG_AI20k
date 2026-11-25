"""Chỉ đọc phần mới của hợp đồng và soát theo ngày chỉ định."""
from datetime import date

import pytest

from rag.bridge.check import check_contract
from rag.bridge.tagger import TAG_PROMPT
from rag.contracts.doc import PageText
from rag.contracts.facts import extract_part_facts
from rag.contracts.llm_json import ContractAIError
from rag.contracts.structure import parse_contract, to_contract_units

from tests.test_bridge_check import PAGES
from tests.versions_helpers import APPENDIX_TEXT, AT, AppendixLLM, base_contract


def with_appendix():
    """Hợp đồng đã soát, rồi nối phụ lục."""
    c = base_contract()
    check_contract(AppendixLLM(), c, at=AT)
    c.page_texts = [*PAGES, PageText(2, APPENDIX_TEXT)]
    c.doc = parse_contract(c.page_texts)
    c.units = to_contract_units(c.doc)
    new = [u.uid for u in c.units if u.uid.startswith("p1.")]
    assert new
    return c, new


def test_extract_part_facts_reads_only_the_new_part():
    c, _ = with_appendix()
    before = list(c.facts["candidates"]["sign_date"])
    llm = AppendixLLM()
    changed = extract_part_facts(llm, c, "p1")
    sent = [u["uid"] for _, p in llm.calls for u in p["units"]]
    assert sent and all(u.startswith("p1.") for u in sent)
    assert changed == ["salary"]
    assert [x["unit"].split(".")[0] for x in c.facts["candidates"]["salary"]] == ["p0", "p1"]
    assert c.sign_date == date(2025, 1, 2) and c.facts["candidates"]["sign_date"] == before
    assert c.facts["appendix_dates"]["p1"]["sign_date"] == "2025-05-20"


def test_extract_part_facts_writes_nothing_when_llm_fails():
    c, _ = with_appendix()

    class Broken:
        def complete(self, system, user):
            return "không phải JSON"

    before = dict(c.facts)
    with pytest.raises(ContractAIError):
        extract_part_facts(Broken(), c, "p1")
    assert c.facts == before


def test_check_only_new_units_at_a_given_day():
    c, new = with_appendix()
    extract_part_facts(AppendixLLM(), c, "p1")
    old_ops = c.oplog.all()
    llm = AppendixLLM()
    report = check_contract(llm, c, at=AT, only_units=new, day=date(2025, 7, 1))
    assert report.day == date(2025, 7, 1) and c.sign_date == date(2025, 1, 2)
    tagged = [u["uid"] for s, p in llm.calls if s.startswith(TAG_PROMPT[:40]) for u in p["units"]]
    assert tagged and all(u in new for u in tagged)
    assert [o for o in old_ops if o not in c.oplog.all()] == []
    added = [o for o in c.oplog.all() if o not in old_ops and o.content.get("kind") == "fact"]
    assert added and all(o.source_uid in new for o in added)
    salary = next(x.facts_used["base_salary_vnd"] for x in report.results if "base_salary_vnd" in x.facts_used)
    assert salary["value"] == 17000000
