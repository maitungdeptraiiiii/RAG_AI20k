# Kết quả evaluation

- Số câu: 20 (20 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 20 | 0.425 | 0.650 | 0.489 | 0.667 |
| hybrid | 20 | 0.358 | 0.550 | 0.368 | 0.525 |
| dense+hyde | 20 | 0.575 | 0.700 | 0.625 | 0.808 |
| dense+rerank | 20 | 0.667 | 0.850 | 0.643 | 0.667 |
| dense+hyde+rerank | 20 | 0.742 | 0.900 | 0.668 | 0.808 |
| all | 20 | 0.725 | 0.900 | 0.696 | 0.767 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| all | multi | 14 | 0.679 | 0.929 | 0.690 | 0.738 |
| all | paraphrase | 6 | 0.833 | 0.833 | 0.708 | 0.833 |
| dense | multi | 14 | 0.393 | 0.714 | 0.532 | 0.595 |
| dense | paraphrase | 6 | 0.500 | 0.500 | 0.389 | 0.833 |
| dense+hyde | multi | 14 | 0.607 | 0.786 | 0.679 | 0.798 |
| dense+hyde | paraphrase | 6 | 0.500 | 0.500 | 0.500 | 0.833 |
| dense+hyde+rerank | multi | 14 | 0.702 | 0.929 | 0.655 | 0.798 |
| dense+hyde+rerank | paraphrase | 6 | 0.833 | 0.833 | 0.700 | 0.833 |
| dense+rerank | multi | 14 | 0.595 | 0.857 | 0.610 | 0.595 |
| dense+rerank | paraphrase | 6 | 0.833 | 0.833 | 0.722 | 0.833 |
| hybrid | multi | 14 | 0.298 | 0.571 | 0.369 | 0.536 |
| hybrid | paraphrase | 6 | 0.500 | 0.500 | 0.367 | 0.500 |
