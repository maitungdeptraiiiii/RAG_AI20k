# Kết quả evaluation

- Số câu: 40 (40 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 40 | 0.871 | 0.950 | 0.780 | 0.933 |
| hyde | 40 | 0.912 | 0.975 | 0.930 | 0.958 |
| dense+hyde | 40 | 0.883 | 0.975 | 0.863 | 0.958 |
| dense+rerank | 40 | 0.925 | 0.975 | 0.925 | 0.933 |
| hyde+rerank | 40 | 0.950 | 1.000 | 0.950 | 0.958 |
| dense+hyde+rerank | 40 | 0.950 | 1.000 | 0.950 | 0.958 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| dense | lookup | 16 | 1.000 | 1.000 | 0.958 | 1.000 |
| dense | multi | 8 | 0.479 | 0.875 | 0.650 | 0.792 |
| dense | paraphrase | 16 | 0.938 | 0.938 | 0.667 | 0.938 |
| dense+hyde | lookup | 16 | 1.000 | 1.000 | 0.958 | 1.000 |
| dense+hyde | multi | 8 | 0.542 | 1.000 | 0.838 | 0.792 |
| dense+hyde | paraphrase | 16 | 0.938 | 0.938 | 0.781 | 1.000 |
| dense+hyde+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| dense+hyde+rerank | multi | 8 | 0.750 | 1.000 | 0.875 | 0.792 |
| dense+hyde+rerank | paraphrase | 16 | 1.000 | 1.000 | 0.938 | 1.000 |
| dense+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| dense+rerank | multi | 8 | 0.750 | 1.000 | 0.875 | 0.792 |
| dense+rerank | paraphrase | 16 | 0.938 | 0.938 | 0.875 | 0.938 |
| hyde | lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| hyde | multi | 8 | 0.562 | 0.875 | 0.875 | 0.792 |
| hyde | paraphrase | 16 | 1.000 | 1.000 | 0.919 | 1.000 |
| hyde+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| hyde+rerank | multi | 8 | 0.750 | 1.000 | 0.875 | 0.792 |
| hyde+rerank | paraphrase | 16 | 1.000 | 1.000 | 0.938 | 1.000 |
