# Trang hỏi đáp hợp đồng trên đồ thị `/contracts/ask` (thiết kế ngắn)

**Vì sao:** người dùng muốn hỏi đáp hợp đồng thành **trang riêng** để demo, giao diện giống trang hỏi đáp luật, có phần
chọn hợp đồng đã dựng đồ thị. Tiếp nối `2026-11-17-contract-page-graph-qa-design.md` (endpoint `/ask/stream` giữ nguyên).

**Mục tiêu**
- Trang `/contracts/ask` hai cột: trái = danh sách hợp đồng, phải = khung chat.
- Danh sách: id hợp đồng mà **trình duyệt này** đã lưu (`ctpage.saved` của trang Hợp đồng + `justice_saved_contracts_v1`
  của plugin chat), đọc qua `GET /api/contracts?ids=`. Hợp đồng chưa có khái niệm đã gán → mờ, không chọn được, kèm link
  "Kiểm tra concept ở trang Hợp đồng" (`/contracts?cid=…`).
- `?cid=` trên URL chọn sẵn hợp đồng (kể cả hợp đồng nạp tạm, không có trong danh sách lưu) và thêm vào danh sách.
- Khung chat cùng phong cách trang hỏi đáp luật (font, màu, bong bóng người hỏi / trả lời, ô nhập dưới cùng, Enter gửi):
  đầu khung tên file + ngày ký + số khái niệm; khi trống hiện 3–4 câu hỏi mẫu bấm được; mỗi câu trả lời dùng lại phần
  hiển thị đã có (tin cậy, đường đi, căn cứ luật, các bước agent + Cypher, cảnh báo); khi chạy hiện từng bước.
- Lịch sử hội thoại giữ theo từng hợp đồng trong phiên trang (đổi hợp đồng rồi quay lại vẫn còn), gửi 3 lượt cuối.
- Thẻ hợp đồng thêm `concepts`: số khái niệm khác nhau trong các thao tác còn hiệu lực của oplog.
- Trang Hợp đồng bước ③: **bỏ khung hỏi đáp**, thay bằng nút "Hỏi về hợp đồng này →" (hiện khi đã Kiểm tra concept);
  trang Hợp đồng nhận `?cid=` để mở thẳng hợp đồng đó ở bước ③. Header hai trang có link qua lại.

**Không làm:** phân quyền / liệt kê hợp đồng toàn server (để sau); sửa `ui/index.html`; lưu lịch sử hỏi đáp xuống server.

**Phương án**
- A (chọn): trang mới, cùng phong cách, tái dùng phần vẽ câu trả lời — trang riêng như yêu cầu, không đụng trang chat.
- B (bỏ): thêm chế độ vào `ui/index.html` — không thành trang riêng, file 2.400 dòng dễ vỡ phần hỏi đáp luật.

**Quyết định của người làm**
- Phần vẽ câu trả lời tách thành `ui/contract_qa.js` (dùng chung giữa hai trang chỉ còn trang hỏi; vẫn tách để trang
  mới gọn). Trang mới: `ui/contract_ask.html` + `ui/contract_ask.js`, route `GET /contracts/ask` và các file JS.
- Bỏ khung bước ③ là đề xuất của tôi trong lúc bàn (để chỉ còn một chỗ hỏi); người dùng chọn A, chưa nói riêng điểm này.
