# Kết quả evaluation

- Số câu: 64 (64 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: text-embedding-3-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 64 | 0.471 | 0.578 | 0.429 | 0.625 |
| dense+rerank | 64 | 0.625 | 0.719 | 0.635 | 0.625 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| dense | multi | 27 | 0.451 | 0.704 | 0.479 | 0.593 |
| dense | paraphrase | 37 | 0.486 | 0.486 | 0.393 | 0.649 |
| dense+rerank | multi | 27 | 0.593 | 0.815 | 0.636 | 0.593 |
| dense+rerank | paraphrase | 37 | 0.649 | 0.649 | 0.635 | 0.649 |
