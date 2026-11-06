# Jev hỗ trợ từng phần — benchmark 64 câu

Checkpoint trước thử nghiệm: `27b361c`. Chỉ chạy cấu hình mới; baseline và phiên bản trước lấy từ CSV đã lưu.

| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 |
|---|---:|---:|---:|---:|
| Baseline lịch sử (đã lưu) | 0.848958 | 0.937500 | 0.826042 | 0.937500 |
| Baseline có trace/cache (đã lưu) | 0.835938 | 0.937500 | 0.800000 | 0.914062 |
| Checkpoint 20+10, prompt Jev cũ | 0.851562 | 0.937500 | 0.802604 | 0.937500 |
| 20+10, prompt Jev hỗ trợ từng phần | 0.880208 | 0.968750 | 0.848698 | 0.937500 |

## So với checkpoint

| Chỉ số | Tăng | Giảm | Giữ nguyên | Delta trung bình |
|---|---:|---:|---:|---:|
| recall@5 | 4 | 1 | 59 | +0.028646 |
| hit@5 | 2 | 0 | 62 | +0.031250 |
| mrr@5 | 10 | 4 | 50 | +0.046094 |

## Các câu thay đổi Recall@5

| ID | Prompt cũ | Prompt mới |
|---|---:|---:|
| d02 | 0.333 | 0.667 |
| d10 | 1.000 | 0.500 |
| d17 | 0.000 | 0.500 |
| d18 | 0.000 | 1.000 |
| d22 | 0.500 | 1.000 |

## Nhóm multi

| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Đủ toàn bộ gold trong top 5 |
|---|---:|---:|---:|---:|
| Prompt cũ | 0.759259 | 0.962963 | 0.698765 | 16/27 |
| Prompt mới | 0.790123 | 1.000000 | 0.808025 | 16/27 |

## Kiểm chứng

- 166 test đạt. 64/64 câu có cùng queries và cùng pool ứng viên/thứ tự so với checkpoint; không thay retrieval, HyDE hay decomposition.
- 1629 cặp query/chunk có điểm cache theo schema mới, gồm đầy đủ instructions và state; không dùng nhầm cache legacy.
- Chỉ một cấu hình được chạy; 64/64 câu rerank thành công, không lỗi/fallback.
- Prompt mới và SHA-256 được lưu trong config.json. Cache key mới bao gồm heading trong state; thay heading/instructions sẽ chấm lại. Legacy key chỉ còn phục vụ audit offline.
- Phép đo này gồm thay đổi prompt và làm mới điểm Jev; không tách riêng tác động của biến động giữa các lần model trả điểm.

## Kết luận và giới hạn

Prompt mới cải thiện cả Recall@5 và MRR@5 trên bộ 64 câu so với checkpoint; các số cũng cao hơn baseline lịch sử đã lưu. Tuy nhiên đây vẫn là bộ đã dùng để phát triển, chưa có đánh giá độc lập hoặc chấm chất lượng câu trả lời cuối.
Không đổi CONTEXT_MIN_P trong thử nghiệm. Ý nghĩa/phân bố điểm Jev đã đổi nên kết quả retrieval chưa chứng minh ngưỡng context/từ chối hiện tại đã phù hợp.
Checkpoint 27b361c giữ phiên bản trước thử nghiệm; thay đổi thử nghiệm đang để trong working tree để xem xét.
