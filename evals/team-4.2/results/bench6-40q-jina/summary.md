# Kết quả evaluation

- Số câu: 40 (40 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 40 | 0.871 | 0.950 | 0.777 | 0.933 |
| hybrid | 40 | 0.738 | 0.825 | 0.729 | 0.912 |
| dense+hyde | 40 | 0.883 | 0.975 | 0.863 | 0.958 |
| dense+rerank | 40 | 0.925 | 0.975 | 0.925 | 0.933 |
| dense+hyde+rerank | 40 | 0.942 | 1.000 | 0.950 | 0.958 |
| all | 40 | 0.917 | 0.975 | 0.938 | 0.942 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| all | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| all | multi | 8 | 0.708 | 1.000 | 0.875 | 0.833 |
| all | paraphrase | 16 | 0.938 | 0.938 | 0.906 | 0.938 |
| dense | lookup | 16 | 1.000 | 1.000 | 0.958 | 1.000 |
| dense | multi | 8 | 0.479 | 0.875 | 0.650 | 0.792 |
| dense | paraphrase | 16 | 0.938 | 0.938 | 0.658 | 0.938 |
| dense+hyde | lookup | 16 | 1.000 | 1.000 | 0.958 | 1.000 |
| dense+hyde | multi | 8 | 0.542 | 1.000 | 0.838 | 0.792 |
| dense+hyde | paraphrase | 16 | 0.938 | 0.938 | 0.781 | 1.000 |
| dense+hyde+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| dense+hyde+rerank | multi | 8 | 0.708 | 1.000 | 0.875 | 0.792 |
| dense+hyde+rerank | paraphrase | 16 | 1.000 | 1.000 | 0.938 | 1.000 |
| dense+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| dense+rerank | multi | 8 | 0.750 | 1.000 | 0.875 | 0.792 |
| dense+rerank | paraphrase | 16 | 0.938 | 0.938 | 0.875 | 0.938 |
| hybrid | lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| hybrid | multi | 8 | 0.438 | 0.875 | 0.750 | 0.688 |
| hybrid | paraphrase | 16 | 0.625 | 0.625 | 0.479 | 0.938 |
