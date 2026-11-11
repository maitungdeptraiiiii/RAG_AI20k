"""Think trong chế độ Hỏi với hợp đồng (spec phần 4 §4.7).

`AgentPipeline` giữ nguyên vòng lặp (lập yêu cầu -> tìm nhiều vòng -> kiểm chứng trích dẫn -> trả lời); ở đây chỉ
thay "kho" nó đọc bằng `ContractAgentRetriever`, gộp 3 nguồn có nhãn:

    Hợp đồng: <file>                      đơn vị của hợp đồng (ĐÃ che PII); dẫn chiếu "Điều 4 của hợp đồng này" đi theo được
    Luật có phiên bản: <tên luật>         chunk kho có phiên bản HIỆU LỰC TẠI NGÀY KÝ (LegalRuntime đang lease)
    <tên file kho cũ>                     kho cũ, chưa xác định phiên bản

PII được che TRƯỚC khi vào agent (câu hỏi, lịch sử, hợp đồng — cùng MaskState của hợp đồng) và mở che ở đầu ra.
Hậu kiểm: câu trả lời không trích được căn cứ luật có phiên bản -> thêm cảnh báo và hạ "answer" xuống "partial".
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import date
from itertools import zip_longest
from typing import Any

from rag.agent import AgentConfig, AgentPipeline
from rag.contracts.llm_json import mask_payload, unmask_payload
from rag.contracts.models import Contract
from rag.index.bm25_index import BM25Index
from rag.quality.pii import mask_text
from rag.retrieve.hybrid import RetrievalResult
from rag.schema import Chunk, Hit

CONTRACT_PREFIX = "Hợp đồng: "
VERSIONED_PREFIX = "Luật có phiên bản: "
LEGAL_WARNING = ("Chưa có căn cứ luật có phiên bản tại ngày ký — các kết luận pháp lý (nếu có) chưa thể khẳng định. "
                 "Có thể upload luật ở trang Nạp văn bản pháp luật (/upload).")
NO_DATE_WARNING = "Hợp đồng chưa có ngày ký — chưa tra được luật có phiên bản; hãy nhập ngày ký trên thẻ hợp đồng."

LegacySearch = Callable[[str, int], list[Hit]]


class _NoDense:
    arm = "dense"

    def search(self, query: str, k: int) -> list[Hit]:
        return []


class ContractAgentRetriever:
    """Giao diện tối thiểu mà `AgentPipeline` dùng: capture_snapshot, search_candidates, arms, reranker, rerank_n."""

    revision = 1
    rerank_n = 10
    reranker = None

    def __init__(self, contract: Contract, runtime, legacy_chunks: Mapping[str, Chunk] | None,
                 legacy_search: LegacySearch | None) -> None:
        self.contract, self.runtime, self.legacy_search = contract, runtime, legacy_search
        self.anchor: date | None = contract.sign_date
        state = contract.mask_state
        doc = f"contract:{contract.contract_id}"
        self.contract_chunks = {}
        for u in contract.units:
            text = mask_text(u.text, state=state).masked_text
            first = text.split("\n", 1)[0].strip()
            self.contract_chunks[f"{doc}:{u.uid}"] = Chunk(f"{doc}:{u.uid}", doc, CONTRACT_PREFIX + contract.filename,
                                                           None, None, first, text)
        self.law_chunks: dict[str, Chunk] = {}
        if runtime is not None and self.anchor is not None:
            titles: dict[str, str] = {}
            for vc in runtime.index.chunks.values():
                if not (vc.valid_from <= self.anchor and (vc.valid_to is None or vc.valid_to > self.anchor)):
                    continue
                if vc.document_key not in titles:
                    d = runtime.service.store.document(vc.document_key)
                    titles[vc.document_key] = d.title if d is not None else vc.document_key
                self.law_chunks[vc.chunk_id] = Chunk(vc.chunk_id, vc.document_key, VERSIONED_PREFIX + titles[vc.document_key],
                                                     None, None, vc.section, vc.text)
        self.legacy_chunks = dict(legacy_chunks or {})
        self._chunks = {**self.legacy_chunks, **self.law_chunks, **self.contract_chunks}
        self._bm25 = BM25Index()
        self._bm25.build(list(self.contract_chunks.values()))
        self.arms = {"bm25": self._bm25, "dense": _NoDense()}

    @property
    def chunks(self) -> Mapping[str, Chunk]:
        return self._chunks

    def capture_snapshot(self) -> tuple[int, Mapping[str, Chunk]]:
        return self.revision, self._chunks

    def search_candidates(self, query: str, k: int = 20, *, revision: int, chunks: Mapping[str, Chunk],
                          mode: str = "hybrid", dense=None, reranker=None) -> RetrievalResult:
        errors: dict[str, str] = {}
        groups: list[list[str]] = [[h.chunk_id for h in self._bm25.search(query, k)]]
        if self.law_chunks:
            try:
                groups.append([vc.chunk_id for vc, _ in self.runtime.index.search(query, self.anchor, self.anchor, k)
                               if vc.chunk_id in self.law_chunks])
            except Exception as exc:  # noqa: BLE001 — một nguồn lỗi không làm hỏng cả lượt tìm
                errors["versioned"] = type(exc).__name__
        if self.legacy_search is not None:
            try:
                groups.append([h.chunk_id for h in self.legacy_search(query, k) if h.chunk_id in self.legacy_chunks])
            except Exception as exc:  # noqa: BLE001
                errors["legacy"] = type(exc).__name__
        order: list[str] = []
        for row in zip_longest(*groups):
            order.extend(cid for cid in row if cid and cid not in order)
        hits = [Hit(cid, 1.0 / i, i, "contract") for i, cid in enumerate(order[:max(k, 1) * 3], 1)]
        return RetrievalResult(query=query, mode="contract", candidates=hits, ranked=hits, hits=hits[:k],
                               errors=errors)


class AgentBaselineView:
    """Các thuộc tính của RAGPipeline mà AgentPipeline đọc, với retriever thay bằng kho hợp đồng."""

    def __init__(self, baseline, retriever: ContractAgentRetriever) -> None:
        self.retriever = retriever
        self.llm = baseline.llm
        self.condenser = baseline.condenser
        self.context_config = baseline.context_config
        self.top_k = baseline.top_k


def _postcheck(contract: Contract, data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    cited = {c.get("source", "") for c in data.get("citations") or []}
    if contract.sign_date is None:
        data["answer"] = f"{data.get('answer', '')}\n\n{NO_DATE_WARNING}"
        data["status"] = "partial" if data.get("status") == "answer" else data.get("status")
    elif data.get("status") in ("answer", "partial") and not any(s.startswith(VERSIONED_PREFIX) for s in cited):
        data["answer"] = f"{data.get('answer', '')}\n\n{LEGAL_WARNING}"
        if data.get("status") == "answer":
            data["status"] = "partial"
    data["contract_id"] = contract.contract_id
    data["anchor"] = contract.sign_date.isoformat() if contract.sign_date else None
    return data


def _with_context(contract: Contract, question: str) -> str:
    """Agent chỉ đọc câu hỏi: nói rõ đang hỏi về hợp đồng đính kèm (loại, các bên, ngày ký), để nó không hỏi ngược
    "hợp đồng gì?" và tìm đúng điều khoản trong nguồn "Hợp đồng"."""
    facts = contract.facts or {}
    roles = ", ".join(p.get("role", "") for p in facts.get("parties") or [] if p.get("role"))
    signed = contract.sign_date.strftime("%d/%m/%Y") if contract.sign_date else "chưa rõ"
    party = contract.party if contract.party and contract.party != "neutral" else "trung lập"
    return (f"[Câu hỏi về hợp đồng đính kèm \"{contract.filename}\": {facts.get('type') or 'hợp đồng'}"
            f"{'; các bên: ' + roles if roles else ''}; ngày ký {signed}; người hỏi: {party}] {question}")


def run_contract_agent(contract: Contract, baseline, config: AgentConfig | None, runtime,
                       legacy_chunks: Mapping[str, Chunk] | None, legacy_search: LegacySearch | None,
                       question: str, history: list[dict], *, stream: bool = False):
    state = contract.mask_state
    retriever = ContractAgentRetriever(contract, runtime, legacy_chunks, legacy_search)
    agent = AgentPipeline(AgentBaselineView(baseline, retriever), config or AgentConfig())
    masked_q = mask_text(_with_context(contract, question), state=state).masked_text
    masked_h = mask_payload([h for h in (history or []) if isinstance(h, dict)], state)

    if not stream:
        trace = agent.ask_debug(masked_q, history=masked_h)
        return _postcheck(contract, unmask_payload(trace.to_response(question), state))

    def events() -> Iterator[dict]:
        for event in agent.ask_stream(masked_q, history=masked_h):
            event = unmask_payload(event, state)
            if event.get("type") == "done":
                event = {"type": "done", **_postcheck(contract, {**event, "query": question})}
            yield event
    return events()
