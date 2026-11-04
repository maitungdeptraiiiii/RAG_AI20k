# Kết quả evaluation

- Số câu: 20 (20 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 20 | 0.708 | 0.900 | 0.650 | 0.900 |
| dense+rerank | 20 | 0.717 | 0.850 | 0.725 | 0.900 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| dense | multi | 14 | 0.655 | 0.929 | 0.619 | 0.857 |
| dense | paraphrase | 6 | 0.833 | 0.833 | 0.722 | 1.000 |
| dense+rerank | multi | 14 | 0.738 | 0.929 | 0.750 | 0.857 |
| dense+rerank | paraphrase | 6 | 0.667 | 0.667 | 0.667 | 1.000 |
