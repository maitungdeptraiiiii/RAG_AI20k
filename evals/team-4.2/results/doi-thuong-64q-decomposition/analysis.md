# Phân tích benchmark query decomposition

Đã kiểm tra đủ 128 dòng: 64 câu × 2 cấu hình; không có lỗi, fallback hoặc thiếu rerank.

## Cấu hình và phạm vi

- Cùng index Jina 1024 chiều hiện có, 3422 chunk của 6 bộ luật; HyDE + Jev, không BM25, không contextual header.
- Câu gốc + tối đa 3 câu con; lấy 10 Điều mỗi câu, RRF k=60, pool tối đa 30 Điều khi có phân rã. Baseline dùng pool 20 Điều.
- Chỉ đo retrieval, chưa đo độ đúng câu trả lời và citation. Giữ cách chấm chunk đại diện của benchmark chính.
- Decomposition chỉ nhận câu hỏi; không nhận gold/reference. Prompt và dữ liệu có SHA-256 trong config.json.
- Thời gian chịu ảnh hưởng cache và thứ tự baseline trước decomposition; không dùng để kết luận độ trễ production.

## So sánh cặp vừa chạy

| Chỉ số | Baseline | Decomposition | Chênh lệch |
|---|---:|---:|---:|
| recall@5 | 0.835938 | 0.838542 | +0.002604 |
| hit@5 | 0.937500 | 0.921875 | -0.015625 |
| mrr@5 | 0.800000 | 0.775260 | -0.024740 |
| recall@20 | 0.914062 | 0.924479 | +0.010417 |
| candidate_recall | 0.914062 | 0.924479 | +0.010417 |

- Thực sự phân rã 14/64 câu; các câu còn lại giữ nguyên truy vấn.
- Recall@5 tăng ở 2 câu: d03, d44.
- Recall@5 giảm ở 2 câu: d02, d10.
- Recall@5 giữ nguyên ở 60 câu.

## Diễn giải

Recall@5 chỉ tăng khoảng 0.26 điểm phần trăm, trong khi MRR@5 và Hit@5 giảm. Chưa có cơ sở để thay baseline hoặc bật decomposition mặc định. DECOMP_ENABLED vẫn mặc định false; có thể bật để thử nghiệm.
Việc giảm pool mỗi nhánh xuống 10 Điều có thể loại ứng viên hữu ích từ nhánh câu gốc. Đây là giả thuyết từ thiết kế, chưa được kiểm chứng bằng ablation. Lần thử tiếp theo nên giữ đầy đủ pool câu gốc và so sánh cùng ngân sách rerank.

## Khác biệt với kết quả lịch sử

Kết quả lưu doi-thuong-64q-hyde-nobm25 có Recall@5=0.849 và MRR@5=0.826; lần chạy lại này là Recall@5=0.836 và MRR@5=0.800. Chưa xác định nguyên nhân khác biệt giữa các lần chạy. Vì vậy so sánh decomposition với baseline chạy lại trong cùng thí nghiệm, không lấy số lịch sử làm đối chứng trực tiếp.

## Các câu có thay đổi Recall@5

| ID | Baseline | Decomposition | Các truy vấn đã dùng |
|---|---:|---:|---|
| d03 | 0.500 | 1.000 | thằng em tôi nhậu xong đánh nhau ngoài quán, bên kia phải khâu mấy mũi, giờ công an gọi lên làm việc / Em trai tôi uống rượu rồi đánh nhau ngoài quán, người bên kia phải khâu vài mũi thì em tôi có thể phải chịu trách nhiệm pháp lý gì? / Khi công an gọi em trai tôi lên làm việc về vụ đánh nhau ngoài quán khiến người bên kia phải khâu vài mũi, em tôi cần lưu ý quyền và nghĩa vụ gì? |
| d44 | 0.500 | 1.000 | chồng mất không để lại di chúc, nhà hai vợ chồng mua chung thì chia thế nào / Khi chồng mất không để lại di chúc, căn nhà hai vợ chồng mua chung được xác định phần tài sản thuộc người chồng như thế nào? / Phần căn nhà thuộc người chồng được chia thừa kế cho những ai khi chồng mất không để lại di chúc? |
| d02 | 0.333 | 0.000 | tôi lỡ tay đẩy người ta xuống vực, có đến nhà bố mẹ họ xin lỗi rồi có sao không / Người lỡ tay đẩy người khác xuống vực có thể phải chịu trách nhiệm pháp lý thế nào khi chưa rõ hậu quả đối với người bị đẩy? / Việc người lỡ tay đẩy người khác xuống vực đến nhà bố mẹ người đó xin lỗi có ảnh hưởng thế nào đến trách nhiệm pháp lý? |
| d10 | 1.000 | 0.500 | mẹ mất rồi mà sổ đỏ vẫn đứng tên mẹ, mấy anh em đang cãi nhau / Khi mẹ mất, sổ đỏ vẫn đứng tên mẹ thì các anh chị em được thừa kế và phân chia quyền sử dụng đất như thế nào? / Nếu các anh chị em không thống nhất về quyền thừa kế hoặc việc chia đất có sổ đỏ đứng tên người mẹ đã mất thì giải quyết tranh chấp thế nào? |
