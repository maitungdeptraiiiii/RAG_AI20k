"""Gộp các chunk cùng một Điều thành MỘT candidate — TV2.

Điều luật dài bị chunker cắt thành nhiều chunk (vd. Điều 134 BLHS). Không gộp thì top 5 có thể là
3 chunk của cùng Điều 134, đẩy điều thứ hai (vd. Điều 13) ra ngoài. Sau khi gộp:

- Mỗi Điều chỉ còn một Hit, ở vị trí của chunk xếp hạng cao nhất; giữ nguyên score / arm của chunk
  đó. Các chunk còn lại của Điều ghi vào `Hit.merged`. Rank đánh lại 1..n liên tục.
- Khoá gộp = (doc_id, section) và CHỈ khi mục cuối của section là "Điều N." Chunk không thuộc Điều
  nào (phần mở đầu văn bản, header Công báo bị nhận nhầm là "Phần ...", tài liệu thường không có
  heading) thì là candidate riêng.

Vì sao khoá này đúng (đã kiểm tra trên 3422 chunk của 6 bộ luật, 11/2026): chunker luôn mở chunk
mới ở dòng "Điều N." và không overlap qua ranh giới Điều, nên một chunk không bao giờ chứa hai
Điều, và mọi chunk cùng (doc_id, section Điều) nằm liên tiếp nhau.

Overlap: trong cùng một Điều, chunk sau thường lặp lại đoạn cuối của chunk trước (overlap 1 đoạn).
`merged_chunk` ghép các chunk theo thứ tự trong văn bản và BỎ đoạn lặp đó; giữa hai chunk không
liền kề thì chèn "[...]".
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import replace

from rag.schema import Chunk, Hit

_ARTICLE_RE = re.compile(r"^Điều\s+\d+[a-zđ]?\s*[.:]", re.IGNORECASE)
GAP = "[...]"


def article_key(chunk: Chunk) -> tuple[str, ...]:
    """(doc_id, section) nếu chunk thuộc một Điều; không thì khoá riêng theo chunk_id (không gộp)."""
    if chunk.section and _ARTICLE_RE.match(chunk.section.rsplit(" > ", 1)[-1].strip()):
        return ("article", chunk.doc_id, chunk.section)
    return ("chunk", chunk.chunk_id)


def merge_by_article(hits: Sequence[Hit], chunks: Mapping[str, Chunk]) -> list[Hit]:
    """Gộp các Hit cùng Điều, giữ thứ tự của Hit đầu tiên mỗi Điều; rank đánh lại 1..n."""
    order: list[tuple[str, ...]] = []
    first: dict[tuple[str, ...], Hit] = {}
    extra: dict[tuple[str, ...], list[str]] = {}
    for h in hits:
        chunk = chunks.get(h.chunk_id)
        key = article_key(chunk) if chunk is not None else ("chunk", h.chunk_id)
        if key not in first:
            order.append(key)
            first[key] = h
            extra[key] = [c for c in h.merged if c != h.chunk_id]
            continue
        for cid in (h.chunk_id, *h.merged):
            if cid != first[key].chunk_id and cid not in extra[key]:
                extra[key].append(cid)
    return [
        replace(first[key], rank=rank, merged=tuple(extra[key]))
        for rank, key in enumerate(order, start=1)
    ]


def take_articles(hits: Sequence[Hit], chunks: Mapping[str, Chunk], n: int) -> list[Hit]:
    """Giữ các Hit thuộc n Điều xuất hiện đầu tiên (giữ thứ tự, giữ MỌI chunk của các Điều đó).

    Dùng để dựng pool rerank theo Điều: lấy dư chunk từ các arm rồi cắt ở n Điều khác nhau, thay vì
    n chunk (n chunk có thể chỉ là ~12-15 Điều vì Điều dài bị chia nhiều chunk).
    """
    keep: set[tuple[str, ...]] = set()
    out: list[Hit] = []
    for h in hits:
        chunk = chunks.get(h.chunk_id)
        key = article_key(chunk) if chunk is not None else ("chunk", h.chunk_id)
        if key not in keep:
            if len(keep) >= n:
                continue
            keep.add(key)
        out.append(h)
    return out


def _index(chunk: Chunk) -> int:
    """Số thứ tự chunk trong tài liệu (chunk_id = '<doc_id>:<NNNN>')."""
    tail = chunk.chunk_id.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else -1


def merged_chunk(hit: Hit, chunks: Mapping[str, Chunk]) -> Chunk:
    """Chunk đại diện cho cả Điều: text các chunk đã gộp theo thứ tự văn bản, bỏ đoạn overlap.

    Giữ chunk_id / source / section của chunk đại diện (hit.chunk_id) để citation và chấm gold
    không đổi; page_start / page_end mở rộng theo các chunk đã gộp.
    """
    head = chunks[hit.chunk_id]
    if not hit.merged:
        return head
    parts = sorted({c.chunk_id: c for c in (head, *(chunks[m] for m in hit.merged))}.values(), key=_index)
    lines: list[str] = []
    prev: Chunk | None = None
    for c in parts:
        cur = c.text.split("\n")
        if prev is not None:
            if _index(c) == _index(prev) + 1:
                # overlap 1 đoạn: dòng đầu của chunk sau = dòng cuối của chunk trước
                if cur and lines and cur[0] == lines[-1]:
                    cur = cur[1:]
            else:
                lines.append(GAP)
        lines.extend(cur)
        prev = c
    pages = [p for c in parts for p in (c.page_start, c.page_end) if p is not None]
    return replace(
        head,
        text="\n".join(lines),
        page_start=min(pages) if pages else head.page_start,
        page_end=max(pages) if pages else head.page_end,
    )


__all__ = ["GAP", "article_key", "merge_by_article", "merged_chunk", "take_articles"]
