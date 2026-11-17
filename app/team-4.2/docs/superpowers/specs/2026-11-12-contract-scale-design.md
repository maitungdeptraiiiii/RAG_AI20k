# Thiết kế: Đồ thị hợp đồng có phiên bản, nối với kho luật — Phần 5

Ngày: 12/11/2026 · Trạng thái: **bản nháp 3 chờ duyệt** (bản 3 viết lại §4 và §7 sau khi đọc kỹ Law-RAG và `rag.legal`; tóm tắt thay đổi ở §15)
· Kế thừa: Phần 4 (`2026-11-11-contract-review-design.md`, module `src/rag/contracts/`), kho luật có phiên bản
(`rag.legal`) · Tham khảo: dự án `C:\Users\Admin\Desktop\Law-RAG` (Neo4j).

Tài liệu này thay mục "§0. Phạm vi demo" của Phần 4 ở những chỗ nêu bên dưới. Các quy tắc cốt lõi của Phần 4 giữ
nguyên: từ chối kết luận khi thiếu căn cứ, trích dẫn nguyên văn được kiểm, che PII trước LLM, căn cứ kèm khoảng hiệu
lực.

Ký hiệu: **[Đã chốt]** = bạn đã nói · **[Tôi chọn]** = quyết định của người viết, cần bạn xem lại ·
**[Cần bạn quyết]** = còn mở (§15).

---

## 1. Vì sao làm, cho ai

Phần 4 chạy được trên một hợp đồng mẫu 12 Điều. Sắp tới là **hợp đồng thật** [Đã chốt]: dài, có phụ lục, dẫn chiếu
chéo. Trên dữ liệu đó hệ thống hiện tại cho kết quả sai hoặc thiếu mà không báo (§3), và chỗ nối hợp đồng ↔ luật là
một câu tìm kiếm do LLM tự viết nên không ổn định.

Phần 5 biến mỗi hợp đồng thành một **đồ thị trong graph database** [Đã chốt], sửa được và có lịch sử theo đúng cơ chế
phiên bản của kho luật [Đã chốt], và nối đồ thị đó với kho luật qua một danh mục vấn đề pháp lý do người và LLM cùng
kiểm [Đã chốt].

**Các câu trả lời của bạn đã đưa vào thiết kế**

| Câu hỏi | Trả lời | Hệ quả trong thiết kế |
|---|---|---|
| Loại hợp đồng | Dự kiến bất động sản, có thể đổi | Danh mục vấn đề và nội dung bắt buộc là **dữ liệu** theo loại hợp đồng, không viết cứng trong code (§8) |
| Định dạng file | Chưa chắc; tập trung Word / PDF có chữ trước | Chịu lỗi OCR lùi xuống cuối thứ tự làm (§13 bước 10) |
| Ai kiểm danh mục | Người và LLM kiểm song song | Quy trình hai người kiểm độc lập ở §8.3 |
| Phụ lục | Tải chung hoặc tải sau | Phụ lục tải sau = một lô thao tác mới trên đồ thị, tạo bản dựng mới (§7.7) |
| Sửa đồ thị | Giống cơ chế phiên bản của kho luật | Nhật ký thao tác là nguồn sự thật, đồ thị là dữ liệu dẫn xuất (§7) |
| Mức tự chấp nhận | Theo đề xuất | Thứ máy trích có trích dẫn khớp nguyên văn thì tự vào đồ thị; ngoại lệ ở §7.4 |
| Người kiểm danh mục | Không có chuyên môn luật, nhưng tra được trên mạng | Mỗi dòng đã kiểm phải kèm đường dẫn nguồn đã đối chiếu (§8.3) |
| Neo4j | Máy cá nhân; bản chung làm sau, hoặc làm luôn nếu đơn giản | Cấu hình bằng biến môi trường; cách chạy chung ở §6.4 |

**Người dùng mục tiêu** [Tôi chọn]: người nhận hợp đồng do bên kia soạn và không có pháp chế (cá nhân, hộ kinh doanh,
doanh nghiệp nhỏ), trước hết với hợp đồng bất động sản.

| Thời điểm | Văn bản họ có | Việc họ cần | Mốc luật |
|---|---|---|---|
| Trước khi ký | Bản dự thảo / mẫu của bên kia | Soát, biết chỗ bất lợi, đề xuất sửa | Ngày dự kiến ký hoặc hôm nay |
| Đang thực hiện | Hợp đồng đã ký, phụ lục ký thêm về sau | Hỏi quyền / nghĩa vụ khi có việc phát sinh; luật đã đổi gì | Ngày ký + hôm nay |
| Tranh chấp | Hợp đồng đã ký | Hỏi theo một sự kiện cụ thể | Ngày ký + ngày sự kiện |

## 2. Mục tiêu, ngoài phạm vi, điều phải tránh

**Mục tiêu**
1. Không còn kết quả thiếu im lặng: hợp đồng dài được đọc hết, hoặc hệ thống nói rõ phần nào chưa đọc.
2. Mọi nút và cạnh trong đồ thị trỏ được về **phần – Điều – khoản – trang – câu nguyên văn**.
3. Đồ thị sửa được bởi người, có lịch sử, hoàn tác được; phụ lục thêm sau không phá những gì đã có.
4. Chỗ nối hợp đồng ↔ luật ổn định giữa các lần chạy, duyệt được, và luôn lấy văn bản luật đúng phiên bản từ kho hiện có.
5. Trả lời được loại câu hỏi mà cách hiện tại yếu: nhiều điều khoản phụ thuộc nhau, điều kiện / ngoại lệ, nội dung
   bắt buộc bị thiếu, mâu thuẫn giữa các điều khoản, điều khoản đã bị phụ lục sửa.
6. Có số liệu so sánh có đồ thị và không có đồ thị trên hợp đồng thật (§11).

**Ngoài phạm vi (lần này)**
- Dựng lại kho luật trong graph database. Kho luật có phiên bản hiện tại vẫn là nguồn duy nhất của văn bản luật (§6.3).
- Tìm kiếm lan truyền trên đồ thị kiểu PageRank, cạnh đồng nghĩa, cạnh tương tự khái niệm (có trong Law-RAG — lý do
  không dùng ở §4.2).
- LLM tự viết câu truy vấn đồ thị (text-to-Cypher).
- Màn hình vẽ đồ thị tự làm. Khi cần nhìn đồ thị thì dùng trình duyệt có sẵn của Neo4j.
- Truy vấn gộp trên nhiều hợp đồng như một tính năng cho người dùng (dữ liệu đã sẵn sàng cho việc đó, chưa làm giao diện).
- So sánh hai bản dự thảo của cùng một hợp đồng qua các vòng đàm phán (mỗi bản là một hợp đồng riêng; phép so hai
  bản dựng ở §7.8 là nền cho việc này).
- Tài khoản, phân quyền, mã hóa lưu trữ (§12).
- Cách sinh bộ đáp án bằng LLM [Đã chốt: tính sau]; chỉ chốt định dạng (§11.2).

**Điều phải tránh**
- Trả lời như đã đọc hết trong khi một phần bị cắt hoặc chưa đọc được.
- Một cạnh do LLM suy ra mà mất điều kiện đi kèm ("Bên A được chấm dứt **nếu** Bên B chậm trả quá 30 ngày" thành
  "Bên A được chấm dứt").
- Trình bày thứ suy diễn như thể có sẵn trong hợp đồng.
- Gắn nhãn "trái luật" bằng căn cứ không áp dụng cho loại quan hệ đó (§10.1).
- Có hai nơi cùng giữ văn bản luật rồi lệch nhau.
- Làm lại những gì Phần 4 đã có (tóm tắt, soát, đối chiếu thay đổi luật, redline, xuất Word/PDF).

## 3. Hạn chế hiện tại và hướng sửa

Đối chiếu với code ngày 12/11/2026.

| # | Hạn chế | Bằng chứng | Hậu quả trên hợp đồng thật | Hướng sửa | Mục |
|---|---|---|---|---|---|
| H1 | Chỉ giữ 30 đơn vị đầu | `parse.py:10,42`; `contracts_api.py:109` | Mất phần cuối; hỏi đáp vẫn trả lời như đã đọc hết | Bỏ giới hạn; soát theo lô; độ phủ thật | §5.1, §9.1 |
| H2 | Phụ lục lẫn vào hợp đồng chính | `split_units` coi cả file là một văn bản | "Điều 2" phụ lục bị nhầm với "Điều 2" hợp đồng | Nút Phần; mã đơn vị có tiền tố phần | §5.1, §6 |
| H3 | Chỉ tách tới Điều; kiểu đánh số lạ thì rơi về tách đoạn | `parse.py:12-13,31-39` | Dẫn chiếu "khoản 1 Điều này" không trỏ được | Cây Điều > khoản > điểm; báo cáo chất lượng tách | §5.1 |
| H4 | Kiểm trích dẫn bằng so chuỗi con tuyệt đối | `llm_json.py:76-78` | Bản scan: trích dẫn đúng vẫn bị loại | Ba mức khớp — làm sau vì ưu tiên file có chữ | §5.4 |
| H5 | Một mốc duy nhất = ngày ký | `review.py:218-219`, `answer()` | Bản dự thảo không soát pháp lý được; tranh chấp sai mốc | Mốc tường minh | §9.2 |
| H6 | Gửi cả hợp đồng trong một lượt LLM | `review.py:188-190`, `answer()` | JSON bị cắt, sót phát hiện, chi phí tăng theo độ dài | Soát theo lô; hỏi đáp lấy điều khoản từ đồ thị | §9.1, §9.3 |
| H7 | Căn cứ luật = một câu tìm kiếm do LLM viết, k=3–4 | `review.py:220-222`, `evidence.py:53` | Không ổn định; thiếu căn cứ; không bắt được nội dung thiếu | Vấn đề pháp lý là nút trong đồ thị; tra theo bảng trước | §8 |
| H8 | Đối chiếu thay đổi luật chỉ trên căn cứ của lần soát gần nhất | `review.py:264-277` | Căn cứ bị sót thì thay đổi cũng bị sót | Chạy trên mọi điều luật nối với hợp đồng trong đồ thị | §8.5 |
| H9 | Không có số trang | `contracts_api.py:106` | Không biết mở trang nào để đối chiếu | Giữ ranh giới trang | §5.1 |
| H10 | Không phát hiện mâu thuẫn giữa điều khoản | `review.py:22` | Điều 5 cho chấm dứt, Điều 12 cấm | Nhóm `conflict`, ứng viên lấy từ đồ thị | §9.4 |
| H11 | Lời giải thích của LLM có thể lệch phiên bản dù căn cứ đúng | `law_hint`, `explanation` | "Theo luật mới…" trong khi căn cứ là bản cũ | Kiểm tất định tên luật trong lời giải thích | §8.6 |
| H12 | Kịch bản demo coi phạt 20% là "vượt mức luật" | spec Phần 4 dòng 28-29; hợp đồng demo Điều 8 | Có thể kết luận sai với hợp đồng dân sự | Kiểm lại, đổi lỗi cài sẵn | §10.1 |
| H13 | Hình / bảng trên trang có chữ không được đọc | Ghi chú dự án `ocr-mixed-page-gap` | Bảng giá, lịch thanh toán dạng ảnh bị mất | Phát hiện và cảnh báo theo trang | §5.1 |
| H14 | Không phân quyền, không mã hóa, một tiến trình | `contracts_api.py:121-122`, `store.py` | Không mở cho người ngoài được | Quy tắc dữ liệu; nêu là hạn chế còn lại | §10.2, §12 |
| H15 | Hợp đồng không sửa được sau khi nạp; không thêm được phụ lục sau | `Contract` chỉ đổi được bên / ngày ký | Phụ lục ký sau → phải nạp lại, mất báo cáo | Nhật ký thao tác + bản dựng | §7 |
| H16 | Dữ kiện trích sai không ai sửa được | `extract_facts` chạy một lần | Sai bên, sai ngày → sai mọi thứ phía sau | Thao tác sửa có người duyệt | §7.3 |

## 4. Học gì từ Law-RAG, không học gì

Đã đọc: `law_rag/retrieval/graph/` (ontology, `neo4j_store.py`, `retrieve.py`, `structured_retrieve.py`),
`law_rag/extraction/legal_entities.py`, `scripts/build_neo4j_legal_graph.py`,
`scripts/audit_prune_neo4j_synonymy_edges.py`, `_check_semantic_edges.py`, `docker/neo4j-compose.yml`,
`evaluation/RAG_EVALUATION_REPORT.md`, `docs/kich_ban_phong_van_law_rag.md`.

Khác biệt gốc giữa hai bài toán, quyết định mọi lựa chọn bên dưới:

| | Law-RAG | Phần 5 |
|---|---|---|
| Đồ thị để làm gì | **Tìm** đoạn luật liên quan trong kho lớn (xếp hạng) | **Biểu diễn** một hợp đồng để đi đúng đường quan hệ và để người sửa |
| Quy mô | Một đồ thị chung, hàng chục nghìn nút | Mỗi hợp đồng vài trăm nút |
| Sai một cạnh thì sao | Một đoạn kém liên quan lọt vào top-k | Một câu trả lời sai về quyền / nghĩa vụ |
| Dữ liệu đổi thế nào | Dựng lại theo đợt bằng script | Người sửa từng mục, phụ lục thêm sau |
| Thời gian | Không có phiên bản (chính tài liệu của dự án ghi đây là việc sẽ làm) | Bắt buộc: luật tại mốc, hợp đồng tại ngày |

### 4.1 Lấy nguyên (chép code làm điểm xuất phát)

| Thứ lấy | Ở đâu | Dùng vào | Lưu ý khi dùng |
|---|---|---|---|
| Biểu thức nhận dẫn chiếu điểm / khoản / Điều | `ARTICLE_REF_RE` | §5.2 | Viết cho văn bản luật; cần thêm "Điều này", "khoản trên", "Phụ lục N", "Hợp đồng này" |
| Biểu thức số tiền, tỉ lệ, thời hạn | `MONEY_RE`, `PERCENT_RE`, `TIME_LIMIT_RE` | §5.3 | `MONEY_RE` chỉ nhận "đồng / triệu đồng / tỷ đồng"; hợp đồng còn có "VNĐ", "VND", "USD", số tiền bằng chữ trong ngoặc |
| Danh sách từ đánh dấu nghĩa vụ, quyền, cấm, điều kiện, ngoại lệ | `OBLIGATION_MARKERS`, `RIGHT_MARKERS`, `PROHIBITION_MARKERS`, `CONDITION_MARKERS`, `EXCEPTION_MARKERS` | Quy tắc chống mất điều kiện (§6.1) và gợi ý cho LLM | Từ ngắn như "khi ", "được " bắt nhầm nhiều — chỉ dùng làm **tín hiệu cảnh báo**, không dùng để tự sinh nút |
| Kiểm bằng chứng nhiều đoạn: trích dẫn được tách theo `;` hoặc `|`, **mọi** đoạn phải có trong văn bản; trích dẫn chứa "…" bị loại | `_evidence_parts`, `_evidence_is_verified` | Kiểm trích dẫn của mệnh đề (§7.3) | Đây là thứ `quote_ok` hiện tại thiếu: vế điều kiện và vế chính thường **không liền nhau** trong câu |
| Chuẩn hóa nhãn để so khớp (bỏ dấu, gộp ký tự) | `normalize_graph_label` | Gộp tên bên ("Bên A", "bên a", "BÊN A") | Chỉ để gộp; hiển thị vẫn dùng nguyên văn |

### 4.2 Lấy ý tưởng (viết lại)

| Ý tưởng | Ở đâu | Dùng vào |
|---|---|---|
| Lược đồ là **file dữ liệu**: lớp, quan hệ, miền và đích hợp lệ của từng quan hệ; cạnh sai kiểu bị loại | `legal_ontology.json`, `relation_allowed` | §6.2 |
| Các lớp Chủ thể, Điều kiện, Nghĩa vụ, Quyền, Hệ quả, Thời hạn, Số tiền | `legal_ontology.json › classes` | §6.1 — bỏ `Act`, `Concept`, `LegalElement`, `Penalty` (lý do ở §4.3) |
| Vấn đề pháp lý có điều luật **ưu tiên**, **liên quan**, **loại trừ**; nhóm vấn đề dễ nhầm | `issues[].preferred_articles / related_articles / negative_articles`, `disjoint_issue_groups` | §8.2 — "loại trừ" là thứ chặn lỗi phạt 20% |
| Trích bằng quy tắc trước, LLM sau, rồi gộp | `rule_extract` + `llm_extract` + `merge_extractions` | §5.3, §7.5 |
| Chỉ dựng vào đồ thị thứ đã kiểm bằng chứng; thứ chưa kiểm vẫn giữ nhưng có cờ | `validate_evidence`, `verified_item` | Trạng thái của mệnh đề (§7.3) |
| Ràng buộc duy nhất và chỉ mục khai báo một chỗ, chạy lại không lỗi | `ensure_schema` | §6.4 |
| Ghi theo lô bằng một câu lệnh nhận danh sách dòng | các hàm `upsert_*` | Ghi bản dựng vào Neo4j |
| Bật / tắt đồ thị bằng biến môi trường; đồ thị là đường bổ sung, văn bản gốc vẫn là căn cứ cuối | `graph_retrieval_enabled`, tài liệu phỏng vấn | §6.4, §9.3 |

### 4.3 Không lấy, và vì sao

| Thứ không lấy | Bằng chứng trong Law-RAG | Lý do |
|---|---|---|
| Tìm kiếm lan truyền (PageRank cá nhân hóa), phạt nút trung tâm, độ đặc hiệu của nút | `graph_ppr_retrieve`, `_hub_penalty`, `update_node_specificity` | Là công cụ xếp hạng trong đồ thị lớn. Đồ thị một hợp đồng cần đi đúng đường và đủ, không cần điểm xấp xỉ |
| Cạnh đồng nghĩa / tương tự khái niệm | `upsert_synonymy_edges`, `upsert_concept_similarities` — và dự án phải có riêng một script **rà và cắt** các cạnh này (`audit_prune_neo4j_synonymy_edges.py`) | Cạnh sinh tự động không có trích dẫn để kiểm; chính Law-RAG đã phải dọn. Với hợp đồng, một cạnh "tương tự" sai là một kết luận sai |
| Một lượt LLM trích 21 loại mục cùng lúc, có cả bộ ba tự do và câu truy vấn gợi ý | `LEGAL_SCHEMA_KEYS` (21 khóa, gồm `triples`, `useful_retrieval_queries`); phải thêm bộ lọc mục "khác" (`GENERIC_LEGAL_ELEMENT_NAMES`) | Lược đồ rộng → đầu ra loãng và khó duyệt. Phần 5 trích **5 loại mệnh đề** có hình dạng cố định (§7.3), không có bộ ba tự do |
| Lớp `Act`, `Concept`, `LegalElement`, `Penalty` | `legal_ontology.json › classes` | `Act` và `Concept` là lớp "chứa mọi thứ", sinh nhiều nút khó duyệt; `LegalElement` (yếu tố cấu thành) thuộc về luật hình sự; `Penalty` gộp vào `Consequence` |
| Ghi dồn kiểu "có thì cập nhật, chưa có thì thêm" trên đồ thị đang chạy | các hàm `upsert_*` dùng `MERGE` | Thứ không còn được sinh ra sẽ **nằm lại** trong đồ thị (nên mới cần script cắt tỉa). Phần 5 thay nguyên khối đồ thị của một hợp đồng ở mỗi lần dựng (§7.8) |
| Đồ thị luật (Văn bản, Điều, Đoạn) chứa văn bản luật | `upsert_articles`, nút `LegalChunk` | Không có phiên bản theo thời gian. Kho luật có phiên bản của dự án này là nguồn duy nhất; trong Neo4j chỉ có nút tham chiếu (§6.3) |
| Nối câu hỏi vào vấn đề bằng điểm từ khóa có trọng số | `match_ontology_issues` (các hệ số 0.18 / 0.34 / 0.28 / 0.2) | Các hệ số chỉnh tay khó giải thích và khó giữ khi danh mục đổi. Điều khoản được gán vấn đề **một lần lúc nạp**, có trích dẫn, người sửa được |
| Script kiểm tra rời đặt ở gốc dự án | `_check_semantic_edges.py` gọi `law_rag.retrieval.neo4j_store` — đường dẫn **không còn tồn tại** sau khi mã được dời sang `retrieval/graph/hippo_graph/` | Script rời thì hỏng mà không ai biết. Mọi kiểm tra đồ thị của Phần 5 nằm trong bộ kiểm thử |
| Mật khẩu viết thẳng trong file compose; nhãn ảnh trôi; cài thêm APOC | `NEO4J_AUTH: neo4j/lawrag-password`, `neo4j:2025-community`, `NEO4J_PLUGINS` | Mật khẩu lấy từ biến môi trường; ghim phiên bản ảnh cụ thể; không cần APOC cho bộ truy vấn §9.3 |

### 4.4 Bài học về đo lường (từ chính tài liệu của Law-RAG)

- Báo cáo đánh giá: độ bám nguồn 3,21/5; thời gian trả lời trung bình khoảng 14 giây, tối đa gần 29 giây. Có đồ thị
  không tự làm hai chỉ số này tốt hơn.
- Tài liệu phỏng vấn ghi thẳng: chưa khẳng định được đồ thị tốt hơn; dữ liệu thô của cặp lần chạy so sánh cũ **không
  còn đủ để tái lập**; nếu làm lại sẽ ghi phiên bản bộ câu hỏi, checksum kho, mô hình, cấu hình và lưu nguyên đầu ra
  của cả hai phía.

Phần 5 làm đúng điều đó từ đầu (§11.3): mỗi lần đo ghi đủ đầu vào để chạy lại được, và lưu nguyên đầu ra.

## 5. Từ file tới các đơn vị (không dùng LLM)

### 5.1 Tách văn bản

1. **Giữ ranh giới trang.** Đi qua từng trang, ghi vị trí ký tự → trang; mỗi đơn vị có trang đầu và trang cuối.
2. **Nhận diện phần.** Dòng tiêu đề "PHỤ LỤC …", "Phụ lục 01", "PHỤ LỤC HỢP ĐỒNG SỐ …" đứng riêng mở một phần mới.
   Nhiều file đính cùng lúc: mỗi file là một hoặc nhiều phần. Người dùng xác nhận / sửa danh sách phần trên thẻ hợp
   đồng (chỗ này bộ tách dễ sai nhất).
3. **Cây đánh số.** Nhận: `Điều N.` / `Điều N:`; `N.` `N.M` `N.M.K`; `Khoản N`; `a)` / `a.`; số La Mã cho mục lớn;
   `ARTICLE N` / `Clause N`. Chọn kiểu theo tính nhất quán trong chính văn bản (dãy số tăng liên tục).
4. **Không cắt.** Bỏ `DEMO_MAX_UNITS`. Chỉ còn giới hạn kỹ thuật có thông báo [Tôi chọn: 150 trang mỗi lần nạp]; vượt
   thì từ chối nạp, không nạp một phần.
5. **Báo cáo chất lượng tách**: kiểu đánh số; số Điều / khoản; chỗ đứt số; tỉ lệ văn bản không thuộc đơn vị nào; trang
   ít chữ bất thường hoặc có ảnh lớn ("trang N có thể chứa nội dung chưa đọc được" — H13). Có cảnh báo thì mọi báo cáo
   và câu trả lời mang dòng cảnh báo kèm số trang.

**Mã đơn vị** ổn định theo cấu trúc: `p0.d5`, `p0.d5.k2`, `p0.d5.k2.a`, `p1.d1` (p0 = hợp đồng chính). Mã không đổi
khi thêm phụ lục hay dựng lại — điều kiện để nhật ký thao tác (§7) trỏ đúng chỗ.

### 5.2 Dẫn chiếu nội bộ

Biểu thức chính quy trên từng đơn vị lá: "Điều N", "khoản M Điều N", "khoản M Điều này", "điểm a khoản M", "Phụ lục
N", "theo quy định tại …". Phân giải tương đối theo vị trí trong cây. Không phân giải được thì giữ lại và đánh dấu:
trỏ tới Điều không tồn tại là một phát hiện nhóm "mơ hồ"; trỏ ra luật ("Điều 328 Bộ luật Dân sự") là gợi ý cho §8.

### 5.3 Giá trị trích bằng quy tắc

Số tiền, tỉ lệ phần trăm, ngày, thời hạn ("trong vòng 30 ngày", "trước 15 ngày") được trích bằng quy tắc và gắn vào
đơn vị chứa chúng. LLM ở §6 chỉ **chọn** trong các giá trị đã trích, không tự gõ lại con số.

### 5.4 Kiểm trích dẫn

- Giữ cách so khớp nguyên văn của `quote_ok` cho file có chữ.
- **Thêm ngay từ đầu**: trích dẫn nhiều đoạn. Một trích dẫn có thể gồm vài đoạn không liền nhau trong cùng một đơn vị
  (vế điều kiện và vế chính của một câu dài); **mọi** đoạn phải có nguyên văn trong đơn vị nguồn; trích dẫn chứa dấu
  "…" bị loại. Cách làm lấy từ Law-RAG (§4.1). Thiếu thứ này thì LLM hoặc phải chép cả câu dài (dễ lệch một chữ), hoặc
  bỏ vế điều kiện.
- Bản chịu lỗi OCR (ba mức: nguyên văn / gần đúng / không khớp; không nới với chữ số và dấu tiếng Việt) là bước cuối
  trong thứ tự làm, chỉ cần khi bắt đầu nhận bản scan.

## 6. Đồ thị hợp đồng

### 6.1 Hai lớp

**Lớp cấu trúc** — sinh hoàn toàn bằng quy tắc từ §5, không có LLM, coi là đúng khi báo cáo tách sạch:

| Nút | Thuộc tính chính |
|---|---|
| `Contract` | mã hợp đồng, tên file, loại hợp đồng, tình trạng ký |
| `Part` | mã phần, loại (chính / phụ lục), tiêu đề, ngày ký riêng |
| `Unit` | mã đơn vị, **số phiên bản và khoảng hiệu lực** (§7.7), cấp (Điều / khoản / điểm), nhãn, văn bản, trang, vị trí ký tự — mỗi phiên bản của một đơn vị là một nút |
| `Value` | loại (tiền / tỉ lệ / ngày / thời hạn), giá trị chuẩn hóa, nguyên văn |

| Cạnh | Ý nghĩa |
|---|---|
| `HAS_PART`, `HAS_UNIT`, `CHILD_OF` | Cây văn bản |
| `REFERS_TO` (Unit → Unit) | Dẫn chiếu nội bộ, kèm câu dẫn chiếu |
| `HAS_VALUE` (Unit → Value) | Giá trị nằm trong đơn vị |

**Lớp ngữ nghĩa** — sinh từ các **mệnh đề** đã được chấp nhận (§7.3; LLM đề xuất hoặc người thêm), chỉ vào đồ thị
khi qua kiểm trích dẫn và kiểm kiểu:

| Nút | Ý nghĩa |
|---|---|
| `Party` | Một bên, kèm vai trò (Bên cho thuê…) |
| `Obligation` | Việc một bên **phải** làm |
| `Right` | Việc một bên **được** làm |
| `Condition` | Điều kiện, là **nút riêng** chứ không phải chú thích trên cạnh |
| `Consequence` | Hệ quả khi vi phạm hoặc khi một điều kiện xảy ra (phạt, mất cọc, chấm dứt…) |
| `Issue` | Vấn đề pháp lý, lấy từ danh mục (§8) |
| `LawRef` | Tham chiếu tới một điều luật trong kho có phiên bản (§6.3) |

| Cạnh | Từ → Tới | Ý nghĩa |
|---|---|---|
| `STATED_IN` | mọi nút ngữ nghĩa → `Unit` | **Bắt buộc**; mang câu trích nguyên văn |
| `OWES` / `HOLDS` | `Party` → `Obligation` / `Right` | Ai phải làm, ai được làm |
| `OWED_TO` | `Obligation` → `Party` | Làm cho ai |
| `REQUIRES` | `Obligation` / `Right` / `Consequence` → `Condition` | Chỉ áp dụng khi điều kiện thỏa |
| `EXCEPT_WHEN` | `Obligation` / `Right` → `Condition` | Ngoại lệ |
| `TRIGGERS` | `Condition` → `Consequence` | Điều kiện xảy ra thì dẫn tới hệ quả |
| `HAS_VALUE` | nút ngữ nghĩa → `Value` | Số tiền, thời hạn của nghĩa vụ / hệ quả |
| `RAISES` | `Unit` → `Issue` | Điều khoản đặt ra vấn đề pháp lý nào |
| `GOVERNED_BY` | `Issue` → `LawRef` | Lấy từ danh mục, không do LLM sinh |
| `AMENDS` | `Unit` (phụ lục) → `Unit` (gốc) | Thay / thêm / bỏ; kèm ngày có hiệu lực |
| `CONFLICTS_WITH` | `Unit` ↔ `Unit` | Mâu thuẫn đã được xác nhận (§9.4) |

Quy tắc chống mất điều kiện: khi câu nguồn của một `Right` hoặc `Obligation` có từ nối điều kiện ("nếu", "khi",
"trong trường hợp", "trừ khi", "với điều kiện", "sau khi") mà đề xuất của LLM **không** có cạnh `REQUIRES` /
`EXCEPT_WHEN` tương ứng, nút đó bị gắn trạng thái "cần xem lại" và không được dùng để trả lời một mình — câu trả lời
phải kèm nguyên văn điều khoản.

### 6.2 Mỗi nút và cạnh mang gì

- Mã nút ổn định giữa các lần dựng (suy từ mã đơn vị hoặc mã thao tác sinh ra nó — §7.5).
- `origin`: `rule` · `llm` · `human` · `catalogue`; `status`: `auto_accepted` · `approved` (thứ `pending` và `rejected`
  **không** được ghi vào Neo4j — chúng chỉ nằm trong nhật ký và hiện ở trang duyệt).
- Với nút ngữ nghĩa: mã thao tác sinh ra nó, mã đơn vị nguồn + số phiên bản, trích dẫn. Mọi nút: mã hợp đồng, mã bản dựng.
- Cờ "cần xem lại" khi vướng quy tắc chống mất điều kiện hoặc khi thao tác nguồn có mục chờ duyệt đang mở.

Lược đồ (lớp, quan hệ, miền và đích hợp lệ của từng quan hệ) là một file dữ liệu có **số phiên bản**, theo cách của
`legal_ontology.json`; mọi cạnh sai kiểu bị loại ở bước kiểm của bản dựng. Đổi lược đồ → mọi hợp đồng được dựng lại
(phiên bản lược đồ là một đầu vào của bản dựng, §7.8). Quy tắc tự chấp nhận ở §7.4.

### 6.3 Phía luật trong đồ thị: chỉ là tham chiếu

`LawRef` chỉ chứa số hiệu văn bản, số Điều, và mã điều trong kho có phiên bản. **Không chứa văn bản luật.** Mỗi khi cần
nội dung, hệ thống lấy từ kho có phiên bản theo mã điều + mốc thời gian (`provision_history` đã có). Như vậy:
- chỉ có một nơi giữ văn bản luật và lịch sử sửa đổi của nó;
- đồ thị không cũ đi khi luật được sửa — cùng một `LawRef`, mốc khác nhau trả văn bản khác nhau;
- câu hỏi ngược "luật X Điều Y vừa sửa, hợp đồng nào bị ảnh hưởng" là một lần đi trên đồ thị:
  `LawRef ← GOVERNED_BY ← Issue ← RAISES ← Unit ← … ← Contract`.

Một kiểm tra tự động sau mỗi snapshot kho luật xác nhận mọi `LawRef` còn phân giải được; cái không phân giải được bị
đánh dấu và báo ra.

### 6.4 Graph database

- **Neo4j bản cộng đồng**, chạy bằng Docker Compose, thư viện `neo4j` cho Python. [Tôi chọn — bạn đã chốt dùng graph
  database, dự án tham khảo dùng Neo4j, và nó có sẵn trình duyệt đồ thị để trình bày.]
- **Một cơ sở dữ liệu cho mọi hợp đồng**; mọi nút mang mã hợp đồng, mã nút là duy nhất toàn cục (`<mã hợp đồng>:<mã
  nút>`). Mọi truy vấn phục vụ một hợp đồng **bắt buộc** lọc theo mã hợp đồng — có kiểm thử riêng cho việc này. (Bản
  cộng đồng không có nhiều cơ sở dữ liệu tách biệt.)
- **PII**: thuộc tính văn bản trong Neo4j lưu ở dạng **đã che** (`[HD_…]`), giải che lúc hiển thị bằng trạng thái che
  của hợp đồng như Phần 4. Số tiền, ngày, tỉ lệ không che. [Tôi chọn — để dữ liệu trong graph database không nhạy cảm
  hơn thứ đã gửi cho LLM.]
- **Truy vấn**: một bộ nhỏ truy vấn Cypher **viết sẵn, có tham số**, đặt sau một giao diện Python (§9.3). LLM không viết
  Cypher.
- **Hạ tầng**: một file compose riêng cho Neo4j, **ghim phiên bản ảnh cụ thể**, mật khẩu và địa chỉ lấy từ biến môi
  trường, không cài thêm phần mở rộng. Máy cá nhân là đủ để phát triển và trình bày [Đã chốt].
- **Bản chạy chung**: vì Neo4j chỉ là dữ liệu dẫn xuất, một Neo4j dùng chung **không đủ** — nhật ký thao tác, file hợp
  đồng và kho luật nằm ở máy chạy ứng dụng. "Bản chung" đúng nghĩa là chạy **cả ứng dụng + Neo4j** trên một máy và
  cả nhóm mở qua trình duyệt. Việc đó chỉ cần cùng file compose và các biến môi trường, không cần thiết kế thêm; nhưng
  hệ thống chưa có tài khoản (§12) nên chỉ chạy chung trong mạng nội bộ của nhóm và chỉ với hợp đồng đã được phép
  chia sẻ. [Tôi chọn: làm máy cá nhân trước, bản chung là một bước triển khai, không phải bước thiết kế.]
- **Bật / tắt**: có biến môi trường. Khi tắt hoặc Neo4j không chạy, phần hợp đồng trở về hành vi Phần 4 (đã bỏ giới
  hạn) và nói rõ "đồ thị không sẵn sàng" — không âm thầm trả lời kém đi.
- **Kiểm thử**: logic dựng đồ thị từ nhật ký thao tác (§7) là Python thuần, cho ra danh sách nút / cạnh — kiểm thử
  không cần Neo4j. Chỉ một nhóm nhỏ kiểm thử tích hợp cần Neo4j và tự bỏ qua khi không có.

## 7. Phiên bản và sửa đồ thị — theo cơ chế kho luật

### 7.1 Nguyên tắc

`rag/legal/models.py`: *"AmendmentOperation là nguồn sự thật (bất biến về nội dung); ProvisionVersion là dữ liệu dẫn
xuất, dựng lại được hoàn toàn từ văn bản gốc + các thao tác."*

Điểm dễ hiểu sai (và bản nháp trước đã sai): trong kho luật, **các Điều gốc không nằm trong nhật ký thao tác** — chúng
được tách lại từ văn bản gốc mỗi lần dựng. Nhật ký chỉ chứa **những quyết định** làm thay đổi kết quả. Đồ thị hợp đồng
theo đúng cách đó:

| Kho luật | Đồ thị hợp đồng |
|---|---|
| Văn bản gốc (`raw/`, theo checksum) | File hợp đồng / phụ lục gốc (theo checksum) |
| `Provision` — tách từ văn bản, không lưu như thao tác | Lớp cấu trúc (§6.1): Phần, Đơn vị, Dẫn chiếu, Giá trị — tách lại từ file mỗi lần dựng |
| `AmendmentOperation` — bất biến, có `review_status`, người duyệt, ghi chú, `supersedes_operation_id` | `GraphOperation` — cùng các trường; chỉ chứa quyết định (§7.2) |
| `refresh_machine_operations` — chạy lại máy mà không mất quyết định của người | Cùng quy tắc (§7.5) |
| Thao tác áp không được → `pending` + phiên bản thành `needs_review` (`builder.py`) | Thao tác mồ côi → mục chờ duyệt, phần liên quan gắn "cần xem lại" (§7.8) |
| `BuildRun` (danh sách thao tác, checksum đầu vào, phiên bản code) | `GraphBuild` — như vậy, thêm phiên bản lược đồ và danh mục |
| `ProvisionVersion` — dẫn xuất, khoảng hiệu lực nửa mở | Phiên bản đơn vị + nút và cạnh trong Neo4j — dẫn xuất |
| `ReviewItem` / `ReviewDecision` (approve / reject / correct) | Dùng lại cùng hình dạng |
| Snapshot: dựng ở chỗ riêng → kiểm → công bố nguyên khối; một người ghi tại một thời điểm | Dựng trong bộ nhớ → kiểm → thay nguyên khối trong Neo4j; khóa ghi theo hợp đồng (§7.8, §7.9) |

**Neo4j không phải nguồn sự thật.** Xóa sạch Neo4j rồi dựng lại từ file gốc + nhật ký phải ra đúng đồ thị cũ.

### 7.2 Cái gì nằm trong nhật ký

| Nằm trong nhật ký (là quyết định) | Không nằm trong nhật ký (dựng lại được) |
|---|---|
| Bố cục phần: file nào / trang nào là hợp đồng chính, phụ lục nào — khi người dùng sửa kết quả tự nhận | Cây Điều / khoản / điểm, số trang |
| Giá trị trường của hợp đồng: loại hợp đồng, ngày ký, tình trạng ký, vai trò các bên | Dẫn chiếu nội bộ |
| Mệnh đề của lớp ngữ nghĩa (§7.3) — do LLM đề xuất hoặc người thêm | Số tiền, ngày, thời hạn trích bằng quy tắc |
| Phụ lục sửa điều khoản nào của hợp đồng gốc, từ ngày nào | Cạnh từ Vấn đề tới điều luật (lấy từ danh mục) |
| Mâu thuẫn đã xác nhận giữa hai điều khoản | |

Hệ quả: sửa lỗi trong bộ tách hay thêm mẫu dẫn chiếu thì chỉ cần dựng lại, không phải viết lại lịch sử.

### 7.3 Đơn vị sửa là **mệnh đề**, không phải nút và cạnh

Người duyệt nghĩ theo câu ("Bên B phải trả tiền thuê trước ngày 5 hằng tháng"), không theo nút và cạnh. Vì vậy thứ
được đề xuất, duyệt, sửa, bác là **mệnh đề** — một bản ghi có hình dạng cố định; bước dựng mới chuyển nó thành nút và
cạnh theo §6.1.

| Loại mệnh đề | Nội dung | Thành gì trong đồ thị |
|---|---|---|
| `party` | tên (dạng đã che), vai trò | `Party` |
| `duty` | loại: **phải làm** / **được làm** / **không được làm**; bên thực hiện; bên thụ hưởng (nếu có); nội dung; danh sách điều kiện; danh sách ngoại lệ; các giá trị (chọn trong giá trị đã trích bằng quy tắc) | `Obligation` (phải làm, hoặc không được làm — có cờ cấm) hoặc `Right`, các `Condition`, cạnh `OWES/HOLDS`, `OWED_TO`, `REQUIRES`, `EXCEPT_WHEN`, `HAS_VALUE` |
| `consequence` | điều kiện kích hoạt; hệ quả (phạt, mất cọc, chấm dứt, bồi thường…); bên chịu; giá trị | `Condition` → `TRIGGERS` → `Consequence` |
| `issue_link` | mã vấn đề trong danh mục | `Unit` → `RAISES` → `Issue` |
| `conflict` | hai đơn vị, mô tả | `CONFLICTS_WITH` |

Mọi mệnh đề bắt buộc có: mã đơn vị nguồn (và phiên bản của đơn vị đó), **trích dẫn** — một hoặc nhiều đoạn, mọi đoạn
phải có nguyên văn trong đơn vị nguồn (cách kiểm nhiều đoạn lấy từ Law-RAG, §4.1); `conflict` cần trích dẫn ở cả hai
đơn vị. Điều kiện nằm **trong** mệnh đề `duty`, nên duyệt một nghĩa vụ là duyệt luôn điều kiện của nó — không thể chấp
nhận nghĩa vụ mà bỏ rơi điều kiện.

### 7.4 Bốn loại thao tác

| Thao tác | Nội dung | Ai sinh |
|---|---|---|
| `SET_LAYOUT` | Bố cục phần của hợp đồng | Bộ tách đề xuất, người sửa |
| `SET_FIELD` | Một trường của hợp đồng hoặc của một bên | LLM (`extract_facts` hiện có), người |
| `ASSERT` | Một mệnh đề (§7.3) | LLM, người |
| `AMEND_UNIT` | Đơn vị đích, kiểu (thay / thêm / bỏ), đơn vị nguồn trong phụ lục, ngày có hiệu lực | Quy tắc, LLM, người |

Không có thao tác "xóa". Bỏ một thứ = đổi trạng thái thao tác sinh ra nó thành `rejected` (có người và ghi chú). Sửa
một thứ = thao tác mới thay thế thao tác cũ. Đây là cách kho luật đang làm (`set_review`, `supersede_operation`).

Mỗi thao tác mang: mã, mã hợp đồng, loại, nội dung, `origin` (`rule` / `llm` / `human`), `status` (`auto_accepted` /
`pending` / `approved` / `rejected`), lý do trạng thái, người duyệt, thời điểm, ghi chú, thao tác nó thay thế; với
thao tác do máy sinh: mô hình và phiên bản lời nhắc.

Tự chấp nhận [Đã chốt: theo đề xuất]: thao tác `rule`; thao tác `llm` có mọi đoạn trích dẫn khớp nguyên văn **và**
không vướng quy tắc chống mất điều kiện (§6.1). Ngoại lệ luôn chờ người: mọi `AMEND_UNIT` do máy đề xuất, mọi
`conflict`, và `SET_FIELD` cho ngày ký khi máy đọc ra nhiều hơn một ngày.

### 7.5 Mã ổn định và chạy lại máy

Lời nhắc, mô hình, bộ tách sẽ đổi; hợp đồng phải trích lại được mà **không mất việc người đã duyệt**.

- **Mã thao tác do máy sinh là hàm của nội dung**: mã hợp đồng + loại + đơn vị nguồn + nội dung đã chuẩn hóa. Chạy lại
  ra cùng mệnh đề → cùng mã → không sinh bản trùng.
- **Mã nút** trong đồ thị suy từ mã thao tác sinh ra nó, nên cũng ổn định giữa các lần dựng.
- Khi chạy lại bước trích cho một đơn vị (quy tắc chép từ `refresh_machine_operations`):

| Tình huống | Xử lý |
|---|---|
| Mệnh đề mới chưa từng có | Thêm |
| Trùng mã với thao tác cũ **chưa ai duyệt** | Ghi đè bằng đánh giá mới của máy |
| Trùng mã với thao tác **người đã duyệt hoặc bác** | Giữ quyết định của người |
| Thao tác máy cũ, chưa ai duyệt, lần này không còn được sinh ra | `rejected`, người duyệt = "system" |
| Thao tác **người đã duyệt** mà lần này máy không còn sinh ra | Giữ hiệu lực, **mở mục chờ duyệt** — không tự hủy quyết định của người |
| Thao tác do người tạo (`origin = human` hoặc là bản sửa) | Không bị đụng tới |

### 7.6 Sửa bởi người

Trên trang hợp đồng, mỗi điều khoản hiện các mệnh đề trích từ nó, viết thành câu, kèm trích dẫn được tô trong nguyên
văn:

| Hành động | Trong nhật ký |
|---|---|
| Duyệt | `status → approved` |
| Bỏ | `status → rejected` |
| Sửa (đổi bên, thêm điều kiện bị sót, đổi giá trị…) | `ASSERT` mới thay thế thao tác cũ; trích dẫn phải qua kiểm |
| Thêm thứ máy bỏ sót | `ASSERT` mới, `origin = human`; phải chọn đơn vị nguồn và đoạn trích |
| Sửa ngày ký, loại hợp đồng, vai trò bên, bố cục phần | `SET_FIELD` / `SET_LAYOUT` mới thay thế cái cũ |
| Hoàn tác về một bản dựng trước | Sinh các quyết định đảo ngược cho những thao tác được thêm / duyệt sau bản đó, rồi dựng bản mới |

Hoàn tác **không** phải là lùi con trỏ: lùi con trỏ mà nhật ký giữ nguyên thì lần dựng kế tiếp sẽ áp lại đúng những
thứ vừa bỏ. Lịch sử chỉ đi tới.

Mọi hành động ghi tên người (tên tự nhập như trang nạp văn bản pháp luật đang làm; chưa có tài khoản — §12).

### 7.7 Phụ lục và phiên bản đơn vị

Mỗi đơn vị có một hoặc nhiều **phiên bản**, mỗi phiên bản có văn bản và khoảng hiệu lực nửa mở `[từ, đến)`. Hợp đồng
chưa có phụ lục: mỗi đơn vị một phiên bản, bắt đầu từ ngày ký.

Phụ lục (tải cùng lúc hay tải sau đều qua cùng các bước):
1. File phụ lục được tách thành phần mới (`p1`, `p2`…); `SET_LAYOUT` ghi nhận.
2. Tìm chỗ phụ lục sửa hợp đồng gốc — quy tắc trước ("sửa đổi Điều 4 … như sau", "bổ sung khoản 3 vào Điều 7", "bãi
   bỏ Điều 9"), LLM cho phần còn lại → `AMEND_UNIT` ở trạng thái `pending`.
3. Người dùng xác nhận từng `AMEND_UNIT` (xem cạnh nhau: điều khoản gốc, câu trong phụ lục, kết quả sau sửa).
4. Dựng: kiểu **thay** đóng phiên bản cũ của đơn vị đích vào ngày có hiệu lực và mở phiên bản mới lấy văn bản từ đơn
   vị nguồn trong phụ lục; kiểu **thêm** tạo đơn vị mới trong cây của hợp đồng gốc, hiệu lực từ ngày đó; kiểu **bỏ**
   đóng phiên bản hiện tại. Không gì bị ghi đè.
5. Mệnh đề gắn với **một phiên bản đơn vị** và mang hiệu lực của phiên bản đó — không có khoảng hiệu lực riêng. Phiên
   bản mới của đơn vị được trích mệnh đề như một đơn vị mới; mệnh đề của phiên bản cũ giữ nguyên.
6. Báo cáo lập trước đó giữ nguyên nội dung, mang nhãn "lập trước Phụ lục N".

Ngày có hiệu lực của phụ lục: lấy từ phụ lục nếu nêu; không nêu thì là ngày ký phụ lục; không có cả hai thì
`AMEND_UNIT` không được xác nhận cho tới khi người dùng nhập ngày.

Nhờ vậy mọi truy vấn có tham số **"hợp đồng tại ngày nào"**, song song với "luật tại ngày nào". Phụ lục không sửa điều
khoản nào (chỉ thêm nội dung riêng) thì chỉ là một phần mới, không có `AMEND_UNIT`.

Bản dự thảo được bên kia gửi lại sau một vòng đàm phán **không** phải phụ lục: đó là một hợp đồng mới (so hai bản dự
thảo là việc của giai đoạn sau, dùng phép so hai bản dựng ở §7.8).

### 7.8 Dựng, kiểm, công bố

**Đầu vào của một bản dựng** (ghi checksum từng thứ): các file gốc · phiên bản bộ tách · danh sách thao tác đang có
hiệu lực (`auto_accepted` + `approved`, sau khi áp quan hệ thay thế) · phiên bản lược đồ đồ thị · phiên bản danh mục
vấn đề. Cùng đầu vào → cùng đồ thị. Bất kỳ đầu vào nào đổi → bản dựng cũ được coi là cũ và dựng lại.

**Các bước**
1. Tách file → lớp cấu trúc; áp `SET_LAYOUT`, `SET_FIELD`.
2. Áp `AMEND_UNIT` theo thứ tự ngày có hiệu lực → các phiên bản đơn vị.
3. Chuyển từng `ASSERT` thành nút và cạnh; nối `Issue` với `LawRef` theo danh mục.
4. **Kiểm** — bản dựng không qua thì **không công bố**, bản đang chạy giữ nguyên:
   - mọi cạnh đúng miền và đích theo lược đồ;
   - mọi nút ngữ nghĩa có đơn vị nguồn và trích dẫn khớp;
   - mọi nút mang đúng mã hợp đồng;
   - không có giá trị chưa che trong thuộc tính văn bản;
   - khoảng hiệu lực của các phiên bản một đơn vị không chồng nhau.
5. **Công bố**: trong một giao dịch Neo4j, xóa mọi nút và cạnh của hợp đồng đó rồi ghi bản mới. Người đọc không bao
   giờ thấy đồ thị dựng dở.

**Thao tác mồ côi.** Một thao tác trỏ tới đơn vị không còn tồn tại (bố cục phần bị sửa, bộ tách được sửa lỗi) hoặc
trích dẫn không còn khớp văn bản của đơn vị:
- thử **neo lại** bằng trích dẫn: nếu đoạn trích xuất hiện đúng một chỗ trong hợp đồng thì chuyển sang đơn vị đó và ghi
  lại việc chuyển;
- không neo lại được → thao tác **không được áp**, không bị xóa, sinh một mục chờ duyệt loại "mồ côi"; bản dựng vẫn
  được công bố và ghi số thao tác bị bỏ ngoài.

Đây là cách `builder.py` của kho luật xử lý thao tác áp không được (chuyển về `pending`, đánh dấu `needs_review`) thay
vì âm thầm bỏ qua hay dừng cả bản dựng.

**Lưu bản dựng.** Chỉ lưu bản ghi (mã, thời điểm, người / việc gây ra, checksum các đầu vào, danh sách mã thao tác,
kết quả kiểm). Đồ thị của một bản dựng cũ dựng lại được khi cần xem hoặc so sánh; Neo4j chỉ giữ bản đang công bố.
Hai bản dựng so được với nhau: mệnh đề và phiên bản đơn vị nào thêm, bớt, đổi.

Mọi báo cáo và câu trả lời ghi mã bản dựng nó dựa trên.

### 7.9 Ghi đồng thời

Một khóa ghi cho mỗi hợp đồng: thay đổi nhật ký + dựng + công bố là một khối, mỗi lúc một người. Người thứ hai nhận
thông báo "đang có thay đổi khác trên hợp đồng này" và tải lại — như `WriteLockedError` của kho luật. Đọc không bị
khóa.

### 7.10 Tương thích dữ liệu cũ

Hợp đồng đã lưu theo định dạng Phần 4 có sẵn file gốc: lần mở đầu tiên sau khi nâng cấp, nó được nạp qua đường mới
(tách, trích, dựng). Bên đã chọn và ngày ký người dùng đã nhập được chuyển thành `SET_FIELD` do người tạo. Báo cáo cũ
giữ nguyên, mang nhãn "lập trước khi có đồ thị".

## 8. Danh mục vấn đề pháp lý — chỗ nối với kho luật

### 8.1 Ý tưởng

Kho luật tổ chức theo điều luật, hợp đồng theo điều khoản. Nối hai bên bằng **vấn đề pháp lý**: danh mục nhỏ, ít đổi,
duyệt được. Trong đồ thị:

```
(Unit) ─RAISES→ (Issue) ─GOVERNED_BY→ (LawRef) ··· kho luật có phiên bản, tại mốc ···→ văn bản điều luật
  LLM gán, có trích dẫn      danh mục, người + LLM kiểm        tra theo mã điều + ngày
```

### 8.2 Hình dạng danh mục

File dữ liệu cạnh `seeds.yaml` [Tôi chọn: `data/team-4.2/legal/issues.yaml`], hình dạng mượn từ `legal_ontology.json`:

```yaml
- id: phat_vi_pham
  name: Phạt vi phạm hợp đồng
  describe: Điều khoản ấn định một khoản tiền bên vi phạm phải trả, không phụ thuộc thiệt hại thực tế…
  contract_types: [thue_nha, thue_mat_bang, mua_ban_nha_dat]   # rỗng = mọi loại
  provisions:        # điều luật điều chỉnh
    - {document: "91/2015/QH13", article: "418", applies_to: [dan_su], status: draft}
  not_applicable:    # điều luật DỄ BỊ ÁP NHẦM — phải loại
    - {document: "36/2005/QH11", article: "301", applies_to: [thuong_mai],
       reason: "Chỉ áp dụng cho quan hệ thương mại", status: draft}
  confused_with: [dat_coc, boi_thuong]     # dễ nhầm bản chất → luôn xét cùng nhau
```

và nội dung bắt buộc theo loại hợp đồng (`contract_type → required: [{issue, provision}]`).

Số Điều ở trên là **minh họa, chưa kiểm**. Loại hợp đồng đổi [Đã chốt: có thể đổi] thì chỉ đổi file này, không đổi code.

### 8.3 Người và LLM kiểm song song [Đã chốt]

Người kiểm trong nhóm **không có chuyên môn luật** nhưng tra cứu được trên mạng [Đã chốt]. Quy trình được thiết kế cho
đúng hoàn cảnh đó: người không được hỏi "điều này đúng không" (câu họ không trả lời được), mà được hỏi những câu
**đối chiếu được**.

Mỗi dòng điều luật trong danh mục đi qua hai bên kiểm độc lập, không bên nào thấy kết luận của bên kia trước:

| Bên | Việc làm | Ghi lại |
|---|---|---|
| LLM | Nhận mô tả vấn đề + **nguyên văn điều luật lấy từ kho có phiên bản** (không dùng trí nhớ) → trả: điều này có điều chỉnh vấn đề này không, cho loại quan hệ nào, lý do | phán quyết, lý do, mô hình, snapshot kho luật |
| Người | (1) Đọc nguyên văn điều luật trong kho: nó có nói về đúng vấn đề này không. (2) Tìm **ít nhất một nguồn bên ngoài** nêu điều luật này là căn cứ cho vấn đề này. (3) Với dòng `not_applicable`: tìm nguồn nêu rõ phạm vi áp dụng | phán quyết, tên, ngày, **đường dẫn nguồn và ngày truy cập** |

Nguồn bên ngoài được chấp nhận, theo thứ tự ưu tiên [Tôi chọn]: cổng văn bản pháp luật chính thức và cổng thông tin
của cơ quan nhà nước; án lệ và bản án đã công bố; bài viết của tổ chức hành nghề luật có nêu tên tác giả. Không chấp
nhận: câu trả lời của một mô hình AI, diễn đàn, bài không rõ nguồn.

| Kết quả | Trạng thái dòng |
|---|---|
| Hai bên cùng đồng ý **và** có đường dẫn nguồn | `verified` — được dùng để kết luận |
| Hai bên cùng đồng ý nhưng chưa có nguồn | `draft` |
| Hai bên cùng bác | `rejected` |
| Lệch nhau | `disputed` — không dùng để kết luận; chờ người thứ hai hoặc nguồn rõ hơn |
| Mới có một bên | `draft` |

LLM cũng được dùng để **đề xuất** dòng mới, nhưng điều luật nó đề xuất phải tồn tại trong kho có phiên bản thì mới
thành dòng `draft`; cái không có trong kho vào danh sách "luật còn thiếu trong kho".

Giới hạn phải nói thẳng: đây là kiểm bởi người không chuyên có nguồn tham khảo, không phải thẩm định pháp lý. Vì vậy
mỗi căn cứ "theo danh mục" hiển thị cho người dùng kèm đường dẫn nguồn đã đối chiếu, và mọi báo cáo ghi "căn cứ theo
danh mục do nhóm phát triển đối chiếu, không thay cho ý kiến luật sư".

### 8.4 Gán vấn đề và tìm căn cứ

- **Gán**: một lượt LLM theo lô lúc nạp; mỗi đơn vị lá chọn 0..n vấn đề **trong danh mục**, kèm trích dẫn → thao tác
  `LINK_ISSUE`. Mã ngoài danh mục bị bỏ. LLM được trả "khác" kèm mô tả — ghi lại để biết danh mục thiếu gì.
- **Tìm căn cứ hai tầng**:

| Tầng | Nguồn | Ghi trên căn cứ |
|---|---|---|
| 1 — theo đồ thị | `Unit → Issue → LawRef` với dòng `verified`, đúng loại quan hệ của hợp đồng, **trừ** các dòng `not_applicable`; văn bản lấy từ kho có phiên bản tại mốc | "theo danh mục" |
| 2 — tìm kiếm | `find_evidence` hiện có; kết quả trùng `not_applicable` của vấn đề đang xét bị loại | "tìm kiếm" |

  Cả hai tầng vẫn qua bước LLM kiểm "căn cứ này có thực sự hỗ trợ nhận định không" và các trạng thái kết luận của Phần
  4. Tầng 1 chỉ nói điều luật nào *liên quan*, không tự thành kết luận *vi phạm*.
- Điều luật trong danh mục chưa có trong kho tại mốc → từ chối kết luận, nêu đúng tên văn bản còn thiếu.

### 8.5 Nội dung bắt buộc và thay đổi luật

- **Thiếu nội dung bắt buộc** = danh sách bắt buộc của loại hợp đồng **trừ** các vấn đề có cạnh `RAISES` trong đồ thị.
  Mỗi mục thiếu được một lượt LLM xác nhận trên toàn văn rằng nội dung thực sự vắng (phòng bước gán sót) rồi mới báo.
- **Đối chiếu thay đổi luật** chạy trên mọi `LawRef` nối với hợp đồng qua đồ thị, cộng căn cứ đã dùng trong các báo
  cáo. Không còn phụ thuộc lần soát gần nhất.

### 8.6 Lời giải thích không nói từ trí nhớ

Sau khi kiểm chứng, lời giải thích / đề xuất chỉ được nêu tên văn bản và số Điều có trong căn cứ đã xác minh của chính
phát hiện đó. Kiểm tất định bằng mẫu ("Luật …", "Bộ luật …", "Nghị định …", "Điều N"); câu nào nhắc thứ không đối được
thì thay bằng ghi chú "chưa có căn cứ trong kho" (không xóa im lặng).

## 9. Dùng đồ thị để làm gì

### 9.1 Soát theo lô

Gom các Điều liền nhau theo ngân sách ký tự. Mỗi lô kèm ngữ cảnh chung (loại hợp đồng, các bên, định nghĩa) và nguyên
văn các đơn vị mà lô **dẫn chiếu tới** (lấy từ `REFERS_TO`), đánh dấu "chỉ để tham khảo". Lô lỗi: thử lại một lần; vẫn
lỗi thì báo cáo ghi lô đó **chưa soát**. Độ phủ: "đã soát X/Y đơn vị; Z trang có cảnh báo đọc".

### 9.2 Mốc thời gian tường minh

| Tình huống | Mốc tra luật | Mốc đọc hợp đồng |
|---|---|---|
| Đã có ngày ký | Ngày ký | Hôm nay (bản đang có hiệu lực), trừ khi câu hỏi nêu ngày khác |
| Bản dự thảo — người dùng chọn "chưa ký" | Ngày dự kiến ký nếu có, không thì hôm nay — ghi rõ | Bản dự thảo |
| Chưa rõ | **Không tra** (`blocked_no_date`), hỏi người dùng | — |
| Câu hỏi nêu một sự kiện có ngày | Ngày ký **và** ngày sự kiện, hai nhóm căn cứ tách bạch | Hợp đồng tại ngày sự kiện (§7.7) |

Không bao giờ ngầm dùng hôm nay. Hệ thống không tự quyết mốc nào là mốc áp dụng trong tranh chấp; nó trình bày theo
từng mốc và chỉ ra chỗ khác nhau. Phụ lục dùng ngày ký của chính nó.

### 9.3 Hỏi đáp: bộ truy vấn viết sẵn

Giao diện Python, mỗi hàm là một truy vấn Cypher có tham số (mã hợp đồng, ngày đọc hợp đồng):

| Truy vấn | Trả về |
|---|---|
| Hồ sơ một bên | Mọi nghĩa vụ và quyền của bên đó, kèm điều kiện, ngoại lệ, giá trị, điều khoản nguồn |
| Quanh một điều khoản | Điều khoản nó dẫn chiếu, điều khoản dẫn chiếu tới nó, điều khoản sửa nó, vấn đề, căn cứ |
| Theo vấn đề | Mọi điều khoản đặt ra một vấn đề (vd. chấm dứt) + điều kiện + hệ quả |
| Chuỗi hệ quả | Từ một điều kiện / sự kiện: hệ quả nào bị kích hoạt, nghĩa vụ nào liên quan (đi tối đa N bước) |
| Thời hạn và khoản tiền | Mọi `Value` kèm nghĩa vụ / hệ quả mang nó |
| Cần xem lại | Nút mang cờ "cần xem lại" (§6.2). Thứ đang chờ duyệt không nằm trong Neo4j — trang duyệt đọc từ nhật ký thao tác |
| Hợp đồng bị ảnh hưởng bởi một điều luật | Đi ngược từ `LawRef` (dùng nội bộ / khi luật đổi) |

Luồng một câu hỏi:
1. Một lượt LLM nhỏ chọn truy vấn và tham số **trong danh sách trên** (bên nào, vấn đề nào, điều khoản nào, ngày nào);
   không chọn được → dùng tìm kiếm văn bản trong hợp đồng như Phần 4.
2. Chạy truy vấn; lấy **nguyên văn** các đơn vị nguồn của mọi nút trả về.
3. LLM trả lời từ nguyên văn + cấu trúc đồ thị + căn cứ luật (§8.4). Đồ thị dùng để **chọn đúng và đủ điều khoản**,
   không thay cho việc đọc nguyên văn.
4. Câu trả lời ghi các điều khoản đã đọc, bản dựng, mốc; nếu có nút "chưa duyệt / cần xem lại" tham gia thì nói rõ.

Câu hỏi tra cứu đơn giản (thời hạn bao lâu, tiền cọc bao nhiêu) trả thẳng từ `Value` + điều khoản nguồn, có thể
không cần LLM ở bước 3.

### 9.4 Mâu thuẫn giữa các điều khoản

Ứng viên lấy từ đồ thị, không xét mọi cặp: hai `Unit` cùng `RAISES` một vấn đề; `Right` và `Obligation` của cùng một
bên trên cùng một việc; đơn vị gốc và đơn vị phụ lục sửa nó mà không có cạnh `AMENDS` rõ ràng. Một lượt LLM xác nhận
từng ứng viên, bắt buộc **hai trích dẫn**, cả hai qua kiểm. Được xác nhận → cạnh `CONFLICTS_WITH` + phát hiện nhóm
`conflict`. Là nhận xét về câu chữ: hệ thống không nói điều khoản nào thắng.

### 9.5 Những gì Phần 4 giữ nguyên

Tóm tắt, soát (`review`), redline, đối chiếu thay đổi luật, xuất Word/PDF, chế độ Think — giữ, chỉ đổi nguồn dữ liệu:
đơn vị mức khoản thay cho mức Điều, căn cứ hai tầng thay cho một lượt tìm kiếm, thêm trang và bản dựng vào mọi dẫn
chiếu.

### 9.6 Giao diện (tối thiểu)

- Thẻ hợp đồng: danh sách phần (sửa được), tình trạng ký, chất lượng đọc, bản dựng hiện tại, số mục chờ duyệt, nút
  "Thêm phụ lục".
- Trang điều khoản: mỗi điều khoản và các mệnh đề trích từ nó, viết thành câu, với Duyệt / Sửa / Bỏ / Thêm (§7.6).
- Hàng chờ duyệt: mệnh đề chờ duyệt, đề xuất sửa của phụ lục, thao tác mồ côi, quyết định của người mà máy không còn sinh ra.
- Phát hiện / căn cứ: "khoản 2 Điều 9 · trang 14", vấn đề pháp lý, nguồn căn cứ ("theo danh mục" / "tìm kiếm").
- Lịch sử: danh sách bản dựng, ai sửa gì, so hai bản dựng, hoàn tác (§7.6).
- Xem đồ thị bằng hình: mở trình duyệt Neo4j (dùng khi trình bày), không tự làm.

## 10. Việc phải làm trước và quy tắc dữ liệu

### 10.1 Sửa kịch bản demo (trước mọi việc khác)

Spec Phần 4 gọi mức phạt 20% (Điều 8 hợp đồng thuê nhà giữa hai cá nhân) là "vượt mức luật cho phép". Theo hiểu biết
của người viết, mức trần phạt là quy định của pháp luật thương mại, còn Bộ luật Dân sự để các bên thỏa thuận — **cần
người hiểu luật xác nhận**. Nếu đúng: đổi lỗi cài sẵn sang lỗi có căn cứ rõ trong luật đã có trong kho, và thêm ca kiểm
thử "phạt 20% trong hợp đồng dân sự không bị gắn nhãn Trái luật". Trường `not_applicable` ở §8.2 sinh ra từ đúng lỗi
này.

### 10.2 Hợp đồng thật trong lúc phát triển

- Hợp đồng thật, nhật ký thao tác, dữ liệu Neo4j, báo cáo: ở thư mục **không theo dõi bởi git**; kiểm `.gitignore`
  trước khi chép file đầu tiên. Kiểm thử tự động chỉ dùng hợp đồng tự soạn.
- Trước khi dùng một hợp đồng thật: chạy che PII và xem bằng mắt bản đã che; ghi lại loại thông tin bị sót.
- Mật khẩu Neo4j lấy từ biến môi trường, không viết trong file cấu hình được theo dõi (Law-RAG đang viết thẳng trong
  file compose — không chép chỗ đó).

### 10.3 Kho luật theo loại hợp đồng

Loại hợp đồng nào được hỗ trợ thì luật điều chỉnh nó phải có trong kho trước. Nhóm bất động sản hiện có Luật Đất đai,
Nhà ở, Kinh doanh bất động sản, Bộ luật Dân sự. **Chưa có**: Luật Thương mại (cần khi hai bên là thương nhân), Luật
Công chứng, và mọi nghị định / thông tư hướng dẫn. Vấn đề nào mà quy định nằm ở đó thì danh mục ghi "ngoài kho" và hệ
thống từ chối kết luận có nêu lý do.

## 11. Đo lường

### 11.1 Ba mức trên cùng bộ hợp đồng thật

| Mức | Hệ thống |
|---|---|
| A | Phần 4 (chỉ bỏ giới hạn 30 đơn vị để so công bằng) |
| B | Phần 5 không dùng lớp ngữ nghĩa: cây khoản + dẫn chiếu + vấn đề pháp lý |
| C | Phần 5 đầy đủ: thêm Nghĩa vụ / Quyền / Điều kiện / Hệ quả và bộ truy vấn §9.3 |

Bạn đã chọn làm graph database [Đã chốt] nên đo không còn để quyết "có làm không", mà để biết **lớp nào của đồ thị
đáng giữ cho loại câu hỏi nào** — và để có số liệu thật khi trình bày.

Chỉ số: tỉ lệ đơn vị tách đúng; dẫn chiếu phân giải đúng; với lớp ngữ nghĩa — tỉ lệ nút / cạnh đúng, và riêng **tỉ lệ
điều kiện bị bỏ sót**; với phát hiện — tìm ra và đúng nhóm; với căn cứ — đúng điều luật và đúng phiên bản tại mốc; từ
chối đúng lúc; độ ổn định (chạy 3 lần); với câu hỏi nhiều điều khoản — tỉ lệ điều khoản cần thiết được đưa vào; độ bám
nguồn của câu trả lời; số lượt LLM, token, thời gian (cả lúc nạp lẫn mỗi câu hỏi).

### 11.2 Định dạng đáp án (chốt bây giờ, sinh sau)

Mỗi hợp đồng một file, ghi kèm mã snapshot kho luật: `units`, `xrefs`, `amends`, `nodes` / `edges` lớp ngữ nghĩa (có
đơn vị nguồn), `issues` theo đơn vị, `findings`, `evidence` (văn bản, Điều, mốc), `questions` (câu hỏi, đơn vị cần đọc,
ý chính, có kết luận pháp lý hay phải từ chối). Khớp phát hiện: cùng đơn vị lá (hoặc cha / con trực tiếp) + cùng nhóm;
khớp căn cứ: (văn bản, Điều, phiên bản).

Trước khi có đáp án: các mệnh đề **đã được người duyệt** của một hợp đồng (§7.6) chính là đáp án cho lớp ngữ nghĩa của hợp
đồng đó — việc duyệt hằng ngày sinh ra dữ liệu đánh giá. Chất lượng tách và dẫn chiếu kiểm được không cần chuyên môn
luật.

### 11.3 Ghi lại mỗi lần đo (bài học từ Law-RAG, §4.4)

Mỗi lần đo lưu: phiên bản bộ câu hỏi và đáp án; mã bản dựng của từng hợp đồng; phiên bản lược đồ và danh mục; mã
snapshot kho luật; mô hình và phiên bản lời nhắc; cấu hình; và **nguyên đầu ra** của từng mức A / B / C. Hai lần đo chỉ
được so với nhau khi các đầu vào ngoài thứ đang so là giống nhau; báo cáo ghi rõ điều đó.

## 12. Hạn chế còn lại sau Phần 5

| Hạn chế | Vì sao chưa sửa | Giảm nhẹ |
|---|---|---|
| Lớp ngữ nghĩa do LLM trích có thể sai hoặc sót, nhất là điều kiện lồng nhau | Bản chất | Trích dẫn bắt buộc; quy tắc chống mất điều kiện; trạng thái duyệt; câu trả lời luôn đọc nguyên văn |
| Thứ `auto_accepted` chưa ai nhìn | Không đủ người duyệt hết | Chỉ tự chấp nhận khi trích dẫn khớp tuyệt đối; hiển thị nguồn gốc; đo tỉ lệ sai ở §11 |
| Câu hỏi nằm ngoài bộ truy vấn viết sẵn | Không cho LLM tự viết truy vấn | Rơi về tìm kiếm văn bản như Phần 4; ghi lại để bổ sung truy vấn |
| Thêm một dịch vụ phải chạy (Neo4j, Docker) | Hệ quả của việc chọn graph database | Bật / tắt bằng biến môi trường; tắt thì về hành vi Phần 4 và nói rõ |
| Chi phí lúc nạp tăng (thêm lượt LLM trích lớp ngữ nghĩa và gán vấn đề) | Trả trước để hỏi rẻ hơn | Chạy theo lô, báo tiến độ; cho dùng hợp đồng ngay khi lớp cấu trúc xong, lớp ngữ nghĩa bổ sung sau |
| Danh mục chỉ phủ vài loại hợp đồng | Mỗi loại cần công kiểm | Tầng tìm kiếm vẫn chạy; ghi lại vấn đề "khác" để mở rộng |
| Danh mục do người không chuyên kiểm, dựa vào nguồn trên mạng | Nhóm không có người hành nghề luật | §8.3: bắt buộc đường dẫn nguồn, thứ tự ưu tiên nguồn, hiển thị nguồn cho người dùng, dòng cảnh báo |
| Sửa bố cục phần hoặc sửa bộ tách có thể làm thao tác cũ mất chỗ bám | Mã đơn vị đi theo cấu trúc | Neo lại bằng trích dẫn; không được thì thành mục chờ duyệt, không âm thầm bỏ (§7.8) |
| Hai mệnh đề cùng ý nhưng khác câu chữ có thể cùng tồn tại sau khi trích lại | Mã theo nội dung chỉ bắt trùng khi nội dung chuẩn hóa giống nhau | Mệnh đề cũ chưa duyệt bị loại khi máy không còn sinh ra; mệnh đề đã duyệt thì mở mục chờ duyệt |
| Thiếu Luật Thương mại, nghị định, thông tư, án lệ | Ngoài kho hiện tại | Từ chối kết luận, nêu loại văn bản còn thiếu |
| Phụ lục sửa hợp đồng bằng câu chữ vòng vo ("các nội dung khác giữ nguyên trừ…") | Khó nhận diện bằng quy tắc | Luôn chờ người xác nhận `AMEND_UNIT` |
| Bảng / hình trên trang có chữ; chữ viết tay; dấu che chữ; bản scan | Ưu tiên file có chữ | Cảnh báo theo trang; kiểm trích dẫn chịu lỗi OCR làm sau |
| Không quyết mốc luật áp dụng trong tranh chấp | Là kết luận pháp lý | Trình bày theo từng mốc |
| "Bất lợi" là nhận định chủ quan | Bản chất | Giữ nhãn "không phải kết luận pháp lý" |
| Mọi hợp đồng chung một cơ sở dữ liệu, cách ly bằng lọc theo mã | Giới hạn bản cộng đồng | Mã nút duy nhất toàn cục; kiểm thử cách ly; lưu dạng đã che |
| Không phân quyền, không mã hóa, một tiến trình | Chưa mở cho người ngoài | §10.2; **không** đưa ra ngoài nhóm khi chưa làm phần này |
| Hợp đồng song ngữ / tiếng nước ngoài | Chưa có nhu cầu | Nhận kiểu đánh số tiếng Anh; chỉ phân tích phần tiếng Việt |

## 13. Thứ tự làm

| Bước | Nội dung | Sửa | Cần Neo4j | Cần người đối chiếu luật |
|---|---|---|---|---|
| 0 | Sửa kịch bản demo; quy tắc dữ liệu thật; `.gitignore` | H12 | — | Có (xác nhận) |
| 1 | Bộ tách mới: phần, cây khoản, trang, bỏ giới hạn, báo cáo chất lượng; giá trị bằng quy tắc | H1 H2 H3 H9 H13 | — | — |
| 2 | Dẫn chiếu nội bộ | — | — | — |
| 3 | Nhật ký thao tác (`SET_LAYOUT`, `SET_FIELD`) + bản dựng: dựng → kiểm → công bố nguyên khối + khóa ghi + hạ tầng Neo4j — **chỉ lớp cấu trúc** | H15 | Có | — |
| 4 | Soát theo lô; mốc thời gian tường minh; đọc hợp đồng theo ngày | H5 H6 | — | — |
| 5 | Phụ lục: tải cùng / tải sau, `AMEND_UNIT`, phiên bản đơn vị, xác nhận của người | H2 H15 | Có | — |
| 6 | Danh mục vấn đề + quy trình người / LLM kiểm có nguồn + gán vấn đề + căn cứ hai tầng + nội dung bắt buộc + thay đổi luật mở rộng + kiểm lời giải thích | H7 H8 H11 | Có | Có |
| 7 | Lớp ngữ nghĩa: trích mệnh đề (`ASSERT`), trích dẫn nhiều đoạn, quy tắc chống mất điều kiện, mã ổn định và quy tắc chạy lại máy | — | Có | — |
| 8 | Duyệt và sửa trên giao diện; hàng chờ duyệt; thao tác mồ côi; lịch sử, so hai bản dựng, hoàn tác | H16 | Có | — |
| 9 | Bộ truy vấn và hỏi đáp qua đồ thị; mâu thuẫn giữa điều khoản | H6 H10 | Có | — |
| 10 | Đo A / B / C trên hợp đồng thật | — | Có | đáp án (thiết kế riêng) |
| 11 | Kiểm trích dẫn chịu lỗi OCR — khi bắt đầu nhận bản scan | H4 | — | — |

Sau bước 3 đã có thứ trình bày được: hợp đồng thật hiện thành đồ thị trong Neo4j, không cắt, có trang, có dẫn chiếu.
Bước 1, 2, 4 không phụ thuộc Neo4j nên làm được song song với việc dựng hạ tầng.

## 14. Kiểm thử

Giữ toàn bộ kiểm thử Phần 4. Thêm (hợp đồng tự soạn):
- **Tách**: hợp đồng 60 Điều không mất đơn vị nào; các kiểu đánh số; đứt số được báo; phụ lục có Điều trùng số không lẫn.
- **Dẫn chiếu**: "khoản 1 Điều này", "Điều 9", trỏ tới Điều không tồn tại, trỏ ra luật.
- **Nhật ký và bản dựng**: cùng đầu vào → cùng đồ thị, cùng mã nút; xóa Neo4j rồi dựng lại ra đúng đồ thị cũ; thao tác
  `rejected` và `pending` không vào Neo4j; thay thế thao tác giữ được lịch sử; hoàn tác tạo bản dựng mới và lần dựng
  sau đó không áp lại thứ đã hoàn tác; bản dựng không qua bước kiểm thì đồ thị đang chạy không đổi; hai lần ghi cùng
  lúc trên một hợp đồng → lần sau bị từ chối.
- **Chạy lại máy** (sáu dòng của bảng §7.5, mỗi dòng một ca): không sinh bản trùng; thao tác chưa duyệt bị ghi đè;
  quyết định của người được giữ; thao tác máy không còn được sinh ra bị loại; thao tác người đã duyệt mà máy không còn
  sinh ra mở mục chờ duyệt; thao tác do người tạo không bị đụng tới.
- **Thao tác mồ côi**: sửa bố cục phần làm đổi mã đơn vị → thao tác được neo lại bằng trích dẫn; trích dẫn xuất hiện
  hai chỗ hoặc không còn → không áp, có mục chờ duyệt, bản dựng vẫn công bố và ghi số thao tác bị bỏ ngoài.
- **Trích dẫn nhiều đoạn**: đủ mọi đoạn → nhận; thiếu một đoạn → loại; có dấu "…" → loại.
- **Phụ lục tải sau**: đơn vị gốc còn nguyên với khoảng hiệu lực đóng; đọc hợp đồng trước và sau ngày phụ lục cho hai
  văn bản khác nhau; `AMEND_UNIT` do máy đề xuất không có hiệu lực khi chưa xác nhận; báo cáo cũ mang nhãn bản dựng cũ.
- **Lớp ngữ nghĩa**: cạnh sai kiểu bị loại; nút không có trích dẫn khớp bị loại; câu có "nếu" mà thiếu điều kiện →
  "cần xem lại".
- **Cách ly**: truy vấn của hợp đồng A không bao giờ trả nút của hợp đồng B.
- **PII**: không có giá trị chưa che trong thuộc tính ghi vào Neo4j.
- **Danh mục**: dòng `draft` / `disputed` không tạo kết luận; dòng hai bên đồng ý nhưng thiếu đường dẫn nguồn vẫn là `draft`; `not_applicable` chặn căn cứ sai loại quan hệ (ca phạt
  20%); điều luật trong danh mục không có trong kho → từ chối nêu đúng tên văn bản; `LawRef` không phân giải được sau
  snapshot mới bị báo.
- **Mốc**: bản dự thảo dùng hôm nay và ghi rõ; chưa chọn thì chặn; câu hỏi có ngày sự kiện trả hai nhóm căn cứ.
- **Neo4j tắt**: hệ thống chạy như Phần 4 và nói rõ đồ thị không sẵn sàng.
- Lô soát bị làm lỗi có chủ đích → "chưa soát", không báo sạch. Lời giải thích nhắc luật ngoài căn cứ → bị thay.

## 15. Thay đổi ở bản nháp 3 và những chỗ cần bạn xem lại

Không còn câu hỏi mở nào chặn việc lập kế hoạch. Ba câu ở bản trước đã được trả lời và đưa vào §7.4, §8.3, §6.4.

**Sửa cơ chế sửa đồ thị (§7) — sau khi đọc kỹ `rag.legal`**

| Bản nháp 2 | Vấn đề | Bản nháp 3 |
|---|---|---|
| Lớp cấu trúc (phần, đơn vị, dẫn chiếu, giá trị) được ghi thành thao tác trong nhật ký | Không đúng cách kho luật làm (Điều gốc được tách lại từ văn bản, không lưu như thao tác); sửa một lỗi của bộ tách sẽ phải viết lại lịch sử | Nhật ký chỉ chứa **quyết định**; lớp cấu trúc dựng lại từ file (§7.2) |
| 12 loại thao tác ở mức nút / cạnh / thuộc tính | Người duyệt phải nghĩ theo nút và cạnh; duyệt được nghĩa vụ mà bỏ rơi điều kiện của nó | Đơn vị sửa là **mệnh đề**; còn 4 loại thao tác; điều kiện nằm trong mệnh đề (§7.3, §7.4) |
| Có thao tác xóa nút / xóa cạnh | Thừa | Bỏ = `rejected`, sửa = thay thế, như kho luật |
| Không nói gì về việc trích lại khi đổi lời nhắc / mô hình | Trích lại sẽ sinh bản trùng hoặc xóa mất việc người đã duyệt | Mã theo nội dung + sáu quy tắc chép từ `refresh_machine_operations` (§7.5) |
| "Quay lại bản cũ = đổi con trỏ" | Nhật ký giữ nguyên nên lần dựng kế tiếp áp lại đúng thứ vừa bỏ | Hoàn tác = sinh quyết định đảo ngược, lịch sử chỉ đi tới (§7.6) |
| Nút ngữ nghĩa có khoảng hiệu lực riêng | Hai nơi cùng giữ thời gian, dễ lệch | Mệnh đề gắn với một **phiên bản đơn vị** và mang hiệu lực của nó (§7.7) |
| Không nói gì khi thao tác trỏ tới đơn vị không còn | Hoặc hỏng bản dựng, hoặc âm thầm mất | Neo lại bằng trích dẫn; không được thì thành mục chờ duyệt (§7.8) |
| Ghi thẳng vào Neo4j | Người đọc có thể thấy đồ thị dựng dở hoặc sai kiểu | Dựng → kiểm → công bố nguyên khối; không qua kiểm thì không công bố (§7.8) |
| Không nói về hai người sửa cùng lúc | Mất thay đổi | Khóa ghi theo hợp đồng (§7.9) |
| Danh mục và lược đồ đổi thì sao — không nói | Đồ thị cũ lệch với danh mục mới | Cả hai là đầu vào có phiên bản của bản dựng (§7.8) |

**Sửa phần học từ Law-RAG (§4) — sau khi đọc thêm phần trích xuất, script cắt tỉa và tài liệu của dự án**

- **Thêm — lấy nguyên**: các biểu thức dẫn chiếu, số tiền, thời hạn; danh sách từ đánh dấu nghĩa vụ / quyền / điều
  kiện / ngoại lệ; cách kiểm trích dẫn nhiều đoạn (thứ `quote_ok` đang thiếu).
- **Thêm — không lấy**: lượt trích 21 loại mục; các lớp `Act` / `Concept` / `LegalElement` / `Penalty`; cách ghi dồn
  để lại rác; script kiểm tra rời (một script trong Law-RAG đã hỏng vì trỏ tới đường dẫn không còn tồn tại); mật khẩu
  viết thẳng trong file compose.
- **Thêm — bài học đo lường**: chính tài liệu Law-RAG ghi rằng lần so sánh cũ không tái lập được → §11.3.
- **Bỏ**: dòng "nhóm đã quen Neo4j" làm lý do chọn — đó là suy đoán của người viết.

**Quyết định của người viết, cần bạn xem lại**

1. Mọi đề xuất sửa của phụ lục và mọi mâu thuẫn **luôn** chờ người, kể cả khi trích dẫn khớp (§7.4) — ngoại lệ của mức
   tự chấp nhận bạn đã chọn.
2. Thứ `pending` không được ghi vào Neo4j (§6.2); chỉ hiện ở trang duyệt.
3. Thứ tự ưu tiên nguồn khi tra trên mạng, và không chấp nhận câu trả lời của mô hình AI làm nguồn (§8.3).
4. "Bản chung" = chạy cả ứng dụng và Neo4j trên một máy trong mạng nội bộ; làm sau máy cá nhân (§6.4).
5. Bỏ các lớp `Act` / `Concept` khỏi lược đồ; "không được làm" là một loại của mệnh đề `duty` (§7.3).
6. Bản dự thảo gửi lại sau đàm phán là hợp đồng mới, không phải phụ lục (§7.7).
7. Neo4j chỉ giữ bản dựng đang công bố; bản cũ dựng lại khi cần (§7.8).

## 16. Để người xây quyết

Tên trường, bảng và module cụ thể; cách lưu nhật ký thao tác (theo kiểu `LegalStore`); ngân sách lô; mẫu biểu thức
chính quy; lời nhắc cho LLM; cách đi từ (số văn bản, số Điều) tới mã điều trong kho; cách phát hiện trang nghi chưa đọc
hết từ thông tin bộ nạp hiện có; số bước tối đa của truy vấn chuỗi hệ quả; cách hiển thị so sánh hai bản dựng; cách chuẩn hóa nội dung để tính mã thao tác; cách khóa ghi; phiên bản ảnh Neo4j
được ghim; cách hiển thị mệnh đề thành câu.
