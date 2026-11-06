"""Soạn NHÁP đáp án mẫu (`reference`) bằng LLM từ text của đúng các trang gold.

    python evals/team-4.2/runners/draft_references.py

Đọc questions.jsonl, ghi questions.draft.jsonl với trường `reference_draft` cho các câu chưa có
`reference`. KHÔNG ghi đè questions.jsonl: người viết câu hỏi đọc lại từng bản nháp, đối chiếu
tài liệu gốc, sửa rồi tự chép vào trường `reference` (xem docs/tech_stack.md mục 3.3).
"""

from __future__ import annotations

import argparse
import sys

from rag.config import Settings
from rag.eval.metrics import load_questions
from rag.eval.runner import draft_reference, write_jsonl
from rag.pipeline import RAGPipeline


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", default="evals/team-4.2/datasets/questions.jsonl")
    ap.add_argument("--out", default="evals/team-4.2/datasets/questions.draft.jsonl")
    args = ap.parse_args()

    pipeline = RAGPipeline.from_settings(Settings.load())
    rows, missing = [], []
    for q in load_questions(args.questions):
        row = q.to_dict()
        if q.in_scope and not q.reference:
            draft = draft_reference(q, pipeline.store, pipeline.llm)
            if draft is None:
                missing.append(q.id)
            row["reference_draft"] = draft
        rows.append(row)
    write_jsonl(rows, args.out)
    print(f"Đã ghi {args.out}. Nhớ kiểm tra thủ công từng `reference_draft` trước khi dùng.")
    if missing:
        print(f"Không tìm thấy text trang gold cho: {missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
