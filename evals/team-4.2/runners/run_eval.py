"""Chạy evaluation trên index hiện có (chạy tại gốc repo, sau khi đã ingest).

    python evals/team-4.2/runners/run_eval.py                               # retrieval: bm25, dense, hybrid
    python evals/team-4.2/runners/run_eval.py --configs bm25 dense hybrid hybrid+hyde hybrid+rerank all
    python evals/team-4.2/runners/run_eval.py --answers                     # thêm: chạy LLM, đo từ chối

Đầu ra trong --out (mặc định evals/team-4.2/results/<thời gian>/):
    retrieval_per_question.csv   mỗi (câu, cấu hình) một dòng
    summary.md                   bảng Recall@5 / Hit@5 / MRR@5 / Recall@20 theo cấu hình và theo type
    answers.csv                  (--answers) câu trả lời + citation, cột `correct`/`citation_ok` để chấm tay
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rag.config import Settings
from rag.eval.metrics import load_questions, unmatched_gold
from rag.eval.runner import (
    RETRIEVAL_CONFIGS,
    answer_rows,
    refusal_summary,
    retrieval_rows,
    summary_markdown,
    write_csv,
)
from rag.pipeline import RAGPipeline


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", default="evals/team-4.2/datasets/questions.jsonl")
    ap.add_argument("--configs", nargs="+", default=["bm25", "dense", "hybrid"],
                    choices=list(RETRIEVAL_CONFIGS))
    ap.add_argument("--answers", action="store_true", help="chạy cả pipeline.ask (gọi LLM)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    settings = Settings.load()
    if any(RETRIEVAL_CONFIGS[c][1] for c in args.configs) and settings.rerank_backend == "none":
        print("Cấu hình có rerank cần RERANK_BACKEND=jev trong .env", file=sys.stderr)
        return 2
    questions = load_questions(args.questions)
    pipeline = RAGPipeline.from_settings(settings)

    bad = unmatched_gold(questions, pipeline.store.all())
    if bad:
        print(f"CẢNH BÁO: {len(bad)} câu có gold không khớp chunk nào (sai tên file/trang?): {bad}",
              file=sys.stderr)

    out = Path(args.out or f"evals/team-4.2/results/{time.strftime('%Y%m%d-%H%M%S')}")
    rows = retrieval_rows(questions, pipeline.retriever, args.configs, k=settings.top_k, pool_k=settings.rerank_n)
    write_csv(rows, out / "retrieval_per_question.csv")

    header = [
        "# Kết quả evaluation", "",
        f"- Số câu: {len(questions)} ({sum(q.in_scope for q in questions)} trong phạm vi)",
        f"- Index: {len(pipeline.store)} chunk, {len(pipeline.store.docs())} tài liệu",
        f"- Embedding: {settings.embed_model} · LLM: {settings.llm_model} · RRF k={settings.rrf_k} · "
        f"rerank: {settings.rerank_backend} · nâng cao: {settings.advanced or 'không'}", "",
    ]
    body = summary_markdown(rows)
    if args.answers:
        arows = answer_rows(questions, pipeline)
        write_csv(arows, out / "answers.csv")
        body += "\n## Từ chối và context\n\n```json\n" + json.dumps(
            refusal_summary(arows), ensure_ascii=False, indent=2) + "\n```\n"
    (out / "summary.md").write_text("\n".join(header) + body, encoding="utf-8")
    print(body)
    print(f"Đã ghi kết quả vào {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
