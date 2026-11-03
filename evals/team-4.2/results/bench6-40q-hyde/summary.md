# Kết quả evaluation

- Số câu: 40 (40 trong phạm vi)
- Index: 3422 chunk, 6 tài liệu
- Embedding: text-embedding-3-small · LLM: gpt-6-luna · RRF k=60 · rerank: none · nâng cao: hyde
## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| hybrid | 40 | 0.633 | 0.700 | 0.658 | 0.783 |
| hyde | 40 | 0.812 | 0.900 | 0.811 | 0.892 |
| hybrid+hyde | 40 | 0.742 | 0.825 | 0.703 | 0.838 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| hybrid | lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| hybrid | multi | 8 | 0.417 | 0.750 | 0.667 | 0.417 |
| hybrid | paraphrase | 16 | 0.375 | 0.375 | 0.344 | 0.750 |
| hybrid+hyde | lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| hybrid+hyde | multi | 8 | 0.333 | 0.750 | 0.750 | 0.562 |
| hybrid+hyde | paraphrase | 16 | 0.688 | 0.688 | 0.412 | 0.812 |
| hyde | lookup | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| hyde | multi | 8 | 0.438 | 0.875 | 0.598 | 0.583 |
| hyde | paraphrase | 16 | 0.812 | 0.812 | 0.729 | 0.938 |

## Từ chối và context

```json
{
  "refuse_rate_out_of_scope": null,
  "refuse_rate_in_scope": 0.225,
  "context_has_gold": 0.825,
  "avg_context_blocks": 5.0
}
```
