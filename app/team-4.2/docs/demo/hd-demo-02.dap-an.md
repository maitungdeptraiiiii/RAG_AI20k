# Ba hợp đồng demo (vay tiền, mua bán hàng hóa, thuê nhà) — đáp án để đối chiếu

Dữ liệu **hư cấu** (người, công ty, CCCD, mã số doanh nghiệp, địa chỉ). Bố cục theo mẫu hợp đồng phổ biến của từng loại,
lỗi cài có chủ ý theo các khái niệm trong gói luật (`app/team-4.2/src/rag/rules/packs/`). **Không** upload file này cùng hợp đồng.

**Chưa chạy hệ thống trên ba file này.** Cột "Chắc chắn" nghĩa là: khái niệm đó có trong gói luật và điều khoản cài khớp
`phrasing` + slot của nó. Dòng "Thử" là khái niệm của `civil_general` mà tôi chưa kiểm tra rule thực tế bắt được hay không.

---

## 1. `hd-vay-demo-01.docx` — vay tiền cá nhân (gói `civil_loan`; ngày ký 12/11/2026)

Dữ kiện nên chọn khi xác nhận: ngày áp luật 12/11/2026; có lãi; không áp luật tổ chức tín dụng (`special_law_applies = false`).

| # | Vị trí | Nội dung sai | Luật | Concept | Chắc chắn |
|---|---|---|---|---|---|
| 1 | Điều 3.1 | Lãi **30%/năm** (2,5%/tháng) | Trần 20%/năm, phần vượt vô hiệu (BLDS Đ468.1) | `loan.interest_cap` | Chắc |
| 2 | Điều 3.3 | Lãi nợ gốc quá hạn **54%/năm** | Không quá 150% trần = 30%/năm (NQ 01/2019 Đ5.2.c) | `loan.overdue_interest_cap` | Chắc |
| 3 | Điều 4.3 | Bên cho vay đòi lại **trước hạn bất cứ lúc nào**, không cần bên vay đồng ý | Chỉ đòi trước hạn khi dùng sai mục đích (BLDS Đ465.3, Đ467) | `loan.lender_early_recall` | Chắc |
| 4 | Điều 5.3 | Bên A **đơn phương chấm dứt không cần thông báo** | Phải thông báo (BLDS) | `civil.unilateral_termination` | Thử |
| 5 | Điều 5.4 | Bên B **từ bỏ quyền khiếu nại** mọi khoản lãi, phí "trong mọi trường hợp" | Điều khoản miễn trách bất công bên không soạn: vô hiệu (BLDS Đ405.3/Đ406.3) | `civil.standard_terms_exemption` | Thử |

Đối chứng đúng: Điều 4.2 (trả trước hạn, kèm lãi đến hết kỳ hạn — Đ470.2), Điều 1–2 (có số tiền, thời hạn 12 tháng),
Điều 7.1 (sửa đổi bằng văn bản).

---

## 2. `hd-mua-ban-demo-01.docx` — mua bán hàng hóa giữa hai công ty (gói `commercial` + `civil_general`; ngày ký 16/11/2026)

Dữ kiện nên chọn: ngày áp luật 16/11/2026; hợp đồng thương mại (`ltm_governs = true`).

| # | Vị trí | Nội dung sai | Luật | Concept | Chắc chắn |
|---|---|---|---|---|---|
| 1 | Điều 5.1 | Phạt vi phạm **15%** giá trị phần nghĩa vụ bị vi phạm | Tối đa 8% (LTM 2005 Đ301) | `commercial.penalty_cap` | Chắc |
| 2 | Điều 6.1 | Tạm ngừng / đình chỉ / hủy bỏ hợp đồng **không cần thông báo** | Phải thông báo ngay (LTM Đ315) | `commercial.sanction_notice` | Chắc |
| 3 | Điều 7.1 | Sửa đổi hợp đồng **bằng lời nói / tin nhắn**, không lập văn bản | Sửa đổi theo hình thức của hợp đồng gốc (BLDS) | `civil.amendment_form` | Thử |
| 4 | Điều 2.3 | Bên bán **không chịu trách nhiệm** mọi lỗi, bên mua **từ bỏ khiếu nại** "trong mọi trường hợp" | Miễn trách bất công: vô hiệu (BLDS Đ405.3) | `civil.standard_terms_exemption` | Thử |

Đối chứng đúng, **không** nên báo vi phạm: Điều 4.3 lãi chậm thanh toán 18%/năm (LTM Đ306 cho thỏa thuận, không áp trần BLDS —
`commercial.late_payment_interest_ltm`); Điều 5.2 phạt không loại trừ bồi thường; Điều 6.2 bất khả kháng có thông báo 07 ngày.

---

## 3. `hd-thue-nha-demo-01.docx` — thuê căn hộ (gói `civil_lease`; hợp đồng bắt đầu 01/12/2026, áp Luật Nhà ở 27/2023)

Hợp đồng cố ý **không ghi ngày ký** ở phần mở đầu. Dữ kiện nên chọn: ngày áp luật 12/11/2026 (hoặc bất kỳ ngày sau 01/08/2024).

### A. Điểm sai

| # | Vị trí | Nội dung sai | Luật | Concept | Chắc chắn |
|---|---|---|---|---|---|
| 1 | Điều 5.1 | Chủ nhà **lấy lại nhà bất cứ lúc nào**, báo trước 03 ngày | Chỉ chấm dứt theo căn cứ luật định (Luật Nhà ở 2023 Đ172.1–2) | `lease.landlord_termination` | Chắc |
| 2 | Điều 5.2 | Chấm dứt khi chậm tiền thuê **quá 01 tháng** | Phải nợ từ 03 tháng (Đ172.2.b) | `lease.nonpayment_termination` | Chắc |
| 3 | Điều 5.3 | Bên thuê **không được chấm dứt** "trong mọi trường hợp", mất cọc | Bên thuê có quyền đơn phương trong các trường hợp luật định (Đ172.3) | `lease.tenant_termination_right` | Chắc |
| 4 | Điều 6 | Bên thuê **chịu mọi chi phí sửa**, kể cả hư hỏng kết cấu không do mình gây ra | Bên cho thuê phải sửa hư hỏng lớn (BLDS Đ477) | `lease.landlord_major_repairs` | Chắc |
| 5 | Điều 7.1–7.2 | Vào nhà **không báo trước**; **cắt điện, nước, khóa cửa** khi chậm tiền | Bảo đảm sử dụng nhà ổn định (BLDS Đ478) | `lease.quiet_enjoyment` | Chắc |

### B. Nội dung bắt buộc BỊ BỎ (hợp đồng im lặng)

| # | Thiếu | Căn cứ | Concept |
|---|---|---|---|
| 6 | **Ngày, tháng, năm ký** (mở đầu chỉ có "Hôm nay, tại Hà Nội") | Luật Nhà ở 2023 Đ163.k10 | `lease.content_sign_date` |
| 7 | **Địa chỉ của Bên thuê** (chỉ có họ tên, CCCD, điện thoại) | Đ163.k1 | `lease.content_parties` |

Đối chứng đúng: Điều 1 mô tả nhà (`lease.content_property`), Điều 3 thời hạn và bàn giao (`lease.content_term_handover`),
Điều 4 giá thuê (`lease.content_rent_payment`; hợp đồng có giá nhưng không ghi kỳ và cách trả — nếu hệ thống báo thiếu phần này
thì cũng hợp lý, ghi lại là kết quả ngoài dự kiến).

---

## Cách demo gợi ý

1. Upload từng file, xác nhận dữ kiện như từng mục trên.
2. Chạy soát, đếm kết quả `violation` / `missing_content`, so với các bảng. Các dòng "Thử" mà hệ thống không bắt được là
   phát hiện hữu ích cho `w04-known-issues`, không phải lỗi của hợp đồng.
3. Mở một kết quả, kiểm tra căn cứ luật hiển thị đúng điều và có link văn bản gốc.
