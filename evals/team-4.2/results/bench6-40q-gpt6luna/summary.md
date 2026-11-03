# Kết quả evaluation

- Số câu: 40 (40 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: text-embedding-3-small · LLM: gpt-6-luna · RRF k=60 · rerank: none · nâng cao: không
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| bm25 | 40 | 0.633 | 0.700 | 0.597 | 0.708 |
| dense | 40 | 0.600 | 0.650 | 0.548 | 0.758 |
| hybrid | 40 | 0.633 | 0.700 | 0.658 | 0.783 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| bm25 | lookup | 16 | 1.000 | 1.000 | 0.854 | 1.000 |
| bm25 | multi | 8 | 0.292 | 0.625 | 0.525 | 0.417 |
| bm25 | paraphrase | 16 | 0.438 | 0.438 | 0.375 | 0.562 |
| dense | lookup | 16 | 1.000 | 1.000 | 0.865 | 1.000 |
| dense | multi | 8 | 0.250 | 0.500 | 0.406 | 0.417 |
| dense | paraphrase | 16 | 0.375 | 0.375 | 0.302 | 0.688 |
| hybrid | lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| hybrid | multi | 8 | 0.417 | 0.750 | 0.667 | 0.417 |
| hybrid | paraphrase | 16 | 0.375 | 0.375 | 0.344 | 0.750 |

## Từ chối và context

```json
{
  "refuse_rate_out_of_scope": null,
  "refuse_rate_in_scope": 0.275,
  "context_has_gold": 0.7,
  "avg_context_blocks": 5.0
}
```
