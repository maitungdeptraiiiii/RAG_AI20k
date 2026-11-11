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
import re
import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rag.advanced.condense import QueryCondenser
from rag.config import Settings
from rag.generate.answer import answer_question, build_citations, build_prompt
from rag.index.bm25_index import BM25Index
from rag.index.embedder import EmbeddingCache, make_embedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.ingest.chunker import chunk_document, chunk_fixed
from rag.ingest.loaders import FlaggedPage, OCRPage, TablePage, load_source
from rag.quality.issues import QualityIssue
from rag.ingest.page_report import page_details, summarize_pages
from rag.ingest.tables import chunk_tables
from rag.quality.apply import assess_tables, mask_pages
from rag.quality.pii import QUERY_PREFIX, MaskState, count_by_type, mask_text
from rag.quality.validate import TableFact
from rag.retrieve.context import ContextConfig, ContextSelection, select_context
from rag.retrieve.hybrid import HybridRetriever, Mode, RetrievalResult
from rag.retrieve.rerank import make_reranker
from rag.schema import REFUSAL, LLM, Answer, Page, nfc

log = logging.getLogger(__name__)


def make_ocr_engine(s: Settings):
    """OCR_ENGINE=gemini -> GeminiOCREngine (cache + ngưỡng chi phí trong DATA_DIR/cache/ocr)."""
    if s.ocr_engine.lower() != "gemini":
        return None
    from rag.ingest.ocr import GeminiOCREngine, TesseractConfidence

    if not s.openrouter_api_key:
        raise ValueError("OCR_ENGINE=gemini cần OPENROUTER_API_KEY trong .env")
    return GeminiOCREngine(
        api_key=s.openrouter_api_key, model=s.ocr_model, cache_dir=s.cache_dir / "ocr",
        cost_cap_usd=s.ocr_cost_cap_usd,
        quality=TesseractConfidence(cmd=s.tesseract_cmd, min_confidence=s.ocr_min_confidence),
    )


_OCR_DETAIL = {
    "ocr.low_confidence": "Chất lượng OCR thấp (Tesseract confidence dưới ngưỡng hoặc có [không đọc được]); "
                          "cần đối chiếu ảnh gốc trước khi dùng số liệu",
    "ocr.truncated": "Output OCR bị cắt (RECITATION / MAX_TOKENS / SAFETY); thiếu nội dung trang",
    "ocr.empty": "OCR không trả về chữ nào",
}


def ocr_issues(pages: Sequence[Page]) -> list[QualityIssue]:
    """QualityIssue từ kiểm tra trích xuất (font cũ vỡ dấu) và từ OCR."""
    out: list[QualityIssue] = []
    for p in pages:
        loc = f"page:{p.page}" if p.page is not None else "document"
        if isinstance(p, FlaggedPage):
            for issue in p.extraction_issues:
                out.append(QualityIssue(f"extraction.{issue.kind}", "warning", loc,
                                        f"{issue.detail}. Text đã index có thể sai dấu: cần bản Unicode "
                                        "hoặc bật OCR_ENGINE=gemini (PDF)", "extraction_check"))
            continue
        if not isinstance(p, OCRPage):
            continue
        if p.ocr_meta.get("reason") == "bad_chars":
            out.append(QualityIssue("extraction.bad_chars", "info", loc,
                                    f"{p.ocr_meta.get('reason_detail', '')}. Đã đọc lại trang từ ảnh bằng OCR",
                                    "extraction_check"))
        conf = p.ocr_meta.get("tesseract_confidence")
        for code in p.ocr_issues:
            detail = _OCR_DETAIL.get(code, code)
            if code == "ocr.low_confidence" and conf is not None:
                detail += f" (Tesseract {conf})"
            out.append(QualityIssue(code, "warning", f"page:{p.page or 1}", detail, f"ocr.{p.ocr_engine}"))
    return out


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]")


def extracted_path(extracted_dir: Path, doc_id: str) -> Path:
    return Path(extracted_dir) / f"{_SAFE_ID_RE.sub('_', doc_id)[:120]}.json"


def save_extracted(extracted_dir: Path, report: IngestReport, pages: Sequence[Page]) -> Path:
    """Lưu TOÀN VĂN từng trang đúng như đã index (sau OCR, bỏ header/footer, ĐÃ mask PII) để người dùng
    đối chiếu với file gốc. ``pages_detail`` giữ cùng thứ tự nên ``index`` khớp với bản đồ trang trên UI."""
    kinds = {d["index"]: d["kind"] for d in report.pages_detail}
    rows = [{"index": i, "page": p.page, "kind": kinds.get(i, "text"), "text": p.text} for i, p in enumerate(pages)]
    path = extracted_path(extracted_dir, report.doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"doc_id": report.doc_id, "source": report.source, "pages": rows},
                               ensure_ascii=False), encoding="utf-8")
    return path


# phương pháp nâng cao chỉ tác động lúc truy vấn lên arm Dense (dùng được cho kho khác, vd. kho luật có phiên bản)
DENSE_WRAPPERS = ("hyde",)


def _listwise_llm(s: Settings) -> LLM:
    from rag.generate.llm import LLMCache, OpenAIChatLLM

    return OpenAIChatLLM(s.listwise_model, temperature=0.0, base_url=s.llm_base_url, api_key=s.llm_api_key,
                         cache=LLMCache(s.cache_dir / "listwise_llm.sqlite"))


def make_hybrid_retriever(s: Settings, llm: LLM, bm25: Any, dense: Any, *,
                          extra_arms: dict[str, Any] | None = None, reranker: Any = None,
                          wrap_dense: Sequence[Any] | None = None,
                          listwise_llm: LLM | None = None) -> HybridRetriever:
    """HybridRetriever cấu hình đúng như pipeline chính: BM25 + Dense (bọc HyDE... theo ADVANCED) -> RRF -> rerank
    (RERANK_BACKEND), cùng arm_k / rerank_n / gộp theo Điều / rewrite / decomposition / coverage / listwise.
    `wrap_dense=None`: tự dựng các phương pháp trong DENSE_WRAPPERS đang bật trong ADVANCED.
    `listwise_llm=None` (khi LISTWISE bật): dựng LLM riêng theo LISTWISE_MODEL, cache listwise_llm.sqlite."""
    from rag.advanced import Components, build_enhancements, parse_names
    from rag.retrieve.coverage import CoverageConfig
    from rag.retrieve.listwise import ListwiseConfig, ListwiseSelector

    if wrap_dense is None:
        names = [n for n in parse_names(s.advanced_methods) if n in DENSE_WRAPPERS]
        comps = Components(settings=s, llm=llm, embedder=getattr(dense, "embedder", None), dense=dense)
        wrap_dense = [e.wrap_dense for e in build_enhancements(names, comps) if e.wrap_dense is not None]
    dense_arm = dense
    for wrap in wrap_dense:               # vd. HyDE: arm Dense tìm bằng (câu hỏi + đoạn giả)
        dense_arm = wrap(dense_arm)
    if reranker is None:
        reranker = make_reranker(s.rerank_backend, cache_path=s.cache_dir / "rerank.sqlite")
    retriever = HybridRetriever(
        bm25,
        dense_arm,
        extra_arms=extra_arms,
        reranker=reranker,
        arm_k=s.arm_k,
        rrf_k=s.rrf_k,
        rerank_n=s.rerank_n,
        merge_articles=s.merge_articles,
        article_pool_factor=s.article_pool_factor,
        bm25_rrf_weight=s.bm25_rrf_weight,
        rewrite_for_rerank=s.rewrite_for_rerank,
        coverage=(CoverageConfig(s.coverage_anchor_k,s.coverage_min_p,s.coverage_weight,s.coverage_branch_k)
                  if s.coverage_enabled else None),
        listwise=(ListwiseSelector(listwise_llm or _listwise_llm(s),
                  ListwiseConfig(s.listwise_candidate_n,s.listwise_margin,
                  s.listwise_min_p,s.listwise_excerpt_words)) if s.listwise_enabled else None),
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
    return retriever


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
    n_tables: int = 0
    ocr_pages: list[int] = field(default_factory=list)                # trang có text do OCR sinh
    ocr_cost_usd: float = 0.0                                         # chi phí OCR lần này (0 nếu cache)
    pii_counts: dict[str, int] = field(default_factory=dict)          # số PII đã mask theo loại
    quality_issues: list[dict[str, Any]] = field(default_factory=list)  # QualityIssue.to_dict()
    pages_detail: list[dict[str, Any]] = field(default_factory=list)    # rag.ingest.page_report.page_details
    summary: dict[str, Any] = field(default_factory=dict)               # độ đầy đủ / độ tin cậy OCR / status
    indexed: bool = False          # đã chunk + embedding + vào kho tra cứu (False = mới trích xuất)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "needs_review": self.needs_review}

    @property
    def needs_review(self) -> bool:
        return any(i.get("severity") in ("warning", "error") for i in self.quality_issues)


@dataclass
class PreparedDoc:
    """Kết quả ``prepare``: trang đã trích xuất + mask, chờ ``commit`` (embedding / index)."""

    report: IngestReport
    pages: list[Page]
    facts: list[Any] = field(default_factory=list)      # fact số liệu bảng, thêm vào kho khi commit


@dataclass
class AskTrace:
    answer: Answer                 # text đã MỞ che (hiển thị cho chính người hỏi)
    retrieval: RetrievalResult     # retrieval.query là câu hỏi ĐÃ che — đúng thứ đã gửi ra ngoài
    context: ContextSelection
    llm_called: bool
    query_pii: dict[str, int] = field(default_factory=dict)   # số PII đã che trong câu hỏi, theo loại
    condensed_query: str | None = None   # câu hỏi độc lập sau khi gộp lịch sử chat (ĐÃ che PII)


# Chỉ thêm vào prompt khi câu hỏi có PII đã che, để câu hỏi thường giữ nguyên prompt (và LLM cache)
PII_NOTE = ("\n(Ghi chú: các ký hiệu dạng [USER_...] là thông tin cá nhân của người hỏi đã được ẩn. "
            "Giữ nguyên đúng ký hiệu khi cần nhắc lại, không đoán giá trị thật.)")


def index_signature(settings: Settings, index_enhancers: Sequence[str]) -> dict[str, Any]:
    """Những gì quyết định nội dung index. Khác nhau -> phải index lại."""
    return {
        "embed_model": settings.embed_model,
        "embed_dim": settings.embed_dim,
        "max_syllables": settings.max_syllables,
        "index_enhancers": list(index_enhancers),
        # chỉ ghi khi khác mặc định, để index cũ (structural) không bị coi là lệch cấu hình
        **({"chunk_strategy": settings.chunk_strategy, "chunk_overlap": settings.chunk_overlap}
           if settings.chunk_strategy != "structural" else {}),
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
        chunk_strategy: str = "structural",
        chunk_overlap: int = 50,
        context: ContextConfig | None = None,
        index_enhancers: Sequence[Any] = (),
        loader: Callable[..., list[Page]] = load_source,
        mask_pii: bool = True,
        mask_queries: bool = True,
        ocr: Any = None,
        extracted_dir: Path | None = None,
        condenser: QueryCondenser | None = None,
    ) -> None:
        self.store = store
        self.ocr = ocr                      # engine OCR cho PDF scan / ảnh (None = không OCR)
        self.extracted_dir = extracted_dir  # lưu toàn văn đã index từng trang để đối chiếu (None = không lưu)
        self.mask_pii = mask_pii            # che PII trong tài liệu lúc ingest
        self.mask_queries = mask_queries    # che PII trong câu hỏi lúc ask
        # fact số liệu của bảng đã ingest trong phiên này, để phát hiện conflict (chưa lưu đĩa)
        self._table_facts: list[tuple[str, TableFact]] = []
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k
        self.max_syllables = max_syllables
        self.chunk_strategy, self.chunk_overlap = chunk_strategy, chunk_overlap
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
        retriever = make_hybrid_retriever(
            s, llm, BM25Index(), dense, extra_arms=extra_arms,
            wrap_dense=[e.wrap_dense for e in enhancements if e.wrap_dense is not None])
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
            top_k=s.top_k, max_syllables=s.max_syllables, chunk_strategy=s.chunk_strategy,
            chunk_overlap=s.chunk_overlap, context=context,
            index_enhancers=index_enhancers, ocr=make_ocr_engine(s), extracted_dir=s.data_dir / "extracted",
            condenser=QueryCondenser(condenser_llm),
        )

    # --- ingest ----------------------------------------------------------------

    def ingest(self, path_or_url: str | Path, *, source: str | None = None) -> IngestReport:
        """Parse -> chunk -> (bối cảnh nâng cao) -> index -> lưu. Cùng tài liệu ingest lại thì bỏ qua.

        = ``prepare`` (trích xuất / OCR / kiểm tra chất lượng) + ``commit`` (chunk / embedding / index).
        UI tách hai bước để người dùng xem bản trích xuất trước khi quyết định đưa vào kho.
        """
        prepared = self.prepare(path_or_url, source=source)
        return prepared.report if prepared.report.skipped else self.commit(prepared)

    def prepare(self, path_or_url: str | Path, *, source: str | None = None) -> PreparedDoc:
        """Bước 1: đọc / OCR, mask PII, kiểm tra chất lượng, lưu bản trích xuất. KHÔNG chunk / embed / index.

        Tài liệu đã có trong kho -> ``report.skipped = report.indexed = True`` (không làm gì thêm, chỉ tạo
        bù bản trích xuất nếu thiếu)."""
        kwargs: dict[str, Any] = {}
        if source:
            kwargs["source"] = source
        if self.ocr is not None:
            kwargs["ocr"] = self.ocr
        pages = self._loader(path_or_url, **kwargs)
        if not pages:
            raise ValueError(f"Không đọc được nội dung: {path_or_url}")
        report = IngestReport(
            doc_id=pages[0].doc_id,
            source=pages[0].source,
            n_pages=len(pages),
            empty_pages=[p.page for p in pages if p.is_empty and p.page is not None],
        )
        if self.store.has_doc(report.doc_id):
            report.skipped = report.indexed = True
            report.n_chunks = len(self.store.by_doc(report.doc_id))
            # tài liệu nạp trước khi có bản trích xuất: tạo bù (OCR đã cache), KHÔNG index lại
            if self.extracted_dir is not None and not extracted_path(self.extracted_dir, report.doc_id).exists():
                masked = mask_pages(pages)[0] if self.mask_pii else pages
                report.pages_detail = page_details(masked)
                save_extracted(self.extracted_dir, report, masked)
                report.pages_detail = []
            return PreparedDoc(report, pages, [])

        # Mask PII TRƯỚC chunk / contextual LLM / embed / BM25 / chunks.jsonl / log (W02-02f)
        if self.mask_pii:
            pages, pii_findings = mask_pages(pages)
            report.pii_counts = count_by_type(pii_findings)
        text_pages = [p for p in pages if not isinstance(p, TablePage)]
        report.n_tables = sum(isinstance(p, TablePage) and p.table is not None for p in pages)
        report.n_pages = len(text_pages) or len(pages)

        # Kiểm tra số liệu bảng + conflict với bảng đã ingest (W02-02h); chạy trên dữ liệu đã mask
        issues, facts = assess_tables(pages, self._table_facts)
        issues = ocr_issues(pages) + issues
        report.quality_issues = [i.to_dict() for i in issues]
        report.pages_detail = page_details(pages)          # trang đã mask: preview không chứa PII gốc
        report.summary = summarize_pages(report.pages_detail, report.quality_issues)
        ocr_pages = [p for p in pages if isinstance(p, OCRPage)]
        report.ocr_pages = [p.page for p in ocr_pages if p.page is not None]
        report.ocr_cost_usd = round(sum(float(p.ocr_meta.get("cost") or 0) for p in ocr_pages
                                        if not p.ocr_meta.get("cached")), 6)
        if self.extracted_dir is not None:
            save_extracted(self.extracted_dir, report, pages)
        log.info("Trích xuất %s: %d trang, %d bảng, PII đã mask %s, %d issue (chưa index)", report.source,
                 report.n_pages, report.n_tables, report.pii_counts or {}, len(issues))
        return PreparedDoc(report, pages, facts)

    def commit(self, prepared: PreparedDoc) -> IngestReport:
        """Bước 2: chunk -> (bối cảnh nâng cao) -> embedding / index -> lưu kho. Trên trang ĐÃ mask."""
        report, pages = prepared.report, prepared.pages
        if report.indexed or self.store.has_doc(report.doc_id):
            report.indexed = True
            report.n_chunks = len(self.store.by_doc(report.doc_id))
            return report
        text_pages = [p for p in pages if not isinstance(p, TablePage)]
        tables = [p.table for p in pages if isinstance(p, TablePage) and p.table is not None]
        if not text_pages:
            chunks = []
        elif self.chunk_strategy == "fixed":
            chunks = chunk_fixed(text_pages, max_syllables=self.max_syllables, overlap=self.chunk_overlap)
        else:
            chunks = chunk_document(text_pages, max_syllables=self.max_syllables)
        chunks += chunk_tables(tables, doc_id=report.doc_id, source=report.source,
                               start_index=len(chunks), max_syllables=self.max_syllables)
        if not chunks:
            raise ValueError(f"{report.source}: không có text để index (PDF scan cần OCR?)")
        for enhancer in self.index_enhancers:
            enriched = enhancer.enrich(chunks, pages)
            if [c.chunk_id for c in enriched] != [c.chunk_id for c in chunks]:
                raise RuntimeError(f"{enhancer.name}: phải trả đúng các chunk đầu vào, cùng thứ tự")
            chunks = enriched
        self.retriever.build(chunks)          # index trước, lưu sau: index lỗi thì không ghi store
        self.store.add(chunks)
        self._table_facts.extend((report.source, f) for f in prepared.facts)
        report.n_chunks = len(chunks)
        report.indexed = True
        log.info("Index %s: %d chunk", report.source, report.n_chunks)
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
        mask_state: MaskState | None = None,
    ) -> AskTrace:
        """Hỏi đáp. Câu hỏi (và lịch sử chat) được che PII TRƯỚC mọi bước (condense, HyDE, embedding,
        rerank, LLM, cache, log); câu trả lời được mở che ở bước cuối, chỉ cho người hỏi thấy.

        ``mask_state``: truyền cùng một state cho cả phiên chat (``new_query_mask_state()``) để
        cùng một khách hàng luôn là cùng placeholder qua các lượt; bỏ trống = state riêng mỗi câu.
        Bảng tra placeholder -> giá trị gốc chỉ nằm trong state (RAM của người gọi).
        ``history``: các lượt trước ``[{"query", "answer"}]`` — QueryCondenser gộp thành câu hỏi độc lập.
        """
        state = mask_state if mask_state is not None else self.new_query_mask_state()
        effective_query, query_pii = self._prepare_query(query, history, state)

        retrieval = self.retriever.retrieve(effective_query, self.top_k, mode=mode, arms=arms, rerank=rerank)
        selection = select_context(retrieval.ranked, self.retriever.chunks, self.context_config)

        # GUARDRAIL (trước LLM, TV5): chặn theo ngưỡng điểm RRF khi không rerank — chưa làm.
        if selection.empty:
            return AskTrace(Answer.refusal(retrieval.hits), retrieval, selection, llm_called=False,
                            query_pii=query_pii, condensed_query=effective_query)

        answer = answer_question(self._prompt_query(retrieval.query), selection.blocks, self.llm, retrieval.hits)
        # GUARDRAIL (sau LLM, TV5): loại [n] sai, không còn citation hợp lệ thì từ chối — chưa làm.
        if not answer.refused:
            answer.text = state.unmask(answer.text)   # sau LLM + cache: cache chỉ giữ bản đã che
        return AskTrace(answer, retrieval, selection, llm_called=True, query_pii=query_pii,
                        condensed_query=effective_query)

    def ask(self, query: str, *, history: Sequence[dict[str, Any]] | None = None,
            mask_state: MaskState | None = None) -> Answer:
        return self.ask_debug(query, history=history, mask_state=mask_state).answer

    @staticmethod
    def new_query_mask_state() -> MaskState:
        """State che PII cho một phiên hỏi đáp: placeholder dạng [USER_PHONE_1]."""
        return MaskState(prefix=QUERY_PREFIX)

    def _prepare_query(self, query: str, history: Sequence[dict[str, Any]] | None,
                       state: MaskState) -> tuple[str, dict[str, int]]:
        """Che PII câu hỏi + lịch sử bằng CÙNG state (cùng người -> cùng placeholder), rồi condense.
        Trả (câu hỏi đã che và đã gộp lịch sử, số PII mới che trong câu hỏi theo loại)."""
        if not self.mask_queries:
            masked_history = history
            query_pii: dict[str, int] = {}
        else:
            masked_history = [
                {**turn, **{k: mask_text(str(turn[k]), state=state).masked_text
                            for k in ("query", "answer") if turn.get(k)}}
                for turn in (history or []) if isinstance(turn, dict)
            ]
            before = dict(state.counts)
            query = mask_text(query, state=state).masked_text
            query_pii = {k: v - before.get(k, 0) for k, v in state.counts.items() if v - before.get(k, 0)}
        effective = self.condenser.condense(query, history=masked_history) if self.condenser else query
        return effective, query_pii

    @staticmethod
    def _prompt_query(query: str) -> str:
        return query + PII_NOTE if f"[{QUERY_PREFIX}" in query else query

    def ask_stream(
        self,
        query: str,
        *,
        history: Sequence[dict[str, Any]] | None = None,
        mode: Mode = "hybrid",
        arms: Sequence[str] | None = None,
        rerank: bool = True,
        mask_state: MaskState | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Như ``ask_debug`` nhưng trả sự kiện: ``sources`` -> nhiều ``token`` -> ``done``.
        Token được mở che PII trước khi gửi; placeholder bị cắt giữa hai token được giữ lại tới token sau."""
        state = mask_state if mask_state is not None else self.new_query_mask_state()
        effective_query, query_pii = self._prepare_query(query, history, state)
        retrieval = self.retriever.retrieve(effective_query, self.top_k, mode=mode, arms=arms, rerank=rerank)
        selection = select_context(retrieval.ranked, self.retriever.chunks, self.context_config)

        if selection.empty:
            yield {
                "type": "done",
                "answer": REFUSAL,
                "refused": True,
                "citations": [],
                "sources": [],
                "query_pii": query_pii,
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

        system, user = build_prompt(self._prompt_query(retrieval.query), selection.blocks)
        collected: list[str] = []
        unmasker = _StreamUnmasker(state)

        deltas = self.llm.stream(system, user) if hasattr(self.llm, "stream") else [self.llm.complete(system, user)]
        for delta in deltas:
            collected.append(delta)
            shown = unmasker.feed(delta)
            if shown:
                yield {"type": "token", "delta": shown}
        tail = unmasker.flush()
        if tail:
            yield {"type": "token", "delta": tail}

        full_text = nfc("".join(collected)).strip()
        answer = build_citations(full_text, selection.blocks, retrieval.hits)
        if not answer.refused:
            answer.text = state.unmask(answer.text)

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
            "query_pii": query_pii,
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


class _StreamUnmasker:
    """Mở che PII trên luồng token: giữ lại đoạn từ dấu ``[`` chưa đóng cuối cùng (có thể là nửa đầu
    của ``[USER_PHONE_1]``) cho tới khi nhận đủ, để không bao giờ gửi placeholder dở dang ra UI."""

    _MAX_HOLD = 40   # placeholder dài nhất cỡ [USER_CCCD_12]; "[" mở quá xa thì không phải placeholder

    def __init__(self, state: MaskState) -> None:
        self.state = state
        self.buf = ""

    def feed(self, delta: str) -> str:
        self.buf += delta
        cut = self.buf.rfind("[")
        if cut == -1 or "]" in self.buf[cut:] or len(self.buf) - cut > self._MAX_HOLD:
            out, self.buf = self.buf, ""
        else:
            out, self.buf = self.buf[:cut], self.buf[cut:]
        return self.state.unmask(out)

    def flush(self) -> str:
        out, self.buf = self.buf, ""
        return self.state.unmask(out)


__all__ = ["DENSE_WRAPPERS", "make_hybrid_retriever", "AskTrace", "IndexConfigMismatchError", "IngestReport", "RAGPipeline", "check_index_config",
           "index_signature"]
