"""Embedder giả, tất định, không gọi mạng — dùng cho unit test của mọi module."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

from rag.schema import nfc


class HashEmbedder:
    """Băm từng âm tiết vào `dim` chiều rồi chuẩn hoá L2. Chung nhiều âm tiết -> cosine cao.

    Không hiểu nghĩa (không phải embedding thật); chỉ để test luồng dữ liệu không cần mạng.
    """

    def __init__(self, dim: int = 64, model_id: str | None = None) -> None:
        self.dim = dim
        self.model_id = model_id or f"hash-{dim}"
        self.calls: list[list[str]] = []   # để test kiểm tra số lần gọi

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"\w+", nfc(text).lower()):
            h = int(hashlib.sha1(tok.encode("utf-8")).hexdigest()[:8], 16)
            v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]
