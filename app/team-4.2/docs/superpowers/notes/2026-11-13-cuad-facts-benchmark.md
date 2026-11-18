# Đo trích dữ kiện nền trên CUAD (lần 1)

Ngày: 2026-11-13. Mã: `scripts/bench_cuad_facts.py`. Kết quả thô: `cuad-run-2026-11-13/` (`runs.jsonl`, `scores.json`, `meta.json`).
Nơi đo: `rag.contracts.facts.extract_facts` ở commit `52db534` (trích theo lô, bản trước khi sửa lỗi nào dưới đây).

## Thiết lập

- **Dữ liệu:** CUAD v1 (510 hợp đồng tiếng Anh, CC-BY-4.0), tải từ Hugging Face, để ngoài repo.
- **Mẫu:** 30 hợp đồng, 10 mỗi nhóm độ dài (ngắn / vừa / dài), hạt giống 20261113. Trung bình 80,8 đơn vị mỗi hợp đồng.
- **Mô hình:** `gpt-6-luna`, nhiệt độ mặc định của mô hình, không dùng cache. Một lần chạy duy nhất.
- **Chi phí:** 137 lượt gọi LLM, 2,28 triệu ký tự prompt, 834 giây cộng dồn (4 luồng song song).
- **Cách chấm** (chốt trước khi chạy): xem đầu file script. Đáp án CUAD là đoạn trích, không phải giá trị chuẩn hóa.

## Kết quả

| Chỉ số | Kết quả |
|---|---|
| Hợp đồng đọc đủ mọi đơn vị | 30/30, không lô nào lỗi |
| **Các bên**: precision / recall / F1 | 0,953 / 0,783 / **0,860** (123 đúng, 6 thừa, 34 thiếu) |
| **Ngày ký**: đúng khi đáp án đọc được ngày | 13/19 (68%) |
| Ngày ký: bỏ trống khi đáp án có | 8/25 hợp đồng |
| Ngày ký: trả ngày khi đáp án là "không có" | 1/5 |
| **Ngày hiệu lực**: đúng khi đáp án đọc được ngày | 15/15 (100%) |
| Ngày hiệu lực: trả ngày khi đáp án là "không có" | 0/8 |
| **Thời hạn**: câu trích trùng đoạn Expiration / Renewal | 18/22 hợp đồng có đáp án |
| Thời hạn: trả giá trị khi đáp án là "không có" | 3/8 |

## Hạn chế của phép đo (đọc trước khi tin các con số)

- **Recall của các bên bị đánh giá thấp.** Đáp án CUAD lẫn các đoạn định nghĩa như `(together the "Parties" each a "Party")`
  hoặc `"Agent" or "you"`; những mục này hệ thống không trích, và bộ chấm tính là thiếu. Chưa tách riêng phần nhiễu này.
- **Bộ chấm khớp tên bằng quy tắc chuỗi và token**, có thể chấm sai các cặp như `PPG Shanghai` với `PPG Paints Trading (Shanghai)`.
  Chưa kiểm tay.
- **Thời hạn chỉ chấm gián tiếp** (trùng đoạn trích), vì hệ thống không có trường "ngày hết hạn".
- **Mẫu nhỏ, một lần chạy.** 30 hợp đồng; chưa đo độ lệch giữa các lần chạy, nên chênh vài điểm phần trăm không có ý nghĩa.
- **Hợp đồng sửa đổi:** CUAD coi "effective as of …" là ngày ký; hệ thống để trống. Đây là khác biệt quy ước, không hẳn là lỗi.

## Phát hiện (sắp theo mức ảnh hưởng)

1. **Danh sách các bên bị lặp ở hợp đồng nhiều lô.** 88/166 mục (53%) trùng tên với một mục khác; hợp đồng một lô có 0 mục lặp,
   hợp đồng nhiều lô trung bình 3,7 mục lặp trên 6,5 mục. Nguyên nhân: bước gộp chỉ loại trùng theo chuỗi vai trò, mà mỗi lô
   viết vai trò hơi khác nhau ("Công ty", "Bên công ty", "Công ty cung cấp dịch vụ"). Hệ quả: danh sách chọn "Bạn là bên nào"
   hiện nhiều biến thể của cùng một bên. Lỗi do bước trích theo lô, F1 không phát hiện được vì mục lặp vẫn khớp đáp án.
2. **Kết quả không ổn định giữa các lần chạy.** Hợp đồng GRIDIRON: lần chạy thử trả 27/01/2020, lần chạy 30 trả trống, rồi ba
   lần thử lại trả 27/01, 27/01, 26/01. Hợp đồng này có hai chữ ký ghi hai ngày khác nhau, nên mô hình chọn ngẫu nhiên.
   Bảng xác minh có người xác nhận là chỗ chặn được loại sai này, nhưng chưa có lớp nào báo "ngày ký có hai giá trị trong cùng hợp đồng".
3. **Ngày ký sai ở hợp đồng dài:** 2/6 ca sai là sai ngày chữ ký / phụ lục thay vì ngày ở phần mở đầu (Sonos 24/09 so với đáp án 04/09/2014).
4. **Vai trò viết tiếng Việt** (139/166 mục) vì lời nhắc ví dụ bằng tiếng Việt. Không ảnh hưởng hợp đồng tiếng Việt; chỉ là hiện tượng của phép đo trên hợp đồng tiếng Anh.
5. **Có "bên" không phải bên của hợp đồng:** "Landlord / Bên cho thuê" từ một điều khoản thuê trong hợp đồng nhượng quyền, và chuỗi mẫu `[resident of] [corporation organized in]…`.

## Chẩn đoán nguyên nhân (đã kiểm bằng đầu ra thô của LLM từng lô)

Cách làm: chạy lại 10 hợp đồng lỗi, ghi JSON mà LLM trả ở từng lô (sau khi mở che), so với kết quả sau bước gộp.
Script: `diag_offline.py`, `diag_spy.py`, `diag_dates.py` (scratchpad của phiên, không lưu trong repo).

### Các bên: 34 mục "thiếu"

| Nhóm | Số | Bằng chứng |
|---|---|---|
| Đáp án là nhãn định nghĩa, không phải tên (`the "Company"`, `Party A`, `(together the "Parties"…)`) | 17 | Bộ chấm tính là thiếu; hệ thống đúng khi không trích |
| Bí danh của bên đã trích (`HPIL ET`, `SCULPTOR MANAGEMENT`) | 2 | Bộ chấm khớp tên chưa đủ |
| **Bước gộp bỏ bên có cùng vai trò** | 11 | GALERA: LLM trả 12/12 bên → còn 1. VIRGIN 4/4 → 1. HPIL 2/2 → 1. ACCELERATED 2/2 → 1. Mọi bên trong các hợp đồng này có cùng vai trò ("Bên liên doanh", "Bên nộp hồ sơ chung") |
| **Câu trích bị loại vì nhiễu định dạng** | 3 | STAMPS: LLM trả "Mail Boxes Etc. USA, Inc." ở 8/8 lô, câu trích bị loại 8/8 vì văn bản gốc là "Mail -------- Boxes" |
| Chưa chẩn đoán | 1 | QUAKER (GOCL Corporation) |

**Nguyên nhân gốc của lỗi gộp:** `facts.py` loại trùng bằng `_norm(role)`, không theo tên. Hai hệ quả ngược nhau:
- hai bên khác nhau có cùng vai trò → bên sau bị bỏ (11 mục thiếu);
- cùng một bên mà mỗi lô viết vai trò khác ("Company" / "Công ty" / "Bên cung cấp dịch vụ (Company)") → giữ cả (88/166 mục lặp).

Lỗi lặp được khuếch đại vì **mọi lô đều trích lại các bên từ phần mở đầu** (phần mở đầu được gửi kèm làm ngữ cảnh,
và lời nhắc cho phép trích từ ngữ cảnh). STAMPS: 8 lô → 8 lần trích cùng hai bên. Lỗi có từ commit `52db534`; bản trước
(một lượt LLM, không gộp) không có.

Ước tính nếu sửa hai lỗi trên (chưa chạy lại): recall theo đáp án CUAD từ 0,78 lên khoảng 0,87; bỏ 17 nhãn định nghĩa
khỏi đáp án thì khoảng 0,98.

### Ngày ký: 6 ca sai trên 19 ca đáp án đọc được ngày

| Ca | Hệ thống | Nguyên nhân |
|---|---|---|
| Bellring, Merit, Xencor | Ký: trống; **Hiệu lực: đúng ngày đáp án** | CUAD gọi ngày "dated / effective as of" là ngày thỏa thuận; hệ thống xếp vào ngày hiệu lực. Lời nhắc không định nghĩa ngày ký |
| Ashworth | Ký: 16/12/1998 (khối chữ ký); Hiệu lực: đúng ngày đáp án | Như trên; ngày hệ thống trả là ngày ký thật ở chữ ký |
| Sonos | Ký: 24/09/2014 | **Lỗi thật:** ngày của một bản sửa đổi nằm ở 91% văn bản. Lô đầu không trả ngày ký, bước gộp lấy ứng viên đầu tiên có được, bất kể vị trí; bộ tách không nhận bản sửa đổi là một phần riêng |
| Gridiron | Lần 1: 27/01, lần 30-HĐ: trống, chạy lại: 26/01, 27/01, 27/01 | Hai chữ ký ghi hai ngày khác nhau; mô hình chọn ngẫu nhiên, mỗi lô chỉ trả một giá trị nên không sinh mâu thuẫn |

Tính cả ô ngày hiệu lực: ngày đáp án có trong ngày ký **hoặc** ngày hiệu lực ở **18/19** ca. Bộ che PII không che ngày nào
(đã kiểm 11 ca). Không câu trích ngày nào bị loại.

Năm ca đáp án không đọc được ngày đều là mẫu để trống (`______ day of ______, 2015`, `, 2006`) và hệ thống để trống: đúng.
Ca "thừa" PRECIGEN: văn bản ghi rõ "Dated: January 7, 2019", đáp án CUAD bỏ sót.

### Thời hạn

- 4 ca trượt: 2 ca hợp đồng chấm dứt theo sự kiện, hệ thống chọn một điều khoản khác liên quan (BANUESTRA, SUNTRON);
  1 ca câu trích bị loại vì gạch ngang trong văn bản (STAMPS: "shall ------- commence"); 1 ca dao động giữa các lần chạy
  (IPAYMENT: lần chạy lại tìm được, câu trích hợp lệ).
- 3 ca thừa: 2 ca nhầm thời hạn khác thành thời hạn hợp đồng (giấy phép "perpetual" ở GARRETT, thời hạn không cạnh tranh ở
  QUAKER); 1 ca hợp lý mà đáp án bỏ sót (GALERA: "remain in full force … until revoked").

### Ngày hiệu lực

15/15 đúng, 0 ca thừa. Không có lỗi để chẩn đoán.

### Xếp hạng nguyên nhân theo ảnh hưởng

1. Gộp các bên theo vai trò, cộng với việc mọi lô trích lại các bên từ phần mở đầu (lỗi code, do bước trích theo lô).
2. Lời nhắc không định nghĩa ngày ký so với ngày "dated as of" / ngày ở khối chữ ký; bước gộp lấy ứng viên đầu tiên, không ưu tiên vị trí.
3. Kiểm trích dẫn khớp tuyệt đối, không chịu được nhiễu định dạng (H4 trong thiết kế hợp đồng).
4. Dao động giữa các lần chạy: số liệu một lần chạy có sai số chưa đo.
5. Nhầm các loại thời hạn khác với thời hạn hợp đồng.
6. Phía bộ đo: đáp án CUAD lẫn nhãn định nghĩa và bỏ sót vài giá trị; regex ngày không đọc được "14t h day".

## Đánh giá cách sửa (viết trước khi sửa)

Nguyên tắc: không sửa để khớp quy ước của CUAD khi quy ước đó trái với mục đích của hệ thống (ngày ký là mốc tra luật).

### S1. Gộp các bên

| Phương án | Sửa được | Rủi ro / chỗ không sửa được | Chọn |
|---|---|---|---|
| A. Loại trùng theo tên đã chuẩn hóa (bỏ ngoặc, dấu câu, hoa thường) | Mất bên cùng vai trò (GALERA 12→1); lặp do vai trò viết khác | Lô sau gọi bên bằng bí danh ("ISO", "Bên B") vẫn thành mục mới | Có, làm lưới đỡ |
| B. Khớp bí danh: tên mới trùng một bí danh (vai trò, chữ trong ngoặc) của bên đã có → gộp; trùng bí danh của nhiều bên ("SERVICERS") → bỏ | Bí danh dùng làm tên | Bí danh không xuất hiện trong vai trò của bên gốc thì không bắt được | Có, lưới đỡ |
| C. Gửi danh sách bên đã biết cho các lô sau, dặn chỉ trả bên **mới** | Gốc của việc lặp: 8 lô trích lại 8 lần; để LLM tự nhận ra bí danh | Các lô phải chạy tuần tự (hiện đang tuần tự); phụ thuộc LLM tuân lời nhắc → cần A, B đỡ | Có, biện pháp chính |
| D. Lô sau chỉ được trả bên có câu trích nằm trong đơn vị của lô | Chặn trích lại từ ngữ cảnh ngay cả khi LLM không tuân | Không: bên ở phần mở đầu đã do lô đầu trích | Có |
| E. Khớp theo tập con token ("Nantz" ⊂ "Nantz Communications") | Bí danh ngắn | Gộp nhầm hai bên khác nhau (James W. Nantz III và Nantz Communications) | **Không** |

Hệ quả phải xử lý: vai trò là mã của bên ở `verify.party_options`, `set_party` và lời nhắc soát. Khi hai bên khác nhau
có cùng vai trò, vai trò được ghi thành "vai trò — tên" để danh sách "Bạn là bên nào" phân biệt được.

### S2. Ngày ký

| Phương án | Đánh giá | Chọn |
|---|---|---|
| Dạy "effective as of" = ngày ký (theo CUAD) | Tăng điểm CUAD (Bellring, Ashworth, Xencor) nhưng sai với mục đích: câu đó chỉ nói ngày hiệu lực; ngày ký thật có thể khác (Ashworth ký 16/12, hiệu lực 01/06) | **Không** |
| Định nghĩa ngày ký trong lời nhắc: ngày ở phần mở đầu ("Hôm nay, ngày…", "dated / made / entered into as of") hoặc ngày cạnh chữ ký; không lấy ngày của phụ lục / bản sửa đổi | Sửa Merit ("dated as of"), giảm lỗi kiểu Sonos; không bảo đảm vì bộ tách không nhận bản sửa đổi là phần riêng | Có |
| Cho phép trả **nhiều** ngày ký; khác nhau → trạng thái "mâu thuẫn", người dùng chọn | Sửa Gridiron (hai chữ ký hai ngày) đúng theo thiết kế xác minh; không tự đặt ngày ký khi có hơn một ứng viên | Có |
| Ưu tiên ứng viên theo vị trí (đầu văn bản) | Sẽ chọn sai khi ngày ký thật ở chữ ký | Không; để người dùng chọn |

Dự kiến sau khi sửa: Bellring, Ashworth, Xencor vẫn lệch với CUAD (khác quy ước, có chủ ý). Sonos còn rủi ro.

### S3. Kiểm trích dẫn

Bỏ các chuỗi ký tự điền chỗ trống (≥ 2 ký tự `- _ = * ~`, ≥ 3 dấu chấm, `…`) ở cả văn bản và câu trích trước khi so.
- Không làm yếu việc chống bịa: mọi chữ và số vẫn phải khớp liền nhau. Điền vào chỗ trống ("ngày 5 tháng 3" cho
  "ngày .... tháng ....") vẫn bị loại vì chữ số không có trong văn bản.
- "…" LLM dùng để rút gọn câu trích vẫn bị loại như cũ (phần còn lại không liền nhau trong văn bản).
- Áp dụng cho mọi nơi dùng `quote_ok` (dữ kiện, phát hiện, câu hỏi, đề xuất sửa). Chưa phải khớp chịu lỗi OCR (H4).

### S4. Thời hạn

Thêm định nghĩa vào lời nhắc: thời hạn của chính hợp đồng, không phải của một nghĩa vụ, bảo hành, giấy phép, thử việc
hay cam kết không cạnh tranh. Rủi ro thấp; hiệu quả chỉ biết sau khi đo.

### S6, S7. Phát hiện thêm khi kiểm lại hợp đồng lao động tiếng Việt (ép 2 lô, 3 lần chạy)

- **S6. Câu trích ghép nhiều dòng.** LLM ghép khoản 1 và khoản 3 của Điều 5 (bỏ khoản 2) thành một câu trích; bộ kiểm đòi
  liền mạch nên loại giá trị "Mức lương" (2/6 lượt lô trong 3 lần chạy). Sửa: khi câu trích không khớp liền mạch, tách theo
  dòng; chấp nhận nếu **mọi** đoạn (≥ 8 ký tự) có nguyên văn trong nguồn và **đúng thứ tự**. Đây là quy định §7.3 của thiết kế
  hợp đồng gốc (trích dẫn nhiều đoạn), chưa được làm. Không áp cho "đoạn cũ" của đề xuất sửa (phải liền mạch để thay thế).
- **S7. Giá trị trích từ đơn vị tham khảo.** Lô 1 trích "Mức lương" từ Điều 5 (được gửi kèm vì Điều 4 dẫn chiếu tới); lô 2
  trích lại từ chính Điều 5 với cách diễn đạt khác → hai ứng viên chữ khác nhau cho cùng một giá trị, thành "mâu thuẫn" giả.
  Sửa: mọi giá trị chỉ được nhận khi câu trích nằm trong một đơn vị **của lô đó**; ngữ cảnh và tham khảo chỉ để hiểu.
  Mỗi đơn vị thuộc đúng một lô nên không mất giá trị nào. Mâu thuẫn còn lại là mâu thuẫn giữa hai điều khoản khác nhau
  (vd. ngày hiệu lực: "từ ngày 01/4/2025" ở Điều 3 và "có hiệu lực từ ngày ký" ở Điều 11), đúng thứ cần người dùng chọn.

### S5. Phép đo

- Chạy bản đã sửa **3 lần** để có khoảng dao động. Bản gốc chỉ có một lần chạy, nên chỉ kết luận ở các chỉ số chênh lớn hơn dao động.
- Thêm chỉ số: tỉ lệ mục bên lặp tên; ngày đáp án có ở ô ngày ký **hoặc** ô ngày hiệu lực.
- Thêm chỉ số phụ "các bên, chỉ tính tên thực thể" (bỏ nhãn định nghĩa khỏi đáp án). Bộ lọc này viết sau khi đã xem kết quả,
  nên chỉ là chỉ số phụ; chỉ số gốc giữ nguyên để so.
- Kiểm lại hợp đồng lao động tiếng Việt sau khi đổi lời nhắc (lời nhắc dùng chung).

## Kết quả sau khi sửa (3 lần chạy, cùng 30 hợp đồng)

Kết quả thô: `cuad-run-2026-11-13-after/{a,b,c}/`. Lần 1 được chấm lại bằng bộ chấm mới (`cuad-run-2026-11-13/scores.json`).
Bộ chấm mới tính tên gọi tắt (`aliases`) như một phần của vai trò; lần 1 không có trường này nên chỉ đổi nhẹ (F1 0,860 → 0,864).

| Chỉ số | Trước (1 lần) | Sau (a / b / c) |
|---|---|---|
| Các bên: precision | 0,954 | 1,0 / 1,0 / 1,0 |
| Các bên: recall | 0,790 | 0,860 / 0,873 / 0,873 |
| Các bên: F1 | 0,864 | 0,925 / 0,932 / 0,932 |
| Các bên: thiếu / thừa | 33 / 6 | 22 / 0, 20 / 0, 20 / 0 |
| Recall trên tên thực thể (chỉ số phụ) | 0,866 | 0,941 / 0,941 / 0,958 |
| Mục bên lặp tên | 88 / 166 | 0 / 85 ở cả ba lần |
| Ngày ký: một ứng viên và đúng | 13 / 19 | 13 / 13 / 14 |
| Ngày ký: đáp án nằm trong các ứng viên | 13 / 19 | 15 / 15 / 16 |
| Ngày ký: hợp đồng báo mâu thuẫn | 0 | 3 / 3 / 3 |
| Đáp án khớp ngày ký hoặc ngày hiệu lực | 18 / 19 | 19 / 19 / 19 |
| Ngày hiệu lực đúng | 15 / 15 | 14 / 14 / 14 |
| Thời hạn: trùng đáp án | 18 / 22 | 19 / 18 / 16 |
| Thời hạn: trả giá trị khi đáp án "không có" | 3 / 8 | 1 / 1 / 1 |
| Thời gian cộng dồn | 834 s | 592 / 603 / 610 s |

Đọc kết quả:
- **Lỗi lặp bên và mất bên cùng vai trò đã hết** (GALERA 12/12, VIRGIN 4/4). Các bên còn "thiếu" là tên viết tắt mà hệ thống
  không gắn được vào bên (CPDC, IAC, EFS, "HPIL ET"…): bên đó vẫn có trong danh sách dưới tên đầy đủ.
- **Ngày ký: số ca tự đặt đúng không đổi (13–14/19), và đó là chủ ý.** Phần tăng nằm ở chỗ hệ thống không còn im lặng chọn
  bừa: Gridiron, Intricon, Xencor giờ báo mâu thuẫn kèm đủ các ngày để người dùng chọn. Bellring, Ashworth vẫn lệch CUAD vì
  khác quy ước ("effective as of").
- **Còn sai thật: Sonos.** Cả ba lần trả 01/10/2017 (ngày trong một bản sửa đổi đính kèm) làm ứng viên duy nhất, nên sẽ được
  điền sẵn là ngày ký. Lời nhắc "không lấy ngày của bản sửa đổi" không đủ; cần bộ tách nhận bản sửa đổi / văn bản đính kèm
  là phần riêng. Chưa sửa.
- **Ngày hiệu lực 15 → 14:** HPIL — hợp đồng ghi "signed this 5th day of January, 2015"; hệ thống giờ xếp vào ngày ký (đúng
  theo định nghĩa mới), CUAD ghi cả hai ô. Không phải lỗi mới về nội dung.
- **Thời hạn dao động 16–19/22 giữa ba lần chạy:** không kết luận được là tốt lên hay xấu đi. Số ca thừa giảm 3 → 1 ở cả ba lần.
- **Dao động giữa ba lần chạy sau nhỏ** ở các bên và ngày (lệch tối đa 2 mục), lớn hơn ở thời hạn. Lần chạy trước khi sửa chỉ
  có một, nên các chênh lệch nhỏ (ngày hiệu lực, thời hạn) không có ý nghĩa thống kê.
- Sau ba lần chạy có sửa thêm một chi tiết: chú thích trong ngoặc không có dấu nháy như "(USA)" không còn bị nhận là tên gọi
  tắt (có test). Thay đổi này không được chạy lại trên CUAD.

## Chưa đo

Quan hệ giữa các thực thể (nghĩa vụ, quyền, điều kiện, hệ quả) và các mục riêng của hợp đồng lao động: CUAD không có nhãn cho hai thứ này.
