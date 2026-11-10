# Bộ câu hỏi fixture Week 2 — Team 4.2

`w02_fixture_questions.jsonl` là bộ câu hỏi cho bảng/version/OCR, dùng sau khi pipeline Week 2 đã ingest `data/team-4.2/fixtures/` vào DATA_DIR riêng.

## Quy ước

- `gold` giữ tương thích schema Week 1: `source` + `section` hoặc `page`; không có `chunk_id`.
- `evidence` mở rộng theo Contract v1: fixture ID, locator và `version_scope`. Eval adapter ánh xạ evidence sang `document_id`, `version_id`, `unit_revision_id` và chunks của chunking strategy đang chạy.
- `expected_behavior` là `answer`, `clarify` hoặc `abstain`. Câu `out_of_scope` không có `gold`/reference.
- `evaluation_surface: "review"` là bài kiểm tra detector/review UI. Nó có thể tham chiếu fixture `pending`, nhưng **không** là câu retrieval trên answer path; adapter phải đọc finding/review riêng và không đưa block pending vào citation/context.
- Split đã chốt: 10 dev, 10 test (q01–q15: 8 dev/7 test; q16–q20 bổ sung: 2 dev/3 test). Không chuyển câu test sang dev để tune threshold/chunker/detector.
- `reviewer: unassigned` là trạng thái tạm; trước report, nhờ Huy hoặc Khánh review gold/reference vì Tú đã tạo fixture.

## Điều kiện trước khi chạy

1. Parser bảng gán section ổn định `table:0` cho mỗi bảng fixture. Nếu Nhóm 1 chọn key khác, sửa **adapter ánh xạ**, không sửa gold theo chunk ID.
2. Scope resolver phải áp dụng `approval`, `QualityAssessment` và applicability interval. Câu `w02-q06`–`w02-q09` kiểm tra answer path; `w02-q10` kiểm tra review UI và việc không chọn bản pending.
3. Answer path chỉ nhận `SafeBlock`; `w02-q14` phải abstain dù raw source có PII giả lập.
4. `w02-q11` chỉ được answer khi `flow` relations đủ bằng chứng; nếu OCR không giữ được nhánh, behavior đúng là clarify.

## Phủ yêu cầu

| Nhóm | Câu |
|---|---|
| Bảng, đơn vị, kỳ, tổng, conflict | `w02-q01`–`w02-q05` |
| As-of (thời điểm trong quá khứ), full/partial, review | `w02-q06`–`w02-q10` |
| Bản hiện hành (`mode: current`, `current_on: 2026-11-09`) | `w02-q16`–`w02-q19` |
| Lịch sử qua các bản (`all_versions`) | `w02-q20` (cùng `w02-q06`–`w02-q09` hỏi tại ngày trong quá khứ) |
| OCR flow, bảng, văn bản | `w02-q11`–`w02-q13` |
| PII và ngoài phạm vi | `w02-q14`–`w02-q15` |
