# Kết quả evaluation

- Số câu: 100 (100 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: none · nâng cao: không
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| bm25 | 100 | 0.620 | 0.670 | 0.521 | 0.742 |
| dense | 100 | 0.912 | 0.960 | 0.853 | 0.967 |
| hybrid | 100 | 0.782 | 0.840 | 0.701 | 0.938 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| bm25 | lookup | 40 | 0.925 | 0.925 | 0.746 | 0.950 |
| bm25 | multi | 20 | 0.500 | 0.750 | 0.597 | 0.608 |
| bm25 | paraphrase | 40 | 0.375 | 0.375 | 0.259 | 0.600 |
| dense | lookup | 40 | 1.000 | 1.000 | 0.958 | 1.000 |
| dense | multi | 20 | 0.708 | 0.950 | 0.827 | 0.883 |
| dense | paraphrase | 40 | 0.925 | 0.925 | 0.760 | 0.975 |
| hybrid | lookup | 40 | 0.950 | 0.950 | 0.865 | 0.975 |
| hybrid | multi | 20 | 0.658 | 0.950 | 0.802 | 0.842 |
| hybrid | paraphrase | 40 | 0.675 | 0.675 | 0.486 | 0.950 |
