# W02-03 — Data quality report: phát hiện / bỏ sót / báo nhầm

Owner: E (+B) · Reviewer: A · Ngày 4 · File: `evals/team-4.2/runners/eval_quality.py`, `evals/team-4.2/results/w02-quality/`

## Checklist

- [x] Script đọc `labels.jsonl` + `quality_report.json`/`review_queue.jsonl` của pipeline
- [x] Quy tắc khớp nhãn ↔ phát hiện (cùng doc + cùng loại lỗi, location nếu có)
- [x] Bảng theo từng loại lỗi: TP (phát hiện), FN (bỏ sót), FP (báo nhầm), precision, recall
- [x] Báo riêng `dev` và `test`; số chính dùng `test`
- [x] Liệt kê từng FN/FP kèm lý do (nguồn cho failure cases)
- [x] Lưu `summary.md` + `per_item.csv` + config (commit hash, ngưỡng)
- [ ] Viết mục "Data quality" trong report tuần

## Tiêu chí nghiệm thu

- Mọi số trong report tái tạo được bằng 1 lệnh ghi trong README.

## Ghi chú

- Script: `evals/team-4.2/runners/run_w02_detectors.py` (chạy pipeline, không đọc labels) + `score_w02_quality.py` (thay cho tên `eval_quality.py` trong kế hoạch).
- Kết quả: `evals/team-4.2/results/w02-quality/` — test, detector Nhóm 2: TP 6 / FN 0 / FP 0; toàn bộ mã: TP 8 / FN 9 / FP 0 (FN là dedup.near, version.ambiguous, ocr.*, flow.* chưa có detector).
- Còn chờ: viết mục "Data quality" trong report tuần.
