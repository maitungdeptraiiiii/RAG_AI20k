# Coverage selection v1 — benchmark offline 64 câu

Chỉ thử một policy cố định trên pool/điểm Jev của v2. Không gọi API; baseline chỉ đọc kết quả đã lưu.

| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |
|---|---:|---:|---:|---:|---:|
| saved-v2 | 0.895833 | 0.984375 | 0.842187 | 0.947917 | 16/27 |
| v2+coverage-v1 | 0.901042 | 0.984375 | 0.846875 | 0.947917 | 16/27 |

Policy: {'anchor_k': 2, 'min_p': 0.5, 'weight': 0.25, 'branch_k': 5}. Điểm kết hợp chỉ dùng để chọn, không ghi đè xác suất Jev.
Branch rank là tín hiệu thay thế cho độ phủ, chưa chứng minh bằng chứng thực sự hỗ trợ ý đó.
Context được mô phỏng trước/sau bằng cùng cấu hình hiện tại; chưa sinh hoặc chấm câu trả lời.
Tập 64 câu đã dùng để phát triển; chưa đánh giá tập độc lập. Không sửa tham số sau khi xem kết quả.
