# Agent trên đồ thị, bản 2: bộ công cụ theo ý định và duyệt đồ thị luật

Ngày: 2026-11-16 · Trạng thái: **bản thiết kế chờ duyệt**, chưa có code.
Thay thế §5.6–5.7 của `2026-11-16-contract-graph-agent-design.md` (bộ công cụ và agent bản 1). Lớp đọc
`ContractGraphView`, `factset_from_graph`, bộ kiểm luật giữ nguyên.
Liên quan: `2026-11-16-contract-pipeline-generalization-design.md` (viết tắt: spec TQH).

## 1. Đánh giá bản 1

### 1.1 Bằng chứng

Phép đo 16/11 (`notes/contract-agent-bench-2026-11-16/`, 4 câu × 5 lần × 2 cấu hình = 40 lần chạy, Neo4j, `gpt-6-luna`):

| Công cụ | Số lần gọi (40 lần chạy) |
|---|---|
| `expand` | 42 |
| `find_concept` | 31 |
| `check_concept` | 10 |
| `find_units` | 4 |
| `concept_basis` | 4 |
| `find_path`, `subgraph`, `contract_facts`, `law_text_at`, `law_changes`, `law_guidance`, `law_references`, `cypher_query` | **0** |

Độ đúng 17–18/20; một lần sai thật là do agent `expand` lần lượt sai phần. Bộ câu hỏi không có câu nào cần đi trong
luật, nên các công cụ luật chưa từng được thử; đó là lỗ của phép đo, và cũng cho thấy agent không tự tìm tới luật.

### 1.2 Vấn đề thiết kế

| # | Vấn đề | Hậu quả đã thấy hoặc suy ra |
|---|---|---|
| V1 | **Công cụ ở mức thao tác đồ thị** (`expand`, `find_path`, `subgraph`), không ở mức câu hỏi nghiệp vụ. Agent phải tự lập trình phép duyệt bằng nhiều lần `expand`. | `expand` chiếm gần nửa số lời gọi; ca sai Q3 là đi lạc khi `expand`. Ba công cụ không bao giờ được gọi. |
| V2 | **Ba đường tới cùng một giá trị** (`contract_facts`, slot trong `find_concept`, `cypher_query` trên `ContractFact`), chỉ một đường tính theo ngày. | Agent chưa bao giờ gọi `contract_facts`; Q4 trả 17 triệu mà không nêu 15 triệu. |
| V3 | **Phía luật chỉ có 4 hàm tra theo `pid`**, agent không có cách nào tìm ra `pid` ngoài `concept_basis`, không đi được cha/con, dẫn chiếu, văn bản hướng dẫn như một phép duyệt. | Không câu trả lời nào trong phép đo có lời văn luật, trừ khi câu hỏi ép. |
| V4 | **Đường đi dừng ở biên hợp đồng.** Hậu kiểm chỉ biết nút của đồ thị hợp đồng; điều luật chỉ nằm trong trường `law` không kiểm. | Kịch bản slide "Điều 6 → Điều 2 → Điều 26" không kiểm chứng được nửa sau. |
| V5 | **Mã nút dài và lộ cấu trúc** (`3jH6r3bB3Szi2XBhy9OmkSi3:p0.d6@1`), agent phải chép lại. | Tốn token, dễ chép sai; một lần agent ghi cứng `contract_id` vào Cypher. |
| V6 | **Rào chắn pháp lý bằng từ khóa** ("đúng luật", "vi phạm"…) và **không kiểm con số** trong câu trả lời. | "Đạt ngưỡng tối thiểu" lọt; phép nhân 85% × 15 triệu do LLM tự tính, không ai kiểm. |
| V7 | **Mỗi bước gửi lại toàn bộ** ngữ cảnh, mô tả 13 công cụ, danh mục 39 khái niệm và mọi bước trước; một công cụ mỗi bước. | Payload tăng theo bình phương số bước; nhiều vòng gọi không cần thiết. |
| V8 | **Không có cầu trực tiếp từ câu chữ hợp đồng sang điều luật.** Hợp đồng viết "theo Điều 35 Bộ luật Lao động" chỉ thành `unresolved_refs`. | Cầu duy nhất là mã khái niệm (39 khái niệm); dẫn chiếu luật ngoài danh mục là ngõ cụt. |

Phần đáng giữ: lớp công cụ có kiểu trên Cypher tham số (semantic layer), kết luận pháp lý qua engine, trả lời kèm
đường đi, chặn kết luận khi còn dẫn chiếu chưa đọc, ngữ cảnh kèm theo (`unit_context`) — phép đo cho thấy nó giảm số
bước và tăng tỉ lệ qua hậu kiểm từ 10/20 lên 18/20.

## 2. Hướng thiết kế lại

1. **Công cụ theo ý định.** Mỗi công cụ trả lời một loại câu hỏi và trả một **thẻ** (card) đã gói sẵn bằng chứng và
   các bước đi tiếp, thay cho hình dạng thô của đồ thị. Phép duyệt nhiều bước cố định (điều khoản → dẫn chiếu → sửa
   đổi) nằm trong code, tất định.
2. **Một không gian tham chiếu cho cả hai đồ thị.** Agent chỉ thấy tham chiếu ngắn có kiểu; mã nút thật do ứng dụng giữ.
3. **Đồ thị luật là công dân hạng nhất:** có công cụ đọc và công cụ duyệt riêng, có giới hạn; điều luật nằm trong
   đường đi và được kiểm như nút hợp đồng.
4. **Hai cây cầu giữa hai đồ thị:** mã khái niệm (đã có) và **dẫn chiếu luật trực tiếp** trong câu chữ hợp đồng (mới).
5. **Rào chắn có cấu trúc thay cho từ khóa:** kết luận pháp lý là một trường có kiểu đối chiếu với engine; con số
   trong câu trả lời phải truy được về thẻ đã đọc hoặc về công cụ tính.

## 3. Mô hình dùng chung

### 3.1 Tham chiếu (`ref`)

| Tiền tố | Trỏ tới | Ví dụ | Phân giải |
|---|---|---|---|
| `c:` | điều khoản hợp đồng (Unit) | `c:p0.d6` | `<contract_id>:<uid>@<phiên bản hiện hành>` |
| `p:` | phần của hợp đồng (Part) | `p:p2` | `<contract_id>:p2` |
| `f:` | dữ kiện hợp đồng | `f:base_salary_vnd` | tên dữ kiện |
| `k:` | khái niệm của danh mục | `k:probation.pay` | `concept_id` |
| `l:` | điều/khoản/điểm luật (Provision) | `l:bo-luat:45/2019/QH14#d26` | `pid` |
| `d:` | văn bản luật (LawDoc) | `d:bo-luat:45/2019/QH14` | `document_key` |

Agent không bao giờ thấy hay viết `contract_id`. Tham chiếu sai dạng hoặc không tồn tại → `{"error"}` kèm gợi ý
(`locate`). Mọi thẻ đều mang `ref` của chính nó và `ref` của các bước đi tiếp, nên agent chỉ chép lại thứ đã thấy.

### 3.2 `GraphNavigator` (module mới `rag/contracts/graph/navigator.py`)

Một lớp đọc thống nhất mà công cụ gọi; không công cụ nào chạm thẳng vào view hay `LegalGraph`:

```python
class GraphNavigator:
    def __init__(self, view: ContractGraphView, legal: LegalGraph | None, anchors: ConceptAnchors,
                 catalog: Catalog, *, day: date, sign_date: date | None): ...
    def resolve(self, ref: str) -> Resolved | None            # kiểm dạng + tồn tại
    def clause_card(self, ref: str, day: date) -> dict
    def law_card(self, ref: str, day: date) -> dict
    def law_neighbors(self, ref: str, relation: str, day: date, limit: int) -> list[dict]
    def edge(self, a: str, b: str, day: date) -> dict | None  # cạnh (thật hoặc cầu) giữa hai ref; dùng cho hậu kiểm
```

`ConceptAnchors` là giao diện của cầu khái niệm, hai bản: `CatalogAnchors` (đọc neo từ `concepts.yaml`, dùng ngay)
và `GraphAnchors` (đọc `Concept`/`ANCHORED_IN` khi lớp của Huy xong). Đổi bản không đổi công cụ.

### 3.3 Hai cây cầu

- **Cầu khái niệm (đã có):** `c:` ←ABOUT← ConceptInstance —`concept_id`→ `k:` —neo (basis / exception)→ `l:`.
- **Cầu dẫn chiếu trực tiếp (mới), cạnh `CITES_LAW`:** điều khoản viết "Điều 35 Bộ luật Lao động" nối thẳng tới
  `l:…#d35`. Dựng ở bước trích quan hệ của spec TQH §4.6 (`target: {external_law}`): mô hình chọn văn bản trong danh
  sách ứng viên do `LegalGraph` trả (tìm theo loại + số hiệu/tên), code kiểm `pid` tồn tại và hiệu lực tại ngày ký;
  ghi `ASSERT kind=relation`. Đồ thị hợp đồng lưu `law_pid` trên một nút `LawCitation` (thuộc hợp đồng, không tạo cạnh
  vật lý xuyên hai đồ thị, để công bố/xóa theo hợp đồng vẫn nguyên khối). Trước khi TQH §4.6 có, cầu này trống và
  công cụ vẫn chạy với cầu khái niệm.

### 3.4 Ngày

Mọi công cụ nhận `day` tùy chọn, mặc định là ngày soát. Phía hợp đồng: giá trị và lời văn hiệu lực tại `day`
(`AMENDS.valid_from`). Phía luật: phiên bản hiệu lực tại `day` (đã là ngữ nghĩa của `LegalGraph`). Mọi thẻ ghi `day`
đã dùng. Thiếu ngày ký: công cụ trả lỗi rõ thay cho mốc 2021 (spec TQH §4.7).

## 4. Bộ công cụ mới

Tám công cụ (bản 1: 13). Bảng ánh xạ ở §4.10.

### 4.1 `locate` — tìm chỗ bắt đầu trong hợp đồng

Tham số: đúng một trong `concept` (`k:`), `label` ("Điều 6", "Phụ lục 2"), `text` (chuỗi cần chứa).
Trả: tối đa 5 mục `{ref, label, part, why: "concept"|"label"|"text", snippet (160 ký tự)}`; với `concept` kèm nhãn
khái niệm và câu trích đã gán. Không trả thẻ đầy đủ: bước sau dùng `read_clause`.
Gộp `find_units` + `find_concept`.

### 4.2 `read_clause` — đọc điều khoản cùng mọi thứ dính vào nó

Tham số: `refs` (1–3 `c:`), `day?`. Trả mỗi điều khoản một thẻ:

```json
{"ref": "c:p0.d6", "label": "Điều 6", "part": "Hợp đồng chính", "day": "2025-01-02",
 "text": "… hưởng 85% mức lương căn bản quy định tại Điều 2 …",
 "refers_to":  [{"ref": "c:p0.d2", "label": "Điều 2", "raw": "Điều 2", "text": "… 15.000.000 đồng/tháng …"}],
 "amended_by": [{"ref": "c:p2.d1", "label": "Phụ lục 2 — Mục 1", "kind": "modify", "valid_from": "2025-07-01",
                 "in_force_at_day": false, "raw": "Sửa đổi Điều 2 …"}],
 "amends":     [],
 "cites_law":  [{"ref": "l:…#d26", "raw": "Điều 26 Bộ luật Lao động"}],
 "concepts":   [{"ref": "k:probation.pay", "label": "Tiền lương thử việc tối thiểu"}],
 "facts":      [{"ref": "f:probation_pay_pct", "value": 85, "unit": "percent"}],
 "children":   []}
```

Là `unit_context` của bản 1 nâng thành công cụ chính. Điều khoản được dẫn chiếu trả kèm lời văn (300 ký tự), nên
"đi theo dẫn chiếu" không còn là một quyết định của mô hình. `in_force_at_day` tính sẵn để mô hình không phải so ngày.
Thay `expand`, `subgraph`, phần ngữ cảnh của `find_units`.

### 4.3 `fact` — giá trị một dữ kiện theo thời gian

Tham số: `name?` (bỏ trống: liệt kê tên dữ kiện có trong hợp đồng), `day?`. Trả:

```json
{"ref": "f:base_salary_vnd", "day": "2025-01-02", "value": 15000000, "unit": "vnd", "source": "c:p0.d2",
 "timeline": [{"from": "2025-01-02", "value": 15000000, "source": "c:p0.d2"},
              {"from": "2025-07-01", "value": 17000000, "source": "c:p2.d1", "via": "amends"}],
 "conflict": false, "warnings": []}
```

`timeline` luôn có mặt: câu hỏi mơ hồ về thời điểm ("lương căn bản là bao nhiêu?") có đủ cả hai mức ngay trong một
thẻ (ca Q4). Đây là **đường duy nhất** tới giá trị theo ngày; `read_clause.facts` chỉ là con trỏ sang đây.

### 4.4 `check` — kết luận pháp lý cho một khái niệm

Tham số: `concept` (`k:`), `day?`. Trả kết quả engine từng rule (`finding`, `status`, giá trị luật, dữ kiện đã dùng
kèm `ref`, dữ kiện còn thiếu), **kèm neo luật** `[{ref: "l:…", role: "basis"|"exception", label, in_force}]` và, khi
đã có soát theo dòng thời gian (TQH §4.7), kết quả theo từng khoảng. Gộp `check_concept` + `concept_basis`: kết luận
và đường sang luật đến trong một lời gọi; `l:` trả về là điểm vào đồ thị luật.

### 4.5 `read_law` — đọc một điều luật tại một ngày

Tham số: `refs` (1–3 `l:`), `day?`. Trả thẻ:

```json
{"ref": "l:bo-luat:45/2019/QH14#d26", "label": "Điều 26", "title": "Tiền lương thử việc",
 "document": {"ref": "d:bo-luat:45/2019/QH14", "type": "Bộ luật", "number": "45/2019/QH14", "title": "Bộ luật Lao động"},
 "day": "2025-01-02", "in_force": true, "valid_from": "2021-01-01", "valid_to": null, "verification": "verified",
 "text": "Tiền lương của người lao động trong thời gian thử việc … ít nhất phải bằng 85% …",
 "parent": null, "children": [],
 "counts": {"refers_to": 0, "referred_by": 3, "guidance": 1, "versions": 1},
 "changed_after_day": false}
```

Không hiệu lực: `in_force: false` kèm `reason` và mốc ngày (đúng như `LegalGraph.text_at` hiện trả). `counts` cho
agent biết đi tiếp có gì mà chưa phải tải; `changed_after_day` trả lời nhanh "luật đã đổi từ ngày ký chưa".
Thay `law_text_at`.

### 4.6 `law_neighbors` — duyệt đồ thị luật, một bước, có kiểu

Tham số: `ref` (`l:` hoặc `d:`), `relation`, `day?`, `to?` (chỉ cho `history`).

| `relation` | Nghĩa | Cạnh trong đồ thị luật | Trả |
|---|---|---|---|
| `children` | khoản/điểm của điều | `CHILD_OF` (ngược) | danh sách `l:` kèm 200 ký tự lời văn tại `day` |
| `parent` | điều chứa khoản này | `CHILD_OF` | một `l:` |
| `refers_to` | điều này dẫn chiếu tới đâu | `REFERS_TO` từ phiên bản hiệu lực | `l:`/`d:` kèm `raw`, `kind` |
| `referred_by` | điều nào dẫn chiếu tới đây | `REFERS_TO` (ngược) | `l:` kèm trích dẫn |
| `guidance` | nghị định/thông tư quy định chi tiết | `REFERS_TO {kind: details}` + `GUIDES` | `l:` kèm văn bản |
| `history` | các phiên bản trong `[day, to]` và văn bản đã sửa | `HAS_VERSION`, `CHANGED_BY` | phiên bản + `l:` của điều khoản sửa đổi |
| `document` | văn bản chứa điều này và văn bản đang áp dụng trong chuỗi thay thế | `HAS_PROVISION`, `REPLACES` | `d:` |
| `doc_relations` | (với `d:`) văn bản sửa đổi / thay thế / hướng dẫn / căn cứ | `AMENDS`, `REPLACES`, `GUIDES`, `BASED_ON` | `d:` |

Tối đa 10 mục mỗi lời gọi (còn lại: `more`), mỗi lời gọi đi **một bước**. Phần lớn là các truy vấn `LegalGraph` đã
có (`references`, `guidance`, `changes`, `applicable`) gói lại; cần thêm ba hàm đọc (§6.1).
Thay `law_changes`, `law_guidance`, `law_references`.

**Giới hạn duyệt luật.** Đồ thị luật có khoảng 110 nghìn nút; agent chỉ vào được từ một `l:` do `check` hoặc
`read_clause.cites_law` trả ra, và có ngân sách **6 lời gọi luật** mỗi câu hỏi (trong tổng 8 bước). Không có tìm kiếm
tự do trên toàn kho luật trong bản này (đó là việc của luồng hỏi đáp luật riêng).

### 4.7 `law_impact` — chiều ngược: điều luật chạm tới điều khoản nào

Tham số: `ref` (`l:`), `since?`. Trả: các khái niệm neo vào điều luật đó (hoặc cha/con của nó), mỗi khái niệm kèm
điều khoản hợp đồng mang nó (`c:`), giá trị liên quan, và `changed`: các phiên bản luật từ `since` (mặc định ngày ký)
tới hôm nay. Là kịch bản "luật đổi → điều khoản bị ảnh hưởng" của slide, trong phạm vi một hợp đồng.

### 4.8 `calc` — phép tính tất định

Tham số: `op ∈ {percent_of, add, subtract, multiply, compare}`, `args`: mỗi đối số là `f:` (lấy giá trị tại `day`)
hoặc số đã xuất hiện trong một thẻ. Trả giá trị, đơn vị, và công thức đã thay số (`85% × 15.000.000 = 12.750.000`).
LLM không còn tự nhân; kết quả `calc` là nguồn hợp lệ cho con số trong câu trả lời (§5.3).

### 4.9 `cypher_query` — giữ, không đổi

Chỉ trên đồ thị hợp đồng, chỉ khi có Neo4j, cho câu đếm/tổng hợp. Kết quả mang `node_id` thật được ứng dụng đổi
sang `c:` trước khi trả cho agent. **Không mở Cypher trên đồ thị luật**: kho luật dùng chung cho cả hệ thống và lớn;
`law_neighbors` đã phủ các phép duyệt cần thiết. Bộ kiểm theo spec TQH §4.10.

### 4.10 Ánh xạ từ bản 1

| Bản 1 | Bản 2 |
|---|---|
| `find_units`, `find_concept` | `locate` (+ `read_clause`) |
| `expand`, `subgraph` | `read_clause` (hợp đồng), `law_neighbors` (luật) |
| `find_path` | bỏ khỏi bộ công cụ; ứng dụng tự kiểm đường đi (`GraphNavigator.edge`) |
| `contract_facts` | `fact` |
| `check_concept`, `concept_basis` | `check` |
| `law_text_at` | `read_law` |
| `law_changes`, `law_guidance`, `law_references` | `law_neighbors` |
| — | `law_impact`, `calc` (mới) |
| `cypher_query` | `cypher_query` |

## 5. Vòng lặp agent

### 5.1 Giao thức

Giữ JSON từng bước (LLM của app chỉ có `complete(system, user)`), ba thay đổi:
- **Phần tĩnh lên `system`:** quy tắc, lược đồ tham chiếu, mô tả 8 công cụ, danh mục khái niệm. `user` chỉ còn câu
  hỏi, tóm tắt hợp đồng (các phần, nhãn điều khoản, khái niệm đã gán) và các bước. Phần tĩnh giống nhau giữa các bước
  và các câu hỏi nên được cache phía nhà cung cấp.
- **Nhiều lời gọi mỗi bước:** `{"thought", "calls": [{"tool", "args"}, …]}` tối đa 3, chạy tuần tự, trả kết quả cùng
  lúc (ví dụ `fact` + `check` + `read_law` trong một vòng).
- **Kết quả cũ được nén:** thẻ ở bước cách bước hiện tại hơn 2 vòng chỉ giữ `ref`, `label`, các con số và các `ref`
  đi tiếp; lời văn đầy đủ lấy lại bằng `read_*` nếu cần.

### 5.2 Câu trả lời có cấu trúc

```json
{"final": {
  "answer": "…",
  "claims": [{"text": "Lương thử việc là 12.750.000 đồng/tháng", "support": ["c:p0.d6", "c:p0.d2", "calc:1"]}],
  "legal": [{"concept": "k:probation.pay", "verdict": "ok"}],
  "path": ["c:p0.d6", "c:p0.d2", "k:probation.pay", "l:bo-luat:45/2019/QH14#d26"],
  "day": "2025-01-02", "confidence": "answer"}}
```

### 5.3 Rào chắn (ứng dụng thực thi, ngoài mô hình)

| Rào | Kiểm | Vi phạm |
|---|---|---|
| R1 Tham chiếu | mọi `ref` trong `claims.support` và `path` đã xuất hiện trong thẻ của lượt này | trả lại một lần, sau đó `partial` |
| R2 Đường đi | mỗi cặp liền kề trong `path` có `GraphNavigator.edge(a, b, day)`: `c→c` (REFERS_TO / AMENDS / CHILD_OF), `c→k` (có ConceptInstance), `k→l` (neo), `c→l` (CITES_LAW), `l→l` (cha/con, dẫn chiếu, hướng dẫn, CHANGED_BY tại `day`), `l→d` | `partial` + cảnh báo nêu cặp sai |
| R3 Dẫn chiếu chưa đọc | điều khoản trên `path` dẫn chiếu tới `c:` chưa có thẻ (đã có ở bản 1) | chặn một lần |
| R4 Con số | mọi con số trong `answer`/`claims` có trong một thẻ thuộc `support` hoặc là kết quả `calc`; đọc số bằng bộ đọc số của spec TQH §4.3 (không regex theo ngữ cảnh) | chặn một lần kèm danh sách số không truy được, sau đó `partial` |
| R5 Kết luận pháp lý | mỗi mục `legal` khớp một kết quả `check` của lượt này (cùng khái niệm, cùng `finding`); `legal` rỗng thì câu trả lời không được mang kết luận pháp lý: kiểm bằng một lời gọi phân loại nhỏ (có / không) thay cho danh sách từ khóa của bản 1 | `partial` + cảnh báo |
| R6 Ngân sách | 8 bước, 6 lời gọi luật, 3 lời gọi mỗi bước | ép kết luận, `partial` |
| R7 Ngày | `final.day` bằng ngày của các thẻ đã dùng, hoặc câu trả lời nêu rõ nhiều mốc | cảnh báo |

R5 thêm một lời gọi LLM mỗi câu trả lời; nếu không muốn trả giá đó thì bỏ vế "câu trả lời không được mang kết luận"
và chỉ kiểm trường `legal` (ghi trong §9, Q4).

## 6. Thay đổi ở các lớp dưới

### 6.1 `LegalGraph` (`rag/legal/graph/query.py`, gói của Huy) — ba hàm đọc mới

```python
def card(self, pid: str, day: date) -> dict       # text_at + cha, con, bộ đếm, changed_after_day: một lượt truy vấn
def children(self, pid: str, day: date, limit: int = 10) -> list[dict]
def find_provision(self, doc_hint: str, label: str, day: date) -> list[dict]   # ứng viên cho CITES_LAW (TQH §4.6)
```

Chỉ đọc, cùng quy ước con trỏ `LGMeta`/`build_id` như các hàm hiện có. Cần thống nhất với Huy ai viết (§9, Q3).

### 6.2 Đồ thị hợp đồng

Lược đồ v4: nút `LawCitation {law_pid, raw, resolved_at}`, cạnh `CITES_LAW: Unit → LawCitation`. Phụ thuộc bước trích
quan hệ của spec TQH; có thể làm sau, công cụ chịu được cầu trống.

### 6.3 Tệp

| Tệp | Việc |
|---|---|
| `rag/contracts/graph/navigator.py` (mới) | `GraphNavigator`, phân giải `ref`, thẻ, `edge` |
| `rag/contracts/graph/anchors.py` (mới) | `ConceptAnchors`, `CatalogAnchors`, `GraphAnchors` |
| `rag/contracts/graph/tools.py` | bộ công cụ bản 2; bản 1 giữ sau cờ `tools_version=1` để đo đối chứng |
| `rag/contracts/graph/agent.py` | giao thức §5.1, câu trả lời §5.2, rào R1–R7 |
| `rag/legal/graph/query.py` | ba hàm §6.1 |
| `scripts/bench_contract_agent.py` | bộ câu hỏi §7, cấu hình `v1` / `v2` |

## 7. Đo

Mở rộng bộ câu hỏi lên ≥ 24 câu, 6 nhóm, đáp án có kiểu (số, `ref`, ngày, `finding`):

| Nhóm | Ví dụ | Cần công cụ |
|---|---|---|
| Tra một điều khoản | "Thời gian thử việc bao lâu?" | `locate`, `read_clause` |
| Đi theo dẫn chiếu + tính | "Lúc thử việc được trả bao nhiêu?" | `read_clause`, `fact`, `calc` |
| Thời điểm / sửa đổi | "Lương căn bản tháng 8/2025 là bao nhiêu?" | `fact` |
| Kết luận pháp lý | "Lương thử việc có đúng luật không?" | `check`, `read_law` |
| **Duyệt luật** | "Điều luật nào quy định mức 85%, có văn bản hướng dẫn nào?"; "Điều 113 đã đổi gì từ ngày ký?"; "Khoản nào của Điều 24 cấm thử việc với hợp đồng dưới 1 tháng?" | `read_law`, `law_neighbors`, `law_impact` |
| Không trả lời được | "Tôi được thưởng Tết bao nhiêu?" (hợp đồng không ghi) | phải trả `cannot` |

Mỗi câu chạy 10 lần mỗi cấu hình (v1, v2), LLM không cache. Chỉ số: đúng (so đáp án có kiểu), qua rào, số bước, số
token vào, phân bố công cụ, tỉ lệ `cannot` đúng chỗ.

**Đạt yêu cầu khi** v2 không kém v1 về độ đúng ở bốn nhóm đầu, nhóm duyệt luật đúng ≥ 70% (v1 dự kiến gần 0 vì không
có đường đi), token vào trung bình giảm, và không công cụ nào có 0 lời gọi trên cả bộ câu hỏi.

## 8. Thứ tự làm và phụ thuộc

1. Bộ câu hỏi + đáp án có kiểu; đo v1 làm mốc (không phụ thuộc gì).
2. `GraphNavigator` + tham chiếu + `locate`, `read_clause`, `fact`, `check`, `calc` (chỉ phía hợp đồng + cầu khái niệm).
3. Ba hàm `LegalGraph` + `read_law`, `law_neighbors`, `law_impact`.
4. Giao thức mới + câu trả lời có cấu trúc + rào R1–R3, R6, R7.
5. Rào R4 (cần bộ đọc số, spec TQH §4.3) và R5.
6. Cầu `CITES_LAW` (cần trích quan hệ, spec TQH §4.6).

Bước 1–4 độc lập với spec TQH và có thể bắt đầu ngay. Lỗi ngày ký (ngày soát 2021) phải sửa trước khi đo nhóm thời
điểm và nhóm duyệt luật, nếu không mọi `day` mặc định đều sai.

## 9. Câu hỏi cần người dùng quyết

- **Q1. Phạm vi duyệt luật.** Chỉ vào từ neo khái niệm và dẫn chiếu trong hợp đồng với ngân sách 6 lời gọi (đề xuất),
  hay cho tìm tự do trong kho luật (cần thêm công cụ tìm kiếm và gần như là gộp luồng hỏi đáp luật vào agent này)?
- **Q2. Cypher trên đồ thị luật.** Đề xuất không mở. Đồng ý không?
- **Q3. Ba hàm `LegalGraph` mới.** Bạn viết (bạn là chủ tích hợp) hay giao Huy?
- **Q4. Rào R5.** Chấp nhận thêm một lời gọi phân loại mỗi câu trả lời, hay chỉ kiểm trường `legal` có cấu trúc?
- **Q5. Bản 1.** Giữ sau cờ tới khi v2 thắng trên bộ đo rồi xóa (đề xuất), hay thay thẳng?

## 10. Lựa chọn của người viết (chưa được xác nhận)

- Bỏ `expand`/`find_path`/`subgraph` khỏi tay agent: phép đo cho thấy hoặc không được dùng, hoặc là nguồn đi lạc.
- Không tạo cạnh vật lý giữa hai đồ thị; cầu là tham chiếu (`law_pid`, `concept_id`) do `GraphNavigator` phân giải:
  giữ nguyên tính "công bố nguyên khối theo hợp đồng" và việc đồ thị luật đổi bản dựng độc lập.
- `calc` là công cụ riêng thay vì để LLM tính rồi kiểm lại: kiểm một phép tính đã khai báo dễ hơn kiểm số học tự do.
- Thẻ trả sẵn lời văn của điều khoản được dẫn chiếu (tốn token hơn) vì đó là thứ đã làm giảm số bước trong phép đo.
