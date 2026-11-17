# Danh mục khái niệm HĐLĐ: đánh giá và thiết kế bổ sung

Ngày: 2026-11-16 · Trạng thái: **bản thiết kế chờ duyệt**. Chưa sửa `concepts.yaml`, `catalog.py`, `engine.py`.
Đối tượng: `src/rag/bridge/concepts.yaml` bản `0.2-draft` (39 khái niệm, 44 rule, 30 slot, 69 neo).
Liên quan: `2026-11-16-contract-pipeline-generalization-design.md` (spec TQH), `2026-11-16-graph-agent-tools-v2-design.md`.

## 1. Kết luận

- **Thiết kế danh mục ổn, không cần làm lại.** Cả 69 neo đều tra được trong đồ thị luật, còn hiệu lực tại 02/01/2025,
  và mọi ngưỡng trong rule khớp nguyên văn luật. Mười nội dung bắt buộc của Điều 21 khoản 1 được phủ đủ.
- **Có 5 chỗ danh mục cho kết quả sai hoặc bỏ sót**, đã xác nhận bằng cách chạy engine thật (§3.2). Hai chỗ sửa
  được ngay trong YAML; hai chỗ cần engine hiểu **ngoại lệ**, thứ mà hiện chỉ là ghi chú trên neo; một chỗ cần thêm
  một dữ kiện mới.
- **Chưa đủ ở đúng một nhóm:** điều khoản mà luật cho phép có giới hạn nhưng không phải nội dung bắt buộc. Hợp đồng
  demo có 4 nhóm điều khoản như vậy không rơi vào khái niệm nào. Đề xuất thêm **4 khái niệm** (§5), đã đọc luật và
  đã chạy thử trên bản sao danh mục.
- **Không thêm** 9 ứng viên khác (§6): hoặc hiếm gặp trong hợp đồng, hoặc chỉ sinh thêm dòng "luật vẫn áp dụng".

## 2. Cách đánh giá

1. Đọc toàn bộ `concepts.yaml`, bộ nạp `catalog.py`, phần đánh giá rule của `engine.py`, prompt gán khái niệm.
2. Tra nguyên văn cả 69 neo qua `LegalGraph.text_at(pid, 2025-01-02)` (đồ thị luật build `51cdbb888d7eca95`, 92 văn
   bản), so từng ngưỡng trong rule với lời văn.
3. Đọc hợp đồng demo, đánh dấu điều khoản không có khái niệm nào chứa.
4. Với mỗi ứng viên khái niệm mới: đọc nguyên văn điều luật trước, rồi mới quyết định (§5, §6).
5. Chạy engine thật với dữ kiện mẫu để xác nhận từng chỗ nghi sai (không kết luận từ việc đọc code).
6. Nạp thử 4 khái niệm mới và 2 bản sửa trên **bản sao** danh mục, chạy engine với dữ kiện mẫu.

Giới hạn: chỉ có một hợp đồng lao động mẫu; nhận định "hay gặp trong hợp đồng" ngoài hợp đồng đó là hiểu biết chung,
chưa đo. Một người rà, chưa có người thứ hai đọc lại. Trạng thái xác minh của mọi phiên bản luật trong đồ thị đang là
`needs_review` (phía đồ thị luật), nên "khớp nguyên văn" nghĩa là khớp với bản đang có trong kho.

## 3. Kết quả đối chiếu với luật

### 3.1 Khớp

| Nhóm | Ngưỡng trong rule | Nguồn đã đọc |
|---|---|---|
| Thời hạn HĐ xác định thời hạn | 36 tháng | BLLĐ Đ20 k1 b |
| Thử việc | 180 / 60 / 30 ngày, 6 ngày làm việc; lương ≥ 85% | Đ25, Đ26 |
| Lương tối thiểu vùng | 3 kỳ × 4 vùng | NĐ 38/2022 Đ3, NĐ 74/2024 Đ3, NĐ 293/2025 Đ3: **khớp cả 12 số** |
| Làm thêm, làm đêm | 150 / 200 / 300%; +30% | Đ98 k1, k2 |
| Khấu trừ lương | ≤ 30% | Đ102 k3 |
| Giờ làm, làm thêm | 8 giờ/ngày, 48 giờ/tuần; 40 giờ/tháng, 200 giờ/năm | Đ105 k1, Đ107 k2 |
| Nghỉ | 24 giờ/tuần; 11 ngày lễ; 12 / 14 / 16 ngày phép; 3 ngày kết hôn | Đ111 k1, Đ112 k1, Đ113 k1, Đ115 k1 |
| Báo trước chấm dứt | 45 / 30 ngày, 3 ngày làm việc | Đ35 k1, Đ36 k2 |
| Thanh toán khi chấm dứt | 14 ngày làm việc | Đ48 k1 |
| Thai sản | 6 tháng | Đ139 k1 |

Hệ quả: dòng chú thích "số do người viết nhớ" ở `wage.minimum_regional` và bốn ghi chú "A chưa đối chiếu nguyên
văn" (Đ168 k1, Đ115 k1, Đ37, Đ62) **bỏ được**: đã đọc trọn bốn điều này, nội dung đúng như rule đang dùng (Đ37 liệt
kê 3 trường hợp NSDLĐ không được đơn phương chấm dứt; Đ62 k1 buộc ký hợp đồng đào tạo nghề; Đ36 k1 là danh sách
đóng từ a đến g). Mục 6.1, 6.2, 6.4 của bản rà 15/11 đã lỗi thời (kho luật khi đó có
35 văn bản, nay 92, gồm đủ các nghị định lương tối thiểu, NĐ 145/2020, TT 10/2020, hai Luật BHXH).

### 3.2 Sai hoặc sót (đã chạy engine xác nhận)

| # | Tình huống | Luật | Engine hiện trả | Loại lỗi |
|---|---|---|---|---|
| E1 | Người quản lý doanh nghiệp, HĐ không xác định thời hạn, báo trước 120 ngày | NĐ 145/2020 Đ7 k2 a: **ít nhất 120 ngày** | `violation` (so với 45 ngày) | báo sai |
| E2 | Giờ làm quy định theo tuần: 10 giờ/ngày, 40 giờ/tuần | BLLĐ Đ105 k2: theo tuần được tới 10 giờ/ngày | `violation` (so với 8 giờ) | báo sai |
| E3 | Thử việc trong HĐ có thời hạn 15 ngày | Đ24 k3: không áp dụng thử việc với HĐ dưới 01 tháng | `ok` | bỏ sót |
| E4 | HĐ ký 01/06/2021, lương 4.000.000, vùng I | NĐ 90/2019 Đ3: 4.420.000 | `needs_facts` (`law_period_not_covered`) | bỏ sót |
| E5 | HĐ xác định thời hạn ký lần thứ 3 | Đ20 k2 c: chỉ được ký thêm 01 lần | không có rule (neo có, ghi "chưa có rule") | bỏ sót |

E1 và E2 có chung nguyên nhân: neo `role: exception` chỉ là ghi chú cho phía đồ thị luật, **engine không đọc**. Tám
neo ngoại lệ hiện có (Đ24 k3, Đ97 k4, Đ105 k2, Đ107 k3, Đ108, Đ35 k2, Đ36 k3, Đ37) đều ở tình trạng này.

Ghi nhận thêm, mức thấp: `leave.personal_paid` chỉ có slot ngày nghỉ kết hôn (luật còn con kết hôn 01 ngày, người
thân mất 03 ngày); `rest.weekly` không biểu diễn được "bình quân 04 ngày/tháng" (Đ111 k1).

## 4. Đánh giá thiết kế lược đồ

### 4.1 Phần ổn, giữ

- Tách ba lớp trường: cho LLM nhận diện (`describe`, `phrasing`, `slots`), cho engine (`rules`), cho đồ thị luật
  (`anchors`, `value_sources`). Mô hình không thấy ngưỡng luật.
- Bốn kiểu rule + `derogation` + `on_silence` biểu diễn được cả 4 khái niệm mới mà **không cần kiểu rule mới** (§5).
- Giá trị theo kỳ (`periods`), chọn theo dữ kiện (`cases`), ba trị T/F/U, bộ nạp báo hết lỗi một lần.
- Tên slot không trùng nhau và không trùng tên dữ kiện (đã kiểm: 30 slot, 0 trùng).

### 4.2 Vấn đề

| # | Vấn đề | Bằng chứng | Mức |
|---|---|---|---|
| S1 | **Ngoại lệ không có trong rule.** Engine chỉ biết ngưỡng chung; ngoại lệ nằm ở `anchors[].role`, không ai đọc. | E1, E2 | cao: báo vi phạm sai |
| S2 | **Dữ kiện tùy chọn bị coi là thiếu.** Rule ngưỡng mà hợp đồng không nêu con số trả `needs_facts`. Riêng slot bool "= false" được vá bằng `_unstated_restriction`. | Lần chạy 14/11: 9 dòng "cần thêm dữ kiện"; thử nghiệm §5: điều khoản điều động không nêu số ngày → `needs_facts` | trung bình: nhiễu, tăng theo số khái niệm |
| S3 | **Slot không có mô tả.** LLM chỉ nhận tên, kiểu, đơn vị (`waives_compulsory_insurance: bool`); chiều đúng/sai của slot bool phải đoán từ tên tiếng Anh. | `tagger.catalog_payload` | trung bình |
| S4 | **Năm trường không được code nào đọc:** `scope`, `phase`, `applies_to`, `counterparty`, `value_sources`. `scope: supporting` (đã định nghĩa trong phần đầu file) không có tác dụng; `holder` chỉ dùng cho cạnh `HOLDER`. | grep toàn `src/rag` | thấp, nhưng gây hiểu nhầm là có lọc |
| S5 | **Từ vựng dữ kiện nằm cứng trong `catalog.py`** (`CONTRACT_FACTS` 8, `USER_FACTS` 8). Thêm rule cần dữ kiện mới là phải sửa code, và dữ kiện không có mô tả hay câu hỏi cho người dùng. | E5 cần `fixed_term_sign_count` | trung bình |
| S6 | **Ngưỡng luật chép tay, không có test nối với lời văn.** Lần này khớp, nhưng chỉ vì có người ngồi đối chiếu. | §3.1 làm thủ công | trung bình |
| S7 | **Điều khoản không thuộc khái niệm nào thì vô hình.** Báo cáo không liệt kê đơn vị nào chưa được gán, nên không biết danh mục thiếu gì. | Phụ lục 1 của demo (3 Điều) không sinh dòng nào | cao với câu hỏi "đủ chưa" |
| S8 | **Mọi quyền mặc định im lặng đều thành một dòng báo cáo** ngang hàng nhau, không có mức ưu tiên. | Demo: 7 quyền ẩn + 6 "có thể có quyền" | thấp hiện nay; chặn việc thêm khái niệm quyền mặc định |

### 4.3 Thay đổi lược đồ đề xuất (tối thiểu)

**C1. `rules[].exceptions` — ngoại lệ là dữ liệu của rule (sửa S1).**

```yaml
exceptions:
  - when: {fact: hours_regime, op: eq, value: theo_tuan}
    law: {max_hours_per_day: {value: 10, unit: hour}}      # tùy chọn: ngưỡng thay thế
    anchor: "bo-luat:45/2019/QH14#d105.k2"
```

Ngữ nghĩa, chỉ xét khi kết quả chính là `FAIL`: kiểm lại `check` với ngưỡng thay thế (không có `law` thì coi ngoại
lệ loại trừ rule). Nếu đạt: `when = T` → `NOT_APPLICABLE` kèm lý do `exception_applies`; `when = U` → `needs_facts`,
hỏi đúng dữ kiện của `when`, kèm neo ngoại lệ; `when = F` → giữ `FAIL`. Kết quả `ok` thì không xét ngoại lệ, nên
không thêm câu hỏi thừa. Bộ nạp kiểm `anchor` phải có trong `anchors` với `role: exception`.

**C2. Khai báo dữ kiện và mô tả slot trong YAML (sửa S2, S3, S5).**

```yaml
facts:
  fixed_term_sign_count: {source: contract, kind: count, unit: count, when_missing: skip,
                          describe: "HĐ xác định thời hạn này là lần ký thứ mấy với cùng NSDLĐ"}
  wage_region: {source: user, kind: enum, options: [I, II, III, IV], when_missing: ask,
                question: "Nơi làm việc thuộc vùng lương tối thiểu nào?"}
slots:
  transfer_notice: {kind: duration, unit: workday, when_missing: skip,
                    describe: "số ngày phải báo trước khi chuyển NLĐ làm việc khác"}
```

`when_missing: skip` → rule trả `PASS/ok` lý do `not_stated`; `ask` → `needs_facts` như hiện nay. Mặc định: slot
`skip`, dữ kiện người dùng `ask`. Thay cho `_unstated_restriction` và cho hai hằng trong `catalog.py`. Khi spec TQH
§4.8 (trạng thái slot `value / defers_to_law / unstated`) được làm thì `skip` là hành vi của `unstated`.

**C3. `scope` có hiệu lực (sửa S4, S8).** `core`: gán, đánh giá, lên báo cáo. `supporting`: được gán và làm cầu sang
luật cho agent, **không** sinh dòng báo cáo. Bỏ `phase` khỏi mô tả hoặc dùng nó để sắp thứ tự trong báo cáo.

**C4. Test nối ngưỡng với lời văn (sửa S6).** Một test chạy khi có đồ thị luật: với mỗi giá trị trong `law` của mọi
rule, con số phải đọc được trong lời văn của ít nhất một neo `basis` (hoặc `source` của kỳ) tại ngày hiệu lực. Đây
là đúng việc đã làm tay ở §3.1; dùng bộ đọc số của spec TQH §4.3.

**C5. Báo cáo độ phủ (sửa S7).** `CheckReport` thêm `unmatched_units`: các đơn vị cấp cao nhất không mang khái niệm
nào (trừ phần mở đầu, chữ ký). Đây là nguồn dữ liệu để quyết định thêm khái niệm về sau, thay cho phỏng đoán.

C1 và C2 cần sửa engine và bộ nạp; C3–C5 là việc nhỏ. Bốn khái niệm mới ở §5 **không phụ thuộc** C1–C5: chạy được
trên lược đồ hiện tại (đã thử), chỉ nhiễu hơn một chút khi chưa có C2.

## 5. Bổ sung đề xuất

### 5.1 Sửa khái niệm hiện có

| Sửa | Nội dung | Cần gì | Đã thử |
|---|---|---|---|
| F1 (E4) | `wage.minimum_regional`: thêm kỳ `2020-01-01`, nguồn NĐ 90/2019: I 4.420.000, II 3.920.000, III 3.430.000, IV 3.070.000 | chỉ YAML | có: 4.000.000 → `violation`, 4.500.000 → `ok` |
| F2 (E3) | `probation.duration` thêm r2 (dưới đây) | chỉ YAML | có: HĐ 15 ngày → `violation`; 12 tháng → `ok`; không xác định thời hạn → không áp dụng |
| F3 (E1) | `termination.employee_unilateral` và `.employer_unilateral`: ngoại lệ `job_level = quan_ly_doanh_nghiep` → báo trước 120 ngày, neo `nghi-dinh:145/2020/NĐ-CP#d7.k2` | C1 | chưa (cần engine) |
| F4 (E2) | `hours.normal`: slot `hours_regime` (`theo_ngay` / `theo_tuan`), ngoại lệ `theo_tuan` → tối đa 10 giờ/ngày | C1 | chưa |
| F5 (E5) | `content.term` thêm r3: HĐ xác định thời hạn, `fixed_term_sign_count ≤ 2`, neo Đ20 k2 c | C2 + bước trích dữ kiện đọc "Ký lần thứ N" | chưa |
| F6 | Bỏ các ghi chú "chưa đối chiếu" đã đối chiếu (§3.1); thêm vào `describe` của `content.protective_equipment` "không gồm thiết bị, công cụ làm việc thông thường" (đề xuất của lần chạy 14/11, chưa làm) | chỉ YAML | — |

```yaml
      - id: r2                       # probation.duration — BLLĐ Đ24 k3
        mode: prohibited
        applicability: {all: [{fact: has_probation, op: eq, value: true},
                              {fact: contract_kind, op: eq, value: xac_dinh_thoi_han}]}
        check: {fact: term_months, op: gte, value: 1, unit: month}
        derogation: mandatory
        on_silence: none
        outcome: {legality: illegal, employee_impact: unfavorable}
```

### 5.2 Bốn khái niệm mới

Tiêu chí "thật sự cần": (a) điều khoản **có trong hợp đồng demo** và hiện không khái niệm nào chứa, (b) luật có
quy định giới hạn cho loại điều khoản đó (đã đọc nguyên văn), (c) không trùng khái niệm đã có.

| Khái niệm | Điều khoản trong demo đang vô chủ | Luật đã đọc |
|---|---|---|
| `appendix.amendment` | Phụ lục 2: "Sửa đổi Điều 2 Hợp đồng lao động về lương căn bản… có hiệu lực từ ngày 01 tháng 07 năm 2025" | BLLĐ Đ22 k2: phụ lục **không được sửa thời hạn** hợp đồng; sửa đổi **phải ghi rõ** nội dung và **thời điểm có hiệu lực**. Đ33 k2 |
| `assignment.transfer` | Đ4: "sẵn sàng chấp nhận mọi sự điều động khi có yêu cầu"; Đ5: "bố trí, điều chuyển công việc", "chuyển tạm thời lao động". Nhãn vàng đang xếp câu đầu vào mục mơ hồ của `hours.overtime_limit` | Đ29: không quá 60 ngày làm việc cộng dồn/năm, quá thì phải có đồng ý bằng văn bản; báo trước ≥ 03 ngày làm việc; lương mới ≥ 85% lương cũ, giữ lương cũ 30 ngày làm việc |
| `liability.damage` | Đ4: "Bồi thường vi phạm vật chất"; Phụ lục 1 Đ2: "bồi thường toàn bộ thiệt hại" | Đ129 k1: sơ suất, thiệt hại ≤ 10 tháng lương tối thiểu vùng thì bồi thường nhiều nhất 03 tháng lương, khấu trừ theo Đ102 k3; Đ129 k2; Đ130 k1: mức bồi thường căn cứ lỗi, thiệt hại thực tế, hoàn cảnh |
| `confidentiality.trade_secret` | Toàn bộ Phụ lục 1 (3 Điều), ràng buộc "5 năm kể từ ngày chấm dứt hợp đồng" | Đ21 k2: được thỏa thuận bằng văn bản về nội dung, thời hạn, quyền lợi, bồi thường; TT 10/2020 Đ4: nội dung thỏa thuận và xử lý vi phạm; Đ125 k2; Đ10 k1 |

Ghi chú trung thực về mức chắc chắn pháp lý:
- `appendix.amendment`: hai rule đều dựa thẳng vào câu chữ của Đ22 k2 → `legality: illegal`.
- `assignment.transfer` r1 (buộc nhận mọi điều động) và `liability.damage` r1 (ấn định bồi thường không theo thiệt
  hại) và `confidentiality.trade_secret` r1 (cam kết không cạnh tranh): luật không cấm bằng một câu rõ ràng, việc
  đánh giá tùy lời văn cụ thể → `legality: unknown`, báo cáo ghi là **cần người xem**, không kết luận trái luật.
  BLLĐ không có điều nào quy định trực tiếp về thỏa thuận không cạnh tranh; neo Đ10 k1 chỉ là căn cứ để xem xét.
- `guidance(Đ21 k2)` của đồ thị luật trả về khoản 1 Điều 1 TT 10/2020 (điều khoản phạm vi), không tìm ra Điều 4, nên
  Điều 4 được neo trực tiếp dù phần đầu file dặn "không cần neo văn bản hướng dẫn".

Kết quả chạy thử trên bản sao danh mục (43 khái niệm nạp được, engine hiện tại):

| Dữ kiện mẫu | Kết quả |
|---|---|
| Phụ lục không đổi thời hạn, có ghi ngày hiệu lực (như Phụ lục 2 của demo) | r1 `ok`, r2 `ok` |
| Phụ lục đổi thời hạn hợp đồng | r1 `violation` (illegal) |
| Phụ lục sửa đổi không ghi ngày hiệu lực | r2 `violation` (illegal) |
| Hợp đồng không có phụ lục sửa đổi | không báo gì |
| "Chấp nhận mọi sự điều động" | r1 `violation` (unknown: cần người xem); r2 `needs_facts` ← nhiễu, hết khi có C2 |
| Điều động 90 ngày làm việc/năm | r2 `violation` |
| Điều động 60 ngày, báo trước 5 ngày, lương 100% | `ok` |
| Bồi thường "theo quy định của pháp luật" (như demo) | `ok` |
| Bồi thường ấn định sẵn không theo thiệt hại | r1 `violation` (unknown) |
| Bảo mật "5 năm" sau khi chấm dứt (như demo) | `ok`; slot chuẩn hóa thành 60 tháng |
| Cam kết không làm việc cho đối thủ | r1 `violation` (unknown) |

YAML đầy đủ (đúng bản đã chạy thử; chèn trước mục ĐỀ XUẤT của `concepts.yaml`):

```yaml
  # ───────────── 8. BỔ SUNG 2026-11-16: phụ lục, điều chuyển, bồi thường, bảo mật ─────────────

  - id: appendix.amendment
    label: Phụ lục sửa đổi, bổ sung hợp đồng
    scope: core
    phase: P0
    holder: NLD
    counterparty: NSDLD
    applies_to: [NLD]
    describe: "Điều khoản của phụ lục hoặc văn bản sửa đổi làm thay đổi một điều, khoản của hợp đồng lao động (lương, công việc, địa điểm, thời hạn). Không gồm phụ lục chỉ quy định chi tiết mà không đổi nội dung hợp đồng."
    phrasing: ["sửa đổi Điều", "bổ sung Điều", "được điều chỉnh", "nội dung thay đổi", "gia hạn hợp đồng"]
    slots:
      amendment_changes_term: {kind: bool, unit: null}            # phụ lục đổi thời hạn / ngày kết thúc / gia hạn hợp đồng
      amendment_states_effective_date: {kind: bool, unit: null}   # có ghi thời điểm nội dung sửa đổi có hiệu lực
    anchors:
      - {pid: "bo-luat:45/2019/QH14#d22.k2", role: basis}
      - {pid: "bo-luat:45/2019/QH14#d22.k1", role: basis}
      - {pid: "bo-luat:45/2019/QH14#d33.k2", role: basis, note: "sửa đổi bằng phụ lục hoặc hợp đồng mới"}
    rules:
      - {id: r1, mode: prohibited, derogation: mandatory, on_silence: none,
         check: {fact: amendment_changes_term, op: eq, value: false},
         outcome: {legality: illegal, employee_impact: unfavorable}}
      - {id: r2, mode: required, derogation: mandatory, on_silence: none,
         check: {fact: amendment_states_effective_date, op: eq, value: true},
         outcome: {legality: illegal, employee_impact: neutral}}

  - id: assignment.transfer
    label: Chuyển người lao động làm công việc khác so với hợp đồng
    scope: core
    phase: P0
    holder: NSDLD
    counterparty: NLD
    applies_to: [NLD]
    describe: "Điều khoản cho NSDLĐ quyền điều động, điều chuyển, chuyển tạm thời NLĐ sang công việc hoặc vị trí khác với hợp đồng; hoặc buộc NLĐ chấp nhận mọi sự điều động."
    phrasing: ["điều động", "điều chuyển công việc", "chuyển tạm thời", "làm công việc khác", "chấp nhận sự phân công"]
    not_about:
      - {text: "làm thêm giờ, tăng ca theo yêu cầu", see: hours.overtime_limit}
      - {text: "thực hiện công việc theo chức danh dưới sự phân công của cấp trên, trong phạm vi công việc đã thỏa thuận", see: content.job_and_workplace}
    slots:
      transfer_obligation_unlimited: {kind: bool, unit: null}     # buộc nhận mọi điều động, không giới hạn thời gian / lý do
      transfer_max_workdays_per_year: {kind: duration, unit: workday}
      transfer_notice: {kind: duration, unit: workday}
      transfer_pay_pct: {kind: percent, unit: percent}
    anchors:
      - {pid: "bo-luat:45/2019/QH14#d29.k1", role: basis, note: "căn cứ chuyển; quá 60 ngày làm việc/năm phải có đồng ý bằng văn bản"}
      - {pid: "bo-luat:45/2019/QH14#d29.k2", role: basis, note: "báo trước ít nhất 03 ngày làm việc"}
      - {pid: "bo-luat:45/2019/QH14#d29.k3", role: basis, note: "giữ lương cũ 30 ngày làm việc; lương mới ít nhất 85%"}
      - {pid: "bo-luat:45/2019/QH14#d29.k4", role: basis, note: "không đồng ý mà phải ngừng việc: lương ngừng việc Điều 99"}
    rules:
      - {id: r1, mode: prohibited, derogation: mandatory, on_silence: none,
         check: {fact: transfer_obligation_unlimited, op: eq, value: false},
         outcome: {legality: unknown, employee_impact: unfavorable}}
      - id: r2
        mode: threshold
        law:
          max_transfer_days: {value: 60, unit: workday}
          min_transfer_notice: {value: 3, unit: workday}
          min_transfer_pay: {value: 85, unit: percent}
        check:
          all:
            - {fact: transfer_max_workdays_per_year, op: lte, law: max_transfer_days}
            - {fact: transfer_notice,                op: gte, law: min_transfer_notice}
            - {fact: transfer_pay_pct,               op: gte, law: min_transfer_pay}
        derogation: floor
        on_silence: none
        outcome: {legality: illegal, employee_impact: unfavorable}

  - id: liability.damage
    label: Bồi thường thiệt hại, trách nhiệm vật chất
    scope: core
    phase: P0
    holder: NSDLD
    counterparty: NLD
    applies_to: [NLD]
    describe: "Điều khoản buộc NLĐ bồi thường khi làm hư hỏng, làm mất tài sản hoặc gây thiệt hại cho NSDLĐ: căn cứ, mức bồi thường, cách thu hồi."
    phrasing: ["bồi thường thiệt hại", "trách nhiệm vật chất", "bồi thường toàn bộ", "làm hư hỏng", "làm mất tài sản"]
    not_about:
      - {text: "phạt tiền, trừ lương khi vi phạm nội quy, đi muộn", see: prohibit.fine_instead_of_discipline}
      - {text: "hoàn trả chi phí đào tạo khi nghỉ việc", see: training.cost_repayment}
    slots:
      fixed_compensation_regardless_of_damage: {kind: bool, unit: null}   # ấn định sẵn số tiền, không phụ thuộc lỗi và thiệt hại thực tế
    anchors:
      - {pid: "bo-luat:45/2019/QH14#d129.k1", role: basis, note: "sơ suất, thiệt hại không quá 10 tháng lương tối thiểu vùng: bồi thường nhiều nhất 03 tháng lương"}
      - {pid: "bo-luat:45/2019/QH14#d129.k2", role: basis, note: "làm mất tài sản; bất khả kháng thì không phải bồi thường"}
      - {pid: "bo-luat:45/2019/QH14#d130.k1", role: basis, note: "mức bồi thường căn cứ lỗi, thiệt hại thực tế, hoàn cảnh"}
      - {pid: "bo-luat:45/2019/QH14#d102.k3", role: basis, note: "khấu trừ không quá 30% lương tháng; rule ở wage.deduction_limit"}
    rules:
      - {id: r1, mode: prohibited, derogation: mandatory, on_silence: none,
         check: {fact: fixed_compensation_regardless_of_damage, op: eq, value: false},
         outcome: {legality: unknown, employee_impact: unfavorable}}

  - id: confidentiality.trade_secret
    label: Bảo vệ bí mật kinh doanh, bí mật công nghệ
    scope: core
    phase: P0
    holder: NSDLD
    counterparty: NLD
    applies_to: [NLD]
    describe: "Thỏa thuận bảo mật: danh mục thông tin phải giữ bí mật, thời hạn bảo mật, bồi thường khi vi phạm; kể cả cam kết không làm việc cho đối thủ hoặc không kinh doanh cạnh tranh sau khi nghỉ việc."
    phrasing: ["bí mật kinh doanh", "bảo mật thông tin", "không tiết lộ", "không làm việc cho đối thủ", "sau khi chấm dứt hợp đồng"]
    not_about:
      - {text: "bồi thường khi làm hư hỏng, làm mất tài sản", see: liability.damage}
    slots:
      confidentiality_after_termination: {kind: duration, unit: month}
      non_compete_after_termination: {kind: bool, unit: null}
    anchors:
      - {pid: "bo-luat:45/2019/QH14#d21.k2", role: basis}
      - {pid: "thong-tu:10/2020/TT-BLĐTBXH#d4", role: basis, note: "nội dung thỏa thuận và xử lý vi phạm; guidance() không tự tìm ra điều này"}
      - {pid: "bo-luat:45/2019/QH14#d125.k2", role: basis, note: "tiết lộ bí mật là căn cứ sa thải khi nội quy có quy định"}
      - {pid: "bo-luat:45/2019/QH14#d10.k1", role: exception, note: "quyền tự do làm việc: căn cứ xem xét thỏa thuận không cạnh tranh"}
    rules:
      - {id: r1, mode: prohibited, derogation: mandatory, on_silence: none,
         check: {fact: non_compete_after_termination, op: eq, value: false},
         outcome: {legality: unknown, employee_impact: unfavorable}}
```

**Liên hệ với đồ thị.** `appendix.amendment` là khái niệm duy nhất có thể kiểm chéo bằng cấu trúc: cạnh `AMENDS` có
`valid_from` rỗng thì `amendment_states_effective_date` phải là `false`; cạnh `AMENDS` trỏ vào điều khoản mang
`content.term` thì `amendment_changes_term` phải là `true`. Khi spec TQH §4.6 (quan hệ có kiểu) xong, hai slot này
nên được **suy ra từ đồ thị** thay cho hỏi LLM; trước đó dùng slot và ghi cảnh báo khi hai nguồn lệch nhau.

**Cần cập nhật kèm:** `tests/fixtures/bridge/demo_gold.yaml` (thêm 4 khái niệm có mặt: Phụ lục 2 → `appendix.amendment`;
Đ4, Đ5 → `assignment.transfer`; Đ4, Phụ lục 1 Đ2 → `liability.damage`; Phụ lục 1 → `confidentiality.trade_secret`,
slot 60 tháng; bỏ dòng mơ hồ `hours.overtime_limit`), `engine_cases.yaml`, và đo lại P/R gán khái niệm vì danh mục
dài thêm 4 mục trong prompt.

## 6. Ứng viên đã đọc luật và quyết định không thêm đợt này

| Ứng viên | Luật | Lý do không thêm |
|---|---|---|
| Lương ngừng việc | Đ99 | Demo chỉ nhắc "ngừng việc… theo quy định của Pháp luật" trong một câu gộp. Là quyền mặc định; thêm vào chỉ sinh dòng "luật vẫn áp dụng" (S8). Xét lại dưới dạng `scope: supporting` khi có C3 và khi bộ câu hỏi agent cần |
| Trợ cấp mất việc làm | Đ47 | Quyền mặc định, hiếm khi được ghi trong hợp đồng |
| Hệ quả chấm dứt trái pháp luật | Đ39–41 | Không phải nội dung hợp đồng; là hậu quả pháp lý |
| Nghỉ giữa giờ, nghỉ chuyển ca | Đ109, Đ110 | Demo có lịch làm việc nghỉ trưa 90 phút, không có gì để soát. Ngưỡng rõ (30 / 45 phút, 12 giờ) nên dễ thêm sau nếu gặp hợp đồng làm ca |
| Tạm hoãn hợp đồng | Đ30 | Danh sách trường hợp, không có ngưỡng để soát |
| Buộc làm việc để trả nợ | Đ17 k3 | Hoàn thiện Điều 17 nhưng hiếm gặp trong hợp đồng viết |
| Khoản tiền phải trả khi NLĐ nghỉ việc | Đ40 k2 | Đáng làm, nhưng là **thêm slot** cho `termination.employee_unilateral` chứ không phải khái niệm mới; demo không có điều khoản này. Làm khi gặp hợp đồng thật có "nghỉ trước hạn bồi thường N tháng lương" |
| Căn cứ sa thải | Đ125 | Gần trùng `termination.employer_unilateral`; phần lớn dẫn về nội quy lao động, không soát được từ hợp đồng |
| Cấm làm việc cho nơi khác trong thời gian hợp đồng | Đ19 k1 | Luật cho giao kết nhiều hợp đồng nhưng không nói rõ về thỏa thuận độc quyền; không có ngưỡng |

Quy tắc cho các đợt sau: thêm khái niệm khi báo cáo độ phủ (C5) cho thấy cùng một loại điều khoản vô chủ ở **nhiều
hợp đồng**, không thêm theo danh sách điều luật.

## 7. Thứ tự làm

1. **Chỉ YAML, làm ngay được:** F1, F2, F6; bốn khái niệm mới; cập nhật nhãn vàng và test; đo lại gán khái niệm.
2. **C5** (báo cáo độ phủ) và **C3** (`scope` có hiệu lực): nhỏ, cho số liệu để quyết các đợt sau.
3. **C1** (ngoại lệ) rồi F3, F4: sửa hai chỗ báo vi phạm sai.
4. **C2** (khai báo dữ kiện, `when_missing`, mô tả slot) rồi F5: giảm nhiễu `needs_facts`, bỏ `_unstated_restriction`.
5. **C4** (test nối ngưỡng với lời văn): sau khi có bộ đọc số của spec TQH.

## 8. Câu hỏi cần người dùng quyết

- **Q1.** Ba rule `legality: unknown` (điều động vô hạn, bồi thường ấn định, không cạnh tranh): báo cáo ghi "cần
  người xem" như `termination.employee_unilateral` hiện làm (đề xuất), hay bỏ hẳn rule và chỉ giữ khái niệm làm cầu
  sang luật?
- **Q2.** Neo trực tiếp TT 10/2020 Đ4 trái với lời dặn "không neo văn bản hướng dẫn" ở đầu file. Chấp nhận ngoại lệ
  này, hay báo Huy sửa `guidance()` để tìm được Điều 4 rồi bỏ neo?
- **Q3.** Phần đầu file ghi Huy là người chốt `anchors`. Bốn khái niệm mới có 15 neo do bản này đề xuất: đưa thẳng
  vào danh sách chính, hay vào mục `proposals` cho Huy rà trước?
- **Q4.** C1 và C2 đổi engine và bộ nạp. Làm trong đợt này, hay chỉ làm bước 1–2 trước?

## 9. Lựa chọn của người viết (chưa được xác nhận)

- Tiêu chí "có trong hợp đồng demo và đang vô chủ" để chọn khái niệm mới: chặt, có thể bỏ lọt điều khoản phổ biến mà
  demo không có (ví dụ phạt khi nghỉ việc trước hạn).
- Gộp ba ngưỡng của Điều 29 vào một rule để chỉ sinh một dòng khi thiếu số liệu.
- `liability.damage` không có rule ngưỡng "03 tháng lương": điều kiện áp dụng (sơ suất, thiệt hại nhỏ) không đọc
  được từ hợp đồng; lời văn luật đến với agent qua neo.
- Slot bool đặt tên theo hành vi cần soát và kiểm `= false`, theo đúng quy ước các khái niệm `prohibit.*` hiện có.
