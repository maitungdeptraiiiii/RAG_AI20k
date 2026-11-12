# Đồ thị hợp đồng — Kế hoạch 1: bộ tách mới, dẫn chiếu, nhật ký thao tác, bản dựng, Neo4j (lớp cấu trúc)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hợp đồng thật (Word / PDF có chữ) được tách đủ — phần, Điều, khoản, điểm, trang, giá trị, dẫn chiếu — không cắt, có báo cáo chất lượng, và được dựng thành lớp cấu trúc của đồ thị trong Neo4j từ một nhật ký thao tác sửa được.

**Architecture:** Bộ tách là hàm thuần trên danh sách trang → `ContractDoc`. Nhật ký thao tác (`OperationLog`) chỉ chứa quyết định (`SET_LAYOUT`, `SET_FIELD` trong kế hoạch này). Bản dựng là hàm thuần (trang + nhật ký → nút / cạnh + `build_id` tất định) → kiểm → công bố nguyên khối vào Neo4j trong một giao dịch. Neo4j là dữ liệu dẫn xuất, bật bằng biến môi trường; tắt hoặc không chạy thì phần hợp đồng vẫn chạy như Phần 4.

**Tech Stack:** Python 3.12, dataclasses, `re`, PyMuPDF (loader sẵn có), Neo4j 5.26 Community (Docker), thư viện `neo4j` cho Python, pytest (`uv run --extra dev pytest`).

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-12-contract-scale-design.md` (bản nháp 3) — kế hoạch này làm §13 bước 1, 2, 3 và phần không cần người hiểu luật của bước 0.

**Không thuộc kế hoạch này** (các kế hoạch sau, theo §13): sửa kịch bản demo phạt 20% (bước 0 — cần người xác nhận luật); soát theo lô, mốc thời gian tường minh (bước 4); phụ lục tải sau, `AMEND_UNIT` (bước 5); danh mục vấn đề pháp lý (bước 6); mệnh đề `ASSERT` và lớp ngữ nghĩa (bước 7); giao diện duyệt (bước 8) — gồm cả màn hình sửa bố cục phần; kế hoạch này chỉ có endpoint `POST /api/contracts/{id}/layout`; truy vấn đồ thị (bước 9); đo (bước 10); OCR (bước 11). Mọi cải tiến trong `2026-11-12-contract-graph-market-review.md` cũng không thuộc kế hoạch này.

Chạy mọi lệnh từ `app/team-4.2/`.

## Global Constraints

- Không cắt hợp đồng ở bước tách: bỏ giới hạn 30 đơn vị khỏi việc nạp (spec §5.1.4). Giới hạn duy nhất: **150 trang** mỗi lần nạp; vượt thì từ chối với thông báo `"Hợp đồng dài hơn 150 trang — chưa hỗ trợ"`, không nạp một phần.
- Trong kế hoạch này, lượt soát toàn bộ (`review` không chọn điều khoản) vẫn chỉ gửi `DEMO_MAX_UNITS = 30` đơn vị mức Điều đầu cho LLM và báo `coverage {"reviewed": 30, "total": N}` — soát theo lô là kế hoạch 2. Không chỗ nào khác được cắt.
- Mã đơn vị ổn định theo cấu trúc: `p0.pre`, `p0.d5`, `p0.d5.k2`, `p0.d5.k2.a`, `p1.d1`, `p0.o3` (đoạn). Chữ `đ` trong mã điểm viết là `dd`. p0 = hợp đồng chính.
- Nhãn hiển thị tiếng Việt: `Phần mở đầu`, `Điều 5`, `khoản 2 Điều 5`, `điểm a khoản 2 Điều 5`, `Mục II`, `Mục 3`, `Đoạn 3`; đơn vị trong phụ lục thêm tiền tố `Phụ lục 1 — ` (số lấy từ tiêu đề phần; không có số thì thứ tự phần).
- Trạng thái thao tác đúng bốn giá trị của kho luật: `auto_accepted`, `pending`, `approved`, `rejected`. Không có thao tác xóa.
- Mã thao tác do máy sinh = `"o" + sha256(contract_id|op_type|target|source_uid|json(content, sort_keys))[:12]`; thao tác của người = `"h" + secrets.token_hex(6)`.
- Neo4j chỉ giữ bản dựng đang công bố; mọi nút có nhãn chung `CGNode`, thuộc tính `node_id` (duy nhất toàn cục, dạng `<contract_id>:<mã>`), `contract_id`, `build_id`.
- Thuộc tính văn bản ghi vào Neo4j ở dạng đã che PII (`MaskState(prefix="HD_")` mới, che lần lượt theo thứ tự đơn vị — tất định). Số tiền, ngày, tỉ lệ không che.
- Biến môi trường: `CONTRACT_GRAPH=1` bật; `NEO4J_URI` (mặc định `bolt://localhost:7687`), `NEO4J_USER` (mặc định `neo4j`), `NEO4J_PASSWORD` (bắt buộc khi bật), `NEO4J_DATABASE` (mặc định `neo4j`). Không viết mật khẩu vào file được theo dõi.
- Kiểm thử tự động chỉ dùng hợp đồng tự soạn; kiểm thử cần Neo4j bỏ qua khi không có `NEO4J_TEST_URI`.
- Thông báo cho người dùng bằng tiếng Việt.

## Review Focus

1. Danh sách đánh số trong phần mở đầu ("1. Ông Nguyễn Văn A …" khi mô tả các bên) không được thành Điều / Mục khi hợp đồng có "Điều N." — test ở Task 3.
2. Câu thân bài bắt đầu bằng "Điều 5 của Hợp đồng được sửa đổi như sau" (thường gặp trong phụ lục) không phải tiêu đề Điều — test ở Task 3.
3. "Phụ lục 1 đính kèm" giữa câu, hoặc dòng "PHỤ LỤC" trong mục lục đầu văn bản không có nội dung sau đó, không tạo phần mới — test ở Task 2.
4. Neo4j không chạy / sai mật khẩu lúc nạp hợp đồng: hợp đồng vẫn tạo được, thẻ báo `graph.error`, không ném lỗi ra API — test ở Task 9.
5. Hợp đồng đã lưu theo định dạng Phần 4 (không có `page_texts`, uid `u1…`) mở lại được, hỏi và xuất được, báo cáo cũ mang `pre_graph: true` — test ở Task 10.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `src/rag/contracts/values.py` (mới) | Trích số tiền, tỉ lệ, ngày, thời hạn bằng quy tắc |
| `src/rag/contracts/doc.py` (mới) | Kiểu dữ liệu: `PageText`, `PartSpec`, `Unit`, `Value`, `CrossRef`, `ParseReport`, `ContractDoc`; ghép trang → văn bản + bản đồ vị trí → trang |
| `src/rag/contracts/parts.py` (mới) | Đề xuất bố cục phần (hợp đồng chính / phụ lục) |
| `src/rag/contracts/tree.py` (mới) | Cây Điều / khoản / điểm cho một phần |
| `src/rag/contracts/xrefs.py` (mới) | Dẫn chiếu nội bộ |
| `src/rag/contracts/structure.py` (mới) | `parse_contract` ghép các bước trên + báo cáo chất lượng |
| `src/rag/contracts/parse.py` (sửa) | `split_units` thành lớp tương thích trên `parse_contract`; giữ `limit_units`, `DEMO_MAX_UNITS` |
| `src/rag/contracts/graph/__init__.py`, `oplog.py` (mới) | `GraphOperation`, `OperationLog` |
| `src/rag/contracts/graph/schema.json`, `build.py` (mới) | Lược đồ có phiên bản; bản dựng thuần + kiểm |
| `src/rag/contracts/graph/neo4j_store.py`, `service.py` (mới) | Ghi Neo4j; dịch vụ dựng-kiểm-công bố + khóa ghi |
| `src/rag/contracts/models.py`, `store.py` (sửa) | `Contract` thêm trang, checksum, nhật ký, tài liệu đã tách, trạng thái đồ thị; lưu / nạp; tương thích Phần 4 |
| `src/rag/contracts/review.py` (sửa) | Giới hạn 30 chuyển vào lượt soát toàn bộ; báo cáo mang cảnh báo đọc |
| `ui/contracts_api.py`, `ui/contracts.js` (sửa) | Nạp qua bộ tách mới, thao tác `SET_FIELD` / `SET_LAYOUT`, endpoint bố cục, thẻ hợp đồng |
| `docker/neo4j-compose.yml` (mới), `pyproject.toml`, `../../.gitignore` (sửa) | Hạ tầng |

---

### Task 1: Giá trị trích bằng quy tắc

**Files:**
- Create: `src/rag/contracts/values.py`
- Test: `tests/test_contracts_values.py`

**Interfaces:**
- Produces: `extract_values(text: str) -> list[RawValue]`; `RawValue(kind: Literal["money","percent","date","duration"], raw: str, norm: dict, start: int, end: int)` (frozen dataclass). `norm`: money `{"amount": int, "currency": "VND"|"USD"}`; percent `{"percent": float}`; date `{"iso": "YYYY-MM-DD"}`; duration `{"n": int, "unit": "ngày"|"tuần"|"tháng"|"năm"|"giờ"}`.

- [ ] **Step 1: Write the failing tests**

```python
from rag.contracts.values import extract_values

def kinds(text): return [(v.kind, v.norm) for v in extract_values(text)]

def test_money_forms():
    assert kinds("Tiền thuê 30.000.000 đồng/tháng") == [("money", {"amount": 30000000, "currency": "VND"})]
    assert kinds("đặt cọc 90 triệu đồng") == [("money", {"amount": 90000000, "currency": "VND"})]
    assert kinds("giá 1,5 tỷ VNĐ") == [("money", {"amount": 1500000000, "currency": "VND"})]
    assert kinds("phí 2.000 USD") == [("money", {"amount": 2000, "currency": "USD"})]

def test_percent_and_dates():
    assert kinds("phạt 20% giá trị") == [("percent", {"percent": 20.0})]
    assert kinds("ký ngày 15 tháng 3 năm 2023") == [("date", {"iso": "2023-03-15"})]
    assert kinds("từ 01/08/2024") == [("date", {"iso": "2024-08-01"})]

def test_duration_not_taken_from_inside_a_date():
    vals = kinds("ngày 15 tháng 3 năm 2023, báo trước 30 ngày, thời hạn 3 năm")
    assert vals == [("date", {"iso": "2023-03-15"}), ("duration", {"n": 30, "unit": "ngày"}),
                    ("duration", {"n": 3, "unit": "năm"})]

def test_spans_point_at_raw_text():
    text = "đặt cọc 90 triệu đồng"
    v = extract_values(text)[0]
    assert text[v.start:v.end] == v.raw == "90 triệu đồng"
```

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_values.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `extract_values` in `src/rag/contracts/values.py`**

Thứ tự quét: ngày → tiền → tỉ lệ → thời hạn; mỗi lần quét bỏ qua vùng đã bị một giá trị trước đó chiếm; kết quả sắp theo `start`. Điểm xuất phát cho biểu thức: `MONEY_RE`, `PERCENT_RE`, `TIME_LIMIT_RE` của Law-RAG (`law_rag/extraction/legal_entities.py`), mở rộng: đơn vị `đồng | VNĐ | VND | vnđ | USD`, dạng "N triệu / N tỷ" có hoặc không có "đồng", dấu phân cách nghìn `.` hoặc dấu cách, phần lẻ `,`. Ngày: "ngày D tháng M năm Y" và `D/M/Y`, `D-M-Y`; ngày không hợp lệ thì bỏ. Thời hạn: `\b\d+\s*(ngày|tuần|tháng|năm|giờ)\b`.

- [ ] **Step 4: Run to verify they pass** — cùng lệnh → 4 passed.

- [ ] **Step 5: Commit** — `git add src/rag/contracts/values.py tests/test_contracts_values.py && git commit -m "feat(team-4.2): rule-based contract values (money, percent, date, duration)"`

---

### Task 2: Kiểu dữ liệu, ghép trang, bố cục phần

**Files:**
- Create: `src/rag/contracts/doc.py`, `src/rag/contracts/parts.py`
- Test: `tests/test_contracts_parts.py`

**Interfaces:**
- Produces (trong `doc.py`, frozen dataclass trừ khi ghi khác):
  - `PageText(page: int | None, text: str, kind: str = "Page")`
  - `Assembled(text: str, page_starts: list[tuple[int, int | None]])` + `page_at(self, offset: int) -> int | None`; `assemble(pages: list[PageText]) -> Assembled` — nối bằng `"\n\n"`, NFC, `\r\n` → `\n`.
  - `PartSpec(part_id: str, kind: Literal["main","appendix"], title: str, start: int, number: int | None)` — `start` là vị trí ký tự trong văn bản đã ghép; phần chạy tới `start` của phần kế tiếp.
  - `Unit(uid, part_id, parent_uid: str | None, level: Literal["preamble","article","clause","point","paragraph"], number: str, label: str, text: str, char_start: int, char_end: int, page_start: int | None, page_end: int | None, version: int = 1)`
  - `Value(vid: str, uid: str, kind: str, raw: str, norm: dict, start: int, end: int)` — `vid = f"{uid}#v{i}"` (i từ 1 trong đơn vị).
  - `CrossRef(from_uid: str, to_uid: str | None, raw: str, kind: Literal["internal","appendix","external_law","missing"])`
  - `ParseReport(styles: dict[str, str], counts: dict[str, int], gaps: list[str], unstructured_ratio: float, warn_pages: list[int], warnings: list[str])`
  - `ContractDoc(parts: list[PartSpec], units: list[Unit], values: list[Value], xrefs: list[CrossRef], report: ParseReport)` + `unit(uid) -> Unit | None`, `children(uid) -> list[Unit]`, `top_units() -> list[Unit]` (cấp `preamble`/`article`/`paragraph` của mọi phần, theo thứ tự).
- Produces (trong `parts.py`): `detect_parts(text: str) -> list[PartSpec]` — luôn có `p0` (`main`, `start=0`).

- [ ] **Step 1: Write the failing tests**

```python
from rag.contracts.doc import PageText, assemble
from rag.contracts.parts import detect_parts

def test_page_map():
    a = assemble([PageText(1, "Điều 1. A"), PageText(2, "Điều 2. B")])
    assert a.text == "Điều 1. A\n\nĐiều 2. B"
    assert a.page_at(0) == 1 and a.page_at(a.text.index("Điều 2")) == 2

def test_appendix_headings_start_parts():
    text = "HỢP ĐỒNG\nĐiều 1. A\n\nPHỤ LỤC 01\nĐiều 1. Giá\n\nPhụ lục 2: Bản vẽ\nNội dung"
    parts = detect_parts(text)
    assert [(p.part_id, p.kind, p.number) for p in parts] == [("p0", "main", None), ("p1", "appendix", 1), ("p2", "appendix", 2)]
    assert text[parts[1].start:].startswith("PHỤ LỤC 01")

def test_inline_mention_and_toc_are_not_parts():
    text = ("MỤC LỤC\nPHỤ LỤC\nĐiều 1. Bên A giao nhà theo Phụ lục 1 đính kèm.\n"
            "Điều 2. Các bên ký Phụ lục 1 cùng ngày.")
    assert [p.part_id for p in detect_parts(text)] == ["p0"]
```

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_parts.py -v` → FAIL.

- [ ] **Step 3: Implement `doc.py` and `detect_parts` in `parts.py`**

Một dòng là tiêu đề phụ lục khi: đứng đầu dòng, dòng ≤ 100 ký tự, và hoặc bắt đầu bằng `PHỤ LỤC` viết hoa, hoặc khớp `^Phụ lục\s+(số\s+)?\d+\b` và dòng trước nó trống (hoặc là dòng đầu). Loại tiêu đề nếu trong 3 dòng không trống tiếp theo không có dòng nào dài hơn 20 ký tự (dòng mục lục). `number` = số đầu tiên trong dòng tiêu đề, không có thì `None`.

- [ ] **Step 4: Run to verify they pass** — 3 passed.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): contract document types, page map, appendix part detection"` (kèm hai file mã và file test).

---

### Task 3: Cây Điều / khoản / điểm

**Files:**
- Create: `src/rag/contracts/tree.py`
- Test: `tests/test_contracts_tree.py`

**Interfaces:**
- Consumes: `Unit`, `PartSpec`, `Assembled` (Task 2).
- Produces: `parse_part(a: Assembled, part: PartSpec, end: int, label_prefix: str) -> tuple[list[Unit], str, list[str]]` — trả (đơn vị theo thứ tự cây, tên kiểu đánh số `"dieu" | "roman" | "numeric" | "paragraph"`, danh sách mô tả chỗ đứt số).

- [ ] **Step 1: Write the failing tests**

```python
from rag.contracts.doc import PageText, PartSpec, assemble
from rag.contracts.tree import parse_part

def parse(text):
    a = assemble([PageText(1, text)])
    return parse_part(a, PartSpec("p0", "main", "", 0, None), len(a.text), "")

CONTRACT = """HỢP ĐỒNG THUÊ NHÀ
Bên A:
1. Ông Nguyễn Văn A
2. Bà Trần Thị B
Điều 1. Đối tượng
Bên A cho Bên B thuê nhà.
Điều 2. Giá thuê
1. Giá thuê là 30.000.000 đồng/tháng.
2. Thanh toán:
a) trước ngày 5 hằng tháng;
đ) bằng chuyển khoản.
Điều 4. Chấm dứt
4.1. Bên A được chấm dứt theo khoản 1 Điều 2.
4.2. Điều 5 của Hợp đồng gốc được sửa đổi như sau: bỏ."""

def test_tree_ids_labels_levels():
    units, style, gaps = parse(CONTRACT)
    assert style == "dieu"
    assert [u.uid for u in units] == ["p0.pre", "p0.d1", "p0.d2", "p0.d2.k1", "p0.d2.k2", "p0.d2.k2.a",
                                       "p0.d2.k2.dd", "p0.d4", "p0.d4.k1", "p0.d4.k2"]
    u = {x.uid: x for x in units}
    assert u["p0.d2.k2.a"].label == "điểm a khoản 2 Điều 2" and u["p0.d2.k2.a"].parent_uid == "p0.d2.k2"
    assert u["p0.d4.k1"].label == "khoản 1 Điều 4"
    assert "2. Bà Trần Thị B" in u["p0.pre"].text          # danh sách trong phần mở đầu không thành Mục
    assert u["p0.d2"].text.startswith("Điều 2.") and "đ) bằng chuyển khoản." in u["p0.d2"].text
    assert gaps == ["p0: sau Điều 2 là Điều 4"]

def test_body_line_starting_with_dieu_is_not_a_heading():
    units, _, _ = parse(CONTRACT)
    assert "p0.d5" not in {x.uid for x in units}

def test_roman_numeric_and_paragraph_fallbacks():
    assert [u.label for u in parse("I. Chung\nNội dung\nII. Giá\nNội dung")[0]] == ["Mục I", "Mục II"]
    assert [u.uid for u in parse("HỢP ĐỒNG\n1. Đối tượng\nA\n2. Giá\nB")[0]] == ["p0.pre", "p0.d1", "p0.d2"]
    units, style, _ = parse("Bên A bán xe.\n\nGiá 20 triệu.")
    assert style == "paragraph" and [u.label for u in units] == ["Đoạn 1", "Đoạn 2"]

def test_article_style_variants():
    assert [u.uid for u in parse("ĐIỀU 1: A\nx\nArticle 2. B\ny")[0]] == ["p0.d1", "p0.d2"]
```

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_tree.py -v` → FAIL.

- [ ] **Step 3: Implement `parse_part` in `tree.py`**

Quy tắc (đầu dòng, đã `strip` trái):

| Cấp | Mẫu |
|---|---|
| Điều | `^(Điều|ĐIỀU|Article|ARTICLE)\s+(\d+[a-zđ]?)\s*[.:\-–]` (phải có dấu sau số — "Điều 5 của …" không khớp) |
| La Mã (cấp trên cùng) | `^([IVXLC]+)\s*[.)]\s+\S` |
| Số (cấp trên cùng khi không có Điều / La Mã) | `^(?:Mục\s+)?(\d+)\s*[.)]\s+\S` |
| Khoản (trong Điều / Mục) | `^(?:Khoản\s+)?(\d+)\s*[.)]\s+\S` hoặc `^(\d+)\.(\d+)\.?\s+\S` với số đầu = số của Điều |
| Điểm (trong khoản, hoặc trong Điều không có khoản) | `^([a-zđ])\s*[).]\s+\S` |

Chọn kiểu cấp trên cùng: ưu tiên Điều nếu có ≥ 2 dòng khớp, rồi La Mã, rồi Số; không có thì tách đoạn theo dòng trống. Chấp nhận một dòng khớp chỉ khi số của nó lớn hơn số trước đó (cùng cấp, cùng cha) và không vượt quá số trước + 3; số đầu tiên của một cấp phải ≤ 3. Bước nhảy > 1 ghi chỗ đứt số (`"p0: sau Điều 2 là Điều 4"`). Điểm theo thứ tự chữ cái tiếng Việt `a b c d đ e g h i k l m n o p q r s t u v x y`, bỏ qua tối đa 3 chữ (cùng ngưỡng với số). Văn bản trước đơn vị cấp trên cùng đầu tiên là `preamble` (bỏ nếu rỗng). Văn bản của một đơn vị bao trùm cả con của nó; `char_start/char_end` theo văn bản đã ghép; trang từ `Assembled.page_at`. Nhãn La Mã giữ chữ La Mã (`Mục II`), mã dùng số Ả Rập (`p0.d2`).

- [ ] **Step 4: Run to verify they pass** — 4 passed.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): article/clause/point tree with stable unit ids and numbering gaps"`

---

### Task 4: Dẫn chiếu nội bộ

**Files:**
- Create: `src/rag/contracts/xrefs.py`
- Test: `tests/test_contracts_xrefs.py`

**Interfaces:**
- Consumes: `Unit`, `PartSpec`, `CrossRef`.
- Produces: `find_xrefs(units: list[Unit], parts: list[PartSpec]) -> list[CrossRef]`.

- [ ] **Step 1: Write the failing tests**

```python
from rag.contracts.doc import PartSpec, Unit
from rag.contracts.xrefs import find_xrefs

def U(uid, level, text, parent=None, part="p0"):
    return Unit(uid, part, parent, level, uid.rsplit(".", 1)[-1], uid, text, 0, len(text), None, None)

UNITS = [U("p0.d2", "article", "Điều 2."), U("p0.d2.k1", "clause", "1. Giá", "p0.d2"),
         U("p0.d9", "article", "Điều 9."),
         U("p0.d9.k1", "clause", "1. Bên A chấm dứt.", "p0.d9"),
         U("p0.d9.k3", "clause", "3. Trường hợp tại khoản 1 Điều này và khoản 1 Điều 2; xem Điều 15; "
                                  "theo Điều 328 Bộ luật Dân sự; giá tại Phụ lục 1.", "p0.d9")]
PARTS = [PartSpec("p0", "main", "", 0, None), PartSpec("p1", "appendix", "PHỤ LỤC 1", 999, 1)]

def test_resolution_kinds():
    refs = {(r.raw, r.to_uid, r.kind) for r in find_xrefs(UNITS, PARTS)}
    assert ("khoản 1 Điều này", "p0.d9.k1", "internal") in refs
    assert ("khoản 1 Điều 2", "p0.d2.k1", "internal") in refs
    assert ("Điều 15", None, "missing") in refs
    assert ("Điều 328 Bộ luật Dân sự", None, "external_law") in refs
    assert ("Phụ lục 1", None, "appendix") in refs        # phần p1 có nhưng chưa có đơn vị trong danh sách này

def test_self_and_ancestor_refs_dropped():
    units = [U("p0.d3", "article", "Điều 3. Theo Điều này các bên…")]
    assert find_xrefs(units, PARTS[:1]) == []
```

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_xrefs.py -v` → FAIL.

- [ ] **Step 3: Implement `find_xrefs`**

Chỉ quét đơn vị lá (không có con). Điểm xuất phát: `ARTICLE_REF_RE` của Law-RAG, mở rộng các dạng `điểm x khoản M Điều N`, `khoản M Điều N`, `khoản M Điều này`, `khoản M` (đứng riêng = Điều hiện tại), `Điều này`, `Điều N`, `Phụ lục (số)? N`. Theo sau là "của|theo|tại" + (`Bộ luật|Luật|Nghị định|Thông tư`) → `external_law`, `raw` gồm cả tên văn bản tới dấu câu kế tiếp. Trong phần phụ lục, "Điều N của Hợp đồng" trỏ về `p0`. Phụ lục N → đơn vị cấp trên cùng đầu tiên của phần có `number == N` (kind `appendix`, `to_uid` = mã đó; không có phần đó → `None`). Không tìm thấy đích nội bộ → `missing`. Bỏ dẫn chiếu tới chính đơn vị hoặc tổ tiên của nó.

- [ ] **Step 4: Run to verify they pass** — 2 passed.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): internal cross-references with relative resolution"`

---

### Task 5: `parse_contract` + báo cáo chất lượng + lớp tương thích

**Files:**
- Create: `src/rag/contracts/structure.py`
- Modify: `src/rag/contracts/parse.py` (giữ `DEMO_MAX_UNITS`, `limit_units`; `split_units` gọi `parse_contract`)
- Test: `tests/test_contracts_structure.py`; `tests/test_contracts_parse_store.py` phải vẫn qua (uid đổi sang `p0.*` — test hiện chỉ kiểm nhãn và tính duy nhất)

**Interfaces:**
- Consumes: Task 1–4.
- Produces:
  - `parse_contract(pages: list[PageText], parts: list[PartSpec] | None = None) -> ContractDoc` — `parts=None` thì gọi `detect_parts`.
  - `PARSER_VERSION = "1"` (đổi khi đổi quy tắc tách — là đầu vào của bản dựng).
  - `to_contract_units(doc: ContractDoc) -> list[ContractUnit]` — `doc.top_units()` → `ContractUnit(uid, label, text, page=page_start)`.

- [ ] **Step 1: Write the failing tests**

```python
from rag.contracts.doc import PageText
from rag.contracts.structure import parse_contract, to_contract_units

def long_contract(n=60):
    return "\n".join(f"Điều {i}. Nội dung {i}\n1. Khoản một.\n2. Khoản hai." for i in range(1, n + 1))

def test_sixty_articles_nothing_dropped():
    doc = parse_contract([PageText(1, long_contract())])
    assert doc.report.counts == {"article": 60, "clause": 120, "point": 0}
    assert len(to_contract_units(doc)) == 60

def test_appendix_units_do_not_collide():
    text = "Điều 1. A\nx\nĐiều 2. B\ny\n\nPHỤ LỤC 1\nĐiều 1. Giá\nz\nĐiều 2. Lịch\nw"
    doc = parse_contract([PageText(None, text)])
    labels = [u.label for u in to_contract_units(doc)]
    assert labels == ["Điều 1", "Điều 2", "Phụ lục 1 — Điều 1", "Phụ lục 1 — Điều 2"]
    assert len({u.uid for u in doc.units}) == len(doc.units)

def test_report_warnings_gaps_and_thin_pages():
    pages = [PageText(i, "Điều %d. " % i + "chữ " * 300) for i in (1, 2)] + [PageText(3, "Điều 4. x")] \
            + [PageText(4, "Điều 5. " + "chữ " * 300)]
    r = parse_contract(pages).report
    assert r.warn_pages == [3]
    assert any("trang 3" in w for w in r.warnings) and any("Điều 4" in w for w in r.warnings)

def test_values_attached_to_leaf_units():
    doc = parse_contract([PageText(1, "Điều 3. Đặt cọc\n1. Tiền cọc 90 triệu đồng.\n2. Hoàn trả trong 30 ngày.")])
    assert [(v.uid, v.kind) for v in doc.values] == [("p0.d3.k1", "money"), ("p0.d3.k2", "duration")]
    assert doc.values[0].vid == "p0.d3.k1#v1"
```

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_structure.py -v` → FAIL.

- [ ] **Step 3: Implement `structure.py`, update `parse.py`**

`label_prefix` cho phụ lục = `f"Phụ lục {number or index} — "`. Giá trị: chạy `extract_values` trên văn bản riêng của mỗi đơn vị lá (phần không thuộc con nào), đổi vị trí sang vị trí trong văn bản đơn vị. Báo cáo:
- `styles` = kiểu đánh số theo phần; `counts` = số `article` / `clause` / `point`;
- `unstructured_ratio` = ký tự trong đơn vị `preamble` + `paragraph` / tổng ký tự; > 0,3 → cảnh báo "Không nhận ra đánh số Điều / khoản cho phần lớn văn bản";
- `warn_pages`: chỉ khi có ≥ 3 trang có số trang — trang có số ký tự < 0,25 × trung vị, hoặc `kind == "OCRPage"`; mỗi trang một cảnh báo `"Trang N có thể chứa nội dung chưa đọc được"`;
- mỗi chỗ đứt số một cảnh báo `"Đánh số không liền mạch: <gap>"`.

`split_units(text)` = `to_contract_units(parse_contract([PageText(None, text)]))`.

- [ ] **Step 4: Run to verify they pass** — `uv run --extra dev pytest tests/test_contracts_structure.py tests/test_contracts_parse_store.py -v` → tất cả qua.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): parse_contract with parse report; split_units on the new parser"`

---

### Task 6: Nhật ký thao tác

**Files:**
- Create: `src/rag/contracts/graph/__init__.py`, `src/rag/contracts/graph/oplog.py`
- Test: `tests/test_contracts_oplog.py`

**Interfaces:**
- Produces:
  - `OpType = Literal["SET_LAYOUT","SET_FIELD","ASSERT","AMEND_UNIT"]`, `Origin = Literal["rule","llm","human"]`, `ReviewStatus` (bốn giá trị).
  - `GraphOperation` (frozen): `op_id, contract_id, op_type, target: str | None, content: dict, origin, status, created_at: datetime, source_uid: str | None = None, quote: tuple[str, ...] = (), status_reasons: tuple[str, ...] = (), reviewer: str | None = None, reviewed_at: datetime | None = None, note: str | None = None, supersedes: str | None = None, model: str | None = None, prompt_version: str | None = None`.
  - `machine_op(contract_id, op_type, target, content, origin, status, *, source_uid=None, quote=(), at) -> GraphOperation` (mã theo Global Constraints); `human_op(contract_id, op_type, target, content, reviewer, *, note="", source_uid=None, quote=(), at) -> GraphOperation` (status `approved`).
  - `class OperationLog(contract_id, ops=())`: `add(op) -> bool` (trùng mã → `False`, không đổi gì); `set_review(op_id, status, reviewer, note, at)`; `supersede(old_id, new_op, reviewer, note, at)` (cũ → `rejected`, mới mang `supersedes=old_id`); `active() -> list[GraphOperation]` (status `auto_accepted` | `approved`, theo thứ tự thêm); `field(name) -> Any` (giá trị `content["value"]` của thao tác `SET_FIELD` đang có hiệu lực thêm sau cùng cho `target == name`, không có → `None`); `layout() -> list[dict] | None`; `all() -> list`; `to_json() -> list[dict]`; `from_json(contract_id, data) -> OperationLog`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timezone
from rag.contracts.graph.oplog import OperationLog, human_op, machine_op

T = datetime(2026, 11, 12, tzinfo=timezone.utc)

def test_machine_ids_are_content_hashes_and_dedupe():
    a = machine_op("c1", "SET_FIELD", "type", {"value": "thuê nhà"}, "llm", "auto_accepted", at=T)
    b = machine_op("c1", "SET_FIELD", "type", {"value": "thuê nhà"}, "llm", "auto_accepted", at=T)
    log = OperationLog("c1")
    assert a.op_id == b.op_id and a.op_id.startswith("o") and log.add(a) and not log.add(b)

def test_human_supersede_wins_and_keeps_history():
    log = OperationLog("c1")
    m = machine_op("c1", "SET_FIELD", "sign_date", {"value": "2023-03-15"}, "llm", "auto_accepted", at=T)
    log.add(m)
    h = human_op("c1", "SET_FIELD", "sign_date", {"value": "2023-03-16"}, "Tùng", at=T)
    log.supersede(m.op_id, h, "Tùng", "sai ngày", T)
    assert log.field("sign_date") == "2023-03-16"
    old = next(o for o in log.all() if o.op_id == m.op_id)
    assert old.status == "rejected" and old.reviewer == "Tùng"
    assert next(o for o in log.all() if o.op_id == h.op_id).supersedes == m.op_id

def test_rejected_and_pending_not_active_and_json_roundtrip():
    log = OperationLog("c1")
    p = machine_op("c1", "SET_FIELD", "type", {"value": "x"}, "llm", "pending", at=T)
    log.add(p)
    assert log.active() == [] and log.field("type") is None
    again = OperationLog.from_json("c1", log.to_json())
    assert again.all() == log.all()
```

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_oplog.py -v` → FAIL.

- [ ] **Step 3: Implement `oplog.py`** — JSON: `datetime` dạng ISO, `tuple` thành `list` và đổi lại khi nạp.

- [ ] **Step 4: Run to verify they pass** — 3 passed.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): contract graph operation log (review states, supersede, content-hash ids)"`

---

### Task 7: Lược đồ, bản dựng thuần, kiểm

**Files:**
- Create: `src/rag/contracts/graph/schema.json`, `src/rag/contracts/graph/build.py`
- Test: `tests/test_contracts_graph_build.py`

**Interfaces:**
- Consumes: `parse_contract`, `PARSER_VERSION` (Task 5); `OperationLog` (Task 6); `MaskState`, `mask_text` (`rag.quality.pii`).
- Produces:
  - `schema.json`: `{"version": "1", "nodes": ["Contract","Part","Unit","Value"], "relations": {"HAS_PART": [["Contract"],["Part"]], "HAS_UNIT": [["Part"],["Unit"]], "CHILD_OF": [["Unit"],["Unit"]], "REFERS_TO": [["Unit"],["Unit"]], "HAS_VALUE": [["Unit"],["Value"]]}}` (mỗi quan hệ: [miền, đích]).
  - `GraphNode(node_id, label, props: dict)`, `GraphEdge(type, src, dst, props: dict)`, `GraphBuild(build_id, contract_id, built_at: datetime, inputs: dict, nodes: tuple, edges: tuple, problems: tuple[str, ...])` (frozen) + `record() -> dict` (mọi thứ trừ `nodes`/`edges`, thêm `n_nodes`, `n_edges`).
  - `build_graph(contract_id: str, pages: list[PageText], oplog: OperationLog, *, file_checksum: str, built_at: datetime) -> tuple[GraphBuild, ContractDoc]` — bố cục lấy từ `oplog.layout()` (dict → `PartSpec`); trường `type`, `sign_date` từ `oplog.field`.
  - `validate(build: GraphBuild) -> list[str]`.

Nút và thuộc tính (mọi nút thêm `contract_id`, `build_id`):

| Nút | `node_id` | Thuộc tính |
|---|---|---|
| Contract | `<cid>` | `type`, `sign_date` |
| Part | `<cid>:<part_id>` | `kind`, `title` (đã che), `number` |
| Unit | `<cid>:<uid>@<version>` | `uid`, `part_id`, `level`, `label`, `text` (đã che), `page_start`, `page_end`, `version`, `valid_from` (= `sign_date` hoặc `None`), `valid_to` (`None`), `unresolved_refs` (list `raw` của dẫn chiếu `missing` / `external_law` / phụ lục không có đích) |
| Value | `<cid>:<vid>` | `kind`, `raw`, các khóa của `norm` |

Cạnh: `HAS_PART` (Contract → Part), `HAS_UNIT` (Part → mọi Unit của phần), `CHILD_OF` (Unit con → Unit cha), `REFERS_TO` (dẫn chiếu có `to_uid`; props `raw`), `HAS_VALUE`.

`inputs` = `{"file_checksum", "parser_version", "schema_version", "op_ids": [mã thao tác đang hiệu lực theo thứ tự]}`; `build_id = "b" + sha256(json(inputs, sort_keys))[:12]`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timezone
from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph, validate, GraphEdge
from rag.contracts.graph.oplog import OperationLog, human_op
import dataclasses

T = datetime(2026, 11, 12, tzinfo=timezone.utc)
PAGES = [PageText(1, "Bên A: Nguyễn Văn An, CCCD 001203004567\nĐiều 1. Giá\n1. Giá 30 triệu đồng.\n"
                     "2. Thanh toán theo khoản 1 Điều này.")]

def test_deterministic_ids_and_content():
    b1, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    b2, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T.replace(year=2027))
    assert b1.build_id == b2.build_id and b1.nodes == b2.nodes
    ids = {n.node_id for n in b1.nodes}
    assert {"c1", "c1:p0", "c1:p0.d1@1", "c1:p0.d1.k1@1", "c1:p0.d1.k1#v1"} <= ids
    assert GraphEdge("REFERS_TO", "c1:p0.d1.k2@1", "c1:p0.d1.k1@1", {"raw": "khoản 1 Điều này"}) in b1.edges
    assert validate(b1) == []

def test_text_is_masked_amounts_are_not():
    b, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    texts = " ".join(str(n.props.get("text", "")) for n in b.nodes)
    assert "001203004567" not in texts and "[HD_" in texts and "30 triệu đồng" in texts

def test_field_ops_change_build_and_contract_props():
    log = OperationLog("c1")
    log.add(human_op("c1", "SET_FIELD", "sign_date", {"value": "2023-03-15"}, "Tùng", at=T))
    b, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)
    base, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    assert b.build_id != base.build_id
    assert next(n for n in b.nodes if n.node_id == "c1").props["sign_date"] == "2023-03-15"

def test_validate_catches_bad_edges_and_foreign_nodes():
    b, _ = build_graph("c1", PAGES, OperationLog("c1"), file_checksum="x", built_at=T)
    bad = dataclasses.replace(b, edges=b.edges + (GraphEdge("HAS_VALUE", "c1", "c1:p0", {}),))
    assert any("HAS_VALUE" in p for p in validate(bad))
    foreign = dataclasses.replace(b, nodes=b.nodes + (dataclasses.replace(b.nodes[0], node_id="c2", props={**b.nodes[0].props, "contract_id": "c2"}),))
    assert any("c2" in p for p in validate(foreign))
```

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_graph_build.py -v` → FAIL.

- [ ] **Step 3: Implement `build.py`**

Che bằng một `MaskState(prefix="HD_")` mới cho mỗi lần dựng, đi theo thứ tự `doc.units`, che `title` của phần trước. `validate` kiểm: (1) mọi cạnh có `type` trong lược đồ, nhãn hai đầu đúng miền / đích; (2) hai đầu cạnh tồn tại; (3) mọi nút `contract_id == build.contract_id` (nút Contract là `<cid>`, các nút khác bắt đầu bằng `<cid>:`); (4) không thuộc tính `text` / `title` nào còn PII (`mask_text(...)` không trả phát hiện nào); (5) không có hai phiên bản của cùng `uid` có khoảng `[valid_from, valid_to)` chồng nhau. Mỗi vi phạm một chuỗi mô tả có nêu `node_id` / loại cạnh.

- [ ] **Step 4: Run to verify they pass** — 4 passed.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): pure contract graph build with deterministic ids, masking, validation"`

---

### Task 8: Ghi Neo4j + hạ tầng

**Files:**
- Create: `src/rag/contracts/graph/neo4j_store.py`, `docker/neo4j-compose.yml`
- Modify: `pyproject.toml` (extra `graph = ["neo4j>=5.28,<6"]`), `../../.gitignore` (thêm `data/team-*/contracts/`, `data/team-*/contracts_real/`, `data/team-*/neo4j/`), `.env.example` nếu có trong `app/team-4.2/` (thêm các biến của Global Constraints, mật khẩu để trống)
- Test: `tests/test_contracts_neo4j.py`

**Interfaces:**
- Consumes: `GraphBuild` (Task 7).
- Produces:
  - `GraphConfig(uri, user, password, database)` (frozen); `graph_config_from_env(env: Mapping[str, str] = os.environ) -> GraphConfig | None` — `None` khi `CONTRACT_GRAPH != "1"`; bật mà thiếu `NEO4J_PASSWORD` → `ValueError("Thiếu NEO4J_PASSWORD")`.
  - `class GraphUnavailable(RuntimeError)`.
  - `class ContractGraphStore(config)`: `ensure_schema()` (ràng buộc duy nhất `CGNode.node_id`, chỉ mục `CGNode.contract_id`; chạy lại không lỗi); `publish(build: GraphBuild) -> None` — một giao dịch: `MATCH (n:CGNode {contract_id:$cid}) DETACH DELETE n`, tạo nút theo từng nhãn (`UNWIND $rows AS r CREATE (n:CGNode:<Label>) SET n = r.props, n.node_id = r.node_id`), tạo cạnh theo từng loại (`MATCH` hai đầu theo `node_id` trong cùng `contract_id`); `current_build_id(contract_id) -> str | None`; `delete(contract_id)`; `close()`. Lỗi kết nối / xác thực của driver → `GraphUnavailable` với thông điệp tiếng Việt.

- [ ] **Step 1: Write the failing tests**

```python
import os, pytest
from rag.contracts.graph.neo4j_store import graph_config_from_env

def test_env_config():
    assert graph_config_from_env({}) is None
    with pytest.raises(ValueError):
        graph_config_from_env({"CONTRACT_GRAPH": "1"})
    c = graph_config_from_env({"CONTRACT_GRAPH": "1", "NEO4J_PASSWORD": "p"})
    assert (c.uri, c.user, c.database) == ("bolt://localhost:7687", "neo4j", "neo4j")

needs_neo4j = pytest.mark.skipif(not os.environ.get("NEO4J_TEST_URI"), reason="cần NEO4J_TEST_URI")

@needs_neo4j
def test_publish_replaces_and_isolates(neo4j_store, build_for):   # fixtures trong file test
    neo4j_store.publish(build_for("cA", "Điều 1. A\nĐiều 2. B"))
    neo4j_store.publish(build_for("cB", "Điều 1. X"))
    neo4j_store.publish(build_for("cA", "Điều 1. A"))                  # bản mới thay nguyên khối
    rows = neo4j_store.run("MATCH (n:CGNode {contract_id:'cA'}) RETURN n.node_id AS id")
    ids = {r["id"] for r in rows}
    assert "cA:p0.d2@1" not in ids and not any(i.startswith("cB") for i in ids)
    assert neo4j_store.current_build_id("cB") is not None
```

Fixture `neo4j_store` đọc `NEO4J_TEST_URI`, `NEO4J_TEST_PASSWORD`, gọi `ensure_schema()`, xóa `cA`, `cB` sau test; `build_for(cid, text)` gọi `build_graph` với `OperationLog(cid)`. `run(query) -> list[dict]` là phương thức chỉ đọc dùng cho test và chẩn đoán.

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev --extra graph pytest tests/test_contracts_neo4j.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `neo4j_store.py`, compose, pyproject, gitignore**

`docker/neo4j-compose.yml`: một dịch vụ `neo4j`, ảnh `neo4j:5.26.0-community`, cổng 7474 / 7687, `NEO4J_AUTH: ${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:?đặt NEO4J_PASSWORD}`, volume `../../../data/team-4.2/neo4j/data:/data`, không có `NEO4J_PLUGINS`.

- [ ] **Step 4: Run to verify** — không có Neo4j: 1 passed, 1 skipped. Có Neo4j (`docker compose -f docker/neo4j-compose.yml up -d`, rồi `NEO4J_TEST_URI=bolt://localhost:7687 NEO4J_TEST_PASSWORD=… uv run --extra dev --extra graph pytest tests/test_contracts_neo4j.py -v`): 2 passed.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): Neo4j contract graph store (atomic publish per contract) and compose"`

---

### Task 9: Dịch vụ dựng → kiểm → công bố, khóa ghi

**Files:**
- Create: `src/rag/contracts/graph/service.py`
- Test: `tests/test_contracts_graph_service.py`

**Interfaces:**
- Consumes: `build_graph`, `validate` (Task 7); `ContractGraphStore`, `GraphUnavailable` (Task 8).
- Produces:
  - `class GraphBusy(RuntimeError)` — thông điệp `"Đang có thay đổi khác trên hợp đồng này — hãy tải lại"`.
  - `class ContractGraphService(store: ContractGraphStore | None)`:
    - `writing(contract_id)` — context manager; khóa riêng từng hợp đồng (`threading.Lock`, `acquire(blocking=False)`); đang bị giữ → `GraphBusy`.
    - `rebuild(contract_id, pages, oplog, *, file_checksum, now) -> tuple[ContractDoc, dict]` — luôn trả `ContractDoc` (tách vẫn chạy khi đồ thị tắt). `dict` trạng thái: `{"enabled": bool, "build_id": str, "published": bool, "problems": [...], "error": str | None, "record": GraphBuild.record()}`. Có vấn đề khi kiểm → không công bố, `published: False`. `store is None` → `enabled: False`, không công bố. `GraphUnavailable` → `published: False`, `error` = thông điệp.

- [ ] **Step 1: Write the failing tests** — dùng một `FakeStore` ghi lại các bản đã `publish` và có cờ `fail`:
  - `test_disabled_still_parses`: `ContractGraphService(None).rebuild(...)` → doc có đơn vị, `status["enabled"] is False`.
  - `test_publishes_valid_build`: `FakeStore` nhận đúng một bản, `status["published"] is True`, `status["build_id"] == FakeStore.published[0].build_id`.
  - `test_invalid_build_not_published`: `monkeypatch` `build.validate` trả `["x"]` → `FakeStore.published == []`, `status["problems"] == ["x"]`.
  - `test_store_down_is_reported_not_raised`: `FakeStore(fail=True)` ném `GraphUnavailable("Không kết nối được Neo4j")` → không ném, `status["error"] == "Không kết nối được Neo4j"`.
  - `test_second_writer_is_refused`: trong `with svc.writing("c1"):` gọi `svc.writing("c1").__enter__()` → `GraphBusy`; `svc.writing("c2")` vẫn vào được.

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_graph_service.py -v` → FAIL.

- [ ] **Step 3: Implement `service.py`.**

- [ ] **Step 4: Run to verify they pass** — 5 passed.

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): contract graph service (build, validate, publish, per-contract write lock)"`

---

### Task 10: Đưa vào hợp đồng, kho, API, giao diện

**Files:**
- Modify: `src/rag/contracts/models.py`, `src/rag/contracts/store.py`, `src/rag/contracts/review.py`, `ui/contracts_api.py`, `ui/server.py` (gắn `CONFIG.graph`), `ui/contracts.js` (dòng thẻ hợp đồng, quanh dòng 178–185)
- Test: `tests/test_contracts_graph_api.py`; toàn bộ `tests/test_contracts_*.py` hiện có phải vẫn qua

**Interfaces:**
- Consumes: Task 5, 6, 9.
- Produces:
  - `Contract` thêm trường (đều có mặc định): `page_texts: list[PageText]`, `file_checksum: str | None`, `oplog: OperationLog` (mặc định rỗng theo `contract_id`), `doc: ContractDoc | None` (dẫn xuất, **không** lưu), `graph: dict` (trạng thái từ Task 9), `builds: list[dict]` (các `record()`, mới nhất cuối).
  - `contract.json` thêm `page_texts`, `file_checksum`, `operations` (`oplog.to_json()`), `graph`, `builds`, `format: 2`. Nạp bản không có `format` → hợp đồng Phần 4 (`doc=None`, `page_texts=[]`).
  - `contracts_api.CONFIG.graph`: `() -> ContractGraphService` (server: `ContractGraphService(ContractGraphStore(cfg) if cfg else None)` với `cfg = graph_config_from_env()`, tạo một lần, `ensure_schema()` lỗi thì ghi log và dùng `None`).
  - Endpoint mới: `POST /api/contracts/{id}/layout` thân `{"parts": [{"start": int, "kind": "appendix", "title": str}], "by": str}` — `p0` luôn giữ; ghi `SET_LAYOUT` của người thay thế thao tác bố cục đang hiệu lực; trả thẻ. `GraphBusy` → 409.
  - `card(c)` thêm: `"parts": [{"part_id","kind","title"}]`, `"parse_report": {"counts","gaps","warnings"}`, `"graph": {"enabled","published","build_id","error","problems"}`.

Hành vi:
- `create`: sau `load_source`, số trang (DOCX / TXT = 1) > 150 → `ValueError` với thông báo ở Global Constraints. `page_texts` = các trang (`PageText(p.page, p.text, type(p).__name__)`), `file_checksum` = sha256 của bytes file. Thêm `SET_LAYOUT` (`origin="rule"`, `auto_accepted`, content `{"parts": [asdict(p) for p in detect_parts(text)]}`). `extract_facts` như cũ; sau đó thêm `SET_FIELD` `llm` `auto_accepted` cho `type` và `sign_date` (khi có). Gọi `rebuild` trong `writing(cid)`; `units = to_contract_units(doc)`, `total_units = len(units)` (**không** gọi `limit_units`).
- `set_party`, `set_sign_date`: như cũ, thêm `SET_FIELD` của người (`by` từ thân request, mặc định `"người dùng"`) thay thế thao tác đang hiệu lực cùng `target` (nếu có), rồi `rebuild`.
- `get`: hợp đồng Phần 4 có file gốc → nạp lại trang bằng `load_source` (như `create`, không gọi LLM), chuyển `party` / `sign_date` do người nhập (`sign_date_source == "user"`) thành `SET_FIELD` của người `"chuyển đổi"`, gắn `pre_graph: True` cho mọi báo cáo cũ, `rebuild`, lưu nếu `persist`. Hợp đồng `format: 2` → `doc` tính lại từ `page_texts` + `oplog.layout()` khi nạp (không gọi Neo4j).
- `review.review` toàn bộ: `scope = contract.units[:DEMO_MAX_UNITS]`; `coverage = {"reviewed": len(scope), "total": len(contract.units)}`. Mọi báo cáo (`_new_report`) và câu trả lời (`answer`) thêm `"warnings": contract.doc.report.warnings` khi có `doc`.
- `contracts.js` thẻ hợp đồng: thêm số phụ lục (khi > 0) và mỗi cảnh báo đọc một dòng màu hổ phách; khi `graph.enabled && !graph.published` thêm dòng "Đồ thị chưa cập nhật: <error hoặc problems[0]>".

- [ ] **Step 1: Write the failing tests** (theo kiểu `tests/test_contracts_api.py` hiện có: fixture đặt `CONFIG.root` vào `tmp_path`, `llm_factory` giả, `CONFIG.graph` = dịch vụ với `FakeStore` của Task 9)
  - `test_create_long_contract_not_cut`: hợp đồng 60 Điều → thẻ có 60 đơn vị, `coverage == {"reviewed": 60, "total": 60}`, `graph.published is True`.
  - `test_over_150_pages_rejected`: `load_source` giả trả 151 trang → lỗi với đúng thông báo, không có hợp đồng nào được lưu.
  - `test_full_review_caps_llm_scope_honestly`: hợp đồng 40 Điều, `run review` → báo cáo `coverage == {"reviewed": 30, "total": 40}`.
  - `test_sign_date_by_user_is_superseding_op`: `set_sign_date` → `oplog.field("sign_date")` là giá trị người nhập; thao tác `llm` trước đó `rejected`; `builds` có 2 bản ghi.
  - `test_layout_endpoint_reparses`: hợp đồng có "Điều 1…Điều 4", gửi bố cục tách phụ lục từ vị trí của "Điều 3" → thẻ có `parts` 2 phần, nhãn đơn vị thứ ba bắt đầu `"Phụ lục 1 — "`.
  - `test_busy_returns_409`: giữ `writing(cid)` rồi gọi endpoint bố cục → 409.
  - `test_graph_down_contract_still_created`: `FakeStore(fail=True)` → tạo thành công, `card["graph"]["error"]` có nội dung.
  - `test_part4_contract_json_still_opens`: ghi tay một `contract.json` định dạng Phần 4 (uid `u1`, một báo cáo, `sign_date_source: "user"`) + `original.txt` → `get` thành công, uid bắt đầu `p0.`, báo cáo có `pre_graph: True`, `oplog.field("sign_date")` đúng ngày cũ; `report_docx` cho báo cáo cũ vẫn chạy.
  - `test_saved_contract_roundtrip_keeps_ops`: lưu, tạo `ContractStore` mới, nạp → `oplog.all()` bằng nhau, `doc` dựng lại có cùng danh sách uid.

- [ ] **Step 2: Run to verify they fail** — `uv run --extra dev pytest tests/test_contracts_graph_api.py -v` → FAIL.

- [ ] **Step 3: Implement theo phần "Hành vi" ở trên.**

- [ ] **Step 4: Run the whole contract suite** — `uv run --extra dev pytest tests/ -k contracts -q` → tất cả qua (gồm các test Phần 4 hiện có).

- [ ] **Step 5: Commit** — `git commit -m "feat(team-4.2): contracts use the new parser, operation log and graph build; layout endpoint"`

---

### Task 11: Chạy thật và kiểm bằng mắt

**Files:**
- Create: `docs/superpowers/notes/2026-11-12-contract-graph-structure-check.md` (ghi kết quả)

- [ ] **Step 1: Chạy toàn bộ kiểm thử** — `uv run --extra dev pytest tests -q` → không có lỗi mới so với trước kế hoạch (ghi số passed / skipped).
- [ ] **Step 2: Bật Neo4j và ứng dụng** — `docker compose -f docker/neo4j-compose.yml up -d`; đặt `CONTRACT_GRAPH=1`, `NEO4J_PASSWORD`; chạy server như README; chạy lại `tests/test_contracts_neo4j.py` với `NEO4J_TEST_URI` → 2 passed.
- [ ] **Step 3: Nạp hợp đồng demo** (`data/team-4.2/contracts_demo/hop_dong_thue_nha_2023.docx`) qua giao diện → thẻ có 12 Điều, không cảnh báo đứt số; trong Neo4j Browser (`http://localhost:7474`): `MATCH (n:CGNode {contract_id:$id}) RETURN count(n)` > 12, không có chuỗi CCCD / số điện thoại gốc trong `text`.
- [ ] **Step 4: Nạp một hợp đồng tự soạn ≥ 40 Điều có 2 phụ lục và dẫn chiếu chéo** → thẻ báo đủ số Điều và 2 phụ lục; soát toàn bộ báo `30/40+`; sửa ngày ký → `build_id` đổi; tắt Neo4j rồi sửa ngày ký → thẻ báo "Đồ thị chưa cập nhật", hợp đồng vẫn hỏi được.
- [ ] **Step 5: Ghi kết quả, ảnh chụp đồ thị (nếu có) vào file ghi chú, commit** — `git commit -m "docs(team-4.2): contract graph structure layer - manual check"`
