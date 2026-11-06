"""Contextual Retrieval (Anthropic, 2024 — có trong tài liệu tham khảo của sprint).

Chunk bị cắt ra khỏi tài liệu thường mất bối cảnh: "Thời hạn là 30 ngày" không nói thời hạn của
việc gì, thuộc luật nào. Trước khi index, thêm một đoạn bối cảnh ngắn vào `Chunk.context`; BM25 và
Dense index `context + text`, còn text gốc giữ nguyên để hiển thị, đưa cho LLM và trích dẫn.

Hai biến thể, bật độc lập (có thể bật cả hai, theo thứ tự trong ADVANCED):

    ADVANCED=contextual_header   Không gọi LLM: bối cảnh = tên tài liệu + heading (`section`).
                                 Miễn phí; nên thử trước.
    ADVANCED=contextual          GPT 5.6 Lunar viết 1-2 câu bối cảnh cho từng chunk, dựa trên phần
                                 đầu tài liệu + heading + đoạn liền trước/sau. Tốn 1 lần gọi LLM mỗi
                                 chunk lúc ingest (có cache; chunk lưu kèm context nên khởi động lại
                                 không gọi lại).

Bài gốc đưa TOÀN BỘ tài liệu vào prompt cho mỗi chunk; văn bản luật dài hàng trăm trang nên ở đây
chỉ đưa phần đầu tài liệu (`doc_chars`) + đoạn lân cận. Phần đầu giống nhau cho mọi chunk của cùng
tài liệu và đứng đầu prompt, để tận dụng prompt caching tự động của API (nếu nhà cung cấp hỗ trợ).

Đổi phương pháp index (bật/tắt contextual) thì phải ingest lại vào index mới — pipeline kiểm tra
và báo lỗi nếu index cũ được build với cấu hình khác.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePath

from rag.advanced.base import Components, Enhancement, add_context, register
from rag.schema import LLM, Chunk, Page, nfc

log = logging.getLogger(__name__)

CONTEXT_SYSTEM = (
    "Bạn giúp cải thiện tìm kiếm tài liệu. Cho phần đầu một tài liệu và một đoạn trích từ tài liệu đó, "
    "hãy viết 1-2 câu tiếng Việt ngắn gọn nêu bối cảnh của đoạn trích: thuộc văn bản nào, chương/điều "
    "nào, nói về chủ đề gì, các đại từ như 'này', 'đó' chỉ cái gì. Chỉ trả lời phần bối cảnh, không "
    "nhắc lại nội dung đoạn trích, không thêm thông tin không có trong tài liệu."
)


def _doc_title(source: str) -> str:
    if source.startswith(("http://", "https://")):
        return source
    return PurePath(source).stem.replace("_", " ").replace("-", " ")


class SectionHeaderEnricher:
    """contextual_header: bối cảnh = tên tài liệu + heading. Không gọi LLM."""

    name = "contextual_header"

    def enrich(self, chunks: list[Chunk], pages: Sequence[Page]) -> list[Chunk]:
        out = []
        for c in chunks:
            parts = [f"Tài liệu: {_doc_title(c.source)}"]
            if c.section:
                parts.append(f"Mục: {c.section}")
            out.append(add_context(c, ". ".join(parts)))
        return out


class ArticleHeaderEnricher:
    """article_header: bối cảnh = tên tài liệu + heading CUỐI (thường là "Điều N. Tên điều").

    Gọn hơn contextual_header: bỏ Phần/Chương vì chuỗi đó giống nhau ở hàng chục Điều, dễ gây nhiễu.
    """

    name = "article_header"

    def enrich(self, chunks: list[Chunk], pages: Sequence[Page]) -> list[Chunk]:
        out = []
        for c in chunks:
            parts = [_doc_title(c.source)]
            if c.section:
                parts.append(c.section.split(">")[-1].strip())
            out.append(add_context(c, ". ".join(parts)))
        return out


class LLMContextEnricher:
    """contextual: LLM viết bối cảnh cho từng chunk, chạy song song."""

    name = "contextual"

    def __init__(
        self,
        llm: LLM,
        *,
        doc_chars: int = 4000,
        neighbor_chars: int = 600,
        max_workers: int = 8,
    ) -> None:
        if doc_chars < 1 or neighbor_chars < 0 or max_workers < 1:
            raise ValueError("doc_chars >= 1, neighbor_chars >= 0, max_workers >= 1")
        self.llm = llm
        self.doc_chars = doc_chars
        self.neighbor_chars = neighbor_chars
        self.max_workers = max_workers

    def _doc_head(self, pages: Sequence[Page]) -> str:
        text = "\n".join(p.text for p in pages if not p.is_empty)
        return text[: self.doc_chars]

    def build_prompt(self, doc_head: str, chunks: Sequence[Chunk], i: int) -> str:
        c = chunks[i]
        n = self.neighbor_chars
        parts = [f"<tài_liệu nguồn=\"{c.source}\">\n{doc_head}\n</tài_liệu>"]   # giống nhau cho cả tài liệu
        if c.section:
            parts.append(f"Heading của đoạn: {c.section}")
        if n and i > 0:
            parts.append(f"Đoạn liền trước:\n{chunks[i - 1].text[-n:]}")
        if n and i + 1 < len(chunks):
            parts.append(f"Đoạn liền sau:\n{chunks[i + 1].text[:n]}")
        parts.append(f"<đoạn_trích>\n{c.text}\n</đoạn_trích>")
        return "\n\n".join(parts)

    def enrich(self, chunks: list[Chunk], pages: Sequence[Page]) -> list[Chunk]:
        if not chunks:
            return []
        head = self._doc_head(pages)

        def one(i: int) -> str | None:
            try:
                return nfc(self.llm.complete(CONTEXT_SYSTEM, self.build_prompt(head, chunks, i))).strip()
            except Exception as e:  # noqa: BLE001 — một chunk lỗi thì bỏ bối cảnh chunk đó
                log.warning("contextual: chunk %s lỗi: %r", chunks[i].chunk_id, e)
                return None

        workers = min(self.max_workers, len(chunks))
        if workers == 1:
            contexts = [one(i) for i in range(len(chunks))]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                contexts = list(pool.map(one, range(len(chunks))))

        failed = sum(1 for x in contexts if x is None)
        if failed == len(chunks):
            raise RuntimeError("contextual: LLM lỗi ở mọi chunk (kiểm tra key / model / mạng)")
        if failed:
            log.warning("contextual: %d/%d chunk không có bối cảnh do LLM lỗi", failed, len(chunks))
        return [add_context(c, ctx) for c, ctx in zip(chunks, contexts)]


@register("contextual_header")
def make_contextual_header(c: Components) -> Enhancement:
    return Enhancement("contextual_header", index_enhancer=SectionHeaderEnricher())


@register("article_header")
def make_article_header(c: Components) -> Enhancement:
    return Enhancement("article_header", index_enhancer=ArticleHeaderEnricher())


@register("contextual")
def make_contextual(c: Components) -> Enhancement:
    return Enhancement("contextual", index_enhancer=LLMContextEnricher(c.llm))


__all__ = ["CONTEXT_SYSTEM", "ArticleHeaderEnricher", "LLMContextEnricher", "SectionHeaderEnricher"]
