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
