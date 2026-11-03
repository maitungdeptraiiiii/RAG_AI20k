# scripts — Team 4.2

[Trang team](../../teams/team-4.2/README.md) · [Quy chuẩn chung](../README.md)

Chạy tại gốc repo, sau khi `pip install -e "app/team-4.2[dev]"` và điền `app/team-4.2/.env`.

| Script | Việc |
|---|---|
| `ingest.py` | Ingest file PDF/TXT/MD, thư mục hoặc URL vào index (`python scripts/team-4.2/ingest.py data/team-4.2/raw/`) |
| `ask.py` | Hỏi trên dòng lệnh: câu trả lời, citation và kết quả từng arm (`--mode bm25\|dense\|hyde`, `--retrieve-only`) |

Evaluation nằm ở `evals/team-4.2/runners/`.
