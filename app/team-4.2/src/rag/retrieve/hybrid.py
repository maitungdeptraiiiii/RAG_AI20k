"""HybridRetriever: BM25 + Dense (+ arm nâng cao) -> RRF -> (rerank Jev) — TV2.

    retrieve(query, k=5)                          -> mọi arm đang bật, gộp bằng RRF
    retrieve(query, k=5, mode="bm25")             -> chỉ một arm (dùng cho eval BM25 / Dense riêng)
    retrieve(query, k=5, arms=("bm25", "dense"))  -> chọn tập arm (ablation)
    search(query, k)                              -> list[Hit] cuối (thoả interface Retriever)

Sau RRF / rerank, các chunk cùng một Điều được gộp thành MỘT candidate (merge_articles=True,
xem retrieve/merge.py): `ranked` và `hits` tính theo Điều, chunk phụ nằm trong `Hit.merged`.

Arm lõi: "bm25", "dense" (HyDE nếu bật thì nằm TRONG arm "dense", xem advanced/hyde.py).
Phương pháp nâng cao thêm arm qua `extra_arms` (vd. {"splade": ...}),
xem src/rag/advanced/. Gọi nhiều arm mà một arm lỗi (vd. mất mạng) thì vẫn trả kết quả các arm còn
lại và ghi lỗi vào `RetrievalResult.errors`; mọi arm đều lỗi thì ném RetrievalError.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import math
from threading import RLock
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag.advanced.decomposition import QueryDecomposer
    from rag.advanced.rewrite import QueryRewriter
    from rag.retrieve.listwise import ListwiseSelector

from rag.retrieve.fusion import DEFAULT_RRF_K, rrf
from rag.retrieve.coverage import CoverageConfig, select_with_coverage
from rag.retrieve.merge import article_key, merge_by_article, take_articles
from rag.schema import Chunk, Hit, Reranker, Retriever, nfc

log = logging.getLogger(__name__)

Mode = str            # "hybrid" | tên một arm ("bm25", "dense", "splade", ...)
CORE_ARMS = ("bm25", "dense")
MODES: tuple[str, ...] = ("hybrid", *CORE_ARMS)


class RetrievalError(RuntimeError):
    """Không arm nào trả được kết quả."""


class CorpusChangedError(RuntimeError):
    """An agent must restart rather than mix two index generations."""


@dataclass
class RetrievalResult:
    query: str
    mode: str
    arms: dict[str, list[Hit]] = field(default_factory=dict)   # kết quả từng arm (top arm_k)
    candidates: list[Hit] = field(default_factory=list)        # fused (nhiều arm) hoặc hit của arm duy nhất
    ranked: list[Hit] = field(default_factory=list)            # toàn bộ candidates sau rerank (= candidates nếu không rerank);
                                                               # dùng để chọn context theo ngưỡng (retrieve/context.py)
    hits: list[Hit] = field(default_factory=list)              # = ranked[:k]: cố định k để chấm Recall@k, MRR@k
    errors: dict[str, str] = field(default_factory=dict)       # arm -> lỗi (nếu có)
    queries: list[str] = field(default_factory=list)
    query_results: dict[str, list[Hit]] = field(default_factory=dict)
    rerank_query: str | None = None
    pre_selection_ranked: list[Hit] = field(default_factory=list)
    selection_policy: str = 'relevance'
    listwise_metadata: dict = field(default_factory=dict)

    @property
    def reranked(self) -> bool:
        return bool(self.hits) and self.hits[0].arm == "rerank"

    @property
    def top_score(self) -> float | None:
        return self.hits[0].score if self.hits else None


class HybridRetriever:
    def __init__(
        self,
        bm25: Retriever,
        dense: Retriever,
        *,
        extra_arms: Mapping[str, Retriever] | None = None,
        reranker: Reranker | None = None,
        arm_k: int = 20,
        rrf_k: int = DEFAULT_RRF_K,
        rerank_n: int = 20,
        merge_articles: bool = True,
        article_pool_factor: int = 2,
        bm25_rrf_weight: float = 1.0,
        rewrite_for_rerank: bool = True,
        coverage: CoverageConfig | None = None,
        listwise: ListwiseSelector | None = None,
    ) -> None:
        if arm_k < 1 or rerank_n < 1 or article_pool_factor < 1:
            raise ValueError("arm_k, rerank_n, article_pool_factor phải >= 1")
        if not math.isfinite(bm25_rrf_weight) or bm25_rrf_weight < 0:
            raise ValueError('BM25 weight must be finite and nonnegative')
        if coverage is not None and listwise is not None:
            raise ValueError('Coverage and listwise are separate selection policies')
        clash = set(extra_arms or {}) & {*CORE_ARMS, "hybrid", "fused", "rerank"}
        if clash:
            raise ValueError(f"Tên arm nâng cao trùng tên dành riêng: {sorted(clash)}")
        self.arms: dict[str, Retriever] = {"bm25": bm25, "dense": dense, **(extra_arms or {})}
        self.reranker = reranker
        self.arm_k, self.rrf_k, self.rerank_n = arm_k, rrf_k, rerank_n
        self.merge_articles = merge_articles
        # khi gộp theo Điều: mỗi arm lấy arm_k * factor chunk, pool rerank cắt ở rerank_n ĐIỀU
        self.article_pool_factor = article_pool_factor if merge_articles else 1
        self._chunks: dict[str, Chunk] = {}
        self.decomposer: QueryDecomposer | None = None
        self.rewriter: QueryRewriter | None = None
        self.bm25_rrf_weight = bm25_rrf_weight
        self.rewrite_for_rerank = rewrite_for_rerank
        self.coverage = coverage
        self.listwise = listwise
        self._corpus_lock = RLock()
        self._corpus_revision = 0
        self._index_ready = True

    # --- build ---------------------------------------------------------------

    def build(self, chunks: Iterable[Chunk]) -> None:
        """Index chunk vào mọi arm và nhớ nội dung chunk (reranker, context cần text).

        Gọi lại với chunk đã có thì không nhân đôi. Khi mở index có sẵn trên đĩa, vẫn gọi
        build(toàn bộ chunk) để retriever có text chunk cho reranker.
        """
        chunks = list(chunks)
        with self._corpus_lock:
            self._corpus_revision += 1
            self._index_ready = False
            for c in chunks:
                if c.chunk_id in self._chunks and self._chunks[c.chunk_id] != c:
                    raise ValueError("Cannot replace an indexed chunk under the same ID")
            for retriever in self.arms.values():
                retriever.build(chunks)
            for c in chunks:
                self._chunks.setdefault(c.chunk_id, c)
            self._index_ready = True

    def capture_snapshot(self) -> tuple[int, Mapping[str, Chunk]]:
        with self._corpus_lock:
            if not self._index_ready:
                raise CorpusChangedError("Index build has not completed")
            return self._corpus_revision, MappingProxyType(dict(self._chunks))

    def search_candidates(
        self, query: str, k: int = 20, *, revision: int,
        chunks: Mapping[str, Chunk], mode: Mode = "dense",
        dense: Retriever | None = None,
        reranker: Reranker | None = None,
    ) -> RetrievalResult:
        """One bounded search, without rewrite/decomposition/listwise recursion.

        A request-local view can wrap Dense with its own budgeted HyDE client.
        The shared retriever and its baseline configuration are never mutated.
        """
        with self._corpus_lock:
            if revision != self._corpus_revision or not self._index_ready:
                raise CorpusChangedError("Corpus changed during the request; retry on the new snapshot")
            view = HybridRetriever(
                self.arms["bm25"], dense if dense is not None else self.arms["dense"],
                reranker=reranker if reranker is not None else self.reranker, arm_k=self.arm_k, rrf_k=self.rrf_k,
                rerank_n=k, merge_articles=self.merge_articles,
                article_pool_factor=self.article_pool_factor,
                bm25_rrf_weight=self.bm25_rrf_weight,
            )
            view._chunks = dict(chunks)
            result = view._retrieve_single(query, k, mode=mode, rerank=True)
            if revision != self._corpus_revision or not self._index_ready:
                raise CorpusChangedError("Corpus changed while retrieving")
            return result

    @property
    def chunks(self) -> Mapping[str, Chunk]:
        return self._chunks

    @property
    def modes(self) -> tuple[str, ...]:
        return ("hybrid", *self.arms)

    # --- retrieve ------------------------------------------------------------

    def _resolve_arms(self, mode: str, arms: Sequence[str] | None) -> list[str]:
        if arms is not None:
            names = list(dict.fromkeys(arms))
        elif mode == "hybrid":
            names = list(self.arms)
        else:
            names = [mode]
        unknown = [n for n in names if n not in self.arms]
        if unknown or not names:
            raise ValueError(f"Arm/mode không hợp lệ: {unknown or names}; đang có {self.modes}")
        return names

    def retrieve(
        self, query: str, k: int = 5, *, mode: Mode = "hybrid",
        arms: Sequence[str] | None = None, rerank: bool = True,
    ) -> RetrievalResult:
        with self._corpus_lock:
            return self._retrieve(query, k, mode=mode, arms=arms, rerank=rerank)

    def _retrieve(
        self, query: str, k: int = 5, *, mode: Mode = "hybrid",
        arms: Sequence[str] | None = None, rerank: bool = True,
    ) -> RetrievalResult:
        if k < 1:
            raise ValueError("k phải >= 1")
        names = self._resolve_arms(mode, arms)
        rewrite = (self.rewriter.rewrite(query)
                   if self.rewriter is not None and query.strip()
                   and (self.rewrite_for_rerank or 'bm25' in names) else None)
        bm25_query = rewrite.query if rewrite is not None else None

        def finish(result: RetrievalResult) -> RetrievalResult:
            result.rerank_query = rewrite.query if rewrite is not None and self.rewrite_for_rerank else None
            if rewrite is not None and rewrite.error:
                result.errors['rewrite'] = rewrite.error
            return self._rank_result(result, k, rerank)

        if self.decomposer is None or not query.strip():
            return finish(self._retrieve_single(query, k, mode=mode, arms=arms, rerank=False,
                                                bm25_query=bm25_query))
        plan = self.decomposer.plan(query)
        if len(plan.queries) <= 1:
            result = self._retrieve_single(query, k, mode=mode, arms=arms, rerank=False,
                                           bm25_query=bm25_query)
            result.queries = plan.queries
            if plan.error:
                result.errors["decomposition"] = plan.error
            return finish(result)
        result = RetrievalResult(query=nfc(query).strip(),
                                 mode="+".join(names) if arms is not None else mode,
                                 queries=plan.queries)
        original_candidates: list[Hit] = []

        def _fetch_subquery(idx: int, subquery: str) -> tuple[int, list[Hit], list[Hit] | None, dict[str, list[Hit]], dict[str, str]]:
            is_original = self.decomposer.include_original and nfc(subquery).strip() == result.query
            sub = self._retrieve_single(
                subquery, max(self.rerank_n, k) if is_original else self.decomposer.per_query_k,
                mode=mode, arms=arms, rerank=False,
                bm25_query=bm25_query if is_original else None)
            selected = {cid for h in sub.hits for cid in (h.chunk_id, *h.merged)}
            q_res = [h for h in sub.candidates if h.chunk_id in selected]
            orig = list(sub.candidates) if is_original else None
            return idx, q_res, orig, sub.arms, sub.errors

        # Batch pre-embed subqueries: gom các subquery thành 1 request embedding duy nhất,
        # tận dụng cache và tránh rate limit 429 khi n subquery gọi đồng thời.
        dense_arm = self.arms.get("dense")
        target_embedder = getattr(dense_arm, "embedder", None)
        if target_embedder is None and hasattr(dense_arm, "dense"):
            target_embedder = getattr(dense_arm.dense, "embedder", None)
        if target_embedder is not None and hasattr(target_embedder, "embed_query"):
            try:
                target_embedder.embed_query(plan.queries)
            except Exception:
                pass

        workers = min(len(plan.queries), 4)
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_fetch_subquery, i, sq) for i, sq in enumerate(plan.queries)]
                sub_results = []
                for fut, i in zip(futures, range(len(plan.queries))):
                    try:
                        sub_results.append(fut.result())
                    except Exception as exc:
                        result.errors[f"q{i}"] = type(exc).__name__
        else:
            sub_results = []
            for i, sq in enumerate(plan.queries):
                try:
                    sub_results.append(_fetch_subquery(i, sq))
                except Exception as exc:
                    result.errors[f"q{i}"] = type(exc).__name__

        sub_results.sort(key=lambda item: item[0])
        for idx, q_res, orig, arms_map, errors_map in sub_results:
            result.query_results[str(idx)] = q_res
            if orig is not None:
                original_candidates = orig
            result.arms.update({f"q{idx}_{name}": hits for name, hits in arms_map.items()})
            result.errors.update({f"q{idx}_{name}": err for name, err in errors_map.items()})
        if not result.query_results:
            raise RetrievalError(f"Every decomposition branch failed: {result.errors}")
        fused = rrf(result.query_results, k=self.rrf_k)
        pool = max(k, self.decomposer.pool_size)
        if original_candidates:
            def key(hit: Hit) -> tuple[str, ...]:
                return (article_key(self._chunks[hit.chunk_id]) if self.merge_articles
                        else ("chunk", hit.chunk_id))

            # Preserve the complete original pool and its order. Subqueries may only
            # contribute NEW articles, never evict an original article before Jev.
            original_keys = {key(h) for h in original_candidates}
            new_limit = min(self.decomposer.max_new_articles, max(0, pool - len(original_keys)))
            novel = [h for h in fused if key(h) not in original_keys]
            extra = ((take_articles(novel, self._chunks, new_limit) if self.merge_articles
                      else novel[:new_limit]) if new_limit else [])
            result.candidates = [replace(h, rank=i) for i, h in enumerate(
                [*original_candidates, *extra], start=1)]
        else:
            result.candidates = (take_articles(fused, self._chunks, pool)
                                 if self.merge_articles else fused[:pool])
        return finish(result)

    def _retrieve_single(
        self,
        query: str,
        k: int = 5,
        *,
        mode: Mode = "hybrid",
        arms: Sequence[str] | None = None,
        rerank: bool = True,
        bm25_query: str | None = None,
    ) -> RetrievalResult:
        if k < 1:
            raise ValueError(f"k phải >= 1, nhận {k}")
        names = self._resolve_arms(mode, arms)
        q = nfc(query).strip()
        result = RetrievalResult(query=q, mode="+".join(names) if arms is not None else mode)
        if not q:
            return result

        for name in names:
            try:
                search_query = bm25_query if name == 'bm25' and bm25_query is not None else q
                result.arms[name] = self.arms[name].search(search_query, self.arm_k * self.article_pool_factor)
            except Exception as e:
                if len(names) == 1:
                    raise
                log.warning("Arm %s lỗi, tiếp tục với arm còn lại: %r", name, e)
                result.errors[name] = repr(e)
        if not result.arms:
            raise RetrievalError(f"Mọi arm đều lỗi: {result.errors}")

        pool = max(self.rerank_n, k)
        fetch = max(pool, self.arm_k) * self.article_pool_factor   # = số chunk mỗi arm đã trả
        if len(names) > 1:
            result.candidates = rrf(result.arms, k=self.rrf_k, top_n=fetch,
                                    weights={'bm25':self.bm25_rrf_weight})
        else:
            result.candidates = result.arms[names[0]][:fetch]
        if self.merge_articles:
            # pool = `pool` Điều khác nhau (kèm mọi chunk của chúng), không phải `pool` chunk
            result.candidates = take_articles(result.candidates, self._chunks, pool)
        else:
            result.candidates = result.candidates[:pool]

        return self._rank_result(result, k, rerank)

    def _rank_result(self, result: RetrievalResult, k: int, rerank: bool) -> RetrievalResult:
        if rerank and self.reranker is not None and result.candidates:
            # chấm TOÀN BỘ candidates (Jev vốn phải chấm hết để sắp xếp), giữ lại để chọn context
            result.ranked = self.reranker.rerank(result.rerank_query or result.query,
                                                result.candidates, self._chunks, len(result.candidates))
        else:
            result.ranked = list(result.candidates)
        if self.merge_articles:
            # nhiều chunk cùng một Điều -> một candidate (sau rerank: mỗi chunk đã được chấm riêng)
            result.ranked = merge_by_article(result.ranked, self._chunks)
        if (self.listwise is not None and rerank and self.merge_articles
                and result.ranked and result.ranked[0].arm=='rerank'):
            decision=self.listwise.rerank(result.query,result.queries,result.ranked,self._chunks,k=k)
            result.listwise_metadata=decision.metadata
            if decision.metadata['triggered']:
                result.pre_selection_ranked=list(result.ranked)
                result.ranked=decision.ranked
                if decision.metadata['error']:
                    result.errors['listwise']=decision.metadata['error']
                else:
                    result.selection_policy='listwise'
        elif (self.coverage is not None and rerank and self.merge_articles
                and result.ranked and result.ranked[0].arm=='rerank'):
            children={str(i):result.query_results[str(i)] for i,q in enumerate(result.queries)
                      if nfc(q).strip()!=result.query and str(i) in result.query_results}
            if len(children)>=2:
                result.pre_selection_ranked=list(result.ranked)
                result.ranked=select_with_coverage(result.ranked,children,self._chunks,k=k,config=self.coverage)
                result.selection_policy='coverage'
        result.hits = result.ranked[:k]
        return result

    def search(self, query: str, k: int) -> list[Hit]:
        return self.retrieve(query, k).hits


__all__ = ["CORE_ARMS", "MODES", "HybridRetriever", "Mode", "RetrievalError", "RetrievalResult"]
