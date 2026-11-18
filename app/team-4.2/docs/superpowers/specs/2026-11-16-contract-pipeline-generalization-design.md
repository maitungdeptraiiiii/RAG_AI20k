# Cải tiến pipeline hợp đồng: thay regex và heuristic bằng cơ chế tổng quát

Ngày: 2026-11-16 · Trạng thái: **bản thiết kế chờ duyệt**, chưa có code.
Dựa trên: bản rà `notes/2026-11-15-contract-pipeline-generalization-audit.md` (64 mục, ID dạng 3.1 dưới đây là ID của
bản rà), danh sách lỗi còn lại và phép đo agent của phiên 16/11 (`notes/contract-agent-bench-2026-11-16/`).

## 1. Vấn đề

Pipeline hiện nhận diện bằng **mẫu chữ**: regex số liền đơn vị, tiêu đề "Điều N" có dấu câu, "PHỤ LỤC + số", năm
động từ sửa đổi, chuỗi con "công ty". Mỗi mẫu đúng với các hợp đồng đã gặp và sai **âm thầm** với cách viết khác:
dữ kiện biến mất, không có lỗi nào được báo. Thêm mẫu cho từng ca mới gặp không hội tụ.

## 2. Nguyên tắc thiết kế

Một cơ chế dùng chung cho mọi bước nhận diện, thay cho từng cụm mẫu riêng:

1. **Mô hình đề xuất, có cấu trúc.** LLM (hoặc mô hình NER với PII) trả đối tượng theo lược đồ có kiểu: giá trị đã
   chuẩn hóa, lựa chọn trong tập đóng (enum, danh sách mã đơn vị cho sẵn), kèm **câu trích nguyên văn**.
2. **Code kiểm chứng, không trích.** Code tất định chỉ trả lời câu hỏi hẹp "đề xuất này có khớp bằng chứng không":
   câu trích có trong đơn vị, mã đích có tồn tại, giá trị chuẩn hóa có đọc ra được từ câu trích, lược đồ đúng.
   Kiểm chứng một khẳng định cụ thể dễ tổng quát hơn nhiều so với tự tìm mọi cách viết.
3. **Không đạt kiểm chứng thì thành `pending`, không bị bỏ.** Mọi đề xuất vào oplog với trạng thái; cái không kiểm
   được hiện ra cho người duyệt và được đếm trong báo cáo. Hết kiểu "mất âm thầm".
4. **LLM chỉ chạy một lần; đồ thị vẫn tất định.** Kết quả ghi vào oplog (đã có `model`, `prompt_version`); `build_graph`
   không gọi LLM, cùng oplog cho cùng đồ thị như hiện nay.
5. **Bộ quy tắc cũ thành "ý kiến thứ hai".** Parser regex hiện có không bị xóa ngay: chạy song song, **bất đồng** với
   mô hình thì gắn cờ duyệt. Nó không còn là nguồn duy nhất, và không được thêm mẫu mới.
6. **Regex chỉ còn ở nơi đối tượng là một định dạng** (ngày ISO, email, số điện thoại, CCCD 12 số): ở đó regex là
   đúng công cụ.
7. **Đo trước, sửa sau.** Bộ đo tổng quát hóa (§4.1) làm trước mọi thay đổi; mỗi thay đổi phải thắng trên bộ đo.

## 3. Mục tiêu, ngoài mục tiêu, phản mục tiêu

Mục tiêu: xử lý các mục P0 của bản rà (3.1, 3.2, 2.1, 2.2, 7.1, 9.1), các cụm vá (4.1, 4.2, 4.3, 5.2, 5.3), các bộ
nhận diện chuỗi con (3.4–3.8, 5.6, 8.5), kiểm lại bằng BM25 (5.5), lỗi ngày ký, dẫn chiếu sai trong phụ lục, chi phí
soát lặp, bộ kiểm Cypher bằng regex.

Ngoài mục tiêu: nối API/giao diện và xuất Word/PDF (8.3, 8.4); OCR (1.1, 1.2); dữ liệu luật nhập tay và lớp
`Concept`/`ANCHORED_IN` (6.x, phần của Huy); mở rộng danh mục 39 khái niệm (5.8); câu hỏi trên nhiều hợp đồng.

Phản mục tiêu:
- LLM kết luận đúng/sai luật (vẫn là việc của rule engine).
- Giá trị hay quan hệ vào đồ thị mà không có câu trích kiểm được.
- Văn bản chưa che PII đi tới LLM bên ngoài (các bước mới làm tăng lượng văn bản gửi đi: §4.2 là điều kiện tiên quyết).
- Thay regex bằng một danh sách từ khóa khác nằm trong prompt.
- `build_graph` gọi LLM, hoặc cùng đầu vào cho đồ thị khác nhau.

## 4. Thiết kế từng phần

### 4.1 Bộ đo tổng quát hóa (làm đầu tiên) — 9.1, 9.2, 9.3, 9.4

Hiện chỉ có một HĐLĐ gần như hợp lệ và nhãn ở mức khái niệm. Ba thành phần:

- **Kiểm thử biến hình (metamorphic).** Từ một hợp đồng gốc, sinh các bản **cùng nghĩa, khác cách viết** bằng phép
  biến đổi có kiểm soát: `15.000.000 đồng` ↔ `15.000.000đ` ↔ `15,000,000 VND` ↔ `15 triệu đồng` ↔ viết bằng chữ;
  `Điều 1.` ↔ `Điều 1` ↔ `Điều thứ nhất`; `PHỤ LỤC 2` ↔ `BIÊN BẢN THỎA THUẬN SỬA ĐỔI`; `12 tháng` ↔ `1 năm` ↔
  `12 (mười hai) tháng`. Tiêu chí: **bảng dữ kiện và kết quả rule phải giống hệt bản gốc**. Đây là phép đo trực tiếp
  của "tổng quát": không cần gán nhãn thêm, mỗi phép biến đổi mới là một ca kiểm mới cho mọi hợp đồng gốc.
- **Hợp đồng cài lỗi.** Phép biến đổi **đổi nghĩa** có đáp án biết trước: 85% → 70% (vi phạm lương thử việc), thử
  việc 2 → 4 tháng, xóa điều khoản nâng lương (thiếu nội dung). Tiêu chí: kết luận đổi đúng như dự kiến, các kết luận
  khác giữ nguyên. Cho nhãn **mức kết luận** mà không phải gán tay từng hợp đồng.
- **Bộ câu hỏi agent.** Mở rộng `scripts/bench_contract_agent.py`: ≥ 20 câu, đáp án có kiểu (số, uid, ngày) thay cho
  regex trên câu trả lời, N lần mỗi câu, báo tỉ lệ kèm khoảng tin cậy; sửa tiêu chí Q4.

Cần thêm 3–5 HĐLĐ thật hoặc mẫu công khai khác nguồn làm hợp đồng gốc (bản rà 9.2). Lần chạy đo dùng LLM không cache.

### 4.2 Che PII bằng mô hình — 7.1

Đã có spec riêng: `specs/2026-11-14-pii-model-masking-design.md` (mô hình NER OpenMed BigMed-278M + quy tắc ngữ cảnh,
regex cũ làm dự phòng), đang chờ duyệt. Bản này **không thiết kế lại**, chỉ đặt thứ tự: phải xong trước §4.4–4.6 vì
các bước đó gửi thêm văn bản tới LLM. Bổ sung một yêu cầu: câu hỏi và kết quả công cụ của agent đi qua cùng lớp che.

### 4.3 Giá trị có kiểu, do mô hình chuẩn hóa — 3.1, 3.2, 3.3, 3.10, 5.1

Hiện: `values.extract_values` (regex) tìm số; `facts_map._duration` lấy **giá trị đầu tiên**.

Mới: bước trích dữ kiện và gán khái niệm trả giá trị **đã chuẩn hóa** theo lược đồ:

```
Money    {amount: int, currency: "VND"|"USD"|…, per: "month"|"day"|"hour"|"once"|null}
Duration {parts: [{n: number, unit: "year"|"month"|"week"|"day"|"workday"|"hour"|"minute"}]}   # "1 năm 6 tháng" = 2 phần
Percent  {value: number, of: <tên dữ kiện> | null}
Date     {iso: "YYYY-MM-DD"}
```

kèm `quote`. `Duration` nhiều phần sửa 3.2 ở tầng mô hình dữ liệu, không ở tầng mẫu chữ; quy đổi sang đơn vị chuẩn
do engine làm (một bảng quy đổi, `workday` giữ là đơn vị riêng, so được với ngưỡng cùng đơn vị — sửa 5.1).

Kiểm chứng (thay vai trò trích): một **bộ đọc số** nhỏ dựa trên văn phạm (chữ số với dấu nghìn/thập phân kiểu Việt và
kiểu Anh, số viết bằng chữ, hậu tố nhân `nghìn/triệu/tỷ/tr/k`) liệt kê mọi con số đọc được trong `quote`; đề xuất đạt
khi mọi `amount`/`n`/`value` nằm trong tập đó. Bộ đọc số chỉ **kiểm**, không quyết định đâu là lương, đâu là thời hạn,
nên không cần biết đơn vị hay ngữ cảnh. Không khớp → `pending` kèm lý do, **không bỏ**.

Kiểm thử thuộc tính: sinh số ngẫu nhiên → kết xuất theo mọi cách viết của §4.1 → bộ đọc số phải đọc lại đúng.

Nút `Value` trên đồ thị dựng từ các giá trị đã kiểm của mô hình; `extract_values` cũ chạy làm ý kiến thứ hai (số nó
thấy mà mô hình không báo → ghi `notes` của bản dựng).

### 4.4 Cấu trúc hợp đồng do mô hình phác, code kiểm phủ — 2.1, 2.2, 2.3, 2.4

Hiện: `tree.py`/`parts.py` nhận tiêu đề bằng regex; trượt là vỡ cả hợp đồng.

Mới: bước **phác bố cục**. Văn bản (đã che) được đánh số dòng; mô hình trả:

```
parts:    [{start_line, kind: "main"|"appendix"|"amendment"|"attachment", title, number|null}]
headings: [{line, level: "article"|"clause"|"point", number: str, label: str}]
```

Mô hình chỉ **chỉ vào số dòng**, không chép lại nội dung; đơn vị vẫn là khoảng ký tự trên văn bản gốc, nên văn bản
không thể bị sửa hay bịa. Kiểm chứng tất định: số dòng tồn tại và tăng dần; mỗi tiêu đề nằm trong một phần; cấp lồng
hợp lệ (point trong clause trong article); mọi ký tự thuộc đúng một đơn vị (kiểm phủ). Đánh số lệch hay lặp chỉ thành
cảnh báo, không còn là lý do nuốt tiêu đề (2.4).

Kết quả ghi vào thao tác `SET_LAYOUT` (đã có trong oplog, hiện chỉ mang `parts`; mở rộng thêm `headings`).
`parse_contract` dựng cây từ layout khi có. Parser regex chạy song song: hai bên cho cùng danh sách đơn vị →
`auto_accepted`; khác nhau → dùng bản của mô hình, trạng thái `pending`, báo chỗ khác cho người duyệt. Hợp đồng dài
chia cửa sổ có chồng lấn; một lời gọi cho hợp đồng cỡ demo.

`kind: "amendment"` giải quyết 2.2 mà không cần danh sách tên văn bản: mô hình phân loại theo nội dung.

### 4.5 Siêu dữ liệu theo phần — lỗi ngày ký, 4.6, 3.4, 3.5, 3.6, 3.7, 3.8, 5.6, 8.5

Lỗi ngày ký hiện nay là lỗi mô hình dữ liệu: ngày ký là thuộc tính của **một văn bản**, nhưng đang được trích như
một dữ kiện toàn hợp đồng rồi bỏ khi có hơn một ứng viên. Mới: mỗi `Part` mang `signed_on`, `effective_from`,
`effective_to` (kèm câu trích); ngày ký hợp đồng = `signed_on` của phần `main`. Không còn quy tắc "đúng một ứng viên".
`effective_from` của phần sửa đổi cũng là nguồn ngày hiệu lực cho §4.6.

Các bộ nhận diện chuỗi con thành **lựa chọn trong tập đóng** của lược đồ trích, code chỉ kiểm thuộc tập:
`party.role ∈ {NLD, NSDLD, other}`, `contract_type ∈ {labor, lease, service, other}`, `labor_kind`, `job_level`
(trả thẳng mã, bỏ việc ghép theo thứ tự danh sách — 3.6), `has_probation ∈ {true, false, unstated}` (sửa 3.7), slot
bool nhận boolean thật (3.8). `check_contract` dừng với thông báo rõ khi `contract_type ≠ labor` (5.6).

### 4.6 Quan hệ có kiểu do mô hình trích — 4.1, 4.2, dẫn chiếu sai, giới hạn của `AMENDS`

Hiện: `xrefs.py` phân giải dẫn chiếu bằng regex; `amendments.py` (phiên 16/11) dựng `AMENDS` từ danh sách động từ
trên cùng dòng với dẫn chiếu; "Điều 2" trong câu "Các nội dung khác của Điều 2 giữ nguyên" bị nối nhầm vào phụ lục.

Mới: với mỗi đơn vị, mô hình trả các quan hệ:

```
{type: "refers_to"|"amends"|"supplements"|"replaces"|"repeals",
 target: <uid chọn trong danh sách đơn vị được cấp> | {external_law: str},
 effective_from: Date|null, quote, effective_quote|null}
```

Điểm mấu chốt: **đích là lựa chọn trong tập đóng**. Mô hình nhận danh sách `(uid, phần, nhãn, tiêu đề)` của mọi đơn
vị và chọn; nó thấy ngữ cảnh "Điều 2 Hợp đồng lao động" nên chọn `p0.d2`, điều regex không làm được. Kiểm chứng: uid
tồn tại; `quote` nguyên văn trong đơn vị nguồn; `effective_quote` nguyên văn trong cùng phần và ngày đọc ra được từ
nó; `amends/supplements/replaces/repeals` chỉ hợp lệ khi nguồn thuộc phần không phải `main` hoặc có ngày ký muộn hơn.
Ghi `ASSERT kind=relation`; `build_graph` dựng `REFERS_TO`/`AMENDS` từ đó. `xrefs.py` và `amendments.py` thành ý kiến
thứ hai (bất đồng → cờ duyệt), không thêm từ khóa.

**Một cách phân xử cho mọi giá trị (4.2).** Hiện chỉ `ContractFact` được phân xử theo `AMENDS`; slot của khái niệm
luôn thành `CONFLICT`. Mới: mọi khẳng định có giá trị (dữ kiện hợp đồng và slot khái niệm) là một `Assertion` gắn
đơn vị chứng cứ; `factset_from_graph` phân xử **cùng một hàm** `value_at(name, day)` trên cạnh `AMENDS`. Bỏ `_merge`
riêng cho slot.

### 4.7 Soát theo dòng thời gian — 4.3, 5.7

Hiện: một ngày soát (ngày ký). Mới: tập mốc = ngày ký ∪ mọi `AMENDS.valid_from` ∪ các mốc đổi giá trị luật theo kỳ
nằm trong thời hạn hợp đồng. Engine chạy tại từng mốc trên `value_at(·, mốc)`; báo cáo gộp các khoảng có cùng kết quả
("02/01/2025–30/06/2025: đạt; từ 01/07/2025: …"). Thuần tất định, không thêm lời gọi LLM. Không có ngày ký → **dừng
và hỏi người dùng** thay cho mốc mặc định 01/01/2021 (5.7).

### 4.8 "Theo luật định" là một trạng thái của slot — 5.2, 5.3

Hiện: `_unstated_restriction` vá cho một mẫu diễn đạt. Mới: mỗi slot có `state ∈ {value, defers_to_law, unstated}`
do mô hình chọn (tập đóng, kèm câu trích). Engine: `defers_to_law` → đạt theo tham chiếu, báo cáo ghi "hợp đồng dẫn
về luật"; `unstated` → xử lý `on_silence` như hiện nay. Một cơ chế cho mọi rule ngưỡng, bỏ hàm vá.

### 4.9 Kiểm lại khái niệm im lặng bằng đọc phủ — 5.5

Hiện: BM25 top-5 theo `phrasing`; điều khoản dùng từ khác bị coi là vắng mặt → báo "thiếu nội dung" sai. Mới: với các
khái niệm im lặng, hỏi mô hình trên **mọi lô** của hợp đồng (hợp đồng ≤ 150 trang, số lô nhỏ): "có đơn vị nào nói về
các khái niệm sau không, trích nguyên văn". Chi phí = số lô lời gọi, không phụ thuộc số khái niệm. Kết luận "vắng mặt"
chỉ ghi khi mọi lô đã được đọc (đã có `coverage`). `phrasing` chỉ còn là mô tả trong prompt.

### 4.10 Bộ kiểm Cypher dựa trên chính Neo4j — rào chắn Text2Cypher

Hiện: `cypher.check_cypher` là regex trên chuỗi truy vấn. Mới, hai lớp do cơ sở dữ liệu trả lời:
- **Chỉ đọc:** chạy `EXPLAIN <query>` trước; chỉ chấp nhận khi loại truy vấn Neo4j báo là đọc (`query_type == "r"`)
  và kế hoạch không có toán tử gọi thủ tục. Kết luận do bộ phân tích của Neo4j đưa ra, không do mẫu chữ.
- **Phạm vi:** duyệt cây kế hoạch của `EXPLAIN`: mọi toán tử lá (quét/tìm nút) phải có vị từ `contract_id = $cid`
  hoặc là mở rộng từ một biến đã neo; nhãn và loại cạnh trong kế hoạch thuộc `schema.json`.

**Cần chạy thử trước** (spike nửa ngày): planner có thể chọn quét theo nhãn rồi lọc, làm hình dạng kế hoạch khó kiểm.
Nếu spike không đạt: dùng bộ phân tích cú pháp openCypher (văn phạm ANTLR) duyệt AST. Bộ kiểm regex hiện tại giữ làm
lớp thứ hai cho tới khi lớp mới qua bộ ca tấn công (thêm vào `tests/test_contract_cypher.py`).

### 4.11 Không soát lại, không công bố lại khi không đổi

- Kết quả các bước mô hình đã nằm trong oplog. `check_contract` bỏ qua bước nào mà oplog đã có thao tác cùng
  `(prompt_version, model, file_checksum)`; hỏi câu thứ hai trên cùng hợp đồng không gọi lại bước soát.
- `ContractGraphService.build_and_publish` bỏ công bố khi `store.current_build_id(cid) == build.build_id` (hàm đã có).
- `op_id` của thao tác máy thêm `prompt_version` và `model` vào băm (8.9), để đổi model tạo thao tác mới.

## 5. Luồng sau cải tiến

```
file → văn bản theo trang → che PII (mô hình, §4.2)
     → phác bố cục (§4.4) → SET_LAYOUT
     → trích theo lô: siêu dữ liệu phần, dữ kiện, khái niệm + slot có kiểu và trạng thái (§4.3, 4.5, 4.8)
     → trích quan hệ (§4.6)                              } mọi đề xuất: kiểm chứng → oplog
     → đọc phủ cho khái niệm im lặng (§4.9)               } (auto_accepted | pending)
     → build_graph (tất định, không LLM)
     → value_at(day) → engine tại từng mốc (§4.7) → báo cáo
     → agent: công cụ có kiểu + Text2Cypher có rào (§4.10)
```

## 6. Cái giá và rủi ro

| Rủi ro | Xử lý |
|---|---|
| Thêm lời gọi LLM (bố cục, quan hệ, đọc phủ): ước 3–6 lời gọi mỗi hợp đồng cỡ demo | Chạy một lần, ghi oplog (§4.11); model nhỏ cho bước tập đóng (cấu hình như `CONCEPT_TAG_MODEL`) |
| Mô hình không tất định giữa các lần chạy | Đồ thị chỉ phụ thuộc oplog; đo độ dao động bằng chạy lạnh lặp lại (§4.1) |
| Mô hình sai mà kiểm chứng không bắt được (chọn sai đích hợp lệ, phân loại sai `kind`) | Ý kiến thứ hai của parser cũ gắn cờ; bộ biến hình và cài lỗi đo tỉ lệ; `pending` cho người duyệt |
| Bộ đọc số vẫn là code viết tay | Phạm vi hẹp (chỉ đọc số, không ngữ cảnh), có kiểm thử thuộc tính; trượt thì `pending`, không mất |
| Nhiều `pending` làm người duyệt quá tải | Đo tỉ lệ `pending` trên bộ đo; đặt ngưỡng chấp nhận trước khi bật mặc định |
| Thay nhiều thứ cùng lúc, khó biết cái nào gây hồi quy | Mỗi phần bật bằng cờ riêng, so trước/sau trên bộ đo, giữ đường cũ tới khi thắng |

## 7. Thứ tự làm

Mỗi bước là một kế hoạch riêng, có số đo trước/sau trên bộ đo §4.1:

1. **Bộ đo** (§4.1): biến hình, cài lỗi, câu hỏi agent. Đo đường hiện tại làm mốc.
2. **Sửa nhanh, không cần mô hình:** không công bố lại (§4.11), dừng khi thiếu ngày ký (§4.7 phần cuối).
3. **Che PII bằng mô hình** (§4.2, theo spec 14/11).
4. **Giá trị có kiểu + siêu dữ liệu phần + tập đóng** (§4.3, 4.5): cùng sửa lược đồ của bước trích, làm một lần.
5. **Phác bố cục** (§4.4).
6. **Quan hệ có kiểu + phân xử chung + dòng thời gian** (§4.6, 4.7).
7. **Trạng thái slot, đọc phủ** (§4.8, 4.9).
8. **Bộ kiểm Cypher** (§4.10), sau spike.

## 8. Câu hỏi cần người dùng quyết

- **Q1. Model cho các bước mới.** Dùng một model nhỏ qua OpenRouter như bước gán khái niệm (Haiku 5.5 đã thắng phép so
  14/11), hay model chạy tại chỗ (ghi nhớ dự án từng định dùng Qwen cho trích điều khoản)? Ảnh hưởng: chi phí, và
  văn bản có rời máy hay không.
- **Q2. Nguồn hợp đồng gốc cho bộ đo.** Cần 3–5 HĐLĐ khác nguồn. Bạn có hợp đồng thật (đã ẩn danh) hay dùng mẫu công khai?
- **Q3. Ai duyệt `pending`.** Chưa có giao diện duyệt cho các loại thao tác mới; đợt này chỉ đếm và in trong báo cáo,
  hay cần màn hình duyệt?
- **Q4. Phạm vi đợt đầu.** Làm đủ 8 bước, hay dừng sau bước 4 (đã hết 4/6 mục P0) rồi đánh giá lại?

## 9. Lựa chọn của người viết (chưa được xác nhận)

- Giữ parser regex làm ý kiến thứ hai thay vì xóa: rẻ, và bất đồng là tín hiệu duyệt tốt.
- Bộ đọc số viết tay theo văn phạm thay cho gọi LLM lần hai để kiểm: tất định, kiểm thử thuộc tính được.
- Bố cục bằng số dòng thay cho mô hình chép lại văn bản: loại hẳn khả năng bịa nội dung.
- Không thiết kế lại phần PII; dùng spec 14/11.
- Bộ kiểm Cypher: ưu tiên `EXPLAIN` của Neo4j, parser ANTLR là phương án dự phòng.
