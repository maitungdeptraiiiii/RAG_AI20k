"""HyDE — Hypothetical Document Embeddings (Gao et al., 2022). Bật bằng ADVANCED=hyde.

Câu hỏi của người dùng thường viết bằng lời thường ("nghỉ phép mấy ngày"), còn văn bản luật dùng
thuật ngữ ("nghỉ hằng năm"). HyDE nhờ LLM viết một đoạn TRẢ LỜI GIẢ theo văn phong văn bản luật,
rồi tìm bằng embedding của đoạn đó: đoạn giả gần các đoạn thật về cách diễn đạt hơn câu hỏi gốc.

    arm "dense":  query -> GPT 5.6 Lunar viết đoạn giả -> embed (query + đoạn giả) -> tìm trên index Dense

- HyDE là LUỒNG CHÍNH của arm Dense: bật ADVANCED=hyde thì arm "dense" tìm bằng (câu hỏi + đoạn
  giả), KHÔNG còn arm Dense riêng tìm bằng câu hỏi gốc để gộp RRF. Benchmark 6 bộ luật (11/2026):
  hyde+rerank ≈ dense+hyde+rerank (Recall@5 0.950 / 0.950 trên 40 câu), arm câu-gốc chỉ tốn thêm
  một lần embed mà không giúp. Câu hỏi gốc vẫn nằm trong text embed nên không mất tín hiệu.
- Chỉ dùng cho Dense. BM25 vẫn tìm bằng câu hỏi gốc, để số Điều / thuật ngữ LLM bịa ra trong đoạn
  giả không làm lệch kết quả keyword.
- Đoạn giả có thể sai sự thật — không sao, nó chỉ dùng để tìm, không bao giờ đưa cho người dùng.
- Mỗi câu hỏi tốn thêm 1 lần gọi LLM (có cache). LLM lỗi / trả rỗng thì arm Dense tự lùi về tìm
  bằng câu hỏi gốc (ghi log cảnh báo), không làm hỏng câu hỏi.
- Ablation có / không HyDE: cùng index, chạy eval hai lần với ADVANCED có / không có "hyde"
  (HyDE không đổi nội dung index).
- Rủi ro: câu ngoài phạm vi cũng sinh được đoạn giả "nghe hợp lý" -> cần đo cả tỉ lệ từ chối nhầm.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from rag.advanced.base import Components, Enhancement, register
from rag.schema import LLM, Chunk, Hit, Retriever, nfc

log = logging.getLogger(__name__)

HYDE_SYSTEM = (
    "Bạn viết một đoạn văn GIẢ ĐỊNH trả lời câu hỏi, dùng để tìm kiếm tài liệu. "
    "Viết 3-5 câu tiếng Việt theo văn phong văn bản pháp luật / tài liệu chính thức, dùng thuật ngữ "
    "chuyên ngành mà tài liệu gốc có thể dùng. Không cần chắc chắn đúng, không nêu số hiệu điều luật, "
    "không giải thích, không mở đầu bằng lời dẫn. Chỉ trả về đoạn văn."
)


class HydeRetriever:
    """Bọc arm Dense: tìm bằng (câu hỏi + đoạn giả). build() chuyển thẳng cho Dense bên trong."""

    def __init__(
        self, llm: LLM, dense: Retriever, *, include_query: bool = True, arm: str = "dense",
        fallback: bool = True,
    ) -> None:
        self.llm = llm
        self.dense = dense
        self.include_query = include_query
        self.arm = arm
        self.fallback = fallback

    def build(self, chunks: Iterable[Chunk]) -> None:
        """Index chính là index Dense — ingest qua arm này vẫn ghi vào Dense."""
        self.dense.build(chunks)

    def hypothetical(self, query: str) -> str:
        return nfc(self.llm.complete(HYDE_SYSTEM, f"CÂU HỎI: {query}")).strip()

    def query_text(self, query: str) -> str:
        """Text đem embed. LLM lỗi / rỗng: lùi về câu hỏi gốc (fallback=True) hoặc ném lỗi."""
        try:
            passage = self.hypothetical(query)
            if not passage:
                raise RuntimeError("HyDE: LLM trả đoạn giả rỗng")
        except Exception as e:
            if not self.fallback:
                raise
            log.warning("HyDE lỗi, Dense tìm bằng câu hỏi gốc: %r", e)
            return query
        return f"{query}\n{passage}" if self.include_query else passage

    def search(self, query: str, k: int) -> list[Hit]:
        return [Hit(h.chunk_id, h.score, h.rank, self.arm) for h in self.dense.search(self.query_text(query), k)]


@register("hyde")
def make_hyde(c: Components) -> Enhancement:
    return Enhancement("hyde", wrap_dense=lambda dense: HydeRetriever(c.llm, dense))


__all__ = ["HYDE_SYSTEM", "HydeRetriever", "make_hyde"]
