"""RAGPipeline: ingest(path/url) và ask(query) — TV5.

    pipeline = RAGPipeline.from_settings(Settings.load())
    report   = pipeline.ingest("data/team-4.2/raw/luat_dat_dai.pdf")
    answer   = pipeline.ask("Thời hiệu khởi kiện là bao lâu?")
    trace    = pipeline.ask_debug("...")     # kèm RetrievalResult + ContextSelection cho UI / eval

Luồng ask:
    HybridRetriever.retrieve -> select_context -> (context rỗng: từ chối, không gọi LLM)
    -> generate -> build_citations -> Answer

CHƯA có guardrail (TV5 làm sau): ngưỡng điểm RRF trước LLM, loại [n] sai / từ chối khi không còn
citation hợp lệ sau LLM. Hai điểm chặn được đánh dấu `# GUARDRAIL` trong `ask_debug`.
Riêng trường hợp context rỗng thì trả câu từ chối ngay vì không có gì để đưa cho LLM.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rag.config import Settings
from rag.generate.answer import answer_question
from rag.index.bm25_index import BM25Index
from rag.index.embedder import EmbeddingCache, OpenAIEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.ingest.chunker import chunk_document
from rag.ingest.loaders import load_source
from rag.retrieve.context import ContextConfig, ContextSelection, select_context
from rag.retrieve.hybrid import HybridRetriever, Mode, RetrievalResult
from rag.retrieve.rerank import make_reranker
from rag.schema import LLM, Answer, Page

log = logging.getLogger(__name__)


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
        loader: Callable[..., list[Page]] = load_source,
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k
        self.max_syllables = max_syllables
        self.context_config = context or ContextConfig(fixed_k=top_k)
        self._loader = loader
        if len(store):
            # khởi động lại: dựng BM25 trong RAM, Qdrant bỏ qua chunk đã có
            self.retriever.build(store.all())

    @classmethod
    def from_settings(cls, s: Settings, *, llm: LLM | None = None) -> RAGPipeline:
        from rag.generate.llm import LLMCache, OpenAIChatLLM

        embedder = OpenAIEmbedder(
            s.embed_model, s.embed_dim, cache=EmbeddingCache(s.cache_dir / "embeddings.sqlite")
        )
        retriever = HybridRetriever(
            BM25Index(),
            VectorIndex.open_qdrant(s.vector_dir, embedder),
            reranker=make_reranker(s.rerank_backend, cache_path=s.cache_dir / "rerank.sqlite"),
            arm_k=s.arm_k,
            rrf_k=s.rrf_k,
            rerank_n=s.rerank_n,
        )
        llm = llm or OpenAIChatLLM(
            s.llm_model,
            temperature=s.llm_temperature,
            base_url=s.llm_base_url,
            api_key=s.llm_api_key,
            cache=LLMCache(s.cache_dir / "llm.sqlite"),
        )
        context = ContextConfig(
            min_p=s.context_min_p,
            max_blocks=s.context_max_blocks,
            max_words=s.context_max_words,
            fixed_k=s.top_k,
        )
        return cls(
            ChunkStore(s.chunks_path), retriever, llm,
            top_k=s.top_k, max_syllables=s.max_syllables, context=context,
        )

    # --- ingest ----------------------------------------------------------------

    def ingest(self, path_or_url: str | Path, *, source: str | None = None) -> IngestReport:
        """Parse -> chunk -> lưu -> index. Cùng tài liệu ingest lại thì bỏ qua."""
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
        self.retriever.build(chunks)          # index trước, lưu sau: index lỗi thì không ghi store
        self.store.add(chunks)
        report.n_chunks = len(chunks)
        log.info("Ingest %s: %d trang, %d chunk", report.source, report.n_pages, report.n_chunks)
        return report

    # --- ask -------------------------------------------------------------------

    def ask_debug(self, query: str, *, mode: Mode = "hybrid", rerank: bool = True) -> AskTrace:
        retrieval = self.retriever.retrieve(query, self.top_k, mode=mode, rerank=rerank)
        selection = select_context(retrieval.ranked, self.retriever.chunks, self.context_config)

        # GUARDRAIL (trước LLM, TV5): chặn theo ngưỡng điểm RRF khi không rerank — chưa làm.
        if selection.empty:
            return AskTrace(Answer.refusal(retrieval.hits), retrieval, selection, llm_called=False)

        answer = answer_question(retrieval.query, selection.blocks, self.llm, retrieval.hits)
        # GUARDRAIL (sau LLM, TV5): loại [n] sai, không còn citation hợp lệ thì từ chối — chưa làm.
        return AskTrace(answer, retrieval, selection, llm_called=True)

    def ask(self, query: str) -> Answer:
        return self.ask_debug(query).answer


__all__ = ["AskTrace", "IngestReport", "RAGPipeline"]
