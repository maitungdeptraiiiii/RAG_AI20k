"""Chuẩn bị benchmark tuần 2 từ ``benchmark_doi_thuong``.

Không sửa bộ 64 câu gốc để các kết quả tuần 1 vẫn tái lập được. File sinh ra:

* tách ``dev``/``test`` một cách xác định;
* giữ toàn bộ 27 câu ``multi`` trong test cho pilot agent multi-hop;
* thay gold phụ thuộc chunk bằng bằng chứng ổn định ``source`` + ``section``;
* thêm câu ``out_of_scope`` không có gold;
* tạo hàng đợi chấm tay từ một ``answers.csv`` có sẵn.

Chạy tại gốc repo:
    python evals/team-4.2/runners/prepare_w02_benchmark.py
"""

from __future__ import annotations

import argparse
import csv
import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = ROOT / "evals/team-4.2/datasets/benchmark_doi_thuong.jsonl"
DEFAULT_OUTPUT = ROOT / "evals/team-4.2/datasets/benchmark_doi_thuong_w02.jsonl"
DEFAULT_ANSWERS = ROOT / "evals/team-4.2/results/bench6-40q-gpt6luna/answers.csv"
DEFAULT_REVIEW = ROOT / "evals/team-4.2/results/w02-carryover/bench6-40q-gpt6luna_manual_review.csv"


OUT_OF_SCOPE = (
    ("oos01", "Hôm nay giá vàng SJC bao nhiêu một lượng?"),
    ("oos02", "Tôi muốn làm hộ chiếu online thì nộp hồ sơ ở đâu?"),
    ("oos03", "Đất nhà tôi bị thu hồi thì năm nay được bồi thường thế nào?"),
    ("oos04", "Lịch thi bằng lái xe máy ở Hà Nội tuần này có ngày nào?"),
    ("oos05", "Trường công thu những khoản nào cho năm học tới?"),
    ("oos06", "Quy định xử phạt giao thông mới nhất vừa có hiệu lực là gì?"),
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assign_split(record: dict, paraphrase_index: int) -> str:
    """27 multi phải nằm ở test; cứ 4 paraphrase chọn 1 câu test."""
    if record["type"] == "multi":
        return "test"
    return "test" if paraphrase_index % 4 == 0 else "dev"


def build_records(source: list[dict]) -> list[dict]:
    output: list[dict] = []
    paraphrase_index = 0
    for original in source:
        record = deepcopy(original)
        record.pop("gold_chunk_ids", None)
        if record["type"] == "paraphrase":
            paraphrase_index += 1
        record.update({
            "benchmark_version": "doi-thuong-w02.v1",
            "data_snapshot": "benchmark_6_bo_luat:week-01-baseline",
            "gold_schema": "source_section.v1",
            "evidence": deepcopy(record.get("gold", [])),
            "expected_behavior": "answer",
            "split": assign_split(record, paraphrase_index),
        })
        output.append(record)

    for index, (question_id, question) in enumerate(OUT_OF_SCOPE):
        output.append({
            "id": question_id,
            "question": question,
            "type": "out_of_scope",
            "author": "TV5",
            "style": "out_of_corpus",
            "benchmark_version": "doi-thuong-w02.v1",
            "data_snapshot": "benchmark_6_bo_luat:week-01-baseline",
            "gold_schema": "source_section.v1",
            "gold": [],
            "evidence": [],
            "reference": "Ngoài phạm vi sáu Bộ luật trong snapshot; hệ thống phải nói không đủ nguồn.",
            "expected_behavior": "abstain",
            "split": "dev" if index < 3 else "test",
        })
    return output


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


def write_manual_review(answers_path: Path, output_path: Path) -> None:
    with answers_path.open("r", encoding="utf-8-sig", newline="") as handle:
        answers = list(csv.DictReader(handle))
        fields = list(answers[0]) if answers else []
    review_fields = fields + ["review_status", "reviewer", "reviewed_at", "review_note"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        for row in answers:
            # Không suy đoán correct/citation_ok: đây là tiêu chí chấm tay có trách nhiệm.
            row.update({"review_status": "pending", "reviewer": "", "reviewed_at": "", "review_note": ""})
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    parser.add_argument("--manual-review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--reset-manual-review", action="store_true",
                        help="ghi đè hàng đợi chấm tay hiện có (mặc định giữ lại nhãn đã chấm)")
    args = parser.parse_args()

    records = build_records(read_jsonl(args.source))
    multi_test = sum(row["type"] == "multi" and row["split"] == "test" for row in records)
    if multi_test != 27:
        raise ValueError(f"Cần đúng 27 multi trong test, nhận được {multi_test}")
    write_jsonl(records, args.output)
    if args.reset_manual_review or not args.manual_review.exists():
        write_manual_review(args.answers, args.manual_review)
        review_message = f"Wrote manual review queue {args.manual_review}"
    else:
        review_message = f"Kept existing manual review queue {args.manual_review}"
    counts = {split: sum(row["split"] == split for row in records) for split in ("dev", "test")}
    # ASCII để script chạy ổn trong PowerShell dùng code page cũ trên Windows.
    print(f"Wrote {args.output} ({counts['dev']} dev, {counts['test']} test; {multi_test} multi test)")
    print(review_message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
