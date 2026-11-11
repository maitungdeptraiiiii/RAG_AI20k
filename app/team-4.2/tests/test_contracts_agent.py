"""Think trong chế độ Hỏi với hợp đồng: agent tìm trên hợp đồng + luật có phiên bản tại ngày ký + kho cũ."""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from rag.agent import AgentConfig, prompts
from rag.agent.corpus import CorpusSnapshot
from rag.contracts.agent_view import (LEGAL_WARNING, ContractAgentRetriever, VERSIONED_PREFIX,
                                      run_contract_agent)
from rag.contracts.models import Contract
from rag.contracts.parse import split_units
from rag.legal.chunks import VersionedChunk
from rag.retrieve.context import ContextConfig
from rag.schema import Chunk, Hit

TEXT = (Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "contracts_demo"
        / "hop_dong_thue_nha_2023.txt").read_text(encoding="utf-8")
SIGNED = date(2023, 3, 15)
LAW = VersionedChunk("luat:65/2014/QH13#d132@b1", "luat:65/2014/QH13", "luat:65/2014/QH13#d132",
                     "Chương VIII > Điều 132. Đơn phương chấm dứt hợp đồng thuê nhà ở",
                     "Điều 132. Đơn phương chấm dứt hợp đồng thuê nhà ở\n3. Bên cho thuê phải thông báo cho bên thuê "
                     "biết trước ít nhất 30 ngày về việc đơn phương chấm dứt hợp đồng thuê nhà.",
                     date(2015, 7, 1), date(2024, 8, 1), "verified", (), (), (), "b1")
LEGACY = Chunk("blds:0428", "blds", "bo_luat_dan_su_2015.txt", 1, 1, "Điều 428. Đơn phương chấm dứt thực hiện hợp đồng",
               "Điều 428. Đơn phương chấm dứt thực hiện hợp đồng\n1. Một bên có quyền đơn phương chấm dứt.")


def contract():
    units = split_units(TEXT)
    c = Contract("c1", "hop_dong.txt", False, datetime(2026, 11, 11, tzinfo=timezone.utc), TEXT, units, len(units))
    c.sign_date, c.party = SIGNED, "Bên thuê"
    return c


class FakeIndex:
    chunks = {LAW.chunk_id: LAW}

    def search(self, query, start, end, k):
        assert start == end == SIGNED
        return [(LAW, 1.0)] if "chấm dứt" in query else []


RUNTIME = SimpleNamespace(index=FakeIndex(), service=SimpleNamespace(store=SimpleNamespace(
    document=lambda key: SimpleNamespace(title="Luật Nhà ở số 65/2014/QH13"))))


def legacy():
    return {LEGACY.chunk_id: LEGACY}, (lambda q, k: [Hit(LEGACY.chunk_id, 0.5, 1, "bm25")])


class AgentLLM:
    """Đóng vai agent: R1 cần điều khoản hợp đồng, R2 cần luật."""

    model_id = "fixture-contract-agent"

    def __init__(self, law_needle="ít nhất 30 ngày"):
        self.calls, self.law_needle = [], law_needle

    def complete(self, system, user):
        payload = json.loads(user)
        self.calls.append(user)
        stage = next((n for n in ("PLAN", "ASSESS", "COMPOSE", "VERIFY") if system == getattr(prompts, n)), "CONDENSE")
        needles = (("R1", "bất cứ lúc nào"), ("R2", self.law_needle))
        if stage == "PLAN":
            return json.dumps({"requirements": [
                {"id": "R1", "question": "Hợp đồng cho Bên A đơn phương chấm dứt thế nào?", "depends_on": []},
                {"id": "R2", "question": "Luật yêu cầu bên cho thuê báo trước khi đơn phương chấm dứt?",
                 "depends_on": []}], "clarification": None}, ensure_ascii=False)
        if stage == "CONDENSE":
            return json.dumps({"standalone_query": payload["query"]}, ensure_ascii=False)
        ex = payload.get("excerpts", [])

        def find(needle):
            return next((e for e in ex if needle in e["text"]), None)
        if stage == "ASSESS":
            rows = []
            for rid, needle in needles:
                e = find(needle)
                rows.append({"requirement_id": rid, "status": "supported" if e else "missing",
                             "evidence": [{"id": e["id"], "quote": needle}] if e else [], "reason": "ok"})
            return json.dumps({"assessments": rows, "followup_queries": [], "xref_ids": []}, ensure_ascii=False)
        if stage == "COMPOSE":
            claims = [{"text": t, "evidence_ids": [find(n)["id"]], "requirement_ids": [rid]}
                      for (rid, n), t in zip(needles, ("Hợp đồng cho Bên A chấm dứt bất cứ lúc nào.",
                                                       "Luật yêu cầu báo trước ít nhất 30 ngày.")) if find(n)]
            return json.dumps({"claims": claims}, ensure_ascii=False)
        claims = payload["claims"]
        return json.dumps({
            "claims": [{"index": i, "supported": True, "reason": "ok",
                        "evidence": [{"id": eid, "quote": needles[i][1] if i < 2 else ""} for eid in c["evidence_ids"]]}
                       for i, c in enumerate(claims)],
            "requirements": [{"id": rid, "covered": any(rid in c["requirement_ids"] for c in claims)}
                             for rid in ("R1", "R2")],
            "facts_preserved": True, "scope_respected": True, "followup_queries": []}, ensure_ascii=False)


def baseline(llm):
    return SimpleNamespace(llm=llm, condenser=SimpleNamespace(llm=llm),
                           context_config=ContextConfig(fixed_k=8), top_k=5)


def test_retriever_merges_three_labelled_sources_with_masked_contract():
    chunks, search = legacy()
    r = ContractAgentRetriever(contract(), RUNTIME, chunks, search)
    _, snap = r.capture_snapshot()
    sources = {c.source.split(":")[0] for c in snap.values()}
    assert {"Hợp đồng", VERSIONED_PREFIX.rstrip(": ")} <= sources and LEGACY.chunk_id in snap
    assert not any("001085012345" in c.text for c in snap.values())
    hits = r.search_candidates("đơn phương chấm dứt", 6, revision=r.revision, chunks=snap).ranked
    kinds = {snap[h.chunk_id].source.split(":")[0] for h in hits}
    assert "Hợp đồng" in kinds and VERSIONED_PREFIX.rstrip(": ") in kinds


def test_contract_internal_reference_is_followable():
    r = ContractAgentRetriever(contract(), None, {}, None)
    revision, snap = r.capture_snapshot()
    corpus = CorpusSnapshot(revision, snap)
    dieu9 = next(c for c in snap.values() if c.section.startswith("Điều 9."))
    from rag.retrieve.merge import article_key
    targets = {x.target_key for x in corpus.xrefs(article_key(dieu9)) if x.status == "resolved"}
    assert any(t and t[-1].startswith("Điều 4.") for t in targets)


def test_think_with_contract_answers_from_contract_and_law_without_leaking_pii():
    llm = AgentLLM()
    chunks, search = legacy()
    out = run_contract_agent(contract(), baseline(llm), AgentConfig(), RUNTIME, chunks, search,
                             "Bên A có được đơn phương chấm dứt không? Gọi tôi 0987 654 321", [])
    assert out["status"] == "answer" and out["contract_id"] == "c1"
    kinds = {s["source"].split(":")[0] for s in out["sources"]}
    assert "Hợp đồng" in kinds and VERSIONED_PREFIX.rstrip(": ") in kinds
    assert LEGAL_WARNING not in out["answer"]
    assert all("0987 654 321" not in call and "001085012345" not in call for call in llm.calls)


def test_without_versioned_law_answer_is_downgraded_with_warning():
    llm = AgentLLM(law_needle="đơn phương chấm dứt.")       # chỉ khớp kho cũ
    chunks, search = legacy()
    out = run_contract_agent(contract(), baseline(llm), AgentConfig(), None, chunks, search,
                             "Bên A có được đơn phương chấm dứt không?", [])
    assert out["status"] == "partial" and LEGAL_WARNING in out["answer"]


def test_stream_events_end_with_unmasked_done():
    llm = AgentLLM()
    chunks, search = legacy()
    events = list(run_contract_agent(contract(), baseline(llm), AgentConfig(), RUNTIME, chunks, search,
                                     "Bên A có được đơn phương chấm dứt không?", [], stream=True))
    assert events[0]["type"] == "progress" and events[-1]["type"] == "done"
    assert events[-1]["contract_id"] == "c1"


def test_agent_question_carries_contract_context():
    llm = AgentLLM()
    c = contract()
    c.facts = {"type": "Hợp đồng thuê nhà ở", "parties": [{"role": "Bên cho thuê"}, {"role": "Bên thuê"}]}
    chunks, search = legacy()
    run_contract_agent(c, baseline(llm), AgentConfig(), RUNTIME, chunks, search, "Bên A có được chấm dứt không?", [])
    plan = json.loads(llm.calls[0])
    assert "Hợp đồng thuê nhà ở" in plan["standalone_question"] and "15/03/2023" in plan["standalone_question"]
    assert "Bên A có được chấm dứt không?" in plan["standalone_question"]
