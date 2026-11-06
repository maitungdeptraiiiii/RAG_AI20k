# Tài liệu bảo vệ code hiện tại — Team 4.2

Đối chiếu code, cấu hình nạp mới và artifact có tại ngày 05/11/2026. Không gọi API hoặc chạy lại benchmark để viết tài liệu này. Đây là bản giải thích triển khai, không phải cam kết hệ thống đã hoàn thiện.

## 1. Câu giới thiệu nên nói được trong 45 giây

“Nhóm xây dựng hệ thống hỏi đáp trên tài liệu luật tiếng Việt. Tài liệu được parse, chuẩn hóa và chia chunk theo cấu trúc Điều. Hệ thống lưu text/metadata trong JSONL và vector trong Qdrant local. Cấu hình thử nghiệm mới dùng query decomposition để mở rộng truy vấn, HyDE để cải thiện nhánh Dense, giữ nguyên pool câu gốc rồi bổ sung tối đa 10 Điều mới. Jev chấm các chunk bằng câu hỏi gốc, sau đó gộp theo Điều. Top 5 dùng chấm retrieval; context cho LLM được chọn riêng theo điểm và ngân sách. Câu trả lời có số nguồn được ánh xạ về tài liệu. Chúng em đã đo retrieval trên 64 câu, nhưng chưa chứng minh chất lượng câu trả lời cuối hoặc giải quyết hết multi-hop.”

Đây là pipeline RAG có bước lập truy vấn bằng LLM; code hiện tại chưa có vòng agent tự lập kế hoạch, gọi tool rồi quan sát và lặp đến khi hoàn thành.

## 2. Điều phải phân biệt trước khi demo

| Phần | Cấu hình nạp từ `.env` hiện tại | Cấu hình benchmark mới |
|---|---|---|
| Embedding | Jina small, 1024 chiều | Cùng model/chiều |
| HyDE | Bật | Bật |
| Decomposition | **Tắt** (`DECOMP_ENABLED=false` mặc định) | **Bật** bởi runner |
| Nhánh tìm kiếm | UI/`ask()` mặc định `hybrid`: BM25 + Dense | `mode="dense"`: không BM25 |
| Jev | Bật; source hiện tại là prompt hỗ trợ từng phần | Cùng prompt hỗ trợ từng phần |
| Index | `data/team-4.2/jina` | Snapshot cùng corpus tại `data/team-4.2/ablation/decomposition-anchor20-add10` |
| Context min score | 0.5 | Benchmark chỉ chấm retrieval; mô phỏng context sau đó dùng 0.5 |

Không nói UI hiện tại đang chạy đúng cấu hình đạt 0.880 nếu chưa bật decomposition và chọn Dense. Dòng `pipeline.ask_debug(question)` trong UI dùng `hybrid` mặc định. Streamlit còn cache pipeline bằng `st.cache_resource`; đổi biến môi trường cần nạp lại process/resource. Không xác nhận trạng thái process đang mở chỉ từ việc đọc file `.env`.

Để chạy CLI theo nhánh benchmark, cấu hình trong process mới phải tương ứng. Ví dụ dưới đây là lệnh chuẩn bị demo, chưa được thực thi trong lần phân tích này:

```powershell
$env:DECOMP_ENABLED='true'
$env:ADVANCED='hyde'
$env:RERANK_BACKEND='jev'
$env:RERANK_N='20'
$env:DECOMP_INCLUDE_ORIGINAL='true'
$env:DECOMP_POOL_SIZE='30'
$env:DECOMP_MAX_NEW_ARTICLES='10'
$env:DATA_DIR='data/team-4.2/ablation/decomposition-anchor20-add10'
python scripts/team-4.2/ask.py --mode dense --retrieve-only "chồng mất không để lại di chúc, nhà hai vợ chồng mua chung thì chia thế nào"
```

`--retrieve-only` bỏ bước sinh câu trả lời, **không** bảo đảm không gọi API: decomposition, HyDE, embedding và Jev vẫn có thể gọi nếu cache thiếu. Qdrant local chỉ cho một process mở một thư mục; không mở cùng index bằng UI và CLI đồng thời.

## 3. Luồng dữ liệu phải vẽ được

```text
INGEST
PDF / URL / TXT
  → load_source → list[Page]
  → chunk_document → list[Chunk]
  → index enhancer nếu bật
  → build index → lưu ChunkStore JSONL

QUERY — CẤU HÌNH BENCHMARK MỚI
Câu gốc
  → QueryDecomposer: câu gốc + tối đa 3 câu con; câu đơn ý giữ nguyên
  → mỗi câu q: HyDE sinh đoạn giả → embed(q + đoạn giả) → Dense
  → giữ đầy đủ pool tối đa 20 Điều của câu gốc
  → mỗi câu con giữ tối đa 10 Điều
  → RRF các danh sách; bỏ Điều đã có; thêm tối đa 10 Điều mới
  → Jev chấm từng chunk bằng CÂU HỎI GỐC
  → gộp các chunk cùng Điều
  ├→ hits = ranked[:5] → chấm Recall@5 / Hit@5 / MRR@5
  └→ select_context(ranked) → context theo ngưỡng/ngân sách
       → rỗng: từ chối, không gọi LLM trả lời
       → có context: generate → parse citation → Answer
```

Nếu dùng hybrid, mỗi câu q còn đi vào BM25 bằng chính q, không dùng đoạn HyDE. Trong chế độ không decomposition và chỉ Dense, không có bước fusion giữa các câu. Các arm retrieval trong code được duyệt tuần tự; Jev mới dùng thread để chấm nhiều cặp song song.

## 4. Phân biệt bốn kiểu dữ liệu

| Kiểu | Vai trò | Không được nhầm |
|---|---|---|
| `Chunk` | Text gốc + doc/source/page/section/context lúc index | Không phải một Điều hoàn chỉnh trong mọi trường hợp |
| `Hit` | chunk_id, score, rank, arm, các ID đã gộp | Score của Dense, BM25, RRF và Jev không cùng thang đo |
| `ContextBlock` | Số `[n]` và chunk thực đưa vào prompt | Không nhất thiết là 5 Hit dùng chấm benchmark |
| `Answer` / `Citation` | Text trả lời, nguồn, trạng thái từ chối, hits | Có citation không tự chứng minh câu trả lời đúng |

`RetrievalResult.candidates` là pool trước rerank; `ranked` là danh sách sau rerank/gộp; `hits` là top k của ranked. `queries`, `query_results`, `errors` giúp debug nhánh decomposition.

## 5. Ingestion và dữ liệu

- PDF: PyMuPDF lấy lớp text, giữ số trang. Không có OCR cho PDF scan.
- URL: trafilatura trích nội dung chính. TXT/MD: đọc UTF-8.
- Text được chuẩn hóa Unicode NFC và dọn khoảng trắng. NFC giúp chuỗi dấu tiếng Việt có dạng biểu diễn nhất quán.
- `doc_id`: SHA-1 nội dung lấy 16 ký tự hex; PDF hash bytes, text/URL hash text chuẩn hóa. Đây là ID theo nội dung, không phải mã hiệu pháp luật hay bảo đảm tuyệt đối không trùng.
- `chunk_id`: `<doc_id>:<thứ tự>`, ví dụ `abc:0007`.
- Chunk theo khoảng 300 đơn vị tách bằng khoảng trắng, không phải 300 tokenizer tokens và cũng không phải 300 từ tiếng Việt sau tách từ.
- Mở chunk mới tại Điều; không overlap qua ranh giới Điều. Có thể overlap một đoạn văn khi vừa ngân sách trong cùng luồng văn bản.
- Giữ heading `Phần > Chương > Mục > Điều` và page_start/page_end để truy nguyên.
- Ingest lại cùng doc_id được bỏ qua. Nội dung thay đổi tạo doc_id mới; code không tự thay thế/xóa bản luật cũ hay quản lý hiệu lực pháp lý.
- Pipeline build index trước, ghi store sau để tránh lưu store nếu build thất bại. Đây **không phải** transaction nguyên tử giữa Qdrant và JSONL; crash giữa hai bước vẫn cần xử lý phục hồi.

Vì sao không chia cửa sổ tùy ý? Cần giảm trộn hai Điều khác nhau, giữ metadata cho gộp và citation. Đánh đổi: parser heading bằng regex có thể sai khi nguồn có bố cục xấu; Điều dài vẫn bị tách thành nhiều chunk.

## 6. BM25, Dense và HyDE

**BM25**: dựa trên từ khóa, tần suất từ, độ hiếm của từ trong corpus và chuẩn hóa độ dài. Code tự viết Okapi BM25, k1=1.5, b=0.75, IDF dạng `ln(1 + (N-df+0.5)/(df+0.5))` để dương. Dùng pyvi để tách từ ghép tiếng Việt; query và document dùng cùng tokenizer.

BM25 có trong code và vẫn được dựng lúc khởi tạo pipeline, kể cả khi truy vấn Dense-only. “Không BM25” trong benchmark nghĩa là không dùng nhánh đó để tìm kiếm, không có nghĩa đã xóa module.

**Dense**: biến text thành vector; tìm vector gần bằng cosine trong Qdrant. Với Jina, chunk dùng task `retrieval.passage`, query dùng `retrieval.query`. Chọn task khác nhau vì hai vai trò khác nhau, không trộn hai cache task. Embedding có 1024 chiều trong index đang đo; đổi model/chiều cần index phù hợp.

Qdrant payload hiện lưu chunk_id; text/metadata được tra từ ChunkStore. Vector index kiểm tra model/chiều; pipeline còn kiểm tra chunk size và index enhancers. Các kiểm tra này chưa bao gồm mọi thay đổi thuật toán/parser hoặc revision dịch vụ model.

**HyDE**: sinh đoạn trả lời giả, embed `q + đoạn giả` để gần văn phong tài liệu. Đoạn giả không được dùng làm bằng chứng/citation. HyDE chỉ bọc nhánh Dense. Không nói HyDE luôn đúng hoặc luôn tốt hơn: nó có thể làm lệch truy vấn, cần đo ablation.

Đổi HyDE/decomposition là thay đổi lúc truy vấn, không phải embed lại corpus. Đổi contextual enrichment lúc ingest thay index text, cần index tương ứng.

## 7. Decomposition và pool 20 + 10

Mục tiêu: chia một nhu cầu thông tin nhiều ý thành các câu tìm kiếm tự đủ nghĩa. Không phải tạo nhiều cách diễn đạt cùng một ý.

Prompt yêu cầu giữ chủ thể, hành vi, số tiền/tuổi/thời điểm, điều kiện và phủ định; không tự bịa luật/Điều/kết luận. Code kiểm tra JSON, loại trùng theo casefold, giới hạn số câu và độ dài. Một câu con duy nhất không được coi là decomposition hữu ích; code lùi về câu gốc. Đây là validation hình thức, không bảo đảm nội dung LLM luôn đúng.

Giữ pool câu gốc để tránh mất ứng viên hữu ích ở hạng 14/18 như thử nghiệm đầu. Khi có pool gốc thành công và `include_original=true`:

- Pool gốc giữ nguyên mọi chunk đã lấy và thứ tự.
- RRF chọn các Điều mới từ câu con, không để Điều đã có chiếm ngân sách bổ sung.
- Mặc định tổng budget 30 Điều và tối đa 10 Điều mới. Nếu gốc chỉ có 12 Điều, không tự thêm 18 để lấp đầy.
- “20 Điều” là tối đa theo pool và kết quả có sẵn, không bảo đảm lúc nào cũng tìm được đủ 20.
- `ARM_K=20`, `ARTICLE_POOL_FACTOR=2` khiến mỗi arm lấy tối đa 40 chunk trước khi cắt pool theo Điều. 40 chunk vẫn có thể chứa ít hơn 20 Điều khác nhau.
- Khi câu gốc lỗi, không thể bảo đảm giữ pool gốc; lỗi được ghi trong trace. Benchmark mới dừng khi có lỗi/fallback để không đo nhầm cấu hình.

## 8. RRF: phải giải thích được công thức

`RRF(d) = Σ_i 1 / (60 + rank_i(d))`, rank bắt đầu từ 1.

RRF dùng thứ hạng thay vì cộng điểm BM25/cosine không cùng thang đo. Một chunk xuất hiện cao ở nhiều danh sách được tăng điểm. Hòa điểm dùng chunk_id. Code hiện là RRF đều trọng số, không phải weighted RRF như một số tài liệu kế hoạch cũ.

Trong benchmark Dense-only có decomposition, RRF gộp danh sách các câu truy vấn. Trong hybrid, có thêm fusion giữa các arm trong mỗi câu. `RRF_K=60` là hằng số làm trơn rank, khác với `TOP_K=5`.

RRF không đánh giá đủ ý, không hiểu luật và có thể ưu tiên các ý bị nhiều truy vấn tương quan lặp lại. Việc giữ pool gốc giảm một phần rủi ro mất ứng viên do fusion.

## 9. Jev và gộp Điều

Jev chấm mỗi cặp **câu hỏi gốc, chunk**, không dùng câu con làm câu hỏi chấm cuối. Nhờ vậy các nhánh tìm kiếm được đánh giá theo cùng nhu cầu ban đầu.

Prompt hiện tại chấm bằng chứng hỗ trợ ít nhất một phần quan trọng, yêu cầu đúng chủ thể/điều kiện và không chỉ trùng từ khóa. Model cấu hình là `jev-1.13.0`. Các cặp chạy bằng ThreadPoolExecutor, tối đa 8 workers; mục tiêu là giảm thời gian chờ I/O, không phải nhân số model.

Jev chấm riêng từng chunk **trước** khi gộp Điều. Sau đó các hit cùng `(doc_id, section Điều)` được gộp; giữ đại diện có thứ hạng tốt nhất, các ID khác vào `Hit.merged`. Context ghép các chunk đã gộp theo thứ tự và bỏ overlap dòng phù hợp; không mặc định tải toàn bộ mọi chunk của Điều từ corpus.

Do đó pool 30 Điều có thể có hơn 30 chunk và hơn 30 cặp cần chấm. Không nói “mỗi câu hỏi chắc chắn chỉ có 30 request Jev”.

Đây cũng không phải xref: gộp chunk cùng Điều không tự lấy Điều khác được viện dẫn.

Điểm Jev dùng làm điểm mức liên quan; chưa có kiểm định calibration để diễn giải 0.8 là 80% khả năng đúng pháp lý.

## 10. Top 5 khác context thế nào?

| Phần | Đầu vào | Quy tắc |
|---|---|---|
| Chấm retrieval | `ranked[:5]` | Cố định 5 Điều đại diện |
| Context có rerank | Toàn bộ `ranked` | Score >= min_p; tối đa 8 block và khoảng 2400 đơn vị khoảng trắng |
| Không rerank/Jev lỗi | ranked chưa chấm xác suất | Lấy fixed_k=5, vẫn xét budget độ dài |

Ngưỡng mặc định code 0.7; cấu hình nạp hiện tại 0.5. Không lấy điểm RRF so với ngưỡng xác suất Jev.

Giới hạn 2400 có ngoại lệ: code luôn nhận block đầu tiên dù nó quá dài. Không tuyên bố đây là hard token limit. Số block tối đa và số tokenizer tokens cũng khác nhau.

Ví dụ quan trọng: d02 có Điều 51 vào top 5 với score 0.49, nhưng nếu context min_p=0.5 thì Điều đó vẫn không vào prompt. Ngược lại d17 có một gold ở hạng 7, score 0.62, có thể vào context dù không nằm trong top 5. Retrieval metric và chất lượng đầu vào reader không hoàn toàn trùng nhau.

## 11. Generation, citation, từ chối

- LLM nhận câu hỏi gốc và text gốc của các ContextBlock; hệ thống đánh số `[1]`, `[2]`...
- Prompt yêu cầu chỉ dựa tài liệu, trích số nguồn sau mỗi ý và từ chối nếu không đủ thông tin.
- Citation parser hỗ trợ `[1]`, `[1][2]`, `[1,2]`; chỉ tạo Citation cho số có trong context.
- Số không tồn tại bị bỏ khỏi danh sách citation, nhưng **không bị xóa khỏi text trả lời**.
- Quote hiển thị là đoạn đầu khoảng 200 ký tự của block, không phải trích đoạn do hệ thống kiểm chứng cho từng mệnh đề.
- Nếu model trả text mà không có citation hợp lệ, code hiện vẫn có thể trả `refused=False`.
- Context rỗng được chặn trước LLM; còn guardrail RRF trước LLM và kiểm tra citation/entailment sau LLM vẫn là TODO trong pipeline.
- Chưa có kiểm tra tự động rằng nội dung cited thật sự chứng minh từng câu trả lời; chưa có bảo đảm chống hallucination/prompt injection.
- UI lưu lịch sử để hiển thị, nhưng build_prompt không truyền lịch sử hội thoại vào LLM. Có giao diện chat không đồng nghĩa có conversational memory.

## 12. Benchmark và điều được phép kết luận

Corpus của lần đo: 3422 chunk, 6 bộ luật. Dataset 64 câu giả lập viết trong script, gồm 27 `multi`, 37 `paraphrase`, không có out_of_scope. Có 95 GoldRef, tất cả dùng source + section; nhiều nhất 3 gold/câu. Đây không phải 64 yêu cầu thực của người dùng hoặc bộ multi-hop chuẩn độc lập.

Gold theo source + section giúp giữ nhãn qua thay đổi chunking, nhưng chưa chấm đúng từng khoản/điểm hay tính hiệu lực văn bản. `unmatched_gold` kiểm tra có chunk khớp metadata, không chứng minh nhãn được gán đúng về mặt nội dung.

| Chỉ số | Định nghĩa | Không có nghĩa là |
|---|---|---|
| Recall@5 | Tỷ lệ GoldRef được top 5 bao phủ, rồi trung bình từng câu | Tỷ lệ câu trả lời đúng |
| Hit@5 | Có ít nhất một gold trong top 5 | Đã đủ mọi gold cho câu multi |
| MRR@5 | 1/rank của gold đầu tiên, không có thì 0 | Đủ tất cả ý |
| Recall@20 | Metric trên 20 hit đầu của ranked | Luôn bằng recall toàn pool 30 Điều |
| candidate_recall | Metric trên toàn bộ ranked trong runner mới | Chất lượng câu trả lời cuối |

Ví dụ: câu có 3 gold, tìm được 2 thì Recall=2/3; gold đầu ở hạng 2 thì MRR=1/2; Hit=1.

| Mốc đã lưu | Recall@5 | Hit@5 | MRR@5 |
|---|---:|---:|---:|
| Baseline lịch sử trước decomposition | 0.848958 | 0.937500 | 0.826042 |
| Baseline có trace/cache dùng đối chiếu tác động | 0.835938 | 0.937500 | 0.800000 |
| Checkpoint 20+10, prompt Jev cũ | 0.851562 | 0.937500 | 0.802604 |
| 20+10, prompt Jev hỗ trợ từng phần | **0.880208** | **0.968750** | **0.848698** |

Phải giữ hai baseline có tên rõ, không chọn mốc thấp hơn để tuyên bố thắng. Audit cho thấy chênh lệch baseline không do tính sai top 5: Dense trước Jev khác ở 57/64 câu, thứ tự lịch sử không tương thích điểm cache hiện tại ở 24/53 câu đủ điểm. Lần lịch sử thiếu trace/fingerprint nên chưa xác định nguyên nhân gốc.

Giữa checkpoint 20+10 và prompt mới, queries/pool khớp 64/64; cache key mới được kiểm tra 1629 cặp. Chỉ cấu hình mới được chạy; đối chứng đọc từ CSV. 166 test đạt trong lần kiểm tra gần nhất, chủ yếu dùng fake client; không đồng nghĩa 166 thử nghiệm pháp lý hoặc 166 kiểm chứng API production.

Kết quả mới: 4 câu tăng Recall, 1 giảm (d10), 59 giữ nguyên. MRR tăng 10, giảm 4. Multi: Recall 0.790, Hit 1, MRR 0.808 nhưng đủ toàn bộ gold vẫn **16/27**. Không nói “đã xử lý hết multi-hop”.

Các điểm cải thiện phù hợp với giả thuyết prompt hỗ trợ từng phần hữu ích; thử nghiệm còn làm mới điểm model, chưa tách hoàn toàn biến động model với tác động prompt. Đã dùng bộ 64 để phát triển nên cần tập kiểm chứng độc lập trước kết luận tổng quát.

## 13. Hai case nên thuộc để giải thích kỹ thuật

**d22 — từ thiếu sang đủ:** gold Điều 134 BLHS đi từ hạng 6, điểm 0.17 lên hạng 3, điểm 0.60. Điều 22 lên hạng 1. Recall từ 0.5 lên 1. Pool không đổi, cải thiện do ranking.

**d10 — phản ví dụ:** Điều 650 BLDS tăng điểm từ 0.29 lên 0.58 nhưng tụt từ hạng 5 xuống 9 vì các Điều liên quan khác được tăng điểm mạnh hơn. Recall từ 1 xuống 0.5, MRR vẫn 1 vì Điều 651 ở đầu. Cho thấy điểm tuyệt đối cao hơn không bảo đảm thứ hạng cao hơn và MRR không đo đủ ý.

Không gọi các đoạn ngoài gold là “sai luật” chỉ vì không được bộ nhãn liệt kê.

## 14. Cache, API và tái lập

Ba cache khác nhau:

1. LLM SQLite: hash model, temperature, messages; dùng chung cho decomposition, HyDE và generation nhưng khác prompt/context thì khác key.
2. Embedding SQLite: model + task + text; query và passage không dùng nhầm cache.
3. Jev SQLite: schema v2 + model + toàn bộ instructions/state + chunk ID. State chứa heading và text. Khóa legacy còn để audit offline, live scoring không đọc lại điểm legacy.

Qdrant là index vector lưu bền; không phải thay thế cho cache API hoặc ChunkStore text. Mỗi DATA_DIR có index/cache riêng.

Khi cache đầy, giảm gọi API và tái lập được output đã lưu. Không kết luận model vốn deterministic; tên model/endpoint có thể không mô tả đầy đủ revision. Index signature và cache cũng không phải hệ thống version/audit hoàn chỉnh của mọi đầu vào.

Số lượt cold-cache nếu có m câu con (0..3), giữ câu gốc và có context:

- 1 lượt decomposition khi bật, kể cả khi cuối cùng không tách.
- 1+m lượt HyDE và truy vấn embedding; mỗi lượt có thể cache hit.
- Jev chấm số cặp query/chunk mới thực có trong pool, không nhất thiết bằng số Điều.
- 1 lượt LLM sinh câu trả lời. Context rỗng thì không có lượt này.

Trong code hiện tại, embedding từng câu chạy riêng; không có batch gộp toàn bộ query con trong một request. Ingest embedding mới thì chia batch.

Prompt mới không thêm một tầng LLM nhưng làm context dài hơn. Mô phỏng với min_p=0.5 cho thấy trung bình 750 → 1289 đơn vị khoảng trắng; số block 2.95 → 5.22. Không tuyên bố chi phí toàn flow bằng cũ chỉ vì số lượt API không tăng. Bộ 64 không có câu ngoài phạm vi nên chưa kiểm tra được false-accept sau đổi ngưỡng/phân bố điểm.

## 15. Fallback phải nói được

| Thành phần lỗi | Hành vi hiện có |
|---|---|
| Decomposition lỗi/JSON sai | Dùng câu gốc, ghi lỗi |
| HyDE lỗi/rỗng | Production dùng câu gốc cho Dense; benchmark đặt strict để dừng |
| Một arm hybrid lỗi | Tiếp tục với arm còn lại, ghi lỗi |
| Tất cả arm lỗi | Ném RetrievalError |
| Một nhánh câu con lỗi | Còn có thể dùng nhánh thành công, ghi lỗi |
| Jev lỗi | Fallback giữ thứ tự trước rerank; ghi last_error |
| Context rỗng | Answer.refusal, không gọi LLM trả lời |
| LLM generation lỗi | Retry các lỗi mạng/rate-limit được hỗ trợ rồi ném lỗi nếu hết lượt; chưa có câu trả lời dự phòng hoàn chỉnh |

Benchmark mới yêu cầu reranked=True và không errors; không coi fallback là kết quả hợp lệ của cấu hình đang đo.

## 16. Câu hỏi phản biện và câu trả lời ngắn

| Câu hỏi | Trả lời nên nắm |
|---|---|
| Tại sao không đưa cả tài liệu vào LLM? | Giới hạn context, chi phí, độ nhiễu; retrieval chọn bằng chứng nhưng có nguy cơ bỏ sót. |
| Tại sao dùng Jina? | Lựa chọn dựa trên benchmark tiếng Việt của dự án; không tuyên bố tốt nhất mọi corpus. |
| Tại sao HyDE dù có thể bịa? | Nó chỉ biến đổi truy vấn tìm kiếm; bằng chứng trả lời vẫn từ corpus thật. |
| HyDE và decomposition khác gì? | Decomposition chia nhu cầu thông tin; HyDE tạo văn bản giả để embed cho từng nhu cầu. |
| Vì sao không lấy 30 mới mà giữ 20 gốc? | Giữ tín hiệu baseline, tránh làm rơi Điều ở hạng thấp nhưng Jev có thể nâng lên. |
| Vì sao BM25 không có trong cấu hình mới? | Code vẫn hỗ trợ; cấu hình benchmark đang đo Dense/HyDE để dựa vào kết quả ablation đã lưu. |
| RRF có còn dùng khi tắt BM25? | Có khi decomposition tạo nhiều danh sách; không dùng fusion nếu chỉ có một nhánh/câu. |
| RRF có dùng score Dense không? | Không; dùng rank. |
| Tại sao 20/10/5/8? | Các giới hạn thực dụng cho pool, ngân sách và giao thức eval; chưa chứng minh tối ưu toàn cục. |
| Có bảo đảm 30 Điều = 30 request Jev? | Không; từng Điều có thể nhiều chunk được chấm riêng. |
| Có phải luôn chọn 5 đoạn cho LLM? | Không; 5 cho benchmark, context chọn bằng ngưỡng và ngân sách. |
| Đổi prompt sao phải đổi cache? | Điểm là hàm của instructions và state; dùng điểm prompt cũ sẽ làm phép đo sai. |
| Có citation thì hết hallucination? | Không; mới kiểm tra ánh xạ số nguồn, chưa kiểm tra entailment từng mệnh đề. |
| Có tự cập nhật luật mới không? | Chưa có quản lý hiệu lực/phiên bản và cập nhật thay thế tự động đầy đủ. |
| Có nhớ lượt chat trước không? | UI có lịch sử hiển thị, nhưng LLM prompt hiện không nhận lịch sử. |
| 0.880 là 88% câu trả lời đúng? | Không; là trung bình Recall@5 theo GoldRef. |
| Hit multi=1 có nghĩa giải quyết hết multi không? | Không; chỉ cần một gold là Hit=1; đủ mọi gold mới là Recall=1. |
| Đã kiểm chứng tổng quát chưa? | Chưa; bộ 64 đã dùng để phát triển, thiếu holdout và đánh giá reader/citation. |
| Test fake để làm gì? | Kiểm tra logic, schema, giới hạn, fallback/cache; benchmark thật kiểm tra hiệu quả trên dữ liệu. |
| Có phải agent tự chủ không? | Chưa; hiện là pipeline RAG với một bước lập truy vấn, không có vòng tool-use nhiều bước. |

## 17. Những câu không nên tuyên bố

- “Context luôn là top 5” hoặc “2400 là hard token limit”.
- “Pool là 30 chunk” khi merge_articles đang bật.
- “BM25 đã bị bỏ khỏi code”.
- “Jev probability là xác suất đúng pháp lý đã được hiệu chỉnh”.
- “Benchmark retrieval chứng minh câu trả lời/citation đúng”.
- “Đã xử lý hết multi-hop”, “không thể hallucinate”, “nguồn pháp luật luôn mới”.
- “Số request không tăng nên chi phí không tăng”.
- “Baseline lịch sử và baseline có trace là một mốc duy nhất”.
- “Prompt mới chắc chắn gây ra toàn bộ cải thiện”; phép đo còn có điểm model được làm mới.
- “Demo UI mặc định là đúng cấu hình benchmark mới”.

## 18. Thứ tự đọc code để chuẩn bị

1. `schema.py`: Page, Chunk, Hit, ContextBlock, Answer, GoldRef.
2. `pipeline.py`: from_settings → ingest → ask_debug.
3. `ingest/chunker.py`: _paragraphs → _split_long → chunk_document.
4. `advanced/decomposition.py`, `advanced/hyde.py`.
5. `retrieve/hybrid.py`: retrieve → _retrieve_single → _rank_result.
6. `retrieve/merge.py`, `retrieve/fusion.py`.
7. `retrieve/rerank.py`: instructions, full-input cache, sort và fallback.
8. `retrieve/context.py`: threshold khác fixed, giới hạn độ dài.
9. `generate/answer.py`: build_prompt → generate → build_citations.
10. `eval/metrics.py`, runner benchmark, CSV/trace và hai case d22/d10.

Checkpoint trước đổi prompt: `27b361c`. Prompt Jev mới, test cache và metadata runner đang là thay đổi chưa commit tại thời điểm lập tài liệu. Không chạy rollback/reset khi chưa lưu các thay đổi muốn giữ.

Để bảo vệ tốt: giải thích được một câu từ input đến citation; chỉ ra từng cấu trúc dữ liệu; tính thử Recall/MRR và RRF bằng tay; đọc được một trace thành công và một trace thất bại; phân biệt điều đã đo với điều mới là hướng phát triển.
