# Tham khảo: thị trường và nghiên cứu về đồ thị hợp đồng — các hướng giải quyết cho vấn đề đang gặp

Ngày: 12/11/2026 · Loại: **tài liệu tham khảo, không phải thiết kế** · Đi kèm:
`2026-11-12-contract-scale-design.md` (bản nháp 3).

Tài liệu này **không sửa** bản thiết kế. Nó gom lại các hướng mà sản phẩm và nghiên cứu khác đã dùng cho từng vấn đề
dự án đang gặp, kèm mức độ đã kiểm chứng. Mọi hướng ở đây chỉ là **ứng viên**; việc đưa hướng nào vào thiết kế chỉ quyết
sau khi có số liệu benchmark trên hợp đồng thật.

Ký hiệu mức kiểm chứng:
**[Đọc gốc]** đã đọc tài liệu / bài báo gốc · **[Tài liệu hãng]** chỉ có tài liệu hoặc thông cáo của chính hãng ·
**[Thứ cấp]** chỉ có bài tổng hợp, blog, diễn đàn · **[Chưa kiểm được]** không tìm thấy nguồn.

---

## 1. Các vấn đề đang gặp

| # | Vấn đề | Nguồn gốc |
|---|---|---|
| V1 | Hợp đồng thật dài, nhiều điều khoản: phải đọc đủ và tìm **đủ** điều khoản liên quan cho một câu hỏi | Bản thiết kế §3 (H1, H6) |
| V2 | Trích xuất bằng LLM làm **mất điều kiện / ngoại lệ** ("A được chấm dứt *nếu* B chậm trả quá 30 ngày") | Bản thiết kế §2, §6.1 |
| V3 | Phụ lục sửa hợp đồng gốc, tải cùng hoặc tải sau; cần biết **hợp đồng tại một ngày** | Bản thiết kế §7.7 |
| V4 | Nối điều khoản với **luật Việt Nam đúng phiên bản tại mốc** (ngày ký / ngày sự kiện) | Bản thiết kế §8, §9.2 |
| V5 | Người **sửa đồ thị**, có lịch sử; chạy lại máy không làm mất việc người đã duyệt | Bản thiết kế §7 |
| V6 | Mọi kết luận **truy ngược** được về câu gốc trong hợp đồng | Bản thiết kế §2, §6.2 |
| V7 | Người duyệt **tin quá mức** vào kết quả máy; không biết thứ tự chấp nhận sai bao nhiêu | Bản thiết kế §7.4, §12 |
| V8 | **Đo** được giá trị của đồ thị so với cách không có đồ thị | Bản thiết kế §11 |
| V9 | Hợp đồng và luật **tiếng Việt** | Bối cảnh dự án |

## 2. Ba hướng tiếp cận trên thị trường

### 2.1 Đồ thị để tìm kiếm

**Ai làm**: Multi-View Contract Graph (MCG, NORA 2026) [Đọc gốc]; Law-RAG (PageRank cá nhân hóa) [Đọc gốc — mã nguồn];
Microsoft GraphRAG, LightRAG [Thứ cấp].

**Cách làm (MCG, đọc từ bài gốc)**
- Nút: đoạn văn hợp đồng, tách theo độ giống nghĩa giữa các câu liền kề.
- Mỗi nút có: embedding (all-MiniLM-L6-v2), tập thực thể (Flair NER), tập từ khóa.
- Cạnh: một điểm số, không dùng LLM, không có loại quan hệ:
  `0,25 × cosine embedding + 0,25 × Jaccard thực thể + 0,25 × Jaccard từ khóa + 0,25 × 1/|khoảng cách vị trí|`
  (hệ số chia đều, không tinh chỉnh).
- Truy vấn: chấm điểm mọi nút với câu hỏi → lấy 2 nút neo → mở rộng sang hàng xóm theo điểm cạnh → đưa 5 đoạn cho LLM.

**Kết quả công bố (MCG)**
- CUAD, 15/41 nhóm thông tin, năm mô hình 7–8B mã mở.
- F1 tốt nhất 0,460 (Mistral-7B-Instruct-v0.3); cùng mô hình: BM25-RAG 0,418, ColBERT-RAG 0,410 → tăng khoảng 10,0% và
  12,2%. Thắng ở 4/5 mô hình.
- Ablation (bỏ từng loại cạnh): bỏ giống nghĩa 0,409; bỏ thực thể 0,438; bỏ từ khóa 0,444; bỏ vị trí 0,451.
- Giới hạn tác giả tự nêu: chi phí tính cặp O(n²); quan hệ thiết kế tay, phụ thuộc chất lượng NER và từ khóa; tập đánh
  giá hẹp. Bài không báo độ dao động giữa các lần chạy.

**Giải quyết được**: V1 (đây đúng là bài toán của họ), V6 (nút chính là đoạn văn gốc), V8 (có cách đo và có số).
**Không giải quyết**: V2, V3, V4, V5 — không trích, không có thời gian, không ai sửa đồ thị.

### 2.2 Đồ thị để biểu diễn tri thức

**Ai làm**
- NCKG — Nested Contract Knowledge Graph (Zheng, Kassem và cộng sự; arXiv 2309.12132, bản 2 tháng 5/2025)
  [Thứ cấp — tóm tắt và trang arXiv]. Thông tin "đã đăng ở *Automation in Construction*, DOI 10.1016/j.autcon.2025.106179"
  **[Chưa kiểm được]**.
- Các bài hướng dẫn Neo4j trên CUAD (Agentic GraphRAG for commercial contracts; GraphRAG in action) [Tài liệu hãng].
- ContractRabbit — tài liệu, bên tham gia, loại tài liệu, lớp điều khoản, thuộc tính, trích dẫn **[Chưa kiểm được]**:
  không tìm thấy tài liệu công khai; mô tả chỉ đến từ đoạn tổng hợp người dùng cung cấp.

**Cách làm**
- NCKG: biểu diễn tri thức về các mẫu hợp đồng chuẩn (FIDIC, NEC) bằng đồ thị **lồng nhau** — dùng RDF-star để gắn điều
  kiện, quan hệ nhân quả, quan hệ phối hợp lên chính một quan hệ khác. Theo tóm tắt, tri thức do chuyên gia định hướng.
  LLM dùng đồ thị này (qua GraphRAG) để soát rủi ro hợp đồng EPC. Đánh giá: 143 điều khoản, 335 bộ ba, **179 bộ ba lồng
  nhau**; so với LLM thuần và RAG vector, NCKG cho kết quả tốt nhất (GPT-4, LLaMA-3).
- Neo4j / CUAD: LLM trích theo schema (loại điều khoản, bên, luật áp dụng…) vào Neo4j; agent truy vấn bằng Cypher kết hợp
  tìm kiếm vector. Mạnh ở câu hỏi gộp trên nhiều hợp đồng ("bao nhiêu hợp đồng có điều khoản X").

**Giải quyết được**
- V2: NCKG là bằng chứng mạnh nhất rằng bộ ba phẳng làm mất điều kiện — hơn một nửa (179/335) quan hệ của họ phải lồng
  nhau mới biểu diễn đúng.
- V6: Neo4j / CUAD giữ văn bản gốc cạnh dữ liệu trích.
- Đối chiếu hợp đồng với một **nguồn tri thức chuẩn** (NCKG: tri thức chuyên gia về mẫu hợp đồng) — cùng dạng bài toán
  với V4, nhưng nguồn chuẩn không có chiều thời gian.

**Không giải quyết**: V3, V4 (phần phiên bản theo thời gian), V5. NCKG dựng cho mẫu chuẩn với tri thức chuyên gia, chưa
cho thấy cách làm với hợp đồng bất kỳ do bên kia soạn. Bài hướng dẫn Neo4j không báo độ chính xác trích xuất so với nhãn
CUAD.

### 2.3 Sản phẩm thương mại

**Ai làm**
- Luminance [Tài liệu hãng]: nền tảng phát hành lại tháng 1/2026. Phân tích "họ hợp đồng" (hợp đồng gốc, phụ lục, thư bổ
  sung, thỏa thuận liên quan) như một quan hệ đang tiến triển và xác định điều khoản nào đang có hiệu lực; truy vấn trên
  cả họ hợp đồng và nghĩa vụ; "bộ nhớ dài hạn" gồm lịch sử đàm phán, hợp đồng liên quan, tiền lệ trong danh mục hợp đồng.
  Tên "Context Graph" và con số "hơn 1.300 khái niệm pháp lý" **[Chưa kiểm được]**. Tài liệu không nói họ có dùng graph
  database hay không.
- Icertis Vera [Tài liệu hãng]: knowledge graph là một thành phần kiến trúc; quản lý nghĩa vụ, phát hiện nghĩa vụ ẩn
  trong câu chữ; phân tích xuyên nhiều hợp đồng. Không có chi tiết kỹ thuật công khai.
- Docusign Iris / Evisort (Workday mua năm 2024), Kira (Litera) [Tài liệu hãng / Thứ cấp]: trích xuất có người duyệt.

**Điểm chung quan trọng**: thứ họ đối chiếu hợp đồng là **chuẩn nội bộ của doanh nghiệp** — playbook, điều khoản mẫu được
duyệt, tiền lệ đàm phán, danh mục nghĩa vụ — **không phải văn bản luật theo phiên bản**. Khách hàng tự định nghĩa và tự
chịu trách nhiệm về chuẩn đó.

**Giải quyết được**: V3 (ý tưởng "điều khoản đang hiệu lực trong họ hợp đồng"), V6, một phần V7 (quy trình duyệt).
**Không giải quyết công khai**: V4, V5 (có quy trình duyệt nhưng không công bố cơ chế), V8 (không có số liệu độc lập).

## 3. Các cơ chế ngoài lĩnh vực hợp đồng, dùng được cho V3, V5, V7

Không sản phẩm hợp đồng nào công bố cách sửa đồ thị có lịch sử. Các hệ dưới đây giải bài tương tự ở lĩnh vực khác.

| Hệ | Cơ chế | Vấn đề liên quan | Mức kiểm chứng |
|---|---|---|---|
| **Graphiti / Zep** (đồ thị tri thức theo thời gian cho agent) | Mỗi cạnh có hai trục thời gian: đúng ngoài đời từ / đến khi nào (`valid_at`, `invalid_at`) và hệ thống ghi nhận / vô hiệu khi nào (`created_at`, `expired_at`). Không xóa cạnh, chỉ vô hiệu. Truy vấn tại một thời điểm. Một lượt LLM tự phát hiện cạnh mới mâu thuẫn cạnh cũ và tự vô hiệu | V3 | [Thứ cấp]; tên trường cần đối chiếu mã nguồn |
| | Một bài phản biện: tự động vô hiệu không nên được coi là có thẩm quyền với tri thức cần kiểm duyệt | V3, V7 | [Thứ cấp] |
| **Palantir Foundry** (người sửa đè lên dữ liệu nguồn) | Mỗi lần sửa là một giao dịch; thay đổi đồng thời → thất bại, không ghi đè. Chiến lược xung đột theo từng nguồn: "bản sửa của người thắng" hoặc "giá trị mới nhất thắng" | V5 | [Tài liệu hãng] |
| | Vấn đề người dùng gặp: bản sửa của người đè cả trường không hề sửa; dòng nguồn bị xóa nhưng đối tượng vẫn còn; xin tính năng "bỏ bản sửa, quay về dữ liệu nguồn"; đổi chiến lược không áp ngược | V5 | [Thứ cấp — diễn đàn] |
| **Wikidata** | Không xóa phát biểu sai, hạ bậc (`deprecated`) kèm **lý do hạ bậc** có cấu trúc; mỗi phát biểu có nguồn riêng; truy vấn mặc định chỉ trả bậc tốt nhất. Nguyên tắc: lưu phát biểu kèm nguồn, không phán chân lý | V5, V7 | [Thứ cấp] |
| **Microsoft GraphRAG** | Cập nhật bằng cách thêm tài liệu mới, gộp thực thể trùng; theo một bài so sánh, sửa / xóa tài liệu phải lập chỉ mục lại toàn bộ | V5 | [Thứ cấp] |
| **LightRAG** | Thêm / xóa tài liệu tại chỗ; xóa thì dựng lại từ **bộ đệm kết quả trích**, không gọi LLM lại | V5 | [Thứ cấp] |
| **FalkorDB GraphRAG SDK** | Mã băm SHA-256 theo nội dung, nội dung không đổi thì bỏ qua; xóa tài liệu chỉ dọn thực thể mồ côi của tài liệu đó; thực thể còn tài liệu khác dùng thì giữ | V5 | [Tài liệu hãng] |
| **Datomic** | Dữ kiện bất biến; cập nhật = thêm dữ kiện; truy vấn "tại thời điểm" (`as-of`) | V3, V5 | [Tài liệu hãng] |
| **TerminusDB** | Commit, nhánh, so sánh, gộp như git trên cả đồ thị | V5 | [Tài liệu hãng] |
| **Công cụ soát hợp đồng** (hướng dẫn của TextMine, Oneflow; Kira) | Người soát theo **mức rủi ro** của điều khoản, không chỉ theo độ tin cậy máy tự báo; dùng 50–100 hợp đồng đầu để hiệu chỉnh loại nào cần người xem; ghi lại người, bằng chứng, quy tắc, quyết định. Cảnh báo **thiên kiến tự động hóa**: người duyệt soi kết quả AI lỏng hơn việc của đồng nghiệp. Kira công bố mỗi trường dựng sẵn đạt tối thiểu 90% recall | V7 | [Thứ cấp]; con số của Kira là [Tài liệu hãng] |

Hai nguồn khác cùng hướng với V3:
- Bài arXiv 2604.14220 (2026): dùng cạnh `SUPERSEDES` và `REFERS_TO` để xử lý phiên bản và phụ thuộc nhiều bước trong văn
  bản pháp lý [Thứ cấp — chỉ đọc tóm tắt].
- Một bài viết về GraphRAG cho văn bản pháp lý: sửa đổi nên tạo phiên bản mới thay vì ghi đè nút [Thứ cấp].

## 4. Đối chiếu tổng hợp

| Vấn đề | Tìm kiếm (MCG…) | Biểu diễn (NCKG, Neo4j/CUAD) | Thương mại (Luminance, Icertis) | Cơ chế ngoài lĩnh vực (§3) |
|---|---|---|---|---|
| V1 Tìm đủ điều khoản | **Có, có số liệu** | Gián tiếp, qua truy vấn quan hệ | Có nói, không số liệu | — |
| V2 Giữ điều kiện / ngoại lệ | Không | **Có** (NCKG: quan hệ lồng nhau) | Không rõ | — |
| V3 Phụ lục, hợp đồng tại một ngày | Không | Không | **Có ý tưởng**, không rõ cách làm | Graphiti, Datomic, bài arXiv `SUPERSEDES` |
| V4 Nối luật VN đúng phiên bản | Không | Một phần: NCKG đối chiếu với tri thức chuẩn, không có thời gian | Không — đối chiếu với playbook | — |
| V5 Người sửa đồ thị, có lịch sử | Không cần | Không đề cập | Có quy trình, không công bố cơ chế | Palantir, Wikidata, LightRAG, FalkorDB, Datomic, TerminusDB |
| V6 Truy ngược về câu gốc | Có | Có | Có | Wikidata (nguồn theo từng phát biểu) |
| V7 Tin quá mức vào máy | — | — | Có quy trình duyệt | Công cụ soát hợp đồng, Wikidata, Graphiti (phản biện) |
| V8 Đo được giá trị | **Có** (CUAD, tiếng Anh) | NCKG: quy mô nhỏ | Không có số liệu độc lập | — |
| V9 Tiếng Việt | Không | Không | Không | — |

## 5. Hướng giải quyết theo từng vấn đề (ứng viên, chờ benchmark)

| Vấn đề | Hướng đã có người dùng | Nguồn | Đã có trong thiết kế bản nháp 3? |
|---|---|---|---|
| V1 | Lấy vài điều khoản neo rồi mở rộng sang hàng xóm theo điểm giống nghĩa / thực thể / từ khóa / vị trí | MCG | Chưa — thiết kế mở rộng theo dẫn chiếu có loại (`REFERS_TO`), không theo điểm giống |
| V1 | Truy vấn có cấu trúc trên đồ thị (Cypher) cho câu hỏi theo bên / vấn đề / điều kiện | Neo4j/CUAD | Có (§9.3, truy vấn viết sẵn) |
| V2 | Biểu diễn điều kiện **lồng vào** quan hệ thay vì bộ ba phẳng | NCKG (RDF-star) | Có, bằng cách khác: điều kiện nằm trong mệnh đề và là nút riêng (§6.1, §7.3); Neo4j không có RDF-star |
| V3 | Đọc hợp đồng gốc + phụ lục như một "họ", xác định điều khoản đang hiệu lực | Luminance | Có (§7.7: `AMEND_UNIT`, phiên bản đơn vị) |
| V3 | Hai trục thời gian: hiệu lực ngoài đời và thời điểm hệ thống ghi nhận | Graphiti | Có ngầm (khoảng hiệu lực + thời điểm trong nhật ký), chưa gọi tên |
| V3 | Không xóa, chỉ vô hiệu; truy vấn tại một thời điểm | Graphiti, Datomic | Có (§7.4, §7.7) |
| V3 | Tự động vô hiệu bằng LLM khi phát hiện mâu thuẫn | Graphiti | Không — thiết kế bắt người xác nhận `AMEND_UNIT`; bài phản biện về Graphiti ủng hộ cách này |
| V3 | Mở rộng "họ hợp đồng" sang thư bổ sung, thỏa thuận liên quan | Luminance | Chưa — ngoài phạm vi |
| V4 | Đối chiếu với một nguồn tri thức chuẩn có cấu trúc | NCKG (tri thức chuyên gia), thương mại (playbook) | Có, nguồn chuẩn là kho luật có phiên bản + danh mục vấn đề (§8) — **không ai công bố cách làm có chiều thời gian** |
| V5 | Sửa = giao dịch; thay đổi đồng thời thì thất bại, không ghi đè | Palantir | Có một phần (khóa ghi §7.9); chưa có kiểm tra "đang sửa trên bản dựng cũ" |
| V5 | Nút "bỏ bản sửa của người, quay về đề xuất của máy" | Palantir (người dùng yêu cầu) | Chưa |
| V5 | Hạ bậc kèm **lý do có cấu trúc** thay vì xóa | Wikidata | Có hạ bậc (`rejected`), chưa có mã lý do — chỉ ghi chú tự do |
| V5 | Bộ đệm kết quả trích theo nội dung; dựng lại không gọi LLM lại | LightRAG, FalkorDB | Chưa |
| V5 | Mã băm theo nội dung; không đổi thì bỏ qua; chỉ dọn mồ côi trong phạm vi của tài liệu | FalkorDB | Có (mã theo nội dung §7.5, thao tác mồ côi §7.8) |
| V5 | Nhánh để thử thay đổi mà không đụng bản chính | TerminusDB | Chưa — ngoài phạm vi |
| V6 | Trích dẫn / nguồn theo từng phát biểu | Tất cả; Wikidata | Có (§6.2, §7.3) |
| V7 | Duyệt theo **mức rủi ro** của loại điều khoản, không chỉ theo độ tin cậy | Công cụ soát hợp đồng | Chưa — thiết kế tự chấp nhận theo bằng chứng (trích dẫn khớp) |
| V7 | Hiệu chỉnh trên 50–100 hợp đồng đầu: loại nào máy hay sai thì chuyển sang chờ duyệt | Công cụ soát hợp đồng | Chưa |
| V7 | Ghi người, bằng chứng, quy tắc, quyết định cho mỗi lần duyệt | Công cụ soát hợp đồng | Có (§7.4) |
| V8 | So với BM25 / dense / ColBERT trên cùng bộ câu hỏi, có ablation từng thành phần | MCG | Có một phần (§11: mức A / B / C) |
| V8 | Ghi phiên bản bộ câu hỏi, kho, mô hình, cấu hình; lưu nguyên đầu ra để tái lập | Bài học từ Law-RAG | Có (§11.3) |
| V9 | — | Không có | — |

## 6. Khoảng trống: không ai công bố lời giải

1. **V4 — đối chiếu hợp đồng với luật theo phiên bản thời gian.** Sản phẩm thương mại đối chiếu với playbook doanh
   nghiệp; nghiên cứu đối chiếu với tri thức chuyên gia không có thời gian. Đây là điểm khác biệt chính của dự án — và là
   phần rủi ro nhất, vì kết luận sai về luật nặng hơn lệch so với playbook.
2. **V5 cho hợp đồng.** Không có cơ chế sửa đồ thị hợp đồng có lịch sử được công bố. Nguồn tham khảo gần nhất là các cơ
   chế quản lý dữ liệu chung (§3) và cơ chế thao tác + bản dựng của kho luật trong chính dự án (`rag.legal`).
3. **V9 — tiếng Việt.** Mọi số liệu hiện có (MCG, NCKG, CUAD) là hợp đồng tiếng Anh; không chuyển thẳng sang được.

## 7. Hệ quả cho việc benchmark

- Các bài học thuật chỉ đo **tìm kiếm / hỏi đáp** (V1, V8). Không có bộ chuẩn công khai nào đo V2, V3, V4, V5.
- MCG là đối chứng tự nhiên cho câu hỏi "có cần đồ thị để **tìm đủ** điều khoản không": không cần LLM lúc dựng, công
  thức và tham số đã công bố đầy đủ, có mã nguồn công khai theo bài báo.
- Giá trị của đồ thị biểu diễn — giữ điều kiện, hợp đồng tại một ngày, căn cứ luật đúng phiên bản, sửa có lịch sử — phải
  tự thiết kế phép đo; các chỉ số liên quan đã liệt kê ở §11.1 của bản thiết kế (tỉ lệ điều kiện bị bỏ sót, căn cứ đúng
  phiên bản tại mốc, tỉ lệ sai của thứ được tự chấp nhận…).
- Số liệu của MCG cần đọc đúng giới hạn: F1 tuyệt đối 0,46; mô hình 7–8B; thắng 4/5 mô hình; không báo độ dao động; hệ
  số chia đều không tinh chỉnh.

## 8. Nguồn

**Đọc gốc**
- Multi-View Contract Graph — [ACL Anthology](https://aclanthology.org/2026.nora-1.5/) · [PDF](https://aclanthology.org/2026.nora-1.5.pdf)
- Law-RAG — `C:\Users\Admin\Desktop\Law-RAG` (mã nguồn, `evaluation/RAG_EVALUATION_REPORT.md`, `docs/kich_ban_phong_van_law_rag.md`)

**Nghiên cứu, đọc qua tóm tắt / trang giới thiệu**
- NCKG — [arXiv 2309.12132](https://arxiv.org/abs/2309.12132) · [EC3 2024](https://ec-3.org/wp-content/uploads/2025/10/EC32024_178.pdf) · [Newcastle University](https://research.ncl.ac.uk/kassem/newsevents/recentpublicationfromteam.html)
- [arXiv 2604.14220](https://arxiv.org/html/2604.14220) · [Temporal semantics in GraphRAG for legal documents](https://sergeyvasiliev.substack.com/p/temporal-semantics-in-graphrag-for)
- [COMPACT: clause graph reasoning (EACL 2026)](https://aclanthology.org/2026.eacl-long.377) · [GRAPH-GRPO-LEX](https://arxiv.org/html/2511.06618v1) · [Contract knowledge graphs overview](https://api.emergentmind.com/topics/contract-knowledge-graphs)

**Sản phẩm thương mại**
- Luminance — [thông cáo 2026](https://www.luminance.com/press/luminance-launches-new-legal-ai-with-institutional-memory-addressing-enterprise-amnesia-and-giving-legal-teams-30-of-their-time-back) · [Contract Intelligence](https://www.luminance.com/contract-intelligence/) · [IT Brief UK](https://itbrief.co.uk/story/luminance-unveils-ai-platform-to-tackle-enterprise-amnesia)
- Icertis — [When contracts finally have context](https://www.icertis.com/research/blog/when-contracts-finally-have-context-everything-changes/) · [Contract extraction](https://www.icertis.com/learn/automate-contract-extraction/)
- Neo4j / CUAD — [Agentic GraphRAG for commercial contracts](https://neo4j.com/blog/developer/agentic-graphrag-for-commercial-contracts/) · [GraphRAG in action](https://neo4j.com/blog/developer/graphrag-in-action/) · [From legal documents to knowledge graphs](https://neo4j.com/blog/developer/from-legal-documents-to-knowledge-graphs/)
- Soát hợp đồng có người duyệt — [TextMine](https://textmine.com/learn/how-to-use-ai-contract-review-software-with-human-approval) · [Oneflow](https://oneflow.com/uk/blog/ai-contract-review/) · [Litera Kira](https://prep.litera.com/products/legal2/kira/patented-machine-learning/) · [Ironclad / Evisort / SpotDraft](https://theneuralbase.com/ai-for-legal/learn/intermediate/tools-ironclad-evisort-spotdraft/)
- ContractRabbit — không tìm thấy nguồn công khai.

**Cơ chế ngoài lĩnh vực**
- Graphiti / Zep — [temporal model](https://mintlify.com/getzep/graphiti/concepts/temporal-model) · [Beyond static knowledge graphs](https://blog.getzep.com/beyond-static-knowledge-graphs/) · [bài phản biện](https://zby.github.io/commonplace/agent-memory-systems/reviews/graphiti/)
- Palantir — [How user edits are applied](https://www.palantir.com/docs/foundry/object-edits/how-edits-applied/) · [Consistency and isolation](https://palantir.com/docs/foundry/action-types/consistency-guarantees/) · [Conflict resolution strategies](https://community.palantir.com/t/introducing-conflict-resolution-strategies-for-ontology-user-edits-and-datasource-updates-ga/346) · [Reset / discard user edits](https://community.palantir.com/t/fr-reset-discard-user-edits-and-fall-back-to-backing-dataset/6521/1)
- Wikidata — [Help:Ranking (lưu trữ)](https://webcf.waybackmachine.org/web/20220322134249/https://www.wikidata.org/wiki/Special:MyLanguage/Help:Ranking) · [Reason for deprecated rank](https://portal.mardi4nfdi.de/wiki/Property:P263)
- GraphRAG / LightRAG / FalkorDB — [GraphRAG update](https://www.mintlify.com/microsoft/graphrag/cli/update) · [LightRAG vs GraphRAG](https://particula.tech/blog/lightrag-vs-graphrag) · [FalkorDB incremental updates](https://docs.falkordb.com/graphrag/incremental-updates.md)
- Datomic / TerminusDB — [Datomic data model](https://docs.datomic.com/whatis/data-model.html) · [TerminusDB](https://terminusdb.com/docs/terminusdb-explanation)
