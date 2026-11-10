# Failure cases tuần 2 — Team 4.2

Các case dưới đây là kịch bản demo/evaluation đã đóng băng từ fixtures. Chúng
không khẳng định detector đã đạt kết quả; kết quả thực tế phải được tạo bằng
pipeline và chấm với `score_w02_quality.py`.

| Case | Fixture | Rủi ro | Hành vi đúng bắt buộc |
|---|---|---|---|
| Exact re-ingest | `w02-01`, `w02-04` | File giống hệt bị index hai lần | Ghi SourceRecord lần thu thập mới, link version cũ, không tăng chunk/index. |
| Near duplicate | `w02-06`–`w02-08` | Xoá nhầm văn bản khác biệt có ý nghĩa | Trả `dedup.near`, mở review; không tự gộp/xoá. |
| Số cùng nghĩa khác đơn vị | `w02-09`, `w02-10` | Báo conflict sai giữa VND và triệu VND | Chuẩn hoá thành 1.500.000 VND, kết quả `equal`. |
| Số mơ hồ | `w02-13` | Đoán sai `1,500.000` | Trả `invalid`/finding locale; không tạo conflict. |
| Tổng cộng sai | `w02-20` | Suy diễn “nguồn đúng” từ số học | Báo `numeric.sum_mismatch`; không đánh dấu `verified`. |
| PII trong cell | `w02-22` | Email/số điện thoại đi vào embedding, log hoặc issue | Mask trước mọi dịch vụ/log; evidence chỉ chứa thông tin đã mask. |
| Version tương lai | `w02-15` | Truy vấn current lấy văn bản chưa hiệu lực | `current` không chọn; `as_of` sau ngày hiệu lực mới chọn. |
| Sửa một phần | `w02-14`, `w02-16` | Bản mới ghi đè các Điều không đổi | Chỉ Điều 3 đổi theo mapping; Điều 1/2 vẫn lấy revision cũ. |
| Scan flowchart | `w02-23` | Mất thứ tự/nhánh khi flatten plain text | Giữ ảnh gốc, `next`/`branch` và condition; confidence thấp thì review. |
| PII regex nuốt số tiền | mẫu âm trong `tests/test_pii.py` | Regex SĐT cũ coi `84.000.000.000 đồng` là số điện thoại → mất mức phạt | SĐT phải đúng đầu số (03/05/07/08/09, 02x) và kiểu nhóm số; MST/STK/CMND chỉ khi có từ khoá. Đã sửa, có test. |
| PII lọt qua bảng DOCX làm phẳng | `w02-27` | Thân văn bản DOCX giữ bảng dạng `ô \| ô`, mất header nên MST/STK không bị nhận ra | Mask bảng trước (theo header cột), rồi thay mọi giá trị PII đã biết trong thân văn bản. Đã sửa, test rò rỉ phủ. |
| Bảng dài mất header | DOCX 60 hàng (`measure_w02_parser_loss.py`) | Parser tuần 1: 1/2 chunk có header và đơn vị | `chunk_tables` lặp caption + đơn vị + header: 3/3 chunk. |
| Bảng OCR mức thu bị báo thiếu đơn vị/kỳ | `w02-24` (dev), `w02-30` | Đơn vị nằm ở tầng header giữa `Mức thu tối đa (nghìn đồng) / Mầm non`; cột "TT" bị coi là cột tiền vì tầng trên chứa "mức thu"; bảng luật không có cột Kỳ | Tìm đơn vị ở mọi tầng; chỉ xét tầng header gần cột; không có cột Kỳ thì không báo thiếu kỳ (hiệu lực theo văn bản). Đã sửa, có test. |
| Bộ lọc header xoá nhầm nội dung | `results/w02-ocr-hf-filter/removed_lines.jsonl` | Luật bản quyền bắt `(C)` trong chú thích hình và ký tự `©` rác của OCR; DOI trong danh mục tham khảo bị coi là URL footer; trang ngắn bị coi cả trang là "mép" | © / (c) phải kèm năm; loại trừ DOI; vùng mép ≤ 1/3 trang và đếm lặp riêng đầu/cuối trang. Đã sửa, có test. |
| Số mơ hồ theo locale vi-VN | `w02-13`, `tests/test_validate.py` | `parse_decimal("1,500.000", vi-VN)` trả 1.5 (nhóm nằm sau dấu thập phân) | Trả `None` → `numeric.invalid_locale`. Đã sửa, có test. |

Khi báo cáo, mỗi hàng cần dẫn tới `evals/team-4.2/results/w02-*` chứa config,
raw output đã mask, và kết quả pass/fail; không dùng labels làm logic detector.
