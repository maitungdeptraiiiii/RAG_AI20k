# Kết quả evaluation

- Số câu: 64 (64 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| bm25 | 64 | 0.258 | 0.281 | 0.157 | 0.414 |
| dense | 64 | 0.823 | 0.922 | 0.692 | 0.938 |
| hybrid | 64 | 0.622 | 0.703 | 0.474 | 0.891 |
| dense+rerank | 64 | 0.849 | 0.938 | 0.826 | 0.938 |
| hybrid+rerank | 64 | 0.833 | 0.922 | 0.817 | 0.891 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| bm25 | multi | 27 | 0.093 | 0.148 | 0.102 | 0.315 |
| bm25 | paraphrase | 37 | 0.378 | 0.378 | 0.197 | 0.486 |
| dense | multi | 27 | 0.728 | 0.963 | 0.664 | 0.889 |
| dense | paraphrase | 37 | 0.892 | 0.892 | 0.713 | 0.973 |
| dense+rerank | multi | 27 | 0.753 | 0.963 | 0.736 | 0.889 |
| dense+rerank | paraphrase | 37 | 0.919 | 0.919 | 0.892 | 0.973 |
| hybrid | multi | 27 | 0.512 | 0.704 | 0.475 | 0.889 |
| hybrid | paraphrase | 37 | 0.703 | 0.703 | 0.473 | 0.892 |
| hybrid+rerank | multi | 27 | 0.753 | 0.963 | 0.760 | 0.889 |
| hybrid+rerank | paraphrase | 37 | 0.892 | 0.892 | 0.858 | 0.892 |
