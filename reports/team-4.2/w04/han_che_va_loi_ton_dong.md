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
