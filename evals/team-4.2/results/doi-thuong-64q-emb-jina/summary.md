# Kết quả evaluation

- Số câu: 64 (64 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: none · nâng cao: không
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 64 | 0.594 | 0.703 | 0.499 | 0.763 |
| hybrid | 64 | 0.458 | 0.562 | 0.386 | 0.727 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| dense | multi | 27 | 0.519 | 0.778 | 0.517 | 0.660 |
| dense | paraphrase | 37 | 0.649 | 0.649 | 0.486 | 0.838 |
| hybrid | multi | 27 | 0.346 | 0.593 | 0.361 | 0.648 |
| hybrid | paraphrase | 37 | 0.541 | 0.541 | 0.404 | 0.784 |
