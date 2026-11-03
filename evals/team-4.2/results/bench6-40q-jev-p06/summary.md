# Kết quả evaluation

- Số câu: 40 (40 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: text-embedding-3-small · LLM: gpt-6-luna · RRF k=60 · rerank: jev · nâng cao: không
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| hybrid | 40 | 0.633 | 0.700 | 0.658 | 0.783 |
| hybrid+rerank | 40 | 0.775 | 0.850 | 0.838 | 0.783 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| hybrid | lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| hybrid | multi | 8 | 0.417 | 0.750 | 0.667 | 0.417 |
| hybrid | paraphrase | 16 | 0.375 | 0.375 | 0.344 | 0.750 |
| hybrid+rerank | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| hybrid+rerank | multi | 8 | 0.375 | 0.750 | 0.688 | 0.417 |
| hybrid+rerank | paraphrase | 16 | 0.750 | 0.750 | 0.750 | 0.750 |

## Từ chối và context

```json
{
  "refuse_rate_out_of_scope": null,
  "refuse_rate_in_scope": 0.2,
  "context_has_gold": 0.825,
  "avg_context_blocks": 1.575
}
```
