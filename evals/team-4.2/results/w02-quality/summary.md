# W02-03 — Data quality: phát hiện / bỏ sót / báo nhầm

Commit `db7d3cf-dirty` · labels `data/team-4.2/fixtures/labels.jsonl` · findings `evals/team-4.2/results/w02-quality/findings.jsonl`.
Khớp = cùng `fixture_id` + cùng mã issue. **Số chính dùng split `test`.**

## Tổng hợp

| Phạm vi | Split | TP | FN | FP | Precision | Recall |
|---|---|---:|---:|---:|---:|---:|
| Detector trong pipeline (pii/numeric/table/ocr) | test | 8 | 0 | 0 | 1.00 | 1.00 |
| Toàn bộ mã trong labels | test | 8 | 3 | 0 | 1.00 | 0.73 |
| Detector trong pipeline (pii/numeric/table/ocr) | dev | 3 | 0 | 0 | 1.00 | 1.00 |
| Toàn bộ mã trong labels | dev | 3 | 3 | 0 | 1.00 | 0.50 |

## Theo mã issue (dev + test)

| Mã | Có detector | TP | FN | FP | Precision | Recall |
|---|---|---:|---:|---:|---:|---:|
| `dedup.near` | chưa (Nhóm 1) | 0 | 3 | 0 | — | 0.00 |
| `flow.structure_loss` | chưa (Nhóm 1) | 0 | 1 | 0 | — | 0.00 |
| `numeric.conflict` | có | 1 | 0 | 0 | 1.00 | 1.00 |
| `numeric.invalid_locale` | có | 1 | 0 | 0 | 1.00 | 1.00 |
| `numeric.sum_mismatch` | có | 1 | 0 | 0 | 1.00 | 1.00 |
| `ocr.low_confidence` | có | 3 | 0 | 0 | 1.00 | 1.00 |
| `pii.detected` | có | 3 | 0 | 0 | 1.00 | 1.00 |
| `table.missing_period` | có | 1 | 0 | 0 | 1.00 | 1.00 |
| `table.missing_unit` | có | 1 | 0 | 0 | 1.00 | 1.00 |
| `version.ambiguous` | chưa (Nhóm 1) | 0 | 2 | 0 | — | 0.00 |

## Từng bỏ sót / báo nhầm

| Loại | Fixture | Split | Mã | Lý do |
|---|---|---|---|---|
| FN | `w02-05` | dev | `dedup.near` | Chưa có detector cho mã này trong pipeline |
| FN | `w02-07` | test | `dedup.near` | Chưa có detector cho mã này trong pipeline |
| FN | `w02-08` | test | `dedup.near` | Chưa có detector cho mã này trong pipeline |
| FN | `w02-17` | dev | `version.ambiguous` | Chưa có detector cho mã này trong pipeline |
| FN | `w02-18` | test | `version.ambiguous` | Chưa có detector cho mã này trong pipeline |
| FN | `w02-23` | dev | `flow.structure_loss` | Chưa có detector cho mã này trong pipeline |

Nhất quán số học (tổng khớp) không chứng minh nguồn đúng; conflict chỉ là tín hiệu review.
