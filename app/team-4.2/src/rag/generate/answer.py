"""Generation + Citation — TV4.

    format_context(blocks)            "[n] (nguồn, trang p, mục)\\n<text>" cho từng đoạn
    build_prompt(query, blocks)       (system, user) gửi LLM
    generate(query, blocks, llm)      text có [n]
    build_citations(text, blocks)     Answer với list[Citation] — chỉ nhận [n] có trong context

Guardrail (TV5, chưa làm) sẽ chặn trước LLM khi context rỗng/điểm thấp và sau LLM khi không còn
citation hợp lệ. Ở đây `build_citations` chỉ bỏ qua [n] không tồn tại, KHÔNG sửa text trả lời.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from rag.generate.llm import LLM
from rag.schema import REFUSAL, Answer, Citation, ContextBlock, Hit, nfc

SYSTEM_PROMPT = f"""Bạn là trợ lý hỏi đáp dựa trên tài liệu.
Quy tắc bắt buộc:
1. Chỉ trả lời dựa trên các đoạn tài liệu được cung cấp. Không dùng kiến thức bên ngoài, không suy diễn vượt quá nội dung các đoạn.
2. Trả lời thẳng vào câu hỏi ngay ở câu đầu, bằng tiếng Việt, ngắn gọn.
3. Sau mỗi ý lấy từ tài liệu, ghi số đoạn nguồn trong ngoặc vuông, ví dụ [1] hoặc [1][3]. Chỉ dùng các số đoạn có trong phần TÀI LIỆU.
4. Nếu các đoạn không chứa thông tin để trả lời, chỉ viết đúng câu: {REFUSAL}"""

_CITE_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
QUOTE_CHARS = 200


def _label(block: ContextBlock) -> str:
    c = block.chunk
    parts = [c.source]
    if c.page_start is not None:
        parts.append(
            f"trang {c.page_start}" if c.page_start == c.page_end else f"trang {c.page_start}-{c.page_end}"
        )
    if c.section:
        parts.append(c.section)
    return f"[{block.n}] ({', '.join(parts)})"


def format_context(blocks: Sequence[ContextBlock]) -> str:
    return "\n\n".join(f"{_label(b)}\n{b.chunk.text}" for b in blocks)


def build_prompt(query: str, blocks: Sequence[ContextBlock]) -> tuple[str, str]:
    user = f"TÀI LIỆU:\n{format_context(blocks)}\n\nCÂU HỎI: {nfc(query).strip()}"
    return SYSTEM_PROMPT, user


def generate(query: str, blocks: Sequence[ContextBlock], llm: LLM) -> str:
    system, user = build_prompt(query, blocks)
    return nfc(llm.complete(system, user)).strip()


def cited_numbers(text: str) -> list[int]:
    """Các số [n] theo thứ tự xuất hiện, không trùng. Hỗ trợ [1], [1][2], [1, 2]."""
    seen: list[int] = []
    for group in _CITE_RE.findall(text):
        for num in re.split(r"\s*[,;]\s*", group):
            n = int(num)
            if n not in seen:
                seen.append(n)
    return seen


def is_refusal(text: str) -> bool:
    return nfc(text).strip().rstrip(".").casefold() == REFUSAL.rstrip(".").casefold()


def _quote(block: ContextBlock) -> str:
    text = " ".join(block.chunk.text.split())
    return text if len(text) <= QUOTE_CHARS else text[:QUOTE_CHARS].rsplit(" ", 1)[0] + " …"


def build_citations(text: str, blocks: Sequence[ContextBlock], hits: Sequence[Hit] = ()) -> Answer:
    """Ánh xạ [n] -> Citation (nguồn, trang, trích đoạn). [n] ngoài phạm vi bị bỏ qua."""
    if is_refusal(text):
        return Answer.refusal(list(hits))
    by_n = {b.n: b for b in blocks}
    citations = [
        Citation.from_block(by_n[n], quote=_quote(by_n[n])) for n in cited_numbers(text) if n in by_n
    ]
    return Answer(text=text, citations=citations, refused=False, hits=list(hits))


def answer_question(
    query: str, blocks: Sequence[ContextBlock], llm: LLM, hits: Sequence[Hit] = ()
) -> Answer:
    return build_citations(generate(query, blocks, llm), blocks, hits)


__all__ = [
    "SYSTEM_PROMPT",
    "answer_question",
    "build_citations",
    "build_prompt",
    "cited_numbers",
    "format_context",
    "generate",
    "is_refusal",
]
