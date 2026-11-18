# Trang demo hợp đồng riêng (`/contracts`) — thiết kế ngắn

Ngày: 2026-11-17 · Cỡ: thay đổi nhỏ–vừa (một trang UI mới + một endpoint)

## Ý định và lý do
Phần hợp đồng hiện là plugin trong khung chat (`ui/contracts.js`, dùng chung ô chat/thanh chế độ/danh sách phiên với hỏi đáp luật).
Khi demo, người xem khó theo dõi. Cần một trang riêng, tách hẳn khỏi hỏi đáp luật, đi **từng bước**: Nạp → Hỏi dữ kiện → Soát.

## Mục tiêu / không phải mục tiêu
- Mục tiêu: trang `/contracts` có stepper 3 bước, mỗi bước xong mới mở bước sau; nhìn một lần là hiểu luồng.
- Mục tiêu: bước ③ có hai nút — **Kiểm tra concept** (đứng đầu, endpoint mới) và **Soát luật** (soát hiện có).
- Không làm: sửa/gỡ plugin hợp đồng trong chat (`contracts.js`, `index.html` giữ nguyên). Gỡ là bước sau, nếu demo ổn.
- Không làm: hỏi đáp có đính kèm hợp đồng, tóm tắt, redline, đối chiếu thay đổi luật trên trang mới (v1).
- Chống mục tiêu: làm hỏng chat hiện tại; thêm heuristic/regex mới (xem ghi chú bên dưới).

## Các hướng đã cân nhắc
- **A. Trang mới viết riêng, plugin chat để nguyên — ĐÃ CHỌN.** Rủi ro thấp, dễ làm đẹp theo stepper; chấp nhận một phần render nằm ở hai nơi.
- B. Rút module render dùng chung: phải sửa plugin đang chạy, dễ hỏng chat, không đáng cho demo.
- C. Gỡ hẳn khỏi chat: mất hỏi đáp kèm hợp đồng trong chat; để sau A.

## Thiết kế
- Route `GET /contracts` trong `ui/server.py` (theo mẫu `/review`), file `ui/contracts.html` + `ui/contract_page.js`, style theo `review.html` (Tailwind CDN, Inter, nút "Quay lại chat").
- Tái dùng API sẵn có `/api/contracts/*`: tạo (`POST`), `party`, `sign-date`, `facts`, `run` (`review`), tải báo cáo.
- Bước ① Nạp: kéo thả file → thẻ hợp đồng (tên file, số điều khoản, trạng thái đồ thị); có danh sách hợp đồng đã lưu để mở lại.
- Bước ② Dữ kiện: bên ký, ngày ký, các dữ kiện mà hợp đồng/danh mục khái niệm cần hỏi (`USER_FACTS`, `CONTRACT_FACTS` trong `rag.bridge.catalog`), cho phép xác nhận/sửa/"không biết" như `verify.apply_answers`.
- Bước ③ Soát: `Kiểm tra concept` → báo cáo theo khái niệm (render từ `report_json`, tải `report.md`/`report.json`); `Soát luật` → báo cáo điều khoản như hiện có.
- Endpoint mới `POST /api/contracts/{cid}/concept-check` (body: `user_facts`): gọi `check_contract` như `scripts/check_contract_concepts.py`, trả `report_json` + markdown, rồi dựng lại đồ thị như script. Phần dựng LLM/tag/đồ thị luật trong script đưa về chỗ dùng chung để script và endpoint không lệch nhau.

## Việc để người xây quyết
- Bố cục chi tiết, màu, cách hiển thị báo cáo concept; cách chia hàm dùng chung với script.
- Concept-check chạy lâu: cần chỉ báo tiến trình/khóa nút; cách làm tùy người xây (không bắt buộc stream).
- Test: endpoint concept-check có test; trang chỉ cần kiểm tay khi chạy app.

## Ghi chú theo quy ước dự án
Không thêm mẫu/heuristic mới; không thêm khái niệm mới. Trang chỉ trình bày kết quả của pipeline sẵn có.
