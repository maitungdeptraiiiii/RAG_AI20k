# W04 — Hạn chế, lỗi và điểm nhỏ theo từng bước (rule engine)

Cập nhật từ giai đoạn 3 trở đi: mỗi giai đoạn mới thêm một mục vào file này (lỗi đã sửa, lỗi còn tồn đọng, hạn chế, quyết định
có chi phí nếu sai). Nhánh `feat/team-4.2/w04-rules-engine`, chưa merge. Trạng thái: **Đã sửa** / **Còn** / **Có chủ ý**.

## Giai đoạn 1 — tách lõi, Reference, gói `labor` (plan `2026-11-22-rule-engine-phase1.md`)

| # | Mục | Trạng thái |
|---|---|---|
| 1.1 | Đơn vị gốc không có dòng quy đổi riêng làm âm thầm tắt so sánh khác đơn vị (reviewer, Important). Loader nay tự thêm `(gốc, 1)` và báo lỗi nếu gốc có hệ số khác 1 (commit 7d8fc9b) | Đã sửa |
| 1.2 | Khi lập kế hoạch tin sai "≥5 rule dùng `contract_kind`" (thực tế 5 lá / 3 rule): test đổi, ghi `Ruling` | Có chủ ý |
| 1.3 | Từng ghi nhầm "Task 8 complete" vào sổ sau lệnh `git add` hỏng: đã xóa dòng, commit lại cho đúng | Đã sửa |
| 1.4 | Bộ nạp ném ngoại lệ thô (`AttributeError`, `TypeError`) khi YAML sai hình dạng ở `concepts.yaml` / `pack.yaml` (phần `derived` đã được sửa ở giai đoạn 3) | Đã sửa (S.7) |
| 1.5 | `version` trong `pack.yaml` không vào `Catalog.version` | Đã sửa (S.7) |
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
| 3.7 | Dữ kiện suy ra `UNKNOWN` chỉ vì đầu vào `CONFLICT` ra `needs_facts` với `missing_facts` rỗng, đúng ra phải là `conflict` (`semantics.py` chỉ xét `CONFLICT` trực tiếp trong `check`) | Đã sửa (S.6) |
| 3.8 | `value: null` trong định nghĩa dữ kiện suy ra được chấp nhận thành `Fact(None)` "có mặt" | Đã sửa (S.7) |
| 3.9 | Bốn rule `r3_*` luôn ra `PASS/ok` khi điều khoản thời hạn có mặt (kể cả applicability chưa biết): mỗi HĐ xác định thời hạn sinh bốn dòng "ok", có thể gây nhiễu UI và báo cáo | Đã sửa ở lớp trình bày (S.15) |
| 3.10 | Hàng U của §5.4 chỉ thêm dữ kiện của ngoại lệ vào `missing_facts` khi rule gốc là `FAIL`; gốc `UNKNOWN` thì phải hỏi thêm một vòng | Có chủ ý (đúng spec) |
| 3.11 | Định nghĩa `from` lấy đơn vị theo nguồn, bỏ qua `unit` đã khai của dữ kiện suy ra, không kiểm hai đơn vị khớp nhau | Đã sửa (S.7) |
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
| 7.21 | Đ428.2 chỉ quy định nghĩa vụ "thông báo ngay" và bồi thường nếu gây thiệt hại; gắn `legality: illegal` cho điều khoản "chấm dứt không cần thông báo" có thể quá tay | Đã duyệt (Tùng, 24/11) |
| 7.22 | `r1_special_law` luôn PASS khi concept có mặt (nhiễu như 3.9) | Đã sửa ở lớp trình bày (S.15) |
| 7.23 | Hợp đồng vay ký trước 2017 vẫn bị soát theo Đ468 BLDS 2015: `law_values_valid_from` không áp lên giá trị luật không có kỳ | Đã sửa (S.1, 24/11) |
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
| M.5 | Đã sửa (D34): `bridge/view.py` lấy nhãn từ `labels` trong `pack.yaml` (R.2); M.4 phần UI cũng đã sửa (D40, K.2) | 9045bb0, a76806f |
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
| K.4 | Crawl thêm cho gói vay: Luật Các tổ chức tín dụng 32/2024/QH15, Nghị quyết 01/2019/NQ-HĐTP (API công khai VBPL, `scripts/team-4.2/fetch_loan_scope.py`); mới vào `raw/` + `supplements/loan-scope-v1/`, chưa nhập snapshot, chưa dựng đồ thị luật (việc của Khánh / Huy) | Đã đồng bộ (S.22) |

## Làm đầy gói vay (23/11)

| # | Mục | Trạng thái |
|---|---|---|
| V.1 | Gói `civil_loan` từ 1 lên 5 khái niệm: trần lãi theo ngày ký (BLDS 2005 Đ476 trước 2017, BLDS 2015 Đ468.1 từ 2017), lãi nợ gốc quá hạn ≤ 30%/năm (NQ 01/2019 Đ5.2.c), lãi chậm trả ≤ 20%/năm (Đ357.2), bên cho vay không đòi trước hạn tùy ý (Đ465.3, ngoại lệ Đ467), bên vay được trả trước hạn khoản vay không lãi (Đ470.1) | Xong |
| V.2 | 7 hợp đồng vay mẫu + nhãn đúng (12 nhãn) viết trước khi chạy engine; engine khớp cả 12 ở hai evaluator. Nhãn do Claude gắn, **cần Tùng duyệt** | Xong, đã duyệt (tùng, 24/11) |
| V.3 | Trần trước 01/01/2017 = 13,5%/năm lấy từ ví dụ trong NQ 01/2019 (lãi suất cơ bản 9%/năm theo QĐ 2868/QĐ-NHNN); QĐ 2868 không có trong kho; trước 01/12/2010 chưa có giá trị (ra UNKNOWN) | Còn |
| V.4 | NQ 01/2019 Đ2.1 (hợp đồng trước 2017 đang thực hiện mà lãi phù hợp BLDS 2015 thì từ 01/01/2017 áp BLDS 2015): engine soát theo ngày ký, chưa chia theo khoảng thực hiện. Gold `l6_truoc_2017` ghi rõ | Còn |
| V.5 | Ngoại lệ tổ chức tín dụng vẫn qua dữ kiện người dùng chung `special_law_applies`; chưa tự nhận ra bên cho vay là tổ chức tín dụng | Còn |
| V.6 | Chưa có rule: lãi chỉ khi có thỏa thuận (Đ463), lãi 50% trần khi không rõ lãi suất (Đ468.2, là giá trị suy ra chứ không phải vi phạm), phạt vi phạm cùng lãi quá hạn (NQ 01/2019 Đ12) | Còn |
| V.7 | Sửa bên giữ quyền của trần lãi: bên vay (bản đầu gán nhầm bên cho vay) | Đã sửa |

## Gói thuê nhà và kind chung (23/11, spec bản 3 đã duyệt)

| # | Mục | Trạng thái |
|---|---|---|
| L.1 | Bản liệt kê `civil_lease.yaml`: 9 quy định, mỗi quy định trích nguyên văn theo kỳ (`periods`: Luật Nhà ở 65/2014 từ 01/07/2015, 27/2023 từ 01/08/2024); test kiểm mọi câu trích | Xong, đã duyệt (tùng, 24/11) |
| L.2 | Sửa nhận định cũ: Luật Nhà ở 27/2023 hiệu lực **01/08/2024** (Luật 43/2024/QH15 Đ2 sửa khoản 1 Điều 197), không phải 01/01/2025 | Đã sửa |
| L.3 | Gói `civil_lease`: 6 khái niệm (3 nội dung bắt buộc Đ163, lấy lại nhà tùy ý Đ172.1, nợ tiền thuê từ 03 tháng Đ172.2.b theo kỳ, tước quyền chấm dứt của bên thuê Đ172.3). Không sửa code engine | Xong |
| L.4 | 6 hợp đồng thuê mẫu, 11 nhãn viết trước khi chạy engine, khớp cả hai evaluator; test không báo FAIL ngoài gold; `check_contract(document_kind="lease_contract")` chạy đầu-cuối không có chữ "lao động" | Xong, nhãn đã duyệt (tùng, 24/11) |
| L.5 | Danh sách kind chung `src/rag/rules/packs/kinds.yaml`, bộ nạp đọc cho mọi gói; gói không được khai lại kind chung khác đi; 46/51 khái niệm có kind, 5 khái niệm thai sản "không vừa" có lý do; 4 kind dùng ở ≥ 2 miền. Bản nháp `docs/rule_inventory/kinds.yaml` đã gộp và xóa | Xong, đã duyệt (tùng, 24/11) |
| L.6 | Nhiều kind có `slot_kinds: []` (required_content, time_limit, payment, notice, count_limit, penalty) vì khái niệm lấy giá trị từ dữ kiện cấp hợp đồng hoặc có slot khác loại: kiểm theo loại slot chỉ còn ý nghĩa với leave_entitlement, prohibited_practice, rate_cap, termination | Còn (hạn chế thiết kế) |
| L.7 | `lease.tenant_termination_right` xếp vi phạm (mandatory) là cách đọc của người soạn: Đ172.3 trao quyền nhưng không nói điều khoản từ bỏ vô hiệu | Tùng duyệt (23/11) |
| L.8 | D37 (rule xuyên văn bản thuê nhà: gia hạn, tăng giá giữa kỳ): giá mới "do các bên thỏa thuận" (Đ170.2) nên phụ lục hai bên ký là hợp lệ, chưa có rule vi phạm có căn cứ; chưa khai `object_types` Lease/Amendment | Tùng duyệt (23/11): không có rule; r1 chỉ là hồ sơ kiểm \"phụ lục hợp lệ không ra vi phạm\" |
| L.9 | Chưa soát: báo trước 30 ngày (Đ172.4, là mặc định, được thỏa thuận khác), cho thuê lại (sự kiện thực hiện), giá do Nhà nước quy định (nhà ở xã hội), lý do chậm trả "đã thỏa thuận" (2023) / "chính đáng" (2014); hợp đồng ký trước 01/07/2015 (Luật Nhà ở 2005) | Còn |
| L.10 | `outcome.employee_impact` sai nghĩa với vay / thuê | Xong (D33): YAML mọi gói ghi `party_impact`; bộ nạp đổi `employee_impact` cũ thành `party_impact` (khai cả hai khác nhau là lỗi); `RuleResult.outcome` (dict) + `party_impact`; `employee_impact` giữ cùng giá trị để tương thích. Golden engine cũ không đổi |
| L.12 | `RuleResult.party_impact` chưa ghi bất lợi cho BÊN nào (spec G10: vai trò `holder`); người đọc lấy `holder` từ khái niệm. UI vẫn đọc `employee_impact` (D34, để sau) | Còn |
| L.13 | `appendix.states_change/r1` (Đ22.2 câu 2) cần hai thuộc tính phụ lục `states_target_clause`, `states_valid_from`; `rag.contracts.amendments` đã bắt được dẫn chiếu và câu "hiệu lực kể từ ngày" nhưng chưa có bước nào ghi chúng vào đối tượng Amendment (việc `dossier_objects` của Huy). Thiếu thì rule ra UNKNOWN, không ra vi phạm | Còn (Huy) |
| L.14 | t7 (mẫu thật) có điều khoản chưa kiểm vì chưa có rule có căn cứ: bên cho thuê điều chỉnh giá khi "thị trường thay đổi" (Điều 4.3), vào nhà không báo trước (6.3), bên thuê chỉ có một căn cứ chấm dứt và mất cọc (9.2) | Còn (cần đọc thêm luật) |
| L.11 | Bộ test đầy đủ sau gói thuê nhà: 35 failed (đúng số baseline, toàn agent / conversation / warehouse / pipeline), 2264 passed; sau D33, D16, hồ sơ a1–r1, B6 (23/11): 35 failed (cùng 6 file baseline), 2340 passed | Ghi nhận |

## Hồ sơ nhiều văn bản a1, b1–b5, r1 (23/11)

| # | Hạn chế | Trạng thái |
|---|---|---|
| H.1 | Gold mới (a1, b1–b5, r1, lease t7) do Claude viết từ luật trước khi chạy engine; engine khớp ngay lần đầu | Đã duyệt (Tùng, 24/11) |
| H.2 | Test dựng đối tượng từ `objects.yaml` viết tay và chọn dữ kiện theo `from` (thay cho `graph_facts`); luồng thật cần `dossier_objects` (Huy, H1) — `objects.yaml` là đáp án của H1 | Còn (Huy) |
| H.3 | Thuộc tính suy từ nhiều văn bản (`worked_after_expiry_days`, `new_contract_signed`) không có câu trích, chỉ ghi `why`; `dossier_objects` phải tính từ ngày hết hạn / ngày ký của các HĐ | Còn (Huy) |
| H.4 | "Không có FAIL ngoài gold" ở hồ sơ chỉ xét rule xuyên đối tượng và rule có dữ kiện trong `facts.yaml`; nội dung bắt buộc của từng HĐ kiểm ở bộ hợp đồng đơn lẻ | Ghi nhận |
| H.5 | Bước `set_review_date` của kịch bản dựng phiên mới: phiên chưa có thao tác đổi ngày soát tăng dần (cần cho dòng thời gian F4 / E3) | Còn |
| H.6 | r1: `civil_lease` chưa khai `object_types` nên `refs` (`lessor`, `lessee`) không đối chiếu được với gói; hồ sơ chỉ kiểm rule trên dữ kiện phẳng theo thời gian | Ghi nhận (D37: không có rule xuyên văn bản) |
| H.7 | b4: bổ sung HĐ bị sót làm kết luận trung gian rút lại NHƯNG HĐ2 thành lần ký xác định thời hạn thứ ba (vi phạm Đ20.2.c) — cách đọc "HĐ bị sót 02 tháng cũng tính một lần ký" cần Tùng xác nhận | Đã duyệt (Tùng, 24/11) |

## Chuẩn hóa giá trị bằng regex sau bước LLM (23/11, nghiên cứu regex → LLM)

Luồng thật đã là lai: LLM trích chuỗi `value` kèm câu trích (`facts.py`, kiểm `quote_ok`), rồi regex trong `contracts/values.py`
đổi chuỗi đó thành số + đơn vị (`facts_map.py`: `_duration`, `_salary`, `_percent`). Đo thử bằng 40 cách viết (kịch bản ở
`app/team-4.2/docs/superpowers/notes/w04-rule-engine/regex_vs_llm_plan.md`); chưa sửa gì. Chưa có số đo trên dữ liệu thật vì bộ fixture chỉ ghi sẵn "đầu ra lý tưởng" của LLM.

| # | Mục | Trạng thái |
|---|---|---|
| V.1 | **Sai im lặng:** "2 năm 6 tháng" -> 24 tháng (mất 6 tháng; đúng là 30); bộ đọc cũ lấy giá trị đầu tiên | **Đã sửa tổng quát** (spec `app/team-4.2/docs/superpowers/specs/2026-11-23-typed-value-reading-design.md`): LLM trả các phần `{n, unit}`, code cộng; chuỗi nhiều giá trị không có dạng có kiểu -> không đọc |
| V.2 | Số kèm chữ trong ngoặc ("24 (hai mươi bốn) tháng", "100.000.000 (một trăm triệu) đồng", "ba mươi (30) ngày") không đọc được | **Đã sửa tổng quát**: đọc qua dạng có kiểu; căn cứ kiểm bằng bộ quét số (chữ số + chữ) |
| V.3 | Số bằng chữ ("hai mươi bốn tháng", "một trăm triệu đồng", "một phẩy năm phần trăm"), "5tr", "100.000.000đ", "20 phần trăm", "1,5 năm" -> None | **Đã sửa tổng quát**: bộ đọc số tiếng Việt theo ngữ pháp đóng chỉ để kiểm căn cứ; cho phép nhân nghìn / triệu / tỷ |
| V.4 | Ngày: "01.03.2024", "mùng 1 tháng 3 năm 2024", "tháng 3 năm 2024", "March 1, 2024" regex không đọc | Ngày ký / hiệu lực đã do LLM trả ISO (không qua regex); regex ngày chỉ còn ở chỗ khác (ingest, agent) — ngoài phạm vi |
| V.5 | Không có cảnh báo khi câu trích có số mà chuẩn hóa thất bại | Sai im lặng đã chặn: slot -> `pending` (`slot_unparsable`); dữ kiện cấp hợp đồng bị bỏ -> UNKNOWN. Dữ kiện cấp hợp đồng bị bỏ **chưa có cảnh báo riêng** — còn |
| V.6 | Chưa đo LLM thật: chưa biết model có trả `norm` đúng không (prompt `facts.py` mới, `concept-tag-3`); nhận định về Qwen nhỏ chỉ dựa tài liệu ngoài | Chờ có model |
| V.7 | Cái giá của V.1: dữ liệu cũ (không có `norm`) mà chuỗi có hai giá trị cùng loại (lương + phụ cấp, "12 tháng, gia hạn 6 tháng") nay là UNKNOWN thay vì lấy số đầu | Có chủ ý |
| V.8 | Ca còn lọt ở đường dự phòng (không có `norm`): chuỗi trộn chữ số và chữ như "2 năm sáu tháng" — regex chỉ thấy "2 năm" -> 24 tháng. Đường chính (có `norm`) không bị | Còn |
| V.9 | Căn cứ chỉ kiểm SỐ có trong câu trích, không kiểm ĐƠN VỊ: LLM ghi 8 "month" cho "8 ngày" vẫn qua nếu regex không đọc được chuỗi để đối chiếu (đọc được thì mâu thuẫn bị chặn) | Đã sửa (S.13) |
| V.10 | Model nhỏ cần constrained decoding (JSON schema) để trả `norm` ổn định — chưa làm; `ask_json` vẫn tìm `{`/`}` | Còn |
| V.11 | Ngoài phạm vi: bộ đọc `contains` / `enum` (phân loại theo cụm chữ trong pack.yaml, vd. `has_interest`), nhận bí danh bên, `AMEND_RE`, cắt "lên/thành" của `_salary` khi không có `norm` | Còn |
| V.12 | **Làm sau (Tùng chốt 23/11):** V.9 (kiểm thêm ĐƠN VỊ LLM ghi có trong câu trích, dùng `unit_forms` của gói) trước, rồi V.11 (phân loại theo cụm chữ: `contains`/`enum`, bí danh bên, `AMEND_RE`) | Ghi để làm sau |

## H1 — `dossier_objects` (23/11, Tùng nhận phần của Huy)

`src/rag/contracts/dossier.py`: `load_dossier`, `bundle`, `extract_dossier_facts` (LLM thật), `dossier_objects`. Cách dựng
khai trong `object_types` của gói. Ra đúng bảng `objects.yaml` của 7 hồ sơ (`tests/test_dossier_objects.py`, 26 test).
Năm quyết định Tùng duyệt: khai cách dựng trong gói; thêm `end_date`; cờ `continuous_employment`; bỏ
`new_contract_signed` khỏi đối tượng; chi tiết phụ lục không tìm thấy -> UNKNOWN chứ không false.

| # | Mục | Trạng thái |
|---|---|---|
| O.1 | Test dùng kết quả trích GIẢ (`extracted.yaml`); chưa chạy LLM thật trên hồ sơ (cùng V.6) | Chờ có model |
| O.2 | Hợp đồng cuối của NLĐ không có văn bản kế tiếp: `worked_after_expiry_days` vắng kể cả khi NLĐ vẫn làm sau hết hạn (giá trị phụ thuộc ngày soát; chưa tính) | Còn |
| O.3 | Dò điều khoản bị sửa và ngày hiệu lực của phụ lục vẫn dùng `amendments.py` (regex cũ, V.11); bỏ sót -> UNKNOWN, không ra vi phạm giả | Còn |
| O.4 | Gom văn bản theo chủ thể vẫn khai tay trong dossier.yaml (bước 2 tự nhận diện theo CCCD/tên chưa làm) | Còn (theo huy.md) |
| O.5 | `new_contract_signed` bỏ khỏi đối tượng; dữ kiện phẳng cùng tên (người dùng trả lời) vẫn giữ cho `contract_kind_effective` | Có chủ ý |
| O.6 | Nhãn nhóm b5 đổi `job=ke_toan` -> `job=nhân viên kế toán` (giá trị `job` là chức danh nguyên văn); trạng thái gold không đổi | Có chủ ý |
| O.7 | Ngày bắt đầu lấy `start_date` -> `effective_date` -> `sign_date`; gói thuê nhà / vay chưa khai `object_types` nên chưa có đối tượng | Còn |

## H2 + E5 — nhận diện loại hợp đồng, chọn gói (23/11, Tùng nhận phần của Huy)

`src/rag/contracts/classify.py` `classify_contract`: LLM chọn một loại trong `document_kinds` của các gói (nhãn
`document_labels`), câu trích kiểm `quote_ok`; câu trích bịa / loại không có gói / độ tin < 0,6 / lỗi gọi model / model
trả unknown -> `unknown`. `check_contract(document_kind="auto")` và `ask_contract_graph(document_kind="auto")` nhận diện
rồi chọn gói; unknown -> không chạy gói nào (soát) / từ chối (hỏi đáp). Danh mục dữ kiện thêm loại `loan` và bảng
`document_kinds` -> danh mục; tagger gửi `kind` của khái niệm (`concept-tag-4`).

| # | Mục | Trạng thái |
|---|---|---|
| K.1 | Chưa đo nhận diện trên hợp đồng mẫu ba miền bằng LLM thật (nghiệm thu H2 trong huy.md); test dùng LLM giả | Chờ có model |
| K.2 | `check_contract` / `ask_contract_graph` không truyền gì vẫn mặc định gói labor (tương thích). UI (`ui/contracts_api.py`, `ui/contract_studio.py`) nay chọn gói theo loại hợp đồng: `concept_check` nhận diện một lần (`classify_contract`), lưu `facts["document_kind"]`, các lần sau và hỏi đáp / báo cáo đọc lại từ đó; `catalog_for(c)`; hợp đồng cũ chưa có loại vẫn dùng labor; loại không có gói: hỏi đáp trả 400, soát trả báo cáo rỗng kèm cảnh báo. Loại nhận diện `unknown` không được lưu (lần sau thử lại). Hợp đồng nhận diện `unknown` thì không kiểm dữ kiện người dùng (không có gói để kiểm) | Đã sửa (D40) |
| K.3 | Ngưỡng độ tin 0,6 đặt tay, chưa hiệu chỉnh (độ tin do model tự báo) | Còn |
| K.4 | Chỉ đọc 8 đơn vị đầu (mỗi đơn vị 800 ký tự): hợp đồng có phần đầu dài (mục lục, định nghĩa) có thể thành unknown | Còn |
| K.5 | Mặc định khi không có gói (`ctx` None) các prompt vẫn ghi "hợp đồng lao động" (tương thích luồng cũ); mọi luồng có gói đã lấy nhãn từ gói | Còn |
| K.6 | "Tagger theo kind": prompt vẫn một mẫu chung, khái niệm mô tả bằng dữ liệu (đã vậy từ trước), nay kèm `kind`; chưa dựng slot từ kind (kinds.yaml chỉ có loại slot, không có tên slot) | Có chủ ý |
| K.7 | Định dạng `fact_catalog.json` viết lại một dòng mỗi trường (nội dung cũ không đổi) | Có chủ ý |

## H3 — đồ thị luật cho luật mới (23/11, Tùng nhận phần của Huy)

Đồ thị luật dựng tổng quát từ mọi văn bản trong snapshot (cấu trúc, `REFERS_TO`, `GUIDES`, phiên bản): BLDS 91/2015,
33/2005, Luật Nhà ở 65/2014, 27/2023 đã có sẵn. Thiếu Luật Các TCTD 32/2024 và NQ 01/2019/NQ-HĐTP (gói vay dẫn tới):
đã tải từ trước (`supplements/loan-scope-v1`) nhưng chưa nạp -> thêm `rag.legal.supplement.import_supplement` +
lệnh `python -m rag.legal import-supplement <fetch-report.json>` và nạp vào snapshot **s20261123063951-32c3b6**
(cha: s20261117024643-c06f0c, giữ nguyên). Test `tests/test_pack_anchors_legal_graph.py`: 114 tham chiếu (neo + nguồn
kỳ giá trị) và mọi `value_sources` giải được trên đồ thị, nguồn kỳ giá trị có hiệu lực giao với kỳ. Neo phải sửa: 0.

| # | Mục | Trạng thái |
|---|---|---|
| G.1 | Neo4j không chạy trên máy: snapshot mới CHƯA đồng bộ vào Neo4j (`python -m rag.legal graph build` khi bật LEGAL_GRAPH=1); kiểm tra dùng bản dựng Python thuần | Đã đồng bộ (S.22) |
| G.2 | Quay lại snapshot cũ: ghi `s20261117024643-c06f0c` vào `app/team-4.2/data/team-4.2/legal/CURRENT` (dữ liệu gitignore, chỉ trên máy này) | Ghi chú |
| G.3 | ~~Luật Thương mại 36/2005 và Luật BVQLNTD 19/2023/QH15 chưa tải~~ -> đã tải và nạp (mục K bên dưới) | Đã xử lý |
| G.4 | 26 văn bản bổ sung lao động (`supplements/labor-scope-v1-26`) vẫn chưa nạp (README ghi cần duyệt PDF/phụ lục); không nạp ở đây | Còn |
| G.5 | Kiểm "hiệu lực trong kỳ" chỉ cho nguồn của kỳ giá trị luật; neo thường chỉ kiểm có phiên bản (không gắn ngày) | Còn |
| G.6 | Hai văn bản mới dựng phiên bản theo đường tự động (`build_all`); chưa ai duyệt mục cần duyệt của chúng (nếu có) trên trang /review | Còn |

## K — tải luật còn thiếu cho gói thương mại / người tiêu dùng / dân sự (23/11)

Script tải chung `scripts/team-4.2/fetch_scope.py --queue <hàng đợi> --staging <thư mục>` (dùng lại `fetch_one` của
`fetch_labor_scope.py`; thêm loại `Quyết định`; `discovered_via` = `scope_version` của hàng đợi, không gán cứng).
- Hàng đợi `commerce-consumer-scope-fetch-queue.json`: LTM 36/2005/QH11, Luật BVQLNTD 19/2023/QH15 -> snapshot
  **s20261123065841-cadf82**.
- Hàng đợi `contract-guidance-scope-fetch-queue.json`: NĐ 55/2024 (hướng dẫn BVQLNTD), QĐ 07/2024/QĐ-TTg (danh mục
  phải đăng ký hợp đồng theo mẫu), Luật Trọng tài thương mại 54/2010, NQ 01/2014/NQ-HĐTP, Luật Quản lý ngoại thương
  05/2017 (kiểm điều LTM bị bãi bỏ), NĐ 95/2024 (Luật Nhà ở), NĐ 96/2024 (KDBĐS) -> snapshot **s20261123071410-54f166**.
- Quay lại: ghi `s20261123063951-32c3b6` (trước K) hoặc `s20261123065841-cadf82` vào `CURRENT`.

| # | Mục | Trạng thái |
|---|---|---|
| K.1 | VBPL không có văn bản hợp nhất của LTM 36/2005. Đã kiểm Luật QLNT 05/2017 Đ113 k3: chỉ bãi bỏ k3 Đ28, k3 Đ29, k3 Đ30, Đ31, 33, 242–247 — không chạm phần hợp đồng (Đ24–87) và chế tài (Đ292–316). Các luật sửa đổi khác của LTM (nếu có) chưa rà | Còn (rà thêm) |
| K.2 | QĐ 07/2024/QĐ-TTg: chỉ có thân văn bản; **danh mục** nằm ở phụ lục .docx mà API VBPL không trả nội dung -> chưa có danh mục ngành phải đăng ký hợp đồng theo mẫu | Còn |
| K.3 | Luật Thương mại điện tử 122/2025/QH15 (hiệu lực 01/7/2026) chưa tải (giao kết hợp đồng trên sàn; không cần cho kiểm văn bản hợp đồng) | Có chủ ý |
| K.4 | Neo4j vẫn chưa đồng bộ hai snapshot mới (G.1) | Còn |
| K.5 | Văn bản nạp theo đường tự động `build_all`; chưa duyệt mục cần duyệt trên /review (như G.6) | Còn |

## M — xây gói luật đầy đủ: phần dân sự (23/11)

Cách làm mỗi quy định: đọc nguyên văn điều luật -> mục bản liệt kê (trích nguyên văn, ngoại lệ, ví dụ) -> YAML -> hợp đồng
mẫu + nhãn đúng viết trước khi chạy engine. Thêm test `tests/test_rule_inventory_examples.py`: mọi ví dụ của bản liệt kê
(viết từ luật) chạy qua engine thật (reference + network). Quy định đã đọc mà không làm rule được ghi lý do ở cuối từng
tệp bản liệt kê.

| # | Mục | Trạng thái |
|---|---|---|
| M.1 | `civil_general`: 1 -> 5 khái niệm / 6 rule: hủy bỏ phải thông báo (Đ423.3), hợp đồng theo mẫu / điều kiện giao dịch chung miễn trách bên soạn (Đ405.3, Đ406.3; hỏi người dùng có phải hợp đồng mẫu không), sửa đổi theo hình thức ban đầu (Đ421.3), lãi chậm trả (Đ357.2) | Xong, đã duyệt (tùng, 24/11) |
| M.2 | `loan.late_interest_cap` **đổi tên** thành `civil.late_payment_interest_cap` và chuyển lên gói chung (Đ357 áp mọi nghĩa vụ trả tiền, cả tiền thuê). Nhãn gold vay chỉ đổi tên rule, không đổi kết luận | Xong (báo Tùng) |
| M.3 | `civil_loan`: thêm vay không kỳ hạn có lãi phải báo trước khi đòi (Đ469.2); trỏ lại các mục bản liệt kê đã có rule; Đ470.2 (cấm trả trước hạn khoản vay có lãi) chưa làm, chờ Tùng chọn cách đọc | Xong / chờ |
| M.4 | `civil_lease`: thêm họ tên + địa chỉ các bên (Đ163.1), ngày ký (Đ163.10), bên cho thuê sửa hư hỏng lớn (BLDS Đ477.1), bảo đảm sử dụng ổn định (BLDS Đ478.1). Hai rule BLDS là **cách đọc của người soạn** (luật không nói điều khoản trái là vô hiệu): cần Tùng duyệt | Đã duyệt (Tùng, 24/11) |
| M.5 | Hợp đồng thuê mẫu t1–t6 thêm dòng địa chỉ giả cho các bên (không đổi câu trích cũ); thêm t8–t10; gold thuê 30 -> 52 nhãn (22 nhãn mới chờ duyệt); t7 thêm 1 vi phạm (vào nhà không báo trước) | Đã duyệt (Tùng, 24/11) |
| M.6 | Ví dụ bản liệt kê cũ viết lỏng (thiếu đơn vị, tên dữ kiện không khớp slot, ngày ghi thành dữ kiện) đã sửa theo quy ước của test mới; kết luận pháp lý không đổi | Xong |
| M.7 | Không làm rule (đã ghi lý do): giao kết, giải thích hợp đồng, công khai mẫu, thời hiệu Đ429, nội dung k6–k9, k11 Đ163, trả nhà 'như mới' (Đ482.1 cho thỏa thuận), mất cọc khi chấm dứt đúng căn cứ (L.14) | Ghi nhận |
| M.8 | Rule BLDS (Đ477, Đ478, Đ357) gắn với BLDS 2015; hợp đồng thuê ký trước 01/01/2017 vẫn được xét theo câu chữ BLDS 2015 (rule không có giá trị theo kỳ) | Đã sửa (S.1, 24/11) |

## N — gói `consumer` (Luật BVQLNTD 2023, 23/11)

| # | Mục | Trạng thái |
|---|---|---|
| N.1 | Gói `consumer` (extends `civil_general`): 26 khái niệm / 26 rule: 14 điều khoản cấm Đ25.1–14, 10 nội dung cơ bản của hợp đồng theo mẫu Đ23.3 (chỉ áp khi người dùng xác nhận là hợp đồng mẫu), dịch vụ liên tục: ngừng dịch vụ (Đ41.3), báo trước khi hết hạn (Đ42.2.đ, e) | Xong, đã duyệt (tùng, 24/11) |
| N.2 | 6 hợp đồng mẫu c1–c6, 52 nhãn viết tay ở `labels.yaml` trước khi chạy engine; gold sinh bằng `scripts/team-4.2/gold_from_labels.py`; test chung `tests/test_rete_pack_fixtures.py` (dùng lại cho gói thương mại) | Đã duyệt (Tùng, 24/11) |
| N.3 | Nhận diện tự động chọn MỘT loại hợp đồng: gói `consumer` chỉ tự chạy khi văn bản được nhận là `consumer_contract`; chồng lên thuê / vay phải truyền `packs=[..., "consumer"]` | Còn (thiết kế) |
| N.4 | Cùng một điều khoản có thể ra hai FAIL: `civil.standard_terms_exemption` (BLDS Đ405.3 / 406.3) và `consumer.liability_exclusion` (Đ25.1) — hai căn cứ cùng đúng; chưa gộp | Đã sửa ở lớp trình bày (S.15) |
| N.5 | Không làm: Đ25.15 (thiện chí, tiêu chí chung), Đ23.2 + NĐ 55/2024 Đ6 (tiếng Việt, cỡ chữ 12, màu tương phản), đăng ký hợp đồng mẫu (Đ28, danh mục QĐ 07/2024 ở phụ lục chưa tải được), ngoại lệ "pháp luật liên quan cho phép" của Đ25.1, 6, 11 | Ghi nhận |
| N.6 | Hợp đồng ký trước 01/07/2024 theo Luật BVQLNTD 59/2010/QH12 (chưa tải); gói không phân kỳ | Đã sửa phần không kết luận sai (S.1); soát theo Luật 59/2010 vẫn chưa có |
| N.7 | Đ25.12 (chế tài bất lợi hơn) và c6 (mất cọc một chiều) là cách đọc của người soạn | Đã duyệt (Tùng, 24/11) |

## O — gói `commercial` (Luật Thương mại 2005, 23/11)

| # | Mục | Trạng thái |
|---|---|---|
| O.1 | Gói `commercial` (extends `civil_general`, loại `commercial_sale_contract`, `commercial_service_contract`): trần phạt 8% (Đ301), thông báo ngay khi tạm ngừng / đình chỉ / hủy bỏ (Đ315), lãi chậm thanh toán theo Đ306 là **ngoại lệ** của trần BLDS Đ357.2 (NQ 01/2019 Đ11) qua dữ kiện suy ra hằng `ltm_governs` | Xong, đã duyệt (tùng, 24/11) |
| O.2 | Cách đọc "trần 20% BLDS không áp cho lãi chậm trả trong hợp đồng thương mại" là của người soạn theo NQ 01/2019 Đ11 | Đã duyệt (Tùng, 24/11) |
| O.3 | Phần lớn LTM về mua bán (Đ34–62) và dịch vụ (Đ78–87) là mặc định hoặc sự kiện khi thực hiện: gói thương mại nhỏ (3 khái niệm) là đúng với luật, không phải thiếu sót; lý do từng điều ở cuối `docs/rule_inventory/commercial.yaml` | Ghi nhận |
| O.4 | Phạt tính trên TOÀN BỘ giá trị hợp đồng hoặc phạt theo ngày không có trần: chưa kiểm (cần giá trị phần bị vi phạm / số ngày); ngoại lệ Đ266 (giám định) chưa làm | Còn |
| O.5 | Luật Trọng tài thương mại: không có rule riêng cho thương mại (Đ16, 18 là sự kiện ngoài văn bản); Đ17 (người tiêu dùng vẫn được chọn Tòa án) gắn làm neo cho `consumer.complaint_right` | Ghi nhận |
| O.6 | 4 hợp đồng mẫu m1–m4, 10 nhãn viết trước khi chạy engine | Đã duyệt (Tùng, 24/11) |
| O.7 | Gộp `labor` / `civil_loan` với `commercial` (packs=[...]) sẽ gỡ trần lãi chậm trả BLDS cho cả hợp đồng đó: chỉ chồng `commercial` khi hợp đồng thật sự thuộc LTM | Ghi nhận |

## Tồn đọng chung (môi trường, quy trình)

| # | Mục | Trạng thái |
|---|---|---|
| E.1 | Toàn bộ suite có **35 test fail có sẵn** (lần chạy sau H1 dossier_objects 23/11: 35 fail cùng 6 file sau khi sửa 2 test do dữ kiện mới job_title) từ trước (nhóm `test_agent_stability`, `test_answer_presentation`, `test_conversation`, `test_dated_agent_e2e`, `test_pipeline`, `test_warehouse_migration`); danh sách tên ở `phase1_baseline.md`. Số fail không đổi sau giai đoạn 1, 2, 3 | Còn, không phải do engine |
| E.2 | `tests/test_agent_partial_review.py` lỗi import có sẵn; phải chạy với `--ignore` | Còn |
| E.3 | `test_warehouse_migration.py::test_both_modes_fail_closed_if_catalog_is_unavailable` chỉ fail khi chạy chung nhóm (phụ thuộc thứ tự), riêng thì pass | Còn |
| E.4 | `test_bridge_tagger.py::test_failed_batch_warns_and_others_continue` fail một lần khi chạy nhóm với `RAG_RULE_EVALUATOR=reference`; sau đó xanh 3 lần riêng và 2 lần nhóm (flaky) | Còn |
| E.5 | Toàn bộ suite mất khoảng 10 phút; chạy nền | Có chủ ý |
| E.6 | Spec §4.2 ghi "chưa xác minh" việc xử lý phủ định trong bài gốc TREAT; checklist A1 chưa tick | Còn |
| E.7 | Chưa merge, chưa push; việc tích hợp là quyết định của người dùng | Chờ quyết định |
| E.8 | Nhánh có thay đổi cũ không phải của phiên này (`reports/week-02`, `week-03` README, các thư mục dữ liệu chưa theo dõi); không đưa vào commit nào | Có chủ ý |
| E.9 | Giai đoạn 6 (benchmark) chờ Khánh; giai đoạn 7 đã xong phần engine | Chờ |

## P. Prompt và danh mục dữ kiện theo kịp các gói (23/11)

- Các prompt (gán khái niệm, kiểm lại, agent) đã được tham số hóa theo `document_label` của gói từ trước; không còn chữ "lao động" cứng.
- Đã sửa: `fact_catalog.json` thiếu `consumer_contract`, `commercial_*` nên hợp đồng loại này rơi về đoán theo chữ loại (một hợp đồng
  tiêu dùng có chữ "thuê" sẽ bị gán trường của hợp đồng thuê nhà). Nay ánh xạ về `common`.
- Đã sửa: prompt gán khái niệm chỉ nêu 3 kind; nay nêu đủ kind đang dùng và cách đọc slot bool của `prohibited_practice`, `void_term`,
  `termination`. `TAG_PROMPT_VERSION` = `concept-tag-5`.
- CHƯA có: kiểm bằng model thật. Test chỉ kiểm nội dung prompt và ánh xạ, không chạy LLM trên 13 hợp đồng mẫu mới; chất lượng gán khái
  niệm của gói `consumer` (26 khái niệm) và `commercial` còn phải đo bằng model thật.
- `verify.catalog_type` vẫn đoán theo chữ "lao động" / "thuê" khi không có loại do `classify_contract` nhận diện (cách cũ, giữ nguyên).

## Q. Đo và eval (phần Khánh K1–K3, Claude làm theo yêu cầu Tùng, 23/11)

Kế hoạch: `app/team-4.2/docs/superpowers/plans/2026-11-23-khanh-ingest-bench-eval.md`. K4 (router chat) không làm.

- Q.1 (K1) `evals/team-4.2/results/w04-rule-engine/legal_ingest.md`: snapshot `s20261123071410-54f166`, 11/11 văn bản có trong kho, ngày hiệu lực khớp.
  Kho nằm ở `app/team-4.2/data/team-4.2/legal` (script phải chạy từ `app/team-4.2`); `data/team-4.2/legal/CURRENT` ở gốc repo là
  bản cũ chưa theo dõi, không dùng.
- Q.2 (K1) Chuỗi sửa đổi chưa đủ: vbpl ghi LTM 36/2005, NĐ 95/2024, NĐ 96/2024 "hết hiệu lực một phần" nhưng kho chưa có thao tác hay
  quan hệ nào trỏ tới (chưa nạp văn bản sửa đổi). Các điều đang dùng (LTM Đ301, 306, 315) có thể đã bị sửa mà kho chưa biết — Còn.
- Q.3 (K1) NQ 01/2014: Điều 19 ghi hiệu lực từ 02/07/2014, khớp kho; đã điền ngày kỳ vọng. Nghiệm thu "Huy dựng được đồ thị": báo cáo có cột
  "Node đồ thị" (dựng từ snapshot hiện hành bằng `build_current`, chỉ trong bộ nhớ, không công bố Neo4j): 11/11 văn bản có node, 0 lỗi kiểm tra.
  Chưa kiểm phía Neo4j thật (cần LEGAL_GRAPH=1) — Còn. Chuỗi sửa đổi (Q.2): crawl vbpl.vn cần người dùng cho phép — chưa chạy.
- Q.4 (K3) `evals/team-4.2/results/w04-rule-engine/eval/summary.md`: 11 thư mục hồ sơ mẫu, 166 nhãn gold. `reference` và `network` đúng 166/166.
  Engine cũ (`rag.bridge.engine.evaluate`) thiếu 18 nhãn, toàn là rule xuyên đối tượng (nó không nhận đối tượng hồ sơ) — đúng thiết kế,
  không phải lỗi. Lưu ý: 0 ca sai một phần do gold được viết song song với engine mới. Tùng đã duyệt gold a1, b1–b5, vay, thuê,
  consumer, commercial (24/11); gói vay (12 nhãn) và thương mại (10 nhãn) vẫn mỏng, cần thêm ca khó.
- Q.5 (K3) Nhận diện loại bằng `classify_contract` (model thật, 23/11): 34 văn bản chính, 33 lần gọi LLM (hai văn bản trùng nội dung),
  0 chọn sai miền. Đệm ở `evals/team-4.2/results/w04-rule-engine/eval/classify_cache.json`. Mẫu nhỏ và mỗi miền chỉ có văn bản "đúng kiểu", chưa có
  văn bản lai (vd. hợp đồng thuê có một bên là người tiêu dùng) — Còn.
- Q.6 (K2) `evals/team-4.2/results/w04-rule-engine/bench/`: chạy đầy đủ seed 0 (260 dòng, 0 ca lệch giữa hai evaluator). Network nhanh hơn rõ ở cập nhật tăng dần
  (≈100× ở 10.000 rule, 1 dữ kiện) và `next_questions` (≈20×); ngang `reference` ở lần đánh giá đầu và khi dùng chung cho nhiều hồ sơ; tốn
  chi phí biên dịch (140–160 ms ở 10.000 rule). Một lần chạy trên một máy, chưa lặp nhiều lần — Còn. Lỗi nhỏ để lại: kịch bản 4 của gói
  `labor` lặp ~15 hồ sơ mẫu cho đủ 100; "tính lại" gồm cả lần khởi động; gold bộ hợp đồng lẻ trỏ sai tên/nhiều kỳ bị bỏ không báo; eval
  chưa đếm FAIL ngoài gold; bảng chọn gói chỉ nhận hợp đồng chính đầu tiên của hồ sơ; tính lặp lại của bảng bench mới kiểm trong cùng
  một tiến trình; báo cáo K1 lấy ngày chạy nên số Điều có thể đổi; đệm classify không gắn phiên bản prompt (đổi prompt phải xóa đệm);
  cột net/ref kịch bản 1 vô nghĩa khi `reference` ≈ 0 ms. Lệnh gate có thêm `tests/test_legal_ingest_report.py tests/test_bench_*.py`
  (692 passed, 1 skipped, 1 xfailed, cả hai chế độ evaluator); `tests/test_agent_partial_review.py` lỗi import từ trước, không liên quan.

- R.1 (D40) Sửa kèm: `check_contract(document_kind="auto")` ghi `facts["document_kind"]` trước bước trích nên hợp đồng chưa có dữ kiện bị bỏ qua bước trích; nay loại không tính là dữ kiện đã trích. UI nhận diện trước khi dựng nền luật (basis) vì `check_contract` tự dựng basis không có đồ thị luật.
- R.2 (D34) Nhãn dữ kiện / kết luận nằm trong `labels` của `pack.yaml`; nhãn của `civil_general`, `civil_loan`, `civil_lease`, `consumer`, `commercial` do Claude viết từ tên dữ kiện và câu hỏi của gói — Tùng đã duyệt (24/11). Studio: dữ kiện không có nhãn hiện trống (như cũ) trong sơ đồ, hiện tên gốc trong báo cáo — Còn (chưa đồng nhất).
- R.3 (E3) `rag/rules/scenario.py` đọc hồ sơ từ `tests/fixtures/rete` (mặc định) — chạy ngoài môi trường dev cần đổi `DOSSIER_ROOT`. Bản đọc hồ sơ trùng logic với `tests/test_rete_dossiers.py` (chưa gộp). Hồ sơ vay / thuê / tiêu dùng / thương mại là bộ lẻ, chưa có `scenario.yaml` nên chưa chạy bằng route này — Còn. (Thư mục hồ sơ và bản đọc trùng: đã sửa, S.10.)
- R.4 (K1) Chuỗi sửa đổi LTM 36/2005, NĐ 95/2024, NĐ 96/2024: cần `python -m rag.legal crawl` (tải vbpl.vn, ghi snapshot mới vào kho dùng chung), chưa chạy vì cần Tùng cho phép — Còn. Đồ thị luật chỉ kiểm bản dựng trong bộ nhớ, chưa kiểm với Neo4j thật — Còn.
- R.5 Gate sau D34/D40/E3 (`tests/test_rules_*`, `test_bridge_*`, các test contract/graph/pack, `test_contract_studio`, `test_rete_dossiers`, `test_scenario_runner`, `test_dossier_sse`, `test_legal_ingest_report`, `test_bench_*`): 1017 passed, 2 skipped, 16 xfailed ở cả hai chế độ (network và reference).
- R.6 (D40, duyệt cuối) `extract_fields` của gói (vd. `loan_interest` của `civil_loan` để suy `has_interest`) không đi vào luồng UI: upload trích dữ kiện trước khi biết loại hợp đồng, rồi `check_contract` bỏ qua bước trích vì đã có dữ kiện. Hợp đồng vay tải lên qua UI vì vậy thiếu `has_interest` (rule dùng nó ra `needs_facts`). Cần quyết định thiết kế: trích bổ sung chỉ các trường còn thiếu sau khi chọn gói (cần chế độ trích gia tăng cho `extract_facts`, tốn thêm lời gọi LLM) — Đã sửa (S.8; ví dụ hợp đồng vay ở đây sai, xem S.8).
- R.7 (D40, duyệt cuối) Đổi loại hợp đồng nhận diện sai: có qua API (`document_kind` trong body của `concept-check` và `concept-check/stream`, phải là loại có gói; được lưu) nhưng UI chưa có chỗ chọn; loại `unknown` được lưu để hỏi đáp báo 400 và lần soát sau nhận diện lại — Còn (UI).
- R.8 (duyệt cuối, lỗi nhỏ hoãn) `scenario.yaml` hỏng (thiếu khóa, bước add/remove/answer trước load) ra 404/500 thay vì 400; `set_review_date` dựng phiên mới nên `nodes_recomputed` là cả mạng; `did` chưa kiểm với `list_dossiers()`; mọi lần `catalog_for` đọc cả 7 `pack.yaml` (chỉ `_packs_catalog` có đệm); `labels.facts` không kiểm khóa; loại `unknown` không kiểm dữ kiện người dùng (chưa có test); `document_kind` lọt vào payload báo cáo LLM; lỗi kiểm tra đồ thị luật (K1) chỉ in stderr, không vào báo cáo / mã thoát.

## S — đợt 1 xử lý hạn chế (24/11, plan `2026-11-24-w04-han-che-dot-1.md`)

| # | Mục | Trạng thái |
|---|---|---|
| S.1 | Luật chưa có hiệu lực khi ký (7.23, M.8, N.6): `in_force: {from, earlier_contracts}` trong concepts.yaml (gói, ghi đè ở khái niệm), đọc từ điều khoản chuyển tiếp: labor `apply` (BLLĐ Đ220.2); civil_general, civil_loan, consumer, 2 rule BLDS của gói thuê `conforming_only` (BLDS Đ688.1, BVQLNTD Đ80.1: hợp đồng cũ chỉ được PASS, FAIL thành NOT_APPLICABLE `earlier_law_governs`); civil_lease, commercial `skip`. Mặc định `skip` từ `law_values_valid_from`. Rule có `periods` không nhận mốc của gói (kỳ tự quyết). Báo cáo có cảnh báo đếm rule bị bỏ và nêu khái niệm cần soát theo luật cũ. Golden không đổi | Đã sửa |
| S.2 | `conforming_only` dùng ngày ký làm mốc; Đ688.1 còn chia "chưa thực hiện / đang thực hiện / đã xong" và cho các bên thỏa thuận áp luật mới — engine không xét (cùng V.4) | Còn |
| S.3 | BVQLNTD Đ80.2: hợp đồng theo mẫu công khai trước 01/07/2024 phải sửa cho phù hợp trước 31/12/2024 — với ngày soát sau 2024 thì luật mới áp cả cho mẫu cũ; engine soát theo ngày ký nên chưa thể hiện | Còn |
| S.4 | Kho có BLDS 33/2005 nhưng thiếu điều hiệu lực cuối; trần lãi trước 01/12/2010 vẫn UNKNOWN (V.3), không khai mốc riêng | Ghi nhận |
| S.5 | Labor `apply` theo Đ220.2 nhưng engine labor vẫn soát theo ngày ký (giá trị luật kỳ trước 2021 không có -> UNKNOWN); soát theo ngày soát cho HĐLĐ đang thực hiện chưa làm | Còn |
| S.6 | 3.7: `derived.conflicted_inputs` (cùng bộ duyệt với `missing_inputs`): dữ kiện suy ra chưa xác định vì đầu vào CONFLICT -> finding `conflict`; Network cập nhật đúng khi đầu vào hết mâu thuẫn | Đã sửa |
| S.7 | Bộ nạp: tệp không phải dict, `concepts` / `slots` / `rules` sai kiểu -> CatalogError nêu tệp; phần sai hình dạng còn lại bắt ở ranh giới YAML (`_shape_guard`) thay vì AttributeError / TypeError (1.4). `Catalog.version` = `<gói>@<version pack.yaml>/<version concepts.yaml>` nối `+`, cả `load_catalog` (1.5; đổi chuỗi version trong báo cáo và thao tác). Dữ kiện suy ra `value: null` bị từ chối (3.8); `from` khác đơn vị đã khai: bộ nạp kiểm quy đổi được, lúc chạy đổi về đơn vị đã khai, không đổi được -> UNKNOWN (3.11) | Đã sửa |
| S.8 | R.6: ví dụ "hợp đồng vay thiếu `has_interest`" là **sai** — `loan_interest` đã có trong danh mục chung `fact_catalog.json` (loại `loan`, commit H2) nên được trích lúc tải lên. Lỗ hổng thật là tổng quát: trường `extract_fields` của gói không chép vào `fact_catalog.json` không bao giờ được trích sau lúc tải lên. Nay `extract_facts` ghi `fields_tried`; `check_contract` khi đã có dữ kiện gọi `extract_more_fields` cho trường của gói chưa hỏi (chỉ hỏi các trường đó, không đụng bên / ngày ký), một lần; lỗi LLM -> cảnh báo, soát vẫn chạy. Dữ kiện cũ chưa có `fields_tried` coi như đã hỏi danh mục chung | Đã sửa |
| S.9 | Trích bổ sung đọc lại mọi lô của hợp đồng (số lời gọi LLM = số lô) dù chỉ hỏi một trường | Có chủ ý (đơn giản; tối ưu khi cần) |
| S.10 | R.3 + R.8: thư mục hồ sơ đọc từ `RAG_DOSSIER_ROOT` (mặc định bộ mẫu trong tests); `tests/test_rete_dossiers.py` dùng chung `scenario.load_dossier` / `objects_of` / `facts_at`. Kịch bản hỏng (không phải danh sách, bước đầu không phải load, thiếu `review_date` / `value` / `state` / `facts`) -> ValueError trước mọi sự kiện (route 400); mã hồ sơ lạ hoặc có đường dẫn (`../b1`) -> `UnknownDossier` (404). `labels.facts` có khóa không phải dữ kiện của gói -> CatalogError (các gói thật đều qua). `packs_for_kind` đệm theo thời điểm sửa `pack.yaml`. `document_kind` / `fields_tried` không gửi cho LLM tóm tắt (`INTERNAL_FACT_KEYS`) | Đã sửa |
| S.11 | R.8 còn lại: `set_review_date` dựng phiên mới (`nodes_recomputed` = cả mạng); lỗi kiểm tra đồ thị luật K1 chỉ in stderr; loại `unknown` không kiểm dữ kiện người dùng (chưa có test riêng) | Còn |
| S.12 | Gate đợt 1 (danh sách mở rộng: thêm `test_three_domains`, `test_contracts_review`, `test_rules_in_force`, `test_rules_loader_shapes`, `test_typed_values`, `test_report_grouping`): 1827 passed, 1 skipped, 1 xfailed ở cả network và reference (sau S.15) | Ghi nhận |
| S.13 | V.9: đơn vị trong `norm` phải có trong câu trích: thời hạn theo bảng cách viết lõi `quantity.DURATION_WORDS` (+ `unit_forms` của gói), kỳ của tỉ lệ theo `unit_forms` của gói (gói không khai cách viết thì không chặn). Thiếu -> không đọc (slot `pending`, như số không có căn cứ) | Đã sửa |
| S.14 | Kiểm đơn vị là "có trong câu trích", không ràng buộc đúng vị trí sau con số: câu có cả "12 tháng" và "30 ngày" vẫn cho qua LLM ghi nhầm 12 ngày; "năm" trong ngày tháng ("năm 2024") làm kiểm đơn vị năm yếu | Còn |
| S.15 | N.4, 3.9, 7.22 (lớp trình bày, `RuleResult` không đổi): `shared_clauses` nhóm FAIL của từ hai khái niệm trên cùng điều khoản (JSON `shared_clauses`, markdown mục "Một điều khoản vi phạm nhiều quy định"); `presence_only` đánh dấu PASS chỉ vì khái niệm có mặt (`stats.presence_only`, markdown đếm riêng). UI (Contract Studio, luồng SSE `evaluation`) chưa dùng hai trường này để ẩn / gộp | Đã sửa phần dữ liệu; UI còn |
| S.16 | Q.2 / R.4 (Tùng cho phép crawl 24/11): sửa discovery hai chỗ rồi crawl có giới hạn (seed chỉ LTM 36/2005, NĐ 95/2024, NĐ 96/2024). (1) Văn bản dưới luật nhận văn bản cùng loại sửa đổi nó (nghị định sửa nghị định). (2) Văn bản sửa nhiều văn bản mà tiêu đề không nêu văn bản gốc vẫn được xét nếu tìm thấy theo số hiệu; đích đọc từ tiêu đề Chương (`directives.chapter_targets`, dùng ở discovery, lập thao tác, upload). Snapshot mới **s20261123190511-f86917** (CURRENT; quay lại: s20261123071410-54f166). Thêm: Luật 75/2025/QH15 sửa LTM (Đ4.2 thay, bãi bỏ Mục 2 Chương IV quảng cáo), NĐ 54/2026/NĐ-CP sửa NĐ 95/2024 và 96/2024, NĐ 02/2022 (bị NĐ 96/2024 thay). **Kết luận: LTM Đ301, 306, 315 (gói thương mại) không bị sửa** — 05/2017 (Đ28–31, 33, 242–247), 44/2019 (cụm từ Đ100.4, 109.4), 75/2025 (Đ4.2, Mục 2 Chương IV) | Đã xử lý |
| S.17 | Luật 44/2019/QH14 (sửa cụm từ LTM) chưa vào kho: discovery chưa đi theo câu "đã được sửa đổi, bổ sung theo Luật số …" trong tiêu đề chỉ dẫn của văn bản sửa đổi (chỉ đi theo câu đó ở Điều hiệu lực); đã đọc tay trên vbpl, không chạm điều gói dùng | Còn |
| S.18 | Thao tác sửa đổi mới: NĐ 95/2024 24 thao tác (14 failed, 9 partial), NĐ 96/2024 21 (9 failed, 5 unsupported); thao tác bãi bỏ Mục 2 Chương IV LTM failed (`unparsed_header`). Chờ duyệt trên /review; các gói không neo vào NĐ 95/96 nên kết luận rule không đổi. Neo4j vẫn chưa đồng bộ (G.1) | Còn |
| S.19 | P / V.6 (Tùng cho phép chạy LLM thật 24/11): `scripts/eval_concept_tagging.py` chạy `check_contract(packs=[gói])` thật (trích dữ kiện: LLM app `gpt-6-luna`; gán khái niệm: `anthropic/claude-haiku-5.5`) trên 10 hợp đồng mẫu, so với `facts.yaml` + `gold.yaml`. Kết quả ở `evals/team-4.2/results/w04-rule-engine/tagging/summary.md`. commercial (4): recall khái niệm 1.0, precision 0.786, slot 11/11, rule 10/10, 0 FAIL thừa. consumer (6): recall 1.0, slot 18/18, rule **50/52 -> 52/52** sau khi thêm `not_about` cho `consumer.content_termination` (Haiku gán nhầm câu "không được chấm dứt khi đổi giá" và câu "kết thúc khi hoàn thành nghĩa vụ"); 2 FAIL ngoài gold còn lại là hai căn cứ cùng đúng cho một điều khoản (c3 Đ25.3 + Đ25.7, c6 Đ25.1 + Đ25.9 — kiểu N.4, báo cáo đã nhóm `shared_clauses`) | Đã đo |
| S.20 | Precision khái niệm thấp (consumer 0.651) chủ yếu vì gold chỉ liệt kê khái niệm có rule áp dụng: hợp đồng không phải mẫu (c2, c5, c6) có điều khoản `content_*` thật nhưng gold không ghi. Mỗi hợp đồng chạy **một lần** (LLM không tất định), một cặp model; chưa thử model nhỏ (Qwen) theo định hướng trích bằng model nhỏ; đệm LLM theo prompt nên đổi prompt / gói là gọi lại | Còn |
| S.21 | Gold `facts.yaml` ghi chữ gốc ("12%"); chấm slot phải chuẩn hóa gold bằng `normalize_slot` như luồng thật (lần chấm đầu so chữ với số nên ra 3/11 sai) | Ghi nhận |
| S.22 | Neo4j (G.1, K.4, R.4) đồng bộ 24/11: `python -m rag.legal graph build` từ snapshot s20261123190511-f86917 (graph_build 5ce182835181db9e, stale=false); `graph check`: 0 lỗi, 0 vấn đề. Cạnh: 53 AMENDS, 55 REPLACES, 74 REPEALS, 38 GUIDES, 20250 REFERS_TO (1187 trỏ văn bản chưa có trong kho, 1223 không tìm thấy điều). Test neo gói / báo cáo K1 xanh. Kiểm tra với Neo4j thật là lần đầu, trước đó chỉ dựng trong bộ nhớ | Đã sửa |
| S.23 | Duyệt thao tác sửa đổi (S.18, G.6; Tùng yêu cầu 24/11): duyệt nguyên trạng mọi mục của NĐ 54/2026 và Luật 75/2025 mà `decide` cho phép: **11 duyệt** (`approved`), **33 không duyệt được** — 27 chưa xác định đơn vị đích (`target_unresolved`, vd. "Sửa đổi điểm …" không nêu điều khoản), 6 sửa phụ lục / bảng (chưa hỗ trợ), gồm bãi bỏ Mục 2 Chương IV LTM. Các mục này cần "Sửa lại" thủ công (nêu đích, nội dung) trên /review; không đoán thay người duyệt. Snapshot mới s20261123194403-83cf3b, Neo4j đã dựng lại (stale=false). Toàn kho còn ~1100 thao tác pending của các luật khác (G.6), không đụng | Một phần |
