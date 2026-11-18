# Che PII bằng mô hình OpenMed thay cho regex

Ngày: 2026-11-14 · Trạng thái: chờ duyệt

## 1. Vì sao làm

Lần chạy thật trên hồ sơ lao động (`notes/2026-11-14-contract-pipeline-real-run.md`, mục 7) cho thấy bộ che PII bằng
regex (`rag/quality/pii.py`) **không che tên người, ngày sinh, địa chỉ cá nhân**: tên người lao động và người đại diện có
mặt trong 7/9 payload gửi LLM. Regex chỉ nhận tên đứng sau "Họ và tên:", còn mẫu hợp đồng lao động thật dùng "ÔNG / BÀ :",
"Đại diện:", "Bà:". Viết thêm regex cho từng kiểu trình bày không bền.

Người dùng quyết định: **thay hẳn bộ phát hiện regex bằng mô hình nhận dạng PII tiếng Việt của OpenMed**, ở mọi chỗ đang
che PII, và dùng mô hình tốt nhất.

## 2. Mục tiêu, ngoài phạm vi, điều phải tránh

**Mục tiêu**
- Che được dữ liệu cá nhân mà regex bỏ sót, trước hết là tên người, địa chỉ cá nhân, ngày sinh.
- Một chính sách che duy nhất cho chủ đề hợp đồng lao động (mục 4), áp dụng ở mọi nơi đang gọi bộ che.
- Có số đo trên văn bản của dự án để chọn mô hình (mục 6).

**Ngoài phạm vi**
- Nạp lại kho văn bản luật đã có (92 văn bản, 12.849 chunk). Lý do: văn bản luật gần như không chứa dữ liệu cá nhân, và
  nạp lại tốn embedding (API Jina đang bị giới hạn tần suất). [Lựa chọn của người viết; xem mục 10.]
- Sửa các lỗi khác của lần chạy thật (ranh giới phụ lục, dẫn chiếu, `_in_store`…), **trừ** lỗi mở che làm lộ CCCD trong
  bản tóm tắt, vì lỗi đó thuộc chính luồng che PII (mục 5.6).
- Tinh chỉnh (fine-tune) mô hình.

**Điều phải tránh** (dù chạy được vẫn là thất bại)
- **Che nhầm thứ phân tích pháp lý cần**: ngày ký, ngày hiệu lực, mức lương, tên luật, tên công ty, nơi làm việc, chức
  danh. Người dùng chấp nhận **sót một ít PII**, nhưng không chấp nhận che nhầm làm hỏng phân tích.
- Dữ liệu cá nhân bị đưa ra ngoài theo đường mới: log, bản ghi đánh giá, cache của mô hình.
- Hệ thống dừng hẳn vì mô hình lỗi: người dùng chọn **dự phòng bằng regex cũ** (mục 5.5).

## 3. Mô hình

### Các bản có sẵn

Họ `OpenMed/OpenMed-PII-Vietnamese-*` có 9 bản PyTorch tải được, đều giấy phép Apache-2.0, cùng 54 nhãn. Điểm do tác giả
tự công bố trên AI4Privacy + dữ liệu tiếng Việt tổng hợp (không phải hợp đồng):

| Bản | Nền | Micro F1 | Recall | Macro F1 | Ghi chú |
|---|---|---|---|---|---|
| BigMed-Large-560M | | 0,7545 | 0,757 | | **không tải được** (repo riêng tư, HTTP 401) |
| SuperClinical-Large-434M | deberta-v3-large | 0,7457 | 0,761 | 0,687 | |
| ClinicalBGE-Large-568M | | 0,7447 | 0,758 | 0,677 | |
| SnowflakeMed-Large-568M | | 0,7447 | 0,757 | 0,681 | |
| mSuperClinical-Large-279M | mdeberta-v3-base | 0,7430 | 0,759 | 0,676 | |
| SuperMedical-Large-355M | | 0,7370 | 0,751 | 0,661 | |
| BigMed-Large-278M | xlm-roberta-base | 0,7343 | 0,747 | 0,657 | bản người dùng nêu tên |
| SuperClinical-Base-184M | deberta-v3-base | 0,7343 | 0,749 | 0,667 | |
| SuperClinical-Small-44M | deberta-v3-small | 0,7305 | 0,747 | 0,655 | |

### Chạy thử (2026-11-14) và lựa chọn

Đã chạy thử hai bản trên 6 đoạn văn bản của dự án (mở đầu hồ sơ lao động, điều khoản lương và thử việc, mở đầu phụ lục,
mở đầu hợp đồng thuê nhà, một câu hỏi chat, một đoạn BLLĐ 2019), GPU RTX 3060. Kết quả chính:

| | BigMed-Large-278M | SuperClinical-Large-434M |
|---|---|---|
| CCCD 12 số (nhãn `SSN`) | 4/4 | 4/4 |
| Điện thoại, số tài khoản, email | bắt đủ ở mọi đoạn | bắt đủ ở mọi đoạn |
| Tên người (kể cả "ÔNG / BÀ :", "Đại diện:", khối chữ ký) | bắt ở mọi đoạn | bắt ở mọi đoạn, một tên chỉ 38% |
| Ranh giới span | theo từ, sạch | **vỡ giữa từ** ("Ph", "ạ", "m"), do bộ tách từ tiếng Anh của DeBERTa-v3 |
| Số hiệu luật "10/2012/QH13" | `DATE` (bị bỏ qua theo chính sách) | **`MASKEDNUMBER`** (sẽ bị che nhầm) |
| Thời gian một đoạn | 10–30 ms | 50–300 ms |

Điểm F1 công bố không phản ánh chất lượng trên tiếng Việt có dấu của dự án. **Chọn BigMed-Large-278M**
(`OpenMed/OpenMed-PII-Vietnamese-BigMed-Large-278M-v1`), cũng là bản người dùng nêu tên.

Bộ kiểm ở mục 6 vẫn chạy để chốt ngưỡng tin cậy và quy tắc ngữ cảnh. Có thể thêm mSuperClinical-Large-279M (nền
mDeBERTa đa ngôn ngữ, chưa thử) làm đối chứng. **Quy tắc chọn** (từ yêu cầu của người dùng) nếu có bản khác thắng: ít che
nhầm thứ cần giữ nhất; nếu ngang nhau thì sót ít PII nhất; nếu vẫn ngang nhau thì bản nhỏ hơn.

Bản thử cũng xác nhận **nhãn của mô hình không đủ để áp chính sách**:
- `DATEOFBIRTH` được gán cả cho **ngày ký** ("tháng 01 năm 2025"), ngày cấp CCCD, và ngày hiệu lực của luật;
- nhãn địa chỉ được gán cả cho **nơi làm việc** và địa chỉ công ty;
- `ACCOUNTNAME` được gán cho mã số thuế công ty.

Vì vậy quy tắc ngữ cảnh ở mục 4 là bắt buộc, không phải tùy chọn.

Tên mô hình đặt bằng biến môi trường (`PII_MODEL`), để đổi bản không cần sửa code.

### Phần cứng

Máy phát triển có GPU RTX 3060 Laptop 6 GB, dư cho bản 278M (khoảng 1,1 GB trọng số fp32). Môi trường `.venv` gốc hiện
**chưa có `torch`**; cần cài `torch` bản CUDA và `transformers`. Hai gói này đã có trong extra `neural` của
`pyproject.toml`; thêm một extra riêng `pii` để không bắt cài phần `neural` khác. Không có GPU thì chạy CPU (chậm hơn,
vẫn đúng).

## 4. Chính sách che (chủ đề hợp đồng lao động)

Người dùng: "chỉ che các thông tin được coi là nhạy cảm trong chủ đề của tôi", "đổi sang dạng chung chung nhưng vẫn giữ
được chi tiết để kết luận". Cơ sở: dữ liệu cá nhân theo Nghị định 13/2023/NĐ-CP, trừ những gì luật lao động cần để kết
luận.

| Hành động | Loại thông tin | Ký hiệu |
|---|---|---|
| **Che** | Họ tên người (người lao động, người đại diện, người ký, người làm chứng) | `NAME` |
| **Che** | Số CCCD/CMND/hộ chiếu; **ngày cấp và nơi cấp** của giấy tờ đó | `CCCD`, `CMND`, `ID_ISSUE` |
| **Che** | Địa chỉ của cá nhân (thường trú, tạm trú, chỗ ở hiện tại, hộ khẩu, quê quán) | `ADDRESS` |
| **Che** | Điện thoại, email | `PHONE`, `EMAIL` |
| **Che** | Số tài khoản, mã số thuế cá nhân, số sổ BHXH, số thẻ | `BANK`, `MST`, `BHXH` |
| **Tổng quát hóa** | Ngày sinh → **tháng/năm sinh**: "14/06/1996" thành "tháng 06/1996" | (không ký hiệu) |
| **Giữ** | Giới tính | |
| **Giữ** | Ngày của hợp đồng (ký, hiệu lực, thử việc, hết hạn), số tiền, tỉ lệ, thời hạn | |
| **Giữ** | Tên công ty, tổ chức, cơ quan; địa chỉ công ty và **nơi làm việc** (để xác định vùng lương tối thiểu) | |
| **Giữ** | Chức danh, phòng ban, nghề nghiệp; tên luật, số hiệu văn bản, số Điều/khoản; thành phố đứng một mình | |

Tại sao tháng/năm sinh mà không phải tuổi: tuổi phải tính tại nhiều mốc (ngày ký, ngày sự kiện, ngày luật thay đổi), và
ngưỡng tuổi nghỉ hưu tăng dần theo tháng. Tháng/năm đủ cho mọi ngưỡng (dưới 15, dưới 18, tuổi nghỉ hưu) và ít định danh
hơn ngày sinh đầy đủ.

**Điểm mà mô hình một mình không làm được.** Mô hình gán nhãn theo loại (`DATE`, `STREET`, `CITY`…), không biết địa chỉ
đó của ai, hay ngày đó là ngày gì. Chính sách trên cần thêm **quy tắc ngữ cảnh** quyết định giữ hay che từng span mà mô
hình tìm thấy:
- địa chỉ đứng sau "thường trú", "cư trú", "chỗ ở", "hộ khẩu", "quê quán" thì che; sau "Địa điểm làm việc", hoặc trong khối
  thông tin công ty, thì giữ;
- ngày đứng sau "Ngày sinh", "sinh ngày" thì tổng quát hóa; ngày đứng sau "cấp ngày" trong dòng giấy tờ tùy thân thì che;
  ngày khác thì giữ, **kể cả khi mô hình gán `DATEOFBIRTH`** (bản thử: mô hình gán nhãn này cho ngày ký);
- số giấy tờ (`SSN`, `MASKEDNUMBER`) che; `ACCOUNTNAME` bỏ qua trừ khi đứng sau "số tài khoản", "STK";
- tên người (`FIRSTNAME`/`MIDDLENAME`/`LASTNAME`) luôn che, kể cả tên người ký văn bản luật (vô hại cho phân tích).

Các quy tắc này **không phát hiện PII**, chỉ quyết định số phận của span mô hình đã tìm ra. Việc phát hiện là của mô
hình, đúng yêu cầu "thay hẳn". [Cách chia việc này là lựa chọn của người viết.]

## 5. Thiết kế

### 5.1 Giao diện không đổi

Mọi chỗ gọi hiện nay (`mask_text`, `MaskState`, `mask_cells`, `SafePIIFinding`, `MaskedText`, `count_by_type`,
`column_pii_type`) **giữ nguyên chữ ký**. Thay đổi nằm bên trong `rag/quality/pii.py`: hàm `_spans(text)` hiện trả các
span regex sẽ được thay bằng một **bộ phát hiện** có thể đổi được:

```
Detector.spans(text) -> list[Span(start, end, kind)]
  ModelDetector  — mô hình OpenMed + ánh xạ nhãn + quy tắc ngữ cảnh (mục 4)
  RegexDetector  — _spans hiện có, giữ nguyên, dùng làm dự phòng
```

Ký hiệu che giữ định dạng hiện tại (`[NAME_1]`, `[HD_CCCD_1]`, `[USER_PHONE_1]`), nên phần mở che, đánh số ổn định trong
một tài liệu, và tiền tố theo nơi dùng không đổi. Thêm các loại mới: `address`, `id_issue`, `bhxh`.

### 5.2 Chạy mô hình

- Dùng `transformers` (token classification) với ánh xạ vị trí ký tự (`return_offsets_mapping`), gộp token cùng thực thể
  thành span ký tự trên **văn bản gốc**.
- Văn bản dài hơn giới hạn của mô hình (512 token): cắt theo cửa sổ có chồng lấn, gộp kết quả; span ở vùng chồng lấn lấy
  theo cửa sổ thấy nó ở giữa.
- Gộp nhãn mô hình thành loại của dự án: `FIRSTNAME` + `MIDDLENAME` + `LASTNAME` liền nhau thành `name`;
  `STREET`/`BUILDINGNUMBER`/`SECONDARYADDRESS`/`COUNTY`/`STATE`/`CITY`/`ZIPCODE` liền nhau thành một ứng viên `address`
  (rồi quy tắc ngữ cảnh quyết định che hay giữ); `PHONE`, `EMAIL`, `BANKACCOUNT`, `SSN`/`MASKEDNUMBER` (số giấy tờ),
  `DATEOFBIRTH`… Các nhãn không thuộc chính sách (`AMOUNT`, `CURRENCY*`, `ORGANIZATION`, `JOBTITLE`, `JOBDEPARTMENT`,
  `OCCUPATION`, `DATE` không thuộc ngữ cảnh ở mục 4, `TIME`, `AGE`, `GENDER`, `SEX`…) bị bỏ qua.
- Ngưỡng tin cậy cho mỗi span: một tham số, mặc định chọn theo số đo (mục 6).
- Mô hình nạp **một lần mỗi tiến trình** (lazy, có khóa), dùng chung cho mọi luồng. Gom nhiều trang/đoạn thành một lô khi
  nạp tài liệu.

### 5.3 Dự phòng

Khi không nạp được mô hình (chưa tải, thiếu `torch`, hết bộ nhớ GPU) hoặc mô hình lỗi khi chạy một đoạn văn bản: dùng
`RegexDetector` cho đoạn đó, ghi **một** cảnh báo vào log (loại lỗi, không có văn bản), và đánh dấu trong kết quả để báo
cáo nạp tài liệu biết tài liệu nào được che bằng dự phòng. Hệ thống không dừng. Biến môi trường `PII_BACKEND = model |
regex` cho phép chạy hẳn bằng regex (test, máy yếu).

### 5.4 Các nơi dùng

| Nơi | Hiện tại | Sau thay đổi |
|---|---|---|
| Nạp tài liệu (`quality/apply.py`, `ingest/tables.py`) | `mask_text` theo trang, `mask_cells` theo ô | Như cũ, qua bộ phát hiện mới. Luật theo header cột (`column_pii_type`) giữ nguyên vì là quy tắc cấu trúc, không phải regex trên nội dung |
| Câu hỏi chat (`pipeline.py`), hỏi đáp theo thời gian (`temporal/qa.py`) | `mask_text` | Như cũ. Câu hỏi ngắn, chạy mô hình mỗi câu |
| Hợp đồng: payload LLM (`contracts/llm_json.py`), agent (`contracts/agent_view.py`), câu tra luật (`contracts/review.py`) | `mask_text` theo từng chuỗi | Như cũ |
| Hợp đồng: bộ lọc giá trị (`contracts/structure.py`) | `_spans` để bỏ giá trị chạm PII | Dùng bộ phát hiện mới |
| Đồ thị: che văn bản nút (`contracts/graph/build.py`) | `mask_text` | Như cũ |
| Đồ thị: kiểm "nút còn PII" (`build.validate`) | chạy lại `mask_text` trên chuỗi đã che | Phải coi ký hiệu che và dạng tổng quát hóa ("tháng 06/1996") là an toàn, nếu không bản dựng sẽ báo lỗi giả và không công bố |

**Hiệu năng.** `llm_json.mask_payload` gọi `mask_text` trên **từng chuỗi** của payload, có lần tới vài chục chuỗi. Cần
cache kết quả phát hiện theo nội dung chuỗi trong một tiến trình (chỉ giữ span, không giữ văn bản), để cùng một đơn vị
hợp đồng không phải chạy mô hình lại ở mỗi lần gọi LLM.

### 5.5 Sửa lỗi lộ CCCD khi mở che

Lần chạy thật: LLM viết "Các thông tin cá nhân được ẩn gồm [HD_CCCD_1]" trong bản tóm tắt; `ask_json` mở che mọi chuỗi
nên số CCCD thật hiện ra. Sửa trong phạm vi này vì nó là rò rỉ của chính luồng che. Hướng: chỉ mở che ở những trường được
phép hiển thị giá trị gốc, hoặc không mở che các loại số định danh (CCCD, CMND, MST, STK, BHXH) trong văn bản do LLM tự
viết. Người làm chọn cách cụ thể và ghi lý do.

## 6. Đo và chọn mô hình

**Bộ kiểm có đáp án**, đặt trong `evals/team-4.2/` (không đưa văn bản PII gốc vào log):
- `data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt` (hồ sơ lao động, 3 văn bản);
- `data/team-4.2/contracts_demo/hop_dong_thue_nha_2023.txt`;
- fixture `w02-27` (DOCX có PII giả trong đoạn văn và bảng, có sẵn mẫu âm: số hiệu, ngày, số tiền, Điều);
- vài đoạn văn bản luật thật trong kho (kiểm che nhầm);
- vài câu hỏi chat có PII.

Mỗi mục có đáp án theo chính sách mục 4: span phải che, span phải tổng quát hóa, và **span phải giữ** (ngày ký, mức lương,
tên công ty, tên luật…).

**Chỉ số**: số span phải che bị sót (theo loại); số span phải giữ bị che nhầm; số ngày sinh tổng quát hóa đúng; thời gian
chạy trên GPU và CPU. Chạy cho regex cũ và ba mô hình ứng viên; ghi kết quả vào một ghi chú trong `docs/superpowers/notes/`.

**Đạt yêu cầu** khi bản được chọn:
- **không che nhầm** ngày của hợp đồng, số tiền, tên công ty, nơi làm việc, tên luật trong bộ kiểm;
- sót ít PII hơn regex cũ ở tên người và địa chỉ cá nhân.

Sau khi chọn: chạy lại `scripts/trace_contract_pipeline.py` trên hồ sơ lao động, xác nhận tên người không còn trong
payload LLM, kết quả trích dữ kiện và soát không kém lần chạy trước.

## 7. Kiểm thử

- Test hiện có của regex (`test_pii.py`, `test_pii_query.py`…) chuyển sang kiểm `RegexDetector`, vẫn phải qua.
- Test mới cho `ModelDetector` dùng **mô hình giả** (trả nhãn định sẵn), không tải mô hình thật: gộp nhãn thành span, quy
  tắc ngữ cảnh (địa chỉ cá nhân vs nơi làm việc, ngày sinh vs ngày ký, ngày cấp giấy tờ), tổng quát hóa ngày sinh, cửa
  sổ chồng lấn, dự phòng khi mô hình lỗi.
- Một nhóm nhỏ test tích hợp với mô hình thật, tự bỏ qua khi không có mô hình hoặc `torch`.
- Test kiểm đồ thị không báo lỗi giả với ký hiệu che và dạng tổng quát hóa.

## 8. Ràng buộc

- Không ghi văn bản gốc hay giá trị PII vào log, bản ghi đánh giá hay cache. Cache phát hiện chỉ giữ vị trí span.
- Mô hình tải từ Hugging Face về cache cục bộ; không gửi văn bản ra dịch vụ ngoài để che.
- Giữ nguyên giao diện công khai của `rag.quality.pii` để không phải sửa nơi gọi.

## 9. Để người làm quyết

- Cấu trúc lớp/hàm bên trong, cách cắt cửa sổ, kích thước lô.
- Ngưỡng tin cậy mặc định (theo số đo).
- Danh sách từ khóa ngữ cảnh cụ thể cho địa chỉ và ngày.
- Cách sửa lỗi mở che ở mục 5.5.

## 10. Lựa chọn của người viết (người dùng chưa xác nhận)

- Chọn BigMed-Large-278M theo bản chạy thử; bộ kiểm mục 6 dùng để chốt ngưỡng và quy tắc.
- Không giữ regex chạy song song với mô hình: bản thử cho thấy mô hình bắt đủ CCCD, điện thoại, tài khoản, email. Regex
  chỉ là dự phòng (người dùng đã chọn).
- Quy tắc ngữ cảnh quyết định giữ/che span do mô hình phát hiện (mô hình không tự biết địa chỉ của ai, ngày gì).
- Không nạp lại kho văn bản luật đã có.
- Luật theo header cột bảng giữ nguyên.
- Sửa lỗi lộ CCCD khi mở che trong cùng đợt.
- Thêm extra `pii` (torch + transformers).
- Gộp các span tên liền nhau (kể cả khoảng trắng giữa chúng) thành một span: bản thử cho thấy mô hình trả từng phần
  "Phạm" / "Quốc" / "Khánh" riêng.
