# Kết quả evaluation

- Số câu: 64 (64 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: jina-embeddings-v5-text-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: contextual_header,hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| dense | 64 | 0.815 | 0.922 | 0.714 | 0.922 |
| dense+rerank | 64 | 0.849 | 0.938 | 0.831 | 0.922 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| dense | multi | 27 | 0.710 | 0.963 | 0.676 | 0.889 |
| dense | paraphrase | 37 | 0.892 | 0.892 | 0.742 | 0.946 |
| dense+rerank | multi | 27 | 0.753 | 0.963 | 0.747 | 0.889 |
| dense+rerank | paraphrase | 37 | 0.919 | 0.919 | 0.892 | 0.946 |
