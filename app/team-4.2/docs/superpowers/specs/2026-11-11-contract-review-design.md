# Thiết kế: Đính kèm hợp đồng trong chat — Phần 4/4

Ngày: 11/11/2026 · Trạng thái: bản nháp chờ duyệt · Phụ thuộc: Phần 1 (`rag.legal`, kho có phiên bản), Phần 2
(`rag.temporal`, hỏi đáp theo mốc), Phần 3 (snapshot + `LegalRuntime` + trang `/upload` văn bản pháp luật), loader /
OCR / che PII hiện có (`rag.ingest.loaders`, `rag.quality.pii`).

## 0. Phạm vi demo (quyết định của người dùng — thắng mọi chỗ mâu thuẫn bên dưới)

Phần 4 làm ở **mức demo để trình bày với mentor**. Giữ nguyên ý tưởng và các quy tắc cốt lõi; bỏ phần "chắc chắn ở quy mô
thật":

**Giữ**: đính kèm trong chat (PDF / DOCX / TXT / ảnh); chọn bên (+ "Trung lập"); 6 thao tác; quy tắc từ chối kết luận
pháp lý khi kho thiếu luật; trích dẫn nguyên văn được kiểm tra; căn cứ kèm khoảng hiệu lực; mốc = ngày ký; che PII
trước LLM; tải Word / PDF (bố cục đơn giản); "Chỉ trong phiên" / "Lưu lại" (bản đơn giản); hai chế độ hỏi + Think với
hợp đồng (§4.7).

**Thu gọn**:
- Hợp đồng tối đa ~30 đơn vị / 20 trang được soát; dài hơn → soát N đơn vị đầu và báo rõ "Bản demo chỉ soát N/M điều
  khoản" (không chia lô / thử lại).
- Kiểm chứng căn cứ (§4.6) gộp thành **một lượt gọi LLM cho cả báo cáo** (không gọi riêng từng kết luận). Một lần soát
  ~4–6 lượt gọi LLM.
- Bản "Chỉ trong phiên": dict trong bộ nhớ server, mất khi tắt server; không có dọn 24h, không kiểm tra `session_id`
  (vẫn dùng `contract_id` ngẫu nhiên). Bản "Lưu lại": thư mục `DATA_DIR/contracts/<id>/` + danh sách id trong
  localStorage; mở lại vào chat mới.
- Không test tải / hợp đồng dài; test cho quy tắc cốt lõi (từ chối, trích dẫn nguyên văn, mốc, che PII, định tuyến chế
  độ hỏi, nguồn của agent).

**Kịch bản demo** (kèm theo bản giao): hợp đồng thuê nhà mẫu ký năm 2023 (`data/team-4.2/contracts_demo/`) có lỗi cài
sẵn — phạt vi phạm vượt mức luật cho phép, thiếu nội dung bắt buộc, điều khoản bất lợi cho bên thuê, một điều khoản
mơ hồ; kho luật demo có nhóm bất động sản (nạp từ fixture phần 1 qua đường snapshot) để thấy: căn cứ Luật Nhà ở 2014
tại ngày ký, "Đối chiếu thay đổi" chỉ ra Luật Nhà ở 2023 thay thế từ 01/8/2024; và một câu Think nhiều bước trên hợp
đồng.

**Cách làm**: Claude làm trực tiếp (không chia subagent / review từng task), một lượt review cuối.

## 1. Ý định và lý do

Ứng dụng dùng để đánh giá hợp đồng. Đến phần 3, người dùng hỏi được "tại ngày X, luật nói gì", nhưng chưa đưa được
**chính hợp đồng của họ** vào cuộc trò chuyện. Phần 4 cho người dùng đính kèm một hợp đồng (chưa biết trước loại nào,
nhiều định dạng) vào chat để AI **hiểu hợp đồng và làm việc trên nó**: tóm tắt, tra soát, chỉ ra điểm chưa hợp lý / lỗ
hổng, đối chiếu với luật **tại ngày ký**, đề xuất sửa, trả lời câu hỏi.

Hệ thống pháp lý: một kết luận "điều khoản này hợp pháp / trái luật" sai nhưng trông chắc chắn là thất bại nặng nhất.
Vì vậy kết luận pháp lý chỉ được đưa ra khi có căn cứ trong kho luật (quyết định của người dùng: **từ chối kết luận**
khi kho thiếu luật liên quan).

## 2. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu**
- Trong khung chat, đính kèm một hợp đồng: PDF (text hoặc scan), DOCX, ảnh scan, TXT. Đọc / OCR bằng loader hiện có.
- Khi đính kèm, người dùng chọn cách lưu (quyết định của người dùng): **"Chỉ trong phiên này"** hoặc **"Lưu lại"**.
- Sau khi đọc: AI liệt kê **các bên** trong hợp đồng; người dùng **chọn mình là bên nào** (quyết định của người dùng),
  có thêm lựa chọn "Trung lập / tư vấn".
- Sáu thao tác trên hợp đồng (quyết định của người dùng — giữ cả 6):
  1. **Tóm tắt**: các bên, đối tượng, giá và thanh toán, thời hạn, nghĩa vụ chính, các mốc thời gian (ngày ký, hiệu
     lực, hạn thanh toán, hạn giao…).
  2. **Soát toàn bộ**: báo cáo các điểm có vấn đề, nhóm: *trái luật*, *thiếu nội dung bắt buộc*, *bất lợi cho bên đã
     chọn*, *mơ hồ / mâu thuẫn / dễ tranh chấp*. Mỗi điểm: mức nghiêm trọng, trích nguyên văn điều khoản, bất lợi cho
     bên nào, căn cứ luật (nếu là kết luận pháp lý), gợi ý sửa.
  3. **Soát một phần**: người dùng chọn điều khoản (AI liệt kê các Điều / mục của hợp đồng để tick) hoặc chủ đề
     (phạt vi phạm, chấm dứt, thanh toán, bồi thường, bảo hành, giải quyết tranh chấp, …); báo cáo cùng dạng mục 2.
  4. **Đối chiếu thay đổi của luật**: luật áp dụng tại ngày ký so với luật hiện hành; điều khoản nào bị ảnh hưởng.
  5. **Đề xuất sửa (redline)**: viết lại các điều khoản có vấn đề; hiện bản cũ cạnh bản đề xuất.
  6. **Hỏi tự do**: hỏi bất kỳ điều gì về hợp đồng; hợp đồng là ngữ cảnh cho mọi lượt sau trong cuộc chat.
- Báo cáo soát (2, 3, 4) và bản đề xuất sửa (5) **tải về được dạng Word (.docx) hoặc PDF** (quyết định của người dùng).
- Mốc pháp lý mặc định = **ngày ký** đọc từ hợp đồng; không đọc được → hỏi người dùng (cho phép nhập ngày). Riêng thao
  tác 4 dùng thêm mốc "hôm nay".

**Không làm trong phần 4**
- So sánh hai phiên bản hợp đồng.
- Đưa hợp đồng vào kho tra cứu chung (hợp đồng không bao giờ được index cùng kho luật / kho tài liệu).
- Soạn hợp đồng mới từ đầu.
- Ký số, chia sẻ hợp đồng giữa người dùng, phân quyền (ứng dụng nội bộ, như các trang hiện có).
- Tự tải luật còn thiếu từ vbpl (người dùng upload qua trang `/upload` của phần 3).

**Phản mục tiêu** (xảy ra là thất bại dù code chạy)
- Một kết luận pháp lý (trái luật / hợp lệ / thiếu nội dung bắt buộc theo luật) **không có căn cứ trích dẫn từ kho**,
  hoặc dựa vào hiểu biết chung của mô hình.
- Dùng luật sai mốc: đánh giá hợp đồng ký năm 2023 bằng luật hiện hành mà không nói rõ.
- Trích dẫn "nguyên văn" điều khoản hợp đồng mà không có trong hợp đồng (bịa câu chữ).
- Hợp đồng của người dùng này xuất hiện trong câu trả lời / tìm kiếm của người khác, hoặc lọt vào kho tra cứu chung.
- Hợp đồng "Chỉ trong phiên này" còn nằm trên đĩa sau khi phiên kết thúc.
- Thông tin cá nhân (CCCD, số tài khoản, SĐT, email…) gửi thẳng ra LLM bên ngoài không qua bước che PII.
- Báo cáo bỏ sót điều khoản mà không nói: soát toàn bộ một hợp đồng dài nhưng chỉ đọc phần đầu.

## 3. Ràng buộc

- Dùng lại: `rag.ingest.loaders.load_source` (đọc / OCR), `rag.ingest.page_report` (chất lượng trang),
  `rag.quality.pii` (`mask_text`, `MaskState`, `unmask`), `LegalRuntime` của phần 3 (snapshot + chỉ mục có phiên bản,
  lease cho mỗi request), tìm kiếm kho cũ (`pipeline.retriever`), LLM của pipeline.
- Tìm căn cứ luật **luôn theo mốc**: kho có phiên bản lọc theo hiệu lực tại mốc (như phần 2); kho cũ chỉ là tham khảo
  và được ghi rõ "chưa xác định phiên bản" (như phần 2). Căn cứ hiển thị kèm khoảng hiệu lực và trạng thái xác minh.
- Mọi request làm việc trên hợp đồng giữ **một** `LegalRuntime` (lease) suốt request — cùng quy tắc phần 3.
- Text gửi ra LLM đi qua che PII; câu trả lời hiển thị cho chính người dùng thì mở che (như chat hiện tại).
- Không cuộn ngang ở 390px; tiếng Việt; khung chat hiện có (`ui/index.html`).
- Thao tác chạy lâu (OCR, soát toàn bộ) không chạy trên event loop; hiển thị tiến độ.
- Xuất DOCX bằng `python-docx` (đã là dependency); PDF bằng PyMuPDF (`fitz.Story`, đã có) — không thêm thư viện mới.

## 4. Luồng chi tiết

### 4.1 Đính kèm

- Nút "+" trong khung chat hiện **hai lựa chọn tách biệt**: "Nạp tài liệu vào kho" (hành vi hiện tại, `/api/ingest`)
  và **"Đính kèm hợp đồng để soát"** (mới). Không được nhầm: hợp đồng không bao giờ đi `/api/ingest`.
- Hộp đính kèm: chọn file + chọn cách lưu ("Chỉ trong phiên này" mặc định, "Lưu lại").
- Server đọc / OCR (không index), chuẩn hoá thành **cấu trúc hợp đồng**: danh sách đơn vị (Điều / mục / khoản theo
  đánh số của chính hợp đồng; hợp đồng không đánh số → theo đoạn), mỗi đơn vị có id ổn định, nhãn hiển thị, text,
  vị trí trang. Báo chất lượng đọc (trang OCR độ tin cậy thấp, trang trống) như trang `/upload`.
- AI trích **thông tin nền**: loại hợp đồng (ước đoán, có thể "chưa rõ"), các bên (tên, vai trò trong hợp đồng — bên
  cho thuê / bên thuê…), ngày ký, ngày hiệu lực, giá trị, thời hạn. Mỗi giá trị kèm trích dẫn đơn vị nguồn; giá trị
  không tìm thấy để trống, không đoán.
- Thẻ hợp đồng trong chat: tên file, số trang, chất lượng đọc, các bên → nút chọn "Tôi là …" (mỗi bên) + "Trung lập /
  tư vấn", ngày ký (sửa được; sửa thì ghi nguồn "người dùng nhập"), 6 nút thao tác.
- Chưa chọn bên → các thao tác vẫn chạy ở chế độ Trung lập; thẻ nhắc chọn bên.
- Một cuộc chat có thể có nhiều hợp đồng; hợp đồng "đang làm việc" là cái được chọn trên thẻ (mặc định cái mới nhất).

### 4.2 Căn cứ luật và quy tắc từ chối

- Với mỗi vấn đề cần kết luận pháp lý, hệ thống tìm căn cứ trong kho tại mốc (ngày ký): kho có phiên bản trước, kho cũ
  sau, như phần 2.
- Một **kết luận pháp lý** (trái luật, hợp lệ, thiếu nội dung bắt buộc theo luật) chỉ được đưa ra khi có ít nhất một
  căn cứ được trích dẫn và kiểm tra được (trích đoạn thật từ kho, đúng mốc). Không có → mục đó ở trạng thái **"Chưa thể
  kết luận"** với lời nhắn: "Kho chưa có [tên luật nếu xác định được / luật điều chỉnh vấn đề này] — chưa thể kết luận
  điều khoản này có hợp pháp không. Có thể upload luật ở trang Nạp văn bản pháp luật." kèm link `/upload`.
- Căn cứ chỉ từ **kho cũ** (chưa có phiên bản) → kết luận tối đa ở mức "có điều kiện", ghi rõ giới hạn (như phần 2).
- **Nội dung bắt buộc** của loại hợp đồng lấy từ luật trong kho (điều về nội dung hợp đồng trong luật chung / luật
  chuyên ngành), không cứng hoá checklist trong code; luật không có trong kho → nhóm "thiếu nội dung bắt buộc" báo
  "chưa thể kiểm tra" thay vì bỏ trống.
- **Nhận xét không pháp lý** (mơ hồ, mâu thuẫn nội bộ, bất lợi thương mại, rủi ro thực tế) vẫn được đưa ra khi không
  có căn cứ luật, nhưng gắn nhãn rõ "Nhận xét về câu chữ / thương mại — không phải kết luận pháp lý".
- Mọi trích dẫn điều khoản hợp đồng phải là đoạn có thật trong text hợp đồng (kiểm tra chuỗi sau chuẩn hoá khoảng
  trắng); trích dẫn không khớp → bỏ trích dẫn đó và hạ mục xuống "cần kiểm tra".

### 4.3 Sáu thao tác

1. **Tóm tắt**: dựa trên thông tin nền + đọc toàn văn; trả về các mục cố định (các bên, đối tượng, giá & thanh toán,
   thời hạn, nghĩa vụ chính mỗi bên, mốc thời gian, luật áp dụng / giải quyết tranh chấp do hợp đồng tự ghi). Mỗi ý có
   tham chiếu đơn vị nguồn.
2. **Soát toàn bộ**: duyệt **mọi** đơn vị của hợp đồng (chia lô nếu dài — không cắt bớt); báo cáo có dòng "Đã soát N/N
   điều khoản". Mỗi phát hiện: nhóm, mức (Nghiêm trọng / Cần sửa / Lưu ý), đơn vị + trích nguyên văn, bất lợi cho bên
   nào, giải thích, căn cứ (hoặc "Chưa thể kết luận…"), gợi ý sửa. Phát hiện bất lợi cho bên đã chọn lên đầu; trái
   luật và thiếu nội dung bắt buộc luôn được báo dù bên nào.
3. **Soát một phần**: như 2 nhưng chỉ trên đơn vị người dùng tick hoặc chủ đề người dùng chọn (hệ thống ánh xạ chủ đề
   → đơn vị liên quan, hiển thị danh sách đơn vị đã chọn để người dùng thấy phạm vi).
4. **Đối chiếu thay đổi của luật**: với các căn cứ dùng cho hợp đồng (hoặc chạy soát nhanh nếu chưa có), so phiên bản
   tại ngày ký với phiên bản hiện hành (kho có phiên bản); liệt kê điều luật đã đổi / hết hiệu lực / luật thay thế, điều
   khoản hợp đồng bị ảnh hưởng, và quy định chuyển tiếp liên quan (như phần 2). Căn cứ chỉ có trong kho cũ → báo "không
   theo dõi được thay đổi (kho chưa có phiên bản)".
5. **Đề xuất sửa**: cho các phát hiện (của lần soát gần nhất, hoặc chạy soát nếu chưa có) — viết lại điều khoản theo
   hướng bảo vệ bên đã chọn (Trung lập: cân bằng hai bên), hiện bản cũ cạnh bản đề xuất (tô khác biệt), kèm lý do. Đề
   xuất cho mục "Chưa thể kết luận" chỉ dựa trên câu chữ và ghi rõ chưa kiểm tra pháp lý.
6. **Hỏi tự do**: câu hỏi trong chat khi có hợp đồng đang làm việc → trả lời dựa trên hợp đồng (các đơn vị liên quan)
   + căn cứ luật tại mốc; cùng quy tắc từ chối và trích dẫn. Người dùng có thể bỏ chọn hợp đồng để hỏi như chat thường.

### 4.4 Tải về

- Báo cáo (2, 3, 4) và đề xuất sửa (5) có nút "Tải Word" / "Tải PDF". Nội dung giống bản trong chat: tiêu đề hợp đồng,
  bên đã chọn, mốc pháp lý, ngày tạo, "Đã soát N/N", từng phát hiện, căn cứ (kèm hiệu lực / trạng thái), các mục "Chưa
  thể kết luận", ghi chú giới hạn ("Không thay thế tư vấn pháp lý").
- Bản tải về **mở che PII** (dành cho chính người dùng), tạo khi bấm, không lưu sẵn ở chế độ "Chỉ trong phiên này".

### 4.5 Lưu trữ

- **Chỉ trong phiên này**: file gốc, text, cấu trúc, kết quả nằm trong bộ nhớ server, gắn với `session_id` chat; xoá khi
  phiên kết thúc (người dùng xoá cuộc chat, hoặc quá N giờ không hoạt động — N do builder chọn, mặc định 24h) hoặc
  server khởi động lại. Không ghi đĩa (file tạm cho OCR phải xoá ngay sau khi đọc).
- **Lưu lại**: `DATA_DIR/contracts/<contract_id>/` — file gốc, text, cấu trúc, thông tin nền, bên đã chọn, các báo cáo
  đã tạo. Trang / ngăn "Hợp đồng đã lưu" trong UI: mở lại vào cuộc chat, xoá (xoá hẳn thư mục).
- Đổi từ "Chỉ trong phiên" sang "Lưu lại" được (nút "Lưu hợp đồng này").

### 4.6 Định danh, vòng đời, định tuyến chat (quyết định của Claude sau review)

- **Định danh**: `contract_id` do server sinh, ngẫu nhiên không đoán được (≥ 128 bit). Mọi API hợp đồng yêu cầu
  `contract_id`; với bản "Chỉ trong phiên" còn phải khớp `session_id` đã đính kèm. Server **không** có API liệt kê mọi
  hợp đồng: danh sách "Hợp đồng đã lưu" là danh sách `contract_id` trình duyệt tự giữ (localStorage, bọc try/catch) —
  người có link/id mở được, như mọi trang nội bộ khác (không có đăng nhập).
- **Vòng đời bản "Chỉ trong phiên"**: xoá khi trình duyệt gọi xoá (xoá cuộc chat, bấm "Gỡ hợp đồng" → `DELETE`), hoặc
  sau 24h không hoạt động, hoặc server khởi động lại. Khi thẻ hợp đồng trỏ tới bản đã mất, thẻ hiện "Hợp đồng này đã
  hết phiên — hãy đính kèm lại" và khoá các nút. Bản "Lưu lại" mở được vào bất kỳ cuộc chat nào (kể cả chat mới).
- **Định tuyến chat**: xem §4.7 (hai chế độ hỏi; Think dùng được với hợp đồng).
- **Kiểm tra căn cứ**: "căn cứ kiểm tra được" = đoạn có thật trong kho, hiệu lực bao trùm mốc, **và** một bước kiểm
  chứng LLM riêng xác nhận đoạn đó thực sự hỗ trợ kết luận (đọc đoạn luật + điều khoản + kết luận, trả lời
  hỗ trợ / không hỗ trợ / không liên quan). Không qua bước này → "Chưa thể kết luận". Lý do: một điều luật tìm được
  nhưng không liên quan "biện minh" cho kết luận chính là phản mục tiêu số 1.
- **Ngày**: ngày ký là mốc duy nhất. Thiếu ngày ký → chỉ chặn các phần pháp lý (kết luận pháp lý ở 2, 3, 6; toàn bộ 4)
  cho tới khi người dùng nhập; tóm tắt và nhận xét câu chữ vẫn chạy. Có nhiều ngày (ký, hiệu lực, phụ lục ký sau) → thẻ
  hiện ngày ký đã chọn kèm trích dẫn và các ngày khác; phụ lục có ngày riêng được ghi chú "phụ lục ký ngày … — đang đánh
  giá theo ngày ký hợp đồng chính". Không bao giờ ngầm dùng "hôm nay" cho kết luận pháp lý (trừ vế "hiện hành" của 4).
- **Che PII**: dùng `mask_text` hiện có với một `MaskState` riêng cho mỗi hợp đồng (placeholder nhất quán trong mọi lượt
  về hợp đồng đó). Các định danh (CCCD/CMND, MST, số tài khoản, SĐT, email, họ tên sau "Họ và tên:") bị che; vai trò
  các bên ("Bên A – bên cho thuê") và nội dung điều khoản giữ nguyên. Kiểm tra trích dẫn nguyên văn, đề xuất sửa và bản
  tải về làm trên text đã mở che.
- **Soát dài**: chia lô, hiện tiến độ "Đã soát i/N"; lô lỗi được thử lại một lần, vẫn lỗi → các đơn vị đó ghi "Chưa soát
  được" trong báo cáo kèm nút "Soát lại phần còn thiếu". Báo cáo không bao giờ ghi "N/N" khi còn đơn vị chưa soát.
- **PDF tiếng Việt**: đóng gói một font có dấu tiếng Việt (giấy phép OFL, ví dụ Noto Sans) trong repo cho `fitz.Story`;
  đề xuất sửa trong PDF/DOCX giữ tô khác biệt (gạch bỏ / gạch chân).
- **Lưu đĩa**: bản "Lưu lại" lưu thô (file gốc + text) dưới `DATA_DIR/contracts/`, như các dữ liệu khác của ứng dụng
  nội bộ; giới hạn file 50 MB như trang `/upload` (413 + thông báo tiếng Việt).

### 4.7 Hai chế độ hỏi và Think với hợp đồng (quyết định của người dùng)

**Hai chế độ** — công tắc ngay trên ô nhập chat:
- **Hỏi tự do**: như chat hiện tại (hỏi đáp theo mốc phần 2–3; Think như hiện có). Không gửi hợp đồng.
- **Hỏi với hợp đồng**: câu hỏi gắn với hợp đồng đang làm việc; chỉ bật được khi đã đính kèm. `/api/chat` nhận
  `contract_id`; có `contract_id` → đường hợp đồng. Nhãn chế độ hiện trên mỗi tin nhắn của người dùng để biết câu đó
  có kèm hợp đồng hay không.
- Nút thứ 6 trên thẻ hợp đồng đổi tên **"Hỏi về hợp đồng này"**: chuyển ô nhập sang chế độ Hỏi với hợp đồng và chọn hợp
  đồng đó.

**Think trong chế độ Hỏi với hợp đồng: bật được** (quyết định của người dùng). Thiết kế (của Claude):
- Agent multi-hop (`rag.agent`) giữ nguyên vòng lặp (lập yêu cầu → tìm nhiều vòng → kiểm chứng trích dẫn nguyên văn →
  trả lời có trạng thái), nhưng tìm trên **nguồn có thể cắm** thay vì chỉ kho cũ: tách một giao diện nguồn từ
  `CorpusSnapshot` hiện tại; cài đặt:
  1. **Nguồn hợp đồng**: các đơn vị của hợp đồng đang làm việc (đã che PII), tìm bằng BM25 trong bộ nhớ; dẫn chiếu nội
     bộ hợp đồng ("Điều 5 của hợp đồng này", "Phụ lục 1") được đi theo.
  2. **Nguồn kho có phiên bản tại ngày ký**: tìm qua chỉ mục của `LegalRuntime` đang lease, lọc hiệu lực tại mốc (như
     phần 2). Bản demo **chưa** đi theo dẫn chiếu trong nguồn này.
  3. **Nguồn kho cũ**: như hiện nay, gắn nhãn "chưa xác định phiên bản".
  Mỗi đoạn bằng chứng mang nhãn nguồn (hợp đồng / luật có phiên bản + hiệu lực / kho cũ).
- **Che PII ở ngoài agent**: câu hỏi, lịch sử và đơn vị hợp đồng được che bằng `MaskState` của hợp đồng trước khi vào
  agent; câu trả lời và trích dẫn mở che ở cuối. Agent không thấy giá trị thật.
- **Quy tắc pháp lý thêm vào bước kết luận của agent**: khẳng định pháp lý phải có ít nhất một bằng chứng từ nguồn kho
  có phiên bản tại mốc; chỉ kho cũ → trạng thái tối đa "một phần / có điều kiện"; không có → nêu "Chưa thể kết luận… có
  thể upload luật ở /upload". Khẳng định về nội dung hợp đồng phải có bằng chứng từ nguồn hợp đồng.
- Hành vi Think **không có hợp đồng** (chế độ Hỏi tự do) giữ nguyên như hiện tại (chỉ kho cũ) trong phạm vi demo; ghi
  nhận việc sau: thêm nguồn kho có phiên bản và che PII cho cả Think tự do.
- `tests/test_agent.py` (37 test) phải tiếp tục qua; thêm test cho nguồn hợp đồng, nguồn có phiên bản lọc theo mốc,
  quy tắc pháp lý và việc agent chỉ nhận text đã che.

## 5. Phần còn lại cho người xây dựng

- Module / API cụ thể (gợi ý gói `rag.contracts` + `ui/contracts_api.py`), dạng dữ liệu cấu trúc hợp đồng, prompt.
- Cách chia lô và cách gom kết quả khi soát hợp đồng dài.
- Cách ánh xạ chủ đề → đơn vị ở "Soát một phần".
- Bố cục thẻ hợp đồng và báo cáo trong chat; bố cục DOCX / PDF.
- Thời gian sống mặc định của bản "Chỉ trong phiên" (mặc định 24h).

## 6. Kiểm thử và tiêu chí xong

- Đơn vị: tách đơn vị hợp đồng (có / không đánh số); trích thông tin nền với giá trị thiếu để trống; kiểm tra trích dẫn
  nguyên văn; quy tắc từ chối (không căn cứ → "Chưa thể kết luận"); căn cứ chỉ kho cũ → không "chắc chắn"; mốc = ngày
  ký; che PII trước LLM; xuất DOCX / PDF chứa các phần bắt buộc.
- Tích hợp với LLM giả + kho thật (fixture bất động sản): hợp đồng thuê nhà ký 2023 → căn cứ Luật Nhà ở 2014 tại ngày
  ký; "Đối chiếu thay đổi" chỉ ra Luật Nhà ở 2023 thay thế từ 01/8/2024 và quy định chuyển tiếp.
- Hợp đồng loại không có luật chuyên ngành trong kho → các mục pháp lý "Chưa thể kết luận", nhận xét câu chữ vẫn có.
- Soát toàn bộ hợp đồng dài (≥ 60 điều) → "Đã soát N/N", không đơn vị nào bị bỏ.
- Cách ly: hợp đồng không xuất hiện trong `/api/chat` của phiên khác; không có trong chỉ mục kho; bản "Chỉ trong phiên"
  không còn trên đĩa sau khi phiên hết hạn / server khởi động lại.
- Giao diện: 1366px và 390px.

## 7. Quyết định

**Của người dùng**: đính kèm trong chat, nhiều định dạng; 6 thao tác (tóm tắt, soát toàn bộ, soát một phần, đối chiếu
thay đổi của luật, đề xuất sửa, hỏi về hợp đồng); người dùng chọn mình là bên nào; từ chối kết luận pháp lý khi kho
thiếu luật; người dùng chọn "chỉ trong phiên" hoặc "lưu lại"; tải về Word hoặc PDF; **mức demo**; **hai chế độ hỏi
(Hỏi tự do / Hỏi với hợp đồng)**; **Think bật được trong chế độ Hỏi với hợp đồng**.

**Của Claude** (người dùng chưa xác nhận riêng):
- Có thêm lựa chọn "Trung lập / tư vấn" ngoài các bên; chưa chọn bên → chạy Trung lập.
- Từ chối chỉ áp dụng cho kết luận pháp lý; nhận xét câu chữ / thương mại vẫn đưa ra, gắn nhãn rõ.
- Mốc pháp lý = ngày ký đọc từ hợp đồng; không có → hỏi người dùng.
- Che PII mọi text gửi LLM; bản tải về mở che.
- Nội dung bắt buộc lấy từ luật trong kho, không cứng hoá checklist.
- Hợp đồng không bao giờ được index vào kho chung; nút "+" tách "Nạp tài liệu vào kho" và "Đính kèm hợp đồng".
- Bản "Chỉ trong phiên" sống tối đa 24h không hoạt động; không ghi đĩa.
- Xuất DOCX bằng python-docx, PDF bằng PyMuPDF (không thêm thư viện).
