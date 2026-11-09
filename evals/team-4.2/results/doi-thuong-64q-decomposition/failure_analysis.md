# Vì sao decomposition chưa cải thiện thứ hạng

Phân tích offline từ CSV, trace, chunk và cache Jev hiện có; không gọi API.

## Điều cần phân biệt

- 14 câu được phân rã không đồng nghĩa 14 câu bị giảm. Recall@5: 2 câu tăng, 2 câu giảm, 10 câu giữ nguyên.
- Trên cả 64 câu, Recall@5 tăng 0.002604; Hit@5 giảm 0.015625; MRR@5 giảm 0.024740.
- 50 câu không phân rã có cùng Recall@5 và MRR@5 với baseline trong lần đo này.
- Đây là chất lượng retrieval theo gold, không phải phép đo độ đúng câu trả lời cuối.

## Toàn bộ 14 câu đã phân rã

| ID | Số câu con | Recall@5 cũ → mới | MRR@5 cũ → mới | Chunk khớp gold trong pool cũ → mới |
|---|---:|---:|---:|---:|
| d02 | 2 | 0.333 → 0.000 | 1.000 → 0.000 | 2 → 1 |
| d03 | 2 | 0.500 → 1.000 | 1.000 → 1.000 | 3 → 4 |
| d05 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 1 → 2 |
| d10 | 2 | 1.000 → 0.500 | 1.000 → 0.250 | 2 → 1 |
| d11 | 3 | 1.000 → 1.000 | 1.000 → 1.000 | 1 → 1 |
| d22 | 3 | 0.500 → 0.500 | 0.333 → 0.500 | 3 → 4 |
| d28 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 3 → 3 |
| d38 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 1 → 1 |
| d39 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 2 → 2 |
| d43 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 1 → 1 |
| d44 | 2 | 0.500 → 1.000 | 1.000 → 1.000 | 1 → 2 |
| d48 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 1 → 1 |
| d49 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 2 → 2 |
| d55 | 2 | 1.000 → 1.000 | 1.000 → 1.000 | 1 → 1 |

## Nguyên nhân đã chứng minh: cắt pool câu gốc trước rerank

Baseline giữ 20 Điều để rerank. Khi phân rã, nhánh câu gốc cũng bị cắt còn 10 Điều. INCLUDE_ORIGINAL=true chỉ bảo đảm tìm bằng câu gốc, chưa bảo đảm giữ đầy đủ pool baseline.

| Câu | Ứng viên gold bị mất | Vị trí Điều trong pool câu gốc trước rerank | Điểm Jev đã cache | Hậu quả |
|---|---|---:|---:|---|
| d02 | BLHS Điều 29 | 14 | 0.32 | Baseline xếp gold ở hạng 1; cấu hình mới không có gold trong top 5 |
| d10 | BLDS Điều 651 | 18 | 0.58 | Baseline gold đầu ở hạng 1; cấu hình mới chỉ còn gold khác ở hạng 4 |

Hai ứng viên trên có trong trace baseline và không có trong pool mới; chúng nằm ngoài 10 Điều đầu nên nhánh câu gốc bị cắt không giữ được, và các nhánh câu con không đưa chúng trở lại pool cuối. Điểm Jev được đọc từ cache theo cùng câu hỏi gốc và text chunk. Đây là bằng chứng trực tiếp; chưa cần thay prompt để giải thích phần mất ứng viên này.

## Vì sao MRR và Hit giảm dù Recall trung bình tăng

- d02: MRR 1 → 0, đồng thời mất một câu có Hit@5=1.
- d10: MRR 1 → 0.25 vì gold đầu tiên chuyển từ hạng 1 xuống hạng 4.
- d22: MRR 1/3 → 1/2, mức tăng nhỏ hơn hai mức giảm trên.
- 61 câu khác giữ nguyên MRR; tổng chênh lệch = (-1 - 0.75 + 1/6) / 64 = -0.0247396.
- d03 và d44 tăng Recall mỗi câu 0.5 nhưng MRR vốn đã là 1, nên không tăng thêm MRR.
- Tổng chênh lệch Recall = (0.5 + 0.5 - 1/3 - 0.5) / 64 = +0.00260417.

## Các yếu tố thiết kế cần kiểm chứng thêm

1. Câu con mở rộng sang ý phụ: d10 thêm giải quyết tranh chấp, từ đó top 5 có Điều 660, Điều 623 và Điều 26 BLTTDS. Đây là các đoạn liên quan chủ đề nhưng không nằm trong gold (Điều 650, 651); không thể gọi chúng là sai pháp lý chỉ vì không khớp gold.
2. HyDE sinh thêm diễn giải cho từng câu con. Cache d10 có thêm công chứng, sang tên và khởi kiện. Các chi tiết này có thể làm retrieval trải rộng sang thủ tục; đây là quan sát về nội dung, chưa phải bằng chứng nhân quả độc lập với việc cắt pool.
3. RRF cộng phiếu từ các truy vấn có tương quan. Một chủ đề phụ được nhiều câu nhắc tới có thể nổi lên; phép gộp không bảo đảm giữ đủ bằng chứng cho mỗi ý. Chưa có ablation riêng để định lượng yếu tố này.
4. Chất lượng tự đủ nghĩa của câu con chưa tuyệt đối: d22 có câu dùng "tình huống trên", và một câu khác không nhắc lại đầy đủ bối cảnh phòng vệ. Đây là lỗi so với yêu cầu prompt; chưa chứng minh nó gây giảm metric vì d22 thực tế tăng MRR.
5. 10/14 câu không tăng Recall: nhiều câu baseline đã đạt 1, nên không còn dư địa tăng Recall@5. Tách thêm vẫn tăng số lượt LLM/embedding.

## Thứ tự cải tiến đề xuất, chưa chạy thêm

1. Giữ nguyên toàn bộ 20 Điều từ câu gốc; chỉ dùng ngân sách bổ sung cho các ứng viên mới từ câu con. Nếu pool tổng 30 thì dành tối đa 10 Điều mới. Dedupe theo cùng khóa Điều và giữ các chunk cần thiết.
2. Siết prompt: mỗi câu con tự đủ nghĩa, giữ các dữ kiện liên quan; hạn chế tự mở rộng sang thủ tục/quyền-nghĩa vụ nếu chưa cần cho ý định câu hỏi.
3. Xem xét rerank theo từng câu con rồi chọn context có độ phủ các ý; cần ablation để biết có đáng tăng API hay không.
4. Lần benchmark sau chỉ chạy cấu hình mới và đối chiếu CSV baseline đã lưu. Không gọi lại baseline. Cùng ID chưa đủ bảo đảm cùng corpus/model, nên cần giữ metadata của mỗi lần đo.

## Giới hạn

Không thay prompt hoặc thuật toán decomposition trong lần phân tích này. Không rerun baseline hay cấu hình mới. Phân tích thứ hạng/điểm chỉ sử dụng artifact và cache sẵn có; các yếu tố chưa được ablation đã được ghi rõ là giả thuyết.
