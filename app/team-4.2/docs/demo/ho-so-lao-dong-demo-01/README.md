# Hồ sơ lao động demo 01: soát hồ sơ nhiều văn bản

Dữ liệu **hư cấu** (người, công ty, CCCD, địa chỉ). Một người lao động ký **ba hợp đồng xác định thời hạn liên tiếp** với
cùng công ty, cùng chức danh, kèm hai phụ lục. Sinh lại file: `python tao_ho_so.py <thư mục>` (cần `python-docx`).
**Không** upload file README này cùng hồ sơ.

| File | Nội dung |
|---|---|
| `01-hdld-2023.docx` | HĐLĐ xác định thời hạn 12 tháng, 01/01/2023–31/12/2023, **có thử việc 2 tháng**, Nhân viên kinh doanh |
| `02-phu-luc-01-hdld-2023.docx` | Phụ lục của HĐ 2023: sửa **lương** (Khoản 1 Điều 3), hiệu lực 01/07/2023 — **hợp lệ** |
| `03-hdld-2024.docx` | HĐLĐ xác định thời hạn 12 tháng, 01/01/2024–31/12/2024, không thử việc |
| `04-hdld-2025.docx` | HĐLĐ xác định thời hạn 24 tháng, 01/01/2025–31/12/2026, **thử việc lại 2 tháng**, cùng chức danh |
| `05-phu-luc-01-hdld-2025.docx` | Phụ lục của HĐ 2025: **gia hạn thời hạn** tới 30/06/2027 (Khoản 2 Điều 1), hiệu lực 01/06/2026 |

## Các bước demo (Contract Studio → "Hồ sơ nhiều văn bản", hoặc `/contract-studio/#ho-so`)

1. Chọn **cả 5 file** một lần. Hệ thống đọc và đoán loại: 3 "Hợp đồng lao động", 2 "Phụ lục hợp đồng".
2. Mục 1: phụ lục `02-…` chọn "sửa đổi hợp đồng" = `01-hdld-2023.docx`; phụ lục `05-…` = `04-hdld-2025.docx`
   (hồ sơ có nhiều hợp đồng chính nên hệ thống không tự gán). Với cả ba hợp đồng, ô `employee` chọn bên người lao động.
3. Mục 2: đặt tên các bên (vd. b1 = "Phạm Minh Khoa", vai trò Người lao động; b2 = "Ánh Dương", Người sử dụng lao động).
   Ngày soát để mặc định (hôm nay) hoặc 25/11/2026.
4. Bấm **Soát hồ sơ** (lần đầu gọi LLM trích dữ kiện ~1 phút).
5. Mục 3 cho thấy hồ sơ theo thời gian (3 hợp đồng nối liền, 2 phụ lục). Mục câu hỏi gợi ý hỏi 4 điều về người lao động
   (cao tuổi, nước ngoài, giám đốc DN nhà nước, cán bộ công đoàn): trả lời **Không** cả 4 — chỉ chạy lại luật, không gọi
   LLM — để thấy kết luận "số lần ký" chuyển từ *Chưa đủ dữ kiện* sang *Vi phạm*.

## Kết quả (đã chạy thật 25/11/2026, LLM của app, ngày soát 25/11/2026)

| Kết luận | Đối tượng | Hệ thống | Đúng theo luật | Căn cứ |
|---|---|---|---|---|
| Ký quá 2 HĐ xác định thời hạn liên tiếp (`content.term/r5`) | người lao động | **Vi phạm** sau khi trả lời 4 câu hỏi (trước đó: Chưa đủ dữ kiện) | Vi phạm: HĐ thứ ba phải là không xác định thời hạn | BLLĐ 2019 Đ20.2.c |
| Thử việc hai lần cùng công việc (`probation.once/r2`) | người lao động + "nhân viên kinh doanh" | **Vi phạm** | Vi phạm | BLLĐ 2019 Đ25 |
| HĐ hết hạn mà vẫn làm quá 30 ngày (`content.term/r6`) | người lao động | Phù hợp | Phù hợp (các HĐ nối liền) | Đ20.2.b |
| Phụ lục ghi rõ điều khoản sửa và ngày hiệu lực (`appendix.states_change/r1`) | HĐ 2023, HĐ 2025 | Phù hợp | Phù hợp | Đ22.2 câu 2 |
| Phụ lục không được sửa thời hạn (`content.term/r7`) | HĐ 2023 | Phù hợp | Phù hợp (chỉ sửa lương) | Đ22.2 câu 1 |
| Phụ lục không được sửa thời hạn (`content.term/r7`) | HĐ 2025 | **Chưa đủ dữ kiện** | **Vi phạm** (phụ lục gia hạn thời hạn) | Đ22.2 câu 1 |

**Điểm lệch (nói trước khi demo):** dòng cuối. Khi trích bộ "HĐ 2025 + phụ lục", LLM chỉ giữ thời hạn *sau khi sửa*
(30 tháng, câu trích nằm ở phụ lục), không giữ thời hạn gốc của Khoản 2 Điều 1, nên engine không xác nhận được phụ lục sửa
đúng điều khoản chứa thời hạn → *chưa biết*, không kết luận vi phạm (đúng nguyên tắc "thiếu dữ kiện không thành vi phạm").
Xem `docs/superpowers/notes/w04-rule-engine/han_che_va_loi_ton_dong.md` mục T.7.

Đáp án "Đúng theo luật" do Claude viết theo yêu cầu của Tùng, **cần Tùng duyệt**.
