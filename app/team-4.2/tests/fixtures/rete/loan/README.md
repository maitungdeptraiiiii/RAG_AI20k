# Hợp đồng vay mẫu (phần Tú, D3)

Tên người và số CCCD đều giả (ghi rõ trong văn bản). Mỗi hợp đồng nhắm một quy định; nhãn đúng ở `gold.yaml`
(viết trước khi chạy engine), dữ kiện bước trích phải lấy được ở `facts.yaml`. Test: `tests/test_rete_loan_fixtures.py`.

| Hợp đồng | Ký ngày | Kiểm gì |
|---|---|---|
| `l1_hop_le` | 01/03/2024 | Lãi 1%/tháng (12%/năm): trong trần 20%/năm (BLDS Đ468.1); đọc đúng đơn vị theo tháng |
| `l2_vuot_tran` | 10/05/2024 | Lãi 3%/tháng (36%/năm) vượt trần; lãi quá hạn 4,5%/tháng (54%/năm) vượt 30%/năm (NQ 01/2019 Đ5.2.c) |
| `l3_lai_nam_hop_le` | 01/08/2023 | Lãi 18%/năm, lãi quá hạn 27%/năm, lãi chậm trả 10%/năm: đều trong trần |
| `l4_khong_lai_cam_tra_truoc` | 01/02/2025 | Vay không lãi có kỳ hạn mà cấm bên vay trả trước hạn: trái Đ470.1 |
| `l5_doi_truoc_han_tuy_y` | 20/06/2024 | Bên cho vay đòi trước hạn bất cứ lúc nào không cần đồng ý: trái Đ465.3 |
| `l6_truoc_2017` | 15/06/2016 | Hợp đồng trước 01/01/2017: trần BLDS 2005 Đ476 (150% × 9% = 13,5%/năm), lãi 15%/năm vượt |
| `l7_doi_truoc_han_sai_muc_dich` | 02/09/2024 | Đòi trước hạn chỉ khi dùng sai mục đích sau khi nhắc: thuộc ngoại lệ Đ467 |

Chưa có: hợp đồng không ghi kỳ của lãi ("lãi suất 2%"), có điều khoản phạt vi phạm cùng lãi quá hạn (NQ 01/2019 Đ12),
hợp đồng của tổ chức tín dụng (ngoại lệ Luật Các TCTD Đ100).
