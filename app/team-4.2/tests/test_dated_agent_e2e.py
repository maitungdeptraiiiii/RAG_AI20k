"""HTTP → actual dated agent → fixture model → JSON/SSE, without external APIs."""

import asyncio
import importlib.util
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from rag.agent import prompts
from rag.agent.temporal import TEMPORAL_REVIEW
from rag.config import Settings
from rag.index.bm25_index import BM25Index
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import RAGPipeline
from rag.retrieve.hybrid import HybridRetriever
from rag.temporal.index import VersionedIndex
from rag.temporal.qa import TemporalQA
from rag.temporal.timeline import TIMELINE_PROMPT
from tests.test_temporal_index import realestate_service


class DatedModel:
    model_id = "offline-dated-fixture"

    def __init__(self):
        self.inputs = []

    def complete(self, system, user):
        self.inputs.append(user)
        if system == TIMELINE_PROMPT:
            return '{"events":[]}'
        payload = json.loads(user)
        if system == prompts.PLAN:
            data = {"requirements": [{"id": "R1", "question": payload["standalone_question"], "depends_on": []}], "clarification": None}
        elif system == prompts.ASSESS:
            evidence = payload["excerpts"][0]
            data = {"assessments": [{"requirement_id": "R1", "status": "supported",
                    "evidence": [{"id": evidence["id"], "quote": evidence["text"][:150]}],
                    "reason": "Fixture có nguyên văn nguồn."}], "followup_queries": [], "xref_ids": []}
        elif system == prompts.COMPOSE:
            data = {"claims": [{"text": "Có căn cứ trong tài liệu được cung cấp.",
                    "evidence_ids": [payload["excerpts"][0]["id"]], "requirement_ids": ["R1"]}]}
        elif system == prompts.VERIFY:
            excerpts = {e["id"]: e["text"] for e in payload["excerpts"]}
            data = {"claims": [{"index": i, "supported": True, "reason": "Fixture verdict.",
                     "evidence": [{"id": eid, "quote": excerpts[eid][:150]} for eid in claim["evidence_ids"]]}
                    for i, claim in enumerate(payload["claims"])],
                    "requirements": [{"id": "R1", "covered": True}], "facts_preserved": True,
                    "scope_respected": True, "followup_queries": []}
        elif system == TEMPORAL_REVIEW:
            sources = payload["scope"]["sources"]
            data = {"issues": [{"claim_index": i,
                     "anchor_ids": list(dict.fromkeys(aid for eid in claim["evidence_ids"] for aid in sources[eid]["anchor_ids"])),
                     "certainty": "firm", "limitation": ""} for i, claim in enumerate(payload["claims"])],
                    "transition_assessments": [{"rule_id": rule["rule_id"], "assessment": "undetermined",
                     "reasons": ["Fixture yêu cầu xác minh chuyển tiếp."], "evidence_ids": [],
                     "missing_information": ["Cần làm rõ tình trạng thực hiện hợp đồng."]}
                     for rule in payload["scope"]["transition_rules"]],
                    "follow_up_questions": ["Tình trạng thực hiện hợp đồng là gì?"]}
        else:
            data = {"standalone_query": payload["query"]}
        return json.dumps(data, ensure_ascii=False)


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    service = realestate_service(tmp_path_factory.mktemp("dated-agent-corpus"))
    index = VersionedIndex(service.store, HashEmbedder(dim=64))
    index.build()
    return service, index


@pytest.fixture
def app(catalog):
    path = Path(__file__).resolve().parents[1] / "ui/server.py"
    spec = importlib.util.spec_from_file_location("dated_agent_e2e_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    model = DatedModel()
    retriever = HybridRetriever(BM25Index(), VectorIndex(HashEmbedder(dim=64)))
    baseline = RAGPipeline(ChunkStore(), retriever, model)
    service, index = catalog
    qa = TemporalQA(service, index, model)
    server._pipeline, server._settings = baseline, Settings()
    server.get_temporal_qa = lambda: qa
    return server, model, index


def post(server, body):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://e2e") as client:
            response = await client.post("/api/chat", json=body)
            if "text/event-stream" in response.headers.get("content-type", ""):
                events = [json.loads(x[5:].strip()) for x in response.text.split("\n\n") if x.startswith("data:")]
                return response, next((e for e in events if e["type"] == "done"), {}), events
            return response, response.json(), []
    return asyncio.run(run())


@pytest.mark.parametrize("as_of", ["2021-06-15", "2025-06-15"])
@pytest.mark.parametrize("stream", [False, True])
def test_date_reaches_all_layers_and_sources_are_valid(app, as_of, stream):
    server, model, index = app
    response, data, events = post(server, {"query": "Email qa@example.invalid. Điều kiện làm chủ đầu tư nhà ở thương mại là gì?",
                                         "think": True, "as_of": as_of, "stream": stream, "session_id": "offline-e2e"})
    assert response.status_code == 200
    assert data["status"] in ("answer", "partial", "clarify")
    assert data["as_of"] == as_of and data["timeline"]["primary"]["start"] == as_of
    assert data["trace"]["agent"]["scope"] == "temporal"
    assert data["query_pii"]["email"] == 1
    assert data["sources"]
    day = date.fromisoformat(as_of)
    for source in data["sources"]:
        version = index.chunks[source["chunk_id"]]
        assert version.valid_from <= day and (version.valid_to is None or version.valid_to > day)
        assert source["store"] == "versioned" and source["anchor_ids"] == ["T1"]
    assert all("qa@example.invalid" not in value for value in model.inputs)
    if stream:
        assert sum(event["type"] == "done" for event in events) == 1
        assert next(i for i, event in enumerate(events) if event["type"] == "token") > next(
            i for i, event in enumerate(events) if event.get("stage") == "verify")


def test_missing_version_does_not_use_legacy_or_call_model(app):
    server, model, _ = app
    response, data, _ = post(server, {"query": "Điều kiện làm chủ đầu tư nhà ở thương mại?", "think": True,
                                      "as_of": "1900-01-01", "stream": True})
    assert response.status_code == 200 and data["status"] == "abstain"
    assert data["sources"] == [] and data["citations"] == []
    assert model.inputs == []


def test_multiple_anchors_keep_revisions_separate_and_block_unresolved_transition(app):
    server, _, _ = app
    response, data, _ = post(server, {"query": "Ký hợp đồng mua nhà ngày 15/06/2023, tranh chấp ngày 15/09/2025. Điều kiện chủ đầu tư thế nào?",
                                      "think": True, "as_of": "2025-09-15", "stream": True})
    assert response.status_code == 200
    assert data["status"] == "clarify" and data["certainty"] == "cannot_conclude"
    assert data["trace"]["agent"]["temporal_claims_blocked"]
    assert data["transition_assessments"]
    assert data["citations"] == []


def test_unavailable_catalog_is_503_before_sse_headers(app):
    server, model, _ = app
    server.get_temporal_qa = lambda: None
    response, data, events = post(server, {"query": "Câu hỏi", "think": True, "as_of": "2025-01-01", "stream": True})
    assert response.status_code == 503 and data["code"] == "temporal_scope_unavailable"
    assert not events and not model.inputs


def test_think_without_as_of_uses_temporal_scope_and_validity_filter(app):
    server, model, index = app
    response, data, events = post(server, {
        "query": "Điều kiện làm chủ đầu tư nhà ở thương mại là gì?",
        "think": True, "stream": False, "session_id": "think-no-date"
    })
    assert response.status_code == 200
    assert data["trace"]["agent"]["scope"] == "temporal"
    assert data.get("as_of") is None
    assert data["timeline"]["primary"]["source"] == "default"
    assert data["sources"]
    today = date.fromisoformat(data["timeline"]["primary"]["start"])
    for source in data["sources"]:
        version = index.chunks[source["chunk_id"]]
        assert version.valid_from <= today and (version.valid_to is None or version.valid_to > today)


@pytest.mark.parametrize("invalid_as_of", [
    "2023-02-29",       # 2023 is not a leap year
    "2024-13-01",       # invalid month
    "2024-04-31",       # April has 30 days
    "15/06/2025",       # wrong format (DD/MM/YYYY)
    "2025-06-15T00:00:00",  # timestamp
    12345,              # non-string
    "not-a-date",       # garbage
])
def test_invalid_as_of_rejected_with_400(app, invalid_as_of):
    server, _, _ = app
    response, data, _ = post(server, {
        "query": "Điều kiện làm chủ đầu tư?",
        "as_of": invalid_as_of,
    })
    assert response.status_code == 400
    assert "as_of" in data["error"]


def test_leap_year_2024_02_29_accepted(app):
    server, _, _ = app
    response, data, _ = post(server, {
        "query": "Điều kiện làm chủ đầu tư?",
        "think": True,
        "as_of": "2024-02-29",
    })
    assert response.status_code == 200
    assert data["as_of"] == "2024-02-29"


def test_parallel_requests_different_as_of_isolated(app):
    server, model, index = app
    import concurrent.futures

    def run_query(as_of_date):
        return post(server, {
            "query": f"Điều kiện làm chủ đầu tư tại {as_of_date}?",
            "think": True,
            "as_of": as_of_date,
            "session_id": f"sess-{as_of_date}",
        })

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_query, "2021-06-15")
        f2 = executor.submit(run_query, "2025-06-15")
        resp1, data1, _ = f1.result()
        resp2, data2, _ = f2.result()

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert data1["as_of"] == "2021-06-15"
    assert data2["as_of"] == "2025-06-15"
    assert data1["timeline"]["primary"]["start"] == "2021-06-15"
    assert data2["timeline"]["primary"]["start"] == "2025-06-15"
    for s in data1["sources"]:
        v = index.chunks[s["chunk_id"]]
        assert v.valid_from <= date(2021, 6, 15) and (v.valid_to is None or v.valid_to > date(2021, 6, 15))
    for s in data2["sources"]:
        v = index.chunks[s["chunk_id"]]
        assert v.valid_from <= date(2025, 6, 15) and (v.valid_to is None or v.valid_to > date(2025, 6, 15))

