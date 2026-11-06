# Kết quả: BM25 dùng rewrite, Jev dùng câu gốc

Đã chạy một cấu hình mới trên 64 câu. Pool và thứ tự 1.821 ứng viên giữ chính xác
như lượt BM25=0.3 trước đó; chỉ đổi câu hỏi đưa vào Jev. Không chạy lại baseline,
retrieval, rewrite, HyDE hoặc embedding. Có 1.575 điểm đã cache và 246 cặp thiếu cache
ở preflight. Số cặp thiếu cache không tính retry SDK hoặc hóa đơn API.

## Kết luận

Cấu hình mới chưa tốt hơn v2 đã lưu: Recall@5 0.888021 so với 0.895833;
Hit@5 0.968750 so với 0.984375; MRR@5 0.831250 so với 0.842188.
Số câu multi tìm đủ gold giữ 16/27.

So với cùng pool nhưng Jev nhận rewrite, dùng câu gốc tăng Recall@5 từ 0.885417
lên 0.888021 và Hit@5 từ 0.953125 lên 0.968750, nhưng giảm MRR từ 0.850260
xuống 0.831250. Không có cải thiện đồng thời giữa độ phủ và thứ hạng.

## Câu tăng và giảm

So với cùng pool BM25=0.3, Jev nhận rewrite:

- d12: Recall@5 0.5 → 1.0.
- d17: Recall@5 0 → 0.5.
- d04: Recall@5 2/3 → 1/3.
- d52: Recall@5 1 → 0.5.
- 60 câu còn lại giữ Recall@5. MRR tăng ở 6 câu, giảm ở 7 câu, giữ ở 51 câu.

So với v2 đã lưu, Recall@5 không tăng ở câu nào; giảm duy nhất d10, từ 0.5 xuống 0.
MRR tăng ở 3 câu, giảm ở 1 câu, giữ ở 60 câu; mức giảm lớn của một câu vẫn có thể
làm trung bình thấp hơn dù số câu tăng nhiều hơn số câu giảm.

## Điểm yếu còn lại nằm ở pool

Ở d10 (mẹ mất, sổ đỏ còn đứng tên mẹ, anh em tranh chấp), Điều 651 BLDS đã bị loại
khỏi pool BM25=0.3. Đổi câu chấm Jev không thể phục hồi ứng viên không được đưa vào.
Điều 650 còn trong pool nhưng xếp hạng 6 với câu gốc, nên top 5 không có gold.
Ở v2, Recall@5 của d10 là 0.5.

Candidate recall của hai lượt cùng pool đều là 0.9453125; thấp hơn 0.953125 của v2.
Việc chỉ thay input reranker không khắc phục được mất độ phủ ở retrieval.

V2 vẫn phù hợp hơn nếu ưu tiên các metric tổng thể trong lần đối chiếu này. Nếu thử
tiếp, hướng có căn cứ là bảo vệ 20 Điều Dense gốc và chỉ cho BM25 bổ sung Điều mới,
thay vì để fusion thay thế ứng viên gốc. Hướng đó chưa được triển khai hoặc benchmark
trong lượt này; không có bảo đảm sẽ cải thiện.

## Kiểm chứng và cấu hình

64/64 câu được replay offline từ cache Jev full-input-v2, xác nhận thứ hạng, điểm,
metric và danh sách/thứ tự ứng viên trùng nguồn. Không có lỗi API hoặc fallback Jev.
179 tests pass. Đây là benchmark retrieval trên bộ 64 câu đã dùng để phát triển,
chưa đánh giá câu trả lời cuối hoặc tập độc lập. Thời gian chịu ảnh hưởng cache.

Đã thêm tùy chọn runtime:

```dotenv
QUERY_REWRITE_ENABLED=true
REWRITE_FOR_RERANK=false
BM25_RRF_WEIGHT=0.3
```

Với mode hybrid: BM25 của nhánh gốc dùng rewrite, các câu con giữ nguyên;
Dense/HyDE và Jev dùng câu gốc ở nhánh tương ứng. Mode Dense không gọi rewriter
khi REWRITE_FOR_RERANK=false. Chưa thay đổi .env của ứng dụng.
