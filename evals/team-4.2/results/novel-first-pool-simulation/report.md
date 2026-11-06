# Mô phỏng lọc trùng trước top 10 — offline

Không sửa pipeline, không gọi API/model và không chạy lại benchmark. Gold chỉ dùng để đánh giá pool sau khi chọn; không dùng để chọn ứng viên.

## Chính sách được mô phỏng

Giữ nguyên pool gốc tối đa 20 Điều. Mỗi câu con xét toàn bộ raw top 40 chunk đã cache, bỏ Điều đã có trong pool gốc trước, rồi giữ tối đa 10 Điều mới. RRF chọn tổng tối đa 10 Điều bổ sung. Bỏ cap trung gian 20 Điều ở nhánh con; giữ rank Dense ban đầu khi tính RRF để không thay cả cách fusion.

## Kết quả

| Kiểm tra | Giá trị |
|---|---:|
| Replay pool hiện tại khớp trace | 64/64 |
| Pool gốc được giữ nguyên | 64/64 |
| Câu đổi pool | 13 |
| Câu có thêm gold | 0 |
| Câu mất gold | 0 |
| Pool recall trung bình cũ | 0.937500 |
| Pool recall trung bình mới | 0.937500 |
| Tổng số chunk ứng viên cũ | 1629 |
| Tổng số chunk ứng viên mới | 1723 |
| Cặp Jev chưa có cache nếu muốn chấm tiếp | 96 |
| Số Điều tối đa | 30 |
| Số Điều mới tối đa | 10 |

## Từng câu có thay đổi pool

| ID | Số Điều cũ → mới | Pool recall cũ → mới | Thêm gold | Mất gold |
|---|---:|---:|---|---|
| d02 | 24 → 30 | 0.667 → 0.667 | — | — |
| d05 | 20 → 30 | 1.000 → 1.000 | — | — |
| d10 | 24 → 30 | 1.000 → 1.000 | — | — |
| d11 | 22 → 30 | 1.000 → 1.000 | — | — |
| d22 | 30 → 30 | 1.000 → 1.000 | — | — |
| d28 | 22 → 30 | 1.000 → 1.000 | — | — |
| d38 | 22 → 30 | 1.000 → 1.000 | — | — |
| d39 | 25 → 30 | 1.000 → 1.000 | — | — |
| d43 | 22 → 30 | 1.000 → 1.000 | — | — |
| d44 | 22 → 30 | 1.000 → 1.000 | — | — |
| d48 | 26 → 30 | 1.000 → 1.000 | — | — |
| d49 | 23 → 30 | 1.000 → 1.000 | — | — |
| d55 | 20 → 30 | 1.000 → 1.000 | — | — |

## Giới hạn

Đây là mô phỏng độ phủ pool, không phải benchmark rerank. Thêm gold vào pool không bảo đảm gold vào top 5; thêm ứng viên ngoài gold có thể làm xếp hạng tốt hoặc xấu hơn. Số Điều không tăng quá 30 nhưng số chunk/cặp Jev thực có thể tăng. Không thể suy ra chi phí tiền hoặc độ đúng câu trả lời từ mô phỏng này.
Các câu không được decomposition tách giữ nguyên pool, nên cách này không sửa được các gold đang nằm sâu trong nhánh câu gốc của chúng.


## Vì sao d02 vẫn không có thêm gold?

Điều 128 BLHS có hạng 25 ở danh sách thô của câu con đầu. Sau khi bỏ các Điều trùng với pool gốc, nó vẫn chỉ ở hạng 17 trong các Điều mới. Vì mỗi câu con giữ 10 Điều mới, nó tiếp tục không được chọn. Do đó thay thứ tự lọc chưa đủ để sửa trường hợp này.

## Quyết định sau mô phỏng

Chưa áp dụng vào pipeline và chưa gọi Jev để chấm cấu hình này. Pool đổi ở 13 câu nhưng không tăng độ phủ gold; nếu muốn đo ranking tiếp sẽ có 96 cặp Jev chưa có điểm cache. Chưa có bằng chứng về lợi ích đủ rõ để ưu tiên chi phí đó. Kết luận chỉ áp dụng cho các truy vấn và bộ nhãn hiện có, không phải chứng minh phương án không bao giờ hữu ích.
