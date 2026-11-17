import pytest

from rag.agent.contracts import Claim, Requirement, OutputError
from rag.agent.validation import parse_verification
from tests.test_agent import A, build_agent, FixtureLLM


def test_rejected_claim_missing_evidence_does_not_destroy_verified_claims():
    req = [Requirement("R1", "Q?", ())]
    claims = [Claim("Valid", ("E1",), ("R1",)), Claim("Rejected", ("E1",), ("R1",))]
    report = {"claims": [{"index": 0, "supported": True, "reason": "Source", "evidence": [{"id": "E1", "quote": A.text}]},
                         {"index": 1, "supported": False, "reason": "Not supported"}],
              "requirements": [{"id": "R1", "covered": True}], "facts_preserved": True,
              "scope_respected": True, "followup_queries": []}
    verdicts, _, quotes, _ = parse_verification(report, req, claims, {"E1": A}, 2)
    assert verdicts == {0: True, 1: False} and quotes[1] == {}


def test_invalid_quote_never_becomes_supported_when_degrading_invalid_claims():
    report = {"claims": [{"index": 0, "supported": True, "reason": "Source", "evidence": [{"id": "E1", "quote": "Invented unsupported quote"}]}],
              "requirements": [{"id": "R1", "covered": True}], "facts_preserved": True,
              "scope_respected": True, "followup_queries": []}
    args = (report, [Requirement("R1", "Q?", ())], [Claim("C", ("E1",), ("R1",))], {"E1": A}, 2)
    with pytest.raises(OutputError):
        parse_verification(*args)
    warnings = []
    verdicts, _, _, _ = parse_verification(*args, warnings, degrade_invalid_claims=True)
    assert verdicts == {0: False} and warnings == ["claim_0_evidence_rejected"]


def test_bad_optional_assessment_actions_do_not_abort_good_evidence():
    def hook(stage, payload, result):
        if stage == "ASSESS":
            result["followup_queries"] = [{"requirement_id": "R1"}]  # malformed optional action
            result["xref_ids"] = ["nonexistent"]
        return result
    agent, _ = build_agent(FixtureLLM(hook))
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status != "error"
    assert "invalid_assessor_followups_discarded" in trace.retrieval.errors


def test_bad_quote_is_removed_but_independent_verified_claim_is_retained():
    def hook(stage, payload, result):
        if stage == "PLAN":
            result["requirements"][1]["depends_on"] = []
        if stage == "VERIFY":
            result["claims"][0]["evidence"][0]["quote"] = "KHẲNG ĐỊNH BỊA"
        return result
    model = FixtureLLM(hook)
    agent, _ = build_agent(model)
    events = list(agent.ask_stream("Điều kiện và hồ sơ?"))
    final = events[-1]
    assert final["status"] == "partial"
    assert "Hồ sơ cần có giấy B" in final["answer"]
    assert "Có quy định về điều kiện A." not in final["answer"]
    assert all("KHẲNG ĐỊNH BỊA" not in e.get("delta", "") for e in events)
    assert len(final["citations"]) == 1
    assert model.calls.count("COMPOSE") <= 2


def test_claim_depending_on_rejected_premise_is_not_published():
    def hook(stage, payload, result):
        if stage == "VERIFY":
            result["claims"][0]["evidence"][0]["quote"] = "KHẲNG ĐỊNH BỊA"
        return result
    agent, _ = build_agent(FixtureLLM(hook))
    final = list(agent.ask_stream("Điều kiện và hồ sơ?"))[-1]
    assert final["status"] == "abstain"
    assert final["citations"] == []
    assert "Hồ sơ cần có giấy B" not in final["answer"]
    assert final["trace"]["agent"]["unresolved_requirements"] == ["R1", "R2"]


def test_schema_repair_is_bounded_and_does_not_coerce_invalid_flags():
    seen = 0
    def hook(stage, payload, result):
        nonlocal seen
        if stage == "VERIFY":
            seen += 1
            if seen == 1:
                result["facts_preserved"] = "true"
        return result
    agent, _ = build_agent(FixtureLLM(hook))
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "answer"
    assert seen == 2
    assert any(c["stage"] == "verify_schema_repair" for c in trace.agent["budget"]["calls"])
