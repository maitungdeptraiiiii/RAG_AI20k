# Audit bottleneck pool decomposition — chỉ dùng cache

Đã tái lập đúng pool và thứ tự của **64/64 câu**, từ 94 truy vấn có cache. API calls = 0; network connect bị chặn; không gọi model, retriever hoặc chạy lại benchmark. Không thay chính sách retrieval.

## Kết luận

Giới hạn **tổng cộng 10 Điều mới** không làm mất gold nào trong lần đo này. Nới riêng quota này chưa có bằng chứng sẽ cải thiện độ phủ gold. Điều này không chứng minh toàn bộ thiết kế 20 + 10 là tối ưu cho mọi dữ liệu.
Các giới hạn trong từng nhánh vẫn tồn tại: lấy 40 chunk, cắt pool trung gian còn 20 Điều, rồi nhánh con giữ 10 Điều. Không được nhầm những giới hạn này với quota 10 Điều mới cuối cùng.

## 15 gold còn thiếu trong top 5 nằm ở đâu?

| Bước mất gold đầu tiên | Số GoldRef | Số câu | ID |
|---|---:|---:|---|
| Quota tổng 10 Điều mới | 0 | 0 | — |
| Top 10 câu con, sau pool trung gian | 0 | 0 | — |
| Pool trung gian 20 Điều mỗi nhánh | 1 | 1 | d02 |
| Không lọt top 40 chunk của bất kỳ nhánh đang có | 6 | 5 | d01, d09, d13, d36, d57 |
| Đã có trong pool cuối, không vào top 5 Jev | 8 | 7 | d04, d10, d17, d26, d52, d59, d62 |

80/95 GoldRef có trong top 5, 15 GoldRef chưa có. Đây là đếm GoldRef, **không phải** Recall@5 macro; benchmark tính trung bình Recall theo từng câu.

## Quota 10 Điều mới chỉ bị chạm ở hai câu

| ID | Điều mới trước quota | Điều bị loại | Gold bị mất vì quota |
|---|---:|---:|---:|
| d03 | 11 | 1 | 0 |
| d22 | 14 | 4 | 0 |

Cả d03 và d22 đều đã lấy đủ gold ở top 5 trong cấu hình mới. 12 câu có decomposition còn lại không có hơn 10 Điều mới sau bỏ trùng với pool gốc. Việc giữ cứng 20 Điều gốc có thể chưa tối ưu nói chung, nhưng quota mới không tạo mất gold được quan sát trên các danh sách này.

## Trường hợp bị cắt trong nhánh: d02

Gold Điều 128 BLHS có vị trí chunk/Điều tốt nhất là 25 trong câu con đầu tiên; nó nằm trong raw top 40 nhưng bị cắt khi dựng pool trung gian 20 Điều. Nó không đến được bước chọn top 10 của nhánh con hay quota 10 Điều mới cuối cùng.
Chỉ tăng quota mới 10 → 20 không cứu được Điều này. Ngay cả bỏ cap trung gian 20, nhánh con vẫn chỉ chọn top 10 nên gold hạng 25 tiếp tục bị loại. Cần thay đổi cách truy vấn/xếp hạng hoặc độ sâu từng nhánh, không chỉ ngân sách cuối.
Gold này gắn với hậu quả chưa được xác định rõ trong câu hỏi; cần rà soát giả định của nhãn trước khi ép prompt tự thêm hậu quả để khớp gold.

## Các gold không lọt raw top 40

| ID | Gold theo dataset | Hạng chunk tốt nhất | Hạng Điều tốt nhất | Có decomposition? |
|---|---|---|---|
| d01 | bo_luat_dan_su_2015.txt: Điều 601 | 66 | 48 | Không |
| d01 | bo_luat_dan_su_2015.txt: Điều 590 | 55 | 38 | Không |
| d09 | bo_luat_hinh_su_2015.txt: Điều 174 | 81 | 77 | Không |
| d13 | bo_luat_dan_su_2015.txt: Điều 584 | 94 | 91 | Không |
| d36 | bo_luat_to_tung_hinh_su_2015.txt: Điều 331 | 45 | 37 | Không |
| d57 | bo_luat_to_tung_dan_su_2015.txt: Điều 37 | 129 | 95 | Không |

Năm câu này đều chỉ tìm bằng câu gốc/HyDE, chưa được decomposition tách. Tăng số Điều mới không có tác dụng khi chưa có nhánh con. Tăng riêng raw fetch 40 cũng chưa chắc giúp, vì phía sau vẫn còn giới hạn Điều từng nhánh.

## Ưu tiên xử lý dựa trên kết quả

1. Chưa nới quota tổng 10 Điều mới chỉ vì nghi nghẽn: hiện không có gold bị mất ở đó.
2. Kiểm tra việc nhận diện nhu cầu thông tin/HyDE ở d01, d09, d13, d36, d57. Không dùng gold làm input prompt và không tự giả định dữ kiện còn thiếu.
3. Xem lại xếp hạng/độ phủ cho d04, d10, d17, d26, d52, d59, d62: có 8 gold trong pool nhưng chưa vào top 5.
4. Với d02, phân biệt cap của từng nhánh với quota mới cuối và rà soát nhãn mơ hồ trước khi tăng độ sâu.

## Phạm vi của bằng chứng

- Gold chỉ dùng sau khi tái lập pool để xác định vị trí mất bằng chứng; không được dùng để chọn pool.
- Chẩn đoán xác định bước lọc đang chặn ứng viên, không chứng minh một cách sửa cụ thể sẽ tăng chất lượng.
- Audit dựa trên 64 câu và các truy vấn đã lưu, không chứng minh tối ưu trên câu hỏi độc lập.
- Mô phỏng dùng cùng thứ tự/dtype nạp vector và cosine implementation của Qdrant local hiện cài. Nếu cache thiếu hoặc pool replay khác trace, script dừng thay vì gọi API hoặc công bố phân loại chắc chắn.
- Không sinh/chấm câu trả lời cuối, không chạy lại baseline hoặc cấu hình khác.
