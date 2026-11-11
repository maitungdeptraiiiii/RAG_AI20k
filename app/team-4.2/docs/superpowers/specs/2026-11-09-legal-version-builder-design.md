# Thiết kế: Kho luật có phiên bản (Legal Version Builder) — Phần 1/4

Ngày: 09/11/2026 · Trạng thái: bản nháp chờ duyệt (đã cập nhật theo trả lời của người dùng)

**Quyết định của người dùng:** tự xác minh thao tác parse chính xác kể cả khi không có VBHN; crawler tự tìm
và tự thêm văn bản liên quan; phạm vi đầu là bất động sản. **Quyết định của người viết** (người dùng xem
lại): package mới `rag.legal` thay vì mở rộng `rag/versioning`; phụ lục/bảng không tự áp dụng; thay cụm từ
chỉ tự áp dụng khi nêu rõ đơn vị và xuất hiện đúng một lần; chunk theo Điều × khoảng hiệu lực; `/review`
chưa có đăng nhập; sửa một thao tác thì dựng lại cả luật.

Dự án gồm bốn phần, làm theo thứ tự: **(1) Kho luật có phiên bản** (tài liệu này) → (2) Hỏi đáp theo mốc
thời gian → (3) Trang `/upload` cho văn bản pháp luật → (4) Đính kèm hợp đồng trong chat. Phần 2–4 có
tài liệu thiết kế riêng; ở đây chỉ nêu những gì phần 1 phải bàn giao cho chúng.

## 1. Ý định và lý do

App dùng để **đánh giá vấn đề pháp lý của hợp đồng** tại Việt Nam. Một hợp đồng ký 15/06/2023 phải được
đối chiếu với luật **có hiệu lực ngày 15/06/2023**; một nghĩa vụ thực hiện năm 2025 đối chiếu với luật năm
2025; không mặc định "luật hôm nay". Hiện tại kho luật chỉ là tập file độc lập: luật gốc và luật sửa đổi
nằm cạnh nhau, không liên kết, nên app có thể trích nguyên văn một điều đã bị sửa mà trông vẫn chính xác.

Phần 1 xây kho luật trả lời được câu hỏi: **"Tại ngày X, Điều/Khoản/Điểm này của luật Y có nội dung gì, và
mức độ tin cậy của nội dung đó là gì?"** — do backend quyết định, không để LLM tự chọn phiên bản.

Nguyên tắc chủ đạo (của người dùng): *thà không đưa ra một điều luật có phiên bản chưa xác minh, còn hơn
đưa ra một phiên bản sai nhưng trông có vẻ chính xác.*

## 2. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu**
- Crawl từ vbpl.vn: văn bản gốc, các văn bản sửa đổi tác động lên nó, và VBHN nếu có.
- Phân tích văn bản sửa đổi thành các **thao tác sửa đổi** có cấu trúc, mỗi thao tác có ngày hiệu lực riêng.
- Dựng lịch sử từng **điều khoản** (Điều / Khoản / Điểm, tên điều, đoạn mở đầu) thành các
  **phiên bản** với khoảng hiệu lực `[valid_from, valid_to)` và trạng thái xác minh.
- Xử lý **thay thế cả luật** (Luật Nhà ở 2023 thay Luật Nhà ở 2014) và **sửa đổi ngày hiệu lực** của luật
  khác (Luật 43/2024/QH15), không chỉ sửa từng điều.
- Ngày hiệu lực của từng điều khoản **tự tính từ chính văn bản** (Điều hiệu lực thi hành, kể cả sau khi bị
  sửa), không tin `effFrom` của vbpl.
- Crawler **tự tìm và tự thêm** văn bản sửa đổi, văn bản thay thế và VBHN của các luật trong kho.
- Đối chiếu với VBHN khi có.
- Hàng đợi duyệt cho các trường hợp bị gắn cờ, có trang duyệt tối thiểu.
- Sửa một thao tác sai → dựng lại các phiên bản phụ thuộc, giữ nguyên nhật ký.
- API truy vấn `as_of(ngày)` cho phần 2.

**Không làm trong phần 1**
- Lọc retrieval theo mốc thời gian, chặn/cảnh báo trong câu trả lời, trích dẫn kèm khoảng hiệu lực (phần 2).
- Form upload văn bản pháp luật (phần 3), đính kèm hợp đồng (phần 4).
- Áp dụng tự động điều khoản chuyển tiếp hoặc hiệu lực hồi tố — chỉ lưu lại làm bằng chứng.
- Sửa đổi phụ lục, biểu thuế, bảng (ví dụ "Biểu thuế tiêu thụ đặc biệt", "Phụ lục IV số thứ tự 132a"):
  ghi nhận thao tác loại `UNSUPPORTED`, gắn cờ điều chứa nó, không tự áp dụng.
- Dùng LLM trong đường dựng phiên bản.

**Phản mục tiêu** (xảy ra là thất bại dù code chạy)
- Một phiên bản dựng sai được đánh dấu `verified`.
- Một thao tác hàng loạt (thay cụm từ "tại một số điều") chỉ được áp dụng ở những chỗ parser tìm thấy
  rồi coi là xong.
- Sửa đè nội dung một phiên bản đã dựng mà không để lại dấu vết.
- Lấy ngày hiệu lực chung của văn bản sửa đổi gán cho thao tác thuộc nhóm có ngày hiệu lực riêng.
- Mất liên kết từ một phiên bản về câu chữ gốc trong văn bản nguồn.

## 3. Dữ liệu thật đã khảo sát (09/11/2026)

- API công khai `vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc` (đã dùng trong `src/rag/ingest/vbpl.py`)
  trả: số hiệu, tiêu đề, loại văn bản, cơ quan, ngày ban hành, `effFrom`, `effTo`, tình trạng hiệu lực
  ("Hết hiệu lực một phần"…), cờ `isConsolidatedDocument`, nội dung HTML.
- API này **không trả lược đồ quan hệ** (sửa đổi, thay thế, hợp nhất…). Không dùng API nội bộ của trang.
- Bảng mã quan hệ của vbpl (dùng cùng tên gọi): `SUA_DOI_BO_SUNG`, `SUA_DOI`, `BO_SUNG`, `THAY_THE`,
  `BAI_BO`, `HOP_NHAT`, `DINH_CHINH`, `TAM_NGUNG_HIEU_LUC`, `DINH_CHI_THI_HANH`, `GIA_HAN_HIEU_LUC`.
- Luật 03/2022/QH15 (hiệu lực 01/03/2022) sửa **9 luật** trong một văn bản; mỗi luật đích là một Điều
  ("Điều 7. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp"), gọi luật đích **bằng tên, không bằng số
  hiệu**. Chỉ dẫn lồng tới ba cấp (`Điều 7` → `3.` → `a)`). Có Điều 10 hiệu lực và Điều 11 chuyển tiếp.
  Bản thân 03/2022/QH15 về sau bị 09/2022, 22/2023, 76/2025, 106/2025 tác động.
- Các dạng chỉ dẫn quan sát được: sửa đổi khoản/điểm; sửa nhiều điểm trong một khoản; **sửa tên điều**;
  **sửa đoạn mở đầu khoản**; bãi bỏ điểm; bổ sung khoản `5a` / điểm `g1` "vào sau" một đơn vị; bổ sung
  Điều `33a`; thay toàn bộ Điều; sửa phụ lục / biểu thuế.
- Văn bản gốc (59/2020/QH14, 218 Điều) có cấu trúc dòng rõ: `Chương`, `Mục`, `Điều N. Tên`, `1.`, `a)`.
- Luật 43/2024/QH15 sửa đồng thời Luật Đất đai 31/2024/QH15, Luật Nhà ở 27/2023/QH15, Luật Kinh doanh bất
  động sản 29/2023/QH15 và Luật Các tổ chức tín dụng 32/2024/QH15 (vbpl ghi hiệu lực 01/08/2024). Trong khi
  đó vbpl vẫn ghi `effFrom` của Luật Đất đai 31/2024/QH15 là 01/01/2025 → **`effFrom` của vbpl không phản
  ánh sửa đổi về hiệu lực**; ngày hiệu lực phải tính từ văn bản. (Nội dung chính xác của 43/2024 kiểm chứng
  khi crawl.)
- Luật Nhà ở 65/2014/QH13 và Luật Kinh doanh bất động sản 66/2014/QH13 có tình trạng "Hết hiệu lực toàn bộ"
  — bị luật 2023 thay thế. Hợp đồng ký trước khi luật mới có hiệu lực phải đối chiếu với luật cũ.
- **Số hiệu không duy nhất giữa các loại văn bản**: tìm `91/2015/QH13` (Bộ luật Dân sự) và `45/2013/QH13`
  (Luật Đất đai 2013) đều ra Nghị quyết cùng số trước. Tra cứu phải lọc theo loại văn bản.
- API danh sách nhận `keyword` (tìm gần đúng trong tiêu đề/số hiệu) và lọc theo loại văn bản, tình trạng
  hiệu lực — đủ để tìm ứng viên theo tên luật.
- VBHN không có đủ cho mọi luật và mọi giai đoạn; VBHN là bản hợp nhất tại một thời điểm, không phải ảnh
  chụp đúng cho mọi ngày trong quá khứ. **Chỉ dùng để đối chiếu**, không làm nguồn dựng.

## 4. Mô hình dữ liệu

Lưu trong một SQLite riêng (`DATA_DIR/legal/catalog.sqlite`). Định danh ổn định, không phụ thuộc hash nội
dung.

**LegalDocument** — một văn bản trên vbpl (gốc, sửa đổi, VBHN).
`document_key` (= loại văn bản + số hiệu chuẩn hoá, ví dụ `luat:59/2020/QH14`, vì số hiệu trùng giữa Luật
và Nghị quyết; VBHN dùng số hiệu VBHN), `vbpl_id`, `title`,
`doc_type`, `issuer`, `issued_on`, `effective_from`, `effective_to` (từ vbpl, chỉ mang tính tham khảo),
`eff_status`, `is_consolidated`, `raw_text_path`, `raw_checksum`, `fetched_at`.

**DocumentRelation** — quan hệ văn bản ↔ văn bản. `source_key`, `target_key`, `relation`
(theo bảng mã vbpl), `evidence` (vị trí câu chữ trong văn bản nguồn), `status` (`detected` / `confirmed`
/ `rejected`). Quan hệ nhiều chiều: một văn bản sửa nhiều luật; văn bản sửa đổi cũng có thể bị sửa đổi.

**Provision** — một đơn vị địa chỉ hoá được trong một văn bản. `provision_id` dạng
`luat:59/2020/QH14#d60.k2.e` (Điều 60, khoản 2, điểm e). Các loại: `article`, `article_title`, `clause`,
`clause_lead_in` (đoạn trước các điểm), `point`. Lưu cha–con và thứ tự. Chương/Mục là heading, không phải
provision có phiên bản; giữ lại để hiển thị đường dẫn.

**AmendmentOperation** — một thao tác sửa đổi; **nguồn sự thật** của lịch sử. Bất biến: sửa một thao tác
= tạo bản ghi mới thay thế bản cũ (`supersedes_operation_id`), bản cũ chuyển `review_status=rejected`.

| Trường | Ý nghĩa |
|---|---|
| `operation_id` | định danh |
| `source_document_key`, `source_locator` | văn bản sửa đổi và vị trí chỉ dẫn (ví dụ `Điều 7 > 3 > a`) |
| `source_excerpt_span` | offset của chỉ dẫn và nội dung mới trong text nguồn |
| `target_document_key` | luật đích (đã phân giải từ tên) |
| `target_provision_id` | đơn vị đích; với `INSERT_*` là vị trí neo (`vào sau ...`) |
| `operation_type` | xem bảng dưới |
| `old_text` | nội dung đích ngay trước khi áp dụng (điền lúc dựng) |
| `new_text` | nội dung mới trích từ phần trong ngoặc kép |
| `effective_from` | ngày hiệu lực của **riêng thao tác** (null nếu chưa xác định) |
| `parse_status` | `exact` / `partial` / `unsupported` / `failed` |
| `review_status` | `auto_accepted` / `pending` / `approved` / `rejected` |
| `reviewer`, `reviewed_at`, `review_note` | ai duyệt, khi nào, lý do |
| `supersedes_operation_id` | thao tác cũ mà bản này sửa lại |

Loại thao tác: `REPLACE_ARTICLE`, `REPLACE_ARTICLE_TITLE`, `REPLACE_CLAUSE`, `REPLACE_CLAUSE_LEAD_IN`,
`REPLACE_POINT`, `INSERT_ARTICLE`, `INSERT_CLAUSE`, `INSERT_POINT`, `DELETE_ARTICLE`, `DELETE_CLAUSE`,
`DELETE_POINT`, `REPLACE_TEXT` (thay cụm từ trong một đơn vị đã nêu rõ), `AMEND_TEXT` (sửa một phần câu
chữ), `REPEAL_DOCUMENT` (văn bản đích hết hiệu lực toàn bộ — do bị thay thế hoặc bãi bỏ),
`UNSUPPORTED` (phụ lục, bảng, thao tác chưa hỗ trợ).

Sửa đổi **Điều hiệu lực thi hành** của luật đích (như 43/2024 với Luật Đất đai) là một `REPLACE_*` bình
thường trên Điều đó; điểm khác là sau khi áp dụng, builder phải tính lại ngày hiệu lực ban đầu của luật đích
(mục 5.4).

**ProvisionVersion** — **dữ liệu dẫn xuất**, sinh lại được hoàn toàn từ văn bản gốc + các thao tác.
`provision_id`, `content`, `valid_from`, `valid_to` (loại trừ; `null` = chưa kết thúc),
`verification_status` (`verified` / `needs_review` / `conflicted`), `status_reasons`,
`source_operations` (danh sách `operation_id`), `build_id`.

Khoảng hiệu lực là nửa mở `[valid_from, valid_to)`: văn bản cũ hết hiệu lực 30/06, văn bản mới hiệu lực
01/07 → phiên bản cũ có `valid_to = 01/07`.

Phiên bản đầu tiên của mỗi provision lấy từ văn bản gốc với `valid_from` = ngày hiệu lực **của provision
đó** theo Điều hiệu lực của chính văn bản gốc (luật có thể có nhóm điều hiệu lực sớm/muộn hơn), không lấy
`effFrom` của vbpl.

**BuildRun** — mỗi lần dựng một luật: `build_id`, `document_key`, danh sách `operation_id` + checksum được
dùng, thời điểm, phiên bản code. Các bản dựng cũ được giữ; bản dựng mới nhất thành công là bản đang dùng.

**ReviewItem** — một mục cần người duyệt, trỏ tới thao tác và/hoặc provision; có lịch sử quyết định.

## 5. Luồng xử lý

```
Danh sách luật gốc (seed)
  → Crawler + discovery: tải luật gốc, tự tìm và thêm văn bản sửa đổi, văn bản thay thế, VBHN (API công khai)
  → Structure parser: text → cây Provision (cho mọi văn bản, kể cả văn bản sửa đổi)
  → Relation detector: văn bản sửa đổi tác động lên luật nào (theo tiêu đề + tiêu đề Điều)
  → Directive parser: Điều/khoản/điểm của văn bản sửa đổi → AmendmentOperation
  → Effective-date resolver: ngày hiệu lực cho từng thao tác
  → Target matcher: định vị đơn vị đích trong cây Provision của luật đích
  → Version builder: áp dụng thao tác theo thời gian → ProvisionVersion
  → VBHN checker: đối chiếu nếu có VBHN
  → Gắn trạng thái xác minh; đẩy các mục cần duyệt vào hàng đợi
```

### 5.1 Seed và tự tìm văn bản liên quan (quyết định của người dùng: tự tìm, tự thêm)

Người dùng chỉ khai **danh sách luật gốc** (`data/team-4.2/legal/seeds.yaml`: loại văn bản + số hiệu).
Crawler tự tìm và tự thêm văn bản liên quan. Vì API công khai không có lược đồ, quan hệ được **tìm bằng
tiêu đề rồi xác nhận bằng nội dung**:

1. **Tìm ứng viên** bằng API danh sách với `keyword` = tên luật (ví dụ "Luật Đất đai") và số hiệu, lọc loại
   văn bản Luật/Bộ luật/Nghị quyết của Quốc hội, ban hành sau văn bản gốc.
2. **Phân loại theo tiêu đề:** "sửa đổi, bổ sung ... <tên luật> [số hiệu]" → ứng viên sửa đổi;
   cùng tên luật, số hiệu mới hơn → ứng viên thay thế; `isConsolidatedDocument` + cùng tên → ứng viên VBHN.
3. **Xác nhận bằng nội dung** (bắt buộc trước khi thêm):
   - Sửa đổi: văn bản có ít nhất một Điều/chỉ dẫn gọi đúng luật đích (tên + số hiệu nếu có).
   - Thay thế: Điều hiệu lực của luật mới có câu "<luật đích, số hiệu> hết hiệu lực kể từ ...".
   - VBHN: phần đầu VBHN nêu luật đích và các văn bản sửa đổi được hợp nhất.
   Ứng viên không xác nhận được → ghi vào nhật ký discovery, không thêm.
4. **Lan rộng có giới hạn:** văn bản đã thêm cũng được tìm sửa đổi của chính nó (văn bản sửa đổi bị sửa
   đổi), tối đa độ sâu 2 tính từ seed. Văn bản thay thế được thêm như một luật gốc mới (độ sâu 0).
5. Mỗi văn bản tự thêm ghi `discovered_via` (seed nào, truy vấn nào, bằng chứng câu chữ nào) để kiểm tra.

Rủi ro của tự thêm: sót văn bản có tiêu đề không theo mẫu, hoặc thêm nhầm. Giảm bằng bước 3; báo cáo
`report` liệt kê văn bản đã thêm, ứng viên bị loại, và luật có tình trạng vbpl "Hết hiệu lực một phần"
nhưng chưa tìm thấy văn bản sửa đổi nào (dấu hiệu sót).

**Seed khởi đầu — bất động sản** (quyết định của người dùng: phạm vi nhỏ, liên quan bất động sản):
Luật Đất đai 31/2024/QH15, Luật Nhà ở 27/2023/QH15, Luật Kinh doanh bất động sản 29/2023/QH15, Bộ luật Dân
sự 91/2015/QH13. Qua discovery sẽ kéo theo: 43/2024/QH15 (sửa cả ba luật BĐS), Luật Nhà ở 65/2014/QH13 và
Luật Kinh doanh bất động sản 66/2014/QH13 (bị thay thế), Luật Đất đai 45/2013/QH13 (bị thay thế), các luật
sửa đổi về sau và VBHN nếu có. 6 Bộ luật hiện có trong kho cũ chưa chuyển sang (để sau).

Bộ kiểm thử cố định thêm: Luật Doanh nghiệp 59/2020/QH14 + 03/2022/QH15 (đã khảo sát kỹ ở mục 3).

### 5.2 Phân giải luật đích

Văn bản sửa đổi gọi luật đích bằng tên. Phân giải tên → `document_key` bằng cách khớp với các luật **trong
danh mục** có cùng tên và **đang có hiệu lực vào ngày ban hành văn bản sửa đổi**. Không khớp đúng một văn
bản → quan hệ `detected` nhưng các thao tác bị `pending` và vào hàng đợi.

### 5.3 Phân tích chỉ dẫn

Parser theo luật (regex + máy trạng thái), không LLM. Nhận diện: hành động (sửa đổi, bổ sung, bãi bỏ, thay,
sửa đổi tên, sửa đổi đoạn mở đầu), địa chỉ đích (điểm/khoản/Điều, kể cả "điểm b và điểm c khoản 4",
"khoản 2 và bổ sung khoản 2a vào sau khoản 2"), và nội dung mới trong ngoặc kép. Một chỉ dẫn gộp nhiều
đích được tách thành nhiều thao tác.

`parse_status`:
- `exact`: hành động, địa chỉ đích và nội dung mới đều xác định duy nhất.
- `partial`: nhận ra là chỉ dẫn sửa đổi nhưng thiếu một phần (đích mơ hồ, "tại một số điều", không tách
  được nội dung mới).
- `unsupported`: phụ lục, biểu, bảng, hoặc dạng chưa hỗ trợ.
- `failed`: câu có dấu hiệu sửa đổi nhưng không phân tích được.

`REPLACE_TEXT` / `AMEND_TEXT` chỉ được tự áp dụng khi chỉ dẫn **nêu rõ đơn vị đích** và cụm từ cũ xuất hiện
**đúng một lần** trong đơn vị đó. "Thay cụm từ X bằng Y tại một số điều" hoặc "trong toàn bộ Luật" →
`partial`; mọi provision chứa X được gắn `needs_review`; không áp dụng ở bất kỳ đâu.

### 5.4 Ngày hiệu lực của từng thao tác

Áp dụng cho **mọi văn bản**, cả luật gốc lẫn văn bản sửa đổi: ngày hiệu lực lấy từ Điều hiệu lực thi
hành của chính văn bản **tại phiên bản đang xét** (nếu Điều hiệu lực của luật gốc bị sửa — như 43/2024 —
thì tính lại từ nội dung sau sửa và dựng lại toàn bộ luật đó). `effFrom` của vbpl chỉ dùng để đối chiếu:
lệch → ghi lý do và `needs_review`.

Đọc Điều hiệu lực của văn bản sửa đổi. Một ngày chung, không ngoại lệ → gán cho mọi thao tác. Có ngoại lệ
theo nhóm điều/khoản ("riêng khoản 3 Điều 7 có hiệu lực từ...") → gán theo nhóm. Ngày tương đối, có điều
kiện, nhiều mốc không giải được, hoặc lệch với `effFrom` của vbpl → `effective_from = null`, thao tác
`pending`. Tái dùng heuristic của `src/rag/versioning/effectivity_guard.py` để phát hiện các dấu hiệu này.

### 5.5 Dựng phiên bản

Với mỗi luật đích: lấy cây Provision từ văn bản gốc, sắp các thao tác **được phép áp dụng** theo
`effective_from` (cùng ngày: theo thứ tự văn bản ban hành, rồi thứ tự trong văn bản), áp dụng tuần tự.
Mỗi lần một provision đổi nội dung → đóng phiên bản cũ (`valid_to = effective_from`) và mở phiên bản mới.
`DELETE_*` đóng phiên bản mà không mở phiên bản mới. `INSERT_*` tạo provision mới.

Thao tác được phép áp dụng: `review_status ∈ {auto_accepted, approved}` và có `effective_from`.

`auto_accepted` (quyết định của người dùng: chấp nhận tự xác minh, kể cả khi luật không có VBHN để đối
chiếu) được gán khi: `parse_status = exact`, có `effective_from`, luật đích phân giải được, đơn vị
đích tồn tại (hoặc vị trí neo tồn tại với `INSERT_*`), và với `REPLACE_*` thì đơn vị mới khớp cấu trúc
(ví dụ thay khoản thì nội dung mới bắt đầu bằng đúng số khoản).

Thao tác không được áp dụng (`pending`, `partial`, `unsupported`, `failed`): phiên bản trước **được giữ
nguyên** nhưng từ ngày dự kiến (hoặc từ ngày hiệu lực chung của văn bản sửa đổi nếu thao tác chưa có ngày)
được tách thành phiên bản mới cùng nội dung, trạng thái `needs_review`, lý do ghi rõ thao tác nào đang chờ.

**Văn bản sửa đổi bị sửa đổi** (B sửa A, A sửa X): A được dựng phiên bản như mọi văn bản. Nếu thao tác của
B tác động lên một Điều của A **chứa chỉ dẫn sửa đổi** X (không phải Điều hiệu lực/chuyển tiếp), các thao
tác của A sinh từ Điều đó bị chuyển `pending` và các provision của X liên quan gắn `needs_review`. Không tự
suy diễn lại hiệu lực dây chuyền.

**Thay thế / hết hiệu lực toàn bộ** (`REPEAL_DOCUMENT`): sinh từ câu "<luật X, số hiệu> hết hiệu lực kể từ
ngày Luật này có hiệu lực" trong Điều hiệu lực của luật mới. Mọi provision của X có `valid_to` = ngày hiệu
lực của luật mới. Luật cũ vẫn ở trong kho để trả lời theo mốc quá khứ. Câu có ngoại lệ ("trừ trường hợp
quy định tại...", điều khoản chuyển tiếp giữ luật cũ cho một số hồ sơ) → ghi chú chuyển tiếp lên các phiên
bản cuối của X, không tự kéo dài hiệu lực. `effTo`/"Hết hiệu lực toàn bộ" của vbpl chỉ dùng đối chiếu.

### 5.6 Trạng thái xác minh

| Trạng thái | Khi nào | Phần 2 dùng thế nào |
|---|---|---|
| `verified` | mọi thao tác tạo nên nội dung đều `auto_accepted`/`approved`, không có thao tác chờ chạm vào provision trong khoảng này, không lệch VBHN | dùng để kết luận |
| `needs_review` | có thao tác `pending`/`partial`/`unsupported`/`failed` chạm vào provision (hoặc cha của nó) trong khoảng này | chỉ tham khảo, phải cảnh báo |
| `conflicted` | lệch VBHN, hoặc hai thao tác cùng hiệu lực mâu thuẫn trên một provision | không dùng để kết luận |

Trạng thái lan từ cha xuống con: thao tác chờ trên Điều 5 làm mọi khoản/điểm của Điều 5 `needs_review`.
Thao tác chờ trên một điểm không làm điểm khác cùng khoản bị gắn cờ.

### 5.7 Đối chiếu VBHN

Khi có VBHN của luật đích: xác định thời điểm hợp nhất từ phần đầu VBHN (văn bản sửa đổi cuối cùng được
hợp nhất và ngày hiệu lực của nó). Dựng `as_of` tại thời điểm đó, so từng Điều sau chuẩn hoá (NFC, khoảng
trắng, dấu ngoặc kép, bỏ chú thích hợp nhất kiểu `[1]`). Lệch → các phiên bản của Điều đó từ các thao tác
liên quan trở đi thành `conflicted`, tạo ReviewItem kèm diff. Không xác định được thời điểm hợp nhất → không
đối chiếu, ghi chú lại.

### 5.8 Sửa sai và dựng lại

Người duyệt có thể: `approve` một thao tác, `reject` nó, hoặc `correct` (tạo thao tác mới thay thế với
trường đã sửa). Mỗi quyết định → dựng lại luật đích (toàn bộ luật, vì một luật vài trăm Điều dựng rất
nhanh) → BuildRun mới. Bản dựng cũ giữ lại để truy vết "trước đây hệ thống đã trả lời dựa trên phiên bản
nào". Không sửa trực tiếp ProvisionVersion.

## 6. Giao diện bàn giao cho các phần sau

```python
catalog.provisions_as_of(document_key, day) -> list[ProvisionVersion]
catalog.provision_history(provision_id) -> list[ProvisionVersion]
catalog.laws() -> list[LegalDocument]
catalog.export_chunks(build_id | "latest") -> list[VersionedChunk]
```

`VersionedChunk` (cho phần 2 index): một chunk = một Điều tại một khoảng hiệu lực trong đó toàn bộ Điều
không đổi nội dung và trạng thái. Metadata: `document_key`, `provision_id` của Điều, `valid_from`,
`valid_to`, `verification_status`, `status_reasons`, `source_operations`, `build_id`. Chunk Điều dài vẫn
được tách theo `max_syllables` như chunker hiện tại, các mảnh chung metadata. Phần 2 sẽ quyết định cách
nạp vào BM25/Qdrant và lọc theo ngày.

## 7. Giao diện duyệt (tối thiểu)

Trang `/review` trong app Starlette hiện có:
- Danh sách ReviewItem đang mở, lọc theo luật, loại lý do.
- Mỗi mục: câu chữ chỉ dẫn trong văn bản nguồn, phân tích của parser (bảng các trường thao tác), nội dung
  đích trước/sau dự kiến, diff với VBHN nếu có.
- Hành động: approve / reject / correct (sửa các trường của thao tác trong form) kèm ghi chú bắt buộc.
- Ô "người duyệt" là text tự nhập (app chưa có đăng nhập).

## 8. Công cụ dòng lệnh

```
python -m rag.legal crawl     # tải theo corpus.yaml, cập nhật LegalDocument
python -m rag.legal build     # parse + dựng mọi luật trong danh mục, in thống kê trạng thái
python -m rag.legal show luat:27/2023/QH15 --as-of 2023-06-15 --provision d60.k3
python -m rag.legal report    # số thao tác theo parse/review status, số provision theo trạng thái
```

## 9. Ràng buộc

- Python, cùng codebase `app/team-4.2/src/rag`. Package mới `rag.legal`. SQLite, không thêm dịch vụ ngoài.
- Chỉ dùng API công khai của vbpl đã dùng trong repo; có giới hạn tốc độ và cache file thô.
- Dữ liệu dưới `DATA_DIR/legal/`, không ghi đè snapshot 6 Bộ luật hiện có.
- Code `src/rag/versioning/` hiện có (catalog theo Điều, chốt chặn, review queue) được tham khảo và tái dùng
  heuristic; không bắt buộc dùng nguyên schema của nó vì mô hình cũ không có cấp khoản/điểm và không có
  thao tác sửa đổi.

## 10. Kiểm thử

- **Bộ thật:** 59/2020/QH14 + Điều 7 của 03/2022/QH15. Kỳ vọng viết tay cho từng thao tác (7 chỉ dẫn,
  tách thành các thao tác: tên Điều 49 + đoạn mở đầu khoản 1 Điều 49, tên Điều 50, điểm e khoản 2 và khoản 3
  Điều 60, điểm d khoản 1 Điều 109, khoản 1 và 2 Điều 148, khoản 2 Điều 158, khoản 5 Điều 217) và cho nội
  dung Điều 60 khoản 3 ngày 28/02/2022 vs 01/03/2022.
- **Bộ bất động sản (thật):** discovery từ seed tìm ra 43/2024/QH15 và các luật bị thay thế; ngày hiệu lực
  của Luật Đất đai 31/2024/QH15 sau khi áp dụng 43/2024 khác `effFrom` của vbpl; hỏi Luật Nhà ở tại
  15/06/2023 ra Luật 65/2014/QH13, tại 15/06/2025 ra Luật 27/2023/QH15. Kỳ vọng cụ thể viết sau khi crawl và
  đọc văn bản (bước đầu của kế hoạch).
- **Bộ giả lập** cho từng loại thao tác, ngày hiệu lực theo nhóm, ngày tương đối, thay cụm từ hàng loạt,
  văn bản sửa đổi bị sửa đổi, lệch VBHN, sửa sai + dựng lại.
- Thuộc tính bất biến: dựng hai lần cùng đầu vào ra kết quả giống hệt; mọi ProvisionVersion truy về được
  văn bản nguồn; không khoảng hiệu lực nào chồng nhau trong cùng một provision.

## 11. Để lại cho người xây dựng

- Thiết kế bảng SQLite cụ thể, chỉ mục, cách tuần tự hoá.
- Chi tiết regex/máy trạng thái của parser, miễn đạt các kỳ vọng ở mục 10.
- Bố cục trang `/review`.
- Cách chuẩn hoá văn bản khi so VBHN.
