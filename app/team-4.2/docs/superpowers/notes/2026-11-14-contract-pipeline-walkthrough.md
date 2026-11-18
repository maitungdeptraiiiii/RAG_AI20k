# Luồng xử lý hợp đồng: từ lúc tải lên đến báo cáo

Ngày: 2026-11-14. Viết từ code ở nhánh `feat/team-4.2/w03-labor-contract-kg` (commit `471bcc1` cộng các thay đổi chưa
commit trong `facts.py`, `llm_json.py`, `review.py`). Mục đích là giải thích, không phải thiết kế. Thiết kế nằm ở
`specs/2026-11-12-contract-scale-design.md` và `specs/2026-11-13-contract-fact-verification-design.md`.

Ký hiệu cho mỗi bước:

- 🤖 **LLM**: gọi mô hình sinh văn bản (đều qua `ask_json`).
- ⚙️ **Quy tắc**: code thường, regex, so chuỗi. Cùng đầu vào thì luôn cùng đầu ra.
- 🔎 **ML**: mô hình không sinh văn bản (OCR, embedding, rerank).
- 👤 **Người**: người dùng thao tác trên giao diện.

---

## 0. Bức tranh chung

```
                         GIAI ĐOẠN 1: TẠO (một lần, khi tải lên)
 file ──► [1] nhận file ──► [2] đọc trang ──► [3] gộp văn bản ──► [4] bố cục phần ──► [5] tách cấu trúc
                               (OCR 🔎 nếu scan)                         ⚙️                    ⚙️
                                                                                                 │
          [9] lưu ◄── [8] dựng đồ thị ◄── [7] ghi SET_FIELD ◄── [6] trích dữ kiện 🤖 ◄────────────┘
              ⚙️            ⚙️ (Neo4j)             ⚙️                (theo lô)
              │
              ▼
                         GIAI ĐOẠN 2: XÁC MINH (người, không LLM)
         [10] bảng xác minh ──► [11] người xác nhận / sửa 👤 ──► [12] ghi thao tác + dựng lại đồ thị ⚙️
                                                                          │
                                                       cổng: đủ dữ kiện bắt buộc chưa?
                                                                          │
                         GIAI ĐOẠN 3: DÙNG                                ▼
         [13] soát: chọn phạm vi (🤖?) → FIND 🤖 theo lô → kiểm ⚙️ → tra luật 🔎 → VERIFY 🤖 → trạng thái ⚙️
         [14] đề xuất sửa 🤖   [15] thay đổi luật ⚙️   [16] tóm tắt 🤖   [17] hỏi đáp 🤖   [18] xuất file ⚙️
```

Nguyên tắc chia việc: **LLM chỉ làm việc cần hiểu ngôn ngữ** (đây là bên nào, ngày nào là ngày ký, điều khoản này có
vấn đề gì). **Mọi thứ cần đúng tuyệt đối dùng quy tắc** (cấu trúc, số liệu, kiểm trích dẫn, kết luận có căn cứ hay
không, lưu trữ). Mọi đầu ra của LLM đều phải đi qua một bước kiểm bằng quy tắc trước khi được dùng.

### Ví dụ chạy xuyên suốt

Dùng một hợp đồng lao động giả định, file `hdld_nguyen_van_a.pdf`, 4 trang, có chữ (không phải bản scan):

```
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM ...
HỢP ĐỒNG LAO ĐỘNG
Hôm nay, ngày 05 tháng 3 năm 2025, tại Hà Nội, chúng tôi gồm:
Bên A (Người sử dụng lao động): Công ty TNHH ABC, MST 0101234567
Bên B (Người lao động): Ông Nguyễn Văn A, CCCD 001203004567, SĐT 0912345678
Điều 1. Thời hạn và công việc
1. Loại hợp đồng: xác định thời hạn 24 tháng, từ ngày 01/4/2025.
2. Chức danh: Nhân viên kế toán. Nơi làm việc: 12 Láng Hạ, Hà Nội.
Điều 2. Thử việc
Thời gian thử việc 90 ngày.
Điều 3. Tiền lương
1. Mức lương: 15.000.000 đồng/tháng, trả ngày 10 hằng tháng.
...
Điều 8. Chấm dứt hợp đồng
Bên A được đơn phương chấm dứt nếu Bên B vi phạm Điều 3 ...
...
PHỤ LỤC 01
Điều 1. Phụ cấp ăn trưa 730.000 đồng/tháng.
```

---

## Giai đoạn 1: Tạo hợp đồng

Hàm điều phối: `ui/contracts_api.py::create()`. Các bước 1 đến 9 chạy liền một mạch trong một request.

### [1] Nhận file ⚙️

| | |
|---|---|
| **Code** | `contracts_api.handle_create` |
| **Nhận vào** | Request HTTP dạng form: `file` (byte của file) và cờ "Lưu lại" hay "Chỉ trong phiên". |
| **Xử lý** | Từ chối nếu quá 50 MB (HTTP 413). Lấy tên file và đuôi. |
| **Truyền đi** | `data: bytes`, `filename: str`, `persist: bool` cho `create()`. |

Ví dụ: `data` = 180 KB byte PDF, `filename = "hdld_nguyen_van_a.pdf"`, `persist = True`.

### [2] Đọc file thành các trang ⚙️ (🔎/🤖 cho trang scan)

| | |
|---|---|
| **Code** | `contracts_api._load_pages` → `rag/ingest/loaders.py::load_source` → `load_pdf` / `load_docx` / `load_text` / `load_image` |
| **Nhận vào** | `data`, `filename`. Byte được ghi ra một file tạm, đọc xong thì xóa. |
| **Xử lý** | Xem chi tiết bên dưới. |
| **Truyền đi** | Danh sách `Page` (mỗi trang một đối tượng, có thể là `Page`, `OCRPage`, `TablePage`, `FlaggedPage`), rồi chuyển thành `PageText(page, text, kind)`. |

Chi tiết theo loại file:

- **PDF**: PyMuPDF lấy chữ từng trang, sắp theo vị trí trên trang (`sort=True`). Sau đó `check_text` kiểm từng trang:
  - Trang có chữ tốt: dùng luôn (⚙️).
  - Trang rỗng (bản scan) hoặc chữ vỡ dấu (font cũ): chụp ảnh trang và gửi OCR. Engine là Gemini
    (`google/gemini-3.5-flash-lite` qua OpenRouter, `rag/ingest/ocr.py`). Đây là mô hình sinh văn bản đọc ảnh (🤖).
    Tesseract chạy cục bộ trên cùng ảnh chỉ để lấy độ tin cậy (🔎). Kết quả OCR được cache theo
    sha256 ảnh + mô hình + phiên bản prompt.
  - Bỏ đầu trang và chân trang lặp lại (`strip_headers_footers`).
- **DOCX**: đọc đoạn và bảng trong thân văn bản. Bản sao `TablePage` bị bỏ vì bảng đã có trong thân.
- **Ảnh**: bắt buộc OCR. Không cấu hình OCR thì báo lỗi.
- **TXT**: đọc thẳng.

Kiểm tra cuối bước: quá 150 trang thì từ chối toàn bộ (không nạp một phần). Không trang nào có chữ thì báo
"Không đọc được nội dung hợp đồng".

Ví dụ: PDF có chữ nên không OCR. Kết quả là 4 `PageText`:
```
PageText(page=1, text="CỘNG HÒA ... Hôm nay, ngày 05 tháng 3 năm 2025 ...", kind="Page")
PageText(page=2, text="Điều 3. Tiền lương ...", kind="Page")
...
```

### [3] Gộp văn bản, tính mã băm ⚙️

| | |
|---|---|
| **Code** | `contracts_api._set_pages`, `doc.assemble` |
| **Nhận vào** | `data` và danh sách `PageText`. |
| **Xử lý** | Nối các trang thành một văn bản liền, ghi lại ranh giới trang (để sau này biết đơn vị nằm ở trang nào). Tính SHA-256 của file gốc. Tạo đối tượng `Contract` với id ngẫu nhiên. |
| **Truyền đi** | `Contract` có `text`, `page_texts`, `file_checksum`, `pages` (số ký tự và loại của từng trang). |

### [4] Đề xuất bố cục phần ⚙️

| | |
|---|---|
| **Code** | `contracts_api._layout_op` → `parts.py::detect_parts` |
| **Nhận vào** | `contract.text`. |
| **Xử lý** | Quét từng dòng. Dòng nào giống tiêu đề phụ lục (`PHỤ LỤC 01`, `Phụ lục số 2`, ngắn, không kết thúc bằng dấu chấm, không nằm ngay sau `MỤC LỤC`) thì mở một phần mới. Phần `p0` luôn là hợp đồng chính. |
| **Truyền đi** | Một thao tác `SET_LAYOUT` ghi vào **nhật ký thao tác** (`contract.oplog`) với `origin = "rule"`, `status = "auto_accepted"`. |

Ví dụ:
```
SET_LAYOUT {parts: [
  {part_id: "p0", kind: "main",     title: "",            start: 0},
  {part_id: "p1", kind: "appendix", title: "PHỤ LỤC 01",  start: 5120, number: 1}
]}
```

Nhật ký thao tác là **nguồn sự thật** của hợp đồng: nó chỉ chứa các **quyết định** (bố cục, giá trị trường, câu trả lời
của người). Những gì tính lại được từ file gốc (cây Điều, giá trị, dẫn chiếu) thì không ghi vào nhật ký. Người dùng
sửa bố cục thì thêm một thao tác mới thay thế thao tác cũ; không bao giờ xóa.

### [5] Tách cấu trúc ⚙️

| | |
|---|---|
| **Code** | `structure.py::parse_contract` (gọi `tree.parse_part`, `values.extract_values`, `xrefs.find_xrefs`), rồi `to_contract_units` |
| **Nhận vào** | `page_texts` và bố cục phần đang hiệu lực (lấy từ nhật ký). |
| **Xử lý** | 1. Với mỗi phần: tách thành cây **Phần mở đầu / Điều / khoản / điểm** theo đánh số (văn bản không đánh số thì tách theo đoạn). 2. Trích **giá trị** bằng regex trong từng đơn vị: tiền, ngày, tỉ lệ, thời hạn. Giá trị chạm vùng PII (CCCD, SĐT) bị bỏ. 3. Tìm **dẫn chiếu nội bộ** ("vi phạm Điều 3", "khoản 1 Điều này"). 4. Lập **báo cáo chất lượng**: đếm Điều/khoản/điểm, số bị đứt ("Điều 4 → Điều 6"), tỉ lệ văn bản không đánh số, trang nghi thiếu chữ. |
| **Truyền đi** | `ContractDoc` (parts, units dạng cây, values, xrefs, report). Từ đó lấy ra `contract.units`: danh sách **đơn vị cấp cao nhất** (`ContractUnit(uid, label, text, page)`), là thứ được gửi cho LLM về sau. |

Ví dụ `contract.units`:
```
u1  "Phần mở đầu"              "Hôm nay, ngày 05 tháng 3 năm 2025 ... Bên B ... Ông Nguyễn Văn A ..."
u2  "Điều 1"                   "Điều 1. Thời hạn và công việc\n1. Loại hợp đồng: ..."
u3  "Điều 2"                   "Điều 2. Thử việc ..."
u4  "Điều 3"                   "Điều 3. Tiền lương ..."
...
u9  "Điều 8"                   "Điều 8. Chấm dứt hợp đồng ... vi phạm Điều 3 ..."
u10 "Phụ lục 1 — Điều 1"       "Điều 1. Phụ cấp ăn trưa ..."
```
Giá trị: `u4#v1 money 15.000.000 đồng`, `u2#v1 date 2025-04-01`, `u3#v1 duration 90 ngày`...
Dẫn chiếu: `u9 → u4` ("vi phạm Điều 3"). Có tiền tố phần nên "Điều 1" của phụ lục không bị nhầm với "Điều 1" của
hợp đồng chính.

### [6] Trích dữ kiện nền 🤖 (bước quan trọng nhất của giai đoạn 1)

| | |
|---|---|
| **Code** | `facts.py::extract_facts`, `batches.py`, `llm_json.py` |
| **Nhận vào** | `Contract` (cần `units`, `doc.xrefs`, `mask_state`) và một client LLM. |
| **Truyền đi** | `contract.facts` (dict, xem cuối mục) và có thể `contract.sign_date`. |

Bước này có 5 bước con:

**6a. Chia lô ⚙️** (`make_batches`). Gom các đơn vị liền nhau đến khi gần vượt 12.000 ký tự. Đơn vị một mình dài hơn
24.000 ký tự thì cắt thành nhiều mảnh cùng `uid`. Mỗi lô kèm thêm, **chỉ để đọc hiểu**:
- `context`: phần mở đầu và Điều định nghĩa (nếu có), mỗi thứ tối đa 3.000 ký tự;
- `references`: nguyên văn các Điều mà lô dẫn chiếu tới nhưng không nằm trong lô, tổng tối đa 3.000 ký tự.

Hợp đồng ví dụ ngắn (khoảng 9.000 ký tự) nên chỉ có **1 lô** chứa u1 đến u10. Hợp đồng dài 30.000 ký tự sẽ có
khoảng 3 lô; khi đó lô chứa Điều 8 sẽ được gửi kèm nguyên văn Điều 3 vì có dẫn chiếu.

**6b. Gọi LLM từng lô, tuần tự 🤖** (`ask_json` với prompt `FACTS_PROMPT`). Payload gửi đi:
```json
{"units": [{"uid": "u1", "label": "Phần mở đầu", "text": "..."}, ...],
 "context": [...], "references": [...],
 "known_parties": [],              // lô sau nhận các bên mà lô trước đã trích
 "fields_wanted": [{"key": "labor_kind", "label": "Loại hợp đồng lao động",
                    "options": ["Không xác định thời hạn", "Xác định thời hạn"]},
                   {"key": "salary", ...}, ...]}   // lấy từ fact_catalog.json
```
`ask_json` làm 3 việc quanh lời gọi LLM:
1. **Che PII** trong mọi chuỗi gửi đi: `001203004567` thành `[HD_CCCD_1]`, `0912345678` thành `[HD_PHONE_1]`.
   Bảng ánh xạ nằm trong `contract.mask_state`, không gửi đi.
2. Gọi `llm.complete(prompt, payload)`. Lỗi mạng hoặc API thì ném `ContractAIError`.
3. Đọc JSON trả về (chịu được trường hợp mô hình bọc trong ```json), rồi **mở che** mọi chuỗi trong kết quả.

LLM trả về, ví dụ:
```json
{"type": "Hợp đồng lao động",
 "parties": [{"name": "Công ty TNHH ABC", "role": "Người sử dụng lao động", "unit": "u1",
              "quote": "Bên A (Người sử dụng lao động): Công ty TNHH ABC"},
             {"name": "Ông Nguyễn Văn A", "role": "Người lao động", "unit": "u1", "quote": "..."}],
 "sign_date": {"value": "2025-03-05", "unit": "u1", "quote": "Hôm nay, ngày 05 tháng 3 năm 2025"},
 "effective_date": {"value": "2025-04-01", "unit": "u2", "quote": "từ ngày 01/4/2025"},
 "term": {"value": "24 tháng", "unit": "u2", "quote": "xác định thời hạn 24 tháng"},
 "fields": {"labor_kind": {"value": "Xác định thời hạn", "unit": "u2", "quote": "..."},
            "salary": {"value": "15.000.000 đồng/tháng", "unit": "u4", "quote": "Mức lương: 15.000.000 đồng/tháng"},
            "probation_period": {"value": "90 ngày", "unit": "u3", "quote": "Thời gian thử việc 90 ngày"}}}
```
Lô lỗi (JSON hỏng, lỗi API) được thử lại 1 lần. Vẫn lỗi thì ghi vào `warnings` ("Chưa đọc được Điều 6 – Điều 12")
và các lô khác vẫn chạy.

**6c. Kiểm trích dẫn ⚙️** (`_checked` → `quote_ok`). Với **mỗi** giá trị LLM trả về:
- `quote` phải có nguyên văn trong một đơn vị **thuộc chính lô này**. So sau khi chuẩn hóa: Unicode NFC, hoa thường,
  khoảng trắng, dấu nháy, bỏ chuỗi điền chỗ trống (`-----`, `.....`, `____`).
- Câu trích ghép nhiều dòng không liền nhau (khoản 1 + khoản 3) được nhận khi **mọi** dòng dài từ 8 ký tự trở lên có
  nguyên văn trong nguồn và đúng thứ tự.
- LLM ghi sai `unit` nhưng câu trích có ở đơn vị khác trong lô: sửa `unit` cho đúng.
- Không khớp ở đâu trong lô, hoặc chỉ khớp trong `context`/`references`: **bỏ giá trị**, không đoán.

Bước này chặn được việc LLM bịa chữ, nhưng **không** chặn được việc LLM hiểu sai một câu có thật (ví dụ lấy ngày của
một bản sửa đổi làm ngày ký).

**6d. Gộp các bên ⚙️** (`_merge_party`, `_text_aliases`, `_distinct_roles`). Gộp ngay sau mỗi lô:
- Trùng **tên** đã chuẩn hóa (bỏ ngoặc, dấu câu, hoa thường) thì là cùng một bên.
- Tên mới trùng **bí danh** của một bên đã có thì là cùng bên. Bí danh lấy từ vai trò ("Bên A / Người sử dụng lao
  động"), chữ trong ngoặc của tên, và tên gọi tắt đọc từ văn bản (`Công ty X (sau đây gọi là "Bên A")`).
- Không gộp theo tập con chữ: "Nantz" và "Nantz Communications" là hai bên khác nhau.
- Hai bên khác nhau nhưng cùng vai trò thì vai trò thành "vai trò — tên" để ô "Bạn là bên nào" phân biệt được.

**6e. Gộp các giá trị khác ⚙️** (`_add`, cuối `extract_facts`):
- Mỗi trường có một danh sách **ứng viên**; giá trị trùng (sau chuẩn hóa) chỉ giữ một lần.
- Ngày được chuẩn hóa về `YYYY-MM-DD`; giá trị trường có `options` phải khớp một lựa chọn (`normalize_value`).
- Loại hợp đồng: lấy loại của lô đầu tiên (lô có phần mở đầu).
- **Ngày ký**: có đúng 1 ứng viên thì đặt `contract.sign_date` và `sign_date_source = "text"`. Có từ 2 ứng viên khác
  nhau thì **không** đặt; bảng xác minh sẽ hiện trạng thái "mâu thuẫn" cho người chọn.

Kết quả ghi vào `contract.facts`:
```
facts = {
  "type": "Hợp đồng lao động",
  "parties": [{name, role, unit, quote, aliases?}, ...],
  "sign_date": {...} | None, "effective_date": {...}, "value": ..., "term": {...},   # ứng viên đầu tiên, dạng cũ
  "other_dates": [...],
  "candidates": {"sign_date": [{value, unit, quote}], "salary": [...], "labor_kind": [...], ...},
  "questions": [],                        # câu hỏi cho người dùng, sinh ra ở bước soát
  "coverage": {"read": 10, "total": 10},  # số đơn vị đã đọc được
  "warnings": []                          # lô lỗi
}
```

Nếu mọi lô đều lỗi: `create()` bắt `ContractAIError`, đặt `facts = {"type": "chưa rõ", "parties": [], "error": ...}`
và vẫn đi tiếp. Hợp đồng vẫn được tạo; người dùng phải tự điền ở bước xác minh.

### [7] Ghi kết quả máy vào nhật ký ⚙️

| | |
|---|---|
| **Code** | cuối `create()` |
| **Nhận vào** | `facts["type"]` và `contract.sign_date`. |
| **Xử lý** | Với loại hợp đồng (nếu khác "chưa rõ") và ngày ký (nếu có), thêm thao tác `SET_FIELD` với `origin = "llm"`, `status = "auto_accepted"`. |
| **Truyền đi** | Nhật ký có thêm tối đa 2 thao tác. Đồ thị ở bước 8 đọc loại và ngày ký từ đây. |

Ví dụ: `SET_FIELD type = "Hợp đồng lao động"`, `SET_FIELD sign_date = "2025-03-05"`.

Lưu ý: hai giá trị này **chưa được người xác minh** nhưng đã vào đồ thị (ngày ký thành `valid_from` của mọi nút `Unit`).
Khi người dùng sửa ở giai đoạn 2, đồ thị được dựng lại.

### [8] Dựng và công bố đồ thị ⚙️

| | |
|---|---|
| **Code** | `contracts_api._rebuild` → `graph/service.py::rebuild` → `graph/build.py::build_graph`, `validate`, `neo4j_store.publish` |
| **Nhận vào** | `contract_id`, `page_texts`, nhật ký thao tác, `file_checksum`. |
| **Xử lý** | 1. **Tách lại** từ trang theo bố cục trong nhật ký (cùng `parse_contract` ở bước 5). 2. Tính `build_id` = băm của (checksum file, phiên bản bộ tách, phiên bản lược đồ, danh sách thao tác đang hiệu lực). Cùng đầu vào thì cùng `build_id`. 3. Sinh nút và cạnh. Văn bản trong nút được **che PII**. 4. **Kiểm**: cạnh đúng loại và đúng miền/đích theo `schema.json`, nút thuộc đúng hợp đồng, không còn PII, khoảng hiệu lực không chồng nhau. 5. Không có lỗi kiểm thì **công bố nguyên khối** lên Neo4j. |
| **Truyền đi** | `ContractDoc` (cập nhật `contract.doc`, `contract.units`) và trạng thái `{enabled, build_id, published, problems, error, record}` lưu vào `contract.graph`; bản ghi bản dựng thêm vào `contract.builds`. |

Nút và cạnh (chỉ lớp cấu trúc; lớp ngữ nghĩa như nghĩa vụ, quyền, điều kiện **chưa làm**):
```
Contract {type, sign_date}
  ─HAS_PART─► Part {kind, title}
                ─HAS_UNIT─► Unit {uid, level, label, text (đã che), page_start, valid_from = ngày ký}
                              ─CHILD_OF─► Unit (cha)
                              ─REFERS_TO {raw: "vi phạm Điều 3"}─► Unit
                              ─HAS_VALUE─► Value {kind, raw, giá trị chuẩn hóa}
```

Neo4j tắt hoặc sập: hợp đồng vẫn tạo được, `graph.error` ghi lý do và giao diện hiện "Đồ thị chưa cập nhật". Sau một
lần lỗi kết nối, 30 giây sau mới thử lại. Neo4j **không** phải nguồn sự thật: xóa sạch Neo4j rồi dựng lại từ file
gốc và nhật ký phải ra đúng đồ thị cũ.

### [9] Lưu và trả thẻ hợp đồng ⚙️

| | |
|---|---|
| **Code** | `store.py::ContractStore.add`, `contracts_api.card` |
| **Nhận vào** | `Contract` hoàn chỉnh, byte file gốc. |
| **Xử lý** | Luôn giữ trong bộ nhớ. Nếu "Lưu lại": ghi `<root>/<id>/original.pdf` và `<root>/<id>/contract.json` (ghi ra file tạm rồi đổi tên, để không bao giờ có file ghi dở). |
| **Truyền đi** | JSON "thẻ hợp đồng" cho giao diện: dữ kiện, danh sách đơn vị, các phần, báo cáo tách, trạng thái đồ thị, **bảng xác minh** (`verify.summary`). |

`contract.json` chứa: văn bản, đơn vị, trang, `facts`, `party`, `sign_date`, `reports` (báo cáo soát), `operations`
(nhật ký thao tác), `graph`, `builds`. Khi mở lại, cây đơn vị được tách lại từ trang và nhật ký, không đọc từ Neo4j.

---

## Giai đoạn 2: Xác minh dữ kiện (không có LLM)

### [10] Dựng bảng xác minh ⚙️

| | |
|---|---|
| **Code** | `verify.py::fields`, `summary` |
| **Nhận vào** | `facts["candidates"]`, `fact_catalog.json`, nhật ký thao tác. |
| **Xử lý** | Chọn danh sách trường theo loại hợp đồng: các trường chung (bên, ngày ký, loại, ngày hiệu lực, thời hạn, giá trị) cộng các trường của loại (lao động: loại HĐLĐ, chức danh, nơi làm việc, lương, thử việc...). Với mỗi trường, xác định trạng thái từ ứng viên và câu trả lời của người. |
| **Truyền đi** | Bảng gồm các dòng `{key, label, required, options, candidates, value, unit, quote, status}`, danh sách trường bắt buộc còn thiếu, các câu hỏi. |

Trạng thái mỗi dòng:

| Trạng thái | Khi nào |
|---|---|
| `found` | Máy đọc ra đúng 1 ứng viên, người chưa xác nhận |
| `conflict` | Máy đọc ra từ 2 ứng viên khác nhau |
| `missing` | Máy không đọc ra |
| `confirmed` | Người chọn đúng một giá trị máy đã đọc |
| `corrected` | Người nhập giá trị khác máy |
| `unknown` | Người chọn "không biết" (không áp dụng cho bên và ngày ký) |

Ví dụ: "Bạn là bên nào" luôn bắt đầu ở trạng thái chưa xác minh (máy không thể biết người dùng là ai), với các lựa chọn
"Tôi là Người sử dụng lao động", "Tôi là Người lao động", "Trung lập / tư vấn".

### [11] Người dùng xác nhận hoặc sửa 👤

| | |
|---|---|
| **Code** | `contracts_api.set_facts` → `verify.apply_answers`; cũng có `set_party`, `set_sign_date`, `set_layout` |
| **Nhận vào** | `{key: {action: "confirm" | "set" | "unknown", value?}}`, tên người thao tác. |
| **Xử lý** | Kiểm từng câu trả lời: giá trị hợp lệ theo kiểu (ngày, tiền, lựa chọn); không "xác nhận" được trường đang mâu thuẫn; không "không biết" được bên và ngày ký. Một câu trả lời sai thì **không ghi gì cả**. |
| **Truyền đi** | Mỗi câu trả lời thành một thao tác `SET_FIELD` với `origin = "human"`, **thay thế** thao tác cũ cùng đích (thao tác cũ vẫn còn trong nhật ký, chỉ hết hiệu lực). Đồng bộ `contract.party`, `contract.sign_date`. |

Ví dụ: người dùng gửi `{"party": {"action": "set", "value": "Người lao động"}, "salary": {"action": "confirm"}}`.

### [12] Ghi, dựng lại, lưu ⚙️

| | |
|---|---|
| **Code** | `contracts_api._change` |
| **Xử lý** | Trong **khóa ghi** của hợp đồng (ai đang sửa thì người kia nhận HTTP 409): chụp trạng thái → ghi thao tác → dựng lại đồ thị (bước 8) → lưu (bước 9). Bất kỳ bước nào lỗi thì **trả hợp đồng về đúng trạng thái trước** rồi báo lỗi. |
| **Truyền đi** | Thẻ hợp đồng mới. Đổi ngày ký thì `build_id` đổi và đồ thị được công bố lại. |

**Cổng xác minh** (`verify.check_gate`): các thao tác soát, soát một phần, thay đổi luật, đề xuất sửa bị chặn
(HTTP 409 kèm danh sách trường còn thiếu) cho tới khi mọi trường **bắt buộc** ở trạng thái `confirmed`, `corrected`
hoặc `unknown`. Tóm tắt và hỏi đáp không bị chặn.

---

## Giai đoạn 3: Dùng hợp đồng

Hàm điều phối: `contracts_api.run(cid, op, unit_ids, topics)` cho soát, tóm tắt, thay đổi luật, đề xuất sửa;
`chat_answer` và `chat_think` cho hỏi đáp. Tất cả nằm trong `review.py` trừ hỏi đáp kiểu agent.

### [13] Soát hợp đồng (`review`, `partial`)

Đây là chức năng chính. Gồm 7 bước con.

**13a. Chọn phạm vi** (`_scope`)
- Người chọn điều khoản cụ thể: lấy đúng các đơn vị đó ⚙️.
- Người chọn **chủ đề** ("thử việc", "lương"): mỗi lô gửi LLM prompt `SELECT` 🤖, LLM trả danh sách uid liên quan.
  Chỉ nhận uid hoặc nhãn có thật ⚙️.
- Không chọn gì: toàn bộ hợp đồng.

**13b. Chia lô** ⚙️: như bước 6a, trên các đơn vị trong phạm vi.

**13c. Tìm vấn đề, từng lô** 🤖 (`_find_batch`, prompt `FIND`). Payload:
```json
{"party": "Người lao động",                  // bên của người dùng, ưu tiên điểm bất lợi cho bên này
 "contract_type": "Hợp đồng lao động",
 "parties": [...],
 "known_facts": {"facts": {"Mức lương": "15.000.000 đồng/tháng", ...},  // chỉ dữ kiện ĐÃ xác minh
                 "answered_questions": [...]},
 "units": [...], "context": [...], "references": [...]}
```
LLM trả:
```json
{"findings": [{"unit": "u3", "quote": "Thời gian thử việc 90 ngày", "group": "illegal", "severity": "major",
               "disadvantaged": "Người lao động",
               "explanation": "Thử việc 90 ngày vượt mức tối đa cho công việc trình độ cao đẳng trở lên (60 ngày)",
               "legal_question": "thời gian thử việc tối đa theo trình độ công việc",
               "law_hint": "Bộ luật Lao động 2019", "suggestion": "...",
               "needs_info": true,
               "cases": [{"if": "công việc cần trình độ cao đẳng trở lên", "conclusion": "vượt mức, trái luật"},
                         {"if": "công việc khác", "conclusion": "vượt mức 30 hoặc 6 ngày"}]}],
 "questions": [{"question": "Công việc kế toán này yêu cầu trình độ nào?", "options": [...], "unit": "u3"}]}
```
Bốn nhóm: `illegal` (trái luật), `missing_required` (thiếu nội dung bắt buộc), `unfavorable` (bất lợi), `ambiguous`
(mơ hồ). Khi kết luận phụ thuộc thông tin không có trong hợp đồng, LLM phải trả kết luận theo từng trường hợp và một
câu hỏi cho người dùng, không được đoán.

**13d. Kiểm từng phát hiện** ⚙️
- Gán phát hiện vào đơn vị (chấp nhận cả khi LLM ghi nhãn "Điều 2" thay vì uid).
- `quote_ok`: trích dẫn sai thì `needs_check = True`, xóa trích dẫn và **không xét pháp lý**. Riêng nhóm
  `missing_required` được phép không có trích dẫn (vì nội dung bị thiếu thì không có chữ để trích).
- Giá trị lạ (nhóm, mức độ không hợp lệ) được đưa về mặc định.
- Câu hỏi được gắn mã băm theo nội dung, lưu vào `facts["questions"]`; câu hỏi trùng không bị hỏi lại.

**13e. Tra căn cứ luật** 🔎 (`evidence.find_evidence`). Chỉ với phát hiện pháp lý (`illegal`, `missing_required` hoặc
có `legal_question`) **và** trích dẫn đúng **và** đã có ngày ký:
- Câu tra (`legal_question`) được che PII trước khi gửi đi.
- Tìm top 3 trong kho luật **có phiên bản**, chỉ lấy điều luật **có hiệu lực tại ngày ký** (embedding + rerank).
- Thêm kết quả từ kho cũ (không có phiên bản).
- Chưa có ngày ký: `legal_status = "blocked_no_date"`, kèm lời nhắc nhập ngày ký.

Kết quả là các `LawEvidence {eid, store: versioned|legacy, source_title, section, text, valid_from, valid_to, status}`.

**13f. Xác minh căn cứ** 🤖 (`_verify`, prompt `VERIFY`). Một lời gọi cho mọi phát hiện. LLM nhận nhận định và các
điều luật ứng viên, trả `eid` nào **thực sự** hỗ trợ nhận định (không chỉ cùng chủ đề). Chỉ nhận `eid` nằm trong
danh sách ứng viên ⚙️, nên LLM không thể bịa ra một căn cứ.

**13g. Quyết định trạng thái pháp lý, sắp xếp** ⚙️ (`_legal_status`)

| Căn cứ được giữ lại | `legal_status` | Hiển thị |
|---|---|---|
| Có ít nhất một điều luật từ kho có phiên bản, không mâu thuẫn | `concluded` | Kết luận, kèm căn cứ |
| Chỉ có căn cứ từ kho cũ | `conditional` | Kèm ghi chú "chưa xác định phiên bản; kết luận có điều kiện" |
| Không còn căn cứ nào | `cannot_conclude` | **Từ chối kết luận**: "Kho chưa có [luật] ... chưa thể kết luận". Nhãn đổi thành "Nghi vấn trái luật — chưa kết luận" |
| Không phải vấn đề pháp lý | `not_legal` | Ghi chú "Nhận xét về câu chữ / thương mại — không phải kết luận pháp lý" |

Sắp xếp: phát hiện bất lợi cho bên của người dùng đứng trước, sau đó theo mức nghiêm trọng.

**Truyền đi**: một báo cáo `{rid, op, findings, questions, coverage: {reviewed, total, requested?}, scope,
batches, warnings, build_id}` lưu vào `contract.reports` và trả cho giao diện. `build_id` ghi lại báo cáo này làm trên
bản dựng nào của đồ thị.

### [14] Đề xuất sửa (`redline`) 🤖

| | |
|---|---|
| **Nhận vào** | Báo cáo soát mới nhất **trên đúng bản dựng hiện tại**. Chưa có thì chạy bước 13 trước. |
| **Xử lý** | Gửi LLM (prompt `REDLINE`) các phát hiện kèm nguyên văn đơn vị. LLM viết lại từng đoạn theo hướng bảo vệ bên của người dùng (hoặc cân bằng nếu trung lập). Kiểm ⚙️: "đoạn cũ" phải khớp **liền mạch** với văn bản hợp đồng (`quote_ok(multi=False)`) thì mới thay được. Phát hiện chưa kết luận pháp lý được ghi "Chưa kiểm tra pháp lý". |
| **Truyền đi** | Báo cáo `{redlines: [{finding_id, old, old_ok, new, reason, legal_note}]}`. |

### [15] Thay đổi luật (`law_changes`) ⚙️

| | |
|---|---|
| **Nhận vào** | Báo cáo soát mới nhất (chạy bước 13 nếu chưa có, khi đó có LLM). |
| **Xử lý** | Lấy mọi điều luật đã làm căn cứ trong báo cáo, so phiên bản **tại ngày ký** với phiên bản **hôm nay** trong kho có phiên bản. |
| **Truyền đi** | Danh sách điều luật đã đổi, kèm các điều khoản hợp đồng bị ảnh hưởng. |

Hạn chế: chỉ xét điều luật mà lần soát đã tìm ra; căn cứ bị sót thì thay đổi của nó cũng bị sót (H8 trong spec).

### [16] Tóm tắt (`summary`) 🤖

| | |
|---|---|
| **Nhận vào** | `llm_units(contract.units)` (**chỉ 30 đơn vị đầu**) và `facts`. |
| **Xử lý** | Prompt `SUMMARY`: tóm theo các mục Các bên, Đối tượng, Giá và thanh toán, Thời hạn, Nghĩa vụ chính, Mốc thời gian, Luật áp dụng. Mỗi ý gắn `unit`. Không có bước kiểm trích dẫn. |
| **Truyền đi** | Báo cáo `{sections: [{title, items: [{text, unit, unit_label}]}]}`. |

### [17] Hỏi đáp

**`chat_answer` (hỏi thường)**
1. 🔎 Có ngày ký thì tra top 4 điều luật hiệu lực tại ngày ký (câu hỏi được che PII).
2. 🤖 Prompt `ANSWER`: gửi câu hỏi, 3 lượt hỏi đáp gần nhất, **30 đơn vị đầu**, các điều luật. LLM trả
   `{answer, legal_conclusion, law_ids, units}`.
3. ⚙️ Nếu `legal_conclusion = true`:
   - chưa có ngày ký: thay câu trả lời bằng lời nhắc nhập ngày ký;
   - có ngày ký: 🤖 `VERIFY` các `law_ids`, rồi ⚙️ `_legal_status` như bước 13g. `cannot_conclude` thì thay câu
     trả lời bằng lời từ chối (không nhắc lại kết luận chưa kiểm chứng).
4. Trả câu trả lời, căn cứ, các điều khoản liên quan, mốc thời gian.

**`chat_think` (hỏi với Think)** 🤖: agent nhiều bước (`agent_view.run_contract_agent`) trên hợp đồng, kho luật có
phiên bản tại ngày ký và kho cũ. Tối đa 2 vòng tìm, hạn 300 giây, có thể trả theo luồng. Ghi chú này không mô tả bên
trong agent.

### [18] Xuất báo cáo ⚙️

`contracts_api.download` → `export.py`: dựng DOCX hoặc PDF từ một báo cáo đã lưu. Không gọi LLM.

---

## Tổng hợp: bước nào dùng LLM

| Bước | Dùng LLM? | Prompt | Đầu ra LLM được kiểm bằng |
|---|---|---|---|
| [2] Đọc file | Chỉ với trang scan hoặc ảnh (OCR Gemini) | prompt OCR | Tesseract confidence (chỉ báo, không chặn) |
| [6] Trích dữ kiện | 🤖 Có, mỗi lô một lần | `FACTS_PROMPT` | Trích dẫn nằm trong đơn vị của lô; chuẩn hóa kiểu; gộp bằng quy tắc; **người xác minh** |
| [13a] Chọn theo chủ đề | 🤖 Chỉ khi chọn chủ đề | `SELECT` | Chỉ nhận uid hoặc nhãn có thật |
| [13c] Tìm vấn đề | 🤖 Có, mỗi lô một lần | `FIND` | Trích dẫn; nhóm và mức độ hợp lệ |
| [13f] Xác minh căn cứ | 🤖 Có, một lần | `VERIFY` | Chỉ nhận `eid` trong ứng viên; trạng thái pháp lý do quy tắc quyết |
| [14] Đề xuất sửa | 🤖 Có | `REDLINE` | Đoạn cũ phải khớp liền mạch |
| [16] Tóm tắt | 🤖 Có | `SUMMARY` | Không kiểm trích dẫn |
| [17] Hỏi đáp | 🤖 Có (1–2 lần) | `ANSWER`, `VERIFY` | Như [13f] cho kết luận pháp lý |
| [1], [3], [4], [5], [7]–[12], [15], [18] | ⚙️ Không | | |

Mọi lời gọi đều đi qua `llm_json.ask_json`: che PII trước khi gửi, mở che sau khi nhận, đòi JSON hợp lệ. Lỗi thì ném
`ContractAIError`; giao diện nhận HTTP 502 "AI trả kết quả không hợp lệ, hãy thử lại", **không** hiểu là "không có
vấn đề".

## Hạn chế đã biết của luồng hiện tại

1. **Tóm tắt và hỏi đáp chỉ thấy 30 đơn vị đầu** (`parse.llm_units`, `DEMO_MAX_UNITS = 30`) và không cảnh báo người
   dùng. Soát thì đã chia lô và báo độ phủ đầy đủ.
2. **Ngày ký và loại hợp đồng do LLM đọc vào đồ thị trước khi người xác minh.** Bước soát vẫn bị chặn tới khi xác minh,
   nhưng đồ thị công bố lần đầu có thể mang ngày sai (ví dụ ngày của một bản sửa đổi đính kèm, ca Sonos trong
   `2026-11-13-cuad-facts-benchmark.md`).
3. **Bộ tách chưa nhận bản sửa đổi hoặc văn bản đính kèm là một phần riêng**, chỉ nhận tiêu đề "PHỤ LỤC".
4. **Kiểm trích dẫn chỉ chặn bịa chữ**, không chặn hiểu sai. Ngăn hiểu sai dựa vào bảng xác minh (dữ kiện) và bước
   `VERIFY` cộng trạng thái pháp lý (kết luận).
5. **Lớp ngữ nghĩa của đồ thị chưa có**: nghĩa vụ, quyền, điều kiện, hệ quả (bước 7 trong thứ tự làm của spec, §6.1,
   §7.3). Đồ thị hiện chỉ có cấu trúc văn bản.
6. **Trang có cả chữ và hình**: hình không được OCR.
