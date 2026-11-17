# Soát hợp đồng lao động theo danh mục khái niệm (phía hợp đồng, bản cơ bản)

Ngày: 2026-11-14. Bản nháp 1. Người làm: A (Tùng).

Tài liệu liên quan:
- Danh mục: `src/rag/bridge/concepts.yaml` (39 khái niệm, P0 + P1).
- Phía luật: `2026-11-14-legal-graph-concept-layer-design.md` (LU, hàm `concept_basis`).
- Đồ thị hợp đồng: `2026-11-12-contract-scale-design.md` (§6.1 lớp ngữ nghĩa, §7.3–7.8 `ASSERT`). Bản này là
  phiên bản rút gọn của bước 7 trong đó, xoay quanh danh mục khái niệm thay cho mệnh đề tự do.
- Che PII: `2026-11-14-pii-model-masking-design.md`.

## 1. Vì sao làm

Mục tiêu sản phẩm: đọc một HĐLĐ, chỉ ra (a) điều khoản trái luật hoặc bất lợi, (b) nội dung bắt buộc bị thiếu,
(c) quyền mà luật cho nhưng hợp đồng không nhắc ("quyền ẩn"), mỗi kết luận kèm trích dẫn hợp đồng và khoản luật
tại ngày ký.

Hiện `review.py` để LLM tự tìm vấn đề trên toàn văn. Cách này không kiểm thử được, không biết đã soát những gì,
và không phát hiện được thứ hợp đồng không nói. Bản này thay bằng: LLM chỉ **nhận diện** điều khoản theo danh mục
đóng, còn **kết luận** do rule tất định đưa ra.

## 2. Mục tiêu, ngoài mục tiêu, điều phải tránh

**Mục tiêu**
- Rule engine logic ba trị chạy trên `concepts.yaml`, có unit test cho từng rule.
- Một lượt LLM gán khái niệm cho từng điều khoản, kèm trích dẫn đã kiểm và giá trị đã chuẩn hóa.
- Kiểm lại khái niệm "im lặng" trước khi báo quyền ẩn hoặc thiếu nội dung.
- Kết quả ghi vào nhật ký thao tác và đồ thị hợp đồng (nút `ConceptInstance`, `Party`).
- Báo cáo JSON + Markdown, chạy được bằng một lệnh trên hợp đồng demo.

**Ngoài mục tiêu (bản này)**
- Hỏi người dùng dữ kiện (mang thai, nuôi con, vùng lương). Thiếu thì UNKNOWN.
- Xử phạt NĐ 283/2026, biện pháp khắc phục.
- Phụ lục sửa điều khoản (`AMEND_UNIT`). Khi cùng một khái niệm có hai giá trị khác nhau, báo "mâu thuẫn, cần xem".
- Quyền ngoài danh mục (tầng 2). Giao diện web. Chọn model cuối cùng.

**Điều phải tránh**
- Báo nhầm quyền ẩn khi hợp đồng có ghi. Đây là lỗi nặng nhất; có bước kiểm lại riêng (§6).
- Coi thiếu dữ kiện là vi phạm. Thiếu dữ kiện luôn ra UNKNOWN.
- LLM đưa ra kết luận pháp lý. LLM chỉ trả: khái niệm nào, ở đâu, nguyên văn, giá trị.
- Gửi dữ liệu cá nhân hoặc dữ kiện nhạy cảm cho LLM.

## 3. Cách tiếp cận đã chọn

| Cách | Mô tả | Đánh giá |
|---|---|---|
| **1. Theo đơn vị, một lượt (chọn)** | Mỗi lô điều khoản gửi kèm danh mục đóng; LLM trả khái niệm có mặt trong từng đơn vị | Số lần gọi bằng số lô (vài lần mỗi hợp đồng). Dùng lại `batches.py`. Rủi ro bỏ sót được bù bằng bước kiểm lại. |
| 2. Theo khái niệm | Mỗi khái niệm một lần gọi trên toàn hợp đồng | Chính xác hơn từng khái niệm nhưng 39+ lần gọi mỗi hợp đồng; tốn và chậm. Chỉ dùng cho bước kiểm lại. |
| 3. Trích tự do rồi ghép | LLM trích quyền / nghĩa vụ tự do, ghép vào danh mục bằng độ giống nghĩa | Ghép trượt sinh quyền ẩn giả; đã loại (xem thiết kế phía luật §2). |

Rule engine: viết bằng Python với tập toán tử cố định. Không dùng DSL riêng, Catala hay OPA: 39 khái niệm không cần,
và thêm phụ thuộc không đáng.

## 4. Luồng chạy

```
file HĐ → parse_contract (có sẵn) → che PII (có sẵn, đang sửa theo spec PII)
  → facts.py (có sẵn): bên ký, loại HĐ, ngày ký, lương, thử việc...        → dữ kiện cấp hợp đồng
  → tagger (mới): mỗi lô đơn vị × danh mục → {concept, uid, quote, slots}  → ASSERT trong oplog
  → normalize (mới): slot thô → số / bool / enum                          → dữ kiện cấp khái niệm
  → engine (mới): mỗi khái niệm × rule → PASS / FAIL / UNKNOWN / NOT_APPLICABLE
  → recheck (mới): khái niệm sắp báo thiếu / quyền ẩn → tìm lại → cập nhật
  → report (mới): kết quả + căn cứ luật (concept_basis) → JSON + Markdown
  → build_graph: thêm ConceptInstance, Party vào đồ thị hợp đồng
```

Mã mới nằm trong `src/rag/bridge/`: `catalog.py`, `engine.py`, `facts_map.py`, `tagger.py`, `recheck.py`,
`basis.py`, `check.py`. Lệnh chạy: `python -m rag.bridge check <file|contract_id>`.

## 5. Danh mục: những gì phải thêm vào `concepts.yaml`

Bản nháp hiện có đủ phần cho phía luật. Phía hợp đồng cần thêm hai trường cho mỗi khái niệm:

- **`slots`**: giá trị LLM phải trích khi gặp khái niệm, kèm kiểu.
  ```yaml
  slots:
    annual_leave_days: {kind: duration, unit: workday}
  ```
  Kiểu: `duration` (đơn vị `day` / `workday` / `month` / `hour`), `percent`, `money`, `bool`, `enum` (kèm `options`).
  Tên slot là tên dữ kiện mà `check` dùng. Khái niệm chỉ cần "có / không" thì không có slot.
- **`phrasing`**: 3–6 cụm từ hay gặp trong hợp đồng; dùng cho prompt và cho truy xuất ở bước kiểm lại.

Sửa thêm trong nháp:
- Giá trị luật có đơn vị: `law: {notice: {value: 3, unit: workday}}` thay cho các khóa khác tên (`notice_days`,
  `notice_workdays`). Engine chỉ so cùng đơn vị; khác đơn vị thì UNKNOWN kèm lý do `unit_mismatch`.
- `probation.duration`: ca "công việc khác" là 6 `workday`.
- `leave.personal_paid`: thêm slot `marriage_leave_days` và check ≥ 3.
- `wage.minimum_regional`: bảng lương vùng theo kỳ viết thẳng trong YAML (giá trị chép từ NĐ 38/2022, 74/2024,
  293/2025, có test đối chiếu lời văn khi kho được giải nén). Vùng là dữ kiện `wage_region`; bản đầu chưa tra vùng
  từ địa chỉ nên thường ra UNKNOWN.

`catalog.py` đọc và kiểm file khi nạp, lỗi thì dừng: id trùng; role không khai báo; toán tử lạ; `check.law` không
có trong `law` hay `cases`; `check.fact` không phải slot của khái niệm và không có trong bảng dữ kiện cấp hợp đồng
(§7); `mode` / `derogation` / `on_silence` ngoài tập cho phép.

## 6. Nhận diện khái niệm (tagger) và kiểm lại (recheck)

### 6.1 Tagger

- Lô: `make_batches` như `facts.py`. Payload qua `ask_json` (che PII bằng `MaskState`).
- Danh mục gửi kèm mỗi lô: với mỗi khái niệm chỉ `id`, `label`, `describe`, `phrasing`, `slots` (khoảng 4–6 nghìn
  ký tự cho 39 khái niệm). Không gửi rule, neo, ngưỡng: LLM không cần biết luật nói gì.
- LLM trả:
  ```json
  {"items": [{"concept": "leave.annual", "uid": "p1.d5.k2",
              "quote": "được nghỉ phép 08 ngày/năm",
              "slots": {"annual_leave_days": "08 ngày"}}]}
  ```
- Kiểm, theo thứ tự; trượt bước nào thì loại item và ghi lý do vào báo cáo:
  1. `concept` có trong danh mục, `uid` có trong lô.
  2. `quote_ok(unit_text, quote)` (đã có, hỗ trợ trích nhiều đoạn).
  3. Mỗi slot thô phải là chuỗi con của `quote` (trừ `bool`, `enum`).
  4. Chuẩn hóa slot được (`values.extract_values` cho tiền, %, thời hạn; `bool`/`enum` theo tập cho phép).
- Item qua kiểm thành một `ASSERT` (`machine_op`, `origin=llm`, `status=auto_accepted`), nội dung:
  `{"kind": "concept", "concept_id", "slots_raw", "slots", "catalog_version"}`, `source_uid`, `quote`, `model`,
  `prompt_version`. Item chỉ trượt bước 4 thành `pending` để người xem.
- Một khái niệm xuất hiện ở nhiều đơn vị là bình thường (nhiều `ASSERT`). Hai giá trị khác nhau cho cùng slot →
  engine báo `conflict` (§8).

### 6.2 Recheck

Chạy sau engine lần 1, chỉ cho khái niệm không có `ASSERT` nào mà kết quả là `missing_content` hoặc `hidden_right`.

- Truy xuất: chấm điểm mọi đơn vị theo từ khóa trong `label` + `phrasing` (BM25 đã có trong repo), lấy 5 đơn vị
  cao nhất.
- Một lần gọi LLM cho một khái niệm: "Các đoạn sau có đoạn nào nói về <describe> không? Trả uid + trích dẫn, hoặc
  rỗng." Kiểm như §6.1.
- Tìm thấy → thêm `ASSERT` (`content.found_by = "recheck"`), chạy lại engine cho khái niệm đó.
- Không thấy → ghi `ASSERT` `{"kind": "concept_absent", "concept_id", "searched_uids"}` để phân biệt "đã kiểm
  lại, không có" với "chưa kiểm".

## 7. Dữ kiện

Engine đọc một bảng phẳng `facts: dict[str, Fact]`, `Fact = {value, unit?, source, uid?, quote?}`, gộp từ:

1. **Cấp hợp đồng** (`facts.py`), qua `facts_map.py`:

   | Dữ kiện rule | Từ `fact_catalog` | Chuyển đổi |
   |---|---|---|
   | `contract_kind` | `labor_kind` | "Không xác định thời hạn" → `khong_xac_dinh_thoi_han`… |
   | `term_months` | `term` | duration → tháng |
   | `base_salary_vnd` | `salary` | money → số |
   | `has_probation` | `probation_period` | có giá trị → true |
   | `probation_days` | `probation_period` | duration → ngày (giữ đơn vị gốc) |
   | `probation_pay_pct` | `probation_salary` | percent → số |
   | `job_level` | `job_level` | 4 lựa chọn của `job_levels` → enum của rule |
   | `sign_date` | `sign_date` | ngày dùng để chọn giá trị luật |

2. **Cấp khái niệm**: slot đã chuẩn hóa của các `ASSERT` đang hiệu lực.
3. **Người dùng**: chưa có ở bản này (`work_condition`, `pregnant`, `wage_region`… luôn thiếu → UNKNOWN). Cấu trúc
   `source = "user"` để sẵn; dữ kiện nguồn này không bao giờ vào payload LLM.

Cùng một dữ kiện từ hai nguồn mà khác giá trị → không chọn, đánh dấu `conflict`.

## 8. Rule engine

Thuần Python, không I/O. Giá trị ba trị: `T`, `F`, `U`.

**Điều kiện** (`applicability`, `cases[].when`): lá `{fact, op, value}`; nút `all` / `any` / `not`. Dữ kiện thiếu
hoặc `conflict` → `U`. `all`: có `F` → `F`, có `U` → `U`, còn lại `T`. `any`: đối xứng. Toán tử: `eq lt lte gt gte
in present absent`; so số chỉ khi cùng đơn vị.

**Đánh giá một rule:**
1. `applicability`: `F` → `NOT_APPLICABLE`. `U` → ghi nhớ "phụ thuộc dữ kiện thiếu".
2. Chọn giá trị luật: `law` cố định, hoặc `case` đầu tiên có `when = T`. Có `case = U` trước khi gặp `T` → `U`.
   Không `case` nào khớp → `NOT_APPLICABLE`.
3. Khái niệm **có mặt** trong hợp đồng: không có `check` → `PASS`; có → so `check.fact` với giá trị luật; thiếu
   dữ kiện → `UNKNOWN`.
4. Khái niệm **im lặng** (không `ASSERT`, hoặc chỉ có `concept_absent`): theo `on_silence`:
   `missing_content` → `FAIL` (loại `missing_content`); `hidden_right` → `PASS` về pháp lý nhưng sinh phát hiện
   loại `hidden_right`; `none` → `PASS` (với điều cấm, không ghi là đúng).
5. Gộp với `applicability = U` ở bước 1: kết quả `FAIL` hoặc `hidden_right` hạ thành `UNKNOWN` loại
   `possible_right` / `needs_facts`.

`derogation`: `floor` nghĩa là `check` đã viết theo hướng có lợi cho NLĐ (ghi nhiều phép hơn vẫn `PASS`);
`mandatory` / `default` chỉ ảnh hưởng nhãn trong báo cáo ở bản này.

**Kết quả mỗi rule:**
```
{concept_id, rule_id, status: PASS|FAIL|UNKNOWN|NOT_APPLICABLE,
 finding: ok|violation|missing_content|hidden_right|possible_right|needs_facts|conflict,
 legality, employee_impact,           # lấy từ outcome khi FAIL / hidden_right; ngược lại để trống
 law_values, facts_used, missing_facts, evidence: [{uid, quote}]}
```

## 9. Căn cứ luật (`basis.py`)

Giao diện `LawBasis.concept_basis(concept_id, day) -> dict` đúng như thiết kế phía luật §6.
- `GraphLawBasis`: gọi hàm của LU khi đồ thị luật có lớp khái niệm.
- `AnchorLawBasis` (dùng ngay): lấy `anchors` từ YAML, gọi `LegalGraph.text_at(pid, day)` nếu đồ thị luật đã công
  bố; không có thì trả neo không kèm lời văn và ghi `basis_unavailable`.
Báo cáo không bao giờ dừng vì thiếu căn cứ luật; nó chỉ thiếu phần trích luật.

## 10. Đồ thị hợp đồng

Thêm vào `schema.json` (lên `version: "2"`):

| Nút / cạnh | Từ → Tới | Thuộc tính |
|---|---|---|
| `Party` | | `role` (`NLD` / `NSDLD`), `label` — không lưu tên người, công ty |
| `ConceptInstance` | | `concept_id`, `slots` (đã chuẩn hóa, phẳng), `quote` (đã che PII), `op_id`, `found_by` |
| `HAS_PARTY` | Contract → Party | |
| `ABOUT` | ConceptInstance → Unit | |
| `HOLDER` | ConceptInstance → Party | theo `holder` của khái niệm |

`build_graph` đọc các `ASSERT` đang hiệu lực có `kind = "concept"`. Mã nút `ConceptInstance` = `<cid>:ci:<op_id>`
nên dựng lại cho cùng kết quả. Kết quả engine **không** ghi vào đồ thị (nó phụ thuộc phiên bản danh mục và luật,
tính lại mỗi lần chạy).

## 11. Sửa lỗi phải làm trước

Từ lần chạy thật 14/11 (`notes/2026-11-14-contract-pipeline-real-run.md`):
1. Ranh giới phần: ngày ký của Phụ lục 2 bị gán vào Phụ lục 1.
2. Xref "Điều 2 HĐLĐ" từ phụ lục trỏ nhầm `p2.d2` thay vì điều 2 của hợp đồng chính.
3. `_in_store` ở `review.py:137` so chuỗi con, khớp nhầm.
4. PII: tên, ngày sinh, địa chỉ lọt vào 7/9 payload. Theo spec che PII; bản này thêm test: payload của tagger và
   recheck trên hợp đồng demo không chứa tên, ngày sinh, địa chỉ của các bên.

## 12. Kiểm thử và nghiệm thu

- `catalog`: file thật nạp không lỗi; mỗi loại lỗi ở §5 có một test file hỏng tương ứng.
- `engine`: bảng ca kiểm `tests/fixtures/bridge/engine_cases.yaml`, mỗi rule ít nhất 3 ca (đúng, sai, thiếu dữ
  kiện); ca P1 phải ra `possible_right` khi thiếu dữ kiện; ca `floor` ghi có lợi hơn ra `PASS`; ca khác đơn vị ra
  `UNKNOWN`.
- `tagger` / `recheck`: LLM giả trả JSON cố định; kiểm các bước loại item; `ASSERT` sinh ra tất định.
- `build_graph`: có `ConceptInstance`, `Party`, cạnh đúng lược đồ; không thuộc tính nào chứa PII.
- **Hợp đồng demo** (`hdld_tvpl_2025_filled`): gán nhãn tay các khái niệm có mặt (uid + giá trị). Chạy thật với
  model trong `.env`, ghi lại: precision / recall gán khái niệm, độ đúng giá trị, số quyền ẩn báo nhầm, số lần gọi,
  thời gian. Không đặt ngưỡng trước lần đo đầu.

## 13. Thứ tự làm

1. Sửa lỗi §11 (1–3); PII theo spec riêng.
2. `catalog.py` + bổ sung `concepts.yaml` (§5).
3. `engine.py` + bảng ca kiểm.
4. `facts_map.py`.
5. `tagger.py` + `ASSERT` + đồ thị (§10).
6. `recheck.py`.
7. `basis.py` (`AnchorLawBasis`), `check.py`, lệnh CLI, báo cáo.
8. Gán nhãn hợp đồng demo, chạy thật, ghi kết quả đo.

Bước 2–4 không cần LLM và không cần LU; xong là demo được bằng dữ kiện nhập tay.

## 14. Để sau

Hỏi người dùng dữ kiện và xử lý dữ liệu nhạy cảm; tra vùng lương từ địa chỉ; NĐ 283/2026 và khắc phục; `AMEND_UNIT`
cho phụ lục; tầng 2; mở rộng P2 / P3; bộ gold 5–10 hợp đồng; so sánh model; nối vào API / giao diện và thay
`review.py`; `traps`, ví dụ, mẫu giải thích trong danh mục.

## 15. Quyết định của người viết (người dựng có thể đổi)

- Tên module và lệnh CLI; vị trí bảng ca kiểm.
- Truy xuất ở recheck dùng BM25 sẵn có, k = 5.
- `slots` lưu phẳng làm thuộc tính của `ConceptInstance`, chưa thành nút `Value` riêng.
- Kết quả engine không lưu vào đồ thị.
- Bảng lương vùng viết thẳng trong YAML thay vì đọc `value_sources` từ đồ thị luật ở bản này.
