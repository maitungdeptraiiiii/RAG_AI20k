"""SPLADE — Sparse Lexical And Expansion (Formal et al., 2021). Bật bằng ADVANCED=splade.

BM25 chỉ khớp đúng từ có trong đoạn. SPLADE dùng một mô hình masked-LM (BERT) để gán trọng số cho
TỪ VỰNG của mô hình: đoạn nói về "nghỉ hằng năm" có thể nhận thêm trọng số cho "phép", "ngày"... dù
đoạn không chứa các từ đó (mở rộng từ), và trọng số từ do mô hình học thay vì đếm tần suất.

    w(t) = max over tokens i of  log(1 + relu(logit_i[t]))      (chỉ giữ w > 0)
    score(q, d) = Σ_t w_q(t) · w_d(t)                           (tích vô hướng hai vector thưa)

    arm "splade":  query -> vector thưa -> tìm trên inverted index (RAM) dựng từ `Chunk.index_text`

- Thêm thành MỘT ARM RIÊNG, gộp với BM25 + Dense bằng RRF; không thay arm nào.
- Index nằm trong RAM và dựng lại mỗi lần khởi động (mã hoá lại mọi chunk) — đủ cho vài nghìn chunk.
- Cần `pip install -e "app/team-4.2[neural]"` (torch + transformers). Mô hình nạp lười: chỉ khi
  bật ADVANCED=splade và bắt đầu build/search.
- Mô hình mặc định (SPLADE_MODEL) là bản TIẾNG ANH; từ vựng của nó không bao phủ tốt tiếng Việt.
  Phải đặt SPLADE_MODEL là một checkpoint SPLADE đa ngữ/tiếng Việt rồi so với BM25 trên tập dev
  trước khi tin kết quả.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from rag.advanced.base import Components, Enhancement, register
from rag.schema import Chunk, Hit, nfc

log = logging.getLogger(__name__)

SparseVec = dict[int, float]


class SparseEncoder(Protocol):
    model_id: str

    def encode(self, texts: Sequence[str], *, is_query: bool = False) -> list[SparseVec]:
        """Một vector thưa {term_id: trọng số > 0} cho mỗi text, cùng thứ tự."""
        ...


class TransformersSpladeEncoder:
    """SPLADE bằng transformers + torch (nạp lười). Chạy CPU hoặc GPU nếu có."""

    def __init__(self, model_id: str, *, batch_size: int = 16, max_length: int = 256, device: str | None = None) -> None:
        self.model_id = model_id
        self.batch_size = batch_size
        self.max_length = max_length
        self.device = device
        self._tok: Any = None
        self._model: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForMaskedLM, AutoTokenizer
        except ImportError as e:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError('SPLADE cần torch + transformers: pip install -e "app/team-4.2[neural]"') from e
        self._torch = torch
        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForMaskedLM.from_pretrained(self.model_id).to(device).eval()
        self.device = device

    def encode(self, texts: Sequence[str], *, is_query: bool = False) -> list[SparseVec]:
        self._load()
        torch = self._torch
        out: list[SparseVec] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [nfc(t) for t in texts[i : i + self.batch_size]]
            enc = self._tok(batch, padding=True, truncation=True, max_length=self.max_length, return_tensors="pt")
            enc = {k: v.to(self.device) for k, v in enc.items()}
            with torch.no_grad():
                logits = self._model(**enc).logits                      # (B, L, V)
            weights = torch.log1p(torch.relu(logits)) * enc["attention_mask"].unsqueeze(-1)
            pooled = weights.max(dim=1).values                           # (B, V)
            for row in pooled:
                idx = torch.nonzero(row > 0).squeeze(-1).tolist()
                vals = row[idx].tolist() if idx else []
                out.append({int(t): float(w) for t, w in zip(idx, vals, strict=True)})
        return out


class SpladeIndex:
    """Inverted index trong RAM trên vector thưa SPLADE."""

    arm = "splade"

    def __init__(self, encoder: SparseEncoder) -> None:
        self.encoder = encoder
        self._ids: set[str] = set()
        self._chunk_ids: list[str] = []
        self._postings: dict[int, list[tuple[int, float]]] = defaultdict(list)

    def __len__(self) -> int:
        return len(self._chunk_ids)

    def build(self, chunks: Iterable[Chunk]) -> None:
        new = [c for c in dict.fromkeys(chunks) if c.chunk_id not in self._ids]
        if not new:
            return
        vectors = self.encoder.encode([c.index_text for c in new])
        if len(vectors) != len(new):
            raise RuntimeError(f"SPLADE: encoder trả {len(vectors)} vector cho {len(new)} chunk")
        for chunk, vec in zip(new, vectors, strict=True):
            doc = len(self._chunk_ids)
            self._chunk_ids.append(chunk.chunk_id)
            self._ids.add(chunk.chunk_id)
            for term, w in vec.items():
                self._postings[term].append((doc, w))
        log.info("SPLADE: index thêm %d chunk (tổng %d)", len(new), len(self))

    def search(self, query: str, k: int) -> list[Hit]:
        if k < 1 or not self._chunk_ids:
            return []
        q = self.encoder.encode([nfc(query)], is_query=True)[0]
        scores: dict[int, float] = defaultdict(float)
        for term, qw in q.items():
            for doc, dw in self._postings.get(term, ()):
                scores[doc] += qw * dw
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return [Hit(self._chunk_ids[d], s, r, self.arm) for r, (d, s) in enumerate(ranked, start=1)]


@register("splade")
def make_splade(c: Components) -> Enhancement:
    return Enhancement("splade", arms={"splade": SpladeIndex(TransformersSpladeEncoder(c.settings.splade_model))})


__all__ = ["SparseEncoder", "SpladeIndex", "TransformersSpladeEncoder", "make_splade"]
