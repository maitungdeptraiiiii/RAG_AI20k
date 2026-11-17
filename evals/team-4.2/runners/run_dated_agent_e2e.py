"""API end-to-end checks using an isolated repository real-estate corpus.

--live uses configured LLM/Jev services for THREE public, synthetic questions.
The date index is BM25 (production cold-start path), not a paid full re-embedding.
No production catalog is modified. Prompts/responses are recorded for debugging.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "app/team-4.2"
sys.path[:0] = [str(APP / "src"), str(APP)]

from rag.agent.contracts import AgentConfig
from rag.config import Settings
from rag.generate.llm import LLMCache, OpenAIChatLLM
from rag.index.bm25_index import BM25Index
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import RAGPipeline
from rag.retrieve.context import ContextConfig
from rag.retrieve.hybrid import HybridRetriever
from rag.retrieve.rerank import make_reranker
from rag.temporal.index import VersionedIndex
from rag.temporal.log import QALog
from rag.temporal.qa import TemporalQA
from tests.test_temporal_index import realestate_service


class Recorder:
    def __init__(self, llm, directory):
        self.llm, self.directory = llm, directory
        self.model_id, self.counter = llm.model_id, 0
        self.directory.mkdir(parents=True, exist_ok=True)

    def complete_bounded(self, system, user, **options):
        self.counter += 1
        target = self.directory / f"call-{self.counter:03d}.json"
        record = {"system": system, "user": user, "options": options}
        try:
            result = self.llm.complete_bounded(system, user, **options)
            record["result"] = asdict(result)
            return result
        except Exception as exc:
            record["error"] = type(exc).__name__
            raise
        finally:
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def complete(self, system, user):
        raise AssertionError("E2E agent must use bounded model calls")


def load_server():
    spec = importlib.util.spec_from_file_location("dated_e2e_server", APP / "ui/server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checks(payload, data, index, event_types):
    problems = []
    if data.get("status") == "error":
        problems.append("agent_error")
    if not isinstance(data.get("answer"), str) or not data["answer"].strip():
        problems.append("empty_answer")
    if data.get("as_of") != payload["as_of"]:
        problems.append("selected_date_lost")
    timeline = data.get("timeline", {})
    if timeline.get("primary", {}).get("start") != payload["as_of"]:
        problems.append("wrong_primary_anchor")
    anchors = {f"T{i}": a for i, a in enumerate(timeline.get("anchors", []), 1)}
    for source in data.get("sources", []):
        if source.get("store") != "versioned":
            problems.append("legacy_source_in_dated_answer")
        if source["chunk_id"] not in index.chunks:
            problems.append("unknown_source")
        for aid in source.get("anchor_ids", []):
            anchor = anchors.get(aid, {})
            if not anchor.get("start") or not (source["valid_from"] <= (anchor.get("end") or anchor["start"]) and
               (source.get("valid_to") is None or source["valid_to"] > anchor["start"])):
                problems.append("source_outside_anchor")
    source_map = {s["chunk_id"]: s for s in data.get("sources", [])}
    for citation in data.get("citations", []):
        if citation["chunk_id"] not in source_map or citation["quote"] not in source_map[citation["chunk_id"]]["text"]:
            problems.append("invalid_citation_quote")
    if data.get("certainty") == "firm" and any(
        s.get("document_status") != "verified" or s.get("provision_status") != "verified"
        for s in data.get("sources", [])
    ):
        problems.append("firm_on_unverified_source")
    budget = data.get("trace", {}).get("agent", {}).get("budget", {})
    if budget.get("rounds", 0) > 3:
        problems.append("round_limit_bypassed")
    if event_types and event_types.count("done") != 1:
        problems.append("invalid_sse_final_count")
    return sorted(set(problems))


async def run(args):
    import httpx

    args.out.mkdir(parents=True, exist_ok=False)
    settings = Settings.load()
    server = load_server()
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    service = realestate_service(args.out / "corpus")
    index = VersionedIndex(service.store)
    index.build()
    llm = OpenAIChatLLM(settings.llm_model, temperature=settings.llm_temperature,
                        base_url=settings.llm_base_url, api_key=settings.llm_api_key,
                        cache=LLMCache(settings.cache_dir / "llm.sqlite"))
    recorder = Recorder(llm, args.out / "model_calls")
    retriever = HybridRetriever(
        BM25Index(), VectorIndex(HashEmbedder()),
        reranker=make_reranker(settings.rerank_backend, cache_path=settings.cache_dir / "rerank.sqlite"),
        arm_k=settings.arm_k, rerank_n=settings.rerank_n, bm25_rrf_weight=settings.bm25_rrf_weight,
    )
    baseline = RAGPipeline(ChunkStore(), retriever, recorder, top_k=settings.top_k,
                           context=ContextConfig(settings.context_min_p, settings.context_max_blocks,
                                                 settings.context_max_words, settings.top_k))
    qa = TemporalQA(service, index, recorder, log=QALog(args.out / "qa_log.sqlite"))
    server._pipeline, server._settings = baseline, settings
    server.get_temporal_qa = lambda: qa
    manifest = {"config": asdict(AgentConfig.from_settings(settings)), "model": settings.llm_model,
                "reranker": settings.rerank_backend, "index": "isolated realestate fixture; BM25 cold-start",
                "documents": len(service.store.documents()), "chunks": len(index.chunks),
                "production_catalog_modified": False}
    (args.out / "config.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    question = "Điều kiện làm chủ đầu tư dự án xây dựng nhà ở thương mại là gì?"
    cases = [
        ("before_change", {"query": question, "as_of": "2021-06-15", "stream": False}),
        ("after_change", {"query": question, "as_of": "2025-06-15", "stream": True}),
        ("multiple_anchors", {"query": "Chủ đầu tư dự án xây dựng nhà ở thương mại đã ký hợp đồng ngày 15/06/2023, tranh chấp phát sinh ngày 15/09/2025. Điều kiện áp dụng và quy định chuyển tiếp cần xem thế nào?", "as_of": "2025-09-15", "stream": True}),
        ("no_version_at_date", {"query": question, "as_of": "1900-01-01", "stream": True}),
    ]
    if args.cases:
        cases = [(name, body) for name, body in cases if name in args.cases]
    outcomes = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://local-e2e") as client:
        for name, body in cases:
            payload = {**body, "think": True, "session_id": f"dated-e2e-{name}"}
            print(f"START {name}", flush=True)
            response = await client.post("/api/chat", json=payload)
            events = []
            if "text/event-stream" in response.headers.get("content-type", ""):
                events = [json.loads(b[5:].strip()) for b in response.text.split("\n\n") if b.startswith("data:")]
                data = next((e for e in events if e.get("type") == "done"), {})
            else:
                data = response.json()
            event_types = [e["type"] for e in events]
            problems = checks(payload, data, index, event_types)
            if response.status_code != 200:
                problems.append(f"http_{response.status_code}")
            if name == "no_version_at_date" and data.get("status") != "abstain":
                problems.append("empty_scope_not_abstained")
            agent = data.get("trace", {}).get("agent", {})
            outcome = {"id": name, "http": response.status_code, "status": data.get("status"),
                       "certainty": data.get("certainty"), "stop_reason": agent.get("stop_reason"),
                       "sources": len(data.get("sources", [])), "budget": agent.get("budget"),
                       "problems": problems}
            outcomes.append(outcome)
            (args.out / f"{name}.json").write_text(json.dumps(
                {"request": payload, "response": data, "events": events, "outcome": outcome},
                ensure_ascii=False, indent=2), encoding="utf-8")
            (args.out / "summary.json").write_text(json.dumps(outcomes, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k: v for k, v in outcome.items() if k != "budget"}, ensure_ascii=False), flush=True)
        for name, payload, expected in [
            ("invalid_date", {"query": question, "think": True, "as_of": "2025-02-30"}, 400),
            ("invalid_think", {"query": question, "think": "false"}, 400),
        ]:
            response = await client.post("/api/chat", json=payload)
            outcomes.append({"id": name, "http": response.status_code,
                             "problems": [] if response.status_code == expected else ["wrong_http_status"]})
        server.get_temporal_qa = lambda: None
        response = await client.post("/api/chat", json={"query": question, "think": True, "as_of": "2025-06-15", "stream": True})
        outcomes.append({"id": "catalog_unavailable", "http": response.status_code,
                         "problems": [] if response.status_code == 503 and response.json().get("code") == "temporal_scope_unavailable" else ["wrong_unavailable_behavior"]})
    (args.out / "summary.json").write_text(json.dumps(outcomes, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(any(row["problems"] for row in outcomes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=["before_change", "after_change", "multiple_anchors", "no_version_at_date"])
    raise SystemExit(asyncio.run(run(parser.parse_args())))
