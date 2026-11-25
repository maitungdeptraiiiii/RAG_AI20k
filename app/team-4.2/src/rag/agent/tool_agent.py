"""Tool-calling legal QA agent: the model picks the next tool from the question and observations.

Each step the model returns one action as JSON. Code validates the arguments,
runs the tool, charges the shared budget and appends the observation:

    search_law(query)                 semantic search, top new articles (excerpts)
    read_article(law_id, article)     exact lookup of one Điều by number
    follow_references(evidence_id)    read the articles an evidence article cites
    answer(claims) | ask_user(question) | refuse(reason)   terminal actions

An ``answer`` is accepted only after (1) every quote is located in its source
article (``find_soft_span``) and (2) one independent verifier call. Rejected
claims are returned to the loop as an observation, so the model itself decides
whether to search again or re-answer. Retrieved text is data, never instructions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

from rag.advanced.hyde import HydeRetriever
from rag.agent.adapters import bounded_dense, bounded_reranker
from rag.agent.contracts import AgentConfig, Budget, BudgetExceeded, ModelGateway, OutputError
from rag.agent.corpus import CorpusSnapshot
from rag.agent.orchestrator import AgentTrace
from rag.agent.prompts import RULES
from rag.agent.validation import find_soft_span
from rag.pipeline import RAGPipeline
from rag.retrieve.context import ContextSelection
from rag.retrieve.hybrid import CorpusChangedError, RetrievalResult
from rag.retrieve.merge import article_key
from rag.schema import Answer, Chunk, Citation, ContextBlock, Hit, nfc

PROMPT_VERSION = "tools-v4"
SCOPE_WARNING = "Câu trả lời dựa trên tài liệu trong kho; chưa xác nhận hiệu lực pháp luật hiện hành."

DECIDE = RULES + """
Bạn là agent tra cứu luật. Mỗi lượt chọn ĐÚNG MỘT hành động tiếp theo dựa trên câu hỏi và các quan sát trước đó.

Công cụ:
- search_law {"query": "..."}: tìm theo ngữ nghĩa trong kho, trả về vài Điều liên quan nhất (trích đoạn).
  Viết truy vấn tự đủ nghĩa bằng thuật ngữ pháp lý; không lặp truy vấn đã dùng.
- read_article {"law_id": "<law_id trong catalog>", "article": "<số Điều>"}: đọc toàn văn một Điều khi đã biết số Điều
  (do người dùng nêu hoặc do trích đoạn dẫn chiếu tới). Không đoán số Điều từ trí nhớ.
- follow_references {"evidence_id": "E3"}: đọc các Điều mà Điều E3 dẫn chiếu tới. Dùng khi trích đoạn trả lời có
  "theo quy định tại Điều...", "trừ trường hợp quy định tại...", mức/cách tính/điều kiện nằm ở Điều khác.

Hành động kết thúc:
- answer {"premise_check": null hoặc "...", "claims": [{"text": "...", "evidence": [{"id": "E1", "quote": "nguyên văn"}]}]}
- ask_user {"question": "..."}: CHỈ khi thiếu dữ kiện mà không thể trả lời kể cả theo từng trường hợp.
- refuse {"reason": "..."}: câu hỏi không phải về quy định pháp luật, hoặc không văn bản nào trong catalog điều chỉnh
  vấn đề được hỏi, hoặc đã tra cứu mà kho không có quy định đó. Không trả lời bằng quy định lân cận.

Cách làm:
- Xét catalog trước: nếu vấn đề rõ ràng nằm ngoài các văn bản trong catalog thì refuse ngay, không cần tìm.
- Trả lời đủ MỌI phần người dùng hỏi, không thêm phần không được hỏi.
- Áp dữ kiện người dùng vào quy định: tính thời hạn, mức tiền, so ngưỡng rồi KẾT LUẬN dứt khoát khi dữ kiện đủ.
  Chỉ nêu theo từng trường hợp khi dữ kiện quyết định thật sự thiếu. Hiểu dữ kiện người dùng theo nghĩa thông thường
  của tình huống; không đặt điều kiện lên cách diễn giải dữ kiện đã nêu.
- Đọc toàn văn (read_article) Điều mà câu trả lời dựa vào khi trích đoạn tìm kiếm bị cắt ([...]).
- Nếu câu hỏi khẳng định một quy định, kiểm tra nó; premise_check ghi tiền đề đó đúng/sai và claim đầu tiên nói rõ
  "Không đúng"/"Đúng" kèm quy định đúng.
- Mỗi claim nêu quy định làm căn cứ với đủ mốc, đơn vị và điều kiện đúng như văn bản (không rút gọn làm mất
  điều kiện), rồi áp vào dữ kiện người dùng để ra kết luận.
- Mỗi claim có evidence trỏ tới E đã quan sát và quote NGUYÊN VĂN, liên tục, lấy từ văn bản
  đã hiển thị của E đó (không ghép đoạn, không sửa chữ). Kết luận suy ra từ dữ kiện người dùng vẫn phải kèm quote
  của quy định làm tiền đề. Không tự chèn [1].
- Khi remaining_steps = 0 phải chọn answer, ask_user hoặc refuse.
- Nếu quan sát có verifier_feedback, sửa đúng các claim bị bác (tìm thêm nếu thiếu nguồn) rồi answer lại.
Chỉ xuất JSON: {"thought": "một câu ngắn", "action": "...", "args": {...}}
"""

VERIFY = RULES + """
Kiểm chứng độc lập từng claim với nguyên văn các Điều được trích và dữ kiện trong câu hỏi.
supported=true khi nội dung claim đúng với các Điều nó trích; kết luận áp quy định vào dữ kiện người dùng
(hiểu theo nghĩa thông thường của tình huống) được chấp nhận nếu phép suy luận đúng.
supported=false khi claim: mâu thuẫn với nguồn, sai số/ngày/mức, mất phủ định, sai đối tượng, tự thêm dữ kiện
người dùng không nêu, hoặc nguồn trích không chứa nội dung đó, hoặc bỏ qua một điều kiện/ngoại lệ mà dữ kiện
người dùng cho thấy rõ là đang áp dụng.
KHÔNG bác claim chỉ vì nó không liệt kê các ngoại lệ, trường hợp đặc thù hoặc chi tiết mà câu hỏi không đặt ra,
hoặc vì dữ kiện người dùng có thể được diễn giải khác đi. Không đòi thông tin ngoài phạm vi câu hỏi.
Trả đúng: {"claims": [{"index": 0, "supported": true, "reason": "ngắn"}]}
"""

ACTIONS = {"search_law", "read_article", "follow_references", "answer", "ask_user", "refuse"}


@dataclass
class ToolEvidence:
    id: str
    key: tuple[str, ...]
    chunk: Chunk                # whole article (merged chunks)
    chunk_ids: tuple[str, ...]
    shown: str                  # the text the model actually saw
    step: int
    origins: list[dict[str, Any]] = field(default_factory=list)
    depth: int = 0


@dataclass
class ToolState:
    evidence: dict[str, ToolEvidence] = field(default_factory=dict)
    by_key: dict[tuple[str, ...], str] = field(default_factory=dict)
    observations: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    searched: set[str] = field(default_factory=set)
    errors: dict[str, str] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


def _words(text: str, start: int, limit: int) -> tuple[str, bool]:
    words = list(re.finditer(r"\S+", text[start:]))
    if len(words) <= limit:
        return text[start:], start > 0
    return text[start:start + words[limit - 1].end()] + " [...]", True


def _loads(raw: str, stage: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1]
    start, end = raw.find("{"), raw.rfind("}")
    try:
        data = json.loads(raw[start:end + 1]) if start >= 0 else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise OutputError(f"Invalid JSON at {stage}")
    return data


def law_id(source: str) -> str:
    """Mã luật trong catalog: bỏ đuôi của tên file; tên văn bản (có "/" trong số hiệu) giữ nguyên."""
    path = Path(source)
    return path.stem if path.suffix.lower() in {".txt", ".md", ".pdf", ".docx", ".html"} else source


class ToolAgentPipeline:
    def __init__(self, baseline: RAGPipeline, config: AgentConfig | None = None, *,
                 max_steps: int = 6, search_k: int = 10, results_per_search: int = 4,
                 excerpt_words: int = 220, article_words: int = 900, max_refs: int = 4):
        self.baseline, self.retriever = baseline, baseline.retriever
        self.config = config or AgentConfig()
        self.max_steps, self.search_k, self.results_per_search = max_steps, search_k, results_per_search
        self.excerpt_words, self.article_words, self.max_refs = excerpt_words, article_words, max_refs

    # --- public API (same shape as AgentPipeline) ---------------------------------

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
            yield {"type": "sources", "sources": data["sources"]}
            yield {"type": "token", "delta": data["answer"]}
            yield {"type": "done", **data}

    # --- tools --------------------------------------------------------------------

    def _add(self, state, corpus, key, step, origin, *, focus: str | None = None, depth: int = 0):
        if key in state.by_key:
            ev = state.evidence[state.by_key[key]]
            ev.origins.append(origin)
            if origin["type"] != "search":
                # A search showed only an excerpt; an explicit read shows the article itself.
                full, _ = _words(ev.chunk.text, 0, self.article_words)
                if full != ev.shown:
                    ev.shown = full
                    return ev, True
            return ev, False
        chunk, ids = corpus.materialize(key)
        start = 0
        if focus:
            located = chunk.text.find(focus[:120])
            start = located if located > 0 else 0
        limit = self.excerpt_words if origin["type"] == "search" else self.article_words
        shown, _ = _words(chunk.text, start, limit)
        if start > 0:
            # Keep the article heading visible even when the window starts mid-article.
            shown = chunk.text.split("\n", 1)[0] + "\n[...] " + shown
        eid = f"E{len(state.evidence) + 1}"
        ev = ToolEvidence(eid, key, chunk, ids, shown, step, [origin], depth)
        state.evidence[eid], state.by_key[key] = ev, eid
        return ev, True

    @staticmethod
    def _view(ev: ToolEvidence) -> dict:
        return {"id": ev.id, "law_id": law_id(ev.chunk.source),
                "article": (ev.chunk.section or "").rsplit(" > ", 1)[-1], "text": ev.shown}

    def _search(self, state, corpus, step, args, ctx):
        query = nfc(str(args.get("query", ""))).strip()[:500]
        norm = " ".join(query.casefold().split())
        if not query:
            return {"error": "query rỗng"}
        if norm in state.searched:
            return {"error": "truy vấn đã dùng; hãy đổi truy vấn hoặc chọn hành động khác"}
        if ctx["budget"].searches >= self.config.max_searches:
            return {"error": "đã hết lượt tìm kiếm"}
        state.searched.add(norm)
        ctx["budget"].searches += 1
        result = self.retriever.search_candidates(
            query, self.search_k, revision=ctx["revision"], chunks=ctx["chunks"],
            mode=self.config.retrieval_mode, dense=ctx["dense"], reranker=ctx["reranker"])
        state.errors.update({f"s{ctx['budget'].searches}:{k}": v for k, v in result.errors.items()})
        new, known = [], []
        for hit in result.ranked:
            chunk = ctx["chunks"].get(hit.chunk_id)
            if chunk is None:
                continue
            key = article_key(chunk)
            if key in state.by_key:
                if state.by_key[key] not in known:
                    known.append(state.by_key[key])
                continue
            if len(new) >= self.results_per_search:
                continue
            ev, _ = self._add(state, corpus, key, step, {
                "type": "search", "query": query, "rank": hit.rank, "chunk_id": hit.chunk_id}, focus=chunk.text)
            new.append(self._view(ev))
        return {"results": new, "already_seen": known}

    def _read(self, state, corpus, step, args, ctx):
        wanted = str(args.get("law_id", "")).strip()
        number = re.sub(r"(?i)^\s*điều\s*", "", str(args.get("article", ""))).strip().rstrip(".").casefold()
        doc = ctx["catalog"].get(wanted)
        if doc is None:
            return {"error": f"law_id không có trong catalog: {wanted!r}"}
        key = corpus.articles.get((doc, number))
        if key is None:
            return {"error": f"không tìm thấy Điều {number} trong {wanted}"}
        ev, fresh = self._add(state, corpus, key, step, {"type": "read_article", "law_id": wanted, "article": number})
        return {"results": [self._view(ev)] if fresh else [], "already_seen": [] if fresh else [ev.id]}

    def _follow(self, state, corpus, step, args, ctx):
        eid = str(args.get("evidence_id", "")).strip()
        source = state.evidence.get(eid)
        if source is None:
            return {"error": f"không có evidence {eid!r}"}
        new, known, skipped = [], [], 0
        for edge in corpus.xrefs(source.key):
            if edge.status != "resolved" or edge.target_key is None or edge.target_key == source.key:
                skipped += edge.status != "resolved"
                continue
            if edge.target_key in state.by_key:
                if state.by_key[edge.target_key] not in known:
                    known.append(state.by_key[edge.target_key])
                continue
            if len(new) >= self.max_refs or ctx["budget"].xref_targets >= self.config.max_xref_targets:
                break
            ctx["budget"].xref_targets += 1
            ev, _ = self._add(state, corpus, edge.target_key, step, {
                "type": "follow_references", "from_evidence": eid, "reference": edge.quote[:200]},
                depth=source.depth + 1)
            new.append({**self._view(ev), "cited_as": edge.quote[:200]})
        out = {"results": new, "already_seen": known}
        if skipped:
            out["unresolved_references"] = skipped
        if not new and not known:
            out["note"] = "Điều này không có dẫn chiếu đọc được trong kho"
        return out

    # --- answer validation ----------------------------------------------------------

    def _parse_claims(self, state, args):
        claims, rejected = [], []
        for i, row in enumerate((args.get("claims") or [])[:20] if isinstance(args.get("claims"), list) else []):
            if not isinstance(row, dict):
                continue
            content = nfc(str(row.get("text", ""))).strip()
            content = re.sub(r"\s*\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]", "", content)
            if not content or re.search(r"<\s*/?\s*[a-zA-Z]|!\[|javascript\s*:", content, re.I):
                continue
            spans, bad = {}, []
            for ev_row in row.get("evidence") or []:
                if not isinstance(ev_row, dict):
                    continue
                eid, quote = str(ev_row.get("id", "")), str(ev_row.get("quote", ""))
                ev = state.evidence.get(eid)
                span = find_soft_span(quote, ev.chunk.text) if ev else None
                if span is None:
                    bad.append(eid)
                    continue
                a, b = span
                if eid in spans:      # several clauses of one article: keep the enclosing original span
                    a, b = min(a, spans[eid][0]), max(b, spans[eid][1])
                spans[eid] = (a, b)
            if not spans:
                rejected.append({"index": i, "text": content[:300],
                                 "reason": "không có quote nguyên văn nào khớp nguồn" + (f" ({', '.join(bad)})" if bad else "")})
                continue
            claims.append({"text": content, "spans": spans})
        return claims, rejected

    def _verify(self, gateway, query, state, claims):
        cited = list(dict.fromkeys(eid for c in claims for eid in c["spans"]))
        payload = {
            "question": query,
            "articles": [{"id": eid, "article": state.evidence[eid].chunk.section,
                          "text": _words(state.evidence[eid].chunk.text, 0, self.article_words)[0]} for eid in cited],
            "claims": [{"index": i, "text": c["text"],
                        "quotes": {eid: state.evidence[eid].chunk.text[a:b] for eid, (a, b) in c["spans"].items()}}
                       for i, c in enumerate(claims)],
        }
        data = _loads(gateway.call("verify", VERIFY, json.dumps(payload, ensure_ascii=False), reserve_calls=0), "verify")
        verdicts = {}
        for row in data.get("claims") or []:
            if isinstance(row, dict) and type(row.get("index")) is int and type(row.get("supported")) is bool:
                verdicts[row["index"]] = (row["supported"], str(row.get("reason", ""))[:300])
        # A claim the verifier did not judge is not verified.
        return [verdicts.get(i, (False, "verifier không đánh giá")) for i in range(len(claims))]

    # --- loop -----------------------------------------------------------------------

    def _compact(self, observations):
        """Fit the input limit: shorten the oldest excerpts first; ids/quotes stay checkable
        against the full article, so a shortened view never weakens verification."""
        limit = int(self.config.max_input_chars * 0.75) - len(DECIDE)
        obs = json.loads(json.dumps(observations, ensure_ascii=False))
        rows = [r for o in obs for r in o.get("results", [])]
        for row in rows:
            if len(json.dumps(obs, ensure_ascii=False)) <= limit:
                break
            short, cut = _words(row["text"], 0, 60)
            if cut:
                row["text"], row["shortened"] = short, True
        return obs

    def _event(self, state, stage, message, **payload):
        event = {"type": "progress", "stage": stage, "message": message,
                 "sequence": len(state.events) + 1, **payload}
        state.events.append(event)
        return event

    def run_events(self, raw_query: str, *, history=None) -> Iterator[dict]:
        state, budget = ToolState(), Budget(self.config)
        gateway = ModelGateway(self.baseline.llm, budget, "decide")
        query = nfc(raw_query).strip()
        if not query or len(query) > 8000:
            raise ValueError("Agent query must contain 1–8000 characters")
        history = [{"query": str(h.get("query", ""))[:2000],
                    "assistant_context_unverified": str(h.get("answer", ""))[:250]}
                   for h in (history or [])[-3:] if isinstance(h, dict)]
        corpus = None
        verified_claims: list[dict] = []
        reason, answers_tried = "max_steps", 0
        try:
            revision, chunks = self.retriever.capture_snapshot()
            corpus = CorpusSnapshot(revision, chunks)
            catalog = {}
            for chunk in chunks.values():
                catalog.setdefault(law_id(chunk.source), chunk.doc_id)
            dense = self.retriever.arms["dense"]
            if isinstance(dense, HydeRetriever):
                dense = dense.dense    # the agent writes its own search queries
            ctx = {"revision": revision, "chunks": chunks, "catalog": catalog, "budget": budget,
                   "dense": bounded_dense(dense, budget), "reranker": bounded_reranker(self.retriever.reranker, budget)}
            tools = {"search_law": self._search, "read_article": self._read, "follow_references": self._follow}
            yield self._event(state, "prepare", "Think · Đang phân tích câu hỏi…")
            for step in range(1, self.max_steps + 3):
                budget.check()
                budget.rounds = step
                remaining = max(0, self.max_steps - step + 1)
                payload = {"question": query, "history": history, "catalog": sorted(catalog),
                           "remaining_steps": remaining, "searched_queries": sorted(state.searched),
                           "observations": self._compact(state.observations)}
                try:
                    decision = _loads(gateway.call("decide", DECIDE, json.dumps(payload, ensure_ascii=False),
                                                   reserve_calls=1), "decide")
                except OutputError as exc:
                    state.errors[f"decide_{step}"] = str(exc)[:200]
                    state.observations.append({"step": step, "error": "đầu ra không phải JSON hợp lệ; trả đúng định dạng"})
                    continue
                action = decision.get("action")
                args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
                if action not in ACTIONS or (remaining == 0 and action in tools):
                    state.observations.append({"step": step, "action": action,
                                               "error": "hành động không hợp lệ ở bước này"})
                    continue
                call = {"step": step, "action": action, "thought": str(decision.get("thought", ""))[:300],
                        "args": {k: v for k, v in args.items() if k != "claims"}}
                state.tool_calls.append(call)
                if action in tools:
                    yield self._event(state, action, f"Think · {action}: {json.dumps(call['args'], ensure_ascii=False)[:120]}")
                    try:
                        result = tools[action](state, corpus, step, args, ctx)
                    except (BudgetExceeded, CorpusChangedError):
                        raise
                    except Exception as exc:
                        state.errors[f"{action}_{step}"] = type(exc).__name__
                        result = {"error": f"công cụ lỗi ({type(exc).__name__})"}
                    call["result_ids"] = [r["id"] for r in result.get("results", [])]
                    call["seen_ids"] = list(result.get("already_seen", []))
                    if "error" in result:
                        call["error"] = str(result["error"])[:300]
                    state.observations.append({"step": step, "action": action, "args": call["args"], **result})
                    continue
                if action == "ask_user":
                    question = nfc(str(args.get("question", ""))).strip()[:1000] or "Bạn vui lòng bổ sung dữ kiện còn thiếu."
                    yield {"type": "result", "result": self._finish(query, state, budget, corpus, "clarify",
                                                                    "ask_user", text=question)}
                    return
                if action == "refuse":
                    call["reason"] = str(args.get("reason", ""))[:300]
                    yield {"type": "result", "result": self._finish(query, state, budget, corpus, "refused", "refuse")}
                    return
                # answer
                answers_tried += 1
                yield self._event(state, "verify", "Think · Đang kiểm chứng từng kết luận và trích dẫn…")
                claims, rejected = self._parse_claims(state, args)
                feedback = list(rejected)
                good = []
                if claims:
                    try:
                        verdicts = self._verify(gateway, query, state, claims)
                    except OutputError as exc:
                        state.errors[f"verify_{step}"] = str(exc)[:200]
                        verdicts = [(False, "verifier lỗi định dạng")] * len(claims)
                    for i, (claim, (ok, why)) in enumerate(zip(claims, verdicts)):
                        if ok:
                            good.append(claim)
                        else:
                            feedback.append({"text": claim["text"][:300], "reason": why})
                if good:
                    verified_claims = good
                call["claims"] = {"proposed": len(claims) + len(rejected), "verified": len(good)}
                call["feedback"] = feedback
                can_retry = (answers_tried < 2 and step < self.max_steps + 2 and
                             budget.model_calls + 2 <= self.config.max_model_calls)
                if not feedback or not can_retry:
                    if good:
                        yield {"type": "result", "result": self._finish(
                            query, state, budget, corpus, "answer" if not feedback else "partial",
                            "verified" if not feedback else "verified_subset", claims=good)}
                    else:
                        yield {"type": "result", "result": self._finish(query, state, budget, corpus,
                                                                        "abstain", "verification_rejected")}
                    return
                state.observations.append({"step": step, "action": "answer", "verifier_feedback": feedback,
                                           "accepted_claims": [c["text"][:300] for c in good]})
            reason = "max_steps"
        except BudgetExceeded as exc:
            reason = str(exc)
            state.errors["agent"] = "BudgetExceeded"
        except CorpusChangedError:
            yield {"type": "result", "result": self._finish(query, state, budget, corpus, "error", "corpus_changed")}
            return
        except Exception as exc:   # never expose SDK bodies/URLs
            reason = f"tool_failure:{type(exc).__name__}"
            state.errors["agent"] = type(exc).__name__
        if verified_claims:
            yield {"type": "result", "result": self._finish(query, state, budget, corpus, "partial", reason,
                                                            claims=verified_claims)}
        else:
            yield {"type": "result", "result": self._finish(
                query, state, budget, corpus, "error" if reason.startswith("tool_failure") else "abstain", reason)}

    # --- result -----------------------------------------------------------------------

    def _finish(self, query, state, budget, corpus, status, reason, *, claims=(), text=None):
        order = list(dict.fromkeys(eid for c in claims for eid in c["spans"]))
        numbered = {eid: n for n, eid in enumerate(order, 1)}
        blocks, citations = [], []
        for eid in order:
            ev = state.evidence[eid]
            a = min(c["spans"][eid][0] for c in claims if eid in c["spans"])
            b = max(c["spans"][eid][1] for c in claims if eid in c["spans"])
            block = ContextBlock(numbered[eid], ev.chunk)
            blocks.append(block)
            citations.append(Citation.from_block(block, quote=ev.chunk.text[a:b]))
        if claims:
            body = "\n\n".join(c["text"] + " " + "".join(f"[{numbered[e]}]" for e in c["spans"]) for c in claims)
            answer = Answer(body, citations, False)
        elif status == "clarify":
            answer = Answer(text or "Bạn vui lòng bổ sung dữ kiện còn thiếu.", [], False)
        elif status == "error":
            answer = Answer("Chưa thể kiểm chứng câu trả lời lúc này. Bạn có thể thử lại hoặc tắt Think để tra cứu thông thường.", [], False)
        else:
            answer = Answer.refusal()
        hits = [Hit(ev.chunk.chunk_id, 0.0, i, "agent", ev.chunk_ids[1:])
                for i, ev in enumerate(state.evidence.values(), 1)]
        retrieval = RetrievalResult(query=query, mode="agent", candidates=hits, ranked=hits,
                                    hits=hits[:self.baseline.top_k], errors=dict(state.errors),
                                    queries=sorted(state.searched), selection_policy="agent_tools")
        answer.hits = retrieval.hits
        metadata = {
            "version": PROMPT_VERSION, "impl": "tools", "scope": "snapshot_only", "scope_warning": SCOPE_WARNING,
            "snapshot_id": corpus.id if corpus else None, "status": status, "stop_reason": reason,
            "verified": bool(claims), "budget": budget.summary(), "tool_calls": state.tool_calls,
            "requirements": [], "unresolved_requirements": [],
            "evidence": [{"id": ev.id, "law": ev.chunk.source,
                          "article": (ev.chunk.section or "").rsplit(" > ", 1)[-1],
                          "chunk_ids": list(ev.chunk_ids), "unit_key": list(ev.key),
                          "round": ev.step, "xref_depth": ev.depth, "origins": ev.origins}
                         for ev in state.evidence.values()],
            "claims": [{"text": c["text"], "evidence_ids": list(c["spans"])} for c in claims],
            "events": list(state.events),
        }
        return AgentTrace(answer=answer, retrieval=retrieval,
                          context=ContextSelection(blocks, "fixed" if blocks else "empty"),
                          llm_called=budget.model_calls > 0, condensed_query=query, agent=metadata, status=status)
