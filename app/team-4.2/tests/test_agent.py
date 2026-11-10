"""Behavioral fixtures: dependent evidence, rejection, budgets and concurrency.

No real model/index service is called. These fixtures verify orchestration and
failure handling, not production semantic/legal accuracy.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import Mock, MagicMock

import pytest

from rag.agent import AgentConfig, AgentPipeline
from rag.agent import prompts
from rag.agent.contracts import Budget, BudgetExceeded, ModelGateway
from rag.agent.corpus import CorpusSnapshot
from rag.generate.llm import LLMCache, OpenAIChatLLM
from rag.index.store import ChunkStore
from rag.pipeline import RAGPipeline
from rag.retrieve.hybrid import CorpusChangedError, HybridRetriever
from rag.schema import Chunk, Hit, REFUSAL


def chunk(doc, article, body, source="bo_luat_mau_2020.txt", index=None):
    return Chunk(f"{doc}:{index if index is not None else article:04d}", doc, source, 1, 1,
                 f"Điều {article}. Quy định", f"Điều {article}. Quy định\n{body}")


A = chunk("law", 1, "Điều kiện A được quy định tại Điều 2 của Bộ luật này.")
B = chunk("law", 2, "Hồ sơ cần có giấy B.")


class Arm:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.calls = []

    def build(self, chunks):
        pass

    def search(self, query, k):
        self.calls.append(query)
        ids = self.mapping.get(query, [A.chunk_id])
        return [Hit(cid, 0.9, i, "dense") for i, cid in enumerate(ids[:k], 1)]


class FixtureLLM:
    model_id = "fixture-agent"

    def __init__(self, hook=None):
        self.calls = []
        self.hook = hook

    def complete(self, system, user):
        payload = json.loads(user)
        stage = next((name for name in ("PLAN", "ASSESS", "COMPOSE", "VERIFY")
                      if system == getattr(prompts, name)), "CONDENSE")
        self.calls.append(stage)
        result = self.respond(stage, payload)
        if self.hook:
            result = self.hook(stage, payload, result)
        return json.dumps(result, ensure_ascii=False)

    def respond(self, stage, payload):
        if stage == "PLAN":
            return {"requirements": [
                {"id": "R1", "question": "Điều kiện A là gì?", "depends_on": []},
                {"id": "R2", "question": "Hồ sơ cần gì?", "depends_on": ["R1"]},
            ], "clarification": None}
        if stage == "CONDENSE":
            return {"standalone_query": payload["query"]}
        if stage == "ASSESS":
            excerpts = payload["excerpts"]
            rows = []
            for rid, needle in (("R1", "Điều kiện A"), ("R2", "giấy B")):
                evidence = next((e for e in excerpts if needle in e["text"]), None)
                rows.append({
                    "requirement_id": rid, "status": "supported" if evidence else "missing",
                    "evidence": [{"id": evidence["id"], "quote": evidence["text"]}] if evidence else [],
                    "reason": "Có nguyên văn căn cứ." if evidence else "Thiếu quy định về hồ sơ.",
                })
            return {"assessments": rows, "followup_queries": [],
                    "xref_ids": [e["id"] for e in payload["available_xrefs"]] if rows[1]["status"] == "missing" else []}
        if stage == "COMPOSE":
            claims = []
            for rid, needle, content in (("R1", "Điều kiện A", "Có quy định về điều kiện A."),
                                         ("R2", "giấy B", "Hồ sơ cần có giấy B.")):
                evidence = next((e for e in payload["excerpts"] if needle in e["text"]), None)
                if evidence:
                    claims.append({"text": content, "evidence_ids": [evidence["id"]], "requirement_ids": [rid]})
            return {"claims": claims}
        if stage == "VERIFY":
            excerpts = {e["id"]: e["text"] for e in payload["excerpts"]}
            claims = payload["claims"]
            return {
                "claims": [{"index": i, "supported": True, "reason": "Phù hợp nguyên văn.",
                            "evidence": [{"id": eid, "quote": excerpts[eid]} for eid in claim["evidence_ids"]]}
                           for i, claim in enumerate(claims)],
                "requirements": [{"id": rid, "covered": any(rid in c["requirement_ids"] for c in claims)}
                                 for rid in ("R1", "R2")],
                "facts_preserved": True, "scope_respected": True, "followup_queries": [],
            }
        raise AssertionError(stage)


def build_agent(llm=None, *, chunks=(A, B), config=None, arm=None):
    arm = arm or Arm()
    retriever = HybridRetriever(Arm(), arm)
    retriever.build(chunks)
    # The agent must not enter the baseline decomposition/listwise paths.
    retriever.decomposer = Mock()
    retriever.decomposer.plan.side_effect = AssertionError("Nested decomposition")
    retriever.listwise = Mock()
    retriever.listwise.rerank.side_effect = AssertionError("Hidden listwise")
    baseline = RAGPipeline(ChunkStore(), retriever, llm or FixtureLLM())
    return AgentPipeline(baseline, config), arm


def test_follows_xref_and_verifies_before_streaming():
    agent, arm = build_agent()
    events = list(agent.ask_stream("Điều kiện và hồ sơ cần gì?"))
    final = events[-1]
    assert final["type"] == "done" and final["status"] == "answer"
    metadata = final["trace"]["agent"]
    assert metadata["budget"]["rounds"] == 2
    assert metadata["budget"]["xref_targets"] == 1
    assert metadata["verified"] is True
    assert metadata["snapshot_id"] and metadata["scope"] == "snapshot_only"
    assert metadata["unresolved_requirements"] == []
    assert len(final["citations"]) == 2
    assert "giấy B" in final["answer"]
    assert "chưa xác nhận hiệu lực" in final["answer"]
    first_token = next(i for i, event in enumerate(events) if event["type"] == "token")
    verify_event = next(i for i, event in enumerate(events) if event.get("stage") == "verify")
    assert first_token > verify_event
    assert len([e for e in events if e["type"] == "done"]) == 1
    agent.retriever.decomposer.plan.assert_not_called()
    agent.retriever.listwise.rerank.assert_not_called()


def test_single_round_returns_verified_partial_not_complete():
    agent, _ = build_agent(config=AgentConfig(max_rounds=1))
    result = agent.ask_debug("Điều kiện và hồ sơ?")
    assert result.status == "partial"
    assert result.agent["unresolved_requirements"] == ["R2"]
    assert "một phần" in result.answer.text
    assert result.agent["budget"]["rounds"] == 1
    assert "giấy B" not in result.answer.text


@pytest.mark.parametrize("failure", ["invented_id", "invented_quote", "missing_requirement", "cycle", "wrong_boolean"])
def test_invalid_model_output_is_rejected_without_draft_leak(failure):
    def hook(stage, payload, output):
        if failure == "invented_id" and stage == "COMPOSE":
            output["claims"][0]["evidence_ids"] = ["E999"]
        if failure == "invented_quote" and stage == "VERIFY":
            output["claims"][0]["evidence"][0]["quote"] = "KHẲNG ĐỊNH BỊA"
        if failure == "missing_requirement" and stage == "ASSESS":
            output["assessments"].pop()
        if failure == "cycle" and stage == "PLAN":
            output["requirements"][0]["depends_on"] = ["R2"]
        if failure == "wrong_boolean" and stage == "VERIFY":
            output["facts_preserved"] = "true"
        return output

    agent, _ = build_agent(FixtureLLM(hook))
    events = list(agent.ask_stream("Điều kiện và hồ sơ?"))
    assert events[-1]["status"] == "error"
    assert events[-1]["citations"] == []
    assert all("KHẲNG ĐỊNH BỊA" not in e.get("delta", "") for e in events)
    assert "Hồ sơ cần có giấy B" not in events[-1]["answer"]


def test_failed_verification_repairs_once_and_does_not_leak_rejected_claim():
    def reject(stage, payload, output):
        if stage == "VERIFY":
            output["facts_preserved"] = False
        return output

    model = FixtureLLM(reject)
    agent, _ = build_agent(model)
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "abstain"
    assert trace.answer.text == REFUSAL
    assert model.calls.count("COMPOSE") == 2
    assert model.calls.count("VERIFY") == 2
    assert trace.agent["verified"] is False


def test_missing_user_fact_is_a_clarification_without_search():
    def hook(stage, payload, output):
        if stage == "PLAN":
            return {"requirements": [], "clarification": "Sự việc xảy ra vào thời điểm nào?"}
        return output

    agent, arm = build_agent(FixtureLLM(hook))
    trace = agent.ask_debug("Vụ đó có được không?")
    assert trace.status == "clarify"
    assert "thời điểm" in trace.answer.text
    assert not arm.calls


def test_verifier_followup_uses_remaining_rounds():
    verifier_count = 0

    def hook(stage, payload, output):
        nonlocal verifier_count
        if stage == "ASSESS" and len(payload["excerpts"]) == 1:
            # The fixture initially overestimates coverage; verifier must recover.
            output["assessments"][1] = {**output["assessments"][0], "requirement_id": "R2"}
            output["xref_ids"] = []
        if stage == "VERIFY":
            verifier_count += 1
            if verifier_count == 1:
                output["followup_queries"] = [{"requirement_id": "R2", "query": "Tìm hồ sơ giấy B"}]
        return output

    arm = Arm({"Tìm hồ sơ giấy B": [B.chunk_id]})
    agent, _ = build_agent(FixtureLLM(hook), arm=arm)
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "answer"
    assert trace.agent["budget"]["rounds"] == 2
    assert verifier_count == 2
    assert trace.agent["budget"]["searches"] <= 8


def test_empty_corpus_never_calls_model():
    model = FixtureLLM()
    agent, _ = build_agent(model, chunks=())
    trace = agent.ask_debug("Có tài liệu không?")
    assert trace.status == "abstain"
    assert model.calls == []


def test_search_exhaustion_and_no_progress_are_bounded():
    def hook(stage, payload, output):
        if stage == "ASSESS":
            output["xref_ids"] = []
            output["followup_queries"] = [{"requirement_id": "R2", "query": "Tìm bổ sung hồ sơ"}]
        return output

    agent, arm = build_agent(FixtureLLM(hook), config=AgentConfig(max_searches=2))
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "partial"
    assert len(arm.calls) <= 2
    assert trace.agent["budget"]["rounds"] <= 3


def test_snapshot_change_is_not_mixed_into_answer():
    agent, arm = build_agent()
    original_search = arm.search
    changed = False

    def search(query, k):
        nonlocal changed
        if not changed:
            changed = True
            agent.retriever.build([chunk("new", 9, "New corpus")])
        return original_search(query, k)

    arm.search = search
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "error"
    assert trace.agent["stop_reason"] == "CorpusChangedError"
    assert not trace.answer.citations


def test_concurrent_requests_have_independent_state_and_budget():
    agent, _ = build_agent()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(agent.ask_debug, ["Câu hỏi thứ nhất?", "Câu hỏi thứ hai?"]))
    assert all(r.status == "answer" for r in results)
    assert results[0].agent["budget"] is not results[1].agent["budget"]
    assert results[0].agent["snapshot_id"] == results[1].agent["snapshot_id"]
    assert all(r.agent["budget"]["xref_targets"] == 1 for r in results)


def test_condense_preserves_numbers_and_runs_once():
    model = FixtureLLM()
    agent, _ = build_agent(model)
    trace = agent.ask_debug("Nếu số tiền là 300 thì sao?", history=[{"query": "Câu trước", "answer": "Chưa xác minh"}])
    assert trace.status == "answer"
    assert model.calls.count("CONDENSE") == 1
    assert "300" in trace.condensed_query


def test_sync_and_stream_use_identical_core_result():
    agent, _ = build_agent()
    first = agent.ask_debug("Điều kiện và hồ sơ?").to_response("Điều kiện và hồ sơ?")
    second = list(agent.ask_stream("Điều kiện và hồ sơ?"))[-1]
    for key in ("answer", "citations", "sources", "status", "refused"):
        assert first[key] == second[key]


def test_xref_distinguishes_documents_and_does_not_guess_unknown_law():
    source = chunk("a", 1, "Theo Điều 2 của Bộ luật dân sự. Theo Điều 3 của Luật không xác định.", "bo_luat_hinh_su_2015.txt")
    wrong = chunk("a", 2, "Wrong same-number article", "bo_luat_hinh_su_2015.txt")
    target = chunk("b", 2, "Right other-document article", "bo_luat_dan_su_2015.txt")
    corpus = CorpusSnapshot(1, {c.chunk_id: c for c in (source, wrong, target)})
    refs = corpus.xrefs(("article", "a", source.section))
    assert len(refs) == 2
    assert refs[0].target_key[1] == "b"
    assert refs[1].status == "unresolved_document" and refs[1].target_key is None
    assert source.text[refs[0].start:refs[0].end] == refs[0].quote


def test_model_budget_admission_and_deadline():
    model = Mock(model_id="fake")
    config = AgentConfig(max_model_calls=6)
    budget = Budget(config, model_calls=2)
    gateway = ModelGateway(model, budget)
    with pytest.raises(BudgetExceeded, match="model_call_limit"):
        gateway.complete("system", "user")
    model.complete.assert_not_called()
    budget.started -= config.deadline_s + 1
    with pytest.raises(BudgetExceeded, match="deadline_exceeded"):
        gateway.complete("system", "user")


def test_bounded_sdk_call_disables_retries_and_separates_cache():
    client = MagicMock()
    response = client.with_options.return_value.chat.completions.create.return_value
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.content = '{"ok":true}'
    response.usage.prompt_tokens = 20
    response.usage.completion_tokens = 5
    model = OpenAIChatLLM("fake", client=client, cache=LLMCache())
    first = model.complete_bounded("s", "u", timeout_s=2.0, max_output_tokens=50)
    second = model.complete_bounded("s", "u", timeout_s=1.0, max_output_tokens=50)
    assert first.input_tokens == 20 and second.cache_hit
    client.with_options.assert_called_once_with(timeout=2.0, max_retries=0)
    assert client.with_options.return_value.chat.completions.create.call_args.kwargs["max_completion_tokens"] == 50


def test_failed_index_build_cannot_supply_an_agent_snapshot():
    retriever = HybridRetriever(Arm(), Arm())
    retriever.build([A])
    retriever.arms["dense"].build = Mock(side_effect=RuntimeError("failed indexing"))
    with pytest.raises(RuntimeError):
        retriever.build([B])
    with pytest.raises(CorpusChangedError):
        retriever.capture_snapshot()


def test_xref_does_not_bind_a_previous_reference_to_the_next_law_name():
    source = chunk("a", 1, "Áp dụng Điều 2 của Bộ luật này và Điều 3 của BLDS.", "bo_luat_hinh_su_2015.txt")
    local = chunk("a", 2, "Local target", "bo_luat_hinh_su_2015.txt")
    foreign = chunk("b", 3, "Foreign target", "bo_luat_dan_su_2015.txt")
    corpus = CorpusSnapshot(1, {c.chunk_id: c for c in (source, local, foreign)})
    refs = corpus.xrefs(("article", "a", source.section))
    assert [edge.target_key[1] for edge in refs] == ["a", "b"]


def test_unknown_abbreviation_does_not_silently_resolve_to_local_article():
    source = chunk("a", 1, "Áp dụng Điều 2 của BLKHONGRO.")
    local = chunk("a", 2, "Wrong target")
    corpus = CorpusSnapshot(1, {c.chunk_id: c for c in (source, local)})
    edge = corpus.xrefs(("article", "a", source.section))[0]
    assert edge.status == "unresolved_document" and edge.target_key is None


def test_partial_verified_answer_survives_a_later_budget_failure():
    def hook(stage, payload, output):
        if stage == "ASSESS":
            output["assessments"][1] = {**output["assessments"][0], "requirement_id": "R2"}
            output["xref_ids"] = []
        if stage == "VERIFY":
            output["followup_queries"] = [{"requirement_id": "R2", "query": "Follow-up reaches budget"}]
        return output

    agent, arm = build_agent(FixtureLLM(hook))
    original = arm.search

    def search(query, k):
        if query == "Follow-up reaches budget":
            raise BudgetExceeded("deadline_exceeded")
        return original(query, k)

    arm.search = search
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "partial" and trace.agent["verified"]
    assert trace.agent["stop_reason"] == "deadline_exceeded"
    assert "điều kiện A" in trace.answer.text
    assert trace.agent["unresolved_requirements"] == ["R2"]


def test_hyde_calls_use_the_same_request_budget():
    from rag.advanced.hyde import HydeRetriever, HYDE_SYSTEM

    class HydeModel(FixtureLLM):
        def complete(self, system, user):
            if system == HYDE_SYSTEM:
                self.calls.append("HYDE")
                return "Đoạn giả chỉ để tìm kiếm, không được trích dẫn."
            return super().complete(system, user)

    model = HydeModel()
    agent, arm = build_agent(model)
    agent.retriever.arms["dense"] = HydeRetriever(model, arm)
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "answer"
    assert model.calls.count("HYDE") >= 1
    assert trace.agent["budget"]["model_calls"] == len(model.calls)
    assert "Đoạn giả" not in trace.answer.text


def test_jina_adapter_limits_requests_without_changing_baseline():
    from rag.agent.adapters import bounded_dense
    from rag.index.embedder import JinaEmbedder
    from rag.index.vector_index import InMemoryVectorStore, VectorIndex

    post = Mock(return_value={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})
    embedder = JinaEmbedder("fake-jina", 2, api_key="test", post=post, max_retries=6)
    store = InMemoryVectorStore()
    store.upsert([A.chunk_id], [[1.0, 0.0]])
    budget = Budget(AgentConfig(max_service_requests=1))
    bounded = bounded_dense(VectorIndex(embedder, store), budget)
    assert bounded.search("query", 1)[0].chunk_id == A.chunk_id
    assert embedder.max_retries == 6 and bounded.embedder.max_retries == 0
    assert post.call_args.args[3] <= 30
    assert budget.service_requests == {"embedding": 1}
    with pytest.raises(BudgetExceeded, match="service_request_limit"):
        bounded.search("another query", 1)
    assert post.call_count == 1


def test_jev_adapter_disables_hidden_retry_and_fallback():
    from types import SimpleNamespace
    from rag.agent.adapters import bounded_reranker
    from rag.retrieve.rerank import FallbackReranker, JevReranker

    pytest.importorskip("typesafe_sdk")
    client = Mock()
    client.system_one.return_value = SimpleNamespace(answers={"relevant": SimpleNamespace(noul=0.9)})
    primary = JevReranker(client=client, question=object())
    baseline = FallbackReranker(primary)
    budget = Budget(AgentConfig())
    bounded = bounded_reranker(baseline, budget)
    result = bounded.rerank("query", [Hit(A.chunk_id, 1, 1, "dense")], {A.chunk_id: A}, 1)
    assert result[0].arm == "rerank"
    assert client.system_one.call_args.kwargs["retry"].max_retries == 0
    assert client.system_one.call_args.kwargs["timeout"] <= 30
    assert budget.service_requests == {"rerank": 1}
    assert baseline.last_error is None


@pytest.mark.parametrize("field,value", [("max_rounds", 1.5), ("max_searches", True),
                                        ("deadline_s", "180"), ("max_model_calls", 3)])
def test_invalid_agent_configuration_is_rejected(field, value):
    with pytest.raises(ValueError):
        AgentConfig(**{field: value})


def test_remote_content_injection_is_not_rendered():
    def hook(stage, payload, output):
        if stage == "COMPOSE":
            output["claims"][0]["text"] = '<img src="https://example.invalid/leak">'
        return output

    agent, _ = build_agent(FixtureLLM(hook))
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "error"
    assert "<img" not in trace.answer.text


def test_multiple_literal_quotes_from_one_article_form_a_literal_enclosing_span():
    from rag.agent.validation import parse_quotes

    evidence = replace(A, text="Điều kiện A. Đoạn ở giữa. Ngoại lệ B.")
    ids, quotes = parse_quotes([
        {"id": "E1", "quote": "Điều kiện A."},
        {"id": "E1", "quote": "Ngoại lệ B."},
    ], {"E1": evidence})
    assert ids == ("E1",)
    assert quotes["E1"] == evidence.text


def test_malformed_optional_queries_do_not_discard_verified_claims():
    def hook(stage, payload, output):
        if stage == "VERIFY":
            output["followup_queries"] = ["This is not a validated action"]
        return output

    agent, arm = build_agent(FixtureLLM(hook))
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "answer"
    assert trace.retrieval.errors["invalid_verifier_followups_discarded"] == "discarded"
    assert "This is not a validated action" not in arm.calls


def test_xref_and_followups_can_be_disabled_for_ablation():
    config = AgentConfig(max_xref_depth=0, followup_searches=0, initial_subqueries=0)
    agent, _ = build_agent(config=config)
    trace = agent.ask_debug("Điều kiện và hồ sơ?")
    assert trace.status == "partial"
    assert trace.agent["budget"]["rounds"] == 1
    assert trace.agent["budget"]["searches"] == 1
    assert trace.agent["budget"]["xref_targets"] == 0


def test_citation_cannot_bridge_an_omitted_segment():
    from rag.agent.validation import parse_quotes
    from rag.agent.contracts import OutputError

    evidence = replace(A, text="Điều kiện A.\n[...]\nNgoại lệ B.")
    with pytest.raises(OutputError, match="omitted source segment"):
        parse_quotes([{"id": "E1", "quote": "Điều kiện A."},
                      {"id": "E1", "quote": "Ngoại lệ B."}], {"E1": evidence})


def test_soft_quote_matching_handles_punctuation_and_whitespace():
    from rag.agent.validation import parse_quotes

    evidence = replace(A, text="Điều 20. Loại hợp đồng lao động\n1. Hợp đồng lao động được giao kết theo các loại:\na) Hợp đồng không xác định thời hạn.")
    bundle = {"E1": evidence}

    # Trailing dot, smart quotes, and whitespace variations should all resolve safely
    ids, quotes = parse_quotes([{"id": "E1", "quote": "“Hợp đồng không xác định thời hạn.”"}], bundle)
    assert ids == ("E1",)
    assert "Hợp đồng không xác định thời hạn" in quotes["E1"]

    # Newline in source vs space in quote
    ids, quotes = parse_quotes([{"id": "E1", "quote": "Loại hợp đồng lao động 1. Hợp đồng lao động"}], bundle)
    assert ids == ("E1",)
    assert "Loại hợp đồng lao động" in quotes["E1"]


def test_claim_citation_brackets_are_cleaned_gracefully():
    from rag.agent.validation import parse_claims
    from rag.agent.contracts import Requirement

    reqs = [Requirement("R1", "Câu hỏi 1", ())]
    bundle = {"E1": replace(A, text="Nội dung nguồn")}

    # LLM outputs text with [1] or [1, 2]; this should be gracefully cleaned without crashing
    claims = parse_claims({"claims": [{"text": "Hợp đồng chuyển thành không xác định thời hạn [1].", "evidence_ids": ["E1"], "requirement_ids": ["R1"]}]}, reqs, bundle)
    assert len(claims) == 1
    assert "[1]" not in claims[0].text
    assert "Hợp đồng chuyển thành không xác định thời hạn." in claims[0].text
