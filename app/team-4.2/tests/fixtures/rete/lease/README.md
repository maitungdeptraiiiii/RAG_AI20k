# Hợp đồng thuê nhà ở mẫu (phần Tú, D3b)

Tên người và số CCCD trong t1–t6, t8–t10 đều giả (ghi rõ trong văn bản); 23/11 thêm dòng địa chỉ giả cho các bên ở t1–t6
(Đ163.1 bắt buộc ghi địa chỉ các bên, giữ đúng ý 'hợp lệ' của từng mẫu); t7 là mẫu có sẵn của dự án
(`data/team-4.2/contracts_demo/hop_dong_thue_nha_2023.txt`). Mỗi hợp đồng nhắm một quy định; nhãn đúng ở `gold.yaml`
(viết trước khi chạy engine), dữ kiện bước trích phải lấy được ở `facts.yaml`. Ký từ 01/08/2024 áp Luật Nhà ở 27/2023,
trước đó Luật Nhà ở 65/2014 (engine chọn theo ngày ký). Test: `tests/test_rete_lease_fixtures.py`.
Hồ sơ nhiều văn bản (HĐ thuê + phụ lục gia hạn + phụ lục tăng giá) nằm ở `../r1/`.

| Hợp đồng | Ký ngày | Kiểm gì |
|---|---|---|
| `t1_hop_le` | 01/03/2025 | Đủ nội dung bắt buộc, bên cho thuê chỉ chấm dứt theo căn cứ luật, nợ 03 tháng mới được chấm dứt: hợp lệ |
| `t2_lay_nha_tuy_y` | 01/10/2024 | Bên cho thuê lấy lại nhà tùy ý: trái Đ172.1 Luật Nhà ở 2023 |
| `t3_no_mot_thang` | 15/01/2025 | Chậm trả 01 tháng đã cho chấm dứt: dưới mức 03 tháng của Đ172.2.b |
| `t4_cam_ben_thue_cham_dut` | 10/09/2024 | Cấm bên thuê đơn phương chấm dứt trong mọi trường hợp: trái Đ172.3 (cách đọc Tùng duyệt 23/11) |
| `t5_thieu_thoi_han` | 01/05/2025 | Không ghi thời hạn thuê và ngày giao nhà: thiếu nội dung bắt buộc Đ163.5 |
| `t6_truoc_2024` | 01/06/2020 | Ký trước 2024: áp Luật Nhà ở 2014 (Đ132.2.b), chậm 02 tháng đã cho chấm dứt: vi phạm |
| `t8_thieu_dia_chi_ngay_ky` | (không ghi) | Chỉ có họ tên, không có địa chỉ các bên, không ghi ngày ký: thiếu nội dung Đ163.1, Đ163.10 |
| `t9_ben_thue_sua_lon` | 20/04/2025 | Bên thuê chịu cả hư hỏng kết cấu: trái BLDS Đ477.1 (cách đọc chờ duyệt) |
| `t10_cat_dien_nuoc` | 05/06/2025 | Bên cho thuê cắt điện nước, khóa cửa không báo trước: trái BLDS Đ478.1 (cách đọc chờ duyệt) |
| `t7_mau_2023` | 15/03/2023 | Mẫu thật của dự án (Luật Nhà ở 2014): bên cho thuê chấm dứt bất cứ lúc nào (Đ132.1) và chậm 30 ngày đã cho chấm dứt (Đ132.2.b): hai vi phạm; bên thuê vẫn có căn cứ chấm dứt nên không vi phạm Đ132.3 |

t7 thêm một vi phạm: vào kiểm tra nhà bất cứ lúc nào không cần báo trước (Điều 6.3, BLDS Đ478.1, cách đọc chờ duyệt).

Chưa kiểm (không có rule có căn cứ, xem `docs/rule_inventory/civil_lease.yaml` và
`app/team-4.2/docs/superpowers/notes/w04-rule-engine/han_che_va_loi_ton_dong.md` mục L): bên cho thuê đơn phương điều chỉnh giá khi "thị trường thay đổi"
(t7 Điều 4.3), bên thuê mất cọc khi chấm dứt đúng căn cứ (t7 Điều 9.2), cho thuê lại.
