"""Request-local network limits; never mutate the baseline's shared clients."""

from __future__ import annotations

from types import SimpleNamespace

from rag.agent.contracts import Budget
from rag.index.embedder import JinaEmbedder, OpenAIEmbedder
from rag.index.vector_index import VectorIndex
from rag.retrieve.rerank import FallbackReranker, JevReranker


def bounded_dense(dense, budget: Budget):
    if not isinstance(dense, VectorIndex):
        return dense  # Local/test/custom protocol implementations.
    original = dense.embedder
    if isinstance(original, JinaEmbedder):
        def post(url, payload, key, timeout):
            budget.charge_service("embedding")
            return original._post(url, payload, key, min(timeout, budget.remaining_s()))

        embedder = JinaEmbedder(
            original.model_id, original.dim, cache=original.cache, api_key=original._api_key,
            batch_size=original.batch_size, max_retries=0, timeout=30.0,
            min_interval=0, post=post,
        )
    elif isinstance(original, OpenAIEmbedder):
        def create(**kwargs):
            budget.charge_service("embedding")
            return original._get_client().with_options(
                timeout=min(30.0, budget.remaining_s()), max_retries=0,
            ).embeddings.create(**kwargs)

        embedder = OpenAIEmbedder(
            original.model_id, original.dim, cache=original.cache,
            batch_size=original.batch_size, max_retries=0,
            client=SimpleNamespace(embeddings=SimpleNamespace(create=create)),
        )
    else:
        embedder = original
    return VectorIndex(embedder, dense.store, batch_size=dense.batch_size)


def bounded_reranker(reranker, budget: Budget):
    primary = reranker.primary if isinstance(reranker, FallbackReranker) else reranker
    if not isinstance(primary, JevReranker):
        return primary

    def system_one(**kwargs):
        from typesafe_sdk import RetryPolicy

        budget.charge_service("rerank")
        remaining = min(30.0, budget.remaining_s())
        return primary._get_client().system_one(
            **kwargs, timeout=remaining, retry=RetryPolicy(max_retries=0, timeout=remaining),
        )

    # Reuse deterministic score cache/question; failures remain visible to the
    # agent rather than silently becoming a successful Jev ranking.
    return JevReranker(
        primary.model_id, cache=primary.cache, instructions=primary.instructions,
        max_workers=min(primary.max_workers, 4),
        client=SimpleNamespace(system_one=system_one), question=primary._get_question(),
    )
