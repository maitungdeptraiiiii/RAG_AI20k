# Giai đoạn 3 — dữ kiện suy ra và ngoại lệ giữa rule (ghi chú)

Nhánh `feat/team-4.2/w04-rules-engine`. Kế hoạch: `app/team-4.2/docs/superpowers/plans/2026-11-23-rule-engine-phase3-derived-exceptions.md`.

## Văn bản luật đã đọc (BLLĐ 45/2019/QH14)

- Đ20.2.a: hết hạn HĐ xác định thời hạn mà NLĐ vẫn làm việc: trong 30 ngày kể từ ngày hết hạn hai bên phải ký HĐ mới.
- Đ20.2.b: hết 30 ngày không ký mới thì HĐ đã giao kết trở thành HĐ không xác định thời hạn.
- Đ20.2.c: ký mới HĐ xác định thời hạn thì chỉ được ký thêm 01 lần, sau đó phải ký HĐ không xác định thời hạn, trừ: giám đốc
  doanh nghiệp có vốn nhà nước; Đ149.1 (NLĐ cao tuổi); Đ151.2 (NLĐ nước ngoài); Đ177.4 (ban lãnh đạo tổ chức đại diện NLĐ
  tại cơ sở, gia hạn đến hết nhiệm kỳ).

## Đã thêm

- `derived` trong `pack.yaml` (cây ngoại lệ ba trị) và `exception_of` trên rule; hai hàm thuần dùng chung cho Reference và
  Network (`rules/derived.py`, `rules/exceptions.py`).
- Rule labor: `contract_kind_effective` (30 ngày: `worked_after_expiry_days > 30 day` vì "hết thời hạn 30 ngày"; đúng 30
  ngày vẫn trong thời hạn ký), `content.term/r3` (tối đa 2 HĐ xác định thời hạn liên tiếp) với `r3_state_director`,
  `r3_elderly`, `r3_foreign`, `r3_union_leader`, và `r4` (loại HĐ hiệu lực khác loại ghi trong văn bản, `legality: unknown`).

## Số liệu (catalog labor, 39 concept, 50 rule)

| | Reference | Network |
|---|---|---|
| tạo phiên | 0.64 ms | 0.70 ms |
| `update` một dữ kiện là đầu vào của dữ kiện suy ra | 0.68 ms | 0.032 ms |
| `update` dữ kiện chỉ vài rule dùng | 0.67 ms | 0.026 ms |

Biên dịch mạng 0.51 ms. Số liệu một máy, chỉ để thấy cùng bậc với giai đoạn 2; benchmark có kiểm soát là giai đoạn 6.

## Sửa sau review độc lập (Important, mỗi mục có test đỏ trước)

1. Nhóm anh em có một ngoại lệ cho giá trị và một ngoại lệ `UNKNOWN` giờ ra `UNKNOWN` (trước: ra giá trị, bớt dữ kiện có thể
   thành `FAIL`). **Lệch chữ spec §5.3 bước 1, chọn bất biến** (xem spec).
2. Người dùng trả lời `worked_after_expiry_days = 45` (không đơn vị) từng làm `r4` kẹt `UNKNOWN` mà không hỏi gì: thêm
   `user_fact_units` trong `pack.yaml`, `user_fact_set` dùng làm đơn vị mặc định.
3. Bộ nạp nay từ chối dữ kiện suy ra trùng `document_facts` / `user_facts` của gói khác (anh em hoặc cha).
4. `content.term/r3` ra `PASS` khi điều khoản thời hạn không được nhận ra dù đã biết đang ký HĐ thứ ba: thêm cờ rule
   `standalone: true`, `r3` dùng.
Kèm: bộ nạp báo `CatalogError` (thay vì crash) với `derived` sai hình dạng và đơn vị lạ trong `when`.

## Kiểm thử

- Đối chiếu ngẫu nhiên Network = Reference trên gói tổng hợp có dữ kiện suy ra hai tầng, ngoại lệ lồng và ngoại lệ chéo
  concept: 20 seed × 150 bước, so bằng JSON (kể cả kiểu giá trị `True` / `1.0`).
- Một lỗi có sẵn từ giai đoạn 2 lộ ra nhờ so bằng JSON và đã sửa: `NetworkSession` bỏ ghi kết quả mới khi `==` coi bằng nhau
  (`True` và `1.0`), nên kiểu giá trị trong `facts_used` bị cũ.
- `tests/test_bridge_tagger.py::test_failed_batch_warns_and_others_continue` fail một lần khi chạy nhóm với
  `RAG_RULE_EVALUATOR=reference`, rồi xanh khi chạy riêng 3 lần và chạy lại nhóm 2 lần (flaky, không liên quan engine).

## Chưa làm

- Đ22.2 và Đ25 "một lần một công việc": chuyển sang giai đoạn 7b (cần đối tượng).
- `fixed_term_contract_count`, `worked_after_expiry_days`, `new_contract_signed` và 4 dữ kiện ngoại lệ hiện do người dùng
  cung cấp; chưa có đường trích từ hồ sơ.
