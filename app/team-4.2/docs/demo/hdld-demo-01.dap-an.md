# Hợp đồng demo `hdld-demo-01.docx` — đáp án để đối chiếu

Toàn bộ dữ liệu là **hư cấu** (công ty, người đại diện, người lao động, số CCCD, mã số doanh nghiệp).
Hợp đồng được viết theo danh sách nội dung bắt buộc tại Điều 21 BLLĐ 2019, **không** sao chép nguyên văn từ
mẫu nào trên mạng. Lỗi và chỗ thiếu được cài có chủ ý; **không** đưa file này vào hợp đồng khi upload.

- Ngày ký: 04/11/2026. Làm việc từ 10/11/2026. Hà Nội (vùng I). Kế toán viên, trình độ đại học, nữ.
- Các căn cứ dưới đây đã đối chiếu với đồ thị luật v2 (build `12622da3d53bc9ed`) ở ngày 04/11/2026.

## A. Điểm SAI cố ý (vi phạm — hệ thống nên báo `violation`)

| # | Vị trí trong HĐ | Nội dung sai | Luật quy định | Concept kỳ vọng |
|---|---|---|---|---|
| 1 | Điều 1.2 | Hợp đồng xác định thời hạn **48 tháng** | Tối đa 36 tháng (Điều 20 khoản 1 điểm b) | `content.term` |
| 2 | Điều 1.3 | Thử việc **90 ngày**, còn cho gia hạn thêm 30 ngày | Công việc cần trình độ từ cao đẳng trở lên: tối đa 60 ngày; chỉ thử việc một lần (Điều 25) | `probation.duration`, `probation.once` |
| 3 | Điều 1.4 | Lương thử việc **70%** | Ít nhất 85% (Điều 26) | `probation.pay` |
| 4 | Điều 3.1 | Lương cơ bản **4.500.000 đ** ở vùng I | Không thấp hơn lương tối thiểu vùng (Điều 90 khoản 2; mức vùng theo nghị định đang hiệu lực) | `wage.minimum_regional` |
| 5 | Điều 4.3 | Bắt buộc làm thêm giờ, **không cần sự đồng ý** | Phải được sự đồng ý của người lao động (Điều 107 khoản 2 điểm a) | `hours.overtime_limit` |
| 6 | Điều 4.4 | Làm thêm ngày thường **130%** | Ít nhất 150% (Điều 98 khoản 1 điểm a) | `wage.overtime_pay` |
| 7 | Điều 4.5 | Làm thêm tới **400 giờ/năm** | Không quá 200 giờ/năm (Điều 107 khoản 2 điểm c); 300 giờ chỉ cho các trường hợp đặc biệt ở khoản 3 | `hours.overtime_limit` |
| 8 | Điều 5.1 | Giữ **bản chính bằng đại học** | Cấm giữ bản chính văn bằng, chứng chỉ (Điều 17 khoản 1) | `prohibit.keep_documents` |
| 9 | Điều 5.2 | **Đặt cọc 5.000.000 đ**, nghỉ trước hạn mất cọc | Cấm buộc bảo đảm bằng tiền hoặc tài sản (Điều 17 khoản 2) | `prohibit.deposit` |
| 10 | Điều 5.3 | **Phạt 100.000 đ** mỗi lần đi muộn, trừ vào lương | Cấm phạt tiền, cắt lương thay xử lý kỷ luật (Điều 127 khoản 2) | `prohibit.fine_instead_of_discipline` |
| 11 | Điều 6 | Cam kết **không kết hôn, không mang thai 24 tháng**; vi phạm thì chấm dứt hợp đồng | Không được chấm dứt hợp đồng vì lý do kết hôn, mang thai (Điều 137 khoản 3) | `maternity.no_dismissal` |
| 12 | Điều 7.1 | NLĐ báo trước **60 ngày** để nghỉ | Hợp đồng xác định thời hạn 12–36 tháng: báo trước ít nhất 30 ngày (Điều 35 khoản 1 điểm b); không có mức tối đa 60 ngày | `termination.employee_unilateral` |
| 13 | Điều 7.3 | NLĐ **từ bỏ trợ cấp thôi việc** | Trợ cấp thôi việc là quyền theo luật (Điều 46) | `termination.severance` |

Mọi căn cứ trong bảng A đã được đối chiếu với đồ thị luật ở ngày 04/11/2026.

## B. Quyền lợi BỊ BỎ (hợp đồng im lặng — hệ thống nên báo `missing_content` hoặc `hidden_right`)

| # | Thiếu | Căn cứ | Concept kỳ vọng |
|---|---|---|---|
| 14 | Không có điều khoản **bảo hiểm xã hội, y tế, thất nghiệp** | Điều 21 khoản 1 điểm i; Điều 168 khoản 1 | `content.insurance` |
| 15 | Không có **nghỉ hằng năm** (12 ngày làm việc) | Điều 113 khoản 1 | `leave.annual` |
| 16 | Không có **nghỉ lễ, tết** hưởng nguyên lương | Điều 112 khoản 1 | `rest.holidays` |
| 17 | Không có **nghỉ việc riêng** hưởng lương (kết hôn, tang…) | Điều 115 khoản 1 | `leave.personal_paid` |
| 18 | Không có **nghỉ thai sản 06 tháng** và bảo đảm việc làm cũ | Điều 139; Điều 140 | `maternity.leave`, `maternity.job_guarantee` |
| 19 | Không có **trang bị bảo hộ lao động** | Điều 21 khoản 1 điểm h | `content.protective_equipment` |
| 20 | Không có **đào tạo, bồi dưỡng** | Điều 21 khoản 1 điểm k | `content.training` |
| 21 | Không có **chế độ nâng bậc, nâng lương** | Điều 21 khoản 1 điểm e; Điều 103 | `content.raise_policy` |

## C. Điều khoản ĐÚNG, làm đối chứng (hệ thống không nên báo vi phạm)

- Điều 1.1: loại hợp đồng xác định thời hạn (hợp pháp, chỉ sai ở thời hạn).
- Điều 3.3: trả lương một lần mỗi tháng — `wage.pay_period`.
- Điều 3.4: làm đêm cộng 30% — `wage.night_pay`.
- Điều 4.1–4.2: 8 giờ/ngày, 48 giờ/tuần, nghỉ Chủ nhật — `hours.normal`, `rest.weekly`.
- Điều 7.2, 7.4: chấm dứt hợp đồng theo luật, bàn giao trong 07 ngày.

## Cách demo gợi ý

1. Upload `hdld-demo-01.docx`, xác nhận dữ kiện: ngày áp luật **04/11/2026**, vùng **I**, lao động **nữ**, trình độ **đại học**.
2. Chạy soát. Đếm số kết quả `violation` và `missing_content`, so với bảng A và B.
3. Mở một kết quả, kiểm tra căn cứ luật hiển thị đúng điều và có link văn bản gốc.
4. Đổi ngày áp luật về một mốc cũ để xem phiên bản luật đổi theo ngày.
