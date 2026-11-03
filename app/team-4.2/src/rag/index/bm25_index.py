"""BM25 (keyword) index — TV2.

Okapi BM25, k1=1.5, b=0.75:

    score(d, q) = Σ_{t ∈ q} idf(t) · tf(t,d)·(k1+1) / (tf(t,d) + k1·(1 − b + b·|d|/avgdl))
    idf(t)      = ln(1 + (N − df(t) + 0.5) / (df(t) + 0.5))

idf dùng dạng "ln(1 + …)" (như Lucene) nên luôn dương. Dạng gốc ln((N − df + 0.5)/(df + 0.5))
(rank_bm25.BM25Okapi) cho idf ≤ 0 khi một từ xuất hiện trong ≥ nửa số chunk — với tài liệu
nhỏ (vài chunk) thì từ khoá đúng bị mất điểm. Vì vậy tự viết thay vì dùng rank_bm25.

Tách từ tiếng Việt bằng pyvi ("tài sản" -> "tài_sản"); query và chunk dùng CÙNG một tokenizer.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path

from rag.schema import Chunk, Hit, nfc

Tokenizer = Callable[[str], list[str]]

_WORD_RE = re.compile(r"\w+", re.UNICODE)   # \w gồm chữ có dấu, số và "_" (nối từ ghép của pyvi)


@lru_cache(maxsize=1)
def _pyvi():
    try:
        from pyvi import ViTokenizer
    except ImportError as e:  # pragma: no cover - phụ thuộc môi trường
        raise RuntimeError("Cần cài pyvi để tách từ tiếng Việt: pip install pyvi") from e
    return ViTokenizer


def pyvi_segment(text: str) -> str:
    """'Quyền sở hữu tài sản' -> 'Quyền sở_hữu tài_sản'."""
    return _pyvi().tokenize(text)


def tokenize_with(segment: Callable[[str], str]) -> Tokenizer:
    """Tạo tokenizer: NFC -> tách từ -> bỏ dấu câu -> chữ thường."""

    def tokenize(text: str) -> list[str]:
        return [t.lower() for t in _WORD_RE.findall(segment(nfc(text)))]

    return tokenize


vi_tokenize: Tokenizer = tokenize_with(pyvi_segment)
"""Tokenizer mặc định: tách từ bằng pyvi."""

syllable_tokenize: Tokenizer = tokenize_with(lambda s: s)
"""Tách theo âm tiết (không dùng pyvi). Dùng cho test hoặc để so sánh với pyvi khi eval."""


class BM25Index:
    """BM25 index trong bộ nhớ, lưu/tải bằng JSON. Thêm chunk nhiều lần không bị nhân đôi."""

    arm = "bm25"
    FORMAT_VERSION = 1

    def __init__(
        self,
        *,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer: Tokenizer | None = None,
        tokenizer_name: str = "pyvi",
    ) -> None:
        if k1 < 0 or not 0 <= b <= 1:
            raise ValueError(f"Tham số BM25 không hợp lệ: k1={k1}, b={b}")
        self.k1, self.b = k1, b
        self.tokenizer_name = tokenizer_name
        self._tokenize = tokenizer or vi_tokenize
        self._ids: list[str] = []
        self._pos: dict[str, int] = {}
        self._lens: list[int] = []
        self._total_len = 0
        self._postings: dict[str, dict[int, int]] = {}   # term -> {doc_idx: tf}

    def __len__(self) -> int:
        return len(self._ids)

    def __contains__(self, chunk_id: object) -> bool:
        return chunk_id in self._pos

    # --- build ---------------------------------------------------------------

    def build(self, chunks: Iterable[Chunk]) -> int:
        """Index thêm chunk; chunk_id đã có thì bỏ qua. Trả số chunk mới được thêm."""
        added = 0
        for c in chunks:
            if c.chunk_id in self._pos:
                continue
            tokens = self._tokenize(c.index_text)   # gồm bối cảnh nếu dùng Contextual Retrieval
            idx = len(self._ids)
            self._ids.append(c.chunk_id)
            self._pos[c.chunk_id] = idx
            self._lens.append(len(tokens))
            self._total_len += len(tokens)
            for term, tf in Counter(tokens).items():
                self._postings.setdefault(term, {})[idx] = tf
            added += 1
        return added

    # --- search --------------------------------------------------------------

    def idf(self, term: str) -> float:
        df = len(self._postings.get(term, ()))
        n = len(self._ids)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int) -> list[Hit]:
        """Top-k chunk có score > 0; hoà điểm thì xếp theo chunk_id để tất định."""
        if k < 1:
            raise ValueError(f"k phải >= 1, nhận {k}")
        n = len(self._ids)
        if n == 0 or self._total_len == 0:
            return []
        avgdl = self._total_len / n

        scores: dict[int, float] = defaultdict(float)
        for term in self._tokenize(query):          # từ lặp trong query được tính lặp (như rank_bm25)
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self.idf(term)
            for idx, tf in postings.items():
                norm = 1 - self.b + self.b * self._lens[idx] / avgdl
                scores[idx] += idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)

        ranked = sorted(
            ((s, i) for i, s in scores.items() if s > 0),
            key=lambda x: (-x[0], self._ids[x[1]]),
        )[:k]
        return [Hit(self._ids[i], s, r, "bm25") for r, (s, i) in enumerate(ranked, start=1)]

    # --- lưu / tải -----------------------------------------------------------

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.FORMAT_VERSION,
            "k1": self.k1,
            "b": self.b,
            "tokenizer": self.tokenizer_name,
            "ids": self._ids,
            "lens": self._lens,
            "postings": {t: [[i, tf] for i, tf in p.items()] for t, p in self._postings.items()},
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)   # ghi file tạm rồi đổi tên: không bị file hỏng nếu đang ghi thì dừng

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        tokenizer: Tokenizer | None = None,
        tokenizer_name: str = "pyvi",
    ) -> BM25Index:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != cls.FORMAT_VERSION:
            raise ValueError(f"BM25 index version {data.get('version')} không hỗ trợ")
        if data["tokenizer"] != tokenizer_name:
            raise ValueError(
                f"Index được build bằng tokenizer {data['tokenizer']!r}, đang tải với {tokenizer_name!r}"
            )
        index = cls(k1=data["k1"], b=data["b"], tokenizer=tokenizer, tokenizer_name=tokenizer_name)
        index._ids = list(data["ids"])
        index._pos = {cid: i for i, cid in enumerate(index._ids)}
        index._lens = list(data["lens"])
        index._total_len = sum(index._lens)
        index._postings = {t: {int(i): int(tf) for i, tf in p} for t, p in data["postings"].items()}
        return index


__all__ = ["BM25Index", "Tokenizer", "pyvi_segment", "syllable_tokenize", "tokenize_with", "vi_tokenize"]
