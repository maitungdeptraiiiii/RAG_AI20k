# Eval rule engine theo gói (K3)

Sinh bằng `app/team-4.2/scripts/eval_rule_engine.py` từ `tests/fixtures/rete/*/gold.yaml`. Engine: `legacy`, `reference`, `network`. `legacy` = `rag.bridge.engine.evaluate` (không nhận đối tượng hồ sơ: rule xuyên đối tượng ra MISSING).

## Theo gói

| engine | gói | đúng | sai | UNKNOWN | thiếu kết quả | tổng nhãn | tỉ lệ đúng |
|---|---|---|---|---|---|---|---|
| legacy | civil_lease | 67 | 0 | 0 | 0 | 67 | 100% |
| legacy | civil_loan | 12 | 0 | 0 | 0 | 12 | 100% |
| legacy | commercial | 10 | 0 | 0 | 0 | 10 | 100% |
| legacy | consumer | 52 | 0 | 0 | 0 | 52 | 100% |
| legacy | labor | 7 | 0 | 0 | 18 | 25 | 28% |
| reference | civil_lease | 67 | 0 | 0 | 0 | 67 | 100% |
| reference | civil_loan | 12 | 0 | 0 | 0 | 12 | 100% |
| reference | commercial | 10 | 0 | 0 | 0 | 10 | 100% |
| reference | consumer | 52 | 0 | 0 | 0 | 52 | 100% |
| reference | labor | 25 | 0 | 0 | 0 | 25 | 100% |
| network | civil_lease | 67 | 0 | 0 | 0 | 67 | 100% |
| network | civil_loan | 12 | 0 | 0 | 0 | 12 | 100% |
| network | commercial | 10 | 0 | 0 | 0 | 10 | 100% |
| network | consumer | 52 | 0 | 0 | 0 | 52 | 100% |
| network | labor | 25 | 0 | 0 | 0 | 25 | 100% |

## Theo loại rule (kind)

| engine | kind | đúng | sai | UNKNOWN | thiếu kết quả | tổng nhãn | tỉ lệ đúng |
|---|---|---|---|---|---|---|---|
| legacy | count_limit | 0 | 0 | 0 | 3 | 3 | 0% |
| legacy | notice | 5 | 0 | 0 | 0 | 5 | 100% |
| legacy | payment | 7 | 0 | 0 | 0 | 7 | 100% |
| legacy | penalty | 4 | 0 | 0 | 0 | 4 | 100% |
| legacy | prohibited_practice | 3 | 0 | 0 | 0 | 3 | 100% |
| legacy | rate_cap | 12 | 0 | 0 | 0 | 12 | 100% |
| legacy | required_content | 71 | 0 | 0 | 1 | 72 | 99% |
| legacy | termination | 20 | 0 | 0 | 0 | 20 | 100% |
| legacy | time_limit | 10 | 0 | 0 | 14 | 24 | 42% |
| legacy | void_term | 16 | 0 | 0 | 0 | 16 | 100% |
| reference | count_limit | 3 | 0 | 0 | 0 | 3 | 100% |
| reference | notice | 5 | 0 | 0 | 0 | 5 | 100% |
| reference | payment | 7 | 0 | 0 | 0 | 7 | 100% |
| reference | penalty | 4 | 0 | 0 | 0 | 4 | 100% |
| reference | prohibited_practice | 3 | 0 | 0 | 0 | 3 | 100% |
| reference | rate_cap | 12 | 0 | 0 | 0 | 12 | 100% |
| reference | required_content | 72 | 0 | 0 | 0 | 72 | 100% |
| reference | termination | 20 | 0 | 0 | 0 | 20 | 100% |
| reference | time_limit | 24 | 0 | 0 | 0 | 24 | 100% |
| reference | void_term | 16 | 0 | 0 | 0 | 16 | 100% |
| network | count_limit | 3 | 0 | 0 | 0 | 3 | 100% |
| network | notice | 5 | 0 | 0 | 0 | 5 | 100% |
| network | payment | 7 | 0 | 0 | 0 | 7 | 100% |
| network | penalty | 4 | 0 | 0 | 0 | 4 | 100% |
| network | prohibited_practice | 3 | 0 | 0 | 0 | 3 | 100% |
| network | rate_cap | 12 | 0 | 0 | 0 | 12 | 100% |
| network | required_content | 72 | 0 | 0 | 0 | 72 | 100% |
| network | termination | 20 | 0 | 0 | 0 | 20 | 100% |
| network | time_limit | 24 | 0 | 0 | 0 | 24 | 100% |
| network | void_term | 16 | 0 | 0 | 0 | 16 | 100% |

## Ma trận nhầm — `legacy` (hàng: gold, cột: engine)

| gold \ engine | PASS | FAIL | UNKNOWN | NOT_APPLICABLE | MISSING |
|---|---|---|---|---|---|
| PASS | 96 | 0 | 0 | 0 | 12 |
| FAIL | 0 | 47 | 0 | 0 | 5 |
| UNKNOWN | 0 | 0 | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 5 | 1 |

## Ma trận nhầm — `reference` (hàng: gold, cột: engine)

| gold \ engine | PASS | FAIL | UNKNOWN | NOT_APPLICABLE | MISSING |
|---|---|---|---|---|---|
| PASS | 108 | 0 | 0 | 0 | 0 |
| FAIL | 0 | 52 | 0 | 0 | 0 |
| UNKNOWN | 0 | 0 | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 6 | 0 |

## Ma trận nhầm — `network` (hàng: gold, cột: engine)

| gold \ engine | PASS | FAIL | UNKNOWN | NOT_APPLICABLE | MISSING |
|---|---|---|---|---|---|
| PASS | 108 | 0 | 0 | 0 | 0 |
| FAIL | 0 | 52 | 0 | 0 | 0 |
| UNKNOWN | 0 | 0 | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 6 | 0 |

## Chọn gói theo loại hợp đồng

| hồ sơ | ca | loại theo hồ sơ | loại nhận diện (classify_contract) | gói được chạy | sai miền |
|---|---|---|---|---|---|
| a1 | a1@2023-03-01 | labor_contract | labor_contract | labor | không |
| b1 | b1@2023-01-01 | labor_contract | labor_contract | labor | không |
| b2 | b2@2024-01-01 | labor_contract | labor_contract | labor | không |
| b3 | b3@2023-06-01 | labor_contract | labor_contract | labor | không |
| b4 | b4@2023-03-15 | labor_contract | labor_contract | labor | không |
| b5 | b5@2022-01-01 | labor_contract | labor_contract | labor | không |
| commercial | m1_mua_ban_hop_le | commercial_sale_contract | commercial_sale_contract | commercial | không |
| commercial | m2_phat_vuot_tran | commercial_sale_contract | commercial_sale_contract | commercial | không |
| commercial | m3_dich_vu_dinh_chi | commercial_sale_contract | commercial_service_contract | commercial | không |
| commercial | m4_tong_muc_phat | commercial_sale_contract | commercial_sale_contract | commercial | không |
| consumer | c1_internet_hop_le | consumer_contract | consumer_contract | consumer | không |
| consumer | c2_dien_may_mien_tru | consumer_contract | consumer_contract | consumer | không |
| consumer | c3_phong_tap_gia_han | consumer_contract | consumer_contract | consumer | không |
| consumer | c4_mau_thieu_noi_dung | consumer_contract | consumer_contract | consumer | không |
| consumer | c5_khoa_hoc_du_lieu | consumer_contract | consumer_contract | consumer | không |
| consumer | c6_noi_that_gia_giao | consumer_contract | consumer_contract | consumer | không |
| lease | t10_cat_dien_nuoc | lease_contract | lease_contract | civil_lease | không |
| lease | t1_hop_le | lease_contract | lease_contract | civil_lease | không |
| lease | t2_lay_nha_tuy_y | lease_contract | lease_contract | civil_lease | không |
| lease | t3_no_mot_thang | lease_contract | lease_contract | civil_lease | không |
| lease | t4_cam_ben_thue_cham_dut | lease_contract | lease_contract | civil_lease | không |
| lease | t5_thieu_thoi_han | lease_contract | lease_contract | civil_lease | không |
| lease | t6_truoc_2024 | lease_contract | lease_contract | civil_lease | không |
| lease | t7_mau_2023 | lease_contract | lease_contract | civil_lease | không |
| lease | t8_thieu_dia_chi_ngay_ky | lease_contract | lease_contract | civil_lease | không |
| lease | t9_ben_thue_sua_lon | lease_contract | lease_contract | civil_lease | không |
| loan | l1_hop_le | loan_contract | loan_contract | civil_loan | không |
| loan | l2_vuot_tran | loan_contract | loan_contract | civil_loan | không |
| loan | l3_lai_nam_hop_le | loan_contract | loan_contract | civil_loan | không |
| loan | l4_khong_lai_cam_tra_truoc | loan_contract | loan_contract | civil_loan | không |
| loan | l5_doi_truoc_han_tuy_y | loan_contract | loan_contract | civil_loan | không |
| loan | l6_truoc_2017 | loan_contract | loan_contract | civil_loan | không |
| loan | l7_doi_truoc_han_sai_muc_dich | loan_contract | loan_contract | civil_loan | không |
| r1 | r1@2024-09-10 | lease_contract | lease_contract | civil_lease | không |

## Hồ sơ chưa có gold

- Không có.

## Gold chờ Tùng duyệt

- `a1`
- `b1`
- `b2`
- `b3`
- `b4`
- `b5`
- `commercial`
- `consumer`
- `r1`

## Ca sai — `legacy` (18)

- `tests/fixtures/rete/a1` · ca `a1@2023-03-01` · rule `content.term/r5` @employee=e1 · ngày 2023-03-01: gold PASS, engine MISSING
- `tests/fixtures/rete/a1` · ca `a1@2024-09-01` · rule `content.term/r7` @contract=hd_2023 · ngày 2024-09-01: gold PASS, engine MISSING
- `tests/fixtures/rete/a1` · ca `a1@2024-09-01` · rule `appendix.states_change/r1` @contract=hd_2023 · ngày 2024-09-01: gold PASS, engine MISSING
- `tests/fixtures/rete/a1` · ca `a1@2025-01-31` · rule `content.term/r7` @contract=hd_2023 · ngày 2025-01-31: gold PASS, engine MISSING
- `tests/fixtures/rete/a1` · ca `a1@2025-02-01` · rule `content.term/r7` @contract=hd_2023 · ngày 2025-02-01: gold FAIL, engine MISSING
- `tests/fixtures/rete/b1` · ca `b1@2023-01-01` · rule `content.term/r5` @employee=e1 · ngày 2023-01-01: gold PASS, engine MISSING
- `tests/fixtures/rete/b1` · ca `b1@2023-12-31` · rule `content.term/r5` @employee=e1 · ngày 2023-12-31: gold PASS, engine MISSING
- `tests/fixtures/rete/b1` · ca `b1@2024-01-01` · rule `content.term/r5` @employee=e1 · ngày 2024-01-01: gold FAIL, engine MISSING
- `tests/fixtures/rete/b1` · ca `b1@2024-03-01` · rule `content.term/r6` @employee=e1 · ngày 2024-03-01: gold PASS, engine MISSING
- `tests/fixtures/rete/b2` · ca `b2@2024-01-01` · rule `content.term/r5` @employee=e1 · ngày 2024-01-01: gold NOT_APPLICABLE, engine MISSING
- `tests/fixtures/rete/b3` · ca `b3@2023-06-01` · rule `content.term/r6` @employee=e1 · ngày 2023-06-01: gold FAIL, engine MISSING
- `tests/fixtures/rete/b3` · ca `b3@2023-06-01` · rule `content.term/r5` @employee=e1 · ngày 2023-06-01: gold PASS, engine MISSING
- `tests/fixtures/rete/b4` · ca `b4@2023-03-15` · rule `content.term/r5` @employee=e1 · ngày 2023-03-15: gold FAIL, engine MISSING
- `tests/fixtures/rete/b4` · ca `b4@2023-06-01` · rule `content.term/r6` @employee=e1 · ngày 2023-06-01: gold PASS, engine MISSING
- `tests/fixtures/rete/b5` · ca `b5@2022-01-01` · rule `probation.once/r2` @employee=e1,job=nhân viên kế toán · ngày 2022-01-01: gold PASS, engine MISSING
- `tests/fixtures/rete/b5` · ca `b5@2022-12-31` · rule `probation.once/r2` @employee=e1,job=nhân viên kế toán · ngày 2022-12-31: gold PASS, engine MISSING
- `tests/fixtures/rete/b5` · ca `b5@2023-01-01` · rule `probation.once/r2` @employee=e1,job=nhân viên kế toán · ngày 2023-01-01: gold FAIL, engine MISSING
- `tests/fixtures/rete/b5` · ca `b5@2023-01-01` · rule `content.term/r5` @employee=e1 · ngày 2023-01-01: gold PASS, engine MISSING

## Ca sai — `reference` (0)

- Không có.

## Ca sai — `network` (0)

- Không có.
