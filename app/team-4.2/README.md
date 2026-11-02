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
│   ├── ingest/           # loaders, chunker, xref            (chưa có)
│   ├── index/            # bm25_index, embedder, vector_index (store: chưa có)
│   ├── retrieve/         # fusion (RRF), hybrid, rerank (Jev), context (chọn đoạn cho LLM)
│   ├── generate/         # llm, answer + citation             (chưa có)
│   └── pipeline.py       # RAGPipeline                        (chưa có)
├── ui/                   # streamlit_app.py                   (chưa có)
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

Chưa có: lệnh ingest, chạy UI và evaluation — bổ sung khi các module tương ứng hoàn thành.
