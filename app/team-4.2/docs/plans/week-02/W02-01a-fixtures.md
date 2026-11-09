# W02-01a — 25 tài liệu lỗi cài sẵn + nhãn

Owner: B · Reviewer: E · Ngày 1 (commit trước 17h) · Output: `data/team-4.2/fixtures/w02/` + `labels.jsonl`

> Người cài lỗi **không** viết detector. Commit nhãn trước khi ai chạy detector.

## Checklist

- [ ] Chọn chủ đề chung: lao động – tiền lương (lương tối thiểu vùng, quy chế lương, hồ sơ nhân sự giả)
- [x] Duplicate chính xác (2): cùng nội dung, khác tên file
- [x] Near-duplicate (3):
  - [x] khác khoảng trắng/định dạng
  - [x] khác 1 câu không quan trọng
  - [x] khác **1 con số quan trọng** (không được gộp)
- [x] Conflict (3): lương vùng I khác nhau; ngày hiệu lực khác nhau; ...
- [x] Version cũ/mới (3 cặp): v1 2024 → v2 2026, có `effective_from` rõ
- [x] Đơn vị khác nhau (3): `4.960.000 đồng` / `4.960 nghìn đồng` / `4,96 triệu`; `1.500` vs `1,500`
- [x] Lỗi tổng / kỳ (2): tổng cột không khớp; sai quý
- [x] OCR kém (3): scan mờ, nghiêng, dấu vỡ (in ra rồi scan / chụp, hoặc làm nhiễu ảnh)
- [x] PII giả (3): CCCD 12 số, SĐT, email, MST, STK — **chỉ dữ liệu giả**
- [x] Sạch đối chứng (≥3) để đo báo nhầm
- [x] Đủ 3 nhóm định dạng: văn bản (TXT/DOCX/PDF), bảng (CSV/XLSX/bảng DOCX), scan (PDF ảnh)
- [x] Viết `labels.jsonl`, mỗi lỗi 1 dòng:
      `{"doc": "...", "error_type": "...", "location": "...", "expected_action": "skip|review|mask|flag|supersede", "note": "..."}`
- [x] Chia 2 phần `split: dev|test` (dev để chỉnh ngưỡng, test để báo cáo)
- [x] `README.md` trong thư mục fixtures mô tả từng file
- [ ] E review nhãn, commit

## Tiêu chí nghiệm thu

- 20–30 tài liệu, đủ 8 loại lỗi + nhóm sạch; mỗi lỗi có nhãn và hành động mong đợi.

## Ghi chú

- 30 fixture (`w02-01`…`w02-30`); `w02-26`…`w02-30` sinh bằng `evals/team-4.2/runners/build_w02_extra_fixtures.py`.
- Chủ đề thực tế là thủ tục tiếp nhận hồ sơ / mức phạt hành chính (giả lập), không phải lao động – tiền lương → để trống mục chọn chủ đề.
- Nhãn dùng contract `w02.v1` (`expected.issue_codes`, `ingest_status`, `dedup_action`) thay cho dạng `doc/error_type/expected_action` trong kế hoạch; ý nghĩa tương đương.
- Định dạng: TXT, MD, CSV, XLSX, DOCX, PNG, PDF ảnh. Split: 13 dev / 17 test.
- Còn chờ: E review nhãn.
