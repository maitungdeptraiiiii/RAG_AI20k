# Phân tích cấu hình mới — 64 câu, pool gốc 20 + tối đa 10 Điều mới

Chỉ phân tích artifact đã lưu, không gọi API. Nhãn `multi` nghĩa là gold gồm nhiều vấn đề/Điều; không phải bộ đo chuyên biệt cho suy luận nhiều bước phụ thuộc nhau. Điểm dưới đây đo retrieval, chưa chấm câu trả lời cuối hoặc citation.

## Tổng quan

| Nhóm | Số câu | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Đủ toàn bộ gold trong top 5 |
|---|---:|---:|---:|---:|---:|---:|
| Tất cả | 64 | 0.852 | 0.938 | 0.803 | 0.938 | 50/64 |
| multi | 27 | 0.759 | 0.963 | 0.699 | 0.926 | 16/27 |
| paraphrase | 37 | 0.919 | 0.919 | 0.878 | 0.946 | 34/37 |

- Multi: đủ gold 16/27; thiếu một phần 10/27; không gold trong top 5 1/27.
- Pool có đủ gold ở 23/27 câu. 4 câu vẫn thiếu gold trong pool; 7 câu pool đủ nhưng top 5 chưa đủ.
- Chỉ 7/27 câu multi được decomposition tách; nhãn benchmark không được đưa vào bước phân rã.
- So với baseline có trace/cache tương thích: d03 và d44 tăng Recall@5 từ 0.5 lên 1; d22 tăng MRR từ 1/3 lên 1/2. Các câu multi khác không thay đổi hai chỉ số này. Không chạy lại baseline.

## Các câu multi chưa đủ gold

| ID | Câu hỏi | Câu con | Recall@5 | Gold còn thiếu ở top 5 | Chẩn đoán từ pool |
|---|---|---:|---:|---|---|
| d01 | hôm nay tôi lỡ tông phải một ông già lúc sang đường, không biết có bị sao không | 0 | 0.333 | dan_su: Điều 601; dan_su: Điều 590 | Pool vẫn thiếu gold |
| d02 | tôi lỡ tay đẩy người ta xuống vực, có đến nhà bố mẹ họ xin lỗi rồi có sao không | 2 | 0.333 | hinh_su: Điều 128; hinh_su: Điều 51 | Pool vẫn thiếu gold |
| d04 | công ty tự nhiên bảo mai khỏi đi làm nữa, thế có được không | 0 | 0.333 | lao_dong: Điều 39; lao_dong: Điều 41 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d13 | nhà bên cạnh đang xây, tường nhà tôi nứt hết cả rồi | 0 | 0.500 | dan_su: Điều 584 | Pool vẫn thiếu gold |
| d17 | tối qua say quá đập vỡ đồ của quán, sáng ra họ đòi đền | 0 | 0.000 | dan_su: Điều 589; hinh_su: Điều 178 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d22 | ông hàng xóm say rượu cầm dao sang chửi, tôi lấy gậy đánh lại gãy tay ông ấy, giờ ổng đòi kiện | 3 | 0.500 | hinh_su: Điều 134 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d26 | cháu tôi 17 tuổi đi trộm điện thoại của người ta bị bắt, liệu có phải đi tù không | 0 | 0.500 | hinh_su: Điều 173 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d36 | tòa vừa xử bố tôi 3 năm tù mà gia đình thấy nặng quá, giờ làm sao | 0 | 0.500 | to_tung_hinh_su: Điều 331 | Pool vẫn thiếu gold |
| d52 | em 15 tuổi muốn đi làm phụ quán cà phê dịp hè được không | 0 | 0.500 | lao_dong: Điều 143 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d59 | bản án phúc thẩm có hiệu lực rồi nhưng tôi vẫn thấy xử sai, còn cách nào không | 0 | 0.500 | to_tung_dan_su: Điều 326 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d62 | đi tàu ra đảo bị mất vali hành lý, hãng tàu có phải đền không | 0 | 0.500 | hang_hai: Điều 213 | Pool đủ gold; rerank/top 5 chưa giữ đủ |

Phân loại pool/rerank chỉ xác định nơi mất gold trong pipeline, không chứng minh nguyên nhân gốc. Chưa thể kết luận prompt hay Jev là nguyên nhân duy nhất.

## Toàn bộ 27 câu multi

| ID | Câu hỏi | Câu con | Recall@5 baseline đã lưu → mới | MRR@5 mới | Kết quả |
|---|---|---:|---:|---:|---|
| d01 | hôm nay tôi lỡ tông phải một ông già lúc sang đường, không biết có bị sao không | 0 | 0.333 → 0.333 | 0.500 | Pool vẫn thiếu gold |
| d02 | tôi lỡ tay đẩy người ta xuống vực, có đến nhà bố mẹ họ xin lỗi rồi có sao không | 2 | 0.333 → 0.333 | 1.000 | Pool vẫn thiếu gold |
| d03 | thằng em tôi nhậu xong đánh nhau ngoài quán, bên kia phải khâu mấy mũi, giờ công an gọi lên làm việc | 2 | 0.500 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d04 | công ty tự nhiên bảo mai khỏi đi làm nữa, thế có được không | 0 | 0.333 → 0.333 | 0.333 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d06 | đang bầu mà bị công ty cho nghỉ việc, chị có làm gì được không | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d07 | tháng nào cũng phải ở lại làm tới 9-10h tối mà chẳng thấy thêm đồng nào | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d08 | cho đứa bạn mượn 50 triệu giờ nó chặn hết liên lạc rồi | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d10 | mẹ mất rồi mà sổ đỏ vẫn đứng tên mẹ, mấy anh em đang cãi nhau | 2 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d12 | con tôi mới 13 tuổi, đi lấy trộm xe đạp bị người ta bắt được | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d13 | nhà bên cạnh đang xây, tường nhà tôi nứt hết cả rồi | 0 | 0.500 → 0.500 | 0.333 | Pool vẫn thiếu gold |
| d15 | bị đứa kia lên facebook bịa chuyện nói xấu, nhục không chịu được | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d16 | nhặt được cái ví ngoài đường, giữ luôn có sao không | 0 | 1.000 → 1.000 | 0.333 | Đủ gold trong top 5 |
| d17 | tối qua say quá đập vỡ đồ của quán, sáng ra họ đòi đền | 0 | 0.000 → 0.000 | 0.000 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d19 | vợ ôm con về ngoại cả năm nay rồi, giờ muốn làm đơn ly hôn thì nộp ở đâu | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d22 | ông hàng xóm say rượu cầm dao sang chửi, tôi lấy gậy đánh lại gãy tay ông ấy, giờ ổng đòi kiện | 3 | 0.500 → 0.500 | 0.500 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d26 | cháu tôi 17 tuổi đi trộm điện thoại của người ta bị bắt, liệu có phải đi tù không | 0 | 0.500 → 0.500 | 0.333 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d32 | cho vay lấy lãi 5 nghìn một triệu một ngày thì có bị sao không | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d36 | tòa vừa xử bố tôi 3 năm tù mà gia đình thấy nặng quá, giờ làm sao | 0 | 0.500 → 0.500 | 0.200 | Pool vẫn thiếu gold |
| d39 | ông nội trước khi mất có nói miệng là cho tôi mảnh đất, mấy chú có cãi được không | 2 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d40 | mua điện thoại về được 3 hôm thì hỏng, cửa hàng không chịu đổi cũng không sửa | 0 | 1.000 → 1.000 | 0.500 | Đủ gold trong top 5 |
| d44 | chồng mất không để lại di chúc, nhà hai vợ chồng mua chung thì chia thế nào | 2 | 0.500 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d49 | thử việc 3 tháng mà công ty chỉ trả có 70% lương | 2 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d50 | làm cho công ty 5 năm rồi giờ xin nghỉ, công ty có phải trả khoản gì không | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d52 | em 15 tuổi muốn đi làm phụ quán cà phê dịp hè được không | 0 | 0.500 → 0.500 | 0.250 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d53 | sếp hay sờ mó, nói chuyện bậy với em ở công ty, em muốn nghỉ luôn | 0 | 1.000 → 1.000 | 1.000 | Đủ gold trong top 5 |
| d59 | bản án phúc thẩm có hiệu lực rồi nhưng tôi vẫn thấy xử sai, còn cách nào không | 0 | 0.500 → 0.500 | 0.333 | Pool đủ gold; rerank/top 5 chưa giữ đủ |
| d62 | đi tàu ra đảo bị mất vali hành lý, hãng tàu có phải đền không | 0 | 0.500 → 0.500 | 0.250 | Pool đủ gold; rerank/top 5 chưa giữ đủ |

## Hướng xử lý tiếp, chưa chạy thêm

- Bốn câu pool thiếu gold (d01, d02, d13, d36): kiểm tra nhu cầu thông tin còn thiếu trong câu con/HyDE và nhánh retrieval; rerank lại cùng pool không thể bổ sung gold chưa có.
- Bảy câu pool đủ nhưng top 5 thiếu (d04, d17, d22, d26, d52, d59, d62): xem điểm Jev và khả năng giữ độ phủ các ý khi chọn top 5; không mặc định tăng pool sẽ giải quyết được.
- Không ép tách cả 27 câu chỉ để khớp nhãn multi: nhiều câu baseline đã đủ gold, và `multi` không đồng nghĩa câu có nhiều ý rõ ràng về mặt ngôn ngữ.
- Muốn nói xử lý được câu hỏi: cần đánh giá tiếp context thực sự vào LLM, câu trả lời và citation. Chưa có dữ liệu này trong benchmark retrieval.
