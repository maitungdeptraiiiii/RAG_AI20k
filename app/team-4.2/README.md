# app — Team 4.2

[Trang team](../../teams/team-4.2/README.md) · [Quy chuẩn chung](../README.md)

Baseline Hybrid RAG (BM25 + Dense + RRF) cho văn bản luật tiếng Việt. Sản phẩm phát triển liên tục qua 5 tuần trong thư mục này, không sao chép code theo tuần.

## Cấu trúc

```text
app/team-4.2/
├── pyproject.toml        # package `rag` (src layout), extras: jev, dev
├── .env.example          # biến môi trường mẫu, chỉ placeholder
├── src/rag/
│   ├── schema.py         # hợp đồng dữ liệu chung (Page, Chunk, Hit, Answer, ...)
│   ├── config.py         # Settings đọc .env / biến môi trường
│   ├── ingest/           # loaders (PDF/URL/TXT), chunker
│   ├── index/            # store (chunks.jsonl), bm25_index, embedder, vector_index
│   ├── retrieve/         # fusion (RRF), hybrid, rerank (Jev), context (chọn đoạn cho LLM)
│   ├── generate/         # llm (gpt-6-luna + cache), answer (prompt + citation)
│   ├── advanced/         # phương pháp nâng cao dạng plugin: hyde, contextual (bật bằng ADVANCED)
│   ├── eval/             # metrics (Recall@k, MRR@k), runner
│   └── pipeline.py       # RAGPipeline: ingest(), ask(), ask_debug()
├── ui/                   # streamlit_app.py
├── tests/                # mỗi module một test_<module>.py
└── docs/
    ├── tech_stack.md     # lựa chọn stack và lý do (nên tách thành ADR)
    ├── phan_cong_sprint1.md
    └── plans/2026-11-01-baseline-rag.md
```

Dữ liệu, evaluation, thí nghiệm, scripts và báo cáo nằm ở thư mục team tương ứng ngoài `app/`:
`data/team-4.2/`, `evals/team-4.2/`, `experiments/team-4.2/`, `scripts/team-4.2/`, `reports/week-0N/team-4.2/`.

## Cài đặt và chạy (tại gốc repo)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "app/team-4.2[dev]"          # thêm [jev] nếu dùng reranker Jev
cp app/team-4.2/.env.example app/team-4.2/.env   # điền key, KHÔNG commit .env
pytest app/team-4.2/tests -v
```

Các lệnh (tại gốc repo, sau khi điền `.env`):

```bash
python scripts/team-4.2/ingest.py data/team-4.2/raw/            # ingest PDF/TXT/MD trong thư mục, hoặc URL
python scripts/team-4.2/ask.py "Câu hỏi ..."                     # trả lời + citation + kết quả từng arm
streamlit run app/team-4.2/ui/streamlit_app.py                  # UI chat
python evals/team-4.2/runners/run_eval.py --answers              # Recall@5, MRR@5 (BM25/Dense/Hybrid) + từ chối
python evals/team-4.2/runners/draft_references.py               # nháp đáp án mẫu, người viết câu hỏi kiểm tra lại
python evals/team-4.2/runners/export_ragas.py                   # dữ liệu đầu vào cho RAGAS
```

Chưa có: guardrail (TV5), bước chấm bằng RAGAS (chờ chốt version `ragas`). Toàn bộ test hiện chạy với
client giả; cần chạy thử một lần với PyMuPDF, trafilatura, pyvi, OpenAI, Qdrant và Jev thật.
