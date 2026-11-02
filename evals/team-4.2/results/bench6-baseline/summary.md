# Kết quả evaluation

- Số câu: 20 (20 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: text-embedding-3-small · LLM: gpt-5.6-luna · RRF k=60 · rerank: none · nâng cao: không
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| bm25 | 20 | 0.617 | 0.650 | 0.567 | 0.750 |
| dense | 20 | 0.633 | 0.700 | 0.617 | 0.767 |
| hybrid | 20 | 0.650 | 0.700 | 0.675 | 0.800 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| bm25 | lookup | 8 | 1.000 | 1.000 | 0.854 | 1.000 |
| bm25 | multi | 4 | 0.083 | 0.250 | 0.250 | 0.250 |
| bm25 | paraphrase | 8 | 0.500 | 0.500 | 0.438 | 0.750 |
| dense | lookup | 8 | 1.000 | 1.000 | 0.875 | 1.000 |
| dense | multi | 4 | 0.167 | 0.500 | 0.500 | 0.333 |
| dense | paraphrase | 8 | 0.500 | 0.500 | 0.417 | 0.750 |
| hybrid | lookup | 8 | 1.000 | 1.000 | 1.000 | 1.000 |
| hybrid | multi | 4 | 0.250 | 0.500 | 0.500 | 0.250 |
| hybrid | paraphrase | 8 | 0.500 | 0.500 | 0.438 | 0.875 |

## Từ chối và context

```json
{
  "refuse_rate_out_of_scope": null,
  "refuse_rate_in_scope": 0.25,
  "context_has_gold": 0.7,
  "avg_context_blocks": 5.0
}
```
