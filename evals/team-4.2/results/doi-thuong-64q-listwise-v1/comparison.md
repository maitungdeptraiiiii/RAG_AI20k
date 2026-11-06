# Gated listwise v1 — benchmark chính 64 câu

Chỉ chạy một cấu hình mới trên pool/điểm Jev v2 đã lưu. Không chạy lại baseline hoặc retrieval.
Gate và prompt cố định ở preflight; không điều chỉnh theo gold sau khi xem kết quả.

| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |
|---|---:|---:|---:|---:|---:|
| saved-v2 | 0.895833 | 0.984375 | 0.842187 | 0.947917 | 16/27 |
| coverage-v1 | 0.901042 | 0.984375 | 0.846875 | 0.947917 | 16/27 |
| listwise-v1 | 0.932292 | 0.984375 | 0.872917 | 0.947917 | 20/27 |

API/usage: {'gated_questions': 18, 'api_requests': 18, 'fallbacks': 0, 'usage_reported_requests': 18, 'reported_prompt_tokens': 70106, 'reported_completion_tokens': 8743}
Context simulation: {'before': {'empty': 0, 'full_gold': 54, 'mean_blocks': 5.390625, 'mean_whitespace_units': 1307.1875}, 'after': {'empty': 0, 'full_gold': 55, 'mean_blocks': 5.359375, 'mean_whitespace_units': 1311.375}}
Giữ xác suất Jev gốc sau selection. Chỉ xếp lại ứng viên, không thêm Điều ngoài pool/shortlist.
Model chỉ thấy đoạn đại diện, không bảo đảm toàn bộ nội dung Điều; excerpt và gate có giới hạn.
Đây là đánh giá retrieval và mô phỏng context, chưa đánh giá câu trả lời hoặc tập độc lập.
Thời gian và số request có ảnh hưởng cache; số token lấy từ usage provider nếu có.
