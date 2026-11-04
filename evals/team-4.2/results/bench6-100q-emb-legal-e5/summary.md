# Kết quả evaluation

- Số câu: 100 (100 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: bqbbao6/vietnamese-legal-embedding · LLM: gpt-6-luna · RRF k=60 · rerank: none · nâng cao: không
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| bm25 | 100 | 0.620 | 0.670 | 0.521 | 0.742 |
| dense | 100 | 0.853 | 0.920 | 0.799 | 0.933 |
| hybrid | 100 | 0.788 | 0.850 | 0.698 | 0.948 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| bm25 | lookup | 40 | 0.925 | 0.925 | 0.746 | 0.950 |
| bm25 | multi | 20 | 0.500 | 0.750 | 0.597 | 0.608 |
| bm25 | paraphrase | 40 | 0.375 | 0.375 | 0.259 | 0.600 |
| dense | lookup | 40 | 1.000 | 1.000 | 0.921 | 1.000 |
| dense | multi | 20 | 0.617 | 0.950 | 0.860 | 0.767 |
| dense | paraphrase | 40 | 0.825 | 0.825 | 0.647 | 0.950 |
| hybrid | lookup | 40 | 0.950 | 0.950 | 0.875 | 1.000 |
| hybrid | multi | 20 | 0.642 | 0.950 | 0.885 | 0.792 |
| hybrid | paraphrase | 40 | 0.700 | 0.700 | 0.428 | 0.975 |
