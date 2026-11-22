# Phân công W04 — Tùng (nhận phần của Tuấn): phân tích luật thành bản liệt kê rule + nhãn gold

> Đường dẫn `src/`, `docs/`, `tests/` tính từ `app/team-4.2/`.
> Thiết kế engine (đọc §5 "Ngữ nghĩa"): `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md`.
> Người quyết định: **Tùng**. Chỗ nào file này không nói rõ → hỏi Tùng, không tự chọn.

## 0. Vai trò trong 5 dòng

> **Định hướng W04 (bản 3, 23/11): phủ rộng nhiều loại hợp đồng.** Ba miền ngang hàng: lao động (T1), vay (T3), thuê
> nhà (**T6**), cùng gói cha dân sự chung (T2). Danh sách `kind` (T4) phải đúng cho cả ba miền.

- Tùng viết engine và chuyển rule thành YAML. Tuấn là người **đọc luật** và ghi lại rule ở dạng có cấu trúc, đủ để
  Tùng chuyển thành YAML **mà không phải đọc lại văn bản luật**.
- Tuấn **không viết code engine, không viết YAML pack**.
- Tuấn gắn **nhãn gold** (kết quả đúng theo luật) cho các hồ sơ Tú soạn.
- Nguồn sự thật duy nhất là **văn bản luật gốc** trong kho (hoặc văn bản hợp nhất), không phải trí nhớ, blog, hay
  câu trả lời của LLM.
- Khi trình bày: Tuấn bảo vệ "vì sao rule này đúng luật, ngoại lệ là gì, vì sao nhãn gold là vậy".

## 1. Việc chi tiết (theo thứ tự)

### T1 — Lao động: Điều 20, 22, 25 BLLĐ 45/2019/QH14 (xong ngày 2)

Phục vụ bộ hồ sơ B (nhiều hợp đồng của một NLĐ) và bộ A (phụ lục). Cần trả lời rõ, có trích nguyên văn:
- Đ20.2: hết hạn mà NLĐ vẫn làm việc → nghĩa vụ ký mới trong bao lâu; không ký thì hệ quả gì; **giới hạn số lần ký
  HĐ xác định thời hạn và danh sách đầy đủ các ngoại lệ** (điều/khoản dẫn chiếu tới: NLĐ cao tuổi, người nước ngoài,
  cán bộ công đoàn, giám đốc DN vốn nhà nước… — kiểm từng cái trong văn bản).
- Đ22.2: phụ lục sửa thời hạn hợp đồng — được sửa mấy lần, có được đổi loại hợp đồng không.
- Đ25: thử việc — "chỉ được thử việc một lần đối với một công việc": "một công việc" xác định bằng dữ kiện gì trong
  hợp đồng (chức danh? mô tả công việc?).
- Văn bản hướng dẫn (NĐ 145/2020) có sửa / làm rõ điều nào ở trên không.

### T2 — BLDS 91/2015/QH13: phần chung về hợp đồng (xong ngày 3)

Chỉ lấy những quy định **kiểm được trên văn bản hợp đồng**: hình thức, hợp đồng theo mẫu / điều kiện giao dịch chung,
phạt vi phạm, bồi thường, đơn phương chấm dứt / hủy bỏ, điều khoản vô hiệu. Với mỗi quy định ghi rõ: bắt buộc
(mandatory), mặc định ("trừ trường hợp có thỏa thuận khác" → default), hay mức trần/sàn.

### T3 — BLDS: hợp đồng vay tài sản, Điều 463–471 (xong ngày 3)

Lãi suất trần, lãi khi vay không thỏa thuận rõ lãi, lãi chậm trả, lãi trên nợ gốc quá hạn, trả nợ trước hạn (có kỳ
hạn / không kỳ hạn, có lãi / không lãi), quyền đòi lại tài sản. Ghi rõ quan hệ với luật chuyên ngành (Luật các TCTD)
— **chỉ ghi nhận là ngoại lệ, không phân tích sâu** trong W04.

### T4 — Đề xuất danh sách `kind` (ngày 1–2; bản 3: kiểm trên ba miền)

Gom concept của **mọi gói** (`packs/labor`, `packs/civil_general`, `packs/civil_loan`, `packs/civil_lease`) và các mục
trong bản liệt kê T1–T3, T6 theo **dạng pháp lý** (payment, time_limit, notice, rate_cap, termination, penalty,
void_clause, form_requirement, …), mỗi kind có slot chung (tên, kiểu, đơn vị). Bắt đầu từ 39 concept lao động là được,
nhưng **danh sách chỉ xong khi mỗi kind dùng chung có concept của ít nhất hai miền**; kind chỉ có ở một miền ghi rõ là
kind riêng của miền đó. Concept không vừa kind nào → liệt kê riêng kèm lý do, đừng ép. Mục bản liệt kê ghi
`kind: none` phải có lý do trong `open_questions`.

### T6 — Thuê nhà ở: BLDS Đ472–482 + Luật Nhà ở 27/2023/QH15 Đ163–173 (bản 3, xong ngày 3)

`docs/rule_inventory/civil_lease.yaml`. Chỉ lấy quy định kiểm được trên văn bản hợp đồng: thời hạn thuê (Đ474 BLDS,
Đ170 LNO), giá thuê và điều chỉnh giá (Đ473 BLDS, Đ170 LNO), cho thuê lại (Đ475 BLDS, Đ170 LNO), trả tiền thuê (Đ481),
đơn phương chấm dứt và báo trước (Đ172 LNO), các trường hợp chấm dứt (Đ171 LNO), hình thức / công chứng (Đ163–164 LNO,
nối với `civil.form_required_by_law`), quyền tiếp tục thuê (Đ173 LNO). Ghi rõ quan hệ luật chung (BLDS) – luật chuyên
ngành (Luật Nhà ở): rule nào của LNO là **ngoại lệ** của rule BLDS (dùng `exceptions`).

### T5 — Nhãn gold cho hồ sơ của Tú (ngày 3–4)

Với mỗi hồ sơ trong `tests/fixtures/rete/<dossier_id>/` (lao động a1, b1–b5; vay `loan/`; thuê nhà `lease/`, r1),
điền `gold.yaml` (định dạng §3). Mỗi nhãn có `basis` (pid +
trích nguyên văn). Không chắc → `status: UNKNOWN` + ghi lý do, **không đoán**.

## 2. Định dạng bản liệt kê rule (chốt ngày 1 với Tùng)

File: `docs/rule_inventory/<pack>.yaml` (`labor_w04.yaml`, `civil_general.yaml`, `civil_loan.yaml`,
`civil_lease.yaml`).

```yaml
- id: civil_loan.interest_cap                 # đề xuất <pack>.<tên ngắn>; Tùng có thể đổi
  source:
    pid: "bo-luat:91/2015/QH13#d468.k1"
    quote: "<chép NGUYÊN VĂN câu luật đặt ra quy định>"
  type: threshold          # threshold | required | prohibited | default | derived | exception
  kind: rate_cap           # theo danh sách T4
  derogation: mandatory    # mandatory | floor | ceiling | default (được thỏa thuận khác)
  applies_when: "Hợp đồng vay có thỏa thuận lãi suất"            # lời
  facts_needed:
    - {name: interest_rate, kind: percent, unit: percent_per_year, from: contract, note: "quy đổi nếu ghi theo tháng"}
    - {name: lender_is_credit_institution, kind: bool, from: user}
  threshold: {value: 20, unit: percent_per_year}
  exceptions:
    - pid: "bo-luat:91/2015/QH13#d468.k1"
      quote: "<câu 'trừ trường hợp luật khác có liên quan quy định khác'>"
      condition: "Bên cho vay là tổ chức tín dụng"
  conclusion: "Phần lãi vượt 20%/năm không có hiệu lực"        # hệ quả pháp lý, lời
  on_silence: none         # hợp đồng không nói gì thì: missing_content | hidden_right | default_applies | none
  derived_from: []         # nếu là kết luận trung gian: dùng kết luận nào
  examples:                # ít nhất 1 PASS, 1 FAIL, 1 UNKNOWN
    - {facts: {interest_rate: 18, lender_is_credit_institution: false}, expected: PASS}
    - {facts: {interest_rate: 24, lender_is_credit_institution: false}, expected: FAIL}
    - {facts: {interest_rate: 24}, expected: UNKNOWN, why: "chưa biết bên cho vay có phải TCTD"}
  open_questions: []
```

Quy tắc ghi:
- `quote` chép đúng từng chữ từ văn bản trong kho. Không diễn giải trong `quote`.
- Mỗi ngoại lệ là một mục riêng có pid riêng — ngoại lệ là phần quan trọng nhất cho engine mới.
- Kết luận trung gian (vd. "HĐ trở thành không xác định thời hạn") ghi `type: derived` thành một mục riêng, rule nào
  dùng nó thì ghi id vào `derived_from`.

## 3. Định dạng gold (chốt ngày 1 với Tùng + Tú)

`tests/fixtures/rete/<dossier_id>/gold.yaml`:

```yaml
dossier_id: a1
labeled_by: Tuấn
expected:
  - rule: wage.minimum_regional/r1          # <concept_id>/<rule_id>; dùng id trong bản liệt kê nếu chưa có YAML
    object: hd_2023                          # doc_id trong dossier.yaml
    periods:                                 # kết quả theo khoảng thời gian (ngày soát rơi vào khoảng nào)
      - {from: 2023-03-01, to: 2024-06-30, status: PASS}
      - {from: 2024-07-01, to: 2024-08-31, status: FAIL, finding: violation}
      - {from: 2024-09-01, status: PASS}
    basis: {pid: "nghi-dinh:74/2024/NĐ-CP#d3", quote: "<nguyên văn>"}
    note: ""
```

## 4. Không được làm

- Không dùng LLM để viết `quote`, kết luận pháp lý hay nhãn gold. (Được dùng để tìm vị trí điều luật, rồi đọc văn bản
  gốc.)
- Không sửa `concepts.yaml`, `pack.yaml`, code. Muốn thêm concept → ghi vào bản liệt kê, Tùng quyết.
- Không mở rộng sang luật khác ngoài T1–T3, T6 khi chưa xong và chưa hỏi Tùng.
- Không bỏ trống `exceptions` vì "chắc không có" — phải ghi `exceptions: []` sau khi đã đọc hết điều luật và các điều
  dẫn chiếu.

## 5. Nghiệm thu

| # | Tiêu chí |
|---|---|
| T1–T3 | Tùng chuyển được 100% mục thành YAML mà không phải mở văn bản luật; Huy xác nhận pid giải được |
| T4 | Mọi concept của cả ba miền có kind hoặc nằm trong danh sách "không vừa" kèm lý do; kind dùng chung có concept của ≥2 miền |
| T6 | Như T1–T3, cho `civil_lease.yaml`; mỗi quy định Luật Nhà ở đè lên BLDS ghi thành `exceptions` |
| T5 | Mỗi nhãn có basis; nhãn khớp với kết quả engine, chỗ không khớp được Tuấn + Tùng xem và ghi kết luận (lỗi engine hay lỗi nhãn) |

## 6. Mốc kiểm tra với Tùng

| Ngày | Mốc |
|---|---|
| 1 (23/11) | Chốt định dạng §2, §3; nộp bản nháp T4 |
| 2 | Nộp T1 (lao động) — Tùng review 30 phút cùng Tuấn |
| 3 | Nộp T2, T3, T6 |
| 4 | Nộp T5 cho bộ A, B và hợp đồng vay |
| 5 | Đối chiếu nhãn với kết quả engine; chuẩn bị phần trình bày |

## 7. Câu hỏi mở (ghi vào đây, Tùng trả lời)

-
