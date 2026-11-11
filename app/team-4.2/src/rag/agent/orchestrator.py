"""Single request-local search/assess/verify loop, shared by JSON and SSE."""

from __future__ import annotations

import re
import html
from dataclasses import asdict, dataclass, field, replace
from itertools import zip_longest
from collections.abc import Iterator, Sequence
from typing import Any

from rag.advanced.condense import CONDENSE_SYSTEM_PROMPT
from rag.advanced.hyde import HydeRetriever
from rag.agent import prompts
from rag.agent.adapters import bounded_dense, bounded_reranker
from rag.agent.contracts import (
    AgentConfig, Budget, BudgetExceeded, Evidence, ModelGateway, OutputError, RunState,
)
from rag.agent.corpus import CorpusSnapshot
from rag.agent.validation import (
    obj, parse_assessment, parse_claims, parse_plan, parse_verification, text,
)
from rag.pipeline import AskTrace, RAGPipeline
from rag.retrieve.context import ContextSelection
from rag.retrieve.hybrid import CorpusChangedError, RetrievalResult
from rag.retrieve.merge import article_key
from rag.schema import Answer, Citation, ContextBlock, Hit, nfc


SCOPE_WARNING = "Câu trả lời dựa trên tài liệu trong kho; chưa xác nhận hiệu lực pháp luật hiện hành."


def _literal_label(value: str) -> str:
    return html.escape(value).replace("[", "&#91;").replace("!", "&#33;")


@dataclass
class AgentTrace(AskTrace):
    agent: dict[str, Any] = field(default_factory=dict)
    status: str = "abstain"

    def to_response(self, query: str) -> dict:
        blocks = {b.chunk.chunk_id: b for b in self.context.blocks}
        sources = [{
            "n": b.n, "chunk_id": b.chunk.chunk_id, "source": b.chunk.source,
            "section": b.chunk.section or "Căn cứ pháp lý", "page": b.chunk.page_start,
            "score": None, "text": b.chunk.text,
        } for b in self.context.blocks]
        citations = [{
            **asdict(c), "section": blocks[c.chunk_id].chunk.section,
            "score": None, "text": blocks[c.chunk_id].chunk.text,
        } for c in self.answer.citations]
        return {
            "query": query, "answer": self.answer.text, "refused": self.answer.refused,
            "status": self.status, "citations": citations, "sources": sources,
            "trace": {
                "condensed_query": self.condensed_query, "context_mode": self.context.mode,
                "n_context_blocks": len(sources), "reranked": False,
                "errors": self.retrieval.errors, "arms": {}, "final_hits": [],
                "agent": self.agent,
            },
        }


class AgentPipeline:
    def __init__(self, baseline: RAGPipeline, config: AgentConfig | None = None):
        self.baseline = baseline
        self.retriever = baseline.retriever
        self.config = config or AgentConfig()

    def ask_debug(self, query: str, *, history: Sequence[dict[str, Any]] | None = None) -> AgentTrace:
        for event in self.run_events(query, history=history):
            if event["type"] == "result":
                return event["result"]
        raise RuntimeError("Agent ended without a result")

    def ask(self, query: str, *, history=None) -> Answer:
        return self.ask_debug(query, history=history).answer

    def ask_stream(self, query: str, *, history=None) -> Iterator[dict]:
        for event in self.run_events(query, history=history):
            if event["type"] != "result":
                yield event
                continue
            data = event["result"].to_response(query)
            # Only verified/rendered final text may enter the token channel.
            yield {"type": "sources", "sources": data["sources"]}
            yield {"type": "token", "delta": data["answer"]}
            yield {"type": "done", **data}

    @staticmethod
    def _event(state: RunState, stage: str, message: str, **payload):
        event = {"type": "progress", "stage": stage, "message": message,
                 "sequence": len(state.events) + 1, **payload}
        state.events.append(event)
        return event

    def _add(self, state, corpus, key, round_number, depth, origin):
        if key in state.by_unit:
            evidence = state.evidence[state.by_unit[key]]
            evidence.origins.append(origin)
            evidence.depth = min(evidence.depth, depth)
            return None
        if len(state.evidence) >= self.config.max_units:
            return None
        round_limit = self.config.initial_pool_size if round_number == 1 else self.config.new_units_per_round
        if sum(e.round == round_number for e in state.evidence.values()) >= round_limit:
            return None
        chunk, ids = corpus.materialize(key)
        eid = f"E{len(state.evidence) + 1}"
        state.evidence[eid] = Evidence(eid, key, chunk, ids, round_number, depth, [origin])
        state.by_unit[key] = eid
        return eid

    def _bundle(self, state):
        """Protect previously substantiated requirements, then inspect new units.

        Exact contiguous source prefixes keep offsets/quotes verifiable. A long
        unit is visibly truncated; no model may assume the missing tail exists.
        """
        cfg = self.baseline.context_config
        protected = [eid for a in state.assessments for eid in a.evidence_ids]
        fresh = [eid for eid, e in state.evidence.items() if e.round == max(x.round for x in state.evidence.values())]
        order = list(dict.fromkeys([*protected, *fresh, *state.evidence]))
        bundle, used = {}, 0
        # Fair byte/word allotment prevents one long article consuming the bundle.
        per_unit = max(1, min(500, cfg.max_words // max(1, min(len(order), cfg.max_blocks))))
        for eid in order:
            if len(bundle) >= cfg.max_blocks or used >= cfg.max_words:
                break
            chunk = state.evidence[eid].chunk
            words = list(re.finditer(r"\S+", chunk.text))
            count = min(len(words), per_unit, cfg.max_words - used)
            if not count:
                continue
            focus = next((origin.get("chunk_id") for origin in reversed(state.evidence[eid].origins)
                          if origin.get("chunk_id")), None)
            # Search may match the tail of a long article. Preserve that source
            # window rather than always showing its unrelated opening clause.
            start = 0
            if focus:
                focus_text = next((origin.get("focus_text", "") for origin in reversed(state.evidence[eid].origins)
                                   if origin.get("chunk_id") == focus), "")
                located = chunk.text.find(focus_text[:120]) if focus_text else -1
                if located >= 0:
                    start = located
            window_words = list(re.finditer(r"\S+", chunk.text[start:]))
            count = min(count, len(window_words))
            excerpt = chunk.text[start:start + window_words[count - 1].end()]
            bundle[eid] = replace(chunk, text=excerpt)
            used += count
        return bundle

    @staticmethod
    def _payload(query, raw_query, history, state, bundle):
        return {
            "original_question": raw_query, "standalone_question": query,
            "history": history, "scope": "snapshot_only; temporal applicability unverified",
            "requirements": [asdict(r) for r in state.requirements],
            "excerpts": [{"id": eid, "source": chunk.source, "section": chunk.section,
                          "text": chunk.text, "truncated": chunk.text != state.evidence[eid].chunk.text}
                         for eid, chunk in bundle.items()],
        }

    def _finish(self, query, state, budget, corpus, bundle, *, status, reason,
                claims=(), quotes=None, coverage=None, clarification=None, verified=False):
        quotes, coverage = quotes or {}, coverage or {}
        used_ids = list(dict.fromkeys(eid for claim in claims for eid in claim.evidence_ids))
        used_bundle = {eid: bundle[eid] for eid in used_ids}
        numbered = {eid: i for i, eid in enumerate(used_ids, 1)}
        blocks = [ContextBlock(numbered[eid], chunk) for eid, chunk in used_bundle.items()]
        citations = []
        for eid, chunk in used_bundle.items():
            quote = next((value[eid] for value in quotes.values() if eid in value), None)
            if quote is None or quote not in chunk.text:
                raise OutputError("Final citation lacks a verified literal source span")
            citations.append(Citation.from_block(ContextBlock(numbered[eid], chunk), quote=quote))
        if claims:
            content = "\n\n".join(
                claim.text + " " + "".join(f"[{numbered[eid]}]" for eid in claim.evidence_ids)
                for claim in claims
            )
            if status == "partial":
                content = "Tôi mới xác minh được một phần câu hỏi:\n\n" + content
            remaining = [r.question for r in state.requirements if not coverage.get(r.id, False)]
            if remaining:
                content += "\n\nChưa đủ căn cứ để kết luận: " + "; ".join(_literal_label(q) for q in remaining)
            content += "\n\n" + SCOPE_WARNING
            answer = Answer(content, citations, False)
        elif status == "clarify":
            answer = Answer(_literal_label(clarification or "Bạn vui lòng làm rõ dữ kiện còn thiếu trong câu hỏi."), [], False)
        elif status == "error":
            answer = Answer("Chưa thể kiểm chứng câu trả lời lúc này. Bạn có thể thử lại hoặc tắt Think để tra cứu thông thường.", [], False)
        else:
            answer = Answer.refusal()
        hits = [Hit(e.chunk.chunk_id, 0.0, i, "agent", e.chunk_ids[1:])
                for i, e in enumerate(state.evidence.values(), 1)]
        retrieval = RetrievalResult(query=query, mode="agent", candidates=hits, ranked=hits,
                                    hits=hits[:self.baseline.top_k], errors=dict(state.errors),
                                    queries=list(state.searched), selection_policy="agent_evidence")
        answer.hits = retrieval.hits
        metadata = {
            "version": prompts.PROMPT_VERSION, "scope": "snapshot_only", "scope_warning": SCOPE_WARNING,
            "snapshot_id": corpus.id if corpus else None, "status": status, "stop_reason": reason,
            "verified": verified, "config": asdict(self.config), "budget": budget.summary(),
            "requirements": [asdict(r) for r in state.requirements],
            "assessments": [asdict(a) for a in state.assessments],
            "unresolved_requirements": [r.id for r in state.requirements if not coverage.get(r.id, False)],
            "evidence": [{"id": e.id, "chunk_ids": list(e.chunk_ids), "unit_key": list(e.key),
                          "round": e.round, "xref_depth": e.depth,
                          "origins": [{k: v for k, v in origin.items() if k != "focus_text"} for origin in e.origins]}
                         for e in state.evidence.values()],
            "claims": [asdict(c) for c in claims], "verified_quotes": quotes, "events": list(state.events),
        }
        return AgentTrace(answer, retrieval, ContextSelection(blocks, "fixed" if blocks else "empty"),
                          budget.model_calls > 0, query, metadata, status)

    def run_events(self, raw_query: str, *, history=None) -> Iterator[dict]:
        state, budget = RunState(), Budget(self.config)
        gateway = ModelGateway(self.baseline.llm, budget)
        corpus, bundle, query = None, {}, nfc(raw_query).strip()
        if not query or len(query) > 8000:
            raise ValueError("Agent query must contain 1–8000 characters")
        # Retain context for reference resolution, never treat old answers as facts.
        history = [{"query": str(h.get("query", ""))[:2000],
                    "assistant_context_unverified": str(h.get("answer", ""))[:250]}
                   for h in (history or [])[-3:] if isinstance(h, dict)]
        reason, repair_used = "max_rounds", False
        last_verified = None
        try:
            revision, chunks = self.retriever.capture_snapshot()
            corpus = CorpusSnapshot(revision, chunks)
            if not chunks:
                yield {"type": "result", "result": self._finish(
                    query, state, budget, corpus, bundle, status="abstain", reason="empty_corpus")}
                return
            yield self._event(state, "prepare", "Think · Đang xác định câu hỏi và phạm vi tài liệu…")
            if history:
                condenser = ModelGateway(self.baseline.condenser.llm, budget, "condense")
                data = condenser.json("condense", CONDENSE_SYSTEM_PROMPT + prompts.RULES,
                                      {"query": query, "history": history}, reserve_calls=5)
                obj(data, ("standalone_query",))
                condensed = text(data["standalone_query"], 8000)
                if set(re.findall(r"\d+(?:[.,/]\d+)*", query)).issubset(set(re.findall(r"\d+(?:[.,/]\d+)*", condensed))):
                    query = condensed
                else:
                    # Preserves raw user numeric facts if condense dropped any, avoiding an abrupt crash.
                    query = query
            data = gateway.json("plan", prompts.PLAN, {
                "original_question": raw_query, "standalone_question": query, "history": history,
                "max_requirements": self.config.max_requirements,
            })
            state.requirements, clarification = parse_plan(data, self.config.max_requirements)
            if clarification:
                yield {"type": "result", "result": self._finish(
                    query, state, budget, corpus, bundle, status="clarify", reason="missing_user_fact",
                    clarification=clarification)}
                return
            yield self._event(state, "plan", f"Think · Đã xác định {len(state.requirements)} yêu cầu cần kiểm chứng.")
            dense = self.retriever.arms["dense"]
            if isinstance(dense, HydeRetriever):
                dense = HydeRetriever(gateway, bounded_dense(dense.dense, budget), include_query=dense.include_query, fallback=False)
            else:
                dense = bounded_dense(dense, budget)
            reranker = bounded_reranker(self.retriever.reranker, budget)
            pending_queries = [("original", query), *[(r.id, r.question) for r in state.requirements[:self.config.initial_subqueries]]]
            pending_xrefs = []
            previous_supported = set()
            previous_bundle = {}
            while budget.rounds < self.config.max_rounds:
                budget.check()
                if not budget.can_finalize_after_search():
                    reason = "model_call_limit"
                    break
                budget.rounds += 1
                yield self._event(state, "retrieve", f"Think · Vòng {budget.rounds}/{self.config.max_rounds}: đang tìm bằng chứng…",
                                  round=budget.rounds)
                before = len(state.evidence)
                branches = []
                for rid, search_query in pending_queries:
                    normalized = " ".join(nfc(search_query).casefold().split())
                    if normalized in state.searched or budget.searches >= self.config.max_searches:
                        continue
                    budget.check()
                    if not budget.can_finalize_after_search():
                        break
                    state.searched.add(normalized)
                    budget.searches += 1
                    try:
                        result = self.retriever.search_candidates(
                            search_query, (min(self.config.initial_pool_size, max(self.config.candidates_per_search, self.retriever.rerank_n))
                                           if rid == "original" and budget.rounds == 1 else self.config.candidates_per_search), revision=revision,
                            chunks=chunks, mode=self.config.retrieval_mode, dense=dense, reranker=reranker,
                        )
                        budget.check()
                        state.errors.update({f"r{budget.rounds}:q{budget.searches}:{k}": v for k, v in result.errors.items()})
                        branches.append((rid, search_query, result.ranked))
                    except (BudgetExceeded, CorpusChangedError):
                        raise
                    except Exception as exc:
                        state.errors[f"search_{budget.searches}"] = type(exc).__name__
                # Interleave rank positions across requirements; scores from different
                # queries are intentionally never compared or added.
                if budget.rounds == 1 and branches and branches[0][0] == "original":
                    for hit in branches[0][2]:
                        if hit.chunk_id in chunks:
                            self._add(state, corpus, article_key(chunks[hit.chunk_id]), budget.rounds, 0, {
                                "type": "search", "requirement_id": "original", "query": query,
                                "rank": hit.rank, "score": hit.score, "score_type": hit.arm,
                                "chunk_id": hit.chunk_id, "focus_text": chunks[hit.chunk_id].text,
                            })
                for group in zip_longest(*(branch[2] for branch in branches)):
                    for index, hit in enumerate(group):
                        if hit is None or hit.chunk_id not in chunks:
                            continue
                        rid, search_query, _ = branches[index]
                        self._add(state, corpus, article_key(chunks[hit.chunk_id]), budget.rounds, 0, {
                            "type": "search", "requirement_id": rid, "query": search_query,
                            "rank": hit.rank, "score": hit.score, "score_type": hit.arm,
                            "chunk_id": hit.chunk_id, "focus_text": chunks[hit.chunk_id].text,
                        })
                for source_eid, edge in pending_xrefs[:self.config.xrefs_per_round]:
                    budget.check()
                    source = state.evidence[source_eid]
                    if (edge.id in state.followed or edge.target_key is None or
                        source.depth >= self.config.max_xref_depth or
                        budget.xref_targets >= self.config.max_xref_targets):
                        continue
                    state.followed.add(edge.id)
                    budget.xref_targets += 1
                    self._add(state, corpus, edge.target_key, budget.rounds, source.depth + 1, {
                        "type": "xref", "from_evidence": source_eid, **edge.to_dict(),
                    })
                if not state.evidence:
                    reason = "tool_failure" if state.errors else "corpus_gap"
                    break
                bundle = self._bundle(state)
                xrefs = {}
                for eid in bundle:
                    evidence = state.evidence[eid]
                    if evidence.depth < self.config.max_xref_depth:
                        for edge in corpus.xrefs(evidence.key):
                            if (edge.status == "resolved" and edge.id not in state.followed and
                                edge.target_key not in state.by_unit and len(xrefs) < 40):
                                xrefs[edge.id] = (eid, edge)
                payload = self._payload(query, raw_query, history, state, bundle)
                payload.update(available_xrefs=[edge.to_dict() for _, edge in xrefs.values()],
                               followup_limit=self.config.followup_searches, searched_queries=sorted(state.searched))
                data = gateway.json("assess", prompts.ASSESS, payload)
                state.assessments, next_queries, selected_xrefs = parse_assessment(
                    data, state.requirements, bundle, xrefs, self.config.followup_searches)
                supported = {a.requirement_id for a in state.assessments if a.status == "supported"}
                pending_queries = [(rid, q) for rid, q in next_queries if " ".join(nfc(q).casefold().split()) not in state.searched]
                pending_xrefs = [xrefs[xid] for xid in selected_xrefs]
                yield self._event(state, "coverage", f"Think · Có căn cứ cho {len(supported)}/{len(state.requirements)} yêu cầu.",
                                  supported=len(supported), total=len(state.requirements))
                current_bundle = {eid: c.text for eid, c in bundle.items()}
                progress = len(state.evidence) > before or supported != previous_supported or current_bundle != previous_bundle
                previous_bundle = current_bundle
                previous_supported = supported
                can_fetch = budget.rounds < self.config.max_rounds and budget.can_finalize_after_search()
                useful_actions = ((pending_queries and budget.searches < self.config.max_searches) or
                                  (pending_xrefs and budget.xref_targets < self.config.max_xref_targets))
                if len(supported) < len(state.requirements) and useful_actions and can_fetch and progress:
                    continue
                if not progress:
                    reason = "no_progress"
                elif len(supported) == len(state.requirements):
                    reason = "evidence_ready"
                elif not useful_actions:
                    reason = "missing_user_fact" if any(a.status == "missing_user_fact" for a in state.assessments) else "corpus_gap"
                # Compose and verify only what actually fits in the source bundle.
                payload = self._payload(query, raw_query, history, state, bundle)
                payload["assessments"] = [asdict(a) for a in state.assessments]
                yield self._event(state, "compose", "Think · Đang tổng hợp câu trả lời từ bằng chứng…")
                claims = parse_claims(gateway.json("compose", prompts.COMPOSE, payload, reserve_calls=1), state.requirements, bundle)
                if not claims:
                    missing_facts = [a.reason for a in state.assessments if a.status == "missing_user_fact"]
                    if missing_facts:
                        yield {"type": "result", "result": self._finish(
                            query, state, budget, corpus, bundle, status="clarify", reason="missing_user_fact",
                            clarification="Bạn vui lòng làm rõ: " + "; ".join(missing_facts))}
                        return
                    reason = "insufficient_evidence"
                    break
                while True:
                    yield self._event(state, "verify", "Think · Đang kiểm chứng từng kết luận và trích dẫn…")
                    verification_payload = {**payload, "claims": [asdict(c) for c in claims],
                                            "followup_limit": self.config.followup_searches}
                    report = gateway.json("verify", prompts.VERIFY, verification_payload, reserve_calls=0)
                    verification_warnings = []
                    verdicts, coverage, quotes, verifier_queries = parse_verification(
                        report, state.requirements, claims, bundle, self.config.followup_searches, verification_warnings)
                    for warning in verification_warnings:
                        state.errors[warning] = "discarded"
                    facts_ok = report["facts_preserved"] and report["scope_respected"]
                    good = [claim for i, claim in enumerate(claims) if verdicts[i] and facts_ok]
                    # A reported covered requirement must also have a supported claim
                    # and supported dependencies, not just a model's boolean flag.
                    covered_by_claims = {rid for claim in good for rid in claim.requirement_ids}
                    checked_coverage = {r.id: bool(coverage[r.id] and r.id in covered_by_claims and r.id in supported)
                                        for r in state.requirements}
                    for r in state.requirements:
                        checked_coverage[r.id] &= all(checked_coverage[d] for d in r.depends_on)
                    good_quotes = {i: spans for i, spans in quotes.items() if verdicts[i] and facts_ok}
                    if good:
                        last_verified = {
                            "claims": good, "quotes": good_quotes, "coverage": checked_coverage,
                            "bundle": dict(bundle),
                        }
                    complete = all(checked_coverage.values()) and len(good) == len(claims)
                    if complete:
                        yield {"type": "result", "result": self._finish(
                            query, state, budget, corpus, bundle, status="answer", reason="complete",
                            claims=good, quotes=good_quotes, coverage=checked_coverage, verified=True)}
                        return
                    new_queries = [(rid, q) for rid, q in verifier_queries
                                   if " ".join(nfc(q).casefold().split()) not in state.searched]
                    if new_queries and can_fetch and budget.searches < self.config.max_searches and budget.can_finalize_after_search():
                        pending_queries, pending_xrefs = new_queries, []
                        reason = "verifier_requested_evidence"
                        break
                    if (not repair_used and len(good) < len(claims) and
                        budget.model_calls + 2 <= self.config.max_model_calls):
                        repair_used = True
                        payload["verification_errors"] = report
                        claims = parse_claims(gateway.json("repair", prompts.COMPOSE, payload, reserve_calls=1), state.requirements, bundle)
                        if claims:
                            continue
                        good = []
                    status = "partial" if good else "abstain"
                    if not good:
                        reason = "verification_rejected"
                    yield {"type": "result", "result": self._finish(
                        query, state, budget, corpus, bundle, status=status, reason=reason,
                        claims=good, quotes=good_quotes,
                        coverage=checked_coverage if good else {}, verified=bool(good))}
                    return
                # The verifier's follow-up consumes the same remaining rounds.
                continue
            if last_verified:
                safe = dict(last_verified)
                old_bundle = safe.pop("bundle")
                yield {"type": "result", "result": self._finish(
                    query, state, budget, corpus, old_bundle, status="partial", reason=reason, verified=True, **safe)}
            else:
                yield {"type": "result", "result": self._finish(
                    query, state, budget, corpus, bundle,
                    status="error" if reason == "tool_failure" else "abstain", reason=reason)}
        except (BudgetExceeded, CorpusChangedError, OutputError) as exc:
            state.errors["agent"] = type(exc).__name__
            if isinstance(exc, OutputError):
                state.errors["validation"] = str(exc)
            if isinstance(exc, BudgetExceeded) and last_verified:
                safe = dict(last_verified)
                old_bundle = safe.pop("bundle")
                yield {"type": "result", "result": self._finish(
                    query, state, budget, corpus, old_bundle, status="partial", reason=str(exc), verified=True, **safe)}
                return
            yield {"type": "result", "result": self._finish(
                query, state, budget, corpus, bundle, status="error",
                reason=str(exc) if isinstance(exc, BudgetExceeded) else type(exc).__name__)}
        except Exception as exc:
            # Do not expose SDK exception bodies/URLs/credentials to users.
            state.errors["agent"] = type(exc).__name__
            yield {"type": "result", "result": self._finish(
                query, state, budget, corpus, bundle, status="error", reason="tool_failure")}
