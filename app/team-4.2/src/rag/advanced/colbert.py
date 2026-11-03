"""ColBERT — late interaction (Khattab & Zaharia, 2020). Bật bằng ADVANCED=colbert.

Dense thường nén cả đoạn thành MỘT vector nên mất chi tiết. ColBERT giữ MỘT VECTOR CHO MỖI TOKEN và
so khớp ở mức token (MaxSim): mỗi token câu hỏi lấy điểm của token đoạn giống nó nhất, rồi cộng lại.

    score(q, d) = Σ_{i ∈ tokens(q)}  max_{j ∈ tokens(d)}  cos(q_i, d_j)

    arm "colbert":  query -> vector theo token -> MaxSim với MỌI chunk (brute force, RAM)

- Thêm thành MỘT ARM RIÊNG, gộp với BM25 + Dense bằng RRF; không thay arm nào.
- Brute force Python thuần: chi phí ~ (số token query) × (tổng số token mọi chunk). Chấp nhận được
  cho vài trăm đến vài nghìn chunk; lớn hơn thì cần PLAID/FAISS, không làm ở sprint này.
- Index trong RAM, dựng lại mỗi lần khởi động. Vector theo token tốn bộ nhớ ~ hidden_size × số token.
- Cần `pip install -e "app/team-4.2[neural]"`. Mô hình nạp lười.
- Encoder mặc định lấy hidden state cuối của checkpoint (COLBERT_MODEL) rồi chuẩn hoá L2, KHÔNG có
  lớp chiếu và query augmentation của ColBERT gốc. Muốn đúng chuẩn ColBERT, viết một MultiVectorEncoder
  khác (vd. bọc PyLate) và thay trong make_colbert. Mô hình mặc định là bản tiếng Anh: cần đặt
  COLBERT_MODEL là mô hình đa ngữ/tiếng Việt và so với Dense trên tập dev.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from rag.advanced.base import Components, Enhancement, register
from rag.schema import Chunk, Hit, nfc

log = logging.getLogger(__name__)

TokenVecs = list[list[float]]


class MultiVectorEncoder(Protocol):
    model_id: str

    def encode(self, texts: Sequence[str], *, is_query: bool = False) -> list[TokenVecs]:
        """Mỗi text -> danh sách vector (đã chuẩn hoá L2), một vector cho mỗi token."""
        ...


class TransformersColbertEncoder:
    """Vector theo token từ hidden state cuối của transformers (nạp lười)."""

    def __init__(self, model_id: str, *, batch_size: int = 8, doc_max_length: int = 512,
                 query_max_length: int = 64, device: str | None = None) -> None:
        self.model_id = model_id
        self.batch_size = batch_size
        self.doc_max_length = doc_max_length
        self.query_max_length = query_max_length
        self.device = device
        self._tok: Any = None
        self._model: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as e:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError('ColBERT cần torch + transformers: pip install -e "app/team-4.2[neural]"') from e
        self._torch = torch
        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModel.from_pretrained(self.model_id).to(device).eval()
        self.device = device

    def encode(self, texts: Sequence[str], *, is_query: bool = False) -> list[TokenVecs]:
        self._load()
        torch = self._torch
        max_length = self.query_max_length if is_query else self.doc_max_length
        out: list[TokenVecs] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [nfc(t) for t in texts[i : i + self.batch_size]]
            enc = self._tok(batch, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
            enc = {k: v.to(self.device) for k, v in enc.items()}
            with torch.no_grad():
                hidden = self._model(**enc).last_hidden_state              # (B, L, H)
            hidden = torch.nn.functional.normalize(hidden, dim=-1)
            mask = enc["attention_mask"].bool()
            for vecs, m in zip(hidden, mask, strict=True):
                out.append(vecs[m].tolist())
        return out


def maxsim(query: TokenVecs, doc: TokenVecs) -> float:
    """Σ_i max_j q_i·d_j (vector đã chuẩn hoá nên tích vô hướng = cosine)."""
    if not doc:
        return 0.0
    return sum(max(sum(a * b for a, b in zip(q, d, strict=True)) for d in doc) for q in query)


class ColbertIndex:
    arm = "colbert"

    def __init__(self, encoder: MultiVectorEncoder) -> None:
        self.encoder = encoder
        self._docs: dict[str, TokenVecs] = {}

    def __len__(self) -> int:
        return len(self._docs)

    def build(self, chunks: Iterable[Chunk]) -> None:
        new = [c for c in dict.fromkeys(chunks) if c.chunk_id not in self._docs]
        if not new:
            return
        vectors = self.encoder.encode([c.index_text for c in new])
        if len(vectors) != len(new):
            raise RuntimeError(f"ColBERT: encoder trả {len(vectors)} kết quả cho {len(new)} chunk")
        for chunk, vecs in zip(new, vectors, strict=True):
            self._docs[chunk.chunk_id] = vecs
        log.info("ColBERT: index thêm %d chunk (tổng %d)", len(new), len(self))

    def search(self, query: str, k: int) -> list[Hit]:
        if k < 1 or not self._docs:
            return []
        q = self.encoder.encode([nfc(query)], is_query=True)[0]
        if not q:
            return []
        scored = [(cid, maxsim(q, vecs)) for cid, vecs in self._docs.items()]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return [Hit(cid, s, r, self.arm) for r, (cid, s) in enumerate(scored[:k], start=1)]


@register("colbert")
def make_colbert(c: Components) -> Enhancement:
    return Enhancement("colbert", arms={"colbert": ColbertIndex(TransformersColbertEncoder(c.settings.colbert_model))})


__all__ = ["ColbertIndex", "MultiVectorEncoder", "TransformersColbertEncoder", "make_colbert", "maxsim"]
