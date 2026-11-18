# Soát hợp đồng ANlI8FDVG13zVp8nauoJU25e

Ngày áp luật: 2021-01-01 · danh mục 0.2-draft

**Cảnh báo:**
- Không có ngày ký: tạm dùng giá trị luật từ 2021-01-01

## Thiếu nội dung bắt buộc (1)

- **Trang bị bảo hộ lao động** (`content.protective_equipment/r1`)
  - Căn cứ: bo-luat:45/2019/QH14#d21.k1.h

## Quyền mà hợp đồng không nhắc (8)

- **Hủy bỏ thử việc không cần báo trước, không bồi thường** (`probation.cancel_no_notice/r1`)
  - Căn cứ: bo-luat:45/2019/QH14#d27.k2
- **Tiền lương làm thêm giờ** (`wage.overtime_pay/r1`)
  - Luật: min_ot_weekday = 150 percent; min_ot_weekly_rest = 200 percent; min_ot_holiday = 300 percent
  - Căn cứ: bo-luat:45/2019/QH14#d98.k1, bo-luat:45/2019/QH14#d98.k3
- **Tiền lương làm việc ban đêm** (`wage.night_pay/r1`)
  - Luật: min_night_extra = 30 percent
  - Căn cứ: bo-luat:45/2019/QH14#d98.k2, bo-luat:45/2019/QH14#d106
- **Nghỉ việc riêng hưởng nguyên lương** (`leave.personal_paid/r1`)
  - Luật: min_marriage_leave = 3 day
  - Căn cứ: bo-luat:45/2019/QH14#d115.k1
- **NLĐ đơn phương chấm dứt hợp đồng** (`termination.employee_unilateral/r1`)
  - Luật: notice = 30 day
  - Căn cứ: bo-luat:45/2019/QH14#d35.k1, bo-luat:45/2019/QH14#d35.k2
- **Trợ cấp thôi việc** (`termination.severance/r1`)
  - Căn cứ: bo-luat:45/2019/QH14#d46.k1, bo-luat:45/2019/QH14#d46.k2, bo-luat:45/2019/QH14#d46.k3
- **Thời hạn thanh toán khi chấm dứt hợp đồng** (`termination.settlement_deadline/r1`)
  - Luật: max_settlement = 14 workday
  - Căn cứ: bo-luat:45/2019/QH14#d48.k1
- **Không bị sa thải, đơn phương chấm dứt vì kết hôn, mang thai, nghỉ thai sản, nuôi con nhỏ** (`maternity.no_dismissal/r1`)
  - Căn cứ: bo-luat:45/2019/QH14#d137.k3

## Có thể có quyền (cần thêm thông tin về bạn) (6)

- **Không làm đêm, làm thêm giờ, đi công tác xa khi mang thai hoặc nuôi con nhỏ** (`maternity.no_night_overtime_travel/r1`)
  - Thiếu dữ kiện: pregnancy_month, child_under_12_months, employee_consent
  - Căn cứ: bo-luat:45/2019/QH14#d137.k1
- **Chuyển việc nhẹ hơn hoặc giảm 01 giờ làm mỗi ngày khi mang thai** (`maternity.lighter_work/r1`)
  - Thiếu dữ kiện: pregnant, work_condition
  - Căn cứ: bo-luat:45/2019/QH14#d137.k2
- **Nghỉ 30 phút mỗi ngày khi hành kinh, 60 phút mỗi ngày khi nuôi con dưới 12 tháng** (`maternity.breaks/r1`)
  - Luật: menstruation_break = 30 minute; nursing_break = 60 minute
  - Thiếu dữ kiện: employee_is_female, child_under_12_months
  - Căn cứ: bo-luat:45/2019/QH14#d137.k4
- **Lao động nữ mang thai đơn phương chấm dứt hoặc tạm hoãn hợp đồng** (`maternity.terminate_or_suspend/r1`)
  - Thiếu dữ kiện: pregnant, medical_certificate
  - Căn cứ: bo-luat:45/2019/QH14#d138.k1, bo-luat:45/2019/QH14#d138.k2, bo-luat:45/2019/QH14#d35.k2.đ
- **Nghỉ thai sản 06 tháng** (`maternity.leave/r1`)
  - Luật: min_maternity_leave = 6 month
  - Thiếu dữ kiện: pregnant, maternity_leave
  - Căn cứ: bo-luat:45/2019/QH14#d139.k1, bo-luat:45/2019/QH14#d139.k2
- **Bảo đảm việc làm cũ sau khi nghỉ thai sản** (`maternity.job_guarantee/r1`)
  - Thiếu dữ kiện: pregnant
  - Căn cứ: bo-luat:45/2019/QH14#d140

## Cần thêm dữ kiện (7)

- **Thời gian thử việc tối đa** (`probation.duration/r1`)
  - Hợp đồng [p0.d6]: “Thời gian thử việc: 02 tháng, từ ngày 02/01/2025 đến ngày 01/03/2025.”
  - Thiếu dữ kiện: job_level
  - Căn cứ: bo-luat:45/2019/QH14#d25, bo-luat:45/2019/QH14#d24.k3
- **Mức lương không thấp hơn lương tối thiểu vùng** (`wage.minimum_regional/r1`)
  - Hợp đồng [p0.d2]: “15.000.000 đồng/tháng”
  - Hợp đồng [p2.d1]: “Sửa đổi Điều 2 Hợp đồng lao động về lương căn bản: Lương căn bản của Người lao động được điều chỉnh từ 15.000.000 đồng/tháng lên 17.000.000 đồng/tháng.”
  - base_salary_vnd từ 2025-07-01: 17000000 vnd [p2.d1]
  - Thiếu dữ kiện: wage_region
  - Căn cứ: bo-luat:45/2019/QH14#d90.k2, bo-luat:45/2019/QH14#d91
- **Nghỉ hằng tuần** (`rest.weekly/r1`)
  - Hợp đồng [p0.d3]: “Nghỉ hàng tuần: Chủ nhật”
  - Luật: min_weekly_rest = 24 hour
  - Thiếu dữ kiện: weekly_rest
  - Căn cứ: bo-luat:45/2019/QH14#d111.k1
- **Nghỉ lễ, tết hưởng nguyên lương** (`rest.holidays/r1`)
  - Hợp đồng [p0.d3]: “Người lao động được nghỉ lễ, tết theo luật định”
  - Luật: min_paid_holidays = 11 day
  - Thiếu dữ kiện: paid_holidays
  - Căn cứ: bo-luat:45/2019/QH14#d112.k1
- **Nghỉ hằng năm hưởng nguyên lương** (`leave.annual/r1`)
  - Hợp đồng [p0.d3]: “nghỉ phép năm có hưởng lương (01 ngày phép/01 tháng, 12 ngày phép/01 năm)”
  - Thiếu dữ kiện: work_condition
  - Căn cứ: bo-luat:45/2019/QH14#d113.k1, bo-luat:45/2019/QH14#d113.k2, bo-luat:45/2019/QH14#d113.k3, bo-luat:45/2019/QH14#d114
- **NSDLĐ đơn phương chấm dứt hợp đồng** (`termination.employer_unilateral/r2`)
  - Hợp đồng [p0.d5]: “Có quyền chuyển tạm thời lao động, ngừng việc, thay đổi, tạm hoãn, chấm dứt HĐLĐ”
  - Hợp đồng [p1.d2]: “Người lao động đồng ý sẽ bị xử lý kỷ luật lao động đến mức cao nhất là sa thải (theo quy định trong Nội quy lao động)”
  - Luật: notice = 30 day
  - Thiếu dữ kiện: employer_notice
  - Căn cứ: bo-luat:45/2019/QH14#d36.k1, bo-luat:45/2019/QH14#d36.k2, bo-luat:45/2019/QH14#d36.k3, bo-luat:45/2019/QH14#d37
- **Hoàn trả chi phí đào tạo** (`training.cost_repayment/r1`)
  - Hợp đồng [p0.d4]: “nhân viên phải hoàn trả lại 100% phí đào tạo và các khoản chế độ đã được nhận trong thời gian đào tạo”
  - Thiếu dữ kiện: has_separate_training_contract
  - Căn cứ: bo-luat:45/2019/QH14#d62

Không có vấn đề: 22 rule.
