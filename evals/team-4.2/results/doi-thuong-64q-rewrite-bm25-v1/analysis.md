# Phân tích rewrite và BM25

Đã chạy đúng ba cấu hình mới trên 64 câu, không chạy lại baseline. Đối chiếu chính là
`doi-thuong-64q-scenario-decomp-v2` đã lưu. Bảng số liệu nằm trong `comparison.md`.

## Kết luận từ lần thử

Không cấu hình mới nào tăng đồng thời Recall@5, Hit@5 và MRR@5 so với v2.
Rewrite cho Jev đạt MRR cao nhất trong bốn cấu hình được đối chiếu (0.854167), nhưng
Recall@5 giảm 0.895833 xuống 0.885417 và số câu multi đủ gold giảm 16 xuống 15/27.
MRR chỉ đánh giá gold đầu tiên, nên nó có thể tăng trong khi độ đầy đủ bằng chứng giảm.

BM25 trọng số 1 đạt 17/27 câu multi đủ gold, nhưng làm mất toàn bộ gold ở một số câu
khác; Hit@5 và MRR đều thấp hơn v2. Giảm trọng số xuống 0.3 phục hồi một phần độ phủ
pool và MRR so với BM25=1, nhưng chưa vượt v2 về Recall@5 hoặc Hit@5.

Với ưu tiên tìm đủ bằng chứng, nên giữ v2 làm cấu hình tham chiếu hiện tại. Các công tắc
mới vẫn có thể dùng để thử nghiệm, chưa có bằng chứng để bật rewrite/BM25 đại trà.

## Rewrite giúp và gây mất thứ hạng như thế nào?

- d04 (công ty đột ngột cho nghỉ): trên cùng pool, Recall@5 tăng 1/3 lên 2/3.
  Với rewrite, Điều 36 ở hạng 1 và Điều 41 ở hạng 3; Điều 39 vẫn ngoài top 5.
- d12 (con 13 tuổi trộm xe): rewrite hỏi hành vi bị xử lý thế nào. Điều 12 vẫn hạng 1,
  nhưng Điều 586 về trách nhiệm bồi thường ở hạng 7 trong lượt chỉ rewrite, giảm Recall
  từ 1 xuống 1/2. Cả hai Điều vẫn có trong pool: đây là lỗi thứ hạng, không phải thiếu retrieval.
- d17 (say rượu làm vỡ đồ, bị đòi đền): rewrite tập trung vào trách nhiệm bồi thường.
  Trong lượt chỉ rewrite, Điều 589 và Điều 178 vẫn có trong pool nhưng xuống hạng 7 và 9.
  Recall@5 từ 1/2 xuống 0. Cách viết lại đã thay đổi trọng tâm; không thể coi mọi rewrite
  trôi chảy là giữ nguyên hiệu quả chấm bằng chứng.
- d40 (điện thoại hỏng sau 3 hôm): Điều 446 ở hạng 6 sau rewrite; thêm BM25 đưa Điều này
  vào hạng 5 ở cả hai trọng số. BM25 có ích cho ca này, nhưng không bảo đảm cải thiện tổng thể.

## BM25 có thể làm mất gold trước Jev

Khi bật hybrid, pool 20 Điều của câu gốc được chọn từ RRF Dense+BM25, sau đó bổ sung
tối đa 10 Điều mới từ câu con. Đây không phải cách cố định 20 Điều Dense rồi chỉ thêm
BM25 vào phần dư; trọng số BM25 có thể thay đổi các Điều đi vào pool ngay từ đầu.

- d02: lượt chỉ rewrite còn Điều 29 và 51 trong pool. BM25=1 loại cả hai khỏi pool;
  Jev không thể kéo lên những Điều không còn được đưa vào. BM25=0.3 phục hồi cả hai,
  ở hạng 2 và 5.
- d10: Điều 651 có trong pool chỉ rewrite, hạng 3. Cả hai cấu hình BM25 đều làm Điều 651
  rời pool. Với trọng số 0.3, Điều 650 còn trong pool nhưng ở hạng 8, nên Recall@5 bằng 0.
- Candidate recall toàn pool: v2 và rewrite-only cùng 0.953125; BM25=1 giảm xuống
  0.919271; BM25=0.3 phục hồi lên 0.945312. Trọng số thấp hạn chế thiệt hại, chưa loại bỏ nó.

Không chạy cấu hình BM25 với câu gốc để rerank trong lần này. Vì vậy chưa thể kết luận
BM25 luôn kém, hoặc đo riêng lợi ích của rewrite đối với BM25 so với BM25 dùng câu gốc.
Hai lượt BM25 ở đây đều dùng cùng câu rewrite cho Jev và BM25 nhánh gốc; câu con giữ nguyên.

## Kiểm chứng và chi phí

- 192/192 kết quả đã kiểm tra lại offline: đúng thứ hạng từ cache Jev full-input-v2,
  đúng metric, cùng kế hoạch decompose và đúng pool RRF theo từng trọng số.
- Lượt chỉ rewrite giữ chính xác danh sách và thứ tự ứng viên của v2.
- HyDE, embedding, kế hoạch decompose và rewrite trong các lượt benchmark chỉ đọc cache;
  thiếu cache thì dừng. Không chạy lại baseline, không sinh câu trả lời cuối.
- 64 yêu cầu rewrite dùng chung cho ba lượt. Hai bản bị kiểm tra từ chối (d19, d32)
  dùng lại câu gốc, được ghi trong `rewrite_review.json` và cột `rewrite_warning`.
- Tổng cặp Jev thiếu cache: 1714 + 751 + 17 = 2482; không phải hóa đơn hoặc số request
  chính xác nếu SDK có retry. Thời gian các lượt chịu ảnh hưởng cache nên không so sánh tốc độ.
- Lượt trọng số 0.3 gặp lỗi ghi file sau CSV câu 58/trace câu 57. Đã tiếp tục từ checkpoint,
  giữ các điểm đã trả phí; thống kê cache miss của dòng 58 được bảo toàn.
- Đây là đánh giá retrieval trên bộ 64 câu đã dùng để phát triển, chưa đánh giá tập độc lập
  hoặc chất lượng câu trả lời. Các giá trị là kết quả lần thử này, không bảo đảm tổng quát hóa.
