# Thiết kế: Hỏi đáp theo mốc thời gian — Phần 2/4

Ngày: 09/11/2026 · Trạng thái: bản nháp chờ duyệt · Phụ thuộc: Phần 1 (`rag.legal`, spec
`2026-11-09-legal-version-builder-design.md`)

## 1. Ý định và lý do

Phần 1 dựng được kho luật trả lời "tại ngày X, điều khoản này nói gì và đã xác minh tới đâu". Phần 2 đưa kho đó vào
khung chat: mọi câu trả lời pháp lý phải gắn với **mốc thời gian pháp lý** (ngày ký, ngày thực hiện, ngày tranh
chấp, ngày đánh giá...), dùng **đúng phiên bản luật tại mốc đó** do backend chọn, và nói rõ độ tin cậy của từng căn
cứ. Ứng dụng dùng để đánh giá hợp đồng; kết luận sai phiên bản luật nhưng trông chắc chắn là thất bại nặng nhất.

Phân vai (quyết định của người dùng):

| Thành phần | Ai làm |
|---|---|
| Nhận diện ngày tháng | Quy tắc (regex) |
| Nhận diện vai trò ngữ nghĩa của mốc | LLM, chỉ khi cần |
| Chuẩn hoá ngày, kiểm tra bằng chứng, xử lý ngày tương đối | Backend |
| Chọn phiên bản luật, lọc theo thời gian, gắn trạng thái | Backend |
| Suy luận pháp lý, đọc quy định chuyển tiếp | LLM, trên dữ liệu backend đã kiểm soát |

## 2. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu**
- Dòng thời gian pháp lý (legal timeline) cho mỗi câu hỏi: nhiều mốc, mỗi mốc có vai trò, khoảng ngày, độ chính
  xác, nguồn, độ tin cậy, bằng chứng.
- Ô chọn ngày trong khung chat; mốc trích từ câu hỏi; mặc định hôm nay — có cảnh báo khi mâu thuẫn.
- Truy xuất trên **hai kho**: kho mới (có phiên bản) là nguồn ưu tiên; kho cũ (6 Bộ luật) là nguồn tham khảo.
- Lọc theo thời gian **trước** khi xếp hạng; mốc chỉ có năm/tháng trả về mọi phiên bản trong khoảng đó.
- Trạng thái hai tầng trên mỗi căn cứ: cấp văn bản và cấp điều khoản.
- Quy định chuyển tiếp: backend tìm và đưa toàn văn vào ngữ cảnh dưới dạng `transition_rules`; LLM đánh giá.
- Câu trả lời có: dòng "Mốc pháp lý đang sử dụng", căn cứ kèm phiên bản + khoảng hiệu lực + trạng thái + văn bản sửa
  đổi đã tạo ra nội dung (provenance), trạng thái đánh giá chuyển tiếp, giới hạn nếu dựa vào nguồn chưa xác minh.
- Lưu lại phân tích mỗi câu hỏi (timeline, căn cứ, đánh giá chuyển tiếp) để audit và làm dữ liệu cho phương án (b).

**Không làm trong phần 2**
- Mô hình hoá quy tắc chuyển tiếp có cấu trúc để backend tự quyết (phương án b) — chỉ chuẩn bị interface.
- Đính kèm hợp đồng (phần 4), form upload văn bản pháp luật (phần 3).
- Migrate 6 Bộ luật cũ sang kho có phiên bản.

**Phản mục tiêu**
- LLM tự chọn phiên bản luật, hoặc tự sinh một ngày không có trong câu hỏi.
- Áp luật tại ngày ký cho mọi vấn đề phát sinh sau đó (mỗi vấn đề theo mốc của nó).
- Dùng kho cũ như luật hiện hành; có thêm dữ liệu kho cũ làm câu trả lời trông chắc chắn hơn thực tế.
- Kết luận chắc chắn khi kết luận phụ thuộc vào: căn cứ `needs_review`/`conflicted`/`unversioned`, quy định chuyển
  tiếp `potentially_applicable`/`undetermined`, hoặc mốc chỉ có năm mà luật đổi trong năm đó.
- Âm thầm bỏ qua một mốc người dùng đã nêu.

## 3. Dòng thời gian pháp lý

### 3.1 Mô hình

```
TimeAnchor
  role: signing | contract_effective | performance | discovery | dispute | evaluation | unspecified
  start: date | None, end: date | None      # khoảng đóng [start, end]; ngày = start == end
  precision: day | month | year | range | relative_unresolved
  source: calendar | question | default
  evidence: str | None                       # câu chữ gốc (bắt buộc khi source=question)
  relative_expression: str | None            # "năm ngoái", "cuối năm ngoái", "bây giờ"
  confidence: float
LegalTimeline
  anchors: list[TimeAnchor]
  primary: TimeAnchor                         # mốc dùng khi câu hỏi không phân biệt vấn đề
  warnings: list[str]                         # mâu thuẫn lịch/câu hỏi, mốc chưa giải được...
  asked_at: datetime, timezone: "Asia/Ho_Chi_Minh"
```

### 3.2 Quy trình

1. **Quy tắc**: nhận diện ngày (`15/06/2023`, `ngày 15 tháng 6 năm 2023`), tháng (`tháng 3/2023`), năm (`năm 2023`),
   khoảng (`từ ... đến ...`), cụm tương đối (`năm ngoái`, `năm nay`, `tháng trước`, `cuối năm ngoái`, `đầu năm`,
   `hiện nay`, `bây giờ`), và từ khoá vai trò gần mốc (`ký`, `giao kết` → signing; `có hiệu lực` (hợp đồng) →
   contract_effective; `thực hiện`, `bàn giao`, `thanh toán` → performance; `phát hiện` → discovery; `tranh chấp`,
   `kiện`, `khởi kiện` → dispute; `hiện nay`, `bây giờ` → evaluation).
2. **LLM chỉ khi**: có mốc chưa gán được vai trò, có cụm tương đối, hoặc câu có từ hai mốc trở lên. Đầu vào: câu hỏi +
   các mốc quy tắc đã thấy. Đầu ra JSON theo mẫu `{"events":[{role, date{start,end,precision}, relative_expression,
   evidence, confidence}]}`. LLM không được tạo mốc không có bằng chứng.
3. **Kiểm tra (backend)**: `evidence` phải là chuỗi con của câu hỏi (sau chuẩn hoá NFC/khoảng trắng), không thì loại
   mốc + cảnh báo; ngày hợp lệ; giữ nguyên precision (tháng → khoảng cả tháng; năm → cả năm); cụm tương đối quy ra
   **khoảng** theo `asked_at` (năm ngoái → cả năm trước; cuối năm ngoái → 01/10–31/12 năm trước, ghi
   precision=range); cụm không quy được → `relative_unresolved` + cảnh báo yêu cầu ngày cụ thể. Ngày LLM trả mà
   không khớp với ngày quy tắc thấy trong `evidence` → dùng ngày của quy tắc.
4. **Hợp nhất với lịch**: có ngày lịch → mốc `source=calendar`, `role=unspecified` (trừ khi UI cho chọn vai trò),
   làm `primary`. Mốc trong câu hỏi khác ngày lịch → giữ cả hai, cảnh báo "câu hỏi nhắc mốc X khác ngày đã chọn".
5. Không có mốc nào → `evaluation = hôm nay`, `source=default`, cảnh báo "đang áp dụng pháp luật hiện hành".

LLM lỗi/timeout → dùng kết quả quy tắc, vai trò chưa rõ = `unspecified`, cảnh báo.

## 4. Truy xuất theo mốc

### 4.1 Kho mới (có phiên bản)

- Nạp `rag.legal.chunks.export_chunks` của **luật gốc** (không phải văn bản chỉ để sửa đổi) vào một chỉ mục riêng
  (BM25 + Qdrant collection riêng), payload: `document_key`, `article_id`, `valid_from`, `valid_to`,
  `verification_status`, `status_reasons`, `notes`, `source_operations`, `build_id`. Đồng bộ lại khi có build mới.
- Văn bản "chỉ để sửa đổi" = văn bản mà mọi Điều có tiêu đề hành động sửa đổi hoặc là Điều hiệu lực/chuyển tiếp
  (vd. 43/2024, 03/2022). Luật có Điều sửa đổi luật khác nhưng còn nội dung riêng (Luật Đầu tư 2020) vẫn là luật gốc.
  Văn bản sửa đổi không xuất hiện làm kết quả, nhưng **provenance** của căn cứ trỏ tới nó (từ `source_operations`).
- Với mỗi mốc có khoảng `[s, e]`: chỉ xét chunk có khoảng hiệu lực giao với `[s, e]` (lọc trước khi BM25/vector chạy;
  Qdrant dùng filter payload; BM25 chạy trên tập con). Mốc chỉ có năm mà một Điều có hai phiên bản trong năm → cả
  hai được đưa vào, gắn khoảng hiệu lực.
- Nhiều mốc: truy xuất cho từng mốc, gộp, mỗi đoạn ngữ cảnh gắn nhãn mốc mà nó phục vụ.

### 4.2 Kho cũ (6 Bộ luật)

- Giữ chỉ mục hiện có. Mỗi Bộ luật cũ có định danh trong một bảng ánh xạ nhỏ (kho cũ không có metadata):
  `data/team-4.2/legal/legacy_map.yaml` — file → loại văn bản, số hiệu, cơ quan ban hành.
- **Loại trùng**: Bộ luật cũ nào có cùng (loại, số hiệu, cơ quan) với một văn bản trong kho mới (vd. Bộ luật Dân sự
  91/2015/QH13) thì không truy xuất từ kho cũ. Giữ đường dẫn nguồn gốc trong trích dẫn.
- Trạng thái cấp văn bản của kho cũ: `unversioned`; nếu biết đã bị thay thế (theo kho mới hoặc vbpl
  "Hết hiệu lực toàn bộ") → `outdated`.

### 4.3 Trạng thái hai tầng

Cấp văn bản (tại mốc đang xét):

| Trạng thái | Khi nào |
|---|---|
| `verified` | kho mới; mọi điều khoản của văn bản tại mốc `verified` |
| `partially_verified` | kho mới; có điều khoản `needs_review`/`conflicted` tại mốc |
| `unversioned` | kho cũ, chưa xác định phiên bản |
| `outdated` | biết chắc không còn hiệu lực tại mốc (kho mới: không có phiên bản hiệu lực; kho cũ: đã bị thay thế) |
| `unknown` | không đủ dữ liệu (vd. mốc `relative_unresolved`, văn bản thiếu Điều hiệu lực) |

Cấp điều khoản: giữ nguyên `verified` / `needs_review` / `conflicted` của phần 1.

## 5. Quy định chuyển tiếp (phương án a, chuẩn bị cho b)

Backend tạo `transition_rules` cho ngữ cảnh khi một trong các điều kiện:
- Căn cứ được dùng có `note:transition:<văn bản>#dN` (văn bản sửa đổi tạo ra phiên bản có Điều chuyển tiếp).
- Luật áp dụng **khác nhau giữa các mốc** của cùng câu hỏi (vd. ký 2023 theo Luật Nhà ở 2014, đánh giá 2025 theo
  Luật Nhà ở 2023) → Điều chuyển tiếp của luật mới hơn.
- Mốc rơi trước ngày hiệu lực của một luật thay thế đang có hiệu lực tại mốc đánh giá → Điều chuyển tiếp của luật đó.

```
TransitionRule (interface tối thiểu, nội dung là văn bản gốc)
  rule_id, source_document_key, source_article ("Điều 199"), text (toàn văn Điều chuyển tiếp)
  old_law_key, new_law_key, new_law_effective_from
  related_anchors: [role...]                 # mốc nào khiến quy tắc này được đưa vào
```

LLM phải trả về cho mỗi `transition_rule`: `assessment` ∈ `not_applicable` / `potentially_applicable` /
`applicable` / `undetermined`, trả lời ba câu (liên quan tới loại sự kiện? đủ dữ kiện? có ngoại lệ có thể đổi kết
luận?), trích dẫn đoạn đã dựa vào, và câu hỏi bổ sung nếu thiếu dữ kiện. `applicable` là đánh giá của LLM, không phải
xác minh của backend. Kết quả được lưu (mục 7) để làm dữ liệu cho phương án b.

## 6. Hợp đồng với LLM và định dạng câu trả lời

Đầu vào LLM: câu hỏi (đã che PII như hiện nay), timeline, các khối ngữ cảnh (mỗi khối: số trích dẫn, mốc phục vụ,
văn bản, điều khoản, khoảng hiệu lực, trạng thái văn bản + điều khoản, provenance, nội dung), `transition_rules`.

Đầu ra LLM (JSON):
```
answer_markdown          # trả lời theo từng vấn đề pháp lý, mỗi vấn đề nêu mốc áp dụng; trích dẫn [n]
issues: [{issue, anchor_role, citations[n], certainty: firm | qualified | cannot_conclude, limitation}]
transition_assessments: [{rule_id, assessment, reasons, citations, missing_information}]
follow_up_questions: [str]
```
Backend kiểm tra: mọi `[n]` tồn tại; `certainty=firm` bị hạ xuống `qualified` nếu dựa vào căn cứ không `verified`
(cả hai tầng) hoặc quy định chuyển tiếp chưa `not_applicable`/`applicable`, hoặc mốc năm mà luật đổi trong năm;
không có căn cứ hợp lệ → từ chối như hiện nay.

Giao diện (chat hiện có, `ui/index.html`):
- Ô chọn ngày (tuỳ chọn) cạnh ô nhập câu hỏi.
- Trên câu trả lời: dòng "Mốc pháp lý đang sử dụng" — mỗi mốc một thẻ (vai trò, ngày/khoảng, nguồn), kèm cảnh báo.
- Mỗi trích dẫn: tên văn bản, điều khoản, "hiệu lực từ … đến …", nhãn trạng thái văn bản + điều khoản (có biểu
  tượng + chữ, không chỉ màu), "do <văn bản sửa đổi> sửa" nếu có; nguồn kho cũ ghi rõ "kho luật cũ — chưa xác định
  phiên bản, chỉ tham khảo".
- Khối "Quy định chuyển tiếp" khi có, với trạng thái đánh giá.
- Câu hỏi bổ sung (nếu có) hiện như gợi ý để người dùng trả lời tiếp.

## 7. Lưu vết phân tích

Mỗi câu hỏi lưu (SQLite `DATA_DIR/legal/qa_log.sqlite`, câu hỏi đã che PII): timeline (kể cả mốc bị loại và lý do),
`build_id` của từng luật dùng, danh sách căn cứ + trạng thái, `transition_rules` + đánh giá của LLM, certainty sau
khi backend hạ cấp. Không lưu giá trị PII gốc.

## 8. API

`POST /api/chat` nhận thêm `as_of` (YYYY-MM-DD, tuỳ chọn). Trả thêm `timeline`, mỗi citation có `valid_from`,
`valid_to`, `document_status`, `provision_status`, `provenance`, `store` (`versioned` | `legacy`),
`transition_assessments`, `issues`, `follow_up_questions`. Trường cũ giữ nguyên để UI hiện tại không vỡ.

## 9. Đánh giá

Bộ câu hỏi theo mốc cho nhóm bất động sản (`evals/team-4.2/datasets/temporal_qa_realestate.jsonl`), mỗi câu có mốc kỳ
vọng (vai trò, khoảng) và phiên bản kỳ vọng (document_key + khoảng hiệu lực của điều khoản chính). Đo: độ đúng trích
mốc, độ đúng phiên bản truy xuất (không cần LLM trả lời), tỉ lệ câu trả lời `firm` dựa trên căn cứ không `verified`
(phải bằng 0). Kèm các ca: mâu thuẫn lịch/câu hỏi, chỉ có năm khi luật đổi giữa năm (01/8/2024), nhiều mốc qua thời
điểm thay luật, câu không có mốc.

## 10. Ràng buộc

- Dùng LLM và embedding đang cấu hình trong `rag.config.Settings`; không thêm dịch vụ ngoài.
- Không phá luồng hỏi đáp hiện có: kho cũ vẫn chạy khi kho mới trống.
- Ngày theo múi giờ Asia/Ho_Chi_Minh.

## 11. Để lại cho người xây dựng

- Regex cụ thể, danh sách từ khoá vai trò mở rộng.
- Cách đồng bộ chỉ mục kho mới với build mới (toàn bộ hay tăng dần).
- Prompt cụ thể và cách gộp/xếp hạng kết quả hai kho.
- Bố cục chi tiết thẻ mốc và nhãn trạng thái.
