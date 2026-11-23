# Hợp đồng thương mại mẫu (gói `commercial`, 23/11)

Tên công ty, mã số doanh nghiệp, địa chỉ đều giả. Nhãn đúng viết tay ở `labels.yaml` từ Luật Thương mại 2005 và
NQ 01/2019/NQ-HĐTP TRƯỚC khi chạy engine; `gold.yaml` sinh bằng `scripts/team-4.2/gold_from_labels.py`. CHỜ TÙNG DUYỆT.
Test: `tests/test_rete_pack_fixtures.py`.

| Hợp đồng | Ký ngày | Kiểm gì |
|---|---|---|
| `m1_mua_ban_hop_le` | 05/03/2025 | Phạt 8% (đúng trần Đ301), thông báo ngay khi đình chỉ / hủy bỏ (Đ315), lãi chậm thanh toán 15%/năm: hợp lệ |
| `m2_phat_vuot_tran` | 20/11/2024 | Phạt 12% > 8% (Đ301); lãi chậm thanh toán 24%/năm: trần BLDS 20% KHÔNG áp cho hợp đồng thương mại (LTM Đ306, NQ 01/2019 Đ11; cách đọc chờ duyệt) |
| `m3_dich_vu_dinh_chi` | 12/06/2025 | Dịch vụ vận chuyển: đình chỉ ngay không cần thông báo (Đ315); phạt 5% hợp lệ |
| `m4_tong_muc_phat` | 18/07/2025 | Tổng mức phạt 10% > 8% (Đ301 áp cho cả tổng mức phạt nhiều vi phạm) |
