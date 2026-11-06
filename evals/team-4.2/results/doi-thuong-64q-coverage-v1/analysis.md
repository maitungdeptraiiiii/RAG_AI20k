# Phân tích coverage selection v1

Chỉ thử một policy cố định trên 64 câu: anchor=2, min_p=0.5, weight=0.25, branch_k=5.
Không quét tham số, không gọi API và không chạy lại baseline. Luồng HybridRetriever thực
được chạy bằng danh sách Dense, kế hoạch decompose và điểm Jev đã lưu, không mở vector index.

## Kết quả

| Chỉ số | v2 đã lưu | v2 + coverage v1 |
|---|---:|---:|
| Recall@5 | 0.895833 | 0.901042 |
| Hit@5 | 0.984375 | 0.984375 |
| MRR@5 | 0.842188 | 0.846875 |
| Recall@20 | 0.947917 | 0.947917 |
| Candidate recall | 0.953125 | 0.953125 |
| Multi đủ gold top 5 | 16/27 | 16/27 |
| Tất cả câu đủ gold top 5 | 52/64 | 52/64 |

Recall@5 tăng 0.52 điểm phần trăm, MRR tăng 0.47 điểm phần trăm. Đây là cải thiện nhỏ
trên bộ phát triển hiện tại, chưa đủ bằng chứng để kết luận tổng quát hóa tốt hơn.

## Câu thay đổi

- d04: Recall@5 từ 1/3 lên 2/3. Điều 41 được đưa từ hạng 6 vào top 5 nhờ tín hiệu câu con;
  câu vẫn thiếu Điều 39 nên chưa thành một câu đủ gold.
- d18: MRR từ 1/4 lên 1/3, Recall giữ 1.
- d52: MRR từ 1/5 lên 1/3, Recall giữ 1/2; chưa cứu Điều 143 đang ngoài top 5.
- d58: MRR từ 1/4 lên 1/3, Recall giữ 1.
- Không câu nào giảm Recall@5 hoặc MRR@5 trong lượt thử. Có 9 câu đổi thứ tự/top 5,
  nhưng chỉ 4 câu thay metric; Recall thay ở một câu, MRR thay ở ba câu.

Policy được áp dụng cho 50 câu có decompose, không dùng nhãn multi/paraphrase để routing.
14 câu không decompose giữ thứ tự cũ. Gold chỉ dùng để chấm kết quả sau lựa chọn.

## Vì sao chưa giải quyết được multi?

Thứ hạng nhánh là tín hiệu thô: khi một Điều đầu đã đại diện tốt cho nhánh đó, Điều khác
cùng nhánh có thể không nhận thêm điểm độ phủ, dù cần cho một phần lập luận khác.
Thuật toán không kiểm chứng vai trò bằng chứng ở mức ngữ nghĩa, nên không thể coi
"mỗi nhánh đã có đại diện" là "đã đủ căn cứ trả lời".

Một số gold có tín hiệu nhánh yếu: d17/Điều 589 đứng ngoài top 5 của mọi câu con;
d26/Điều 173 cũng ngoài top 5 câu con. d04/Điều 39 có Jev=0.27 và hạng toàn cục 21,
nên bị ngưỡng chất lượng loại khỏi khả năng được đẩy lên. Nới các rào này chỉ vì biết
gold sẽ làm việc thử nghiệm lệ thuộc nhãn; chưa thay đổi chúng sau khi xem kết quả.

## Context và chi phí

Mô phỏng trước/sau với cùng cấu hình context hiện tại (ghi trong config.json):

- Context rỗng: 0 → 0 câu.
- Context đủ gold: 54/64 → 54/64.
- Số block trung bình: 5.390625 → 5.390625.
- Độ dài trung bình, đếm đơn vị cách nhau bởi khoảng trắng: 1307.19 → 1309.48.

Không có bằng chứng cải thiện độ đầy đủ context hoặc câu trả lời cuối từ phép đo này.
Context mô phỏng dùng cùng thiết lập hiện tại cho cả hai thứ tự, không phải đối chiếu
với một bản đo context lịch sử dùng thiết lập không xác định.

0 API calls; 1.774 cặp Jev đều đọc cache full-input-v2. Tái lập đúng pool/thứ tự ứng viên
v2 ở cả 64 câu, kiểm tra lại đúng các metric tham chiếu. Chỉ thứ tự sau Jev thay đổi;
top 2, điểm Jev, merged IDs và candidate recall được giữ nguyên. 183 tests pass.

## Trạng thái

Đã thêm công tắc COVERAGE_ENABLED và các tham số, mặc định tắt; chưa thay đổi .env.
Phiên bản này có thể giữ làm thí nghiệm chi phí thấp, nhưng chưa nên gọi là giải pháp
multi-hop hoàn chỉnh. Muốn tăng rõ số câu đủ gold cần tín hiệu phân biệt vai trò bằng
chứng tốt hơn (ví dụ lựa chọn theo danh sách có kiểm tra các nhu cầu), hoặc retrieval
bổ sung cho những gold chưa vào pool. Các hướng đó chưa được chạy trong lượt này.
