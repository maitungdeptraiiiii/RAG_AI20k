# Phân tích và hướng tiếp theo

Kết quả và kiểm chứng chuẩn nằm trong comparison.md và verification.json.

Prompt v2 mở rộng phân tách từ 14 lên 50 câu. Nó cứu được d09 bằng cách đưa thêm bằng chứng về dấu hiệu chiếm đoạt tài sản vào pool, nhưng không tăng số câu multi tìm đủ gold. Các ứng viên mới cũng có thể chiếm thứ hạng cao: d22 và d31 giữ đủ gold trong top 5 nhưng MRR giảm. Giữ nguyên 20 Điều gốc bảo vệ độ phủ của pool gốc, không bảo đảm giữ thứ hạng sau rerank.

Ưu tiên thử rewrite có chọn lọc cho câu nói đời thường/mơ hồ: chuẩn hóa thuật ngữ, giữ mọi điều kiện, không tự thêm hậu quả hay kết luận pháp lý. Có thể gộp quyết định rewrite vào planner hiện có để không thêm một lượt gọi LLM riêng. Mỗi câu tối đa một rewrite; giữ câu gốc làm neo, câu đơn ý không cần phân tách thành hai câu gần nghĩa. Đây là đề xuất, chưa triển khai hoặc benchmark trong lần này.

Rewrite xử lý cách diễn đạt; decomposition xử lý nhiều nhu cầu bằng chứng. Với các Điều đã có trong pool nhưng chưa lên top 5, thêm rewrite không trực tiếp giải quyết lỗi xếp hạng. Với các Điều còn ngoài pool, kiểm tra lại câu truy vấn và độ sâu tìm kiếm trước khi tăng thêm nhánh.

Không có bảo đảm rewrite sẽ cải thiện benchmark. Cần thử trên những nhóm lỗi đã xác định và đối chiếu kết quả đã lưu, sau đó đánh giá thêm trên tập độc lập. Không chạy thêm cấu hình hay baseline trong lượt này.
