# Ý tưởng: Agent "Soát hợp đồng trước khi ký"

> Trạng thái: **ý tưởng / bản nháp** — chưa phải thiết kế đã chốt.
> Ngày: 2026-11-03 · Nhóm: team-4.2

## 1. Bài toán

Chatbot hiện tại trả lời câu hỏi luật dạng "tôi làm việc A thì bị tội gì". Bước nâng cấp: người dùng
**upload hợp đồng/tài liệu**, agent chỉ ra từng điều khoản **vi phạm pháp luật** hoặc **bất lợi** cho họ,
kèm căn cứ điều luật, và soạn sẵn đề nghị sửa để gửi lại bên kia.

### Người dùng mục tiêu
- **Sinh viên sắp ký hợp đồng thuê trọ** — không rành luật, cần lời giải thích dễ hiểu.
- **Một bên sắp ký hợp đồng với đối tác** (cá nhân kinh doanh / doanh nghiệp nhỏ) — cần phân tích kỹ hơn, trích dẫn cụ thể.

### Kết quả trả về (cho mọi loại hợp đồng)
- Danh sách điều khoản gắn nhãn: 🔴 **vi phạm pháp luật** · 🟠 **bất lợi cho bạn** · 🟢 **ổn**, mỗi mục **kèm trích dẫn điều luật**.
- **Điều khoản còn thiếu** mà lẽ ra nên có.
- **Gợi ý câu chữ sửa** / thư đề nghị sửa đổi.
- Ghi chú: "Căn cứ luật phiên bản ngày X — mang tính tham khảo, không thay thế luật sư."

## 2. Các case áp dụng

### Làm được ngay với corpus hiện có
Corpus hiện tại: BLDS 2015, BLLĐ 2019, BLHS 2015, BLTTDS 2015, BLTTHS 2015, BL Hàng hải 2015.

**a. Hợp đồng thuê trọ / thuê nhà**
- Đặt cọc một chiều: bên thuê bỏ thì mất cọc, chủ nhà vi phạm không bị phạt tương ứng (BLDS Điều 328).
- Chủ nhà được đơn phương chấm dứt bất cứ lúc nào / báo trước quá ngắn (BLDS — phần thuê tài sản).
- Phí ẩn: điện nước vượt giá quy định, phí dịch vụ không rõ, tự ý tăng giá giữa kỳ.
- Đẩy toàn bộ sửa chữa lớn sang người thuê.
- Điều khoản trái luật/vô hiệu: tự ý vào phòng, giữ giấy tờ tùy thân.
- Thiếu thông tin bắt buộc: thời hạn, thông tin chủ sở hữu thật (rủi ro "cò" cho thuê lại).

**b. Hợp đồng lao động / thử việc / thực tập có lương**
- Thử việc quá thời hạn hoặc lương thử việc < 85% (BLLĐ Điều 25, 26).
- Giữ bằng gốc, bắt đặt cọc tiền (BLLĐ Điều 17 — hành vi bị cấm).
- Phạt tiền / trừ lương thay xử lý kỷ luật (BLLĐ Điều 127).
- Không cạnh tranh, bồi hoàn chi phí đào tạo bất hợp lý.
- Gia hạn hợp đồng xác định thời hạn quá số lần cho phép.

**c. Hợp đồng vay tiền giữa cá nhân**
- Lãi suất > 20%/năm (BLDS Điều 468), lãi chồng lãi.
- Lãi cực cao có dấu hiệu cho vay nặng lãi (BLHS Điều 201).

### Cần mở rộng corpus
**d. Hợp đồng giữa doanh nghiệp với đối tác** — thiếu Luật Thương mại 2005. Nếu chỉ dựa BLDS sẽ
tư vấn sai (ví dụ phạt vi phạm tối đa 8% theo LTM Điều 301, BLDS không giới hạn).

**e. Hợp đồng theo mẫu** (gym, internet, khóa học, app) — Luật Bảo vệ quyền lợi người tiêu dùng 2023
có danh sách điều khoản **không có hiệu lực** trong hợp đồng theo mẫu.

## 3. Mở rộng corpus — theo loại hợp đồng, không nạp tràn lan

| Loại hợp đồng | Văn bản cần thêm | Lý do |
|---|---|---|
| Thuê trọ, thuê nhà | Luật Nhà ở 2023, Luật Kinh doanh BĐS 2023 | Quy định riêng về thuê nhà ở, ưu tiên hơn BLDS |
| Doanh nghiệp – đối tác | Luật Thương mại 2005, Luật Doanh nghiệp 2020 | Phạt vi phạm, bồi thường, miễn trách |
| Hợp đồng theo mẫu | Luật BVQLNTD 2023 | Danh sách điều khoản vô hiệu |
| Lao động | Nghị định 145/2020/NĐ-CP | Hướng dẫn chi tiết BLLĐ |
| Vay tiền | Nghị quyết 01/2019/NQ-HĐTP | Cách tính lãi, phạt chậm trả |

### Checklist "cờ đỏ" theo loại hợp đồng
Ngoài văn bản luật, xây một bộ checklist do người soạn tay cho mỗi loại hợp đồng; mỗi mục gồm:
mô tả rủi ro, mức độ (🔴/🟠), điều luật căn cứ, câu chữ đề xuất sửa.

Lý do:
- RAG thuần **không phát hiện được điều khoản bị thiếu** (không có gì để retrieve) — checklist thì có.
- Checklist cho agent biết **cần tìm gì**, giảm phụ thuộc vào retrieval multi-hop, vốn là điểm yếu
  hiện tại (benchmark: hybrid recall@5 ≈ 0.25 với câu multi-hop).

## 4. Luồng soát hợp đồng (có người duyệt)

```
Upload (PDF/DOCX/ảnh)
  → Nhận diện loại hợp đồng
  → Tách thành từng điều khoản
  → Mỗi điều khoản: đối chiếu checklist + retrieve luật liên quan
  → [Người dùng] xem danh sách vấn đề, bỏ mục không quan tâm, thêm lo ngại riêng
  → Agent soạn báo cáo có trích dẫn + thư đề nghị sửa
  → Kiểm tra: mọi trích dẫn phải tồn tại trong corpus, đúng điều/khoản
  → [Người dùng] chỉnh sửa / duyệt → xuất báo cáo
```

Trạng thái báo cáo: nháp → đã duyệt → đã xuất; chỉnh sửa sau duyệt phải duyệt lại.
Báo cáo do agent sinh **không** được ingest ngược vào corpus như nguồn đã xác minh.

## 5. Luồng giữ corpus đúng luật hiện hành

```
Kiểm tra nguồn văn bản định kỳ → phát hiện văn bản mới / sửa đổi / hết hiệu lực
  → diff → parse/validate → kiểm tra xung đột với bản cũ
  → chạy lại benchmark (ngưỡng regression chốt trước)
  → [Người duyệt] approve / reject → cập nhật index (có snapshot để rollback)
```

Audit: ai duyệt, lúc nào, diff, version, lý do.

> Phần 4 và 5 có vẻ khớp với yêu cầu tuần 5 (`weeks/week-05/README.md`): luồng sáng tạo có chốt duyệt
> và luồng dữ liệu có regression — cần xác nhận.

## 6. Rủi ro chính

- **Tách điều khoản sai** với hợp đồng scan/ảnh chụp, định dạng lộn xộn.
- **Retrieval paraphrase/multi-hop yếu** → bỏ sót căn cứ hoặc trích sai điều.
- **Áp sai luật chuyên ngành** (dùng BLDS thay vì Luật Thương mại / Luật Nhà ở).
- **Trích dẫn ảo** — bắt buộc kiểm tra trích dẫn trước khi xuất.
- Người dùng tin tuyệt đối vào kết quả với hợp đồng giá trị lớn → cần cảnh báo rõ.

## 7. Câu hỏi còn mở

- Đây là bài tập tuần 5 (có deadline) hay sản phẩm phát triển lâu dài?
- Bản đầu nhắm loại hợp đồng nào? Đề xuất: thuê trọ + lao động/thử việc.
- Định dạng upload cần hỗ trợ: PDF text, DOCX, hay cả ảnh chụp (cần OCR)?
- Kết quả hiển thị ở đâu: giao diện hiện có trong `app/` hay giao diện mới?
- Nguồn lấy văn bản luật mới (thuvienphapluat, vbpl.vn, ...) và chu kỳ kiểm tra?
