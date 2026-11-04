# Kết quả evaluation

- Số câu: 64 (64 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense+rerank | 64 | 0.849 | 0.938 | 0.826 | 0.938 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| dense+rerank | multi | 27 | 0.753 | 0.963 | 0.736 | 0.889 |
| dense+rerank | paraphrase | 37 | 0.919 | 0.919 | 0.892 | 0.973 |
