# Kết quả evaluation

- Số câu: 64 (64 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: bqbbao6/vietnamese-legal-embedding · LLM: gpt-6-luna · RRF k=60 · rerank: none · nâng cao: không
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 64 | 0.576 | 0.672 | 0.432 | 0.727 |
| hybrid | 64 | 0.477 | 0.578 | 0.299 | 0.685 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| dense | multi | 27 | 0.401 | 0.630 | 0.367 | 0.648 |
| dense | paraphrase | 37 | 0.703 | 0.703 | 0.480 | 0.784 |
| hybrid | multi | 27 | 0.315 | 0.556 | 0.240 | 0.549 |
| hybrid | paraphrase | 37 | 0.595 | 0.595 | 0.342 | 0.784 |
