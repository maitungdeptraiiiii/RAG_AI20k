# W04 — Hạn chế, lỗi và điểm nhỏ theo từng bước (rule engine)

Cập nhật từ giai đoạn 3 trở đi: mỗi giai đoạn mới thêm một mục vào file này (lỗi đã sửa, lỗi còn tồn đọng, hạn chế, quyết định
có chi phí nếu sai). Nhánh `feat/team-4.2/w04-rules-engine`, chưa merge. Trạng thái: **Đã sửa** / **Còn** / **Có chủ ý**.

## Giai đoạn 1 — tách lõi, Reference, gói `labor` (plan `2026-11-22-rule-engine-phase1.md`)

| # | Mục | Trạng thái |
|---|---|---|
| 1.1 | Đơn vị gốc không có dòng quy đổi riêng làm âm thầm tắt so sánh khác đơn vị (reviewer, Important). Loader nay tự thêm `(gốc, 1)` và báo lỗi nếu gốc có hệ số khác 1 (commit 7d8fc9b) | Đã sửa |
| 1.2 | Khi lập kế hoạch tin sai "≥5 rule dùng `contract_kind`" (thực tế 5 lá / 3 rule): test đổi, ghi `Ruling` | Có chủ ý |
| 1.3 | Từng ghi nhầm "Task 8 complete" vào sổ sau lệnh `git add` hỏng: đã xóa dòng, commit lại cho đúng | Đã sửa |
| 1.4 | Bộ nạp ném ngoại lệ thô (`AttributeError`, `TypeError`) khi YAML sai hình dạng ở `concepts.yaml` / `pack.yaml` (phần `derived` đã được sửa ở giai đoạn 3) | Còn |
| 1.5 | `version` trong `pack.yaml` không vào `Catalog.version` | Còn |
| 1.6 | Gói con không dùng được role của gói cha và `not_about.see` trỏ khái niệm của gói cha | Còn |
| 1.7 | `ReferenceSession` chia sẻ đối tượng kết quả và dict `evidence` giữa các lần gọi | Còn |
| 1.8 | Docstring nói nạp lười gói labor, nhưng `bridge/catalog.py` nạp ngay khi import | Còn |
| 1.9 | Test `test_evaluate_all_matches_old_engine_on_whole_catalog` giờ chỉ so engine với chính nó (engine cũ đã thành lớp vỏ); golden (2571 ca) mới là bảo vệ thật | Có chủ ý |
| 1.10 | Thông báo `load_packs` có chỗ trùng hoặc gây hiểu lầm | Còn |
| 1.11 | `Rule` dựng tay (không qua loader) không tự suy `unstated_false` | Còn |

## Giai đoạn 2 — mạng điều kiện tăng dần `NetworkEvaluator`

| # | Mục | Trạng thái |
|---|---|---|
| 2.1 | `by` khai trong `cases[*].law` không được `referenced()` / bộ nạp theo dõi (reviewer, Important; commit deda5dc) | Đã sửa |
| 2.2 | `Fact.__eq__` coi `1 == True == 1.0` nên `update` bỏ qua thay đổi kiểu (ca `wage_region`); sửa bằng `_same` so cả kiểu (ee883e6) | Đã sửa |
| 2.3 | `cond_key` (`json.dumps`) crash khi điều kiện có giá trị ngày YAML; nay ghi ngày kèm tên kiểu (bd07d12) | Đã sửa |
| 2.4 | `make_evaluator` mặc định `reference` trong khi `default_kind()` mặc định `network`; chú thích cũ ghi "network chưa có" (675b9fc) | Đã sửa |
| 2.5 | `make_tools` chọn evaluator chỉ theo biến môi trường, không có tham số | Còn |
| 2.6 | Mạng biên dịch lại mỗi lần gọi `check_contract`, không cache theo spec §7. Đo thực tế 0.33 ms (50 rule: 0.51 ms) nên chưa đáng kể | Còn |
| 2.7 | `tools.check_concept` dựng phiên cho cả catalog rồi lọc theo concept | Còn |
| 2.8 | Số đo tốc độ: Reference 0.46 ms, Network 0.003 ms cho một lần `update`, nhưng đều dưới 1 ms vì chỉ 44–50 rule. **Chưa chứng minh được "nhiều rule vẫn chịu được"**: cần benchmark giai đoạn 6 (hàng nghìn rule, hai trục) | Còn (giai đoạn 6) |

## Giai đoạn 3 — dữ kiện suy ra và ngoại lệ giữa rule (plan `2026-11-23-rule-engine-phase3-derived-exceptions.md`)

**Lỗi do review độc lập tìm ra, đã sửa** (mỗi lỗi có test đỏ trước):

| # | Mục | Trạng thái |
|---|---|---|
| 3.1 | Nhóm anh em có một ngoại lệ cho giá trị và một ngoại lệ `UNKNOWN` ra giá trị → bớt dữ kiện có thể thành `FAIL`. Nay `UNKNOWN`. **Lệch chữ spec §5.3 bước 1, chọn bất biến §10** | Đã sửa (có chủ ý) |
| 3.2 | Trả lời `worked_after_expiry_days = 45` không kèm đơn vị làm `r4` kẹt `UNKNOWN` mà `missing_facts` rỗng. Thêm `user_fact_units` | Đã sửa |
| 3.3 | Bộ nạp không từ chối dữ kiện suy ra trùng `document_facts` / `user_facts` của gói khác | Đã sửa |
| 3.4 | `content.term/r3` ra `PASS` khi điều khoản thời hạn không được nhận ra dù biết đã ký HĐ thứ ba. Thêm cờ rule `standalone: true` | Đã sửa |
| 3.5 | `derived` sai hình dạng hoặc đơn vị lạ trong `when` làm crash thay vì `CatalogError` | Đã sửa |
| 3.6 | `NetworkSession` không ghi kết quả mới khi `==` coi bằng nhau (`True` vs `1.0`), kiểu giá trị trong `facts_used` bị cũ (lộ ra khi so bằng JSON) | Đã sửa |

**Điểm nhỏ còn tồn đọng:**

| # | Mục | Trạng thái |
|---|---|---|
| 3.7 | Dữ kiện suy ra `UNKNOWN` chỉ vì đầu vào `CONFLICT` ra `needs_facts` với `missing_facts` rỗng, đúng ra phải là `conflict` (`semantics.py` chỉ xét `CONFLICT` trực tiếp trong `check`) | Còn |
| 3.8 | `value: null` trong định nghĩa dữ kiện suy ra được chấp nhận thành `Fact(None)` "có mặt" | Còn |
| 3.9 | Bốn rule `r3_*` luôn ra `PASS/ok` khi điều khoản thời hạn có mặt (kể cả applicability chưa biết): mỗi HĐ xác định thời hạn sinh bốn dòng "ok", có thể gây nhiễu UI và báo cáo | Còn |
| 3.10 | Hàng U của §5.4 chỉ thêm dữ kiện của ngoại lệ vào `missing_facts` khi rule gốc là `FAIL`; gốc `UNKNOWN` thì phải hỏi thêm một vòng | Có chủ ý (đúng spec) |
| 3.11 | Định nghĩa `from` lấy đơn vị theo nguồn, bỏ qua `unit` đã khai của dữ kiện suy ra, không kiểm hai đơn vị khớp nhau | Còn |
| 3.12 | Nhãn dữ kiện `worked_after_expiry_days` chưa nói ngày hết hạn có tính là ngày 0 hay không (ca biên đúng 30 ngày phụ thuộc cách đếm) | Còn |

**Hạn chế và quyết định có chi phí nếu sai:**

| # | Mục | Chi phí nếu sai |
|---|---|---|
| 3.13 | `evaluate_concept` (từng concept, lớp tương thích) chỉ áp dụng ngoại lệ giữa rule cùng concept; ngoại lệ chéo concept chỉ có ở `evaluate_all` và phiên. Rule labor hiện đặt ngoại lệ cùng concept | Gói dân sự giai đoạn 5 có ngoại lệ chéo concept sẽ không có hiệu lực nếu gọi `evaluate_concept` |
| 3.14 | `r3` dùng `contract_kind` (loại ghi trong văn bản), không dùng `contract_kind_effective` | Hợp đồng đã tự chuyển loại mà vẫn ký thêm HĐ xác định thời hạn không bị `r3` bắt; cần người làm pháp lý xem |
| 3.15 | Điều 177.4 là nghĩa vụ "gia hạn đến hết nhiệm kỳ", mô hình hóa thành ngoại lệ theo chữ cuối Điều 20.2.c | Phần nội dung nghĩa vụ không được xét |
| 3.16 | `fixed_term_contract_count`, `worked_after_expiry_days`, `new_contract_signed` và 4 dữ kiện ngoại lệ do người dùng cung cấp; chưa có đường trích từ hồ sơ. Hạn chế đến giai đoạn 7b | Rule chạy nhưng cần người dùng trả lời |
| 3.17 | Điều 22.2 (phụ lục sửa thời hạn) và Điều 25 phần "một lần một công việc" **chưa làm**, chuyển sang 7b vì cần đối tượng phụ lục / nhiều hợp đồng | Checklist D16 chưa tick hết |
| 3.18 | Ca biên 30 ngày chọn `worked_after_expiry_days > 30 day` (Đ20.2.b: "hết thời hạn 30 ngày") | Ca đúng 30 ngày |

## Giai đoạn 4 — giải thích, câu hỏi gợi ý, sự kiện diff

| # | Mục | Trạng thái |
|---|---|---|
| 4.1 | Chỉ dữ kiện người dùng có khai miền trong `user_fact_questions` mới được gợi ý; dữ kiện như `work_condition`, `wage_region`, `pregnancy_month` chưa có miền nên không bao giờ được hỏi | Còn |
| 4.2 | Miền dữ kiện số là giá trị đại diện do người viết chọn (vd. `worked_after_expiry_days: [10, 45]`), không tự suy từ ngưỡng luật; đổi ngưỡng luật mà quên đổi miền thì điểm câu hỏi sai | Còn |
| 4.3 | `next_questions` fork + update một lần mỗi giá trị khả dĩ trên toàn bộ catalog: đủ nhanh cho 50 rule, chưa đo cho catalog lớn (giai đoạn 6) | Còn |
| 4.4 | `explain` dựng lại cây từ kết quả + bảng dữ kiện, không lưu vết lúc đánh giá; nên nếu ngữ nghĩa `decide_rule` đổi mà quên cập nhật `explain` thì hai bên có thể lệch (test chỉ ghim các ca chính) | Còn |
| 4.5 | `evaluation_diff` chỉ phát sau recheck; lần đọc đầu vẫn phát từng `evaluation` như cũ | Có chủ ý |
| 4.6 | Hai nút `fact` của cùng một dữ kiện có thể lặp trong cây (mỗi điều kiện kèm nút dữ kiện của nó) | Có chủ ý |

## Giai đoạn 5 — gói dân sự `civil_general` + `civil_loan`, `kind`, `packs=`

| # | Mục | Trạng thái |
|---|---|---|
| 5.1 | Mới có 3 rule dân sự: trần lãi 20%/năm (Đ468.1) + ngoại lệ luật chuyên ngành, đơn phương chấm dứt phải thông báo (Đ428.2). Chưa viết: Đ466.4 (lãi chậm trả), Đ468.2 (lãi 50% mức trần khi không xác định rõ), Đ470 (trả nợ trước hạn), Đ465.3/467 (đòi nợ trước hạn), phạt vi phạm | Còn |
| 5.2 | `check_contract(packs=["civil_loan"])` chỉ chọn catalog; **trích dữ kiện và gán khái niệm vẫn là prompt lao động**, nên hợp đồng vay chưa chạy end-to-end. Cần tagger / nhận diện loại hợp đồng theo kind (phần Huy) | Còn |
| 5.3 | Nhãn kết quả dùng từ vựng lao động (`employee_impact`) cho hợp đồng dân sự; role `BEN_*` tạm đặt tên | Còn |
| 5.4 | Cạnh `pid` anchors dân sự (`bo-luat:91/2015/QH13#d468.k1`, `#d428.k2`) chưa kiểm với đồ thị luật; `AnchorLawBasis` chưa thử với catalog dân sự | Còn |
| 5.5 | `kind`: bộ nạp kiểm theo loại slot (concept phải có slot thuộc loại kind yêu cầu), không kiểm tên; danh sách kind chung của B1 chưa có (mới `rate_cap`) | Còn |
| 5.6 | Khoản vay không ghi đơn vị lãi (`Fact(30)` không đơn vị) ra `UNKNOWN`, không phải vi phạm (có chủ ý, đúng bất biến) | Có chủ ý |
| 5.7 | Tháng = 30 ngày, năm = 360 ngày trong bảng quy đổi (cùng cách với gói labor) | Có chủ ý |
| 5.8 | Ngoại lệ chéo gói chưa có ca thật (ngoại lệ luật chuyên ngành đặt cùng gói `civil_loan`); cơ chế đã có test bằng gói tổng hợp | Còn |

## Giai đoạn 6 — benchmark

| # | Mục | Trạng thái |
|---|---|---|
| 6.1 | Benchmark (`scripts/bench_rule_engine.py`, `src/rag/rules/bench/synth.py`, 6 kịch bản, hai trục) **giao cho Khánh** theo `khanh.md` (K2); Tùng không làm thay để giữ phần đo độc lập. Engine đã có đủ interface Khánh cần (`engine_interface.md`). Đến khi có số liệu, vẫn **chưa chứng minh được** "nhiều rule vẫn chịu được" (xem 2.8) | Chờ Khánh |
| 6.2 | `network+beta` (D30, Could) không làm | Có chủ ý |

## Giai đoạn 7 — đối tượng, đếm, phủ định (TREAT)

| # | Mục | Trạng thái |
|---|---|---|
| 7.1 | `next_questions` khóa kết quả theo `(concept, rule)` nên gộp nhầm các nhóm của rule xuyên đối tượng (đếm 1 thay vì 2). Nay khóa theo cả `object`; `evaluation_diff` và `explain` cũng phân biệt nhóm | Đã sửa |
| 7.2 | Viết `timeline.py` trước khi chạy test đỏ (lệch TDD); bù bằng 3 đột biến cố ý, test đều bắt được | Đã xử lý |
| 7.3 | `over` chỉ một biến; nối nhiều biến (ghép cặp hai đối tượng khác kiểu, vd. phụ lục ↔ hợp đồng theo điều kiện trên cả hai) chưa làm; hiện thay bằng `group_by` nhiều khóa | Còn |
| 7.4 | Rule xuyên đối tượng không dùng được `exception_of`; bốn ngoại lệ Đ20.2.c của `r5` viết lại bằng `applicability` (lặp với `r3_*`) | Có chủ ý |
| 7.5 | Không có đối tượng của kiểu → `NOT_APPLICABLE no_objects` (kể cả `exists`): hồ sơ thiếu hẳn hợp đồng không bị báo vi phạm | Có chủ ý |
| 7.6 | Chưa có nguồn đối tượng thật: `dossier_objects` của Huy (H2) chưa xong, `check_contract` chưa truyền `objects`; rule xuyên văn bản chỉ chạy trong test và qua API phiên | Còn |
| 7.7 | `explain` của rule xuyên đối tượng dừng ở số đếm nhóm, chưa mở tới từng đối tượng / ứng viên U | Còn |
| 7.8 | `history: true` đếm cả hợp đồng đã hết hạn nhưng không kiểm "liên tiếp" (Đ20.2.c nói ký mới sau HĐ cũ); hợp đồng cách nhau nhiều năm vẫn bị đếm | Còn (cần người làm pháp lý xem) |
| 7.9 | `r7` (Đ22.2) dựa vào thuộc tính `modifies_term` của phụ lục; việc nhận ra phụ lục có sửa thời hạn là phần trích (Huy), engine không tự suy | Còn |
| 7.10 | Soát theo kỳ (D28) chưa so với `gold.yaml` vì bộ A (C1, C4) chưa có; mỗi ngày ranh giới tạo một phiên mới (không tận dụng tăng dần giữa các ngày) | Còn |
| 7.11 | Network tính lại số đếm của rule bằng cách cộng lại toàn bộ trị ứng viên đã nhớ của rule đó (O(số đối tượng) phép cộng); chỉ phần đắt (đánh giá `where`, dữ kiện suy ra theo đối tượng) là tăng dần | Có chủ ý |
| 7.12 | Hai đối tượng khác kiểu có thể trùng `id`; `apply_object_changes` coi `id` là khóa duy nhất của cả hồ sơ | Còn |

**Review độc lập giai đoạn 4, 5, 7** (Network = Reference: 0 lệch trên 300 seed × 60 bước; bất biến giữ trên 3000 ca bớt thông tin). Sửa, mỗi mục có test đỏ trước (`tests/test_rules_review7_fixes.py`):

| # | Mục | Trạng thái |
|---|---|---|
| 7.13 | **r5 / r6 không kết luận được trên hồ sơ thật**: HĐ đang hiệu lực chưa có `worked_after_expiry_days` nên `kind_effective` thành UNKNOWN, r5 ra UNKNOWN thay vì FAIL (test cũ gán `days=0` cho mọi HĐ nên che lỗi). Thêm thuộc tính dựng sẵn `expired` (`valid_to < ngày soát`) cho mọi đối tượng; ngoại lệ Đ20.2.b chỉ xét HĐ đã hết hạn | Đã sửa |
| 7.14 | **Gói vay bị chặn qua bridge**: `user_fact_set` kiểm tên theo hằng gói labor nên `special_law_applies` bị từ chối, trần lãi luôn UNKNOWN. Nay kiểm theo `Context.input_units` của gói đang dùng | Đã sửa |
| 7.15 | "Có đối tượng nhưng mọi ứng viên F + khóa chưa biết" bị gộp với "không có đối tượng" (`no_objects`), bớt thông tin có thể làm NOT_APPLICABLE → FAIL | Đã sửa |
| 7.16 | YAML `over` / `group_by` / `count.value` / `history` / `kind` sai hình dạng làm crash lúc nạp hoặc lúc đánh giá; nay là `CatalogError` | Đã sửa |
| 7.17 | `{"removed": "k1"}` xóa nhầm id `k` và `1`; `WorkingObject` sai kiểu (thuộc tính không phải Fact, `attrs=None`, ngày là chuỗi) crash sâu trong engine; nay `TypeError` rõ ràng ở cửa vào phiên | Đã sửa |
| 7.18 | `explain(obj=None)` trên rule nhiều nhóm âm thầm lấy nhóm đầu; nay `KeyError` liệt kê các nhóm | Đã sửa |
| 7.19 | `packs=[]` âm thầm rơi về gói labor; nay `ValueError` | Đã sửa |
| 7.20 | `group_by` nhiều khóa: ứng viên biết `employee` mà thiếu `job` vẫn cộng U vào nhóm của người lao động khác (đúng chữ spec, sinh UNKNOWN thừa) | Còn |
| 7.21 | Đ428.2 chỉ quy định nghĩa vụ "thông báo ngay" và bồi thường nếu gây thiệt hại; gắn `legality: illegal` cho điều khoản "chấm dứt không cần thông báo" có thể quá tay | Còn (cần người làm pháp lý xem) |
| 7.22 | `r1_special_law` luôn PASS khi concept có mặt (nhiễu như 3.9) | Còn |
| 7.23 | Hợp đồng vay ký trước 2017 vẫn bị soát theo Đ468 BLDS 2015: `law_values_valid_from` không áp lên giá trị luật không có kỳ | Còn |
| 7.24 | Bảng dữ kiện phẳng: HĐ xác định thời hạn đang hiệu lực mà thiếu `worked_after_expiry_days` cho `content.term/r4` UNKNOWN (hỏi người dùng). Gói phẳng không có `expired` vì không có ngày hết hạn ở dạng đối tượng | Còn |

## Đánh giá lại theo định hướng "phủ rộng nhiều loại hợp đồng" (23/11, spec bản 3)

Tiêu chí: lõi và luồng soát dùng được cho hợp đồng không phải lao động mà không sửa lõi; ba miền ngang hàng.

**Phần đã làm — đúng hướng (giữ)**

| # | Phần | Vì sao đúng hướng |
|---|---|---|
| R.1 | Giai đoạn 1: lõi tách khỏi lao động (`Context`, `pack.yaml`, đơn vị / dữ kiện / finding / `silences` khai theo gói) | Đây là điều kiện để có miền thứ hai, thứ ba |
| R.2 | Giai đoạn 3: dữ kiện suy ra, ngoại lệ giữa rule và giữa gói | Dùng được cho quan hệ luật chung (BLDS) – luật chuyên ngành (Luật Nhà ở, Luật TCTD) |
| R.3 | Giai đoạn 5: `extends`, `packs=`, `kind`, gói `civil_general` + `civil_loan` | Chứng minh được gói thứ hai không sửa lõi |
| R.4 | Giai đoạn 7: `object_types` khai trong gói (không cố định `Employee`), `group_by` theo ref bất kỳ | Thuê nhà (`Lease`, ref `tenant`) dùng lại được |
| R.5 | Giai đoạn 4: `user_fact_questions`, `explain`, `evaluation_diff` | Không gắn với miền |
| R.6 | Bản liệt kê `civil_general.yaml` (9 mục), `civil_loan.yaml` (11 mục) | Hai phần ba bản liệt kê là ngoài lao động |

**Phần đã làm — lệch hướng (phải sửa, đã đưa vào checklist P8)**

| # | Phần | Lệch thế nào | Việc sửa |
|---|---|---|---|
| R.7 | `kinds.yaml` (T4) | Suy từ 39 concept lao động; 3 kind dân sự rỗng; 7/29 mục liệt kê `kind: none` (4 mục dân sự chung không có kind nào chứa) | **Đã sửa 23/11** (mục Gói thuê nhà, L.5) |
| R.8 | `RuleResult.employee_impact`, outcome của gói dân sự | Hợp đồng vay gắn `employee_impact: unfavorable` (sai nghĩa); spec §5.2 hứa `outcome` dict nhưng cài đặt chưa có | D33 |
| R.9 | `check_contract` mặc định gói `labor` khi không truyền `packs` | Hợp đồng thuê nhà đưa vào bị soát bằng rule lao động | D32, E5 |
| R.10 | `bridge/view.py` (`VERDICTS`, `FACT_LABELS`), prompt `tagger` / `recheck` / `agent` | Viết cứng "người lao động", "hợp đồng lao động" | D34 (Tùng), H2 (Huy) |
| R.11 | Gói dân sự mới có 3 rule chạy được (Đ468.1 + ngoại lệ, Đ428.2) dù bản liệt kê có 20 mục | Miền dân sự mỏng so với lao động (54 rule) | D20/D21 bổ sung theo bản liệt kê |
| R.12 | Thuộc tính dựng sẵn `expired` và các attr Đ20.2 nằm trong gói labor | Đúng chỗ (gói), nhưng chưa có ca thuê nhà để kiểm `expired` dùng chung | D37 |
| R.13 | `engine_interface.md` chỉ ví dụ gói labor | Huy / Khánh dễ hiểu là chỉ có lao động | cập nhật khi có `civil_lease` |

**Phần đang làm dở (phần Tú / Tuấn) — điều chỉnh trước khi làm tiếp**

| # | Phần | Điều chỉnh |
|---|---|---|
| R.14 | Hồ sơ mẫu (C1–C3) chưa soạn | Soạn theo định dạng `dossier.yaml` tổng quát (bản 3), thêm C3b thuê nhà + r1; không soạn theo định dạng cũ có khóa `employee` |
| R.15 | Gold (C4) chưa soạn | Gồm cả ba miền; bảng a1 đã sửa theo Đ22.2 (phụ lục 2 cũng vi phạm) |
| R.16 | Thuê nhà (B7 / T6) chưa đọc | **Đã làm 23/11** (mục Gói thuê nhà) |
| R.17 | UI (F) chưa làm | Kịch bản demo có r1 (thuê nhà); nhãn lấy theo gói |

## Thử nghiệm "cắm gói mới như module" (23/11)

Câu hỏi của Tùng: thêm một loại hợp đồng mới có cần sửa nhiều code không. Cách kiểm: chạy hợp đồng vay mẫu qua
`check_contract(packs=["civil_loan"])` với LLM giả, và tìm chỗ còn gọi gói labor ngoài `rag.rules`.

**Kết luận: lớp engine là module (chỉ YAML); lớp quanh engine chưa.** Thêm gói chỉ bằng YAML đã chạy được cho rule,
ngoại lệ, đơn vị, kiểu đối tượng, `kind`. Nhưng một loại hợp đồng mới hiện còn phải sửa code ở 6 chỗ:

| # | Chỗ | Bằng chứng | Hậu quả với loại hợp đồng mới | Việc |
|---|---|---|---|---|
| M.1 | `facts_map.normalize_slot` | Lãi "30%/năm" ra `Fact(30, "percent")` thay vì `percent_per_year`; so với trần 20%/năm không quy đổi được | Rule ra `UNKNOWN needs_facts` mà `missing_facts` rỗng: **không bao giờ báo vi phạm, người dùng không có gì để trả lời**. Lãi theo tháng bị coi như theo năm nếu bỏ chữ kỳ: sai gấp 12 lần | D38 |
| M.2 | `facts_map._CONTRACT_MAP` | 7 dữ kiện lao động viết cứng (`contract_kind`, `term_months`, `base_salary_vnd`, …) | `document_facts` khai trong `pack.yaml` của gói mới không bao giờ được điền từ hợp đồng. Hai gói dân sự hiện để `document_facts: {}` nên che mất lỗi này | D39 |
| M.3 | Prompt `TAG_PROMPT`, `RECHECK_PROMPT`, `AGENT_PROMPT` | Thử nghiệm: prompt gán khái niệm gửi cho hợp đồng vay mở đầu bằng "hợp đồng lao động tiếng Việt" | LLM bị dẫn sai miền; đã giao Huy (H2) | H2 |
| M.4 | `ui/contracts_api.py` 437, 514; `ui/contract_studio.py` 34, 268; `contracts/graph/build.py:164` | Đều gọi `load_catalog()` (labor) không có `packs` | UI không chọn được gói; đồ thị bỏ cạnh `HOLDER` im lặng cho khái niệm gói khác (không cảnh báo) | D40 |
| M.5 | `bridge/view.py` `FACT_LABELS`, `VERDICTS` | Bảng tĩnh tiếng lao động | Dữ kiện / finding của gói mới hiển thị thô hoặc sai nghĩa | D34 |
| M.6 | Chọn gói theo loại hợp đồng | `resolve_catalog` mặc định labor; chưa có `classify_contract` | Hợp đồng thuê nhà bị soát bằng rule lao động | D32, E5 |

**Trạng thái sau khi sửa (23/11, phần logic; UI để sau theo yêu cầu):**

| # | Trạng thái | Commit |
|---|---|---|
| M.1 | Đã sửa: `unit_forms` trong `pack.yaml`; "30%/năm" ra `percent_per_year`; tỉ lệ không ghi kỳ với slot theo kỳ thì không đoán (slot không chuẩn hóa được → thao tác chờ duyệt) | f0c5777 |
| M.2 | Đã sửa: `document_facts` khai `from` + `parse`; `extract_fields`; gói labor chuyển sang khai báo, kết quả giữ nguyên | 50aed8a |
| M.3 | Đã sửa phần nhãn loại văn bản: `document_labels`; ba prompt điền theo gói, gói labor ra đúng văn bản cũ. Phần prompt dựng theo `kind` vẫn là của Huy (H2) | 9c2fdc3 |
| M.4 | Phần logic đã sửa: vai trò các bên theo `roles` (+ `aliases`) của gói; ASSERT khái niệm ghi `holder`; đồ thị nối `HOLDER` cho mọi gói. **Còn** `ui/contracts_api.py`, `ui/contract_studio.py` (UI, để sau) | 9bf2816 |
| M.5 | **Còn** (UI, để sau): `bridge/view.py` | — |
| M.6 | Phía engine đã sửa: `packs_for_kind`, `check_contract(document_kind=)`, loại không có gói → không chạy rule nào, không gọi LLM. **Còn** `classify_contract` (Huy) và việc bỏ mặc định labor khi không truyền gì (chuyển tiếp) | 1ae4ee3 |
| M.7 | Test chặn tái phát: `tests/test_pack_plugin.py` (gói giả chạy hết luồng; đã thử ba đột biến, đều bị bắt) | (commit này) |
| M.8 | Mới thấy khi sửa M.1: slot không chuẩn hóa được làm thao tác ASSERT thành `pending` (chờ duyệt), khái niệm coi như chưa có mặt cho tới khi duyệt; với rule `on_silence: none` kết quả tạm là PASS. Đây là hành vi có sẵn cho mọi gói, không mới, nhưng với "lãi 30%" không ghi kỳ thì kết quả tạm PASS dễ gây hiểu nhầm | Còn |

Vì sao test cũ không bắt được: `test_check_contract_with_packs_labor_matches_default` và test gói vay chỉ dùng LLM giả
trả khái niệm lao động, và hai gói dân sự không khai `document_facts`. Đã thêm D41: test "gói giả chạy qua
`check_contract` không sửa file code nào" để lỗi kiểu này lộ ra khi thêm gói thứ tư.

## Sửa nhận định sai về kho luật (23/11)

| # | Mục | Trạng thái |
|---|---|---|
| K.1 | Các bản trước (bản liệt kê T1, câu trả lời 23/11) ghi "kho không có NĐ 145/2020 và nghị định lương tối thiểu". **Sai**: mình kiểm `data/team-4.2/legal/raw/` ở gốc repo (bản cũ, ít văn bản), còn kho ứng dụng dùng là `app/team-4.2/data/team-4.2/legal/raw/` (120 văn bản, có NĐ 145/2020, 38/2022, 74/2024, 293/2025). Test trích dẫn giờ đọc kho ứng dụng trước (`tests/legal_corpus.py`) | Đã sửa |
| K.2 | Mức lương tối thiểu vùng trong gói labor (12 số) khớp đúng bảng của ba nghị định; thay ghi chú "số người viết nhớ" bằng test đối chiếu | Đã sửa |
| K.3 | NĐ 145/2020 có trong kho nhưng chưa đọc phần liên quan Đ20, Đ22, Đ25 (B3) | Còn |
| K.4 | Crawl thêm cho gói vay: Luật Các tổ chức tín dụng 32/2024/QH15, Nghị quyết 01/2019/NQ-HĐTP (API công khai VBPL, `scripts/team-4.2/fetch_loan_scope.py`); mới vào `raw/` + `supplements/loan-scope-v1/`, chưa nhập snapshot, chưa dựng đồ thị luật (việc của Khánh / Huy) | Còn |

## Làm đầy gói vay (23/11)

| # | Mục | Trạng thái |
|---|---|---|
| V.1 | Gói `civil_loan` từ 1 lên 5 khái niệm: trần lãi theo ngày ký (BLDS 2005 Đ476 trước 2017, BLDS 2015 Đ468.1 từ 2017), lãi nợ gốc quá hạn ≤ 30%/năm (NQ 01/2019 Đ5.2.c), lãi chậm trả ≤ 20%/năm (Đ357.2), bên cho vay không đòi trước hạn tùy ý (Đ465.3, ngoại lệ Đ467), bên vay được trả trước hạn khoản vay không lãi (Đ470.1) | Xong |
| V.2 | 7 hợp đồng vay mẫu + nhãn đúng (12 nhãn) viết trước khi chạy engine; engine khớp cả 12 ở hai evaluator. Nhãn do Claude gắn, **cần Tùng duyệt** | Xong (chờ duyệt) |
| V.3 | Trần trước 01/01/2017 = 13,5%/năm lấy từ ví dụ trong NQ 01/2019 (lãi suất cơ bản 9%/năm theo QĐ 2868/QĐ-NHNN); QĐ 2868 không có trong kho; trước 01/12/2010 chưa có giá trị (ra UNKNOWN) | Còn |
| V.4 | NQ 01/2019 Đ2.1 (hợp đồng trước 2017 đang thực hiện mà lãi phù hợp BLDS 2015 thì từ 01/01/2017 áp BLDS 2015): engine soát theo ngày ký, chưa chia theo khoảng thực hiện. Gold `l6_truoc_2017` ghi rõ | Còn |
| V.5 | Ngoại lệ tổ chức tín dụng vẫn qua dữ kiện người dùng chung `special_law_applies`; chưa tự nhận ra bên cho vay là tổ chức tín dụng | Còn |
| V.6 | Chưa có rule: lãi chỉ khi có thỏa thuận (Đ463), lãi 50% trần khi không rõ lãi suất (Đ468.2, là giá trị suy ra chứ không phải vi phạm), phạt vi phạm cùng lãi quá hạn (NQ 01/2019 Đ12) | Còn |
| V.7 | Sửa bên giữ quyền của trần lãi: bên vay (bản đầu gán nhầm bên cho vay) | Đã sửa |

## Gói thuê nhà và kind chung (23/11, spec bản 3 đã duyệt)

| # | Mục | Trạng thái |
|---|---|---|
| L.1 | Bản liệt kê `civil_lease.yaml`: 9 quy định, mỗi quy định trích nguyên văn theo kỳ (`periods`: Luật Nhà ở 65/2014 từ 01/07/2015, 27/2023 từ 01/08/2024); test kiểm mọi câu trích | Xong (chờ duyệt) |
| L.2 | Sửa nhận định cũ: Luật Nhà ở 27/2023 hiệu lực **01/08/2024** (Luật 43/2024/QH15 Đ2 sửa khoản 1 Điều 197), không phải 01/01/2025 | Đã sửa |
| L.3 | Gói `civil_lease`: 6 khái niệm (3 nội dung bắt buộc Đ163, lấy lại nhà tùy ý Đ172.1, nợ tiền thuê từ 03 tháng Đ172.2.b theo kỳ, tước quyền chấm dứt của bên thuê Đ172.3). Không sửa code engine | Xong |
| L.4 | 6 hợp đồng thuê mẫu, 11 nhãn viết trước khi chạy engine, khớp cả hai evaluator; test không báo FAIL ngoài gold; `check_contract(document_kind="lease_contract")` chạy đầu-cuối không có chữ "lao động" | Xong (nhãn chờ duyệt) |
| L.5 | Danh sách kind chung `src/rag/rules/packs/kinds.yaml`, bộ nạp đọc cho mọi gói; gói không được khai lại kind chung khác đi; 46/51 khái niệm có kind, 5 khái niệm thai sản "không vừa" có lý do; 4 kind dùng ở ≥ 2 miền. Bản nháp `docs/rule_inventory/kinds.yaml` đã gộp và xóa | Xong (chờ duyệt) |
| L.6 | Nhiều kind có `slot_kinds: []` (required_content, time_limit, payment, notice, count_limit, penalty) vì khái niệm lấy giá trị từ dữ kiện cấp hợp đồng hoặc có slot khác loại: kiểm theo loại slot chỉ còn ý nghĩa với leave_entitlement, prohibited_practice, rate_cap, termination | Còn (hạn chế thiết kế) |
| L.7 | `lease.tenant_termination_right` xếp vi phạm (mandatory) là cách đọc của người soạn: Đ172.3 trao quyền nhưng không nói điều khoản từ bỏ vô hiệu | Chờ Tùng duyệt |
| L.8 | D37 (rule xuyên văn bản thuê nhà: gia hạn, tăng giá giữa kỳ): giá mới "do các bên thỏa thuận" (Đ170.2) nên phụ lục hai bên ký là hợp lệ, chưa có rule vi phạm có căn cứ; chưa khai `object_types` Lease/Amendment | Chờ Tùng quyết |
| L.9 | Chưa soát: báo trước 30 ngày (Đ172.4, là mặc định, được thỏa thuận khác), cho thuê lại (sự kiện thực hiện), giá do Nhà nước quy định (nhà ở xã hội), lý do chậm trả "đã thỏa thuận" (2023) / "chính đáng" (2014); hợp đồng ký trước 01/07/2015 (Luật Nhà ở 2005) | Còn |
| L.10 | `outcome.employee_impact` vẫn dùng cho gói vay / thuê (sai nghĩa) | Còn (D33) |
| L.11 | Bộ test đầy đủ sau gói thuê nhà: 35 failed (đúng số baseline, toàn agent / conversation / warehouse / pipeline), 2264 passed | Ghi nhận |

## Tồn đọng chung (môi trường, quy trình)

| # | Mục | Trạng thái |
|---|---|---|
| E.1 | Toàn bộ suite có **35 test fail có sẵn** từ trước (nhóm `test_agent_stability`, `test_answer_presentation`, `test_conversation`, `test_dated_agent_e2e`, `test_pipeline`, `test_warehouse_migration`); danh sách tên ở `phase1_baseline.md`. Số fail không đổi sau giai đoạn 1, 2, 3 | Còn, không phải do engine |
| E.2 | `tests/test_agent_partial_review.py` lỗi import có sẵn; phải chạy với `--ignore` | Còn |
| E.3 | `test_warehouse_migration.py::test_both_modes_fail_closed_if_catalog_is_unavailable` chỉ fail khi chạy chung nhóm (phụ thuộc thứ tự), riêng thì pass | Còn |
| E.4 | `test_bridge_tagger.py::test_failed_batch_warns_and_others_continue` fail một lần khi chạy nhóm với `RAG_RULE_EVALUATOR=reference`; sau đó xanh 3 lần riêng và 2 lần nhóm (flaky) | Còn |
| E.5 | Toàn bộ suite mất khoảng 10 phút; chạy nền | Có chủ ý |
| E.6 | Spec §4.2 ghi "chưa xác minh" việc xử lý phủ định trong bài gốc TREAT; checklist A1 chưa tick | Còn |
| E.7 | Chưa merge, chưa push; việc tích hợp là quyết định của người dùng | Chờ quyết định |
| E.8 | Nhánh có thay đổi cũ không phải của phiên này (`reports/week-02`, `week-03` README, các thư mục dữ liệu chưa theo dõi); không đưa vào commit nào | Có chủ ý |
| E.9 | Giai đoạn 6 (benchmark) chờ Khánh; giai đoạn 7 đã xong phần engine | Chờ |
