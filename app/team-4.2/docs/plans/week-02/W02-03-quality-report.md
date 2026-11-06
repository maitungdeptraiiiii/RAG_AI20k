# W02-03 — Data quality report: phát hiện / bỏ sót / báo nhầm

Owner: E (+B) · Reviewer: A · Ngày 4 · File: `evals/team-4.2/runners/eval_quality.py`, `evals/team-4.2/results/w02-quality/`

## Checklist

- [ ] Script đọc `labels.jsonl` + `quality_report.json`/`review_queue.jsonl` của pipeline
- [ ] Quy tắc khớp nhãn ↔ phát hiện (cùng doc + cùng loại lỗi, location nếu có)
- [ ] Bảng theo từng loại lỗi: TP (phát hiện), FN (bỏ sót), FP (báo nhầm), precision, recall
- [ ] Báo riêng `dev` và `test`; số chính dùng `test`
- [ ] Liệt kê từng FN/FP kèm lý do (nguồn cho failure cases)
- [ ] Lưu `summary.md` + `per_item.csv` + config (commit hash, ngưỡng)
- [ ] Viết mục "Data quality" trong report tuần

## Tiêu chí nghiệm thu

- Mọi số trong report tái tạo được bằng 1 lệnh ghi trong README.

## Ghi chú

-
