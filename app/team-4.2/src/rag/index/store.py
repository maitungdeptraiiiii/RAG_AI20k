"""ChunkStore: lưu toàn bộ chunk ra `chunks.jsonl` — TV5 (dùng chung TV1, TV2, TV3).

Khởi động lại app: đọc lại chunk từ đây rồi `HybridRetriever.build(store.all())` (BM25 dựng lại
trong RAM từ chunk; Qdrant đã lưu trên đĩa nên chỉ bỏ qua chunk đã có). Reranker và context
cần text chunk nên phải có file này.

Ingest cùng một tài liệu hai lần (cùng doc_id) thì bỏ qua — không nhân đôi chunk.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from rag.schema import Chunk


@dataclass(frozen=True)
class DocInfo:
    doc_id: str
    source: str
    n_chunks: int


class ChunkStore:
    def __init__(self, path: Path | str | None = None) -> None:
        """`path=None`: chỉ giữ trong RAM (dùng cho test)."""
        self.path = Path(path) if path is not None else None
        self._chunks: dict[str, Chunk] = {}
        self._docs: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        if self.path is not None and self.path.exists():
            with self.path.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self._remember(Chunk.from_dict(json.loads(line)))

    def _remember(self, chunk: Chunk) -> None:
        if chunk.chunk_id not in self._chunks:
            self._chunks[chunk.chunk_id] = chunk
            self._docs.setdefault(chunk.doc_id, []).append(chunk.chunk_id)

    def has_doc(self, doc_id: str) -> bool:
        return doc_id in self._docs

    def add(self, chunks: Iterable[Chunk]) -> int:
        """Thêm chunk của các tài liệu CHƯA có. Trả số chunk mới được thêm."""
        chunks = list(chunks)
        with self._lock:
            new = [c for c in chunks if c.doc_id not in self._docs and c.chunk_id not in self._chunks]
            if not new:
                return 0
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    for c in new:
                        f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
            for c in new:
                self._remember(c)
            return len(new)

    def get(self, chunk_id: str) -> Chunk:
        return self._chunks[chunk_id]

    def all(self) -> list[Chunk]:
        return list(self._chunks.values())

    def by_doc(self, doc_id: str) -> list[Chunk]:
        return [self._chunks[c] for c in self._docs.get(doc_id, [])]

    def docs(self) -> list[DocInfo]:
        return [
            DocInfo(doc_id, self._chunks[ids[0]].source, len(ids)) for doc_id, ids in self._docs.items()
        ]

    def __len__(self) -> int:
        return len(self._chunks)

    def __contains__(self, chunk_id: object) -> bool:
        return chunk_id in self._chunks


__all__ = ["ChunkStore", "DocInfo"]
