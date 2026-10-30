# Evaluation suite

## Team workspace

- [Team 4.1](team-4.1/README.md)
- [Team 4.2](team-4.2/README.md)

Hướng dẫn dưới đây áp dụng riêng cho mỗi team; đường dẫn dữ liệu và output nằm trong thư mục team tương ứng.


Áp dụng [quy chuẩn](../docs/EVALUATION.md). Gợi ý `datasets/` cho câu hỏi/nhãn, `configs/` cho cấu hình, `runners/` cho mã đánh giá, `results/` cho kết quả nhỏ đã rà soát.

File mẫu dưới đây chỉ minh họa schema, không phải câu hỏi đã gán nhãn. Không dùng làm metric khóa học. Dữ liệu test độc lập có thể do mentor giữ ngoài repo; không coi nhãn public là test mù.

Mỗi run ghi commit, snapshot, model/version, config và số câu. Chỉ commit kết quả đã bỏ thông tin nhạy cảm; output lớn lưu ngoài repo và liên kết trong báo cáo.
