"""Embedding cho Dense retrieval — TV3. Mỗi nhà cung cấp một module, chọn qua registry.

    base.py         Embedder (Protocol), EmbeddingCache (SQLite), CachedEmbedder (cache + batch)
    jina_api.py     JinaEmbedder — jina-embeddings-v5-text-small (1024) qua Jina API — MẶC ĐỊNH
    openai_api.py   OpenAIEmbedder — text-embedding-3-*
    local.py        SentenceTransformerEmbedder — checkpoint HuggingFace chạy local (extra [local])
    hashing.py      HashEmbedder — giả, cho unit test
    registry.py     KNOWN_MODELS + BACKENDS + make_embedder

Đổi model: sửa EMBED_MODEL trong .env (EMBED_DIM để trống thì lấy theo registry). Vector index của
mỗi model nằm ở thư mục riêng `indexes/vector/<model>/`, nên không cần ingest lại: lần chạy đầu
với model mới tự embed lại các chunk trong chunks.jsonl.

Query và chunk dùng CÙNG một model, đưa text gốc (NFC), không đưa text đã tách từ bằng pyvi.
Embedder nào có `embed_query` thì VectorIndex dùng nó cho câu hỏi, `embed` cho chunk.

Vì sao Jina: trên 40 câu benchmark_6_bo_luat, dense-only recall@5 0.600 -> 0.871 (paraphrase
0.375 -> 0.938); trên 20 câu văn nói benchmark_doi_thuong 0.100 -> 0.425.
"""

from rag.index.embedders.base import CachedEmbedder, Embedder, EmbeddingCache, embed_queries
from rag.index.embedders.hashing import HashEmbedder
from rag.index.embedders.jina_api import JINA_URL, JinaEmbedder, JinaHTTPError
from rag.index.embedders.local import SentenceTransformerEmbedder
from rag.index.embedders.openai_api import OPENAI_EMBED_DIM, OPENAI_EMBED_MODEL, OpenAIEmbedder
from rag.index.embedders.registry import (
    BACKENDS,
    KNOWN_MODELS,
    EmbedSpec,
    make_embedder,
    model_slug,
    register_backend,
    resolve_spec,
)

DEFAULT_EMBED_MODEL = "jina-embeddings-v5-text-small"
DEFAULT_EMBED_DIM = 1024

__all__ = [
    "BACKENDS",
    "CachedEmbedder",
    "DEFAULT_EMBED_DIM",
    "DEFAULT_EMBED_MODEL",
    "EmbedSpec",
    "Embedder",
    "EmbeddingCache",
    "HashEmbedder",
    "JINA_URL",
    "JinaEmbedder",
    "JinaHTTPError",
    "KNOWN_MODELS",
    "OPENAI_EMBED_DIM",
    "OPENAI_EMBED_MODEL",
    "OpenAIEmbedder",
    "SentenceTransformerEmbedder",
    "embed_queries",
    "make_embedder",
    "model_slug",
    "register_backend",
    "resolve_spec",
]
