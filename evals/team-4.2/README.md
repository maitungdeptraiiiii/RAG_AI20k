# evals — Team 4.2

[Trang team](../../teams/team-4.2/README.md) · [Quy chuẩn chung](../README.md)

| Thư mục | Nội dung |
|---|---|
| `datasets/` | `questions.jsonl` — câu hỏi, gold `source` + `page`, `reference` (mẫu: `questions.example.jsonl`) |
| `configs/` | Cấu hình các arm/ablation (BM25, Dense, Hybrid, +rerank) |
| `runners/` | `run_eval.py` (Recall@5, Hit@5, MRR@5, Recall@20; từ chối), `draft_references.py`, `export_ragas.py`. Logic nằm ở `app/team-4.2/src/rag/eval/` để có unit test |
| `results/` | Kết quả nhỏ đã rà soát (per-question CSV, summary) |
| `REPORT.md` | Evaluation + failure analysis, liên kết từ báo cáo tuần |

Chưa có kết quả. Mỗi run ghi commit, snapshot dữ liệu, model/version, config và số câu.

## Carryover tuần 1 cho tuần 2

Chạy `python evals/team-4.2/runners/prepare_w02_benchmark.py` để tạo
`datasets/benchmark_doi_thuong_w02.jsonl` và hàng đợi chấm tay tại
`results/w02-carryover/`. Dataset dẫn xuất giữ gold theo `source` + `section`,
không theo `chunk_id`; 27 câu `multi` nằm trong `test` phục vụ agent multi-hop.
Chạy `python evals/team-4.2/runners/validate_w02_data.py` trước eval để kiểm
tra consistency fixtures/câu hỏi; runner này không phải detector chất lượng.

Data quality W02-03 (chi tiết: `results/w02-quality/README.md`):

```powershell
python evals/team-4.2/runners/run_w02_detectors.py --out evals/team-4.2/results/w02-quality/findings.jsonl
python evals/team-4.2/runners/score_w02_quality.py --observed evals/team-4.2/results/w02-quality/findings.jsonl --out-dir evals/team-4.2/results/w02-quality
python evals/team-4.2/runners/measure_w02_parser_loss.py --out evals/team-4.2/results/w02-inventory
```

`score_w02_quality.py` tính TP/FN/FP offline từ labels đã đóng băng, theo mã issue và theo split. Findings phải mang `fixture_id`
qua eval adapter; labels tuyệt đối không được đưa vào detector.

## Bộ multi-hop khó bổ sung — 06/11/2026

- [Dataset 25 câu mới và schema](datasets/benchmark_multihop_hard25.README.md), độc lập với bộ 64 câu `benchmark_doi_thuong.jsonl` được giữ nguyên.
- [Báo cáo retrieval-only theo cấu hình hiện tại](results/multihop-hard25-current-20261106-verified/REPORT.md): giữ HyDE, decomposition, Jev và listwise; không chạy generation trả lời cuối.
- Runner: `runners/run_multihop_hard25.py`; kiểm chứng metrics và phân tích lỗi offline: `runners/analyze_multihop_hard25.py`.
