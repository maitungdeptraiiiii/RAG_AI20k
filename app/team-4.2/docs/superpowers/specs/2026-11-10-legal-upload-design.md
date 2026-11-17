# Thiết kế: Upload văn bản pháp luật vào kho có phiên bản — Phần 3/4

Ngày: 10/11/2026 · Trạng thái: bản 2 (sau review của người dùng) · Phụ thuộc: Phần 1 (`rag.legal`, spec
`2026-11-09-legal-version-builder-design.md`), Phần 2 (`rag.temporal`, spec `2026-11-09-temporal-legal-qa-design.md`),
trang `/upload` hiện có (`ui/upload.html`, `rag.ingest.page_report`).

## 1. Ý định và lý do

Kho luật có phiên bản (phần 1) hiện chỉ nhận văn bản qua crawler dòng lệnh (`python -m rag.legal crawl`). Trang
`/upload` thì đưa văn bản vào kho cũ (chunk + embed), không qua `rag.legal`: một luật sửa đổi upload lên không tạo
phiên bản mới, hỏi đáp theo mốc thời gian (phần 2) không thấy nó.

Phần 3 cho người dùng tự thêm một văn bản pháp luật lấy từ trang văn bản pháp luật (vbpl) vào kho có phiên bản,
**kiểm tra trước khi đưa vào**: (1) text có đúng bản gốc không (OCR), (2) hệ thống có hiểu đúng văn bản không — loại
văn bản, số hiệu, ngày hiệu lực, sửa luật nào, sửa những điều nào. Kho luật dùng để đánh giá hợp đồng; một văn bản
vào kho với text sai hoặc bị hiểu sai sẽ tạo phiên bản luật sai, nên bước kiểm tra là trọng tâm, không phải phụ.

**Yêu cầu tin cậy cao nhất** (người dùng): chat **không bao giờ** trả lời dựa trên một kho luật nửa cũ nửa mới. Mọi
thay đổi kho được dựng ở vùng tạm (staging), kiểm tra, rồi mới công bố nguyên khối; chat luôn đọc một cặp
**(snapshot kho, chỉ mục)** hoàn chỉnh và khớp nhau (§4.4).

## 2. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu**
- Trang `/upload` có lựa chọn loại upload: **"Tài liệu thường"** (luồng hiện tại, giữ nguyên) và **"Văn bản pháp
  luật"** (luồng mới).
- Đầu vào: file tải từ vbpl (PDF có text, PDF scan, DOCX, ảnh scan) **hoặc** URL trang chi tiết vbpl.
- Luồng 3 bước, **phải xác nhận bước trước mới sang bước sau** (quyết định của người dùng, hướng B):
  1. **Text đúng chưa?** — ảnh trang gốc cạnh text đã trích / OCR (dùng lại code hiện có); kiểm tra trùng.
  2. **Hệ thống hiểu đúng chưa?** — thông tin văn bản (kèm nguồn của từng trường), luật bị sửa, danh sách chỉ dẫn
     sửa đổi với ngày hiệu lực và trạng thái từng chỉ dẫn, cảnh báo thiếu luật gốc.
  3. **Đưa vào kho** — nhập tên người thực hiện; dựng snapshot mới ở staging; kiểm tra; công bố; dựng chỉ mục; chuyển
     chat sang cặp mới.
- Văn bản trùng số hiệu: báo trùng; nếu nội dung khác thì hiện **so sánh từng điều** để người dùng review rồi chọn
  "Thay bản trong kho" hoặc "Hủy" (quyết định của người dùng), theo quy tắc thay thế theo nguồn (§4.1).
- Luật sửa đổi mà luật gốc chưa có trong kho: **báo "cần upload luật gốc"** (quyết định của người dùng).
- Sau bước 3, hỏi đáp theo mốc (phần 2) dùng văn bản mới mà không cần khởi động lại server — nhưng chỉ khi cả
  snapshot lẫn chỉ mục mới đều hoàn tất.

**Không làm trong phần 3**
- Đính kèm hợp đồng trong chat (phần 4).
- Sửa từng chỉ dẫn sửa đổi ngay trong trang upload — việc đó làm ở trang `/review` đã có.
- Tự tải luật gốc / văn bản liên quan từ vbpl khi upload (crawler `discover` vẫn là đường cho việc này). Chỉ tra
  **thông tin** (metadata) vbpl của chính văn bản đang upload theo số hiệu, để đối chiếu (§4.2).
- Nhận nghị định, thông tư, quyết định vào kho luật.
- Xoá văn bản khỏi kho.
- Phân quyền / đăng nhập (ứng dụng chạy nội bộ, như các trang hiện có).
- Thay đổi mô hình thời gian của phần 1 (ngày hiệu lực theo chỉ dẫn / theo đơn vị đã có sẵn; xem §4.2).

**Phản mục tiêu** (xảy ra là thất bại dù code chạy)
- **Chat đọc một trạng thái kho chưa hoàn chỉnh**: một phần luật đã dựng lại, phần còn lại chưa; hoặc snapshot mới
  với chỉ mục cũ (hay ngược lại).
- Văn bản vào kho khi người dùng chưa qua đủ 3 bước xác nhận.
- Bản trong kho bị thay mà không giữ bản cũ, hoặc thay mà người dùng không được xem chỗ khác.
- Hai lần ghi đồng thời vào kho (hai upload cùng số hiệu, upload và quyết định duyệt) mà một lần âm thầm mất.
- Text đưa vào kho là text đã che PII (luật là văn bản công khai; che PII có thể làm hỏng số hiệu, ngày, tên cơ
  quan → hỏng chỉ dẫn sửa đổi).
- Một ngày người dùng gõ vào form âm thầm thay cho ngày đọc từ câu chữ văn bản, rồi phiên bản dựng ra `verified`.
- Thông tin vbpl kế thừa từ bản cũ được dùng như thông tin đã xác minh cho bản mới mà không ghi rõ nguồn.
- Upload một văn bản làm hỏng chat (dựng / chỉ mục lỗi phải giữ cặp cũ).
- Trang báo "xong" khi dựng hoặc chỉ mục lỗi.
- Phiên bản do text upload tạo ra trông đáng tin hơn phiên bản do crawler tạo ra (cùng quy tắc tự xác minh của
  phần 1, không nới lỏng).

## 3. Ràng buộc

- Dùng lại `rag.legal` (phần 1): `parse_structure`, `parse_effectivity`, `parse_directives`, `build_operations`,
  `LegalStore`, `LegalService.plan_operations` / `build_law` / `build_all`. Quy tắc tự xác minh / `needs_review` giữ
  nguyên.
- Dùng lại phần trích xuất / OCR / báo cáo từng trang / ảnh trang của trang `/upload` hiện có. Khác biệt duy nhất về
  dữ liệu: text đi vào kho luật **không che PII**.
- Text văn bản trong kho phải ở cùng dạng với text crawler tạo (`html_to_legal_text`: mỗi Điều/Khoản/Điểm/tiêu đề
  một dòng) vì `parse_structure` dựa vào ranh giới dòng.
- Giao diện theo khung trang `/upload` hiện có (Tailwind, cột trái tải lên + lịch sử, cột phải chi tiết), tiếng Việt,
  dùng được ở 390px.
- Thao tác chạy lâu (OCR, dựng, chỉ mục) không chạy trên event loop.

## 4. Luồng chi tiết

### 4.0 Bản nháp upload

Mỗi lần upload văn bản pháp luật tạo một **bản nháp** (`upload_id`), lưu dưới `DATA_DIR/legal/uploads/<upload_id>/`:
file gốc (hoặc URL), text đã trích, thông tin văn bản kèm nguồn từng trường, bước hiện tại, các quyết định ở từng
bước, và **snapshot cơ sở** (`base_snapshot_id` + checksum của bản trong kho mà người dùng đã so sánh, nếu trùng).
Bản nháp **không** nằm trong kho cho tới khi snapshot chứa nó được công bố. Bản nháp sống qua khởi động lại server;
lịch sử bên trái liệt kê cả bản nháp dang dở và bản đã vào kho. Người dùng có thể huỷ bản nháp.

Trạng thái bản nháp: `step1` → `step2` → `step3` → `queued` → `building` → `published` | `failed` | `stale`
(kho đã thay đổi, phải xem lại — §4.4) | `cancelled`.

### 4.1 Bước ① — Text đúng chưa?

**Lấy text**
- *URL vbpl* (dạng `https://vbpl.vn/van-ban/chi-tiet/{id}`): gọi `VbplClient.detail(id)`, text bằng
  `html_to_legal_text`, thông tin văn bản bằng `metadata_from_detail` — giống hệt crawler. Không có ảnh trang; bước ①
  hiện text và đường link về trang vbpl.
- *File*: trích xuất / OCR bằng loader hiện có (không che PII, không qua bước bỏ qua `has_doc` của kho cũ), hiện báo
  cáo từng trang như trang `/upload` (ảnh trang gốc cạnh text, độ tin cậy OCR, trang thiếu nội dung). Text được chuẩn
  hoá về dạng một-đơn-vị-một-dòng trước khi phân tích (ghép dòng bị ngắt giữa câu do PDF; tách dòng tại "Điều N.",
  "N.", "a)", "Chương", "Mục"...).

**Kiểm tra cấu trúc**: số Điều đọc được, các Điều bị nhảy số (ví dụ có Điều 12 rồi Điều 14), có tìm thấy điều hiệu
lực thi hành không. Nhảy số hoặc không có Điều nào → cảnh báo nổi bật, vẫn cho đi tiếp nếu người dùng xác nhận.

**Kiểm tra trùng** — theo số hiệu đọc được → `document_key`, so với **snapshot đang công bố**:
- Không trùng → nút "Text đúng, sang bước ②".
- Trùng, text giống hệt (cùng checksum) → báo "Văn bản này đã có trong kho (đưa vào ngày …, nguồn …), không có gì
  thay đổi"; bản nháp dừng ở đây, không tạo bản mới.
- Trùng, text khác → báo trùng và hiện **phần so sánh từng điều**:
  - tóm tắt: số điều giống / sửa / thêm / bỏ;
  - danh sách điều bị sửa; mỗi điều hiện bản trong kho cạnh bản mới, tô màu chỗ khác ở mức từ;
  - điều thêm / bỏ liệt kê riêng;
  - so sánh trên text đã chuẩn hoá dòng / khoảng trắng, để khác biệt định dạng không hiện thành "điều bị sửa";
  - nút **"Thay bản trong kho"** (nếu quy tắc dưới cho phép; đi tiếp sang bước ② ở chế độ thay thế) và **"Hủy"**.
- Số hiệu chưa đọc được → kiểm tra trùng lại ở bước ② sau khi người dùng nhập số hiệu (cùng quy tắc, có thể quay về
  hiện phần so sánh).

**Quy tắc thay thế theo nguồn** (quyết định của người dùng):

| Bản trong kho | Bản mới là URL vbpl | Bản mới là file |
|---|---|---|
| từ vbpl (crawler hoặc upload URL) | được thay | **không được thay**: vẫn hiện so sánh để tham khảo, chỉ có nút "Hủy" kèm giải thích "bản vbpl là text gốc" |
| từ file upload | được thay | được thay (ví dụ sửa lỗi OCR) |

Quy tắc kiểm tra ở server, không chỉ ở giao diện.

### 4.2 Bước ② — Hệ thống hiểu đúng chưa?

**Thông tin văn bản** (form, điền sẵn những gì đọc được). Mỗi trường hiển thị **giá trị + nguồn + thời điểm**:

| Nguồn | Ý nghĩa |
|---|---|
| `vbpl` | tra từ vbpl trong lần upload này (kèm `vbpl_id`, thời điểm tra) |
| `text` | đọc từ câu chữ văn bản (kèm câu chữ làm bằng chứng) |
| `user` | người dùng nhập (kèm tên, thời điểm) |
| `inherited` | giữ lại từ bản trước trong kho (kèm nguồn gốc và thời điểm của bản trước) |

- Loại văn bản: chỉ nhận `Luật`, `Bộ luật`, `Nghị quyết` (của Quốc hội / UBTVQH) và văn bản hợp nhất `VBHN-VPQH`.
  Loại khác → báo "Kho luật chỉ nhận Luật / Bộ luật / Nghị quyết / VBHN của VPQH; hãy dùng 'Tài liệu thường'" và
  không cho đi tiếp.
- Số hiệu, tên văn bản, cơ quan ban hành, ngày ban hành.
- Trường bắt buộc còn trống → không cho đi tiếp. Nguồn URL: điền từ vbpl, vẫn cho xem lại.

**Ngày hiệu lực — nhiều mốc.** Phần 1 đã có mô hình thời gian theo đơn vị; phần 3 **hiển thị** nó, không tạo mô
hình khác:
- Ngày hiệu lực chung của văn bản (`EffectivityInfo.default_from`), kèm câu chữ điều hiệu lực.
- Các ngoại lệ theo đơn vị (`EffectivityInfo.exceptions`: "Điều 190 và Điều 248 có hiệu lực từ 01/4/2024"), các
  đơn vị hiệu lực theo sự kiện (`conditional_units`), mỗi mục kèm câu chữ.
- Mỗi chỉ dẫn sửa đổi trong danh sách bên dưới hiện ngày hiệu lực **riêng của nó** (`AmendmentOperation.effective_from`
  = `effective_date_for(effectivity, directive.source_address)`).
- Không đọc được ngày chung: bắt nhập ngày (nguồn `user`); ngày này chỉ là dự phòng (`vbpl_effective_from`), phiên
  bản dựng từ đó vẫn `needs_review` (`effectivity.unresolved`) như phần 1.
- Phạm vi gắn cờ giữ nguyên quy tắc phần 1: chỉ dẫn không xác định được ngày thì chính chỉ dẫn đó `pending`; riêng
  khi điều hiệu lực có ngày không gắn được vào đơn vị nào (`effectivity.unit_exception_unresolved`) hoặc cờ hiệu lực
  khác, phần 1 đặt **mọi** chỉ dẫn của văn bản `pending` (`operations.py`: `reasons += effectivity.flags`). Phần 3 không
  đổi quy tắc này; giao diện nói rõ lý do ("điều hiệu lực có ngày 01/7/2025 chưa gắn được vào điều nào, nên mọi chỉ
  dẫn cần duyệt").

**Đối chiếu vbpl cho nguồn file** (quyết định của người dùng): khi có số hiệu và loại văn bản, hệ thống tra vbpl
theo số hiệu (`search_by_number` + lọc loại như `fetch_document`) chỉ để lấy thông tin: `vbpl_id`,
`vbpl_effective_from/to`, `eff_status`, cơ quan, ngày ban hành. Thông tin tra được hiện cạnh thông tin đọc từ text;
chỗ lệch được nêu rõ. Mục đích: các kiểm tra phần 1 dựa trên thông tin vbpl (`effectivity.vbpl_mismatch`,
`_flag_known_gaps`) chạy giống hệt văn bản crawl về. Tra không được (không tìm thấy, mạng lỗi) → vẫn cho đi tiếp,
nhưng mọi phiên bản sinh ra từ văn bản này `needs_review` với lý do mới `source.no_vbpl_metadata` ("không có thông tin
vbpl đối chiếu trong lần upload này"); lý do này nằm trong logic dựng phiên bản (builder/status), không chỉ ở giao
diện. Nút "Tra lại vbpl" trên bản nháp.

**Kế thừa thông tin khi thay thế** (chế độ thay thế): trường vbpl của bản cũ (`vbpl_id`, `eff_status`,
`vbpl_effective_from/to`, `issuer`) được giữ khi bản mới không có giá trị, với nguồn `inherited`. Quy tắc:
- Giá trị `inherited` **không** tính là đối chiếu vbpl của lần này: nếu lần upload này tra vbpl không được, vẫn áp
  `source.no_vbpl_metadata` dù có giá trị kế thừa.
- Giá trị kế thừa mâu thuẫn với text mới (ví dụ ngày hiệu lực kế thừa ≠ ngày đọc từ điều hiệu lực mới, số hiệu
  khác) → cảnh báo ở bước ② và lý do `source.inherited_metadata_conflict` trên phiên bản (→ `needs_review`).

**Hai trạng thái xác minh nguồn của văn bản** (lưu cùng văn bản trong kho, hiển thị ở bước ② và trong lịch sử):
- `content_verified`: người dùng đã xác nhận text khớp bản gốc ở bước ① (ai, lúc nào). Văn bản từ crawler/URL vbpl:
  text gốc từ vbpl, coi như đã xác minh nội dung.
- `source_verified`: thông tin văn bản đã đối chiếu với vbpl trong lần nạp này (thời điểm, `vbpl_id`). `false` ⇔
  có `source.no_vbpl_metadata`.

**Hệ thống hiểu văn bản** (xem trước, chưa ghi gì vào kho):
- Văn bản là: luật gốc / luật sửa đổi / văn bản hợp nhất.
- Luật sửa đổi: liệt kê luật bị sửa; mỗi luật ghi "có trong kho" hoặc cảnh báo **"Văn bản này sửa <tên> <số hiệu>,
  nhưng kho chưa có luật này. Hãy upload luật gốc."** Vẫn cho đi tiếp; chỉ dẫn nhắm vào luật thiếu ở trạng thái chờ
  luật gốc (`operation.target_law_not_found`) và được áp dụng khi luật gốc vào kho sau. Trang lịch sử có danh sách
  **"Chỉ dẫn đang chờ luật gốc"** (theo luật đích còn thiếu) để quản lý.
- Danh sách chỉ dẫn sửa đổi, mỗi dòng: vị trí trong văn bản nguồn (ví dụ "Điều 1 khoản 2"), thao tác bằng lời (ví dụ
  "Sửa đoạn đầu khoản 4 Điều 260"), **ngày hiệu lực riêng**, trạng thái **tự xác minh** / **cần duyệt** kèm lý do bằng
  tiếng Việt (ánh xạ từ mã `status_reasons`). Bấm một dòng → xem câu chữ gốc của chỉ dẫn.
- Văn bản làm hết hiệu lực luật khác (`REPEAL_DOCUMENT`): liệt kê.
- Luật gốc: số chỉ dẫn từ các văn bản đã có trong kho đang chờ luật này (sẽ được áp dụng).
- VBHN: phải xác định được luật được hợp nhất (`parse_consolidation_header`) — không xác định được → không cho đi
  tiếp; luật đó chưa có trong kho → cảnh báo "cần upload luật gốc". Quan hệ `HOP_NHAT` được ghi khi đưa vào kho.
- Chế độ thay thế: "Các chỉ dẫn đã được duyệt tay sẽ giữ nguyên quyết định; chỉ dẫn đã duyệt mà không còn trong bản
  mới sẽ mở mục duyệt". Thay VBHN: giữ quan hệ `HOP_NHAT` tới luật được hợp nhất; thay luật gốc / luật sửa đổi: giữ
  mọi quan hệ (`SUA_DOI_BO_SUNG`, `THAY_THE`, `HOP_NHAT`) trỏ tới / từ văn bản này.

Nút: "← Quay lại bước ①" và "Hiểu đúng, sang bước ③".

### 4.3 Bước ③ — Đưa vào kho

- Ô **tên người thực hiện** (bắt buộc) và ghi chú (không bắt buộc). Tóm tắt những gì sẽ xảy ra (văn bản mới hay
  thay thế; toàn kho sẽ được dựng lại ở staging; chat chuyển sang dữ liệu mới chỉ khi mọi thứ xong).
- Bấm "Đưa vào kho luật" → bản nháp vào **hàng đợi ghi** (§4.4). Màn hình kết quả hiện các giai đoạn: chờ lượt →
  dựng snapshot (luật đang dựng / tổng số) → kiểm tra → công bố → dựng chỉ mục → chat đã chuyển sang dữ liệu mới.
- **Kết quả** (sau khi chat đã chuyển): với từng luật có thay đổi: số điều có phiên bản mới so với snapshot trước, số
  mục duyệt mới mở do lần upload này, link sang `/review` (lọc theo luật).
- Thất bại ở bất kỳ giai đoạn nào: trang báo rõ giai đoạn nào lỗi và lý do; chat vẫn dùng cặp cũ; bản nháp `failed`
  kèm nút "Thử lại" (dựng lại staging từ snapshot đang công bố) và "Huỷ"; không báo thành công.
- Nhật ký upload: ai, lúc nào, nguồn, checksum, mới / thay thế, snapshot tạo ra, kết quả từng giai đoạn.

### 4.4 Snapshot, staging và công bố nguyên khối

**Snapshot kho** là một trạng thái hoàn chỉnh, bất biến sau khi công bố của toàn bộ kho luật: danh mục văn bản, quan
hệ, thao tác, mục duyệt, bản dựng. Mỗi snapshot có `snapshot_id` riêng (khác `build_id` của từng luật — một snapshot
chứa một bản dựng cho mỗi luật) và trạng thái `building` → `validated` → `published` | `failed`. Snapshot ghi
`parent_snapshot_id`, lý do (upload `<upload_id>` / quyết định duyệt `<review_id>` / crawler), người thực hiện.

**Text nguồn bất biến, đánh địa chỉ theo nội dung**: text văn bản ghi vào `DATA_DIR/legal/raw/<key>/<checksum>.txt`,
không bao giờ ghi đè. Nhiều snapshot dùng chung file; thay thế văn bản = snapshot mới trỏ tới file mới, file cũ còn
nguyên (thay cho việc chuyển file vào `archive`). Văn bản đã có (đường dẫn cũ `raw/<key>.txt`) giữ nguyên; người xây
dựng quyết định có chuyển đổi hay không, miễn không ghi đè.

**Luồng ghi** (một người ghi tại một thời điểm — khoá ghi toàn kho):
1. Lấy lượt trong hàng đợi ghi. Kiểm tra lại bản nháp với snapshot đang công bố: nếu `base_snapshot_id` khác và văn
   bản cùng số hiệu đã thay đổi so với bản người dùng đã so sánh (checksum khác) → bản nháp `stale`, người dùng phải
   xem lại bước ① (so sánh mới). Hai người upload cùng số hiệu gần như đồng thời: người đến sau luôn rơi vào trường
   hợp này hoặc trường hợp "đã có, giống hệt" — chỉ một thao tác được ghi nhận.
2. Tạo staging từ snapshot đang công bố (bản sao `catalog.sqlite`, hoặc cách khác của người xây dựng — miễn snapshot
   đang công bố không bị chạm tới).
3. Ghi văn bản, quan hệ, trạng thái xác minh nguồn vào staging; chạy `LegalService.build_all()` trên staging (lập lại
   thao tác cũ → mới, dựng mới → cũ). Toàn kho, vì `plan_operations` dùng `prior_operations` của mọi văn bản ban hành
   trước: một luật sửa đổi chen vào giữa dòng thời gian làm thay đổi cách lập của các văn bản sau.
4. **Kiểm tra (validate)** staging: `build_all` chạy hết không lỗi; mọi văn bản không phải VBHN có bản dựng mới nhất
   trong staging với `inputs` khớp thao tác hiện tại; mọi văn bản tham chiếu tới file text tồn tại và checksum khớp;
   không có thao tác `auto_accepted/approved` trỏ tới văn bản không tồn tại. Đạt → `validated`.
5. **Công bố**: đổi con trỏ "snapshot đang công bố" sang staging (thao tác nguyên tử, ví dụ ghi file con trỏ rồi
   `os.replace`). Snapshot `published`.
6. **Dựng chỉ mục** từ chính snapshot vừa công bố, ở nền; chỉ mục ghi `corpus_snapshot_id`.
7. **Chuyển nguyên tử**: khi chỉ mục xong, chat chuyển sang cặp (snapshot mới, chỉ mục mới) bằng một phép gán tham
   chiếu duy nhất. Trước thời điểm này chat dùng cặp cũ (snapshot cũ + chỉ mục cũ), kể cả khi snapshot mới đã công bố.

**Thất bại**:
- Lỗi ở 2–4 → staging `failed`, giữ để xem lỗi / thử lại; snapshot đang công bố và chat không đổi.
- Lỗi ở 6 (chỉ mục) → snapshot mới vẫn `published` nhưng chat **giữ cặp cũ**; trang báo "kho đã cập nhật nhưng chỉ
  mục hỏi đáp lỗi, chat đang dùng dữ liệu trước đó" + nút "Dựng lại chỉ mục".
- Không rollback toàn kho: không cần, vì snapshot chưa hoàn chỉnh không bao giờ được công bố.

**Đồng thời khi đang dựng chỉ mục**: lần ghi kế tiếp có thể công bố snapshot mới hơn trong lúc chỉ mục trước đang
dựng. Chỉ mục luôn gắn với đúng một snapshot; khi xong, chỉ chuyển chat nếu snapshot của nó vẫn là snapshot mới nhất
đã công bố có chỉ mục (không bao giờ chuyển lùi); chỉ mục của snapshot đã bị vượt có thể bỏ. Không bao giờ có chỉ mục
trộn dữ liệu của hai snapshot.

**Request đang chạy**: mỗi request chat lấy tham chiếu tới cặp (snapshot, chỉ mục) một lần lúc bắt đầu và dùng nó đến
hết. Snapshot cũ (file sqlite, chỉ mục) chỉ được dọn khi không còn request nào giữ và đã có ít nhất N snapshot mới
hơn (N do người xây dựng chọn, mặc định giữ 3 snapshot gần nhất).

**Mọi đường ghi vào kho đi qua cùng cơ chế**: upload (phần 3), quyết định duyệt ở `/review` (hiện `decide` dựng lại
luật tại chỗ), và lệnh `python -m rag.legal crawl/build`. Quyết định duyệt cũng vào hàng đợi ghi → staging → công
bố → chỉ mục; trang `/review` hiện "đang áp dụng quyết định" thay vì kết quả tức thì. Vòng kiểm tra định kỳ
`index.stale()` của server hiện tại được thay bằng việc chuyển cặp ở bước 7.

**Đọc ở các trang khác**: `/review` và `/upload` (so sánh trùng, xem trước bước ②) đọc snapshot đang công bố.

## 5. Phần còn lại cho người xây dựng

- API cụ thể (đường dẫn, payload) và cách chia module; gợi ý `rag.legal.upload` (bản nháp, chuẩn hoá, xem trước,
  so sánh) và `rag.legal.snapshots` (staging, validate, công bố, con trỏ, dọn dẹp) cho phần không phụ thuộc web.
- Cách lưu bản nháp (JSON trong thư mục, hay sqlite) miễn sống qua khởi động lại.
- Cơ chế staging cụ thể (sao chép file sqlite là cách đơn giản; kho hiện cỡ vài MB).
- Thuật toán chuẩn hoá dòng cho text từ PDF/DOCX, miễn `parse_structure` đọc được đúng văn bản mẫu (xem §6).
- Cách xem trước chỉ dẫn ở bước ② mà không ghi vào kho (tách phần thuần của `plan_operations`, hoặc chạy trên một
  bản sao tạm).
- Thuật toán so sánh mức từ.
- Dựng chỉ mục toàn bộ hay tăng dần (cache embedding theo nội dung đã có), miễn chỉ mục gắn đúng một snapshot.
- Có chuyển đổi đường dẫn text cũ sang dạng đánh địa chỉ theo nội dung hay không.

## 6. Kiểm thử và tiêu chí xong

**Đơn vị**: chuẩn hoá dòng; kiểm tra trùng (giống / khác / chưa có số hiệu); so sánh từng điều; từ chối loại văn bản
không nhận; VBHN không xác định được luật được hợp nhất bị chặn; cảnh báo thiếu luật gốc; quy tắc thay thế theo
nguồn (kiểm tra ở server); nguồn từng trường thông tin; text vào kho không che PII; bước sau không gọi được khi bước
trước chưa xác nhận (server).

**Tích hợp trên văn bản thật** (fixture phần 1):
- Upload Luật 43/2024/QH15 vào kho đã có Luật Đất đai 31/2024/QH15 → phiên bản giống hệt khi đưa 43/2024 vào bằng
  crawler rồi `build_all`.
- Cùng văn bản dưới dạng PDF có text → cùng danh sách Điều và chỉ dẫn như bản vbpl (nếu khác, phần khác hiện ở bước
  ① / ② chứ không lặng lẽ vào kho).
- Văn bản có nhiều mốc hiệu lực (Luật Đất đai 2024 Điều 252) → bước ② hiện đủ ngày chung, ngoại lệ, đơn vị theo sự
  kiện; mỗi chỉ dẫn mang ngày riêng.

**Các trường hợp biên do người dùng yêu cầu**:

| Test | Kết quả mong muốn |
|---|---|
| Upload luật sửa đổi trước luật gốc | Chỉ dẫn chờ được áp dụng khi luật gốc xuất hiện |
| Upload cùng file hai lần | Phát hiện checksum trùng, không tạo bản mới, không tạo snapshot |
| Hai người upload cùng số hiệu gần như đồng thời | Chỉ một thao tác được ghi nhận; người sau `stale` hoặc "đã có" |
| Upload file sửa bản upload cũ, tra vbpl không được | Không kế thừa trạng thái xác minh nguồn: `source_verified=false`, `source.no_vbpl_metadata` dù có giá trị `inherited` |
| `build_all` lỗi ở luật thứ N | Snapshot staging `failed`; chat tiếp tục dùng snapshot cũ (kiểm bằng truy vấn trước/sau) |
| Dựng phiên bản thành công nhưng chỉ mục lỗi | Chat dùng cặp snapshot/chỉ mục cũ |
| Hai lần upload liên tiếp khi chỉ mục đang dựng | Không có chỉ mục trộn dữ liệu; chat không chuyển lùi |
| Thay VBHN | Giữ liên kết `HOP_NHAT` tới văn bản được hợp nhất; đối chiếu VBHN dùng text mới |
| Request chat đang chạy khi công bố / chuyển cặp | Request trả lời trọn vẹn trên cặp cũ |
| Quyết định duyệt trong lúc upload đang dựng | Xếp hàng; quyết định không bị mất khi snapshot upload công bố |

**Giao diện**: 1366px và 390px.

## 7. Quyết định

**Của người dùng** (buổi thiết kế + review): luồng từng bước (hướng B); kiểm tra cả text lẫn cách hệ thống hiểu văn
bản; trùng số hiệu khác nội dung → so sánh từng điều để review; thiếu luật gốc → báo cần upload luật gốc; tra thông
tin vbpl theo số hiệu cho nguồn file, không tra được → `needs_review`; file không thay được bản vbpl; `build_all`
toàn kho; không rollback toàn kho; **staging + công bố nguyên khối, chat chỉ đọc cặp (snapshot, chỉ mục) hoàn chỉnh**;
nguồn cho từng trường thông tin; tách `content_verified` / `source_verified`; hiển thị nhiều mốc hiệu lực theo mô
hình phần 1; các test biên ở §6.

**Của Claude** (người dùng chưa xác nhận riêng):
- Quyết định duyệt ở `/review` và lệnh CLI cũng đi qua staging/công bố (nếu không, đường ghi đó vẫn tạo trạng thái
  nửa vời — trái yêu cầu tin cậy cao nhất). Hệ quả: duyệt một mục không còn thấy kết quả tức thì.
- Giữ quy tắc phần 1 "cờ hiệu lực cấp văn bản → mọi chỉ dẫn `pending`" (không thu hẹp về từng chỉ dẫn trong phần 3).
- Text nguồn đánh địa chỉ theo nội dung, không ghi đè (thay cho thư mục `archive`).
- Bản nháp có trạng thái `stale` khi kho đổi giữa lúc so sánh và lúc ghi (kiểm soát đồng thời lạc quan).
- Chỉ nhận Luật / Bộ luật / Nghị quyết / VBHN-VPQH; text vào kho không che PII; kiểm tra cấu trúc đặt ở bước ①.
- Text OCR người dùng đã xác nhận theo đúng quy tắc tự xác minh phần 1 (không tự `needs_review` vì là OCR).
- Giữ 3 snapshot gần nhất.
