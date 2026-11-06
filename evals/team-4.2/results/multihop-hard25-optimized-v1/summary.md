# Multi-hop hard25 — retrieval only

## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| current-retrieval | 25 | 0.802 | 1.000 | 0.960 | 0.890 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| current-retrieval | multi | 25 | 0.802 | 1.000 | 0.960 | 0.890 |

```json
{
  "status": "complete",
  "n": 25,
  "metrics": {
    "recall@5": 0.802,
    "hit@5": 1.0,
    "mrr@5": 0.96,
    "recall@20": 0.89,
    "all_gold@5": 0.44,
    "all_gold@20": 0.68,
    "merged_recall@5": 0.802,
    "merged_recall@20": 0.89
  },
  "questions_with_errors": 0,
  "error_types": {},
  "retrieval_llm_logical_calls": 128,
  "retrieval_llm_cache_hits": 25,
  "retrieval_llm_sdk_requests": 103,
  "answer_generation_calls": 0,
  "old_dataset_unchanged": true,
  "elapsed_s_sum": 636.536
}
```
