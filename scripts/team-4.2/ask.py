"""Hỏi trên dòng lệnh, in câu trả lời, citation và kết quả từng arm (chạy tại gốc repo).

    python scripts/team-4.2/ask.py "Thời giờ làm việc bình thường là bao nhiêu?"
    python scripts/team-4.2/ask.py --mode bm25 "..."        # chỉ chạy một arm (bm25 | dense; dense = HyDE nếu bật)
    python scripts/team-4.2/ask.py --retrieve-only "..."     # không gọi LLM
"""

from __future__ import annotations

import argparse
import sys

from rag.config import Settings
from rag.pipeline import RAGPipeline


def _row(hit, chunks) -> str:
    c = chunks[hit.chunk_id]
    page = f" tr.{c.page_start}" if c.page_start is not None else ""
    preview = " ".join(c.text.split())[:90]
    return f"  {hit.rank:>2}. {hit.score:8.4f}  {c.source}{page}  {preview}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--mode", default="hybrid", help="hybrid | bm25 | dense | arm nâng cao đang bật (vd. splade)")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--retrieve-only", action="store_true", help="chỉ retrieve, không gọi LLM")
    args = ap.parse_args()

    p = RAGPipeline.from_settings(Settings.load())
    chunks = p.retriever.chunks
    if args.retrieve_only:
        res = p.retriever.retrieve(args.query, p.top_k, mode=args.mode, rerank=not args.no_rerank)
    else:
        trace = p.ask_debug(args.query, mode=args.mode, rerank=not args.no_rerank)
        res = trace.retrieval
        print("\n=== TRẢ LỜI ===")
        print(trace.answer.text)
        for c in trace.answer.citations:
            page = f", trang {c.page}" if c.page is not None else ""
            print(f"  [{c.n}] {c.source}{page}: {c.quote}")
        print(f"\n(context: {len(trace.context.blocks)} đoạn, chế độ {trace.context.mode}; "
              f"gọi LLM: {trace.llm_called})")

    for arm, hits in res.arms.items():
        print(f"\n=== {arm.upper()} (top 5/{len(hits)}) ===")
        for h in hits[:5]:
            print(_row(h, chunks))
    print(f"\n=== KẾT QUẢ CUỐI ({'rerank' if res.reranked else res.mode}) ===")
    for h in res.hits:
        print(_row(h, chunks))
    if res.errors:
        print(f"\nCảnh báo, arm lỗi: {res.errors}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
