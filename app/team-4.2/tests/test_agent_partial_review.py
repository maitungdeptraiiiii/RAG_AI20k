"""Retain independent checked conclusions; block uncertainty and dependents."""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from rag.agent.contracts import Evidence, Requirement, RunState
from rag.agent.orchestrator import AgentTrace, _partition_claims
from rag.agent.temporal import TemporalScope
from rag.retrieve.context import ContextSelection
from rag.retrieve.hybrid import RetrievalResult
from rag.schema import Answer, Chunk, Citation, ContextBlock
from rag.temporal.answer import ContextItem
from rag.temporal.models import LegalTimeline, TimeAnchor, TransitionRule


def review_fixture(*, rule=False, unknown_date=False, shared=False, reference=False):
    day = date(2025, 6, 15)
    known = TimeAnchor("evaluation", day, day, "day", "question", None, None, 1.0)
    scope = TemporalScope.__new__(TemporalScope)
    scope.calendar_date, scope.query, scope.request_context = None, "Q", {}
    scope.anchors = {"T1": known}
    if unknown_date:
        scope.anchors["T2"] = TimeAnchor("signing", None, None, "relative_unresolved", "question", None, None, 0.5)
    scope.timeline = LegalTimeline(tuple(scope.anchors.values()), known, (), datetime.now(timezone.utc))
    count = 2 if shared else 4
    requirements = [Requirement(f"R{i}", f"Question {i}", (f"R{i-1}",) if i >= 3 else ())
                    for i in range(1, count + 1)]
    state = RunState(requirements=requirements)
    blocks, claims, quotes, items = [], [], {}, []
    scope.metadata, scope.versioned = {}, {}
    for i in range(1, count + 1):
        eid = "E1" if shared else f"E{i}"
        if not shared or i == 1:
            chunk = Chunk(f"c{i}", f"law:{i}", f"Law {i}", None, None, f"Article {i}",
                          "Premise one.\nPremise two." if shared else f"Literal premise {i}.")
            n = len(blocks) + 1
            blocks.append(ContextBlock(n, chunk))
            state.evidence[eid] = Evidence(eid, (str(i),), chunk, (chunk.chunk_id,), 1, 0, [])
            scope.metadata[chunk.chunk_id] = {"document_key": chunk.doc_id, "store": "versioned",
                                             "anchor_ids": ["T1"], "anchor_roles": ["evaluation"]}
            scope.versioned[chunk.chunk_id] = SimpleNamespace(valid_from=None if reference else date(2020, 1, 1), valid_to=None)
            items.append(ContextItem(n, "reference" if reference else "versioned", chunk.doc_id, chunk.source,
                                     str(i), chunk.section, chunk.text, None if reference else date(2020, 1, 1), None,
                                     "unversioned" if reference else "verified", "needs_review" if reference else "verified",
                                     (), ("evaluation",), chunk.chunk_id))
        claims.append({"text": f"Checked conclusion {i}.", "evidence_ids": [eid], "requirement_ids": [f"R{i}"]})
        quotes[i - 1] = {eid: ("Premise one." if i == 1 else "Premise two.") if shared else chunk.text}
    citations = [Citation.from_block(b, quote="Premise one." if shared else b.chunk.text) for b in blocks]
    trace = AgentTrace(answer=Answer("Original answer", citations, False),
                       retrieval=RetrievalResult("Q", "agent"), context=ContextSelection(blocks, "fixed"),
                       llm_called=True,
                       agent={"claims": claims, "verified_quotes": quotes, "unresolved_requirements": [],
                              "requirements": [asdict(r) for r in requirements], "verified": True,
                              "status": "answer", "stop_reason": "complete"}, status="answer")
    rules = [TransitionRule("rule-B", "amend:B", "Article 9", "Transition text", "old:B", "law:2",
                            date(2024, 1, 1), ("evaluation",))] if rule else []
    scope._current = lambda: None
    scope._items = lambda current: items
    scope._rules_for = lambda ids: rules
    scope.payload = lambda current, bundle: {}
    scope._record = lambda current: None
    data = {"issues": [{"claim_index": i, "anchor_ids": ["T1"], "certainty": "firm", "limitation": ""}
                       for i in range(count)],
            "transition_assessments": [{"rule_id": "rule-B", "assessment": "undetermined", "reasons": [],
                                        "evidence_ids": ["E2"], "missing_information": ["Tình trạng thực hiện?"]}] if rule else [],
            "follow_up_questions": []}

    class Gateway:
        budget = SimpleNamespace(summary=lambda: {})
        def json(self, *args, **kwargs):
            return deepcopy(data)

    return scope, state, trace, data, Gateway()


def finalize(fixture):
    scope, state, trace, _, gateway = fixture
    scope.finalize(trace, gateway, state, {eid: e.chunk for eid, e in state.evidence.items()})
    assert trace.status != "error", trace.retrieval.errors
    return trace


def test_one_uncertain_claim_keeps_independent_answer_and_blocks_transitive_dependents():
    fixture = review_fixture()
    fixture[3]["issues"][1]["certainty"] = "cannot_conclude"
    fixture[3]["issues"].reverse()  # Model row order must not change claim identity.
    trace = finalize(fixture)
    assert trace.status == "partial" and trace.temporal["certainty"] == "firm"
    assert "Checked conclusion 1." in trace.answer.text
    assert all(f"Checked conclusion {i}." not in trace.answer.text for i in (2, 3, 4))
    assert trace.agent["unresolved_requirements"] == ["R2", "R3", "R4"]
    assert trace.agent["blocked_claim_indices"] == [1, 2, 3]
    assert [c.chunk_id for c in trace.answer.citations] == ["c1"]
    assert [b.chunk.chunk_id for b in trace.context.blocks] == ["c1"]
    assert len(trace.temporal["issues"]) == 1


def test_unresolved_transition_does_not_erase_unrelated_law_or_leave_wrong_citations():
    trace = finalize(review_fixture(rule=True))
    assert trace.status == "partial" and trace.temporal["certainty"] == "firm"
    assert [c["requirement_ids"] for c in trace.agent["claims"]] == [["R1"]]
    assert trace.temporal["follow_up_questions"] == ["Tình trạng thực hiện?"]
    assert trace.temporal["transition_assessments"][0]["citations"] == []


def test_unknown_date_only_blocks_issues_assigned_to_it():
    fixture = review_fixture(unknown_date=True)
    fixture[3]["issues"][1]["anchor_ids"].append("T2")
    trace = finalize(fixture)
    assert trace.status == "partial" and len(trace.agent["claims"]) == 1
    assert trace.temporal["follow_up_questions"]
    unrelated = finalize(review_fixture(unknown_date=True))
    assert unrelated.status == "answer"
    assert unrelated.temporal["follow_up_questions"] == []


@pytest.mark.parametrize("questions, status", [([], "abstain"), (["Sự việc diễn ra thế nào?"], "clarify")])
def test_no_verified_conclusion_does_not_mislabel_missing_sources_as_missing_user_facts(questions, status):
    fixture = review_fixture()
    for issue in fixture[3]["issues"]:
        issue["certainty"] = "cannot_conclude"
    fixture[3]["follow_up_questions"] = questions
    trace = finalize(fixture)
    assert trace.status == status and trace.temporal["certainty"] == "cannot_conclude"
    assert trace.answer.citations == [] and trace.context.blocks == []
    assert trace.agent["claims"] == [] and not trace.agent["verified"]
    if not questions:
        assert "bổ sung" not in trace.answer.text


def test_shared_source_uses_quote_from_retained_claim_and_renumbers_trace_consistently():
    fixture = review_fixture(shared=True)
    fixture[3]["issues"][0]["certainty"] = "cannot_conclude"
    trace = finalize(fixture)
    assert trace.answer.citations[0].quote == "Premise two."
    assert trace.answer.citations[0].n == 1
    assert "[1]" in trace.answer.text
    assert trace.agent["verified_quotes"] == {0: {"E1": "Premise two."}}
    assert trace.temporal["issues"][0]["issue"] == "Checked conclusion 2."


def test_partial_result_does_not_promote_unverified_source():
    fixture = review_fixture(reference=True)
    fixture[3]["issues"][1]["certainty"] = "cannot_conclude"
    trace = finalize(fixture)
    assert trace.status == "partial" and trace.temporal["certainty"] == "qualified"


def test_retained_sources_are_renumbered_after_first_claim_is_blocked():
    fixture = review_fixture()
    fixture[3]["issues"][0]["certainty"] = "cannot_conclude"
    trace = finalize(fixture)
    response = trace.to_response("Q")
    assert [c["n"] for c in response["citations"]] == [1, 2, 3]
    assert [c["chunk_id"] for c in response["sources"]] == ["c2", "c3", "c4"]
    assert [i["citations"] for i in response["issues"]] == [[1], [2], [3]]
    assert "Checked conclusion 1." not in response["answer"]


def test_missing_requirement_blocks_its_child_even_if_child_has_a_quote():
    requirements = [Requirement("R1", "Independent", ()), Requirement("R2", "Missing", ()),
                    Requirement("R3", "Dependent", ("R2",))]
    keep, unavailable = _partition_claims(requirements, [("R1",), ("R3",)], {"R2"})
    assert keep == [0] and unavailable == {"R2", "R3"}
