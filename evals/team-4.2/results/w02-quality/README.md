# W02-03 — Kết quả data quality (TP / FN / FP)

Chấm detector đang nối trong `RAGPipeline.ingest` trên 30 fixture của `data/team-4.2/fixtures/`.
Labels chỉ được đọc ở bước chấm; detector không import labels.

| File | Nội dung |
|---|---|
| `findings.jsonl` | Output pipeline cho từng fixture: `issue_codes`, `ingest_status`, `pii_counts` (chỉ đếm theo loại), `issues` (đã mask) |
| `result.json` | TP/FN/FP tổng, theo mã issue, theo split `dev`/`test`, trong/ngoài phạm vi detector |
| `summary.md` | Bảng cho report + danh sách từng FN/FP kèm lý do |
| `per_item.csv` | Mã kỳ vọng vs mã phát hiện từng fixture |
| `config.json` | Commit, quy tắc khớp, numeric config, override `header_rows` |

## Chạy lại (tại gốc repo)

```powershell
python evals/team-4.2/runners/build_w02_extra_fixtures.py   # chỉ khi cần sinh lại w02-26..30
python evals/team-4.2/runners/validate_w02_data.py
python evals/team-4.2/runners/run_w02_detectors.py --ocr gemini --out evals/team-4.2/results/w02-quality/findings.jsonl   # cần OPENROUTER_API_KEY còn hạn; bỏ --ocr nếu không có
python evals/team-4.2/runners/score_w02_quality.py --observed evals/team-4.2/results/w02-quality/findings.jsonl --out-dir evals/team-4.2/results/w02-quality
```

## Đọc kết quả

- **Số chính: split `test`, phạm vi detector trong pipeline** (`pii.*`, `numeric.*`, `table.*`, `ocr.*`).
- `ocr.*` chỉ có khi chạy `--ocr gemini` (Gemini 3.5 Flash-Lite đọc chữ, Tesseract local cho confidence, ngưỡng 65 chọn trên dev w02-23/24). Kết quả hiện tại **chạy có OCR thật** (09/11/2026, 5 trang scan, tổng 0.0097 USD; chạy lại dùng cache, 0 USD): `ocr.low_confidence` bắt đúng 3/3 (w02-23 dev, w02-29/30 test), trang rõ w02-24/25 không bị báo.
- Hai luật bảng đã sửa sau báo nhầm trên **dev w02-24** (bảng OCR mức thu): đơn vị nằm ở tầng header giữa; bảng không có cột Kỳ thì không báo `table.missing_period`. **w02-30 là ảnh làm hỏng từ w02-24** → kết quả `table.*` trên w02-30 (test) không độc lập với lần sửa này.
- Mã `dedup.near`, `version.ambiguous`, `flow.*` chưa có detector trong pipeline (Nhóm 1).
  Chúng được tính là FN ở dòng "Toàn bộ", không bị loại khỏi báo cáo.
- Tập fixture nhỏ (8 cặp lỗi trong phạm vi), và fixtures + detector do cùng nhóm viết, nên precision/recall
  1.00 **không** chứng minh detector tổng quát. Cần một bộ fixture "mù" do người khác viết để đo lại.
- Kiểm tra số học (tổng khớp) không chứng minh nguồn đúng; `numeric.conflict` chỉ mở review.
