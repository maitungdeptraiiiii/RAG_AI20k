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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag.config import Settings
from rag.generate.answer import answer_question
from rag.index.bm25_index import BM25Index
from rag.index.embedder import EmbeddingCache, make_embedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.ingest.chunker import chunk_document
from rag.ingest.loaders import load_source
from rag.retrieve.context import ContextConfig, ContextSelection, select_context
from rag.retrieve.hybrid import HybridRetriever, Mode, RetrievalResult
from rag.retrieve.rerank import make_reranker
from rag.schema import LLM, Answer, Page

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


# Không còn thuộc chữ ký index: mỗi embedding model có vector index riêng (Settings.vector_dir,
# kiểm tra bằng vector meta.json). File index_config.json cũ còn các khoá này thì bỏ qua.
_LEGACY_SIGNATURE_KEYS = ("embed_model", "embed_dim")


def index_signature(settings: Settings, index_enhancers: Sequence[str]) -> dict[str, Any]:
    """Những gì quyết định nội dung chunk (chunks.jsonl, BM25). Khác nhau -> phải ingest lại."""
    return {
        "max_syllables": settings.max_syllables,
        "index_enhancers": list(index_enhancers),
    }


def check_index_config(path: Path, signature: dict[str, Any]) -> None:
    if path.exists():
        have = json.loads(path.read_text(encoding="utf-8"))
        have = {k: v for k, v in have.items() if k not in _LEGACY_SIGNATURE_KEYS}
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
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k
        self.max_syllables = max_syllables
        self.context_config = context or ContextConfig(fixed_k=top_k)
        self.index_enhancers = list(index_enhancers)
        self._loader = loader
        if len(store):
            # khởi động lại: dựng BM25 trong RAM, Qdrant bỏ qua chunk đã có; chunk đã lưu kèm context
            self.retriever.build(store.all())

    @classmethod
    def from_settings(cls, s: Settings, *, llm: LLM | None = None) -> RAGPipeline:
        from rag.advanced import Components, build_enhancements
        from rag.generate.llm import LLMCache, OpenAIChatLLM

        llm = llm or OpenAIChatLLM(
            s.llm_model,
            temperature=s.llm_temperature,
            base_url=s.llm_base_url,
            api_key=s.llm_api_key,
            cache=LLMCache(s.cache_dir / "llm.sqlite"),
        )
        embedder = make_embedder(
            s.embed_model, s.embed_dim, cache=EmbeddingCache(s.cache_dir / "embeddings.sqlite"),
            backend=s.embed_backend or None,
            query_prefix=s.embed_query_prefix, passage_prefix=s.embed_passage_prefix,
            jina_api_key=s.jina_api_key, device=s.embed_device or None, batch_size=s.embed_batch_size,
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
            reranker=make_reranker(s.rerank_backend, model_id=s.rerank_model or None,
                                   cache_path=s.cache_dir / "rerank.sqlite"),
            arm_k=s.arm_k,
            rrf_k=s.rrf_k,
            rerank_n=s.rerank_n,
            merge_articles=s.merge_articles,
            article_pool_factor=s.article_pool_factor,
            default_arms=s.retrieval_arm_list,
        )
        context = ContextConfig(
            min_p=s.context_min_p,
            max_blocks=s.context_max_blocks,
            max_words=s.context_max_words,
            fixed_k=s.top_k,
        )
        log.info("Phương pháp nâng cao: %s", [e.name for e in enhancements] or "không (baseline)")
        return cls(
            ChunkStore(s.chunks_path), retriever, llm,
            top_k=s.top_k, max_syllables=s.max_syllables, context=context,
            index_enhancers=index_enhancers,
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
        mode: Mode = "hybrid",
        arms: Sequence[str] | None = None,
        rerank: bool = True,
    ) -> AskTrace:
        retrieval = self.retriever.retrieve(query, self.top_k, mode=mode, arms=arms, rerank=rerank)
        selection = select_context(retrieval.ranked, self.retriever.chunks, self.context_config)

        # GUARDRAIL (trước LLM, TV5): chặn theo ngưỡng điểm RRF khi không rerank — chưa làm.
        if selection.empty:
            return AskTrace(Answer.refusal(retrieval.hits), retrieval, selection, llm_called=False)

        answer = answer_question(retrieval.query, selection.blocks, self.llm, retrieval.hits)
        # GUARDRAIL (sau LLM, TV5): loại [n] sai, không còn citation hợp lệ thì từ chối — chưa làm.
        return AskTrace(answer, retrieval, selection, llm_called=True)

    def ask(self, query: str) -> Answer:
        return self.ask_debug(query).answer


__all__ = ["AskTrace", "IndexConfigMismatchError", "IngestReport", "RAGPipeline", "check_index_config",
           "index_signature"]
