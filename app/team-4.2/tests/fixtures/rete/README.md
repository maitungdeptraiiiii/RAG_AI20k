# Bộ hồ sơ mẫu cho rule engine (W04) — định dạng chốt (A4, C7)

Mỗi hồ sơ một thư mục. Hồ sơ nhiều văn bản (a1, b1–b5, r1) dùng đủ năm loại file dưới đây; bộ hợp đồng đơn lẻ
(`loan/`, `lease/`) chỉ có `facts.yaml` + `gold.yaml` (một hợp đồng là một đối tượng). Test: `tests/test_rete_dossiers.py`
(hồ sơ), `tests/test_rete_loan_fixtures.py`, `tests/test_rete_lease_fixtures.py`.

| Hồ sơ | Văn bản | Kiểm gì | Căn cứ |
|---|---|---|---|
| a1 | HĐ xác định thời hạn 2023 + 3 phụ lục | lương tối thiểu vùng theo kỳ (vi phạm phát sinh khi luật đổi, hết khi phụ lục tăng lương, lại vi phạm 2026); phụ lục sửa thời hạn | NĐ 38/2022, 74/2024, 293/2025; BLLĐ Đ22.2 |
| b1 | 3 HĐ xác định thời hạn liên tiếp | giới hạn số lần ký | BLLĐ Đ20.2.c |
| b2 | như b1, NLĐ cao tuổi | ngoại lệ ghi đè quy tắc chung | Đ20.2.c, Đ149.1 |
| b3 | HĐ1 hết hạn, NLĐ vẫn làm, HĐ2 ký sau 73 ngày | kết luận trung gian "trở thành HĐ không xác định thời hạn" | Đ20.2.b |
| b4 | b3 + HĐ bị sót ký 10/01/2023 | kết luận trung gian rút lại; thành HĐ xác định thời hạn thứ ba | Đ20.2.b, Đ20.2.c |
| b5 | HĐ2 thử việc lại cùng công việc | join theo (NLĐ, công việc) | Đ25 |
| r1 | HĐ thuê nhà + phụ lục gia hạn + phụ lục tăng giá | phụ lục hai bên ký là hợp lệ: không ra vi phạm (D37) | Luật Nhà ở 2023 Đ170.2 |

## 1. `dossier.yaml` (tu.md §3)

```yaml
dossier_id: b1
review_date: 2024-03-01            # ngày soát mặc định (kịch bản có thể đổi)
packs: [labor]                     # bỏ trống -> chọn theo loại văn bản (packs_for_kind / classify_contract)
parties:                           # role = id vai trò trong `roles` của gói (labor: NLD / NSDLD; thuê nhà: BEN_CHO_THUE / BEN_THUE)
  - {id: e1, role: NLD, name: "Nguyễn Văn Mẫu"}
  - {id: c1, role: NSDLD, name: "Công ty TNHH Mẫu"}
documents:                         # kind = một document_kinds của gói, hoặc `amendment` (phụ lục; refs.contract bắt buộc)
  - {doc_id: hd1_2022, file: hd1_2022.txt, kind: labor_contract, refs: {employee: e1, employer: c1}}
  - {doc_id: hd1_2022_pl1, file: hd1_2022_pl1.txt, kind: amendment, refs: {contract: hd1_2022}}
user_facts: {wage_region: I}       # dữ kiện người dùng trả lời (tên theo user_facts của gói)
```

`refs` trỏ tới `id` của một bên hoặc `doc_id` của một văn bản. Tên khóa của `refs` là tên `refs` trong `object_types`
của gói (labor: Contract `employee`, Amendment `contract`). Không dùng dữ liệu cá nhân thật.

## 2. Văn bản `.txt`

Giữ cấu trúc Điều/Khoản để `parse_contract` đọc được. Phụ lục bắt đầu bằng dòng `PHỤ LỤC …`, có câu
"có hiệu lực kể từ ngày dd/mm/yyyy" và dẫn chiếu kiểu "sửa đổi Điều 2 của Hợp đồng" (để `rag.contracts.amendments`
bắt được). Test ghép hợp đồng + các phụ lục của nó thành một tài liệu (mỗi file một trang) như khi quét cả bộ.

## 3. `objects.yaml` — bảng đối tượng kỳ vọng (viết tay)

Đầu vào engine trong test và **đáp án cho `dossier_objects` của Huy (H1)**: chạy `dossier_objects(load_dossier(...))`
phải ra đúng bảng này. Mỗi văn bản là một đối tượng cùng id.

```yaml
- id: hd1_2022
  type: Contract                   # một kiểu trong object_types của gói
  valid_from: 2022-01-01
  valid_to: 2022-12-31             # bỏ trống: còn hiệu lực / không thời hạn
  refs: {employee: e1}
  attrs:                           # tên trong object_types[type].attrs; value [+ unit] [+ quote nguyên văn trong văn bản]
    kind: {value: xac_dinh_thoi_han, quote: "Loại hợp đồng: Hợp đồng lao động xác định thời hạn"}
    worked_after_expiry_days: {value: 0, unit: day, why: "HĐ2 ký ngay ngày hôm sau"}
```

Thuộc tính không có câu trích (vd. số ngày làm tiếp sau khi hết hạn: suy từ ngày của hai văn bản) ghi `why`.

## 4. `facts.yaml` — dữ kiện cấp hợp đồng theo thời gian (khi cần)

```yaml
base_salary_vnd:                   # dữ kiện của gói; mỗi giá trị có hiệu lực từ `from` (ngày hiệu lực của văn bản ghi nó)
  - {value: 4700000, unit: vnd, from: 2023-03-01, doc: hd_2023, quote: "Mức lương chính: 4.700.000 đồng/tháng."}
  - {value: 5000000, unit: vnd, from: 2024-09-01, doc: hd_2023_pl1, quote: "…"}
```

Ngày soát D dùng giá trị có `from` lớn nhất mà ≤ D (phụ lục sau thay thế giá trị trước, như `graph_facts`).

## 5. `gold.yaml` — nhãn đúng theo kỳ (tuan.md §3)

Viết **trước** khi chạy engine trên hồ sơ, chỉ từ văn bản luật; mỗi nhãn có `basis` (pid + câu trích nguyên văn).

```yaml
dossier_id: b1
labeled_by: "…"
expected:
  - rule: content.term/r5
    object: employee=e1            # nhãn nhóm của rule xuyên đối tượng; null với rule trên dữ kiện phẳng
    periods: [{from: 2023-01-01, status: PASS}, {from: 2024-01-01, status: FAIL}]
    basis: {pid: "bo-luat:45/2019/QH14#d20.k2.c", quote: "…"}
```

Test soát ở từng `from` (và ngày trước `from` kế tiếp), ở cả Reference và Network; ngoài nhãn gold không được có FAIL.

## 6. `scenario.yaml` — kịch bản demo theo bước (tu.md D4)

```yaml
dossier_id: b4
steps:
  - {do: load, state: b3, review_date: 2023-06-01, say: "Kết quả ban đầu",
     expect: {"content.term/r6@employee=e1": FAIL}}
  - {do: add, state: b4, docs: [hd_sot_2023], say: "Bổ sung HĐ bị sót", expect: {...}}
  - {do: answer, facts: {is_elderly_employee: true}, say: "…", expect: {...}}
  - {do: set_review_date, value: 2026-01-15, say: "Đổi ngày soát", expect: {...}}
```

`state` = thư mục hồ sơ lấy bảng đối tượng; bước `add` / `remove` đưa vào phiên phần chênh (đối tượng thêm, bớt, đổi
thuộc tính) giữa trạng thái trước và `state`. `expect`: `"<concept>/<rule>[@<nhóm>]": STATUS` sau bước đó.
Đổi ngày soát hiện dựng phiên mới (phiên chưa có thao tác đổi ngày tăng dần).
