# Kết quả evaluation

- Số câu: 20 (20 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: text-embedding-3-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 20 | 0.100 | 0.200 | 0.087 | 0.267 |
| hybrid | 20 | 0.175 | 0.250 | 0.117 | 0.317 |
| dense+hyde+rerank | 20 | 0.475 | 0.700 | 0.554 | 0.492 |
| all | 20 | 0.400 | 0.600 | 0.479 | 0.417 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| all | multi | 14 | 0.429 | 0.714 | 0.542 | 0.452 |
| all | paraphrase | 6 | 0.333 | 0.333 | 0.333 | 0.333 |
| dense | multi | 14 | 0.143 | 0.286 | 0.125 | 0.310 |
| dense | paraphrase | 6 | 0.000 | 0.000 | 0.000 | 0.167 |
| dense+hyde+rerank | multi | 14 | 0.464 | 0.786 | 0.577 | 0.488 |
| dense+hyde+rerank | paraphrase | 6 | 0.500 | 0.500 | 0.500 | 0.500 |
| hybrid | multi | 14 | 0.107 | 0.214 | 0.077 | 0.310 |
| hybrid | paraphrase | 6 | 0.333 | 0.333 | 0.208 | 0.333 |
