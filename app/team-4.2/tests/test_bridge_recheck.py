import json
from datetime import date, datetime, timezone

from rag.bridge.catalog import load_catalog
from rag.bridge.engine import RuleResult
from rag.bridge.facts_map import FactSet
from rag.bridge.recheck import RECHECK_PROMPT_VERSION, needs_recheck, recheck
from rag.contracts.models import Contract, ContractUnit

CAT = load_catalog()
AT = datetime(2026, 11, 14, 9, 0)
UNITS = [ContractUnit(f"u{i}", f"Điều {i}", f"Điều {i}. Nội dung chung số {i} về công việc hành chính.") for i in range(1, 9)]
UNITS.append(ContractUnit("u9", "Điều 9", "Điều 9. Chế độ nâng bậc, nâng lương: xét nâng lương mỗi năm một lần."))


def contract():
    return Contract("c1", "hd.txt", False, datetime(2026, 11, 14, tzinfo=timezone.utc),
                    "\n".join(u.text for u in UNITS), UNITS, len(UNITS))


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, system, user):
        self.calls.append((system, user))
        return json.dumps(self.reply(json.loads(user)), ensure_ascii=False)


def rr(concept, finding):
    return RuleResult(concept, "r1", "FAIL", finding, None, None, {}, {}, (), (), ())


def test_needs_recheck_only_silent_reportable():
    fs = FactSet({}, frozenset({"leave.annual"}), {}, frozenset({"rest.weekly"}))
    res = [rr("content.raise_policy", "missing_content"), rr("leave.annual", "hidden_right"),
           rr("rest.weekly", "hidden_right"), rr("wage.night_pay", "hidden_right"), rr("prohibit.deposit", "ok"),
           rr("wage.night_pay", "hidden_right")]
    assert needs_recheck(res, fs) == ["content.raise_policy", "wage.night_pay"]


def test_recheck_found_becomes_concept_assert():
    def reply(p):
        assert [c["id"] for c in p["concepts"]] == ["content.raise_policy"]
        assert "u9" in [u["uid"] for u in p["units"]] and len(p["units"]) <= 5
        return {"items": [{"concept": "content.raise_policy", "uid": "u9", "quote": "xét nâng lương mỗi năm một lần"}]}
    llm = FakeLLM(reply)
    ops = recheck(llm, contract(), CAT, ["content.raise_policy"], at=AT, model="m")
    assert len(llm.calls) == 1 and len(ops) == 1
    assert ops[0].content["kind"] == "concept" and ops[0].content["found_by"] == "recheck"
    assert ops[0].source_uid == "u9" and ops[0].prompt_version == RECHECK_PROMPT_VERSION


def test_recheck_not_found_records_absence():
    llm = FakeLLM(lambda p: {"items": []})
    ops = recheck(llm, contract(), CAT, ["content.raise_policy", "wage.night_pay"], at=AT)
    assert len(llm.calls) == 2
    assert [o.content["kind"] for o in ops] == ["concept_absent", "concept_absent"]
    searched = ops[0].content["searched_uids"]
    assert 1 <= len(searched) <= 5 and searched[0] == "u9"


def test_recheck_invented_quote_is_absence():
    llm = FakeLLM(lambda p: {"items": [{"concept": "content.raise_policy", "uid": "u9", "quote": "tăng lương 20% mỗi quý"}]})
    ops = recheck(llm, contract(), CAT, ["content.raise_policy"], at=AT)
    assert [o.content["kind"] for o in ops] == ["concept_absent"]
