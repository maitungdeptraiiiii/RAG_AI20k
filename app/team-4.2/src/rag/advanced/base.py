"""Khung plugin cho phương pháp nâng cao (bonus #8).

Một phương pháp nâng cao là một hàm factory đăng ký bằng `@register("tên")`, nhận `Components`
(những gì pipeline đã dựng sẵn) và trả `Enhancement` gồm ba điểm gắn, dùng một hoặc nhiều:

    index_enhancer   chạy LÚC INGEST, sau chunking, trước khi index: thêm `Chunk.context`
                     (bối cảnh để BM25/Dense index). Text gốc giữ nguyên để hiển thị và trích dẫn.
                     Vd. Contextual Retrieval.
    arms             arm retrieval thêm vào HybridRetriever, gộp cùng BM25 + Dense bằng RRF.
                     Vd. SPLADE, ColBERT.
    wrap_dense       THAY arm Dense bằng một Retriever bọc nó (đổi cách tạo truy vấn, cùng index).
                     Vd. HyDE. Nhiều wrapper thì bọc lần lượt theo thứ tự ADVANCED.

Bật/tắt bằng biến môi trường `ADVANCED` (danh sách, cách nhau dấu phẩy, giữ đúng thứ tự):

    ADVANCED=                          # baseline sprint 1
    ADVANCED=hyde,contextual

Thêm phương pháp mới: tạo file trong src/rag/advanced/, viết factory có `@register("tên")`, thêm
một dòng import trong advanced/__init__.py, rồi bật bằng ADVANCED. Bỏ: xoá khỏi ADVANCED (hoặc
xoá file + dòng import). Pipeline không phải sửa.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from rag.config import Settings
from rag.index.embedder import Embedder
from rag.schema import LLM, Chunk, Page, Retriever


class IndexEnhancer(Protocol):
    name: str

    def enrich(self, chunks: list[Chunk], pages: Sequence[Page]) -> list[Chunk]:
        """Trả chunk mới (cùng chunk_id, cùng thứ tự) đã thêm bối cảnh vào `context`."""
        ...


@dataclass
class Components:
    """Những gì một phương pháp nâng cao được dùng."""

    settings: Settings
    llm: LLM
    embedder: Embedder
    dense: Retriever          # VectorIndex đã mở (SPLADE/ColBERT... dùng nếu cần; HyDE dùng wrap_dense)


@dataclass
class Enhancement:
    name: str
    index_enhancer: IndexEnhancer | None = None
    arms: dict[str, Retriever] = field(default_factory=dict)
    wrap_dense: Callable[[Retriever], Retriever] | None = None


Factory = Callable[[Components], Enhancement]
REGISTRY: dict[str, Factory] = {}


def register(name: str) -> Callable[[Factory], Factory]:
    def deco(factory: Factory) -> Factory:
        if name in REGISTRY:
            raise ValueError(f"Phương pháp nâng cao {name!r} đã được đăng ký")
        REGISTRY[name] = factory
        return factory

    return deco


def parse_names(value: str | Sequence[str]) -> list[str]:
    items = value.split(",") if isinstance(value, str) else list(value)
    return list(dict.fromkeys(x.strip().lower() for x in items if x and x.strip()))


def build_enhancements(names: str | Sequence[str], components: Components) -> list[Enhancement]:
    names = parse_names(names)
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise ValueError(f"ADVANCED có phương pháp không tồn tại: {unknown}; đang có {sorted(REGISTRY)}")
    return [REGISTRY[n](components) for n in names]


def add_context(chunk: Chunk, extra: str | None) -> Chunk:
    """Nối thêm bối cảnh vào `chunk.context` (nhiều enhancer có thể cùng thêm, theo thứ tự ADVANCED)."""
    extra = (extra or "").strip()
    if not extra:
        return chunk
    merged = f"{chunk.context}\n{extra}" if chunk.context else extra
    return replace(chunk, context=merged)


__all__ = [
    "REGISTRY",
    "Components",
    "Enhancement",
    "IndexEnhancer",
    "add_context",
    "build_enhancements",
    "parse_names",
    "register",
]
