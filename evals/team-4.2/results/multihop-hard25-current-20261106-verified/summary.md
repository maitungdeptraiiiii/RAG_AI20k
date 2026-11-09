# Multi-hop hard25 — retrieval only

## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| current-retrieval | 25 | 0.789 | 1.000 | 0.940 | 0.840 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| current-retrieval | multi | 25 | 0.789 | 1.000 | 0.940 | 0.840 |

```json
{
  "status": "complete",
  "n": 25,
  "metrics": {
    "recall@5": 0.7886666666666666,
    "hit@5": 1.0,
    "mrr@5": 0.94,
    "recall@20": 0.84,
    "all_gold@5": 0.44,
    "all_gold@20": 0.6,
    "merged_recall@5": 0.7886666666666667,
    "merged_recall@20": 0.84
  },
  "questions_with_errors": 0,
  "error_types": {},
  "retrieval_llm_logical_calls": 128,
  "retrieval_llm_cache_hits": 21,
  "retrieval_llm_sdk_requests": 107,
  "answer_generation_calls": 0,
  "old_dataset_unchanged": true,
  "elapsed_s_sum": 721.678
}
```
