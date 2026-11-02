"""Vector (dense) index — TV3.

    VectorIndex          build(chunks) / search(query, k) -> Hit(arm="dense"), score = cosine.
    QdrantVectorStore    Qdrant local mode (chạy trong tiến trình, không cần server), cosine.
    InMemoryVectorStore  lưu trong RAM, dùng cho unit test.

Đổi model embedding thì vector cũ không so được với vector mới: file `meta.json` cạnh index ghi
lại model + số chiều, mở index bằng model khác sẽ báo lỗi thay vì trộn lẫn.
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from rag.index.embedder import Embedder
from rag.schema import Chunk, Hit, nfc

_POINT_NS = uuid.UUID("6f1c2a9e-3b8d-4d6a-9a51-2a7f0d4e8c10")


class IndexMismatchError(RuntimeError):
    """Index trên đĩa được build bằng model/số chiều khác cấu hình hiện tại."""


class VectorStore(Protocol):
    def has(self, chunk_ids: Sequence[str]) -> set[str]: ...
    def upsert(self, chunk_ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None: ...
    def query(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]: ...
    def count(self) -> int: ...


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._vecs: dict[str, list[float]] = {}

    @staticmethod
    def _unit(v: Sequence[float]) -> list[float]:
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def has(self, chunk_ids: Sequence[str]) -> set[str]:
        return {c for c in chunk_ids if c in self._vecs}

    def upsert(self, chunk_ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        for cid, v in zip(chunk_ids, vectors, strict=True):
            self._vecs[cid] = self._unit(v)

    def query(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]:
        q = self._unit(vector)
        scored = [(cid, sum(a * b for a, b in zip(q, v))) for cid, v in self._vecs.items()]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]

    def count(self) -> int:
        return len(self._vecs)


class QdrantVectorStore:
    """Qdrant local mode. Chỉ MỘT tiến trình được mở cùng thư mục `path` tại một thời điểm."""

    def __init__(
        self, path: Path | str | None, dim: int, *, collection: str = "chunks", client: Any = None
    ) -> None:
        from qdrant_client import QdrantClient, models

        self._models = models
        self.collection = collection
        if client is not None:
            self.client = client
        elif path is None:
            self.client = QdrantClient(location=":memory:")
        else:
            Path(path).mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(path))

        if not self.client.collection_exists(collection):
            self.client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )
        else:
            size = self.client.get_collection(collection).config.params.vectors.size
            if size != dim:
                raise IndexMismatchError(f"Collection {collection!r} có {size} chiều, cấu hình dim={dim}")

    @staticmethod
    def point_id(chunk_id: str) -> str:
        """Qdrant chỉ nhận id là số nguyên hoặc UUID -> UUID5 tất định từ chunk_id."""
        return str(uuid.uuid5(_POINT_NS, chunk_id))

    def has(self, chunk_ids: Sequence[str]) -> set[str]:
        if not chunk_ids:
            return set()
        points = self.client.retrieve(
            collection_name=self.collection,
            ids=[self.point_id(c) for c in chunk_ids],
            with_payload=True,
            with_vectors=False,
        )
        return {p.payload["chunk_id"] for p in points}

    def upsert(self, chunk_ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        points = [
            self._models.PointStruct(id=self.point_id(cid), vector=list(v), payload={"chunk_id": cid})
            for cid, v in zip(chunk_ids, vectors, strict=True)
        ]
        if points:
            self.client.upsert(collection_name=self.collection, points=points)

    def query(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]:
        res = self.client.query_points(
            collection_name=self.collection, query=list(vector), limit=k, with_payload=True
        )
        return [(p.payload["chunk_id"], float(p.score)) for p in res.points]

    def count(self) -> int:
        return self.client.count(collection_name=self.collection).count


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


class VectorIndex:
    arm = "dense"

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore | None = None,
        *,
        meta_path: Path | str | None = None,
        batch_size: int = 256,
    ) -> None:
        self.embedder = embedder
        self.store = store if store is not None else InMemoryVectorStore()
        self.batch_size = batch_size
        if meta_path is not None:
            self._check_meta(Path(meta_path))

    @classmethod
    def open_qdrant(cls, index_dir: Path | str, embedder: Embedder, **kwargs: Any) -> VectorIndex:
        """Mở (hoặc tạo) index tại `index_dir`: qdrant ở `index_dir/qdrant`, meta ở `index_dir/meta.json`."""
        index_dir = Path(index_dir)
        meta_path = index_dir / "meta.json"
        cls._check_meta_file(meta_path, embedder)        # kiểm tra TRƯỚC khi mở Qdrant
        store = QdrantVectorStore(index_dir / "qdrant", embedder.dim)
        return cls(embedder, store, **kwargs)

    @staticmethod
    def _check_meta_file(path: Path, embedder: Embedder) -> None:
        want = {"embed_model": embedder.model_id, "dim": embedder.dim}
        if path.exists():
            have = json.loads(path.read_text(encoding="utf-8"))
            if have != want:
                raise IndexMismatchError(
                    f"Index tại {path.parent} được build bằng {have}, cấu hình hiện tại là {want}. "
                    "Xoá thư mục index để build lại."
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(want), encoding="utf-8")

    def _check_meta(self, path: Path) -> None:
        self._check_meta_file(path, self.embedder)

    def __len__(self) -> int:
        return self.store.count()

    def build(self, chunks: Iterable[Chunk]) -> int:
        """Embed + lưu các chunk chưa có trong index. Trả số chunk mới được thêm."""
        unique: dict[str, Chunk] = {}
        for c in chunks:
            unique.setdefault(c.chunk_id, c)
        ids = list(unique)
        existing: set[str] = set()
        for start in range(0, len(ids), self.batch_size):
            existing |= self.store.has(ids[start : start + self.batch_size])
        new = [unique[c] for c in ids if c not in existing]

        for start in range(0, len(new), self.batch_size):
            batch = new[start : start + self.batch_size]
            vectors = self.embedder.embed([c.text for c in batch])
            self.store.upsert([c.chunk_id for c in batch], vectors)
        return len(new)

    def search(self, query: str, k: int) -> list[Hit]:
        if k < 1:
            raise ValueError(f"k phải >= 1, nhận {k}")
        q = nfc(query).strip()
        if not q or self.store.count() == 0:
            return []
        vector = self.embedder.embed([q])[0]
        return [
            Hit(cid, score, rank, "dense")
            for rank, (cid, score) in enumerate(self.store.query(vector, k), start=1)
        ]


__all__ = [
    "InMemoryVectorStore",
    "IndexMismatchError",
    "QdrantVectorStore",
    "VectorIndex",
    "VectorStore",
]
