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

Khi báo cáo, mỗi hàng cần dẫn tới `evals/team-4.2/results/w02-*` chứa config,
raw output đã mask, và kết quả pass/fail; không dùng labels làm logic detector.
