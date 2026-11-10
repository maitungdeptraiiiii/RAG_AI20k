# Thiết kế: Upload văn bản pháp luật vào kho có phiên bản — Phần 3/4

Ngày: 10/11/2026 · Trạng thái: bản nháp chờ duyệt · Phụ thuộc: Phần 1 (`rag.legal`, spec
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

## 2. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu**
- Trang `/upload` có lựa chọn loại upload: **"Tài liệu thường"** (luồng hiện tại, giữ nguyên) và **"Văn bản pháp
  luật"** (luồng mới).
- Đầu vào: file tải từ vbpl (PDF có text, PDF scan, DOCX, ảnh scan) **hoặc** URL trang chi tiết vbpl.
- Luồng 3 bước, **phải xác nhận bước trước mới sang bước sau** (quyết định của người dùng, hướng B):
  1. **Text đúng chưa?** — ảnh trang gốc cạnh text đã trích / OCR (dùng lại code hiện có); kiểm tra trùng.
  2. **Hệ thống hiểu đúng chưa?** — thông tin văn bản, luật bị sửa, danh sách chỉ dẫn sửa đổi và trạng thái từng
     chỉ dẫn, cảnh báo thiếu luật gốc.
  3. **Đưa vào kho** — nhập tên người thực hiện, ghi vào kho, dựng lại phiên bản, báo kết quả.
- Văn bản trùng số hiệu: báo trùng; nếu nội dung khác thì hiện **so sánh từng điều** để người dùng review rồi chọn
  "Thay bản trong kho" hoặc "Hủy" (quyết định của người dùng).
- Luật sửa đổi mà luật gốc chưa có trong kho: **báo "cần upload luật gốc"** (quyết định của người dùng).
- Sau bước 3, hỏi đáp theo mốc (phần 2) dùng được văn bản mới mà không cần khởi động lại server.

**Không làm trong phần 3**
- Đính kèm hợp đồng trong chat (phần 4).
- Sửa từng chỉ dẫn sửa đổi ngay trong trang upload — việc đó làm ở trang `/review` đã có.
- Tự tải luật gốc / văn bản liên quan từ vbpl khi upload (crawler `discover` vẫn là đường cho việc này). Chỉ tra
  **thông tin** (metadata) vbpl của chính văn bản đang upload theo số hiệu, để đối chiếu (§4.2).
- Nhận nghị định, thông tư, quyết định vào kho luật.
- Xoá văn bản khỏi kho.
- Phân quyền / đăng nhập (ứng dụng chạy nội bộ, như các trang hiện có).

**Phản mục tiêu** (xảy ra là thất bại dù code chạy)
- Văn bản vào kho khi người dùng chưa qua đủ 3 bước xác nhận.
- Bản trong kho bị thay mà không giữ bản cũ, hoặc thay mà người dùng không được xem chỗ khác.
- Text đưa vào kho là text đã che PII (luật là văn bản công khai; che PII có thể làm hỏng số hiệu, ngày, tên cơ
  quan → hỏng chỉ dẫn sửa đổi).
- Một ngày người dùng gõ vào form âm thầm thay cho ngày đọc từ câu chữ văn bản, rồi phiên bản dựng ra `verified`.
- Upload một văn bản làm hỏng chat (dựng lại chỉ mục lỗi phải giữ chỉ mục cũ, như phần 2 đã làm).
- Kho ở trạng thái nửa vời không ai thấy: văn bản đã ghi nhưng dựng phiên bản lỗi mà trang báo "xong".
- Phiên bản do text upload tạo ra trông đáng tin hơn phiên bản do crawler tạo ra (cùng quy tắc tự xác minh của
  phần 1, không nới lỏng).

## 3. Ràng buộc

- Dùng lại `rag.legal` (phần 1): `parse_structure`, `parse_effectivity`, `parse_directives`, `build_operations`,
  `LegalStore`, `LegalService.plan_operations` / `build_law`. Quy tắc tự xác minh / `needs_review` giữ nguyên.
- Dùng lại phần trích xuất / OCR / báo cáo từng trang / ảnh trang của trang `/upload` hiện có. Khác biệt duy nhất về
  dữ liệu: text đi vào kho luật **không che PII**.
- Text văn bản trong kho phải ở cùng dạng với text crawler tạo (`html_to_legal_text`: mỗi Điều/Khoản/Điểm/tiêu đề
  một dòng) vì `parse_structure` dựa vào ranh giới dòng.
- Giao diện theo khung trang `/upload` hiện có (Tailwind, cột trái tải lên + lịch sử, cột phải chi tiết), tiếng Việt,
  dùng được ở 390px.
- Thao tác chạy lâu (OCR, dựng phiên bản, dựng lại chỉ mục) không chạy trên event loop (dùng `_executor` như hiện tại).

## 4. Luồng chi tiết

### 4.0 Bản nháp upload

Mỗi lần upload văn bản pháp luật tạo một **bản nháp** (`upload_id`), lưu dưới `DATA_DIR/legal/uploads/<upload_id>/`:
file gốc (hoặc URL), text đã trích, thông tin văn bản, bước hiện tại, các quyết định ở từng bước. Bản nháp **không**
nằm trong `LegalStore` cho tới bước 3. Bản nháp sống qua khởi động lại server; lịch sử bên trái liệt kê cả bản nháp
dang dở và bản đã đưa vào kho. Người dùng có thể huỷ bản nháp.

### 4.1 Bước ① — Text đúng chưa?

**Lấy text**
- *URL vbpl* (dạng `https://vbpl.vn/van-ban/chi-tiet/{id}`): gọi `VbplClient.detail(id)`, text bằng
  `html_to_legal_text`, thông tin văn bản bằng `metadata_from_detail` — giống hệt crawler. Không có ảnh trang; bước ①
  hiện text và đường link về trang vbpl.
- *File*: trích xuất / OCR bằng loader hiện có (không che PII), hiện báo cáo từng trang như trang `/upload` (ảnh trang
  gốc cạnh text, độ tin cậy OCR, trang thiếu nội dung). Text được chuẩn hoá về dạng một-đơn-vị-một-dòng trước khi
  phân tích (ghép dòng bị ngắt giữa câu do PDF; tách dòng tại "Điều N.", "N.", "a)", "Chương", "Mục"...).

**Kiểm tra cấu trúc** (hiện ngay ở bước ①, vì text sai thường lộ ra ở đây): số Điều đọc được, các Điều bị nhảy số
(ví dụ có Điều 12 rồi Điều 14), có tìm thấy điều hiệu lực thi hành không. Nhảy số hoặc không có Điều nào → cảnh báo
nổi bật, vẫn cho đi tiếp nếu người dùng xác nhận.

**Kiểm tra trùng** — dựa trên số hiệu đọc được (từ vbpl hoặc phần đầu văn bản) → `document_key`:
- Không trùng → nút "Text đúng, sang bước ②".
- Trùng, text giống hệt (cùng checksum) → báo "Văn bản này đã có trong kho (đưa vào ngày …, nguồn …), không có gì
  thay đổi"; bản nháp dừng ở đây.
- Trùng, text khác → báo trùng và hiện **phần so sánh từng điều**:
  - tóm tắt: số điều giống / sửa / thêm / bỏ;
  - danh sách điều bị sửa; mỗi điều hiện bản trong kho cạnh bản mới, tô màu chỗ khác ở mức từ;
  - điều thêm / bỏ liệt kê riêng;
  - hai nút: **"Thay bản trong kho"** (đi tiếp sang bước ② ở chế độ thay thế) và **"Hủy"**.
  - So sánh trên text đã chuẩn hoá dòng / khoảng trắng, để khác biệt định dạng không hiện thành "điều bị sửa".
- **Quy tắc thay thế theo nguồn** (quyết định của người dùng):

  | Bản trong kho | Bản mới là URL vbpl | Bản mới là file |
  |---|---|---|
  | từ vbpl (crawler hoặc upload URL) | được thay | **không được thay**: vẫn hiện so sánh để tham khảo, chỉ có nút "Hủy" kèm giải thích "bản vbpl là text gốc" |
  | từ file upload | được thay | được thay (ví dụ sửa lỗi OCR) |

  Khi thay, các trường lấy từ vbpl của bản cũ (`vbpl_id`, `eff_status`, `vbpl_effective_from/to`, `issuer`) được
  giữ lại nếu bản mới không có giá trị cho trường đó (`upsert_document` là `INSERT OR REPLACE`, phải gộp trước khi
  ghi).
- Số hiệu chưa đọc được → chưa kiểm tra trùng ở bước ①; kiểm tra lại ở bước ② sau khi người dùng nhập số hiệu
  (cùng quy tắc như trên, có thể quay về hiện phần so sánh).

### 4.2 Bước ② — Hệ thống hiểu đúng chưa?

**Thông tin văn bản** (form, điền sẵn những gì đọc được):
- Loại văn bản: chỉ nhận `Luật`, `Bộ luật`, `Nghị quyết` (của Quốc hội / UBTVQH) và văn bản hợp nhất `VBHN-VPQH`.
  Loại khác → báo "Kho luật chỉ nhận Luật / Bộ luật / Nghị quyết / VBHN của VPQH; hãy dùng 'Tài liệu thường'" và
  không cho đi tiếp.
- Số hiệu, tên văn bản, cơ quan ban hành, ngày ban hành.
- **Ngày hiệu lực**: hiện ngày đọc từ điều hiệu lực của văn bản kèm câu chữ gốc làm bằng chứng (chỉ đọc, không sửa).
  Nếu không đọc được: bắt nhập ngày; ngày này chỉ dùng làm ngày dự phòng (`vbpl_effective_from`), và các phiên bản
  dựng từ đó vẫn `needs_review` (`effectivity.unresolved`) như quy tắc phần 1.
- Trường bắt buộc còn trống → không cho đi tiếp. Nguồn URL: điền từ vbpl, vẫn cho xem lại.
- **Đối chiếu vbpl cho nguồn file** (quyết định của người dùng): khi có số hiệu và loại văn bản, hệ thống tra vbpl
  theo số hiệu (`search_by_number` + lọc loại như `fetch_document`) chỉ để lấy thông tin: `vbpl_id`,
  `vbpl_effective_from/to`, `eff_status`, cơ quan, ngày ban hành. Thông tin tra được hiện cạnh thông tin đọc từ
  text; chỗ lệch được nêu rõ. Mục đích: các kiểm tra phần 1 dựa trên thông tin vbpl (`effectivity.vbpl_mismatch`,
  `_flag_known_gaps`) chạy giống hệt văn bản crawl về. Tra không được (không tìm thấy, mạng lỗi) → vẫn cho đi tiếp,
  nhưng mọi phiên bản sinh ra từ văn bản này `needs_review` với lý do mới `source.no_vbpl_metadata` ("không có thông
  tin vbpl để đối chiếu"); lý do này nằm trong logic dựng phiên bản (builder/status), không chỉ ở giao diện. Một lần
  upload sau (hoặc nút "Tra lại vbpl" trên bản nháp) tra được thì lý do này hết.

**Hệ thống hiểu văn bản** (xem trước, chưa ghi gì vào kho):
- Văn bản là: luật gốc / luật sửa đổi / văn bản hợp nhất.
- Luật sửa đổi: liệt kê luật bị sửa; mỗi luật ghi "có trong kho" hoặc cảnh báo **"Văn bản này sửa <tên> <số hiệu>,
  nhưng kho chưa có luật này. Hãy upload luật gốc."** Vẫn cho đi tiếp; chỉ dẫn nhắm vào luật thiếu ở trạng thái chờ
  luật gốc và tự áp dụng khi luật gốc được đưa vào sau (kho đã xử lý như vậy qua `operation.target_law_not_found`).
- Danh sách chỉ dẫn sửa đổi, mỗi dòng: vị trí trong văn bản nguồn (ví dụ "Điều 1 khoản 2"), thao tác bằng lời
  (ví dụ "Sửa đoạn đầu khoản 4 Điều 260"), ngày hiệu lực, trạng thái **tự xác minh** / **cần duyệt** kèm lý do bằng
  tiếng Việt (ánh xạ từ mã `status_reasons`). Bấm một dòng → xem câu chữ gốc của chỉ dẫn.
- Văn bản làm hết hiệu lực luật khác (`REPEAL_DOCUMENT`): liệt kê.
- Luật gốc: số chỉ dẫn từ các văn bản đã có trong kho đang chờ luật này (sẽ được áp dụng sau bước ③).
- VBHN: luật được hợp nhất và có trong kho hay chưa (thiếu → cùng cảnh báo "cần upload luật gốc").
- Chế độ thay thế: thêm dòng "Các chỉ dẫn đã được duyệt tay sẽ giữ nguyên quyết định; chỉ dẫn đã duyệt mà không còn
  trong bản mới sẽ mở mục duyệt".

Nút: "← Quay lại bước ①" và "Hiểu đúng, sang bước ③".

### 4.3 Bước ③ — Đưa vào kho

- Ô **tên người thực hiện** (bắt buộc) và ghi chú (không bắt buộc). Tóm tắt những gì sẽ xảy ra (văn bản mới hay
  thay thế, các luật sẽ được dựng lại).
- Bấm "Đưa vào kho luật":
  1. Ghi text vào `DATA_DIR/legal/raw` (cùng quy ước đặt tên `raw_path_for`). Chế độ thay thế: chuyển file cũ vào
     kho lưu trữ (ví dụ `raw/archive/<key>/<checksum cũ>.txt`) trước khi ghi đè; không xoá.
  2. `upsert_document` với `discovered_via="upload:<upload_id>"`; nguồn URL giữ `vbpl_id` thật, nguồn file để
     `vbpl_id` rỗng.
  3. Ghi quan hệ (`DocumentRelation`, `status="confirmed"`, bằng chứng là câu chữ) như crawler: sửa đổi → luật đích,
     hợp nhất → luật được hợp nhất, thay thế → luật bị thay.
  4. Chạy `LegalService.build_all()` trên toàn kho (lập lại thao tác cũ → mới, dựng mới → cũ). Lập lại chỉ một phần
     không đủ: `plan_operations` dùng `prior_operations` của mọi văn bản ban hành trước, nên một luật sửa đổi chen vào
     giữa dòng thời gian làm thay đổi cách lập của các văn bản sau. Chạy ở nền; màn hình kết quả hiện tiến độ (luật
     đang dựng / tổng số). Chỉ một lần đưa vào kho chạy tại một thời điểm (lần khác chờ, hiện "đang có lần cập nhật
     khác").
  5. Báo chỉ mục hỏi đáp (phần 2) dựng lại ở nền; chat dùng chỉ mục cũ cho tới khi xong.
  6. Ghi nhật ký upload: ai, lúc nào, nguồn, checksum, mới / thay thế, kết quả.
- **Kết quả**: với từng luật được dựng lại: số điều có phiên bản mới so với bản dựng trước, số mục duyệt mới mở do lần
  upload này, link sang `/review` (lọc theo luật); trạng thái chỉ mục hỏi đáp (đang cập nhật / đã cập nhật / lỗi —
  vẫn dùng chỉ mục cũ).
- Lỗi giữa chừng (ví dụ dựng phiên bản lỗi): **không rollback**. Trang báo rõ bước nào lỗi, bản nháp ở trạng thái
  "lỗi khi đưa vào kho" kèm nút "Thử lại" (chạy lại các bước từ đầu; các bước đều ghi đè được nên chạy lại là tự
  sửa), ghi vào nhật ký upload; không báo thành công. Chấp nhận rằng trong lúc lỗi chưa được thử lại, chỉ mục hỏi đáp
  có thể đã nhận một phần bản dựng mới — giống như khi `python -m rag.legal build` bị dừng giữa chừng.

## 5. Phần còn lại cho người xây dựng

- API cụ thể (đường dẫn, payload) và cách chia module; gợi ý `rag.legal.upload` cho phần không phụ thuộc web.
- Cách lưu bản nháp (JSON trong thư mục, hay bảng sqlite trong `catalog.sqlite`) miễn sống qua khởi động lại.
- Thuật toán chuẩn hoá dòng cho text từ PDF/DOCX, miễn `parse_structure` đọc được đúng văn bản mẫu (xem §6).
- Cách xem trước chỉ dẫn ở bước ② mà không ghi vào kho (tách phần thuần của `plan_operations`, hoặc chạy trên một
  bản sao kho tạm).
- Thuật toán so sánh mức từ trong phần so sánh từng điều.
- Có dựng lại chỉ mục toàn bộ hay tăng dần.

## 6. Kiểm thử và tiêu chí xong

- Test đơn vị cho: chuẩn hoá dòng, kiểm tra trùng (giống / khác / chưa có số hiệu), so sánh từng điều, từ chối loại
  văn bản không nhận, cảnh báo thiếu luật gốc, chế độ thay thế giữ quyết định duyệt tay và lưu file cũ, text vào kho
  không che PII.
- Test tích hợp trên văn bản thật của kho hiện có (fixture phần 1): upload Luật 43/2024/QH15 vào một kho đã có Luật
  Đất đai 31/2024/QH15 → các phiên bản sinh ra giống hệt khi đưa 43/2024 vào bằng crawler rồi `build_all`.
- Cùng văn bản đó dưới dạng PDF có text → text sau chuẩn hoá cho cùng danh sách Điều và cùng danh sách chỉ dẫn như
  bản từ vbpl (nếu khác, phần khác phải hiện ở bước ① / ② chứ không lặng lẽ vào kho).
- Upload luật sửa đổi trước, luật gốc sau → sau khi luật gốc vào, chỉ dẫn của luật sửa đổi được áp dụng.
- Nguồn file tra được vbpl → cùng trạng thái phiên bản như bản crawl; tra không được → mọi phiên bản `needs_review`
  với `source.no_vbpl_metadata`.
- Quy tắc thay thế theo nguồn (bảng §4.1): file không thay được bản vbpl (kiểm tra ở server); thay giữ các trường
  vbpl cũ và lưu file cũ vào `raw/archive`.
- API: bước sau không gọi được khi bước trước chưa xác nhận (server kiểm tra, không chỉ giao diện).
- Kiểm tra giao diện ở 1366px và 390px.

## 7. Quyết định của Claude (người dùng chưa xác nhận riêng)

- Vẫn cho đưa luật sửa đổi vào kho khi thiếu luật gốc; chỉ dẫn chờ và tự áp dụng sau.
- Nguồn URL lấy thông tin từ API vbpl; nguồn file đọc từ phần đầu văn bản và điều hiệu lực, thiếu thì bắt nhập.
- Ngày hiệu lực ở bước ② chỉ đọc từ câu chữ; ngày người dùng nhập chỉ là dự phòng và luôn kéo theo `needs_review`.
- Chỉ nhận Luật / Bộ luật / Nghị quyết / VBHN-VPQH; loại khác chuyển sang "Tài liệu thường".
- Text vào kho luật không che PII.
- Kiểm tra cấu trúc (nhảy số Điều, thiếu điều hiệu lực) đặt ở bước ①.
- Bản nháp lưu bền, có lịch sử và huỷ được.
- Chế độ thay thế lưu file cũ vào `raw/archive`, giữ quyết định duyệt tay.
- Sau bước ③ dựng lại chỉ mục hỏi đáp ở nền ngay, không chờ chu kỳ kiểm tra `stale()`.
- Bước ③ chạy `build_all` toàn kho (đúng tuyệt đối, đổi lại thời gian chờ) thay vì dựng lại tăng dần.
- Lỗi ở bước ③ không rollback; báo lỗi + "Thử lại".
- Text OCR đã được người dùng xác nhận ở bước ① theo đúng quy tắc tự xác minh của phần 1 (không tự động
  `needs_review` chỉ vì là OCR); rủi ro OCR sai được chặn ở bước ① (ảnh cạnh text, kiểm tra cấu trúc) và bởi đối
  chiếu vbpl.

Quyết định của người dùng ghi nhận trong buổi thiết kế: luồng từng bước (hướng B); kiểm tra cả text lẫn cách hệ
thống hiểu văn bản; trùng số hiệu khác nội dung → so sánh từng điều để review; thiếu luật gốc → báo cần upload luật
gốc; tra thông tin vbpl theo số hiệu cho nguồn file, không tra được → `needs_review`; file không thay được bản vbpl.
