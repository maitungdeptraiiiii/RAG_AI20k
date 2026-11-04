"""Model embedding chạy local bằng sentence-transformers (checkpoint HuggingFace).

Cần extra `[local]` (sentence-transformers + torch). Tự chọn CUDA nếu có.
Model kiểu E5 cần tiền tố "query: " / "passage: " — khai báo trong registry hoặc qua
EMBED_QUERY_PREFIX / EMBED_PASSAGE_PREFIX. Tiền tố nằm trong cache key, đổi tiền tố không dùng lại vector cũ.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from rag.index.embedders.base import CachedEmbedder, EmbeddingCache

log = logging.getLogger(__name__)


class SentenceTransformerEmbedder(CachedEmbedder):
    """`model` cho phép truyền model giả khi test (cần `.encode(list[str], ...)`)."""

    def __init__(
        self,
        model_id: str,
        dim: int | None = None,
        *,
        cache: EmbeddingCache | None = None,
        query_prefix: str = "",
        passage_prefix: str = "",
        device: str | None = None,
        batch_size: int = 32,
        max_seq_length: int | None = None,
        model: Any = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size phải >= 1")
        self.model_id = model_id
        self.cache = cache
        self.query_prefix, self.passage_prefix = query_prefix, passage_prefix
        self.device = device or None
        self.batch_size = batch_size
        self.max_seq_length = max_seq_length
        self._model = model
        # dim chưa biết -> nạp model để hỏi (VectorIndex cần dim trước khi mở Qdrant)
        self.dim = dim if dim is not None else self._get_model().get_sentence_embedding_dimension()

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    f"Embedder local '{self.model_id}' cần sentence-transformers: pip install -e '.[local]'"
                ) from e
            log.info("Nạp model embedding local %s", self.model_id)
            self._model = SentenceTransformer(self.model_id, device=self.device)
            if self.max_seq_length:
                self._model.max_seq_length = self.max_seq_length
        return self._model

    def embed_query(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, "query")

    def _prefix(self, kind: str) -> str:
        return self.query_prefix if kind == "query" else self.passage_prefix

    def _cache_ns(self, kind: str) -> str:
        return f"{self.model_id}#{kind}#{self._prefix(kind)}"

    def _call(self, batch: list[str], kind: str) -> list[list[float]]:
        prefix = self._prefix(kind)
        vectors = self._get_model().encode(
            [prefix + t for t in batch],
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in v] for v in vectors]
