"""HyDE — Hypothetical Document Embeddings (Gao et al., 2022). Bật bằng ADVANCED=hyde.

Câu hỏi của người dùng thường viết bằng lời thường ("nghỉ phép mấy ngày"), còn văn bản luật dùng
thuật ngữ ("nghỉ hằng năm"). HyDE nhờ LLM viết một đoạn TRẢ LỜI GIẢ theo văn phong văn bản luật,
rồi tìm bằng embedding của đoạn đó: đoạn giả gần các đoạn thật về cách diễn đạt hơn câu hỏi gốc.

    arm "hyde":  query -> GPT 5.6 Lunar viết đoạn giả -> embed (query + đoạn giả) -> tìm trên index Dense

- Thêm thành MỘT ARM RIÊNG, gộp với BM25 + Dense bằng RRF; không thay arm Dense gốc.
- Chỉ dùng cho Dense. BM25 vẫn tìm bằng câu hỏi gốc, để số Điều / thuật ngữ LLM bịa ra trong đoạn
  giả không làm lệch kết quả keyword.
- Đoạn giả có thể sai sự thật — không sao, nó chỉ dùng để tìm, không bao giờ đưa cho người dùng.
- Mỗi câu hỏi tốn thêm 1 lần gọi LLM (có cache). LLM lỗi thì arm này lỗi, HybridRetriever vẫn trả
  kết quả BM25 + Dense.
- Rủi ro: câu ngoài phạm vi cũng sinh được đoạn giả "nghe hợp lý" -> cần đo cả tỉ lệ từ chối nhầm.
"""

from __future__ import annotations

from collections.abc import Iterable

from rag.advanced.base import Components, Enhancement, register
from rag.schema import LLM, Chunk, Hit, Retriever, nfc

HYDE_SYSTEM = (
    "Bạn viết một đoạn văn GIẢ ĐỊNH trả lời câu hỏi, dùng để tìm kiếm tài liệu. "
    "Viết 3-5 câu tiếng Việt theo văn phong văn bản pháp luật / tài liệu chính thức, dùng thuật ngữ "
    "chuyên ngành mà tài liệu gốc có thể dùng. Không cần chắc chắn đúng, không nêu số hiệu điều luật, "
    "không giải thích, không mở đầu bằng lời dẫn. Chỉ trả về đoạn văn."
)


class HydeRetriever:
    arm = "hyde"

    def __init__(self, llm: LLM, dense: Retriever, *, include_query: bool = True) -> None:
        self.llm = llm
        self.dense = dense
        self.include_query = include_query

    def build(self, chunks: Iterable[Chunk]) -> None:
        """Dùng chung index Dense — không index gì thêm."""

    def hypothetical(self, query: str) -> str:
        return nfc(self.llm.complete(HYDE_SYSTEM, f"CÂU HỎI: {query}")).strip()

    def search(self, query: str, k: int) -> list[Hit]:
        passage = self.hypothetical(query)
        if not passage:
            raise RuntimeError("HyDE: LLM trả đoạn giả rỗng")
        text = f"{query}\n{passage}" if self.include_query else passage
        return [Hit(h.chunk_id, h.score, h.rank, self.arm) for h in self.dense.search(text, k)]


@register("hyde")
def make_hyde(c: Components) -> Enhancement:
    return Enhancement("hyde", arms={"hyde": HydeRetriever(c.llm, c.dense)})


__all__ = ["HYDE_SYSTEM", "HydeRetriever", "make_hyde"]
