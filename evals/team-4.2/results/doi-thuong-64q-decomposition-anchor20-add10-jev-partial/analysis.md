# Phân tích prompt Jev hỗ trợ từng phần

Phân tích offline từ kết quả và cache đã lưu. Không gọi API hoặc chạy lại benchmark. Đối chứng chính trong phân tích thay đổi là checkpoint 27b361c (cùng pool và truy vấn).

## Mức cải thiện

| Nhóm | Recall@5 cũ → mới | Hit@5 cũ → mới | MRR@5 cũ → mới | Đủ gold top 5 cũ → mới |
|---|---:|---:|---:|---:|
| Tất cả | 0.852 → 0.880 | 0.938 → 0.969 | 0.803 → 0.849 | 50/64 → 51/64 |
| multi | 0.759 → 0.790 | 0.963 → 1.000 | 0.699 → 0.808 | 16/27 → 16/27 |
| paraphrase | 0.919 → 0.946 | 0.919 → 0.946 | 0.878 → 0.878 | 34/37 → 35/37 |

- Toàn bộ: Recall tăng 2.865 điểm phần trăm; MRR tăng 4.609 điểm phần trăm; Hit tăng 3.125 điểm phần trăm.
- 4 câu tăng Recall, 1 câu giảm, 59 câu giữ nguyên. MRR tăng ở 10 câu, giảm ở 4 câu, giữ nguyên ở 50 câu.
- Recall@20/pool không đổi: 0.9375. Pool không có thêm bằng chứng; thay đổi nằm ở thứ tự chọn.
- Multi: Hit đạt 27/27, nhưng chỉ 16/27 câu lấy đủ toàn bộ gold. 11 câu còn thiếu gold ở top 5.

## Các thay đổi Recall có bằng chứng từ rank/cache

| ID | Tình huống | Recall cũ → mới | Thay đổi cụ thể |
|---|---|---:|---|
| d02 | Đẩy người xuống vực, đã xin lỗi | 0.333 → 0.667 | Điều 51 BLHS từ hạng 6, điểm 0.16 lên hạng 3, điểm 0.49; Điều 29 từ hạng 1 xuống 2 nên MRR giảm 1 → 0.5 |
| d17 | Say rượu đập đồ quán | 0 → 0.5 | Điều 178 BLHS từ hạng 10, điểm 0.36 lên hạng 5, điểm 0.66; Điều 589 BLDS vẫn ở hạng 7 |
| d18 | Không thể đến tòa theo giấy gọi | 0 → 1 | Điều 227 BLTTDS từ hạng 8, điểm 0.72 lên hạng 4, điểm 0.85 |
| d22 | Đánh lại người cầm dao | 0.5 → 1 | Điều 134 BLHS từ hạng 6, điểm 0.17 lên hạng 3, điểm 0.60; Điều 22 lên hạng 1 |
| d10 | Tranh chấp đất sau khi mẹ mất | 1 → 0.5 | Điều 650 BLDS từ hạng 5 xuống 9 dù điểm tăng 0.29 → 0.58; các Điều 623, 660, 656, 616 được ưu tiên cao hơn |

Các Điều ngoài gold vẫn có thể liên quan tình huống; không gọi chúng là sai pháp lý chỉ vì không khớp gold. Điểm/rank trên chỉ mô tả hành vi retrieval.

## Vì sao có cải thiện và vì sao chưa giải quyết hết multi

Kết quả phù hợp với giả thuyết rằng tiêu chí hỗ trợ một phần giúp những bằng chứng chuyên biệt được ưu tiên hơn: Điều 51, 178, 134 và 227 vượt vào top 5. Tuy nhiên thử nghiệm cũng làm mới toàn bộ điểm Jev bằng cache schema mới; chưa tách riêng tác động của prompt và biến động giữa các lần chấm.
Prompt mới không chọn theo độ phủ của cả tập. Ở d10, nhiều đoạn liên quan đến thừa kế cùng được tăng điểm và đẩy Điều 650 khỏi top 5. Tăng điểm tuyệt đối không bảo đảm tăng thứ hạng tương đối.
MRR tăng mạnh ở multi chủ yếu có nghĩa bằng chứng gold đầu tiên được đưa lên cao hơn; không có nghĩa đã lấy đủ các Điều cần cho tất cả các ý. d22 trở thành câu đủ gold, nhưng d10 mất trạng thái đủ gold, nên số câu đủ vẫn 16/27.

## MRR giảm ở đâu

| ID | MRR cũ → mới |
|---|---:|
| d02 | 1.000 → 0.500 |
| d50 | 1.000 → 0.500 |
| d52 | 0.250 → 0.200 |
| d58 | 1.000 → 0.250 |

## Mô phỏng context theo cấu hình hiện tại, không sinh câu trả lời

Đọc cấu hình hiện tại: CONTEXT_MIN_P=0.5, max_blocks=8, max_words=2400. Đây là mô phỏng offline, không phải dữ liệu answer generation của benchmark.

| Chỉ số | Prompt cũ | Prompt mới |
|---|---:|---:|
| Context rỗng, sẽ từ chối trước LLM | 9/64 | 0/64 |
| Context chứa đủ gold | 41/64 | 54/64 |
| Số block trung bình | 2.953 | 5.219 |
| Số từ/âm tiết cách khoảng trắng trung bình | 750.2 | 1288.5 |

Prompt mới không thêm bước LLM hay tăng số cặp Jev theo cùng pool, nhưng context có thể dài hơn nên chi phí/độ trễ sinh câu trả lời có thể tăng. Không thể suy ra số tiền từ số từ trong mô phỏng.
Bộ 64 câu đều có gold trong phạm vi. Không có context rỗng không chứng minh khả năng từ chối ngoài phạm vi tốt hơn; cần kiểm tra riêng các câu ngoài tài liệu trước khi kết luận về guardrail.

## Đánh giá tổng thể

Đây là cải thiện retrieval đáng kể hơn hai lần chỉnh trước trên chính bộ 64 câu: cả Recall, Hit và MRR đều tăng so với checkpoint và cũng cao hơn số baseline lịch sử đã lưu. Chưa chứng minh chất lượng câu trả lời cuối hoặc hiệu quả trên câu hỏi độc lập.
Ưu tiên tiếp theo nếu tiếp tục: kiểm tra d10 và bốn câu giảm MRR; kiểm tra context/từ chối với prompt mới. Lần thử này cải thiện mà không tăng pool. Bốn câu multi vẫn thiếu gold trong pool cần giải pháp retrieval riêng; chỉnh prompt Jev không thể tạo thêm bằng chứng chưa có. Không chỉnh ngưỡng hoặc chạy thêm API trong lần phân tích này.
