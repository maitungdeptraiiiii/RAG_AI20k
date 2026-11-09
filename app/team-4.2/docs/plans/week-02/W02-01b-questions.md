# W02-01b — Bộ câu hỏi cho dữ liệu bảng / version / OCR

Owner: E · Reviewer: C · Ngày 1 · Output: `evals/team-4.2/datasets/w02_quality.jsonl`

## Checklist

- [x] 15–20 câu theo schema `Question` (có `gold` source/page/section)
- [x] ≥5 câu cần đọc bảng (header + đơn vị mới trả lời đúng)
- [x] ≥4 câu "bản hiện hành" (đáp án chỉ đúng ở version mới)
- [x] ≥3 câu hỏi lịch sử ("trước năm 2026 quy định thế nào")
- [x] ≥3 câu trên tài liệu OCR
- [x] ≥2 câu `out_of_scope`
- [ ] Soạn câu **không nhìn** chunk đã cắt (tránh lỗi tuần 1); C review
- [x] Đánh dấu `split: dev|test`

## Ghi chú

- 20 câu (`w02-q01`…`w02-q20`), 10 dev / 10 test; `validate_w02_data.py` kiểm tra đủ số câu theo nhóm.
- Hiện hành: `w02-q16`–`q19` (`mode: current`, `current_on: 2026-11-09`); lịch sử: `w02-q06`–`q09` (as-of ngày quá khứ) + `w02-q20` (`all_versions`).
- Còn chờ: C review (`reviewer: unassigned`).
