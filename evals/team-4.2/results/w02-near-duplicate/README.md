# Near-duplicate baseline/v2 comparison

Run from `app/team-4.2`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.eval_near_duplicate
```

[evaluation.json](evaluation.json) contains source/config/dataset checksums, predictions for each pair and TP/FP/FN/TN per split. The [dataset](../../datasets/near_duplicate/pairs.json) is synthetic and handcrafted; the same template families occur across dev/test. It was visible during implementation and is not independent real-world validation.

Each split has 12 pairs:

| Policy | TP | FP | FN | TN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| Baseline v1 | 6 | 4 | 1 | 1 | 0.60 | 0.8571 |
| V2 | 7 | 2 | 0 | 3 | 0.7778 | 1.00 |

Both use threshold 0.85. Remaining false positives are retained conservatively when identity/scope evidence is insufficient. See the [implementation and limitations](../../../../app/team-4.2/docs/NEAR_DUPLICATE_EVALUATION.md).
