"""Chạy pipeline trên bộ câu hỏi và xuất dữ liệu theo định dạng mẫu của RAGAS.

    python evals/team-4.2/runners/export_ragas.py --out evals/team-4.2/results/ragas_input.jsonl

Mỗi dòng: {"id", "user_input", "retrieved_contexts", "response", "reference"?}. Bỏ câu out_of_scope
và câu bị từ chối (đo bằng chỉ số guardrail). Bước chấm bằng RAGAS (Faithfulness, Response
Relevancy, Context Recall, Answer Correctness) chạy trên file này sau khi nhóm chốt version
`ragas` — API của RAGAS đổi nhiều giữa các bản nên chưa viết sẵn ở đây.
"""

from __future__ import annotations

import argparse
import sys

from rag.config import Settings
from rag.eval.metrics import load_questions
from rag.eval.runner import ragas_rows, write_jsonl
from rag.pipeline import RAGPipeline


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", default="evals/team-4.2/datasets/questions.jsonl")
    ap.add_argument("--out", default="evals/team-4.2/results/ragas_input.jsonl")
    args = ap.parse_args()

    pipeline = RAGPipeline.from_settings(Settings.load())
    rows = ragas_rows(load_questions(args.questions), pipeline)
    write_jsonl(rows, args.out)
    with_ref = sum(1 for r in rows if "reference" in r)
    print(f"Đã ghi {len(rows)} mẫu vào {args.out} ({with_ref} mẫu có reference)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
