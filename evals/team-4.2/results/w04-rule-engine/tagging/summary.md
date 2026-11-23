# Đo gán khái niệm bằng LLM thật (2026-11-24)

Trích dữ kiện: `gpt-6-luna` · gán khái niệm: `anthropic/claude-haiku-5.5` · luồng `check_contract(packs=[gói])`.

## commercial

| Chỉ số | Giá trị |
|---|---|
| docs | 4 |
| concept_precision | 0.786 |
| concept_recall | 1.0 |
| slots | 11/11 |
| rules | 10/10 |
| false_fail | 0 |
| missed_fail | 0 |

| Hợp đồng | Thiếu khái niệm | Gán thừa | Chờ duyệt | Slot sai | Rule sai | FAIL thừa | FAIL bỏ sót |
|---|---|---|---|---|---|---|---|
| m1_mua_ban_hop_le | — | civil.rescission_notice, civil.unilateral_termination | — | — | — | — | — |
| m2_phat_vuot_tran | — | — | — | — | — | — | — |
| m3_dich_vu_dinh_chi | — | — | — | — | — | — | — |
| m4_tong_muc_phat | — | civil.rescission_notice | — | — | — | — | — |

## consumer

| Chỉ số | Giá trị |
|---|---|
| docs | 6 |
| concept_precision | 0.651 |
| concept_recall | 1.0 |
| slots | 18/18 |
| rules | 52/52 |
| false_fail | 2 |
| missed_fail | 0 |

| Hợp đồng | Thiếu khái niệm | Gán thừa | Chờ duyệt | Slot sai | Rule sai | FAIL thừa | FAIL bỏ sót |
|---|---|---|---|---|---|---|---|
| c1_internet_hop_le | — | — | — | — | — | — | — |
| c2_dien_may_mien_tru | — | civil.standard_terms_exemption, consumer.content_delivery, consumer.content_parties, consumer.content_payment, consumer.content_price_quality, consumer.content_product, consumer.content_time_term | — | — | — | — | — |
| c3_phong_tap_gia_han | — | consumer.unilateral_change | — | — | — | consumer.unilateral_change/r1 | — |
| c4_mau_thieu_noi_dung | — | — | — | — | — | — | — |
| c5_khoa_hoc_du_lieu | — | consumer.content_delivery, consumer.content_parties, consumer.content_payment, consumer.content_price_quality, consumer.content_product, consumer.content_termination, consumer.content_time_term | — | — | — | — | — |
| c6_noi_that_gia_giao | — | consumer.content_delivery, consumer.content_parties, consumer.content_payment, consumer.content_price_quality, consumer.content_product, consumer.content_time_term, consumer.liability_exclusion | — | — | — | consumer.liability_exclusion/r1 | — |
