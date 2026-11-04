# Kết quả evaluation

- Số câu: 40 (40 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense+hyde+rerank | 40 | 0.950 | 1.000 | 0.950 | 0.958 |
| all | 40 | 0.925 | 0.975 | 0.938 | 0.942 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| all | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| all | multi | 8 | 0.750 | 1.000 | 0.875 | 0.833 |
| all | paraphrase | 16 | 0.938 | 0.938 | 0.906 | 0.938 |
| dense+hyde+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| dense+hyde+rerank | multi | 8 | 0.750 | 1.000 | 0.875 | 0.792 |
| dense+hyde+rerank | paraphrase | 16 | 1.000 | 1.000 | 0.938 | 1.000 |
