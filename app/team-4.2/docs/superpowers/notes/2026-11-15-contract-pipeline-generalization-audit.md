# Rà soát tổng quát hóa của pipeline hợp đồng: chỗ vá, rule cứng, heuristic

Ngày: 2026-11-15. Nhánh `feat/team-4.2/w03-labor-contract-kg`. Người rà: Claude (đọc code, chạy thử 3 phép thử nhỏ, không sửa code).

## 1. Mục đích, phạm vi, phương pháp

**Mục đích.** Liệt kê mọi chỗ trong pipeline hợp đồng đang (a) vá theo một ca đã gặp, (b) dùng rule cứng hoặc danh sách từ khóa
chỉ đúng với một phạm vi hẹp, (c) xấp xỉ ngầm, để quyết định sửa gì trước khi nói pipeline "tổng quát".

**Phạm vi đã rà** (đọc toàn bộ file trừ khi ghi khác):
`contracts/` (parse, doc, structure, parts, tree, values, xrefs, facts, verify, batches, review, evidence, llm_json, store, export,
agent_view, `graph/` build, oplog, service, neo4j_store), `bridge/` (catalog, engine, facts_map, check, tagger, recheck, basis,
llm, `concepts.yaml`), `ingest/loaders.py`, `ingest/extraction_check.py`, `ingest/headers.py`, `quality/pii.py`,
`ui/contracts_api.py`, các script chấm điểm, `fact_catalog.json`, nhãn vàng `demo_gold.yaml`.

**Không rà:**
- **Đồ thị luật của Huy** (theo yêu cầu).
- `ingest/ocr.py` (chỉ đọc docstring), `ingest/tables.py`, `near_duplicate.py`, `vbpl.py`, `chunker.py`, `dedup.py`,
  `quality/validate|numeric|review_queue`: kiểm bằng grep thì chỉ `ui/legal_api.py` import chúng, không nằm trên đường chạy hợp đồng.
- `ui/*.js|html`, các script `demo_*`, nội dung các file test.

**Phương pháp.** Mỗi mục ghi rõ bằng chứng: **[chạy thử]** là đã chạy code và thấy kết quả (mục 8), **[đọc code]** là suy ra từ
mã nguồn, chưa chạy. Mức độ:

- **P0**: dữ kiện sai hoặc mất **âm thầm** trên cách viết phổ biến, hoặc làm kết quả đo không đáng tin.
- **P1**: giới hạn phạm vi, hoặc vá theo ca có thể sai trên hợp đồng khác.
- **P2**: xấp xỉ, rủi ro thấp hoặc chưa kiểm chứng.

## 2. Tóm tắt

**64 phát hiện** trong 9 nhóm: **6 P0**, 36 P1, 22 P2. Các mục ghi "chạy thử" (2.1, 2.2, 2.3, 3.1, 3.2, 3.4, 3.5, 7.1) đã chạy code
và thấy kết quả; 9.1, 9.2, 6.4 là đã mở file kiểm trực tiếp; phần còn lại suy ra từ đọc code.

| Nhóm | Số mục | Nhóm | Số mục |
|---|---|---|---|
| 1. Nhập file | 8 | 6. Dữ liệu luật nhập tay | 4 |
| 2. Tách cấu trúc | 7 | 7. Che PII và lưu dữ liệu | 5 |
| 3. Trích giá trị, chuẩn hóa | 10 | 8. Đồ thị, API, báo cáo, hỏi đáp | 10 |
| 4. Mâu thuẫn, phụ lục | 6 | 9. Đo lường và kiểm thử | 4 |
| 5. Rule engine, kiểm lại | 10 | | |

Sáu mục P0: 2.1, 2.2, 3.1, 3.2, 7.1, 9.1.

Ba phát hiện quan trọng nhất, đều đã chạy thử:

1. **Bộ trích giá trị bỏ sót các cách viết rất thường gặp** (`15.000.000đ`, `12 (mười hai) tháng`, `15,000,000 VND`). Dữ kiện biến mất
   mà không báo lỗi, rồi rơi vào "cần dữ kiện" hoặc "thiếu nội dung" (mục 3.1).
2. **Tách cấu trúc vỡ khi tiêu đề Điều không có dấu câu** (`Điều 1 Thời hạn`, `Điều thứ nhất`): 13 đơn vị còn 3. Và các văn bản
   sửa đổi không tên "Phụ lục" (`Biên bản thỏa thuận sửa đổi`) bị nuốt vào Điều cuối của hợp đồng chính (mục 2.1, 2.2).
3. **Che PII chỉ nhận tên sau nhãn `Họ và tên:`.** Tên sau `Ông/Bà`, `Người lao động:`, `Đại diện:` cùng địa chỉ, ngày sinh vẫn
   đi thẳng tới LLM (mục 7.1).

## 3. Bảng phát hiện

### Nhóm 1. Nhập file

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 1.1 | P1 | `loaders.py:163-165,186-193`; `.env.example` `OCR_ENGINE=none` | Mặc định OCR tắt. PDF scan cho trang rỗng chỉ cảnh báo, file ảnh bị từ chối. Hợp đồng scan không dùng được khi chưa cấu hình. | đọc code |
| 1.2 | P1 | `ocr.py:17` (docstring) | Khi bật OCR, **ảnh trang được gửi ra ngoài (OpenRouter → Google) trước khi che PII**. Chỉ che text OCR sau đó. | đọc code |
| 1.3 | P2 | `loaders.py:203-249` | DOCX chỉ đọc thân văn bản và bảng. Text box, footnote, header/footer, tracked changes, comment không được đọc: nội dung đặt trong text box mất âm thầm. | đọc code, chưa thử |
| 1.4 | P2 | `loaders.py:162` | PDF dùng `get_text(sort=True)`. Với bố cục nhiều cột có thể đọc sai thứ tự. | đọc code, chưa thử |
| 1.5 | P2 | `contracts_api.py:60`; `loaders.py:267-274` | Không hỗ trợ `.doc`, `.rtf`, `.odt`. TXT chỉ nhận UTF-8 (có báo lỗi rõ). | đọc code |
| 1.6 | P2 | `headers.py:27-37` | Với PDF/ảnh, bỏ dòng mép chỉ có số, `3/10`, `Trang N`, URL, dòng bản quyền. Có bảo vệ dòng `Điều/Khoản`; DOCX và TXT không qua bước này. | đọc code |
| 1.7 | P2 | `extraction_check.py:27-29` | Phát hiện font vỡ dấu: ≥5 ký tự lạ và ≥3% số chữ. Trang tiếng Đức/Pháp cũng bị gắn cờ (docstring tự ghi). | đọc code |
| 1.8 | P2 | `contracts_api.py:59-64` | Tối đa 150 trang, 50 MB. | đọc code |

### Nhóm 2. Tách cấu trúc (Điều, khoản, phụ lục, tham chiếu, lô)

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 2.1 | **P0** | `tree.py:10` `_ARTICLE` | Tiêu đề Điều **bắt buộc** có dấu `. : - –` sau số. `Điều 1 Thời hạn`, `Điều thứ nhất: …`, `Điều 1) …` không nhận: cả hợp đồng rơi sang kiểu `numeric` ("Mục 1…"), **13 đơn vị còn 3**. | **chạy thử** (8.3) |
| 2.2 | **P0** | `parts.py:8-19,42-72` | Chỉ nhận phần bắt đầu bằng "PHỤ LỤC / Phụ lục + số". `BIÊN BẢN THỎA THUẬN SỬA ĐỔI`, `BẢN SỬA ĐỔI, BỔ SUNG HỢP ĐỒNG` không thành phần riêng: nội dung sửa đổi **bị nuốt vào Điều cuối** của hợp đồng chính, và logic "phần sau mới hơn" (`facts_map._resolve`) không còn dữ kiện để phân biệt. | **chạy thử** (8.3) |
| 2.3 | P1 | `parts.py:8,10` | `Phụ lục A` (chữ thường, mã chữ) không nhận. `PHỤ LỤC A` (hoa) nhận. | **chạy thử** (8.3) |
| 2.4 | P1 | `tree.py:20-22` | Số Điều kế tiếp phải tăng và không quá +3; điểm bỏ tối đa 3 chữ; kiểu đánh số cần tối thiểu 1/2/2 tiêu đề. Đánh số lặp hoặc lệch bị bỏ qua và nuốt vào Điều trước. | đọc code |
| 2.5 | P2 | `parts.py:13-19` | `_LETTERHEAD` khóa cứng quốc hiệu, tiêu ngữ, dòng `Nơi, ngày … tháng … năm …`. | đọc code |
| 2.6 | P2 | `xrefs.py:8-26` | Dẫn chiếu ngoài chỉ nhận 4 loại văn bản: Bộ luật, Luật, Nghị định, Thông tư. `Quyết định`, `Nghị quyết`, `Pháp lệnh` thành "missing". `_BASE_CONTRACT_RE` (`Hợp đồng lao động / gốc / số`, loại `thử việc / đào tạo`) là mẫu cứng. | đọc code |
| 2.7 | P2 | `batches.py:16-20,91-96` | Lô 12 000 ký tự; đơn vị dài >24 000 cắt mảnh; ngữ cảnh chung chỉ là Điều có chữ "giải thích từ ngữ / định nghĩa", tối đa 3. | đọc code |

### Nhóm 3. Trích giá trị và chuẩn hóa

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 3.1 | **P0** | `values.py:23-38` | Regex chỉ nhận số liền đơn vị. Bỏ sót `15.000.000đ`, `15.000.000 đ`, `15,000,000 VND`, `15tr`, `12 (mười hai) tháng`, `60 (sáu mươi) ngày`, số viết bằng chữ, `30 phút`, `tháng 01/2025`. Chỉ 5 đơn vị thời gian (ngày/tuần/tháng/năm/giờ). | **chạy thử** (8.1) |
| 3.2 | **P0** | `facts_map.py:24-35` `_duration` | Lấy **giá trị đầu tiên**. `1 năm 6 tháng` ra 12 tháng thay vì 18. | **chạy thử** (8.1) |
| 3.3 | P1 | `facts_map.py:30,32-33,71-80` | "Ngày làm việc" nhận bằng chữ đứng ngay sau số; năm = 12 tháng; ngày → tháng chia 30. | đọc code |
| 3.4 | P1 | `facts_map.py:199-203` `party_role` | Nhận vai trò bằng chuỗi con: "công ty", "sử dụng lao động", "người lao động". Trượt với `Hộ kinh doanh`, `Doanh nghiệp tư nhân`, `Bên A`, `Chủ cửa hàng`, `Giám đốc`. | **chạy thử** (8.2) |
| 3.5 | P1 | `facts_map.py:64-68` `_labor_kind` | Chỉ nhận cụm "xác định / không xác định". Trượt với `Có thời hạn 12 tháng`, `Mùa vụ`. | **chạy thử** (8.2) |
| 3.6 | P1 | `facts_map.py:19,101-106` | `_JOB_LEVEL_CODES` ghép **theo thứ tự** với danh sách `job_levels` trong `fact_catalog.json`; so khớp nhãn tuyệt đối. Đổi thứ tự một danh sách là sai ngầm. | đọc code |
| 3.7 | P1 | `facts_map.py:113` | `has_probation` chỉ true khi có ứng viên thử việc; **không bao giờ false**. Hợp đồng không thử việc ra "chưa biết". | đọc code |
| 3.8 | P1 | `facts_map.py:20-21,44-48` | Slot bool chỉ nhận `true/có/yes/1` và `false/không/no/0`. LLM trả "được"/"không được" thì bỏ slot. | đọc code |
| 3.9 | P1 | `tagger.py:89-90` | Slot số mà `raw` không nằm trong câu trích thì **loại cả khái niệm**, trong khi slot lạ chỉ bị bỏ slot, giữ khái niệm. Hai xử lý khác nhau cho cùng một loại lỗi. | đọc code |
| 3.10 | P2 | `facts_map.py:58-60,88-93` | Tiền chỉ nhận VND (USD thành None). | đọc code |

### Nhóm 4. Mâu thuẫn, phụ lục, dữ kiện cấp hợp đồng

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 4.1 | P1 | `facts_map.py:83-85,88-93,120-134` | **Cụm vá phụ lục.** `_AMEND` = 5 từ khóa (`điều chỉnh\|sửa đổi\|thay đổi\|thay thế\|nâng`); `_NEW_VALUE` = `lên\|thành`; "phần sau cùng mới hơn" và chỉ thắng khi là phần **duy nhất** mang giá trị đó. Hai phụ lục nối tiếp, hoặc diễn đạt "bổ sung / kể từ ngày … mức lương là …" → CONFLICT. | đọc code |
| 4.2 | P1 | `facts_map.py:167-172` `_merge` | Xử lý phụ lục chỉ áp cho dữ kiện cấp hợp đồng. **Slot của khái niệm** (vd. phép năm bị phụ lục sửa) hai giá trị khác nhau luôn thành CONFLICT, không có logic phụ lục. | đọc code |
| 4.3 | P1 | `check.py:82-85`; `engine.py:216` | Mọi giá trị luật tra theo **một ngày** (ngày ký hợp đồng chính). Lương sau phụ lục không được so ở ngày hiệu lực của phụ lục. | đọc code |
| 4.4 | P2 | `contracts/facts.py:50,75-124` | Nhận tên gọi tắt của bên bằng 3 regex (`_AFTER_NAME`, `_IN_QUOTES`, `_CALLED`); ngoặc không có nháy chỉ nhận dạng `(Bên …)` tối đa 4 từ. Gộp bên bằng tên/alias, loại nhãn chung. | đọc code |
| 4.5 | P2 | `contracts/facts.py:132-144`; `llm_json.py:81-102` | `_checked` tự sửa `uid` mà LLM ghi nhầm bằng cách dò nơi chứa câu trích. `quote_ok` bỏ `---`, `...`; câu trích nhiều dòng chấp nhận nếu từng dòng ≥8 ký tự khớp theo thứ tự (dung sai có thể nhận câu ghép không liền mạch). | đọc code |
| 4.6 | P2 | `contracts/facts.py:218-229` | Dạng cũ lấy ứng viên đầu; loại hợp đồng lấy theo lô đầu; ngày ký chỉ tự gán khi có đúng 1 ứng viên, nhiều ngày thì để người dùng chọn. | đọc code |

### Nhóm 5. Rule engine, kiểm lại, kiểm loại hợp đồng

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 5.1 | P1 | `engine.py:44-54` `_BASE` | 1 tháng = 720 giờ, 1 tuần = 168 giờ; **`workday` không quy đổi được**. "Thử việc 6 ngày làm việc" so với ngưỡng tính bằng ngày ra "chưa biết". | đọc code |
| 5.2 | P1 | `engine.py:195-201` | `_unstated_restriction`: rule `= false` + slot trống → PASS. Là quy ước hợp lý nhưng viết cho một mẫu diễn đạt ("theo quy định pháp luật"). | đọc code |
| 5.3 | P1 | `engine.py:_evaluate_rule` | **Chưa xử lý** "theo luật định" cho rule dạng ngưỡng (nghỉ lễ, báo trước khi chấm dứt) và "nghỉ Chủ nhật" → 24 giờ. Nếu sửa theo cách cũ sẽ thành hai chỗ vá mới. | đọc code |
| 5.4 | P1 | `engine.py:188-192` | Rule chỉ dùng dữ kiện cấp hợp đồng được xét như "khái niệm có mặt" kể cả khi LLM không gán khái niệm nào. | đọc code |
| 5.5 | P1 | `recheck.py:29,41-53` | Kiểm lại bằng **BM25 top-5** theo `label + phrasing`, chỉ cho `missing_content`/`hidden_right`; không kiểm lại cho `violation`. Điều khoản dùng từ khác `phrasing` bị coi là vắng mặt → báo "thiếu nội dung" hoặc "quyền ẩn" sai. | đọc code |
| 5.6 | P1 | `check.py:66-` | **Không chặn loại hợp đồng**: đưa hợp đồng thuê nhà vào vẫn chạy rule lao động. | đọc code |
| 5.7 | P1 | `check.py:82-85` | Không có ngày ký thì dùng `law_values_valid_from` = 2021-01-01. | đọc code |
| 5.8 | P1 | `catalog.py:21-27` | Danh mục đóng: 39 khái niệm; 8 dữ kiện hợp đồng (`CONTRACT_FACTS`) và 8 dữ kiện người dùng (`USER_FACTS`) là tập cứng. Nội dung ngoài danh mục (điều động, kỷ luật, bồi thường, bảo mật) không có chỗ chứa. | đọc code |
| 5.9 | P2 | `engine.py:104-124` | Chọn giá trị theo kỳ bằng "kỳ có `valid_from` ≤ ngày, lấy kỳ mới nhất"; không có `valid_to`, không biểu diễn văn bản bị bãi bỏ. | đọc code |
| 5.10 | P2 | `concepts.yaml` `not_about` | 2 dòng, mỗi lỗi gán nhầm gặp thêm một dòng. Là dữ liệu nhưng tăng theo số lỗi đã gặp. | đọc code |

### Nhóm 6. Dữ liệu luật nhập tay

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 6.1 | P1 | `concepts.yaml:332-338` | Lương tối thiểu vùng, 3 kỳ × 4 vùng: ghi rõ "số do người viết nhớ", chưa đối chiếu nghị định. | đọc code |
| 6.2 | P1 | `concepts.yaml:198,600,659,787` | 4 neo ghi "A chưa đối chiếu nguyên văn". Có khoảng 33 giá trị số hoặc danh sách hằng trong rule. | đọc code + grep |
| 6.3 | P1 | `concepts.yaml:52,20` | `law_values_valid_from` = 2021-01-01 áp cho mọi giá trị không theo kỳ. Giá trị chép từ BLLĐ 2019 bản gốc; văn bản sửa đổi đổi giá trị nào thì phải ghi `note` thủ công. | đọc code |
| 6.4 | P1 | `concepts.yaml` (anchors) | 5 anchor dẫn vào Luật BHXH 2014/2024, NĐ 293/2025, 74/2024, 38/2022: các văn bản này **không có trong snapshot kho luật hiện hành** (35 văn bản, chỉ BLLĐ 2019 và 2012 thuộc luật lao động). | đã kiểm catalog |

### Nhóm 7. Che PII và lưu dữ liệu

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 7.1 | **P0** | `pii.py:64-67,191-202` `NAME_RE` | Tên người chỉ được che khi đứng sau `Họ và tên:` hoặc `Họ tên:`. **Không che:** `Ông/Bà + tên`, `Người lao động: tên`, `Bên B: tên`, `Đại diện: Bà … - Giám đốc`, `Họ tên người đại diện: tên` (regex cho phép đúng một từ sau "người"), địa chỉ, ngày sinh, số hộ chiếu, mã BHXH. Lần chạy thật 14/11: tên lộ ở 7/9 payload. | **chạy thử** (8.4); xfail `test_payload_masks_person_names` |
| 7.2 | P1 | `pii.py:53` | CCCD chỉ nhận mã tỉnh 001–096. | đọc code |
| 7.3 | P1 | `pii.py:156-157,177-185` | `mask_known` chỉ thay các giá trị đã gặp ở chỗ khác và dài ≥4 ký tự. | đọc code |
| 7.4 | P1 | `store.py:98-106` | Khi "Lưu lại", ghi xuống đĩa **văn bản thô, `page_texts`, `facts` (tên các bên), báo cáo và file gốc**, không che, không mã hóa. Che chỉ áp khi gửi LLM và ghi graph. | đọc code |
| 7.5 | P1 | `ocr.py:17` | Xem 1.2: ảnh đi ra ngoài trước khi che. | đọc code |

### Nhóm 8. Đồ thị, API, báo cáo, hỏi đáp

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 8.1 | P1 | `check.py`, `build.py` | Engine **không đọc từ Neo4j**: dữ kiện đi từ oplog và factset trong bộ nhớ; graph dựng lại sau khi kiểm tra (lớp truy vết, không phải lớp suy luận). | đọc code |
| 8.2 | P1 | `build.py:141` | Cạnh `HOLDER` chỉ nối khi `concept.holder` có nút Party. Chỉ NLĐ/NSDLĐ có Party nên khái niệm của lao động nữ, mang thai... không có cạnh `HOLDER`. | đọc code |
| 8.3 | P1 | `contracts_api.py` | API và UI vẫn chạy `review.py` (lớp cũ, kết luận do LLM); concept-check chỉ chạy qua script. `create()` gọi `extract_facts` bằng LLM app. | đọc code |
| 8.4 | P1 | `export.py:20-22,50-115` | Xuất Word/PDF chỉ hỗ trợ báo cáo lớp cũ (`review/partial/law_changes/redline/summary`). Báo cáo concept-check chỉ có `.md` và `.json`. | đọc code |
| 8.5 | P2 | `verify.py:43-49` | `catalog_type`: chỉ hai loại cứng, chứa "lao động" → labor, chứa "thuê" → lease, còn lại common. | đọc code |
| 8.6 | P2 | `parse.py:9,16`; `review.py:60-98,143` | Lớp cũ: `DEMO_MAX_UNITS = 30` cho `summarize`/`answer`; `_law_name`/`_in_store` so khớp tên luật bằng regex; prompt cố định; `DEFAULT_LAW`. | đọc code |
| 8.7 | P2 | `agent_view.py:40-44,92-112` | Hỏi đáp hợp đồng: BM25 trên hợp đồng, nhánh dense là `_NoDense` (trống), điểm gán giả `1.0/i`, trộn nguồn bằng `zip_longest`, `rerank_n=10`. | đọc code |
| 8.8 | P2 | `export.py:32-33` | Font PDF: 4 đường dẫn cứng (Windows, Linux, macOS). | đọc code |
| 8.9 | P2 | `oplog.py:42-49` | `op_id` của thao tác máy là băm nội dung: cùng nội dung thì trùng id và bị bỏ. Đổi model hay prompt mà nội dung giống nhau không tạo thao tác mới. | đọc code |
| 8.10 | P2 | `service.py:17`; `neo4j_store.py:91` | Neo4j sập thì chờ 30 giây mới thử lại; mỗi lần công bố xóa toàn bộ đồ thị hợp đồng rồi tạo lại trong một giao dịch. | đọc code |

### Nhóm 9. Đo lường và kiểm thử

| ID | Mức | Vị trí | Phát hiện | Bằng chứng |
|---|---|---|---|---|
| 9.1 | **P0** | `tests/fixtures/bridge/demo_gold.yaml`; `scripts/score_concept_check.py` | Nhãn vàng chỉ có `present` (18 khái niệm) và `ambiguous` (3). **Không có nhãn cho kết luận** (vi phạm / thiếu nội dung / quyền ẩn / cần dữ kiện). Script chấm P/R khái niệm, slot và `false_silent`, không chấm kết luận. | đã kiểm |
| 9.2 | P1 | `data/team-4.2/contracts_demo/` | Chỉ 1 HĐLĐ (demo) và 1 hợp đồng thuê nhà. HĐLĐ demo gần như hợp lệ nên chưa chứng minh được việc bắt lỗi. Số liệu P/R 1,0 và slot 5/5 đo trên chính hợp đồng đã dùng để chỉnh code và chọn model. | đã kiểm |
| 9.3 | P1 | `tests/test_bridge_*.py` | 53 hàm test ở 8 file `test_bridge_*` + `engine_cases.yaml`, phần lớn viết theo ca đã gặp (regression), do cùng người sửa code viết. Chưa có test thuộc tính cho chuẩn hóa số, đơn vị, cấu trúc. | đọc code |
| 9.4 | P2 | `scripts/check_contract_concepts.py` | Các lần chạy gần nhất lấy LLM từ cache (0,0 giây); chưa có phép chạy lạnh lặp lại để đo độ dao động. | ghi chú phiên làm việc |

## 4. Phần tổng quát thật (giữ)

- Chuẩn hóa NFC và xuống dòng (`doc.py`), kiểm câu trích nguyên văn, mô hình "LLM nhận diện, rule quyết định".
- Cây Điều/khoản/điểm theo chuỗi số (trừ điều kiện dấu câu ở 2.1), đơn vị có mã ổn định theo cấu trúc.
- Engine ba trị T/F/U, thuần Python, không I/O; thiếu dữ kiện không bao giờ thành vi phạm; danh mục được kiểm khi nạp.
- Kiểm PII trước khi ghi vào graph (`build.validate`), `build_id` tất định, nhật ký thao tác chỉ thêm.
- Đọc số dạng `15.000.000` có dấu chấm nghìn và dấu phẩy thập phân.

## 5. Phân loại để quyết định cách sửa

| Loại | Mục | Hướng xử lý |
|---|---|---|
| Vá theo ca (nên thay bằng cơ chế) | 4.1, 4.2, 3.4, 3.5, 3.6, 3.7, 5.2, 5.3, 5.10 | Quan hệ có kiểu (`AMENDS`...) do LLM trích và kiểm bằng schema; rule khai báo trạng thái `defers_to_law` |
| Lỗ hổng tổng quát hóa ở tầng thấp | 3.1, 3.2, 2.1, 2.2, 2.3, 7.1 | Sửa trước: bộ chuẩn hóa số/đơn vị có test thuộc tính, tách cấu trúc chịu dấu câu và tên phần tổng quát, che tên tổng quát hơn |
| Xấp xỉ có chủ đích (giữ, ghi rõ) | 3.3, 5.1, 5.9, 1.6-1.8, 2.5 | Giữ và đưa vào tài liệu giới hạn |
| Thiếu dữ liệu luật | 6.1-6.4 | Nạp văn bản vào kho, đối chiếu, bỏ số nhập tay |
| Phạm vi và tích hợp | 5.6, 5.8, 8.1-8.4, 1.1-1.2 | Chặn loại hợp đồng, nối API/UI, xuất báo cáo mới |
| Đo lường | 9.1-9.4 | Nhãn vàng mức kết luận, hợp đồng cài lỗi, hợp đồng lạ, chạy lạnh |

## 6. Thứ tự sửa đề xuất

1. **Chuẩn hóa giá trị (3.1, 3.2).** Làm lại bằng bộ nhận số/đơn vị có test thuộc tính (thử cả chục cách viết mỗi loại), hoặc để LLM trả giá trị chuẩn hóa kèm câu trích và để code chỉ kiểm tra lại. Đây là chỗ làm sai mọi rule dùng số.
2. **Tách cấu trúc (2.1, 2.2, 2.3).** Nhận tiêu đề Điều không dấu câu và `Điều thứ …`; nhận phần sửa đổi/bổ sung không gọi là "Phụ lục".
3. **Nhãn vàng mức kết luận và hợp đồng cài lỗi (9.1, 9.2).** Có đo thì mới biết 1 và 2 đã sửa đúng chưa.
4. **Che PII (7.1)** trước khi chạy trên hợp đồng thật; đồng thời quyết định về 7.4 và 1.2.
5. **Chặn loại hợp đồng (5.6)** và quy ước "theo luật định" (5.3).
6. **Thay cụm vá phụ lục (4.1, 4.2, 4.3)** bằng quan hệ có kiểu, so với cách hiện tại trên bộ hợp đồng chưa thấy.
7. **Nạp luật và đối chiếu (6.1-6.4)**, phần của Huy.

## 7. Hạn chế của bản rà này

- Chỉ 1 người rà (Claude), chưa có người khác đọc lại.
- Các mục ghi "đọc code, chưa thử" (1.3, 1.4, 2.4-2.7, 3.3, 3.6-3.10, 4.x, 5.x...) có thể sai khi chạy thật; mục **chạy thử** chỉ gồm 3 phép thử nhỏ (mục 8).
- Chưa rà: nội bộ OCR, đồ thị luật, giao diện web, nội dung test.
- Số đếm "33 giá trị hằng" trong `concepts.yaml` là grep thô các dòng `value:` số hoặc danh sách, có thể gồm cả những dòng không phải ngưỡng luật.

## 8. Bằng chứng chạy thử

Cách chạy: script tạm ngoài repo (không lưu trong repo), gọi trực tiếp `extract_values`, `_duration`, `party_role`, `_labor_kind`, `mask_text`,
`parse_contract`. Có thể chuyển thành test pytest nếu cần.

### 8.1 Bộ trích giá trị (`values.extract_values`, `facts_map._duration`)

| Chuỗi | Kết quả |
|---|---|
| `Thời hạn hợp đồng: 12 tháng` | duration `12 tháng` |
| `12 (mười hai) tháng` | **không bắt được** |
| `thử việc 60 (sáu mươi) ngày` | **không bắt được** |
| `hai mươi bốn tháng` | không bắt được |
| `Mức lương 15 triệu đồng/tháng` | money `15 triệu đồng` |
| `Mức lương: 15.000.000đ/tháng` | **không bắt được** |
| `15.000.000 đ` | **không bắt được** |
| `Mức lương 15,000,000 VND` | **không bắt được** |
| `lương 15tr/tháng`, `mười lăm triệu đồng` | không bắt được |
| `85% mức lương`, `85 % lương` | percent đúng |
| `tám mươi lăm phần trăm` | không bắt được |
| `nghỉ phép 12 ngày làm việc/năm` | `12 ngày`, đơn vị `workday` |
| `1 năm 6 tháng` | hai duration; `_duration` trả **12 tháng** (sai, đúng là 18) |
| `từ 02/01/2025 đến 01/01/2026` | hai date đúng |
| `tháng 01/2025` | không bắt được |
| `làm việc 8 giờ/ngày, 48 giờ/tuần` | `8 giờ`, `48 giờ` |
| `báo trước ít nhất 03 ngày làm việc` | `3`, `workday` |
| `30 phút nghỉ giữa ca` | không bắt được |
| `nghỉ ngày Chủ nhật hàng tuần` | không bắt được |

### 8.2 Nhận diện vai trò bên và loại hợp đồng

| Hàm | Đầu vào | Kết quả |
|---|---|---|
| `party_role` | `Công ty TNHH Minh An` | NSDLĐ |
| | `Cá nhân sử dụng lao động` | NSDLĐ |
| | `Ông Nguyễn Văn An - Người lao động` | NLĐ |
| | `Hộ kinh doanh Nguyễn Văn A` | **None** |
| | `Doanh nghiệp tư nhân X`, `Bên A`, `Chủ cửa hàng`, `Giám đốc` | **None** |
| `_labor_kind` | `Hợp đồng lao động xác định thời hạn` | xác định |
| | `HĐLĐ không xác định thời hạn` | không xác định |
| | `Có thời hạn 12 tháng`, `Mùa vụ` | **None** |

### 8.3 Tách cấu trúc (`parse_contract`), hợp đồng 4 Điều, mỗi Điều có 2 khoản

| Cách viết tiêu đề | Kết quả |
|---|---|
| `Điều N. Tiêu đề` / `Điều N: …` / `ĐIỀU N. …` | đúng: 4 Điều, 13 đơn vị |
| `Điều N Tiêu đề` (không dấu) | **kiểu `numeric`**: "Mục 1, Mục 2", **3 đơn vị** |
| `Điều thứ nhất: …` | **kiểu `numeric`**, 3 đơn vị |
| `Điều N) …` | **kiểu `numeric`**, 3 đơn vị |
| `1. 2. 3.` (không có "Điều") | kiểu `numeric`, đúng như thiết kế |
| `I. II. III.` | kiểu `roman` |
| Phần cuối: `PHỤ LỤC 01`, `Phụ lục số 1`, `PHỤ LỤC A`, `PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG SỐ 01/2025/PL-HĐLĐ` | nhận là phần `appendix` |
| Phần cuối: `Phụ lục A` (chữ thường) | **không nhận**, nuốt vào Điều 4 |
| Phần cuối: `BIÊN BẢN THỎA THUẬN SỬA ĐỔI` | **không nhận**, nuốt vào Điều 4 |
| Phần cuối: `BẢN SỬA ĐỔI, BỔ SUNG HỢP ĐỒNG` | **không nhận**, nuốt vào Điều 4 |

### 8.4 Che PII (`mask_text`)

| Đầu vào | Kết quả |
|---|---|
| `Họ và tên: Nguyễn Văn An` | `Họ và tên: [NAME_1]` (che) |
| `Họ và tên: NGUYỄN VĂN AN` | che |
| `Số CCCD: 001095012345` | che |
| `CMND số 012345678` | che |
| `Điện thoại: 0912 345 678` | che |
| `Email: an@example.com`, `MST: 0123456789`, `STK 1234567890 …` | che |
| `Ông Nguyễn Văn An, sinh ngày 05/03/1995` | **không che** (tên và ngày sinh) |
| `Người lao động: Trần Thị B` | **không che** |
| `Bên B: Ông/Bà Lê Văn C` | **không che** |
| `Họ tên người đại diện: Phạm Văn D` | **không che** |
| `Đại diện: Bà Hoàng Thị E - Giám đốc` | **không che** |
| `Ông NGUYỄN VĂN AN` | **không che** |
| `Địa chỉ thường trú: 12 Nguyễn Trãi, Quận 1, TP. Hồ Chí Minh` | **không che** |
| `Sinh ngày: 05/03/1995` | **không che** |
| `Hộ chiếu số B1234567`, `Mã số BHXH: 0123456789` | **không che** |

Trên hợp đồng demo, các dòng `Đại diện: Ông Phạm Quốc Khánh …`, `Ông (bà): Nguyễn Thị Thu Hà …`, địa chỉ thường trú (dòng 104,
156, 159, 163 của file `.txt`) đều thuộc nhóm không che.

## 9. Danh sách theo bản chất vấn đề (cùng 64 mục, xếp lại)

Mục 3 xếp theo bước pipeline. Mục này xếp theo loại vấn đề để chọn cách sửa. ID tham chiếu mục 3. **P0** là mục nghiêm trọng nhất; **[chạy thử]** là đã chạy thật.

### A. Regex / từ khóa viết cứng, chỉ đúng với cách viết đã gặp

| ID | Chỗ | Cứng ở đâu |
|---|---|---|
| 3.1 **P0** [chạy thử] | `values.py` | Chỉ nhận số liền đơn vị. Bỏ sót `15.000.000đ`, `15,000,000 VND`, `15tr`, `12 (mười hai) tháng`, số viết bằng chữ, `30 phút`, `tháng 01/2025`. Chỉ 5 đơn vị thời gian. |
| 2.1 **P0** [chạy thử] | `tree.py:10` | Tiêu đề Điều bắt buộc có `. : - –`. `Điều 1 Thời hạn`, `Điều thứ nhất` làm cả hợp đồng vỡ (13 đơn vị còn 3). |
| 2.2 **P0**, 2.3 [chạy thử] | `parts.py` | Chỉ nhận "PHỤ LỤC + số". `BIÊN BẢN THỎA THUẬN SỬA ĐỔI`, `Phụ lục A` bị nuốt vào Điều cuối. |
| 7.1 **P0** [chạy thử] | `pii.py` | Chỉ che tên sau `Họ và tên:`. Không che tên sau `Ông/Bà`, `Người lao động:`, `Đại diện:`, cũng không che địa chỉ, ngày sinh, hộ chiếu, mã BHXH. |
| 7.2, 7.3 | `pii.py` | CCCD chỉ nhận mã tỉnh 001–096. `mask_known` chỉ thay giá trị dài ≥4 ký tự. |
| 3.4 [chạy thử] | `party_role` | Nhận chuỗi con "công ty", "người lao động". Trượt với `Hộ kinh doanh`, `Bên A`, `Giám đốc`. |
| 3.5 [chạy thử] | `_labor_kind` | Chỉ nhận cụm "xác định / không xác định". Trượt với `Có thời hạn 12 tháng`, `Mùa vụ`. |
| 3.8 | `facts_map` | Slot bool chỉ nhận `true/có/yes/1`. "được/không được" bị bỏ. |
| 2.5, 2.6 | `parts`, `xrefs` | Quốc hiệu, tiêu ngữ viết cứng. Dẫn chiếu luật chỉ nhận 4 loại văn bản. |
| 4.4 | `facts.py` | Tên gọi tắt của bên nhận bằng 3 regex. |
| 8.5 | `verify.py` | Loại hợp đồng: chứa "lao động" → labor, chứa "thuê" → lease. |
| 1.6, 1.7 | `headers`, `extraction_check` | Ngưỡng bỏ dòng mép, ngưỡng nhận diện font vỡ (≥5 ký tự, ≥3%). |

### B. Heuristic hoặc xấp xỉ có thể sai âm thầm

| ID | Chỗ | Vấn đề |
|---|---|---|
| 3.2 **P0** [chạy thử] | `_duration` | Lấy giá trị đầu tiên. `1 năm 6 tháng` ra 12 tháng, đúng là 18. |
| 3.3, 5.1 | `facts_map`, `engine._BASE` | 1 tháng = 30 ngày = 720 giờ, năm = 12 tháng. "Ngày làm việc" không quy đổi được. |
| 3.6 | `_JOB_LEVEL_CODES` | Ghép theo thứ tự với `fact_catalog.json`. Đổi thứ tự là sai ngầm. |
| 3.7 | `has_probation` | Không bao giờ false. |
| 3.9 | `tagger.py:89` | Slot số lệch câu trích thì loại cả khái niệm; slot lạ chỉ bị bỏ slot. |
| 2.4 | `tree.py:20` | Số Điều kế tiếp phải tăng và không quá +3. Đánh số lệch bị nuốt vào Điều trước. |
| 2.7 | `batches.py` | Lô 12 000 ký tự. Ngữ cảnh chung chỉ lấy Điều có chữ "định nghĩa". |
| 5.5 | `recheck.py` | BM25 top-5 theo `phrasing`. Điều khoản dùng từ khác bị coi là vắng mặt. |
| 5.4 | `engine:188` | Rule dùng dữ kiện cấp hợp đồng bị coi là "khái niệm có mặt" dù LLM không gán. |
| 4.5, 4.6 | `facts.py`, `llm_json` | Tự sửa `uid` LLM ghi nhầm. Câu trích nhiều dòng khớp lỏng. Lấy ứng viên đầu. |
| 5.9 | `engine:104` | Chọn giá trị luật theo kỳ chỉ có `valid_from`, không có `valid_to`. |
| 5.7 | `check.py` | Không có ngày ký thì dùng 2021-01-01. |
| 8.7, 8.9 | `agent_view`, `oplog` | Điểm giả `1.0/i`, nhánh dense trống. `op_id` bằng băm nội dung. |

### C. Cụm vá theo từng ca đã gặp (nên thay bằng cơ chế)

| ID | Chỗ | Vá cái gì |
|---|---|---|
| 4.1 | `facts_map` | `_AMEND` (5 từ khóa), `_NEW_VALUE` (`lên\|thành`), "phần sau cùng mới hơn". Hai phụ lục nối tiếp hoặc diễn đạt khác thì thành CONFLICT. |
| 4.2 | `_merge` | Xử lý phụ lục chỉ áp cho dữ kiện cấp hợp đồng. Slot khái niệm bị phụ lục sửa vẫn thành CONFLICT. |
| 4.3 | `check.py` | Mọi giá trị luật tra theo một ngày (ngày ký hợp đồng chính). |
| 5.2 | `_unstated_restriction` | Viết cho đúng mẫu "theo quy định pháp luật". |
| 5.3 | `engine` | "Theo luật định" và "nghỉ Chủ nhật → 24 giờ" chưa xử lý; sửa theo cách cũ sẽ thành hai chỗ vá nữa. |
| 5.10 | `concepts.yaml` | `not_about` tăng thêm một dòng cho mỗi lỗi gán nhầm gặp phải. |

### D. Danh mục và dữ liệu luật đóng hoặc nhập tay

| ID | Vấn đề |
|---|---|
| 5.8 | Chỉ có 39 khái niệm, 8 dữ kiện hợp đồng, 8 dữ kiện người dùng. Điều động, kỷ luật, bồi thường, bảo mật không có chỗ chứa. |
| 5.6 | Không chặn loại hợp đồng. Hợp đồng thuê nhà vẫn chạy rule lao động. |
| 6.1 | Lương tối thiểu vùng ghi "số do người viết nhớ". |
| 6.2 | 4 neo "chưa đối chiếu nguyên văn", khoảng 33 giá trị hằng. |
| 6.3 | `law_values_valid_from` = 2021-01-01 áp cho mọi giá trị không theo kỳ. |
| 6.4 | 5 anchor trỏ tới văn bản không có trong snapshot kho luật. |
| 3.10 | Tiền chỉ nhận VND. |

### E. Giới hạn phạm vi và tích hợp

| ID | Vấn đề |
|---|---|
| 1.1, 1.2, 7.5 | OCR mặc định tắt. Khi bật, ảnh trang gửi ra ngoài trước khi che PII. |
| 1.3–1.5, 1.8 | DOCX không đọc text box, footnote, header/footer. PDF nhiều cột có thể sai thứ tự. Không hỗ trợ `.doc/.rtf`. Giới hạn 150 trang, 50 MB. |
| 7.4 | "Lưu lại" ghi văn bản thô, tên các bên và file gốc xuống đĩa, không che. |
| 8.1 | Engine không đọc Neo4j; đồ thị chỉ là lớp truy vết dựng sau khi kiểm tra. |
| 8.2 | Cạnh `HOLDER` chỉ có cho NLĐ/NSDLĐ. |
| 8.3, 8.4 | API/UI vẫn chạy lớp review cũ. Concept-check chỉ chạy qua script. Báo cáo mới chưa xuất được Word/PDF. |
| 8.6, 8.8, 8.10 | Lớp cũ giới hạn 30 đơn vị. Font PDF 4 đường dẫn cứng. Neo4j sập thì chờ 30 giây. |

### F. Đo lường không đủ để biết có tổng quát hay không

| ID | Vấn đề |
|---|---|
| 9.1 **P0** | Nhãn vàng chỉ có khái niệm và slot, không có nhãn kết luận. Script chấm không chấm kết luận. |
| 9.2 | Chỉ 1 HĐLĐ demo, gần như hợp lệ. P/R 1,0 đo trên chính hợp đồng đã dùng để chỉnh code. |
| 9.3 | Test chủ yếu là regression theo ca đã gặp, không có test thuộc tính. |
| 9.4 | Chưa có lần chạy lạnh lặp lại để đo độ dao động. |

Test đỏ cho các mục P0 nằm ở `tests/test_contracts_generalization_p0.py` (xfail strict, phủ 3.1, 3.2, 2.1, 2.2, 7.1).
