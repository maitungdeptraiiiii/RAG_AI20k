"""Chọn embedder theo tên model — đổi model chỉ cần đổi EMBED_MODEL trong .env.

Hai bảng:
    BACKENDS      tên backend -> hàm dựng embedder ("jina", "openai", "local", "hash")
    KNOWN_MODELS  tên model -> EmbedSpec (backend, dim, tiền tố query/passage, ...)

Model chưa có trong KNOWN_MODELS vẫn dùng được: backend suy từ tên
("jina-*" -> jina, "text-embedding-*" -> openai, có "/" -> local HuggingFace), hoặc đặt EMBED_BACKEND.
dim của model local chưa biết được hỏi từ chính model; model API thì phải đặt EMBED_DIM.

Thêm model mới: một dòng trong KNOWN_MODELS. Thêm nhà cung cấp mới: viết lớp con CachedEmbedder
rồi `register_backend("ten", factory)`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from rag.index.embedders.base import Embedder, EmbeddingCache


@dataclass(frozen=True)
class EmbedSpec:
    backend: str
    dim: int | None = None             # None = hỏi từ model (chỉ backend local)
    query_prefix: str = ""
    passage_prefix: str = ""
    max_seq_length: int | None = None
    note: str = ""


KNOWN_MODELS: dict[str, EmbedSpec] = {
    "jina-embeddings-v5-text-small": EmbedSpec("jina", 1024, note="mặc định; task query/passage riêng"),
    "jina-embeddings-v3": EmbedSpec("jina", 1024),
    "text-embedding-3-small": EmbedSpec("openai", 1536),
    "text-embedding-3-large": EmbedSpec("openai", 3072),
    # Fine-tune từ multilingual-e5-base trên văn bản luật VN; text thô (không tách từ), định dạng E5
    "bqbbao6/vietnamese-legal-embedding": EmbedSpec(
        "local", 768, query_prefix="query: ", passage_prefix="passage: ", max_seq_length=512,
        note="e5-base fine-tune luật VN",
    ),
    # Fine-tune từ BGE-M3, không cần tiền tố
    "AITeamVN/Vietnamese_Embedding": EmbedSpec("local", 1024, max_seq_length=2048, note="BGE-M3 fine-tune VN"),
    "BAAI/bge-m3": EmbedSpec("local", 1024, max_seq_length=8192),
    "intfloat/multilingual-e5-base": EmbedSpec("local", 768, "query: ", "passage: ", 512),
    "intfloat/multilingual-e5-large": EmbedSpec("local", 1024, "query: ", "passage: ", 512),
}

BackendFactory = Callable[..., Embedder]
BACKENDS: dict[str, BackendFactory] = {}


def register_backend(name: str, factory: BackendFactory) -> None:
    """factory(model_id, spec, *, cache, **opts) -> Embedder."""
    BACKENDS[name] = factory


def _jina(model_id: str, spec: EmbedSpec, *, cache: EmbeddingCache | None, **opts: Any) -> Embedder:
    from rag.index.embedders.jina_api import JinaEmbedder

    return JinaEmbedder(model_id, _need_dim(model_id, spec), cache=cache, api_key=opts.get("jina_api_key"))


def _openai(model_id: str, spec: EmbedSpec, *, cache: EmbeddingCache | None, **opts: Any) -> Embedder:
    from rag.index.embedders.openai_api import OpenAIEmbedder

    return OpenAIEmbedder(model_id, _need_dim(model_id, spec), cache=cache)


def _local(model_id: str, spec: EmbedSpec, *, cache: EmbeddingCache | None, **opts: Any) -> Embedder:
    from rag.index.embedders.local import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(
        model_id, spec.dim, cache=cache,
        query_prefix=spec.query_prefix, passage_prefix=spec.passage_prefix,
        max_seq_length=spec.max_seq_length,
        device=opts.get("device"), batch_size=opts.get("batch_size") or 32,
    )


def _hash(model_id: str, spec: EmbedSpec, *, cache: EmbeddingCache | None, **opts: Any) -> Embedder:
    from rag.index.embedders.hashing import HashEmbedder

    return HashEmbedder(dim=spec.dim or 64, model_id=model_id)


register_backend("jina", _jina)
register_backend("openai", _openai)
register_backend("local", _local)
register_backend("hash", _hash)


def _need_dim(model_id: str, spec: EmbedSpec) -> int:
    if spec.dim is None:
        raise ValueError(f"Model API '{model_id}' chưa có trong KNOWN_MODELS: đặt EMBED_DIM")
    return spec.dim


def guess_backend(model_id: str) -> str:
    if model_id.startswith("jina-"):
        return "jina"
    if model_id.startswith("text-embedding-"):
        return "openai"
    if model_id.startswith("hash-"):
        return "hash"
    if "/" in model_id:
        return "local"
    raise ValueError(
        f"Không đoán được backend cho EMBED_MODEL={model_id!r}: đặt EMBED_BACKEND "
        f"({' | '.join(sorted(BACKENDS))}) hoặc thêm model vào KNOWN_MODELS"
    )


def resolve_spec(
    model_id: str,
    *,
    backend: str | None = None,
    dim: int | None = None,
    query_prefix: str | None = None,
    passage_prefix: str | None = None,
) -> EmbedSpec:
    """Spec trong registry, ghi đè bằng tham số khác None. Model đã biết mà dim khác -> lỗi (dễ đặt nhầm)."""
    known = KNOWN_MODELS.get(model_id)
    spec = known or EmbedSpec(backend or guess_backend(model_id))
    if known and dim is not None and known.dim is not None and dim != known.dim:
        raise ValueError(
            f"EMBED_DIM={dim} không khớp {model_id} ({known.dim} chiều). Bỏ EMBED_DIM để lấy tự động."
        )
    overrides = {
        k: v for k, v in {"backend": backend, "dim": dim, "query_prefix": query_prefix,
                          "passage_prefix": passage_prefix}.items() if v is not None
    }
    spec = replace(spec, **overrides)
    if spec.backend not in BACKENDS:
        raise ValueError(f"EMBED_BACKEND={spec.backend!r} không có; chọn {' | '.join(sorted(BACKENDS))}")
    return spec


def make_embedder(
    model_id: str,
    dim: int | None = None,
    *,
    cache: EmbeddingCache | None = None,
    backend: str | None = None,
    query_prefix: str | None = None,
    passage_prefix: str | None = None,
    **opts: Any,
) -> Embedder:
    """Dựng embedder cho `model_id`. `opts`: jina_api_key, device, batch_size (backend tự lấy cái cần)."""
    spec = resolve_spec(model_id, backend=backend, dim=dim,
                        query_prefix=query_prefix, passage_prefix=passage_prefix)
    return BACKENDS[spec.backend](model_id, spec, cache=cache, **opts)


def model_slug(model_id: str) -> str:
    """Tên thư mục an toàn cho model: "bqbbao6/vietnamese-legal-embedding" -> "bqbbao6__vietnamese-legal-embedding"."""
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "__", model_id).strip("_") or "model"
