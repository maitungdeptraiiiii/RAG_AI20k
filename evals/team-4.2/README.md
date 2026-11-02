# evals — Team 4.2

[Trang team](../../teams/team-4.2/README.md) · [Quy chuẩn chung](../README.md)

| Thư mục | Nội dung |
|---|---|
| `datasets/` | `questions.jsonl` — câu hỏi, gold `source` + `page`, `reference`, split |
| `configs/` | Cấu hình các arm/ablation (BM25, Dense, Hybrid, +rerank) |
| `runners/` | `metrics.py` (Recall@5, MRR@5), `run_eval.py`, `draft_references.py`, `oracle.py` |
| `results/` | Kết quả nhỏ đã rà soát (per-question CSV, summary) |
| `REPORT.md` | Evaluation + failure analysis, liên kết từ báo cáo tuần |

Chưa có kết quả. Mỗi run ghi commit, snapshot dữ liệu, model/version, config và số câu.
