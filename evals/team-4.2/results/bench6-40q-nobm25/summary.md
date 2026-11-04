# Kết quả evaluation

- Số câu: 40 (40 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: text-embedding-3-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 40 | 0.600 | 0.650 | 0.548 | 0.758 |
| dense+hyde | 40 | 0.733 | 0.800 | 0.680 | 0.829 |
| dense+rerank | 40 | 0.750 | 0.825 | 0.800 | 0.758 |
| dense+hyde+rerank | 40 | 0.812 | 0.900 | 0.875 | 0.829 |
| all | 40 | 0.821 | 0.900 | 0.875 | 0.838 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| all | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| all | multi | 8 | 0.479 | 0.875 | 0.812 | 0.562 |
| all | paraphrase | 16 | 0.812 | 0.812 | 0.781 | 0.812 |
| dense | lookup | 16 | 1.000 | 1.000 | 0.865 | 1.000 |
| dense | multi | 8 | 0.250 | 0.500 | 0.406 | 0.417 |
| dense | paraphrase | 16 | 0.375 | 0.375 | 0.302 | 0.688 |
| dense+hyde | lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| dense+hyde | multi | 8 | 0.417 | 0.750 | 0.567 | 0.521 |
| dense+hyde | paraphrase | 16 | 0.625 | 0.625 | 0.448 | 0.812 |
| dense+hyde+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| dense+hyde+rerank | multi | 8 | 0.438 | 0.875 | 0.812 | 0.521 |
| dense+hyde+rerank | paraphrase | 16 | 0.812 | 0.812 | 0.781 | 0.812 |
| dense+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| dense+rerank | multi | 8 | 0.375 | 0.750 | 0.688 | 0.417 |
| dense+rerank | paraphrase | 16 | 0.688 | 0.688 | 0.656 | 0.688 |
