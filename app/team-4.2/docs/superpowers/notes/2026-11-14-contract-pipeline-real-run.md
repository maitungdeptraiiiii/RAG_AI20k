# Một lần chạy thật của pipeline hợp đồng trên hồ sơ lao động, từng bước một

Ngày chạy: 2026-11-14. Đi kèm `2026-11-14-contract-pipeline-walkthrough.md`: file kia giải thích từng bước làm gì, file
này cho thấy **dữ liệu thật** đi qua từng bước. Số thứ tự bước [1]…[18] trùng với file kia.

## 1. Văn bản đầu vào

### Nguồn

Một bộ hồ sơ lao động gồm **ba văn bản**, nguyên văn từ các mẫu công khai trên Thư Viện Pháp Luật:

| Phần | Mẫu gốc | Nội dung |
|---|---|---|
| Hợp đồng chính | [HỢP ĐỒNG LAO ĐỘNG](https://thuvienphapluat.vn/hopdong/36918/HOP-DONG-LAO-DONG) (cập nhật 26/04/2025, "Căn cứ Bộ luật Lao động 2019") | 7 Điều: công việc và thời hạn, lương, thời giờ làm việc và bảo hiểm, đào tạo và nghĩa vụ người lao động, quyền và nghĩa vụ công ty, thỏa thuận khác, thi hành |
| Phụ lục 1 | [PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG (về cam kết bảo mật thông tin và trách nhiệm vật chất)](https://thuvienphapluat.vn/hopdong/682/PHU-LUC-HOP-DONG-LAO-DONG-VE-CAM-KET-BAO-MAT-THONG-TIN-VA-TRACH-NHIEM-VAT-CHAT) | 3 Điều: thông tin bảo mật, cam kết của người lao động, điều khoản chung |
| Phụ lục 2 | [PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG](https://thuvienphapluat.vn/hopdong/146/PHU-LUC-HOP-DONG-LAO-DONG) | Mẫu phụ lục thay đổi nội dung hợp đồng, dùng để điều chỉnh lương |

Các mẫu là **mẫu trống**. Hợp đồng lao động thật đã điền thông tin không được công bố vì chứa dữ liệu cá nhân. Để có
dữ kiện cho pipeline đọc, tôi đã:

- **Giữ nguyên văn mọi điều khoản và tiêu đề**, kể cả lỗi chính tả của mẫu ("Điạ chỉ", "cuả", "qui định") và các điều
  khoản có vấn đề (hoàn trả 100% phí đào tạo, ràng buộc bảo mật 5 năm sau khi nghỉ, "không khiếu nại về sau").
- **Chỉ điền vào chỗ trống** bằng dữ liệu giả lập: Công ty TNHH Giải pháp số Minh An; người lao động Nguyễn Thị Thu Hà,
  kế toán; CCCD, số điện thoại, mã số thuế, số tài khoản đều giả. Ký ngày 02/01/2025, hợp đồng xác định thời hạn 12
  tháng, lương 15.000.000 đồng/tháng.
- Điền Điều 6 "Những thỏa thuận khác" (mẫu để trống) bằng một thỏa thuận thường gặp: thử việc 02 tháng, hưởng 85% lương.
- Phụ lục 2 ngày 01/07/2025: sửa Điều 2, tăng lương lên 17.000.000 đồng/tháng, thêm phụ cấp trách nhiệm 500.000 đồng.

### Định dạng

Ghép ba văn bản thành một file Word (Times New Roman 13, mỗi văn bản bắt đầu trang mới), rồi để **Microsoft Word xuất
PDF**, giống cách một hợp đồng thật được tạo ra. Kết quả: **PDF 10 trang, 13.530 ký tự**. Chữ đọc lại từ PDF trùng khớp
hoàn toàn với bản gốc.

Các file: `data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.{txt,docx,pdf}`.

(Hai cách tạo PDF trực tiếp bằng PyMuPDF đã bị bỏ: chúng biến dấu "-" thành ký tự gạch mềm U+00AD khi đọc lại, tạo lỗi
giả không có ở file thật.)

## 2. Thiết lập

| | |
|---|---|
| **Đường chạy** | Đúng đường của ứng dụng: script nạp `ui/server.py` rồi gọi `contracts_api.create`, `set_facts`, `run`, `chat_answer` |
| **Môi trường** | `.venv` ở gốc repo (như README), có `typesafe-sdk` (reranker Jev) và `neo4j`. Neo4j chạy bằng `docker/neo4j-compose.yml` |
| **LLM** | Mô hình trong `.env` (`gpt-6-luna`), một lần chạy |
| **Kho luật** | Snapshot `s20261112174549-ca73d5`, BM25 + Dense (Jina) + rerank (Jev), lọc hiệu lực theo ngày ký |
| **Script** | `scripts/trace_contract_pipeline.py <file> <json ra> "<câu hỏi>"` |
| **Dữ liệu thô** | `contract-trace-2026-11-14/trace_hdld_tvpl.json` (mọi payload gửi LLM, câu trả lời thô, kết quả tra luật) |

Trong lúc chạy, API embedding Jina trả 429 (giới hạn tần suất) 5 lần. Mỗi lần hệ thống chờ 3 s rồi thử lại thành công,
nên kết quả không bị ảnh hưởng, chỉ chậm hơn.

## 3. Tổng quan

| Giai đoạn | Thời gian | Lời gọi LLM | Tra luật |
|---|---|---|---|
| Tạo [1]–[9] | 21,2 s | 2 (trích dữ kiện, 2 lô) | 0 |
| Xác minh [10]–[12] | < 1 s | 0 | 0 |
| Soát [13] | 147,4 s | 3 (`FIND` × 2 lô, `VERIFY`) | 9 |
| Đề xuất sửa [14] | 32,5 s | 1 | 0 |
| Thay đổi luật [15] | 2,3 s | 0 | 0 |
| Tóm tắt [16] | 14,5 s | 1 | 0 |
| Hỏi đáp [17] | khoảng 14 s | 2 (`ANSWER`, `VERIFY`) | 1 |
| **Tổng** | khoảng 4 phút | **9** | **10** |

---

## 4. Giai đoạn 1: Tạo hợp đồng

### [1]–[2] Đọc PDF

PyMuPDF đọc chữ từng trang. Cả 10 trang đều có lớp chữ tốt nên **không trang nào phải OCR**.

| Trang | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Ký tự | 1.177 | 1.791 | 1.963 | 2.009 | **111** | 1.637 | 2.234 | 790 | 1.460 | **340** |
| Nội dung | HĐ: mở đầu | HĐ: Đ1–Đ2 | HĐ: Đ3 | HĐ: Đ4–Đ7 | HĐ: chữ ký | PL1: mở đầu | PL1: Đ1–Đ2 | PL1: Đ3 | PL2 | PL2: chữ ký |

### [3]–[4] Gộp văn bản, nhận phần

Bộ tách phần nhận đúng **hai phụ lục** với tiêu đề nguyên văn của mẫu:

```
p0  main      ""                               start = 0
p1  appendix  "PHỤ LỤC 1- HỢP ĐỒNG LAO ĐỘNG"   start = 7124,  number = 1
p2  appendix  "PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG"      start = 11825, number = null  → hiển thị "Phụ lục 2" theo thứ tự
```

**Lỗi ranh giới phần.** Mỗi phần bắt đầu **từ dòng tiêu đề "PHỤ LỤC"**. Vì vậy những dòng nằm *trên* tiêu đề (quốc hiệu,
và với Phụ lục 2 là **dòng ngày "Hà Nội, ngày 01 tháng 07 năm 2025"**) bị gắn vào cuối phần trước:

```
Cuối Điều 7 hợp đồng chính (p0.d7):
  …Nguyễn Thị Thu Hà Phạm Quốc Khánh
  CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM          ← quốc hiệu của Phụ lục 1
  Độc lập – Tự do – Hạnh phúc

Cuối Điều 3 Phụ lục 1 (p1.d3):
  …Nguyễn Thị Thu Hà Phạm Quốc Khánh
  CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM          ← quốc hiệu của Phụ lục 2
  Độc lập - Tự do - Hạnh phúc
  Hà Nội, ngày 01 tháng 07 năm 2025           ← NGÀY KÝ CỦA PHỤ LỤC 2
```

Hậu quả thấy ở các bước sau: Phụ lục 2 "không có ngày ký" (bước 6, 13). Bộ tách cần lùi điểm bắt đầu phần lên các dòng
quốc hiệu và ngày tháng đứng ngay trên tiêu đề.

### [5] Tách cấu trúc

**Đơn vị:** 15 cấp cao nhất, 25 tổng cộng (12 Điều, 10 khoản, 3 phần mở đầu).

| Phần | Kiểu đánh số | Đơn vị cấp cao nhất |
|---|---|---|
| Hợp đồng chính | `dieu` | Phần mở đầu (996 ký tự), Điều 1–7 (Điều 4 dài nhất, 1.926 ký tự) |
| Phụ lục 1 | `dieu` | Phần mở đầu, Điều 1–3 ("Điều 1 : TÀI LIỆU/THÔNG TIN BẢO MẬT"…) |
| Phụ lục 2 | `numeric` | Phần mở đầu, **Mục 1** ("1. Nội dung thay đổi"), **Mục 2** ("2. Thời gian thực hiện") |

**Giá trị:** 32. Đáng chú ý:

| Đơn vị | Loại | Nguyên văn | Ghi chú |
|---|---|---|---|
| Phần mở đầu | date | ngày 02 tháng 01 năm 2025 | ngày ký |
| Phần mở đầu | date | 14/06/1996, 20/04/2021 | ngày sinh, ngày cấp CCCD (vẫn thành giá trị) |
| Điều 1 | duration / date | 12 tháng; 02/01/2025; 01/01/2026 | thời hạn |
| Điều 2 | money | 15.000.000 đồng; 1.000.000 đồng | lương, phụ cấp |
| Điều 3 | duration | 8 giờ; 48 giờ; 12 ngày… | 7 giá trị thời lượng |
| Điều 4 | percent | 100% | hoàn trả phí đào tạo |
| Điều 6 | duration / percent | 02 tháng; 85% | thử việc |
| Phụ lục 1, Điều 3 | duration | 5 năm | ràng buộc bảo mật sau khi nghỉ |
| Phụ lục 1, Điều 3 | **date** | **ngày 01 tháng 07 năm 2025** | **ngày của Phụ lục 2, gắn nhầm phần** |
| Phụ lục 2, Mục 1 | money | 15.000.000; 17.000.000; 500.000 đồng | lương cũ, mới, phụ cấp |

**Dẫn chiếu:** 4.

```
Điều 6               ─"Điều 2"─────► Điều 2                      đúng
Điều 6               ─"Phụ lục 01"─► Phụ lục 1 — Phần mở đầu     đúng (dẫn chiếu sang phụ lục)
Phụ lục 1 — Điều 2   ─"Điều 1"─────► Phụ lục 1 — Điều 1          đúng ("Điều 1 Phụ lục này")
Phụ lục 2 — Mục 1    ─"Điều 2"─────► Phụ lục 2 — Mục 2           SAI
```
Câu gốc là "Sửa đổi **Điều 2 Hợp đồng lao động** về lương căn bản", tức phải trỏ về Điều 2 hợp đồng chính. Bộ dẫn chiếu
hiểu "Điều 2" theo phần đang đứng, và lại khớp nó với "Mục 2" của Phụ lục 2. Đây là lỗi thật.

**Báo cáo chất lượng:** không đứt số, tỉ lệ văn bản không đánh số 0,23. Có hai cảnh báo:
```
Trang 5 có thể chứa nội dung chưa đọc được
Trang 10 có thể chứa nội dung chưa đọc được
```
Cả hai đều là **báo động giả**: trang 5 và 10 chỉ có khối chữ ký nên ít chữ (dưới 25% trung vị). Quy tắc "trang mỏng"
không phân biệt trang chữ ký với trang bị mất chữ.

### [6] Trích dữ kiện nền 🤖

**6a. Chia lô.** Hợp đồng dài 13.530 ký tự, vượt ngân sách 12.000, nên có **2 lô**:

| Lô | Đơn vị | Ký tự | `context` | `references` |
|---|---|---|---|---|
| 0 | Hợp đồng chính (8 đơn vị) + Phụ lục 1 (4 đơn vị) | 11.812 | (không) | (không) |
| 1 | Phụ lục 2 (3 đơn vị) | 1.703 | Phần mở đầu hợp đồng chính (996 ký tự) | (không) |

Lô 1 được gửi kèm phần mở đầu hợp đồng chính **chỉ để hiểu** các bên là ai.

**6b. Gọi LLM, tuần tự.**

*Che PII.* Payload gửi đi đã che CCCD (`[HD_CCCD_1]`), điện thoại (`[HD_PHONE_1]`, `[HD_PHONE_3]` cho số fax), mã số
thuế (`[HD_MST_1]`), số tài khoản (`[HD_BANK_1]`). **Tên người không bị che ở bất kỳ đâu**:

```
Đại diện: Phạm Quốc Khánh Chức vụ: Giám đốc Quốc tịch: Việt Nam
Bên B : Người lao động
ÔNG / BÀ : Nguyễn Thị Thu Hà
Ngày sinh: 14/06/1996
```
Kiểm trên cả 9 lời gọi: tên hai người có mặt trong **7/9 payload** (trừ hai lời gọi `VERIFY`). Ngày sinh, địa chỉ cũng
không bị che. Bộ che PII chỉ nhận tên đứng sau "Họ và tên:" (thấy ở lần chạy hợp đồng thuê nhà), còn mẫu lao động dùng
"ÔNG / BÀ :", "Đại diện:", "Bà:".

*Lô 0* (13,9 s) trả về đúng hết:

```json
{"type": "Hợp đồng lao động",
 "parties": [{"name": "Công ty TNHH Giải pháp số Minh An", "role": "Người sử dụng lao động", "unit": "p0.pre"},
             {"name": "Nguyễn Thị Thu Hà", "role": "Người lao động", "unit": "p0.pre", "quote": "ÔNG / BÀ : Nguyễn Thị Thu Hà"}],
 "sign_date": {"value": "2025-01-02", "unit": "p0.pre", "quote": "Hôm nay, ngày 02 tháng 01 năm 2025"},
 "effective_date": {"value": "2025-01-02", "unit": "p0.d7", "quote": "có hiệu lực kể từ ngày ký"},
 "term": {"value": "12 tháng (từ 02/01/2025 đến 01/01/2026)", "unit": "p0.d1"},
 "fields": {"labor_kind": "Xác định thời hạn", "job_title": "Nhân viên kế toán tổng hợp",
            "workplace": "Tầng 5, số 18 phố Trần Thái Tông, …, Hà Nội", "start_date": "2025-01-02",
            "salary": "15.000.000 đồng/tháng lương căn bản; phụ cấp 1.000.000 đồng/tháng",
            "probation_period": "02 tháng", "probation_salary": "85% mức lương căn bản quy định tại Điều 2",
            "working_hours": "8 giờ/ngày, 48 giờ/tuần"}}
```
LLM **không** lấy ngày "01 tháng 07 năm 2025" (nằm nhầm trong Phụ lục 1, Điều 3) làm ngày ký. Lời nhắc "không lấy ngày
của phụ lục" hoạt động ở ca này.

*Lô 1* (6,0 s) nhận `known_parties` = hai bên của lô 0, và **không trả lại bên nào** (đúng: Phụ lục 2 nhắc lại cùng hai
bên). Kết quả:
```json
{"type": "Phụ lục hợp đồng lao động", "parties": [], "sign_date": null,
 "effective_date": {"value": "2025-07-01", "unit": "p2.d2", "quote": "có hiệu lực từ ngày 01 tháng 07 năm 2025"},
 "fields": {"salary": {"value": "Lương căn bản 17.000.000 đồng/tháng; phụ cấp trách nhiệm 500.000 đồng/tháng", "unit": "p2.d1"}}}
```
`sign_date = null` vì dòng ngày của Phụ lục 2 đã bị gắn sang Phụ lục 1 (xem bước 4).

**6c–6e. Kiểm và gộp.** Mọi trích dẫn khớp. Loại hợp đồng lấy theo lô 0 ("Hợp đồng lao động"), bỏ "Phụ lục hợp đồng lao
động" của lô 1. Ngày ký có 1 ứng viên nên `sign_date = 2025-01-02` được đặt tự động.

Hai trường có **2 ứng viên**, vì phụ lục sửa hợp đồng chính:

| Trường | Ứng viên từ hợp đồng chính | Ứng viên từ Phụ lục 2 |
|---|---|---|
| Ngày có hiệu lực | 2025-01-02 (Điều 7) | 2025-07-01 (Mục 2) |
| Mức lương | 15.000.000 + phụ cấp 1.000.000 (Điều 2) | 17.000.000 + phụ cấp trách nhiệm 500.000 (Mục 1) |

Đây không phải mâu thuẫn mà là **sửa đổi theo thời gian**: lương 15 triệu từ 02/01/2025, 17 triệu từ 01/07/2025. Hệ
thống chưa có khái niệm sửa đổi (`AMEND_UNIT`, phiên bản đơn vị, spec §7.7 chưa làm), nên coi đây là mâu thuẫn và đẩy
cho người dùng chọn **một** giá trị.

Kết quả: `coverage = 15/15`, `warnings = []`.

### [7] Nhật ký sau khi tạo

```
SET_LAYOUT  (3 phần)                     rule  auto_accepted
SET_FIELD   type = "Hợp đồng lao động"   llm   auto_accepted
SET_FIELD   sign_date = "2025-01-02"     llm   auto_accepted
```

### [8] Đồ thị

`build_id = b9e2d039629ed`, **61 nút, 74 cạnh, 0 lỗi kiểm, đã công bố lên Neo4j** (`published = true`).

| Nút | Số | | Cạnh | Số |
|---|---|---|---|---|
| Contract | 1 | | HAS_PART | 3 |
| Part | 3 | | HAS_UNIT | 25 |
| Unit | 25 | | CHILD_OF | 10 |
| Value | 32 | | REFERS_TO | 4 (1 sai, xem bước 5) |
| | | | HAS_VALUE | 32 |

Mọi nút `Unit` có `valid_from = 2025-01-02`, kể cả các đơn vị của Phụ lục 2 vốn chỉ có hiệu lực từ 2025-07-01.

---

## 5. Giai đoạn 2: Xác minh

### [10] Bảng xác minh

`catalog_type = "labor"`, nên bảng có 6 trường chung + 9 trường lao động:

| Trường | Bắt buộc | Trạng thái | Máy đọc |
|---|---|---|---|
| Bạn là bên nào | ✔ | missing | (Người sử dụng lao động / Người lao động / Trung lập) |
| Ngày ký | ✔ | found | 2025-01-02 |
| Loại hợp đồng | ✔ | found | Hợp đồng lao động |
| Ngày có hiệu lực | | **conflict** | 2025-01-02 / 2025-07-01 |
| Thời hạn hợp đồng | | found | 12 tháng (từ 02/01/2025 đến 01/01/2026) |
| Giá trị hợp đồng | | missing | |
| Loại hợp đồng lao động | ✔ | found | Xác định thời hạn |
| Chức danh / công việc | ✔ | found | Nhân viên kế toán tổng hợp |
| Nơi làm việc | ✔ | found | Tầng 5, số 18 phố Trần Thái Tông… |
| Ngày bắt đầu làm việc | | found | 2025-01-02 |
| Mức lương | | **conflict** | 15 triệu + 1 triệu / 17 triệu + 500 nghìn |
| Nhóm trình độ công việc | | missing | |
| Thời gian thử việc | | found | 02 tháng |
| Lương thử việc | | found | 85% mức lương căn bản |
| Thời giờ làm việc | | found | 8 giờ/ngày, 48 giờ/tuần |

### Thử soát trước khi xác minh: bị chặn

```
NeedsVerification: Hãy xác minh thông tin trước khi soát: Bạn là bên nào, Ngày ký, Loại hợp đồng,
                   Loại hợp đồng lao động, Chức danh / công việc, Nơi làm việc
```

### [11]–[12] Xác nhận

Script đóng vai người lao động: chọn "Người lao động", xác nhận mọi trường `found`. Hai trường mâu thuẫn (ngày hiệu lực,
mức lương) không bắt buộc nên **để nguyên**. Nhóm trình độ không bắt buộc nên để trống.

Kết quả: `complete = true`. Đồ thị dựng lại với `build_id = b3bfce74d70bf` và công bố lại lên Neo4j.

Hệ quả của việc để trống: "Mức lương" và "Nhóm trình độ công việc" **không** nằm trong `known_facts` gửi cho bước soát.

---

## 6. Giai đoạn 3: Dùng hợp đồng

### [13] Soát

**13c. `FIND` 🤖, 2 lô.** Payload có `party = "Người lao động"` và các dữ kiện đã xác minh.

*Lô 0* (59,9 s): **13 phát hiện** và 1 câu hỏi cho người dùng:
> Vị trí Nhân viên kế toán tổng hợp này yêu cầu trình độ chuyên môn, kỹ thuật nào theo mô tả công việc hoặc tiêu chuẩn
> tuyển dụng của Công ty? [Từ cao đẳng trở lên / Trung cấp, công nhân kỹ thuật hoặc nhân viên nghiệp vụ / Nhóm công việc
> khác / Không biết]

Đây đúng là hành vi thiết kế: thời gian thử việc tối đa phụ thuộc trình độ công việc (BLLĐ Điều 25), mà hợp đồng không
ghi, nên LLM hỏi thay vì đoán.

*Lô 1* (20,5 s): 1 phát hiện và 1 câu hỏi "Hai bên thực tế ký Phụ lục 2 vào thời điểm nào?". LLM thấy Phụ lục 2 chỉ có
"Hôm nay, tại Công ty…" mà không có ngày. Đây là **hậu quả trực tiếp của lỗi ranh giới phần** ở bước 4: dòng ngày của
Phụ lục 2 nằm trong lô 0, ở cuối Phụ lục 1.

**13d. Kiểm phát hiện ⚙️.** 13/14 trích dẫn khớp. **F8 bị loại trích dẫn**: LLM ghi đơn vị là Điều 4 hợp đồng chính,
nhưng câu trích ("Trong trường hợp vi phạm cam kết này… sa thải…") thuộc **Phụ lục 1, Điều 2**. Bước soát không tự sửa
đơn vị, nên F8 thành "Nghi vấn trái luật — chưa kết luận" với lời từ chối "Trích dẫn không khớp hợp đồng". F8 cũng
trùng nội dung với F12 (cùng câu, gắn đúng đơn vị).

**13e. Tra luật 🔎.** 9 lần, mốc **2025-01-02**. Ví dụ:

| Câu tra (rút gọn) | Ba điều luật trả về |
|---|---|
| Thời gian thử việc tối đa cho công việc kế toán… | BLLĐ 2019 Đ25 *Thời gian thử việc*; BLLĐ Đ61 *Học nghề, tập nghề*; NĐ 12/2022 Đ10 *Vi phạm quy định về thử việc* |
| Phạm vi, điều kiện hoàn trả chi phí đào tạo khi nghỉ… | BLLĐ Đ40 *Nghĩa vụ khi đơn phương chấm dứt trái pháp luật*; BLLĐ Đ62 *Hợp đồng đào tạo nghề*; TT 10/2020 Đ3 |
| Vi phạm bảo mật nào là căn cứ sa thải… | BLLĐ Đ125 *Áp dụng hình thức sa thải*; NĐ 145/2020 Đ89 *(người giúp việc gia đình, lạc đề)*; BLLĐ Đ122 *Trình tự xử lý kỷ luật* |
| Hợp đồng phải ghi mức đóng bảo hiểm nào… | Luật BHYT 2008 Đ13; Luật BHXH 2014 Đ86; NĐ 143/2018 Đ12 (đều hiệu lực tới 2025-07-01, đúng tại ngày ký) |
| Ngày nghỉ bù khi lễ trùng ngày nghỉ hằng tuần… | BLLĐ Đ111 *Nghỉ hằng tuần*; NĐ 145/2020 Đ55; Bộ luật Hàng hải Đ64 *(thuyền viên, lạc đề)* |

Lọc thời gian đúng: Luật BHXH 2014 và Luật BHYT 2008 được chọn vì còn hiệu lực ngày 02/01/2025, dù đã hết hiệu lực từ
01/07/2025. Có reranker, phần lớn ứng viên đúng chủ đề; vẫn còn vài ứng viên lạc đề ở vị trí thứ 2–3.

Nhiều điều của BLLĐ 2019 trong kho có `status = needs_review` (kho chưa duyệt xong phiên bản). Trạng thái này **không**
hạ kết luận: `_legal_status` chỉ hạ khi `conflicted`.

**13f. `VERIFY` 🤖.** LLM giữ 0–3 căn cứ cho mỗi phát hiện. Các ứng viên lạc đề ở bảng trên đều bị loại.

**13g. Báo cáo** (`coverage = 15/15`, 2 lô, 2 cảnh báo trang mỏng, 2 câu hỏi), sắp bất lợi cho người lao động lên trước:

| # | Đơn vị | Nhóm hiển thị | Mức | Trạng thái | Căn cứ / ghi chú |
|---|---|---|---|---|---|
| F8 | Điều 4 (sai, đúng là PL1 Đ2) | Nghi vấn trái luật — chưa kết luận | critical | cannot_conclude | "Trích dẫn không khớp hợp đồng" |
| F12 | PL1 — Điều 2 | Trái luật | critical | concluded | BLLĐ Đ125, Đ122 (sa thải khi chưa đánh giá được thiệt hại) |
| F1 | Điều 1 | Bất lợi | major | not_legal | "Hoàn thành những công việc khác tùy thuộc theo yêu cầu kinh doanh" |
| F3 | Điều 3 | Trái luật | major | concluded | BLLĐ Đ111 (nghỉ bù "ngày trước hoặc ngày kế tiếp tùy Ban lãnh đạo") |
| F4 | Điều 3 | Nghi vấn thiếu nội dung bắt buộc — chưa kết luận | major | cannot_conclude | **"Kho chưa có Bộ luật Lao động 2019"** (sai, xem dưới) |
| F6 | Điều 4 | Thiếu nội dung bắt buộc | major | concluded | BLLĐ Đ62 (đào tạo phải có hợp đồng đào tạo riêng) |
| F7 | Điều 4 | Bất lợi | major | concluded | BLLĐ Đ62, Đ40 (hoàn trả 100% phí đào tạo) |
| F9 | Điều 6 | **Trái luật? — tùy trường hợp, cần thêm thông tin** | major | concluded | BLLĐ Đ25, NĐ 12/2022 Đ10; kèm 3 trường hợp và câu hỏi về trình độ |
| F10 | Điều 6 | Bất lợi | major | concluded | BLLĐ Đ24, Đ26, Đ27 (thử việc) |
| F11 | PL1 — Điều 1 | Bất lợi | major | not_legal | Danh mục bảo mật "có thể được bổ sung vào bất kỳ lúc nào" |
| F13 | PL1 — Điều 3 | Bất lợi | major | concluded | BLTTDS Đ9 ("không khiếu nại về sau") |
| F2 | Điều 2 | Mơ hồ | minor | not_legal | "Các khoản bổ sung khác: tùy quy định cụ thể của Công ty" |
| F5 | Điều 3 | Mơ hồ | minor | concluded | NĐ 145/2020 Đ65, BLLĐ Đ113 (phép năm khi thâm niên dưới 12 tháng) |
| F14 | PL2 — Phần mở đầu | Mơ hồ? — tùy trường hợp | minor | not_legal | "Phụ lục không ghi ngày ký" (sai, do lỗi ranh giới phần) |

F9 hiển thị kết luận theo từng trường hợp:
```
Nếu công việc yêu cầu trình độ từ cao đẳng trở lên → tối đa 60 ngày; 02 tháng có thể phù hợp nếu không vượt giới hạn này.
Nếu công việc yêu cầu trình độ trung cấp, công nhân kỹ thuật, nhân viên nghiệp vụ → tối đa 30 ngày; 02 tháng vượt giới hạn.
```

**Lời từ chối của F4 sai sự thật.** "Kho chưa có Bộ luật Lao động 2019", trong khi chính báo cáo này dùng "Bộ Luật lao
động số 45/2019/QH14" làm căn cứ cho 7 phát hiện khác. Nguyên nhân (`review.py:137`): `_in_store` kiểm `law_hint`
("Bộ luật Lao động 2019") có phải **chuỗi con** của tên văn bản trong kho ("Bộ Luật lao động số 45/2019/QH14") hay không.
Không bao giờ khớp khi LLM viết tên luật kiểu thông thường.

### [14] Đề xuất sửa 🤖

14 đề xuất, **cả 14 có `old_ok = true`**. F8 và F4 kèm "Chưa kiểm tra pháp lý". Ví dụ F7 (phí đào tạo):

```
Cũ:  Nếu sau khi kết thúc khóa đào tạo mà nhân viên không tiếp tục hợp tác với Công ty thì nhân viên phải hoàn trả
     lại 100% phí đào tạo và các khoản chế độ đã được nhận trong thời gian đào tạo..
Mới: Người lao động chỉ có nghĩa vụ hoàn trả chi phí đào tạo khi có thỏa thuận đào tạo hợp lệ và việc hoàn trả thuộc
     trường hợp được quy định trong thỏa thuận đó và phù hợp quy định pháp luật. Việc xác định khoản hoàn trả phải căn
     cứ vào chi phí đào tạo thực tế có chứng từ; không áp dụng nghĩa vụ hoàn trả chỉ vì quan hệ lao động chấm dứt không
     do lỗi hoặc vi phạm cam kết của Người lao động.
Lý do: "Không tiếp tục hợp tác" không phân biệt nguyên nhân chấm dứt; yêu cầu hoàn trả cả các khoản chế độ có thể áp
       dụng cả khi Người lao động không vi phạm cam kết.
```
Câu cũ trải trên ba dòng của PDF và vẫn khớp liền mạch, vì kiểm trích dẫn chuẩn hóa khoảng trắng và xuống dòng.

### [15] Thay đổi luật ⚙️

13 điều luật được dùng làm căn cứ, so phiên bản tại 02/01/2025 với hôm nay (14/11/2026):

| Điều luật | Trạng thái | Điều khoản hợp đồng bị ảnh hưởng |
|---|---|---|
| NĐ 12/2022 Đ10 *Vi phạm quy định về thử việc* | **repealed**, thay bởi NĐ 283/2026/NĐ-CP | Điều 6 |
| BLLĐ 2019 Đ122 *Trình tự xử lý kỷ luật* | **changed** | PL1 — Điều 2 |
| BLLĐ 2019 Đ113 *Nghỉ hằng năm* | **changed** | Điều 3 |
| 10 điều còn lại | unchanged | |

Không gọi LLM, 2,3 s.

### [16] Tóm tắt 🤖

15 đơn vị (dưới giới hạn 30, không cắt). 7 mục, mỗi ý gắn đơn vị nguồn. Tóm tắt nêu đúng cả hai mức lương và mốc
01/07/2025:
> Theo hợp đồng ban đầu, lương căn bản là 15.000.000 đồng/tháng và phụ cấp là 1.000.000 đồng/tháng. Phụ lục 2 điều
> chỉnh… [Điều 2]

**Lỗi rò rỉ PII qua bước mở che.** Mục "Đối tượng" có một ý:
> Các thông tin cá nhân được ẩn gồm 036196001234. [Phần mở đầu]

LLM viết "Các thông tin cá nhân được ẩn gồm **[HD_CCCD_1]**". `ask_json` mở che **mọi** chuỗi trong kết quả, nên ký
hiệu bị đổi thành số CCCD thật và hiện ra trong bản tóm tắt. Bước tóm tắt không kiểm trích dẫn nên câu thừa này không
bị chặn.

### [17] Hỏi đáp 🤖

**Câu hỏi:** "Công ty có được buộc tôi hoàn trả 100% phí đào tạo nếu tôi nghỉ việc sau khóa đào tạo không?"

1. Tra luật 🔎 (mốc 2025-01-02): BLLĐ Đ40, BLLĐ Đ62, NĐ 12/2022 Đ14, Luật Việc làm 2013 Đ48.
2. `ANSWER` 🤖 → `legal_conclusion = true`, đơn vị Điều 4, Điều 7.
3. `VERIFY` 🤖 giữ BLLĐ Đ62 và Đ40, nên `legal_status = concluded`.

> Không thể kết luận Công ty đương nhiên được buộc bạn hoàn trả 100% chỉ dựa trên điều khoản trong hợp đồng lao động
> hiện có. […] Theo Điều 62 Bộ luật Lao động được cung cấp, khi Công ty dùng kinh phí của mình để đào tạo nâng cao kỹ
> năng hoặc đào tạo lại, hai bên phải ký hợp đồng đào tạo nghề; hợp đồng phải nêu thời hạn cam kết làm việc, chi phí
> đào tạo và trách nhiệm hoàn trả. […] Nếu bạn đơn phương chấm dứt hợp đồng trái pháp luật, Điều 40 quy định phải hoàn
> trả chi phí đào tạo theo Điều 62. Nếu nghỉ việc đúng pháp luật, các căn cứ được cung cấp không nói rằng cứ nghỉ sau
> khóa học thì tự động phải trả 100% […]

Câu trả lời bám đúng hai điều luật, phân biệt nghỉ đúng luật và trái luật, và nói rõ giới hạn của căn cứ.

---

## 7. Rút ra

### Chạy tốt

- **Đọc và tách:** PDF 10 trang đọc đúng; nhận đủ hai phụ lục theo tiêu đề nguyên văn của mẫu; 12 Điều, 10 khoản,
  32 giá trị.
- **Chia lô:** 2 lô; lô sau nhận `known_parties` nên không trích lại các bên (lỗi lặp bên của benchmark CUAD không xuất
  hiện).
- **Dữ kiện nền:** đúng hết 11 trường; không lấy ngày của phụ lục làm ngày ký hợp đồng.
- **Câu hỏi thay vì đoán:** thử việc 02 tháng được trả kết luận theo trình độ công việc kèm câu hỏi, đúng thiết kế.
- **Phát hiện:** bắt được các điều khoản có vấn đề có sẵn trong mẫu thật: hoàn trả 100% phí đào tạo không có hợp đồng
  đào tạo, sa thải khi chưa đánh giá được thiệt hại, "không khiếu nại về sau", danh mục bảo mật bổ sung tùy ý.
- **Thời gian:** luật được chọn đúng phiên bản tại ngày ký; bước thay đổi luật báo NĐ 12/2022 đã bị thay.
- **Đồ thị** được công bố lên Neo4j ở cả hai bản dựng.

### Lỗi thật (theo mức ảnh hưởng)

| # | Lỗi | Bước | Bằng chứng | Mức |
|---|---|---|---|---|
| 1 | **Tên người, ngày sinh, địa chỉ không bị che khi gửi LLM** | mọi lời gọi gửi đơn vị | Tên hai người có trong 7/9 payload; mẫu dùng "ÔNG / BÀ :", "Đại diện:", "Bà:" | Cao |
| 2 | **Bản tóm tắt in ra số CCCD thật** | [16] | LLM viết `[HD_CCCD_1]` trong câu tóm tắt; `ask_json` mở che thành số thật | Cao |
| 3 | **Ranh giới phần bắt đầu từ dòng tiêu đề**, nên quốc hiệu và **ngày ký của phụ lục** rơi vào phần trước | [4] | "Hà Nội, ngày 01 tháng 07 năm 2025" nằm ở PL1 Đ3; PL2 bị coi là "không ghi ngày ký" (F14) | Cao (chính là dạng lỗi Sonos của benchmark) |
| 4 | **Lời từ chối nói "Kho chưa có [luật]" khi kho có luật đó** | [13g] | F4: "Kho chưa có Bộ luật Lao động 2019" trong khi 7 phát hiện khác dùng BLLĐ 45/2019 | Trung bình |
| 5 | **Phụ lục sửa đổi bị coi là mâu thuẫn** | [6], [10] | Lương 15 triệu / 17 triệu, ngày hiệu lực 02/01 / 01/07 thành "conflict", người dùng phải chọn một | Trung bình (đã biết: spec §7.7 chưa làm) |
| 6 | **Dẫn chiếu "Điều 2 Hợp đồng lao động" từ phụ lục trỏ nhầm** về "Mục 2" của chính phụ lục | [5] | `p2.d1 → p2.d2` | Trung bình |
| 7 | **Bước soát không tự sửa đơn vị khi LLM ghi nhầm** | [13d] | F8 gắn Điều 4, câu thuộc PL1 Đ2; thành phát hiện trùng với F12, mất kết luận | Thấp |
| 8 | **Cảnh báo "trang mỏng" báo động giả** ở trang chỉ có chữ ký | [5] | Trang 5 (111 ký tự), trang 10 (340 ký tự) | Thấp |
| 9 | Mọi đơn vị, kể cả của phụ lục, mang `valid_from` = ngày ký hợp đồng chính; tra luật cho phụ lục cũng dùng mốc 02/01/2025 | [8], [13e] | PL2 có hiệu lực 01/07/2025 | Thấp (spec H5, §7.7) |

Lỗi 4 và lỗi 7 đã thấy ở lần chạy hợp đồng thuê nhà và lặp lại ở đây. Lỗi 1 rộng hơn lần trước: lần trước chỉ thấy tên
ở khối chữ ký, lần này tên không bị che ở bất kỳ đâu.

### Giới hạn của lần chạy

- Một bộ hồ sơ, một lần chạy. LLM có dao động giữa các lần chạy (benchmark CUAD đo được), nên số phát hiện và cách diễn
  đạt có thể khác ở lần sau.
- Điều khoản là thật, nhưng dữ liệu điền vào là giả lập, và Điều 6 do tôi điền.
- Không có đáp án chuẩn để chấm phát hiện; đánh giá "đúng / lạc đề" ở trên là nhận xét của người viết, chưa được người
  có chuyên môn luật lao động kiểm.

## 8. Lần chạy trước trên hợp đồng thuê nhà

Bản trước của ghi chú này dùng `hop_dong_thue_nha_2023.docx` (3.355 ký tự, 1 lô), chạy hai lần: thiếu reranker và
Neo4j, rồi đủ môi trường. Dữ liệu thô vẫn giữ ở `contract-trace-2026-11-14/trace_thue_nha.json` và
`trace_thue_nha_after_env_fix.json`. Kết luận chính của lần đó: thiếu reranker làm căn cứ luật lạc đề (vd. điều về hợp
đồng ủy quyền cho phát hiện về quyền vào nhà thuê); có reranker thì hết.
