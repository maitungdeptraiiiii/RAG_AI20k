"""RAGPipeline: ingest(path/url) và ask(query) — TV5.

    pipeline = RAGPipeline.from_settings(Settings.load())
    report   = pipeline.ingest("data/team-4.2/raw/luat_dat_dai.pdf")
    answer   = pipeline.ask("Thời hiệu khởi kiện là bao lâu?")
    trace    = pipeline.ask_debug("...")     # kèm RetrievalResult + ContextSelection cho UI / eval

Luồng ingest:
    load -> chunk_document -> [index_enhancers của phương pháp nâng cao] -> index -> ChunkStore
Luồng ask:
    HybridRetriever.retrieve (BM25 + Dense [HyDE nếu bật] + arm nâng cao) -> select_context
    -> (context rỗng: từ chối, không gọi LLM) -> generate -> build_citations -> Answer

Phương pháp nâng cao (HyDE, Contextual Retrieval, ...) gắn qua src/rag/advanced/, bật bằng ADVANCED;
pipeline không cần sửa khi thêm/bỏ phương pháp.

CHƯA có guardrail (TV5 làm sau): ngưỡng điểm RRF trước LLM, loại [n] sai / từ chối khi không còn
citation hợp lệ sau LLM. Hai điểm chặn được đánh dấu `# GUARDRAIL` trong `ask_debug`.
Riêng trường hợp context rỗng thì trả câu từ chối ngay vì không có gì để đưa cho LLM.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag.advanced.condense import QueryCondenser
from rag.config import Settings
from rag.generate.answer import answer_question, build_citations, build_prompt
from rag.index.bm25_index import BM25Index
from rag.index.embedder import EmbeddingCache, make_embedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.ingest.chunker import chunk_document
from rag.ingest.loaders import load_source
from rag.retrieve.context import ContextConfig, ContextSelection, select_context
from rag.retrieve.hybrid import HybridRetriever, Mode, RetrievalResult
from rag.retrieve.rerank import make_reranker
from rag.schema import REFUSAL, LLM, Answer, Page, nfc

log = logging.getLogger(__name__)


class IndexConfigMismatchError(RuntimeError):
    """Index trên đĩa được build với cấu hình index khác (chunk size, embedding, phương pháp lúc index)."""


@dataclass
class IngestReport:
    doc_id: str
    source: str
    n_pages: int
    empty_pages: list[int] = field(default_factory=list)
    n_chunks: int = 0
    skipped: bool = False          # tài liệu đã ingest trước đó (cùng doc_id)


@dataclass
class AskTrace:
    answer: Answer
    retrieval: RetrievalResult
    context: ContextSelection
    llm_called: bool
    condensed_query: str | None = None


def index_signature(settings: Settings, index_enhancers: Sequence[str]) -> dict[str, Any]:
    """Những gì quyết định nội dung index. Khác nhau -> phải index lại."""
    return {
        "embed_model": settings.embed_model,
        "embed_dim": settings.embed_dim,
        "max_syllables": settings.max_syllables,
        "index_enhancers": list(index_enhancers),
    }


def check_index_config(path: Path, signature: dict[str, Any]) -> None:
    if path.exists():
        have = json.loads(path.read_text(encoding="utf-8"))
        if have != signature:
            raise IndexConfigMismatchError(
                f"Index tại {path.parent} được build với {have}, cấu hình hiện tại là {signature}. "
                "Đổi DATA_DIR sang thư mục mới (vd. để so sánh ablation) hoặc xoá "
                "indexes/ và processed/ trong DATA_DIR rồi ingest lại."
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding="utf-8")


class RAGPipeline:
    def __init__(
        self,
        store: ChunkStore,
        retriever: HybridRetriever,
        llm: LLM,
        *,
        top_k: int = 5,
        max_syllables: int = 300,
        context: ContextConfig | None = None,
        index_enhancers: Sequence[Any] = (),
        loader: Callable[..., list[Page]] = load_source,
        condenser: QueryCondenser | None = None,
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k
        self.max_syllables = max_syllables
        self.context_config = context or ContextConfig(fixed_k=top_k)
        self.index_enhancers = list(index_enhancers)
        self._loader = loader
        self.condenser = condenser or QueryCondenser(llm)
        if len(store):
            # khởi động lại: dựng BM25 trong RAM, Qdrant bỏ qua chunk đã có; chunk đã lưu kèm context
            self.retriever.build(store.all())

    @classmethod
    def from_settings(cls, s: Settings, *, llm: LLM | None = None) -> RAGPipeline:
        from rag.advanced import Components, build_enhancements
        from rag.generate.llm import LLMCache, OpenAIChatLLM
        from rag.retrieve.coverage import CoverageConfig
        from rag.retrieve.listwise import ListwiseConfig, ListwiseSelector

        llm = llm or OpenAIChatLLM(
            s.llm_model,
            temperature=s.llm_temperature,
            base_url=s.llm_base_url,
            api_key=s.llm_api_key,
            cache=LLMCache(s.cache_dir / "llm.sqlite"),
        )
        embedder = make_embedder(
            s.embed_model, s.embed_dim, cache=EmbeddingCache(s.cache_dir / "embeddings.sqlite"),
            jina_api_key=s.jina_api_key,
        )
        dense = VectorIndex.open_qdrant(s.vector_dir, embedder)   # mở index có sẵn không ghi gì
        enhancements = build_enhancements(
            s.advanced_methods, Components(settings=s, llm=llm, embedder=embedder, dense=dense)
        )
        index_enhancers = [e.index_enhancer for e in enhancements if e.index_enhancer is not None]
        # kiểm tra TRƯỚC khi đọc chunks.jsonl và index thêm: index cũ phải cùng cấu hình
        check_index_config(s.index_config_path, index_signature(s, [e.name for e in index_enhancers]))

        extra_arms = {name: arm for e in enhancements for name, arm in e.arms.items()}
        dense_arm = dense
        for e in enhancements:            # vd. HyDE: arm Dense tìm bằng (câu hỏi + đoạn giả)
            if e.wrap_dense is not None:
                dense_arm = e.wrap_dense(dense_arm)
        retriever = HybridRetriever(
            BM25Index(),
            dense_arm,
            extra_arms=extra_arms,
            reranker=make_reranker(s.rerank_backend, cache_path=s.cache_dir / "rerank.sqlite"),
            arm_k=s.arm_k,
            rrf_k=s.rrf_k,
            rerank_n=s.rerank_n,
            merge_articles=s.merge_articles,
            article_pool_factor=s.article_pool_factor,
            bm25_rrf_weight=s.bm25_rrf_weight,
            rewrite_for_rerank=s.rewrite_for_rerank,
            coverage=(CoverageConfig(s.coverage_anchor_k,s.coverage_min_p,s.coverage_weight,s.coverage_branch_k)
                      if s.coverage_enabled else None),
            listwise=(ListwiseSelector(
                OpenAIChatLLM(
                    s.listwise_model,
                    temperature=0.0,
                    base_url=s.llm_base_url,
                    api_key=s.llm_api_key,
                    cache=LLMCache(s.cache_dir / "listwise_llm.sqlite"),
                ),
                ListwiseConfig(s.listwise_candidate_n, s.listwise_margin, s.listwise_min_p, s.listwise_excerpt_words)
            ) if s.listwise_enabled else None),
        )
        if s.query_rewrite_enabled:
            from rag.advanced.rewrite import QueryRewriter

            retriever.rewriter = QueryRewriter(llm)
        if s.decomp_enabled:
            from rag.advanced.decomposition import QueryDecomposer

            retriever.decomposer = QueryDecomposer(
                llm, s.decomp_max_subqueries, s.decomp_include_original,
                s.decomp_per_query_k, s.decomp_pool_size,
                s.decomp_max_new_articles,
            )
        context = ContextConfig(
            min_p=s.context_min_p,
            max_blocks=s.context_max_blocks,
            max_words=s.context_max_words,
            fixed_k=s.top_k,
        )
        log.info("Phương pháp nâng cao: %s", [e.name for e in enhancements] or "không (baseline)")
        condenser_llm = OpenAIChatLLM(
            s.condense_model,
            temperature=0.0,
            base_url=s.llm_base_url,
            api_key=s.llm_api_key,
            cache=LLMCache(s.cache_dir / "condense_llm.sqlite"),
        )
        return cls(
            ChunkStore(s.chunks_path), retriever, llm,
            top_k=s.top_k, max_syllables=s.max_syllables, context=context,
            index_enhancers=index_enhancers,
            condenser=QueryCondenser(condenser_llm),
        )

    # --- ingest ----------------------------------------------------------------

    def ingest(self, path_or_url: str | Path, *, source: str | None = None) -> IngestReport:
        """Parse -> chunk -> (bối cảnh nâng cao) -> index -> lưu. Cùng tài liệu ingest lại thì bỏ qua."""
        pages = self._loader(path_or_url, source=source) if source else self._loader(path_or_url)
        if not pages:
            raise ValueError(f"Không đọc được nội dung: {path_or_url}")
        report = IngestReport(
            doc_id=pages[0].doc_id,
            source=pages[0].source,
            n_pages=len(pages),
            empty_pages=[p.page for p in pages if p.is_empty and p.page is not None],
        )
        if self.store.has_doc(report.doc_id):
            report.skipped = True
            report.n_chunks = len(self.store.by_doc(report.doc_id))
            return report

        chunks = chunk_document(pages, max_syllables=self.max_syllables)
        if not chunks:
            raise ValueError(f"{report.source}: không có text để index (PDF scan cần OCR?)")
        for enhancer in self.index_enhancers:
            enriched = enhancer.enrich(chunks, pages)
            if [c.chunk_id for c in enriched] != [c.chunk_id for c in chunks]:
                raise RuntimeError(f"{enhancer.name}: phải trả đúng các chunk đầu vào, cùng thứ tự")
            chunks = enriched
        self.retriever.build(chunks)          # index trước, lưu sau: index lỗi thì không ghi store
        self.store.add(chunks)
        report.n_chunks = len(chunks)
        log.info("Ingest %s: %d trang, %d chunk", report.source, report.n_pages, report.n_chunks)
        return report

    # --- ask -------------------------------------------------------------------

    def ask_debug(
        self,
        query: str,
        *,
        history: Sequence[dict[str, Any]] | None = None,
        mode: Mode = "hybrid",
        arms: Sequence[str] | None = None,
        rerank: bool = True,
    ) -> AskTrace:
        effective_query = (
            self.condenser.condense(query, history=history)
            if hasattr(self, "condenser") and self.condenser
            else query
        )
        retrieval = self.retriever.retrieve(effective_query, self.top_k, mode=mode, arms=arms, rerank=rerank)
        selection = select_context(retrieval.ranked, self.retriever.chunks, self.context_config)

        # GUARDRAIL (trước LLM, TV5): chặn theo ngưỡng điểm RRF khi không rerank — chưa làm.
        if selection.empty:
            return AskTrace(
                Answer.refusal(retrieval.hits),
                retrieval,
                selection,
                llm_called=False,
                condensed_query=effective_query,
            )

        answer = answer_question(effective_query, selection.blocks, self.llm, retrieval.hits)
        # GUARDRAIL (sau LLM, TV5): loại [n] sai, không còn citation hợp lệ thì từ chối — chưa làm.
        return AskTrace(
            answer,
            retrieval,
            selection,
            llm_called=True,
            condensed_query=effective_query,
        )

    def ask(self, query: str, *, history: Sequence[dict[str, Any]] | None = None) -> Answer:
        return self.ask_debug(query, history=history).answer

    def ask_stream(
        self,
        query: str,
        *,
        history: Sequence[dict[str, Any]] | None = None,
        mode: Mode = "hybrid",
        arms: Sequence[str] | None = None,
        rerank: bool = True,
    ) -> Iterator[dict[str, Any]]:
        effective_query = (
            self.condenser.condense(query, history=history)
            if hasattr(self, "condenser") and self.condenser
            else query
        )
        retrieval = self.retriever.retrieve(effective_query, self.top_k, mode=mode, arms=arms, rerank=rerank)
        selection = select_context(retrieval.ranked, self.retriever.chunks, self.context_config)

        if selection.empty:
            yield {
                "type": "done",
                "answer": REFUSAL,
                "refused": True,
                "citations": [],
                "sources": [],
                "trace": {
                    "condensed_query": effective_query,
                    "context_mode": selection.mode,
                    "n_context_blocks": 0,
                    "reranked": retrieval.reranked,
                    "errors": retrieval.errors,
                },
            }
            return

        chunks = self.retriever.chunks
        scores_map = {h.chunk_id: round(float(h.score), 4) for h in retrieval.ranked}
        sources = []
        for b in selection.blocks:
            c = b.chunk
            sources.append({
                "n": b.n,
                "chunk_id": c.chunk_id,
                "source": c.source,
                "section": c.section or "Không có tiêu đề",
                "page": c.page_start,
                "score": scores_map.get(c.chunk_id, 0.0),
                "text": c.text,
            })

        # Yield sources right after retrieval so UI can show them immediately
        yield {
            "type": "sources",
            "sources": sources,
            "condensed_query": effective_query,
        }

        # Build prompt
        system, user = build_prompt(effective_query, selection.blocks)
        collected: list[str] = []

        if hasattr(self.llm, "stream"):
            for delta in self.llm.stream(system, user):
                collected.append(delta)
                yield {"type": "token", "delta": delta}
        else:
            text = self.llm.complete(system, user)
            collected.append(text)
            yield {"type": "token", "delta": text}

        full_text = nfc("".join(collected)).strip()
        answer = build_citations(full_text, selection.blocks, retrieval.hits)

        citations_data = []
        for c in answer.citations:
            chunk_obj = chunks.get(c.chunk_id)
            citations_data.append({
                "n": c.n,
                "chunk_id": c.chunk_id,
                "source": c.source,
                "section": chunk_obj.section if chunk_obj else "Căn cứ pháp lý",
                "page": c.page,
                "quote": c.quote,
                "score": scores_map.get(c.chunk_id, 0.0),
                "text": chunk_obj.text if chunk_obj else "",
            })

        arms_data = {}
        for arm_name, arm_hits in retrieval.arms.items():
            rows = []
            for h in arm_hits[:5]:
                c = chunks.get(h.chunk_id)
                rows.append({
                    "rank": h.rank,
                    "score": round(float(h.score), 4),
                    "source": c.source if c else "",
                    "section": c.section if c else "",
                    "page": c.page_start if c else None,
                    "text": " ".join(c.text.split())[:180] if c else "",
                })
            arms_data[arm_name] = rows

        final_hits = []
        for h in retrieval.hits[:5]:
            c = chunks.get(h.chunk_id)
            final_hits.append({
                "rank": h.rank,
                "score": round(float(h.score), 4),
                "source": c.source if c else "",
                "section": c.section if c else "",
                "page": c.page_start if c else None,
                "text": " ".join(c.text.split())[:180] if c else "",
            })

        yield {
            "type": "done",
            "answer": answer.text,
            "refused": answer.refused,
            "citations": citations_data,
            "sources": sources,
            "trace": {
                "context_mode": selection.mode,
                "n_context_blocks": len(selection.blocks),
                "condensed_query": effective_query,
                "reranked": retrieval.reranked,
                "errors": retrieval.errors,
                "arms": arms_data,
                "final_hits": final_hits,
            },
        }


__all__ = ["AskTrace", "IndexConfigMismatchError", "IngestReport", "RAGPipeline", "check_index_config",
           "index_signature"]
