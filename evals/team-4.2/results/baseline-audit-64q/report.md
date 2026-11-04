# Kiểm tra baseline offline — 64 câu

Không gọi API, không chạy retriever hoặc benchmark. Chỉ đọc artifact và sắp xếp điểm Jev đã cache.

## Kết luận

Chưa chứng minh decomposition tốt hơn baseline lịch sử. Nó cải thiện nhẹ so với baseline có trace/cache tương thích, nhưng mức tăng còn nhỏ và mới được đo trên bộ 64 câu đã dùng để phát triển.

| Mốc | Recall@5 | Hit@5 | MRR@5 |
|---|---:|---:|---:|
| Baseline lịch sử | 0.848958 | 0.937500 | 0.826042 |
| Baseline có trace/cache tương thích | 0.835938 | 0.937500 | 0.800000 |
| Decomposition mới 20 + tối đa 10 | 0.851562 | 0.937500 | 0.802604 |

## Đã xác định được gì về baseline lệch

- Tính lại các top 5 đã lưu bằng gold/chunk hiện tại: 0 sai khác. Chênh lệch không phải do phép tính điểm cho các top 5 này.
- Top 5 Dense trước Jev khác ở 57/64 câu: thay đổi đã có trước rerank.
- Trong 53 câu lịch sử có đủ điểm hiện tại, 24 thứ tự top 5 không giảm dần theo điểm Jev hiện tại. Do đó điểm/hành vi rerank lịch sử không thể coi là giống hiện tại.
- Ví dụ d40: thứ tự lịch sử đặt chunk có điểm cache hiện tại 0.82 trước chunk 0.83; d60 là 0.97 trước 0.98. Với thuật toán hiện tại, hai thứ tự đó không được tái tạo chỉ bằng thay đổi tie-break.
- Chưa thể quy nguyên nhân cụ thể cho HyDE, embedding, model, prompt hoặc cấu hình: lần lịch sử thiếu trace và fingerprint đủ chi tiết. Không kết luận chắc chắn model ngẫu nhiên hay dữ liệu đã đổi.
- Sắp xếp lại điểm cache tái tạo chính xác top 5 baseline có trace 64/64 và cấu hình mới 64/64. Pool gốc và thứ tự được giữ ở 64/64 câu.

## Chênh lệch theo từng câu

| Đối chiếu | Chỉ số | Tăng | Giảm | Giữ nguyên | Delta trung bình | Khoảng bootstrap 95% |
|---|---|---:|---:|---:|---:|---|
| new_vs_historical | recall@5 | 2 | 2 | 60 | +0.002604 | [-0.026042, +0.031250] |
| new_vs_historical | hit@5 | 0 | 0 | 64 | +0.000000 | [+0.000000, +0.000000] |
| new_vs_historical | mrr@5 | 0 | 3 | 61 | -0.023438 | [-0.054688, +0.000000] |
| new_vs_controlled | recall@5 | 2 | 0 | 62 | +0.015625 | [+0.000000, +0.039062] |
| new_vs_controlled | hit@5 | 0 | 0 | 64 | +0.000000 | [+0.000000, +0.000000] |
| new_vs_controlled | mrr@5 | 1 | 0 | 63 | +0.002604 | [+0.000000, +0.007812] |

Bootstrap lấy mẫu lại theo cặp câu hỏi 10.000 lần, seed 20261105. Đây là mô tả độ bất định trên bộ đang có; không sửa được việc khác điều kiện giữa các lần chạy hoặc việc đã dùng bộ này để chỉnh hệ thống.

## Bốn câu làm baseline lịch sử lệch

| ID | Recall lịch sử → baseline có trace | MRR lịch sử → baseline có trace |
|---|---:|---:|
| d02 | 0.667 → 0.333 | 1.000 → 1.000 |
| d22 | 1.000 → 0.500 | 1.000 → 0.333 |
| d40 | 1.000 → 1.000 | 1.000 → 0.500 |
| d60 | 1.000 → 1.000 | 1.000 → 0.500 |

## Mốc cố định cho lần tiếp theo

Giữ baseline lịch sử làm mốc sản phẩm chính; baseline có trace/cache làm mốc phân tích tác động của decomposition. Hai mốc có tên riêng trong manifest.json, không chọn mốc thấp hơn để tuyên bố thắng.
Các CSV, trace, gold/chunk và điểm cache đã được chụp vào frozen/ kèm SHA-256. Lần sau chỉ chạy cấu hình mới, đọc baseline từ đây; không gọi lại API cho baseline.
Để kết luận vượt baseline tổng thể: đặt trước tiêu chí Recall và MRR, theo dõi câu giảm và chi phí; xác nhận trên bộ câu hỏi/gold độc lập chưa dùng để chỉnh prompt. Chưa có bộ độc lập được chấm trong lần kiểm tra này.
Không có câu trả lời được sinh/chấm trong các artifact đang dùng; chưa kết luận chất lượng trả lời hoặc citation.
