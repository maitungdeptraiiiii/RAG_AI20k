# Hợp đồng người tiêu dùng mẫu (gói `consumer`, 23/11)

Tên công ty, tên người, địa chỉ, số điện thoại đều giả. Nhãn đúng viết tay ở `labels.yaml` từ Luật BVQLNTD 19/2023/QH15
TRƯỚC khi chạy engine; `gold.yaml` sinh từ đó bằng `scripts/team-4.2/gold_from_labels.py` (câu căn cứ lấy từ
`docs/rule_inventory/consumer.yaml`). CHỜ TÙNG DUYỆT. Test: `tests/test_rete_pack_fixtures.py`.

| Hợp đồng | Ký ngày | Người dùng trả lời | Kiểm gì |
|---|---|---|---|
| `c1_internet_hop_le` | 10/02/2025 | mẫu, dịch vụ liên tục | Đủ 10 nội dung Đ23.3, báo trước khi hết hạn (Đ42.2), đổi giá có quyền chấm dứt (Đ25.7), bảo trì báo trước 03 ngày (Đ41.3): hợp lệ |
| `c2_dien_may_mien_tru` | 03/09/2025 | không mẫu | Miễn trách mọi hư hỏng (Đ25.1), cấm khiếu nại / khởi kiện (Đ25.2), bên bán giải thích cuối cùng (Đ25.8) |
| `c3_phong_tap_gia_han` | 15/08/2025 | mẫu, dịch vụ liên tục | Tự động gia hạn trừ tiền (Đ25.13), đổi phí không cho chấm dứt (Đ25.7), ngừng dịch vụ không báo (Đ41.3), thiếu 4 nội dung Đ23.3 và báo trước khi hết hạn |
| `c4_mau_thieu_noi_dung` | 20/10/2025 | mẫu, không liên tục | Thiếu bảo vệ thông tin, chấm dứt, bất khả kháng, giải quyết tranh chấp (Đ23.3.g, h, i, k) |
| `c5_khoa_hoc_du_lieu` | 01/11/2025 | không mẫu | Buộc đồng ý chia sẻ dữ liệu mới được ký (Đ25.14), đổi hợp đồng tùy ý (Đ25.3), chế tài lệch (Đ25.12) |
| `c6_noi_that_gia_giao` | 12/09/2025 | không mẫu | Giá tính lúc giao (Đ25.6), miễn trách qua bên vận chuyển (Đ25.9), vẫn phải trả khi bên bán vi phạm (Đ25.10), bên bán tự kết luận vi phạm (Đ25.5), chuyển giao không cần đồng ý (Đ25.11), mất cọc một chiều (Đ25.12, cách đọc chờ duyệt) |

Chưa có mẫu cho Đ25.4 (đổi điều kiện giao dịch chung không cho chấm dứt): đã kiểm bằng ví dụ trong bản liệt kê.
