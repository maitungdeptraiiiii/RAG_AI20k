# Đồ thị corpus luật (bản nháp 1)

Ngày: 2026-11-13. Phạm vi: **chỉ corpus luật**. Lớp cầu nối (khái niệm, rule, ngưỡng) và phía hợp đồng
(xác minh dữ kiện, LLM đọc điều khoản) có bản thiết kế riêng, viết sau.

Tài liệu liên quan:
- Kho luật có phiên bản: `2026-11-09-legal-version-builder-design.md` (nguồn dữ liệu của đồ thị này).
- Đồ thị hợp đồng: `2026-11-12-contract-scale-design.md` (không sửa; đồ thị luật dùng lại cơ chế dựng / công bố).
- Tham khảo: `C:\Users\Admin\Desktop\Law-RAG` (xem §9, vì sao không làm theo).

## 1. Vì sao làm

Mục tiêu cuối: khi soát một hợp đồng lao động, hệ thống chỉ ra điều khoản nào trái luật hoặc bất lợi, lệch bao
nhiêu, kèm đúng khoản luật áp dụng **tại ngày ký**. Để làm được, phía luật phải trả lời chắc chắn năm câu hỏi mà
vector / BM25 không trả lời được:

1. Lời văn của điều khoản X tại ngày D là gì?
2. Điều khoản X đã thay đổi thế nào giữa hai ngày?
3. Nghị định, thông tư nào quy định chi tiết điều khoản X?
4. Điều khoản X dẫn chiếu tới những điều khoản nào (và ngược lại)?
5. Trong một chuỗi văn bản thay thế nhau (lương tối thiểu vùng), văn bản nào áp dụng ngày D?

Kho luật hiện tại (`rag.legal`, SQLite) đã có câu 1 và 2 ở mức dữ liệu. Câu 3, 4, 5 chưa có: 56 văn bản chứa
khoảng 16.000 chỗ dẫn chiếu trong lời văn (6.800 chỗ sang văn bản khác) chưa được lưu thành quan hệ, và quan hệ
"hướng dẫn thi hành" không tồn tại.

## 2. Mục tiêu, ngoài mục tiêu, điều phải tránh

**Mục tiêu**
- Một đồ thị luật trong Neo4j, dựng tất định từ snapshot kho luật đã công bố, trả lời năm câu hỏi ở §1.
- Mọi nút điều khoản có mã ổn định và phiên bản theo ngày, để lớp cầu nối neo rule vào.
- Sửa ba chỗ hổng của kho làm đồ thị không dùng được (§7).

**Ngoài mục tiêu**
- Không thay vector / BM25 cho chat hỏi luật. Pipeline cũ giữ nguyên, chạy song song.
- Không có lớp khái niệm, rule, ngưỡng, chủ thể, quyền / nghĩa vụ. Thuộc bản thiết kế cầu nối.
- Không dùng LLM, không dùng embedding ở tầng này.

**Điều phải tránh**
- Đồ thị lệch với kho luật (hai nguồn sự thật). Đồ thị chỉ là dữ liệu dẫn xuất, xóa đi dựng lại được.
- Một quan hệ sai mà trông như đúng. Dẫn chiếu không giải được phải được ghi là chưa giải được, không đoán.
- Sửa `parse_structure` làm đổi lời văn điều khoản đã công bố (sẽ đổi checksum, phiên bản và chunk vector).

## 3. Mô hình

### 3.1 Nút

Mọi nút mang nhãn chung `LGNode` và thuộc tính `build_id`.

| Nhãn | Khóa | Thuộc tính chính |
|---|---|---|
| `LawDoc` | `key` = document_key (`bo-luat:45/2019/QH14`) | `doc_type`, `doc_number`, `title`, `issuer`, `issued_on`, `effective_from`, `effective_to`, `eff_status`, `is_consolidated` |
| `Provision` | `pid` = provision_id (`bo-luat:45/2019/QH14#d25.k1`) | `kind` (article / clause / point), `article`, `clause`, `point`, `label` ("khoản 1 Điều 25"), `order` |
| `ProvisionVersion` | `vid` = `pid@valid_from` | `text`, `title` (với Điều), `lead_in` (với khoản có điểm), `heading_path`, `valid_from`, `valid_to`, `verification_status`, `status_reasons`, `unresolved_refs` |
| `Appendix` | `aid` = `key#pl<n>` | `number`, `title`, `kind` (list / form / other), `text`, `span` |

Quyết định:
- **Danh tính tách khỏi phiên bản.** `Provision` không chứa lời văn. Quan hệ trỏ vào `Provision`; người hỏi chọn
  phiên bản theo ngày. Một điều khoản bị bãi bỏ vẫn còn nút danh tính, phiên bản cuối có `valid_to`.
- **Tên Điều và đoạn mở đầu khoản là thuộc tính của phiên bản**, không phải nút riêng (kho hiện lưu thành
  `article_title` / `clause_lead_in`). Lý do: không rule hay dẫn chiếu nào trỏ riêng vào chúng.
- **Chương / Mục là thuộc tính `heading_path`**, không phải nút.
- **Khoảng hiệu lực nửa mở** `[valid_from, valid_to)`, giống kho.

### 3.2 Quan hệ

| Quan hệ | Từ → Tới | Thuộc tính | Nguồn |
|---|---|---|---|
| `HAS_PROVISION` | LawDoc → Provision (Điều) | | kho |
| `CHILD_OF` | Provision → Provision | | kho |
| `HAS_VERSION` | Provision → ProvisionVersion | | kho |
| `HAS_APPENDIX` | LawDoc → Appendix | | mới (§7.2) |
| `AMENDS`, `REPLACES`, `REPEALS`, `CONSOLIDATES` | LawDoc → LawDoc | `evidence` | kho (`DocumentRelation`) |
| `GUIDES` | LawDoc → LawDoc | `evidence` | mới (§5.1) |
| `BASED_ON` | LawDoc → LawDoc | `evidence` | mới (§5.1) |
| `REFERS_TO` | ProvisionVersion → Provision \| LawDoc \| Appendix | `raw`, `kind` (cite / details), `offset` | mới (§5.2) |
| `CHANGED_BY` | ProvisionVersion → Provision | `operation_id`, `operation_type` | kho (`source_operations`) |

"Chuỗi kế tiếp" (câu hỏi 5) không cần quan hệ riêng: đi theo `REPLACES` từ văn bản bất kỳ trong chuỗi rồi chọn
văn bản có `[effective_from, effective_to)` chứa ngày D.

Danh sách nút và quan hệ hợp lệ ghi trong `schema.json`; bước kiểm tra từ chối mọi thứ ngoài danh sách.

## 4. Dựng và công bố

```
snapshot kho luật đã công bố (SQLite + raw text)
   → build (tất định, thuần Python): nút + cạnh + báo cáo
   → validate
   → ghi Neo4j dưới build_id mới → đổi con trỏ → xóa build cũ
```

- **Đầu vào duy nhất** là một snapshot đã công bố. `build_id` = băm của (`snapshot_id`, `GRAPH_VERSION`). Cùng
  đầu vào cho cùng đồ thị.
- **Công bố nguyên khối bằng con trỏ.** Đồ thị luật lớn hơn đồ thị hợp đồng (ước lượng 60.000 nút, hơn 100.000
  cạnh) nên không ghi trong một giao dịch. Ghi theo lô dưới `build_id` mới; khi xong mới cập nhật nút
  `LGMeta {current_build}`; sau đó xóa build cũ. Mọi truy vấn lọc theo `current_build`, nên người đọc không bao
  giờ thấy đồ thị dở dang.
- **Cùng instance Neo4j** với đồ thị hợp đồng, khác nhãn (`LGNode` so với `CGNode`). Cấu hình dùng lại
  `NEO4J_*`; bật bằng `LEGAL_GRAPH=1`.
- **Kích hoạt:** lệnh `python -m rag.legal graph build` (dựng, kiểm tra, công bố) và `graph check` (chỉ dựng và
  in báo cáo, không ghi). Khi `LEGAL_GRAPH=1`, sau mỗi lần kho công bố snapshot mới, đồ thị được dựng lại.
- **Neo4j sập không chặn kho luật.** Snapshot vẫn công bố; đồ thị được đánh dấu "chưa cập nhật" kèm
  `snapshot_id` nó đang phản ánh. Lớp cầu nối phải kiểm tra dấu này trước khi dùng.
- **Vector / BM25 không bị đụng tới.** Chúng đọc cùng snapshot nên không lệch với đồ thị.

**Kiểm tra trước khi công bố** (lỗi nào cũng dừng, không ghi):
- Số `Provision` và `ProvisionVersion` khớp với kho cho từng văn bản.
- Không có khóa trùng; mọi cạnh có đủ hai đầu; nhãn và quan hệ thuộc `schema.json`.
- Với mỗi `Provision`, các phiên bản không chồng khoảng hiệu lực.
- Mọi `REFERS_TO` có `raw` xuất hiện đúng ở `offset` trong `text` của phiên bản nguồn.

## 5. Quan hệ mới và cách suy ra

### 5.1 Hướng dẫn thi hành (`GUIDES`, `BASED_ON`)

- `GUIDES`: tên văn bản dưới luật có cụm "quy định chi tiết" hoặc "hướng dẫn thi hành" kèm tên hoặc số hiệu một
  luật có trong kho. Ví dụ NĐ 145/2020 → BLLĐ 45/2019; TT 08/2026 → NĐ 337/2025.
- `BASED_ON`: mỗi dòng "Căn cứ …" ở phần mở đầu trỏ tới văn bản có trong kho. Ví dụ NĐ 293/2025 (lương tối
  thiểu) → BLLĐ. Yếu hơn `GUIDES`: chỉ nói văn bản này ban hành dựa trên luật đó.
- Tên luật không kèm số hiệu được giải bằng cơ chế "họ luật" đã có (`law_family`), lấy văn bản hiệu lực tại ngày
  ban hành của văn bản nguồn.

### 5.2 Dẫn chiếu (`REFERS_TO`)

Lời văn luật viết dẫn chiếu theo thể thức cố định, nên dùng một bộ phân tích theo mẫu (không LLM). Một dẫn chiếu
gồm phần địa chỉ ("điểm a khoản 1 Điều 35", "các khoản 1, 2 và 3 Điều 20", "Điều 21 và Điều 22") và phần văn bản
đích. Quy tắc giải văn bản đích, theo thứ tự:

1. Có số hiệu ("Nghị định số 122/2020/NĐ-CP") → đúng văn bản đó.
2. Có tên luật ("của Bộ luật Lao động") → họ luật, văn bản hiệu lực tại `valid_from` của phiên bản nguồn.
3. "Luật này", "Bộ luật này", "Nghị định này", "Điều này", "khoản này" → cùng văn bản / cùng Điều / cùng khoản.
4. Không ghi văn bản, nằm trong Điều phạm vi điều chỉnh của một văn bản có đúng một `GUIDES` → văn bản được
   hướng dẫn, `kind = details`. Ví dụ Điều 1 NĐ 145/2020: "Hợp đồng lao động theo khoản 4 Điều 21; điểm d khoản 1
   Điều 35…" → các điều khoản đó của BLLĐ.
5. Không ghi văn bản, các trường hợp còn lại → cùng văn bản.

Ngoài quy tắc 4, `kind = details` cũng được gán khi câu nguồn có cụm "quy định chi tiết" / "hướng dẫn" đứng
trước dẫn chiếu tới văn bản được `GUIDES`. Mọi trường hợp khác là `cite`.

Dẫn chiếu không tạo cạnh khi: văn bản đích không có trong kho (`doc_not_in_store`), điều khoản đích không tồn tại
(`provision_not_found`), hoặc tên luật khớp nhiều họ (`ambiguous_law`). Các trường hợp này ghi vào
`unresolved_refs` của phiên bản nguồn và vào báo cáo dựng, kèm lý do.

Dẫn chiếu nằm trong đoạn trích dẫn của văn bản sửa đổi ("…" sau "sửa đổi, bổ sung như sau:") không được phân
tích ở văn bản sửa đổi; chúng được phân tích ở phiên bản mới của điều khoản đích, nơi lời văn đó thực sự có hiệu lực.

### 5.3 Được sửa bởi (`CHANGED_BY`)

Mỗi `ProvisionVersion` có `source_operations` trong kho. Với mỗi thao tác, tạo cạnh tới `Provision` là
`source_address` của thao tác trong văn bản sửa đổi. Thao tác không có địa chỉ nguồn thì cạnh trỏ tới Điều chứa nó
nếu xác định được; không thì bỏ qua và ghi vào báo cáo.

## 6. Truy vấn

Một lớp Python `LegalGraph` (chỉ đọc), mỗi phương thức ứng với một câu hỏi ở §1. Mọi kết quả trả kèm trích dẫn:
số hiệu văn bản, nhãn điều khoản, khoảng hiệu lực của phiên bản, trạng thái xác minh.

| Phương thức | Trả về |
|---|---|
| `text_at(pid, day)` | Phiên bản hiệu lực ngày đó, hoặc "không có hiệu lực" kèm lý do (chưa ban hành / đã bãi bỏ) |
| `changes(pid, from_day, to_day)` | Danh sách phiên bản trong khoảng, mỗi phiên bản kèm văn bản đã sửa nó |
| `guidance(pid, day)` | Các điều khoản dưới luật có `REFERS_TO kind=details` tới `pid` hoặc tới cha của nó, hiệu lực ngày đó |
| `references(pid, day, direction)` | Điều khoản được dẫn chiếu (out) hoặc dẫn chiếu tới nó (in), một bước |
| `applicable(document_key, day)` | Văn bản trong chuỗi `REPLACES` hiệu lực ngày đó |

`pid` là Điều thì `text_at` trả cả Điều; là khoản thì trả khoản. Phụ lục đọc qua `appendices(document_key)`.

## 7. Phải sửa trong kho

### 7.1 Sửa đổi và thay thế giữa văn bản dưới luật

Hiện `discover` chỉ nhận Luật / Bộ luật / Nghị quyết làm văn bản sửa đổi, và khi đọc Điều hiệu lực chỉ thử tải
văn bản bị thay thế dưới dạng Luật / Bộ luật. Hệ quả đo được: NĐ 145/2020 "hết hiệu lực một phần" nhưng kho không
có văn bản sửa nó; chuỗi NĐ 38 → 74 → 293 và NĐ 115 → 158, NĐ 12 → 283 không có quan hệ `THAY_THE`.

Sửa: cho phép văn bản cùng loại hoặc cấp cao hơn sửa đổi / thay thế văn bản dưới luật (Nghị định ↔ Nghị định,
Thông tư ↔ Thông tư, Nghị định → Thông tư), vẫn giữ nguyên tắc "chỉ thêm khi nội dung xác nhận". Loại văn bản bị
thay thế lấy từ chính câu chữ ("Nghị định số … hết hiệu lực"). Chỉ áp dụng cho họ của các văn bản trong seeds, để
không kéo về hàng trăm quyết định cấp tỉnh.

### 7.2 Phụ lục

Phần sau chữ ký hiện bị dồn vào Điều cuối, hoặc bị cắt (quy tắc "Điều lặp số" thêm ngày 12/11). Danh mục địa bàn
vùng lương nằm ở đây; không có nó thì không tra được vùng.

Sửa **ở tầng dựng đồ thị, không sửa `parse_structure`**: đọc raw text, tìm ranh giới phần thân (khối chữ ký "Nơi
nhận:", "TM. CHÍNH PHỦ", "BỘ TRƯỞNG"… hoặc Điều lặp số), rồi tách phần còn lại thành các `Appendix` theo tiêu đề
"PHỤ LỤC", "Phụ lục I", "Mẫu số 01", "DANH MỤC". `kind = form` khi phụ lục chứa Điều đánh số lại hoặc dòng chấm
chấm để điền; `list` khi là danh mục; còn lại `other`.

Hệ quả đã biết: `text` của Điều cuối trong kho vẫn kèm khối chữ ký (và phần phụ lục đứng trước Điều lặp số đầu
tiên). Đồ thị ghi `body_end_offset` trên phiên bản đó để người đọc cắt; kho không đổi.

### 7.3 Văn bản hết hiệu lực toàn bộ

Đo ngày 13/11 trên snapshot `s20261112164023-9d5ada`: NĐ 38/2022, NĐ 74/2024, NĐ 115/2015 và NĐ 12/2022 có
trạng thái vbpl "Hết hiệu lực toàn bộ" và có `vbpl_effective_to`, nhưng mọi phiên bản điều khoản của chúng vẫn mở
(`valid_to` rỗng) và `laws_in_force(hôm nay)` vẫn trả về chúng. Luật BHXH 58/2014 thì đúng (0 điều khoản hiệu
lực hôm nay) vì kho có quan hệ `THAY_THE` từ Luật 41/2024. Nguyên nhân là §7.1: kho chỉ đóng phiên bản khi có
văn bản thay thế được xác nhận, mà quan hệ thay thế giữa nghị định chưa được tìm.

Sửa: sau §7.1, quan hệ thay thế được xác nhận sẽ đóng phiên bản như với luật. Thêm lưới an toàn: văn bản có
trạng thái "Hết hiệu lực toàn bộ" và `vbpl_effective_to` nhưng không có văn bản thay thế trong kho thì phiên bản
được đóng tại `vbpl_effective_to`, kèm lý do `closed_by_vbpl_status` (nguồn là metadata vbpl, không phải câu chữ).
Nếu không sửa, `text_at` trả lời văn của NĐ 74/2024 cho một ngày trong năm 2026.

## 8. Nghiệm thu

Chạy trên snapshot thật (56 văn bản, trong đó 17 văn bản lao động):

- **Khớp kho:** số điều khoản và phiên bản bằng kho cho mọi văn bản; `graph check` không lỗi.
- **Tỉ lệ giải dẫn chiếu được đo và báo cáo**, tách theo lý do không giải được. Không đặt ngưỡng trước khi đo.
- **Mẫu kiểm tay:** 100 dẫn chiếu lấy ngẫu nhiên từ các văn bản lao động, người kiểm đối chiếu với văn bản gốc; ghi
  lại số sai và dạng sai.
- **Năm câu hỏi trên ca cụ thể:**
  - `text_at` Điều 25 BLLĐ tại 01/03/2025 trả đúng lời văn về thời gian thử việc.
  - `applicable` cho NĐ lương tối thiểu tại 01/01/2024, 01/01/2025, 01/02/2026 trả NĐ 38, NĐ 74, NĐ 293.
  - `guidance` cho khoản 4 Điều 21 BLLĐ trả điều khoản của NĐ 145/2020.
  - `changes` cho một điều khoản Luật BHXH 41/2024 đã bị sửa trả đủ các phiên bản kèm văn bản sửa.
  - `appendices` của NĐ 293/2025 trả danh mục địa bàn, tìm được tên một quận / huyện trong đó.
- **Tất định:** dựng hai lần từ cùng snapshot cho cùng `build_id` và cùng số nút, số cạnh.
- **Neo4j sập:** kho vẫn công bố snapshot; trạng thái đồ thị báo "chưa cập nhật".

## 9. So với Law-RAG

| | Law-RAG | Thiết kế này |
|---|---|---|
| Mục đích | Trả lời câu hỏi về luật | Điểm neo để soát hợp đồng |
| Phiên bản theo thời gian | Không | Có, tách danh tính và phiên bản |
| Đơn vị | Điều và đoạn (chunk) | Điều / khoản / điểm |
| Lớp ngữ nghĩa | LLM trích trên toàn kho (chủ thể, quyền, nghĩa vụ, cạnh tương tự / phân biệt) | Không có ở tầng này |
| Dẫn chiếu | Cấp Điều, trong một văn bản | Cấp điểm, liên văn bản, giải theo ngày |
| Nghị định hướng dẫn | Không | `GUIDES`, `REFERS_TO kind=details` |
| Phạm vi | BLLĐ 45/2019 | Cả kho (56 văn bản) |

Giữ lại từ Law-RAG một ý cho bản thiết kế cầu nối: "vấn đề pháp lý" viết tay trỏ tới Điều ưu tiên. Không giữ lớp
LLM trích toàn kho vì không kiểm chứng được ở quy mô đó, và một quan hệ sai sẽ thành kết luận sai về hợp đồng.

## 10. Giới hạn đã biết

- **Dẫn chiếu dạng lạ.** Bộ phân tích theo mẫu phủ các dạng thể thức; dạng viết tự do ("theo quy định về thử
  việc của pháp luật lao động") không thành cạnh. Mức độ sẽ biết sau khi đo ở §8.
- **VBHN.** VBHN 2026 của BLLĐ chưa có trên vbpl; phiên bản BLLĐ dựng từ văn bản gốc và các thao tác sửa đổi.
- **Luật BHYT.** Luật sửa đổi 46/2014 bị loại ở bước xác nhận nội dung; lịch sử phiên bản BHYT thiếu một bước.
- **Bảng trong phụ lục.** Lấy dưới dạng dòng chữ từ HTML của vbpl; bảng nhiều cột có thể mất cấu trúc cột.
- **Văn bản ngoài kho.** Dẫn chiếu tới văn bản chưa crawl chỉ được ghi là chưa giải được; báo cáo dựng liệt kê
  các văn bản bị dẫn chiếu nhiều nhất để quyết định có thêm vào seeds không.
- **Trạng thái xác minh.** Phiên bản `needs_review` / `conflicted` vẫn vào đồ thị kèm trạng thái; lớp cầu nối
  quyết định có dùng hay không.

## 11. Thứ tự làm

1. Sửa kho: §7.3 (kiểm tra `valid_to`), §7.1 (văn bản dưới luật), crawl lại.
2. Dựng phần cấu trúc: nút, `HAS_*`, `CHILD_OF`, quan hệ văn bản có sẵn, `CHANGED_BY`; kiểm tra; công bố bằng con trỏ.
3. `GUIDES` và `BASED_ON`.
4. Bộ phân tích dẫn chiếu và `REFERS_TO`; báo cáo tỉ lệ giải.
5. Phụ lục.
6. Lớp truy vấn `LegalGraph` và nghiệm thu §8.

## 12. Việc để người dựng tự quyết

Tên module và file trong `src/rag/legal/graph/`, kích thước lô khi ghi Neo4j, chỉ mục Neo4j, định dạng báo cáo
dựng, cách tổ chức test.
