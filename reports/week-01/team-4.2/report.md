# Báo cáo tuần 1 — Team 4.2

## Scope and version

- **Team:** 4.2 — lĩnh vực sơ bộ: **hỏi đáp văn bản luật Việt Nam** (6 Bộ luật crawl từ vbpl.vn).
- **Thành viên và đóng góp** (theo commit trong `app/`, `evals/`, `data/`, `scripts/` team-4.2):

| Ký hiệu | Họ tên | Đóng góp chính |
|---|---|---|
| A | Mai Phan Anh Tùng | BM25 index, RRF fusion + hybrid retrieval, reranker; tích hợp nhánh `w01-integration` |
| B | Nguyễn Gia Khánh | Ingestion: loaders (PDF/URL/TXT), chunker theo Điều, chunk store, contextual header |
| C | Lương Quang Huy | Dense embedding + Qdrant vector index, HyDE, khung evaluation (`run_eval.py`), benchmark 6 Bộ luật và kết quả |
| D | Nguyễn Quốc Tuấn | Schema chung, Settings/config, `RAGPipeline`, Streamlit chat UI, tài liệu/đóng gói |
| E | Nguyễn Anh Tú | Context builder, generation (prompt + citation), script `ask.py` |

- **Mục tiêu tuần:** baseline RAG end-to-end (ingest → BM25/Dense/RRF → trả lời có citation, từ chối khi thiếu bằng chứng) + evaluation Recall@5/MRR@5.
- **Đã hoàn thành:**
  - Ingest TXT/PDF/URL, chunk theo Điều (`MAX_SYLLABLES=300`), metadata `source` + `section`; crawler vbpl.vn (bonus).
  - BM25 (pyvi), Dense (Qdrant local), Hybrid RRF (k=60) chạy độc lập, có kết quả riêng từng arm trong eval.
  - Chat UI Streamlit, trả lời có citation, từ chối khi context không có bằng chứng.
  - Benchmark 40 câu (mở rộng 100 câu) trên 6 Bộ luật + bộ 64 câu "đời thường"; Recall@5, Hit@5, MRR@5, Recall@20.
  - Bonus: rerank Jev, HyDE, so sánh embedding (OpenAI / Jina v5 / legal-e5), hỗ trợ tiếng Việt kiểm chứng bằng câu hỏi thực tế.
- **Chưa hoàn thành:** guardrail 2 tầng; chấm tay đúng/sai câu trả lời (cột `correct`/`citation_ok` trong `answers.csv` còn trống); RAGAS; câu `out_of_scope`; đo latency/chi phí; slides và video demo.
- **Commit / snapshot / cấu hình:**
  - Repo nộp bài: nhánh `feat/team-4.2/w01-integration`, HEAD `6d87e5f` (có thay đổi chưa commit).
  - Repo làm việc chạy eval: `RAG_AI20k`, HEAD `5bdaafe` (`feat(team-4.2): expand 6-code benchmark to 100 questions`).
  - Dữ liệu: 6 Bộ luật (HS 2015, TTHS 2015, LĐ 2019, DS 2015, TTDS 2015, HH 2015), 3.422 chunk, snapshot `data/team-4.2/`.
  - Model: embedding `text-embedding-3-small` (1536d) cho baseline; `jina-embeddings-v5-text-small` và `bqbbao6/vietnamese-legal-embedding` cho thí nghiệm embedding; LLM `gpt-6-luna` (temperature mặc định, có cache); reranker Jev (`RERANK_N=20`, `CONTEXT_MIN_P=0.6`).
- **Chạy lại:** xem [app/team-4.2/README.md](../../../app/team-4.2/README.md) và mục "Chạy lại" trong [BENCHMARK_6_BO_LUAT.md](../../../evals/team-4.2/results/BENCHMARK_6_BO_LUAT.md).

  ```bash
  pip install -e "app/team-4.2[dev,jev]"
  cp app/team-4.2/.env.example app/team-4.2/.env   # điền key, không commit
  Q=evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl
  RERANK_BACKEND=none ADVANCED= python evals/team-4.2/runners/run_eval.py --questions $Q --answers \
      --out evals/team-4.2/results/bench6-40q-gpt6luna
  streamlit run app/team-4.2/ui/streamlit_app.py
  ```

## Design decisions

| Bài toán | Lựa chọn | Phương án đã cân nhắc | Trade-off |
|---|---|---|---|
| Chunking văn bản luật | Mỗi Điều mở chunk mới, Điều dài tách theo 300 âm tiết; `section` = Chương > Mục > Điều | Chunk cố định theo token | Citation trỏ đúng Điều; chunk không đều độ dài |
| Gold label | Gold ở cấp **Điều** (`source` + `section`), không theo `chunk_id` | Gold theo chunk_id | Bền khi đổi cách chunk; không phân biệt được khoản/điểm |
| Tách từ BM25 | pyvi | Tách theo khoảng trắng | Khớp từ ghép tiếng Việt tốt hơn; thêm phụ thuộc |
| Fusion | RRF k=60 | Weighted score fusion | Không cần chuẩn hoá điểm; nhưng arm yếu có thể kéo kết quả xuống (xem bộ đời thường) |
| Context cho LLM | Rerank Jev + ngưỡng p ≥ 0.6 (tối đa 8 đoạn / 2400 từ); không đoạn nào qua ngưỡng → từ chối, không gọi LLM | Top-5 cố định; ngưỡng 0.7 | 0.7 cắt mất gold (q20 trả lời sai); 0.6 chọn trên chính benchmark nên có thể lạc quan |
| Câu hỏi đời thường | HyDE (LLM viết đoạn giả văn phong luật, embed "câu hỏi + đoạn giả") | Query rewrite | +1 lần gọi LLM/câu; chưa đo rủi ro với câu ngoài phạm vi |
| Vector store | Qdrant local | FAISS | Có filter/metadata, chạy local không cần server |

Chi tiết stack: [tech_stack.md](../../../app/team-4.2/docs/tech_stack.md).

## Evaluation

**Dataset**

- [`benchmark_6_bo_luat.jsonl`](../../../evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl): 100 câu, tỉ lệ lookup : paraphrase : multi = 40 : 40 : 20. Các bảng chính dùng **40 câu đầu** (16 lookup, 16 paraphrase, 8 multi). Câu hỏi và đáp án mẫu viết sau khi đọc nguyên văn Điều; gold = Điều.
- [`benchmark_doi_thuong.jsonl`](../../../evals/team-4.2/datasets/benchmark_doi_thuong.jsonl): 64 câu văn nói, mơ hồ, thiếu dữ kiện (37 paraphrase, 27 multi), sinh bởi [`build_benchmark_doi_thuong.py`](../../../evals/team-4.2/runners/build_benchmark_doi_thuong.py).
- Không có câu `out_of_scope` → tỉ lệ từ chối đúng với câu ngoài phạm vi là **N/A**.

> **Bộ 6 Bộ luật quá dễ so với câu hỏi thực tế, nên số đẹp trên bộ này không có nghĩa pipeline đã tối ưu.**
> Bộ này được soạn *sau khi đọc nguyên văn Điều*, nên câu hỏi mượn lại thuật ngữ và cấu trúc câu của luật:
>
> - 40% là câu **lookup**, gần như chép lại câu chữ luật → Recall@5 = **1.000 ở mọi cấu hình** (kể cả Dense Jina, BM25 OpenAI). Nhóm này không giúp phân biệt cấu hình tốt hay xấu, chỉ đẩy điểm tổng lên.
> - Câu **paraphrase** vẫn đủ dữ kiện, một ý, nhiều từ khoá pháp lý; câu **multi** nêu rõ các vế cần nối.
> - Người dùng thật hỏi khác hẳn: văn nói, mơ hồ, thiếu dữ kiện, nhiều vấn đề trong một câu ("hôm nay tôi lỡ tông phải một ông già lúc sang đường, không biết có bị sao không"). Bộ **đời thường** (64 câu) được xây sau để đo đúng trường hợp này.
>
> Cùng cấu hình, đổi sang bộ đời thường thì điểm giảm mạnh:
>
> | Cấu hình (cùng index, cùng embedding) | 6 Bộ luật R@5 / MRR@5 | Đời thường R@5 / MRR@5 | Chênh R@5 |
> |---|---|---|---|
> | Hybrid RRF, OpenAI 3-small | 0.633 / 0.658 (40 câu) | **0.175 / 0.117** (20 câu) | −0.458 |
> | Hybrid RRF, Jina v5 | 0.782 / 0.701 (100 câu) | **0.458 / 0.386** (64 câu) | −0.324 |
> | Dense, Jina v5 | 0.912 / 0.853 (100 câu) | **0.594 / 0.499** (64 câu) | −0.318 |
> | Dense + HyDE + Jev, Jina v5 | 0.942 / 0.950 (40 câu) | **0.849 / 0.826** (64 câu) | −0.093 |
>
> Nguồn: `bench6-40q-gpt6luna`, `doi-thuong-20q`, `bench6-100q-emb-jina`, `doi-thuong-64q-emb-jina`, `bench6-40q-jina`, `doi-thuong-64q-hyde-nobm25`. Số câu hai bên chưa bằng nhau, nên chỉ xem chênh lệch là ước lượng.
>
> Hệ quả: **baseline Hybrid RRF mà nhóm coi là "chạy được" trên bộ cũ (R@5 0.633) thực tế chỉ tìm đúng Điều cho 17.5% câu văn nói.** Kết luận về cấu hình tốt nhất cũng thay đổi khi đổi bộ eval: BM25 gần như không hại trên bộ cũ, nhưng trên bộ đời thường thì kéo Hybrid xuống dưới Dense. Từ đây nhóm lấy **bộ đời thường làm thước đo chính**; bộ 6 Bộ luật chỉ còn dùng để bắt regression ở câu tra cứu.

**Metric:** Recall@5 (số Điều gold có ít nhất 1 chunk trong top-5 / tổng Điều gold), Hit@5, MRR@5, Recall@20; chấm trên top-5 cố định ở mọi cấu hình. Trả lời: tỉ lệ từ chối, context có gold.

**Điều kiện chạy:** cùng index 3.422 chunk, RRF k=60, LLM `gpt-6-luna` có cache. Latency và chi phí chưa được đo → N/A.

### Benchmark 6 Bộ luật — 40 câu, embedding `text-embedding-3-small`

*Đọc bảng này cùng cảnh báo ở trên: đây là bộ dễ, điểm cao hơn mức thực tế.*

| Cấu hình | Nhóm / số câu | Recall@5 | MRR@5 | Độ đúng/citation | Latency | Chi phí |
|---|---|---|---|---|---|---|
| BM25 | Tổng / 40 | 0.633 | 0.597 | N/A (chưa chấm tay) | N/A | N/A |
| Dense | Tổng / 40 | 0.600 | 0.548 | N/A | N/A | N/A |
| **Hybrid RRF (baseline)** | Tổng / 40 | 0.633 | 0.658 | Từ chối 11/40; context có gold 0.700 | N/A | N/A |
| Hybrid RRF | lookup / 16 | 1.000 | 0.969 | — | N/A | N/A |
| Hybrid RRF | paraphrase / 16 | 0.375 | 0.344 | — | N/A | N/A |
| Hybrid RRF | multi / 8 | 0.417 | 0.667 | — | N/A | N/A |
| + Jev rerank (p ≥ 0.6) | Tổng / 40 | 0.775 | 0.838 | Từ chối 8/40; context có gold 0.825 | N/A | N/A |
| + HyDE | Tổng / 40 | 0.742 | 0.703 | Từ chối 9/40; context có gold 0.825 | N/A | +1 LLM call/câu |
| **+ HyDE + Jev** | Tổng / 40 | **0.821** | **0.875** | Từ chối 8/40; context có gold 0.875 | N/A | +1 LLM call/câu |
| + HyDE + Jev | paraphrase / 16 | 0.812 | 0.781 | — | N/A | N/A |
| + HyDE + Jev | multi / 8 | 0.479 | 0.812 | — | N/A | N/A |

Nguồn: [`bench6-40q-gpt6luna/`](../../../evals/team-4.2/results/bench6-40q-gpt6luna/summary.md), [`bench6-40q-jev-p06/`](../../../evals/team-4.2/results/bench6-40q-jev-p06/summary.md), [`bench6-40q-hyde/`](../../../evals/team-4.2/results/bench6-40q-hyde/summary.md), [`bench6-40q-hyde-jev-p06/`](../../../evals/team-4.2/results/bench6-40q-hyde-jev-p06/summary.md), tổng hợp ở [`BENCHMARK_6_BO_LUAT.md`](../../../evals/team-4.2/results/BENCHMARK_6_BO_LUAT.md).

### Thí nghiệm embedding và bộ câu đời thường

| Cấu hình | Nhóm / số câu | Recall@5 | MRR@5 | Độ đúng/citation | Latency | Chi phí |
|---|---|---|---|---|---|---|
| Dense Jina v5 small | 6 Bộ luật / 100 | 0.912 | 0.853 | N/A | N/A | N/A |
| Hybrid (Jina v5) | 6 Bộ luật / 100 | 0.782 | 0.701 | N/A | N/A | N/A |
| Dense legal-e5 | 6 Bộ luật / 100 | 0.853 | 0.799 | N/A | N/A | N/A |
| Dense + HyDE + Jev (Jina v5) | 6 Bộ luật / 40 | 0.942 | 0.950 | N/A | N/A | N/A |
| Hybrid (OpenAI 3-small) | Đời thường / 20 (d01-d20) | 0.175 | 0.117 | N/A | N/A | N/A |
| Dense (Jina v5) | Đời thường / 64 | 0.594 | 0.499 | N/A | N/A | N/A |
| Hybrid (Jina v5) | Đời thường / 64 | 0.458 | 0.386 | N/A | N/A | N/A |
| Dense + HyDE, bỏ BM25 (OpenAI 3-small) + Jev | Đời thường / 64 | 0.625 | 0.635 | N/A | N/A | N/A |
| **Dense + HyDE, bỏ BM25 (Jina v5) + Jev** | Đời thường / 64 | **0.849** | **0.826** | N/A | N/A | N/A |
| Như trên + rerank Jina thay Jev | Đời thường / 64 | 0.518 | 0.358 | N/A | N/A | N/A |

Nguồn: [`bench6-100q-emb-jina`](../../../evals/team-4.2/results/bench6-100q-emb-jina/summary.md), [`bench6-100q-emb-legal-e5`](../../../evals/team-4.2/results/bench6-100q-emb-legal-e5/summary.md), [`bench6-40q-jina`](../../../evals/team-4.2/results/bench6-40q-jina/summary.md), [`doi-thuong-20q`](../../../evals/team-4.2/results/doi-thuong-20q/summary.md), [`doi-thuong-64q-emb-jina`](../../../evals/team-4.2/results/doi-thuong-64q-emb-jina/summary.md), [`doi-thuong-64q-hyde-nobm25`](../../../evals/team-4.2/results/doi-thuong-64q-hyde-nobm25/summary.md), [`doi-thuong-64q-hyde-nobm25-openai3small`](../../../evals/team-4.2/results/doi-thuong-64q-hyde-nobm25-openai3small/summary.md), [`doi-thuong-64q-rerank-jina`](../../../evals/team-4.2/results/doi-thuong-64q-rerank-jina/summary.md). Các lượt phụ khác (pool, merge, ctxheader, hyde-only) cũng nằm trong `evals/team-4.2/results/`.

## Failure analysis

Mọi case dưới đây lấy từ **bộ đời thường (bộ khó, 64 câu)** với cấu hình tốt nhất hiện có: Dense + HyDE + Jev, embedding Jina v5, bỏ BM25 (R@5 0.849). Nguồn số liệu từng câu là [`doi-thuong-64q-hyde-nobm25/retrieval_per_question.csv`](../../../evals/team-4.2/results/doi-thuong-64q-hyde-nobm25/retrieval_per_question.csv); trong đó "Dense + HyDE" là config `dense`, "+ Jev" là config `dense+rerank`. Trên bộ này mới chạy retrieval, **chưa chạy phần trả lời**, nên chưa phân tích được lỗi generation. Các case của bộ 6 Bộ luật (q09–q38) vẫn được lưu ở [`BENCHMARK_6_BO_LUAT.md`](../../../evals/team-4.2/results/BENCHMARK_6_BO_LUAT.md). Bộ đó dễ nên lỗi của nó ít đại diện cho người dùng thật, vì vậy không đưa vào bảng này.

| Case | Kỳ vọng / thực tế | Bằng chứng | Bước gây lỗi | Cách sửa / kết quả chạy lại |
|---|---|---|---|---|
| d18 "tòa gửi giấy gọi lên mà tôi bận không đi được thì sao" | Gold TTDS Đ227 (sự có mặt của đương sự). Dense + HyDE R@5 = **1.00**, nhưng sau Jev còn **0.00**: top-5 toàn Bộ luật Tố tụng hình sự (Đ182 triệu tập bị can, Đ290 sự có mặt của bị cáo) | `retrieval_per_question.csv`, dòng d18 | Rerank kết hợp với câu hỏi mơ hồ về lĩnh vực: "tòa gọi" có thể là vụ dân sự hoặc hình sự, Jev chọn hẳn một phía | Chưa sửa. Hướng thử: khi top-k trải trên nhiều bộ luật thì hỏi lại người dùng (`clarify`), hoặc giữ đủ nguồn từ mỗi bộ luật trong context |
| d17, d52, d59, d62 (vd. d62 "đi tàu ra đảo bị mất vali, hãng tàu có phải đền không") | Gold có trong top-20 (R@20 = 1.00) nhưng Jev đẩy gold xuống: d62 giảm 1.00 → 0.50 vì Jev xếp DS Đ541/Đ528 (hợp đồng vận chuyển chung) lên trên HH Đ213; d17 0.50 → 0.00, d52 và d59 1.00 → 0.50 | `retrieval_per_question.csv`. Tính trên 64 câu, Jev làm tăng R@5 ở 7 câu, làm giảm ở 5 câu (gồm cả d18) | Rerank: Jev ưu tiên Điều chung của Bộ luật Dân sự hơn luật chuyên ngành (Hàng hải) và đoạn có từ khoá gần câu hỏi hơn Điều gold | Chưa sửa. Hướng thử: kết hợp điểm dense với điểm rerank thay vì chỉ dùng điểm rerank; tách tập dev để quyết định có dùng Jev hay không |
| d09 "chuyển khoản cọc mua hàng trên mạng xong bị block luôn" | Gold HS Đ174 (lừa đảo chiếm đoạt tài sản). R@5 = 0 ở **mọi** cấu hình dù R@20 = 1.00; top-5 có DS Đ328 (đặt cọc), Đ330 | `retrieval_per_question.csv` (`doi-thuong-64q-hyde-nobm25`, `doi-thuong-64q-emb-jina`) | Retrieval/HyDE: câu hỏi không có từ "lừa", chữ "cọc" kéo cả HyDE lẫn Jev về hướng tranh chấp dân sự. Ở bộ dễ, câu tương tự (q31, "lừa người ta lấy 30 triệu") thì HyDE cứu được | Chưa sửa. Hướng thử: HyDE sinh nhiều giả thuyết song song (dân sự và hình sự) rồi gộp kết quả |
| d01 "hôm nay tôi lỡ tông phải một ông già lúc sang đường, không biết có bị sao không" | Cần 3 Điều trên 2 bộ luật: HS Đ260, DS Đ601 (nguồn nguy hiểm cao độ), DS Đ590. Chỉ lấy được HS Đ260: R@5 = R@20 = 0.33 ở mọi cấu hình | `retrieval_per_question.csv`, dòng d01 | Retrieval: một truy vấn duy nhất không phủ hết các vế (hình sự + bồi thường dân sự); thuật ngữ "nguồn nguy hiểm cao độ" không xuất hiện trong câu (cùng lỗi với q32 ở bộ dễ) | Chưa sửa. Hướng thử: query decomposition (owner A) |
| d57 "người nợ tiền tôi đang sống ở nước ngoài, giờ muốn kiện thì nộp đơn ở đâu"; d17 "say quá đập vỡ đồ của quán" | d57: gold TTDS Đ37, R@20 = 0, nhưng top-5 có TTDS Đ469 (thẩm quyền của Tòa án Việt Nam với vụ việc có yếu tố nước ngoài) và Đ40. d17: top-1 là DS Đ596 (bồi thường do người dùng chất kích thích gây ra) nhưng Điều này không có trong gold | `retrieval_per_question.csv`; tiêu đề Điều lấy từ `data/team-4.2/processed/chunks.jsonl` | **Nhãn đánh giá**: gold có thể quá hẹp. Nhãn do LLM sinh, chưa có người thứ hai rà soát | Chưa sửa. Cần rà lại nhãn và cho phép nhiều Điều gold thay thế; điểm R@5 ở các câu này có thể đang **thấp hơn** thực tế |
| BM25 làm loãng kết quả khi fusion | Kỳ vọng Hybrid ≥ Dense, thực tế Hybrid 0.458 < Dense 0.594 (Jina, 64 câu) | `doi-thuong-64q-emb-jina/summary.md` | Fusion RRF: với câu văn nói, arm BM25 kéo đoạn sai lên | Bỏ BM25, dùng Dense + HyDE + Jev → R@5 0.849 / MRR@5 0.826 (`doi-thuong-64q-hyde-nobm25`) |

## Findings and limitations

**Phát hiện quan trọng nhất: bộ eval ban đầu quá dễ, che mất điểm yếu của pipeline**

- Bộ 6 Bộ luật soạn từ nguyên văn Điều nên câu hỏi trùng nhiều từ với văn bản luật. Kết quả tốt trên bộ này (đến 0.821–0.942 R@5) chủ yếu phản ánh độ dễ của câu hỏi, không phản ánh chất lượng retrieval với người dùng thật.
- Nhóm lookup (40% bộ) đạt 1.000 ở mọi cấu hình, nên không có giá trị so sánh.
- Trên câu văn nói, baseline Hybrid RRF (OpenAI) giảm từ 0.633 xuống **0.175** R@5; Dense Jina giảm 0.912 → 0.594. Pipeline mặc định của tuần này **chưa tối ưu** cho cách hỏi thực tế.
- Chỉ khi đo trên bộ đời thường mới thấy các vấn đề thật: BM25 làm hại fusion, embedding OpenAI 3-small yếu với văn nói, phải có HyDE + rerank mới lên được ~0.85. Nếu chỉ dùng bộ cũ, nhóm có thể đã dừng ở baseline.
- Bài học cho các tuần sau: không soạn câu hỏi eval bằng cách nhìn vào đáp án; cần câu do người khác (hoặc người dùng thật) viết, có câu mơ hồ, thiếu dữ kiện và ngoài phạm vi.

**Giả thuyết được dữ liệu hỗ trợ**

- Hybrid RRF không vượt rõ ràng từng arm trên 40 câu (Recall@5 0.633 = BM25), chỉ cải thiện MRR@5 (0.658 vs 0.597/0.548).
- Rerank Jev chủ yếu sửa xếp hạng (paraphrase R@5 0.375 → 0.750) nhưng bị chặn bởi trần Recall@20; HyDE nâng trần Recall@20 (0.783 → 0.838). Kết hợp hai cách cho kết quả tốt nhất (0.821 / 0.875).
- Embedding chọn ảnh hưởng lớn nhất: trên 100 câu, Dense Jina v5 (0.912) > legal-e5 (0.853) > Hybrid (0.78); trên bộ đời thường OpenAI 3-small chỉ đạt 0.625 so với 0.849 của Jina trong cùng cấu hình.
- Với câu văn nói, BM25 gây hại khi fusion bằng RRF.

**Không được hỗ trợ / chưa kiểm chứng**

- Trên bộ đời thường, Jev chỉ thêm +0.026 R@5 (Dense + HyDE 0.823 → 0.849): tăng ở 7 câu, giảm ở 5 câu. Kết luận "rerank sửa xếp hạng" rút ra từ bộ dễ không còn rõ ràng trên bộ khó.
- Rerank Jina không thay được Jev (R@5 0.518 vs 0.849 trên bộ đời thường).
- Câu multi vẫn yếu ở mọi cấu hình (R@5 tối đa 0.479 với OpenAI embedding).

**Giới hạn**

- **Bộ 6 Bộ luật thiên lệch dễ** (soạn từ nguyên văn Điều, 40% lookup bão hoà ở 1.000) → không nên dùng số trên bộ này để kết luận pipeline đã đủ tốt. Bộ đời thường sát thực tế hơn nhưng vẫn do LLM sinh, chưa phải câu hỏi của người dùng thật.
- Mẫu nhỏ: 1 câu = 0.025 điểm trên 40 câu, 0.125 trong nhóm multi 8 câu.
- Câu hỏi và đáp án mẫu do một người (với LLM hỗ trợ) soạn, chưa có người thứ hai/luật sư rà soát.
- `CONTEXT_MIN_P=0.6` chọn trên chính benchmark (không có tập dev riêng) → số liệu có Jev có thể lạc quan.
- Chưa chấm tay đúng/sai và citation; chưa có câu `out_of_scope`; HyDE có thể tăng trả lời nhầm với câu ngoài phạm vi.
- `gpt-6-luna` không nhận temperature=0; kết quả lặp lại được nhờ cache, xoá cache có thể khác.
- Gold ở cấp Điều, không phân biệt khoản/điểm.
- Latency và chi phí chưa đo.

**Hành động tiếp theo** (owner theo phân công sprint, cần team xác nhận)

| Việc | Owner |
|---|---|
| Đổi embedding mặc định sang Jina v5, chạy lại answers với Dense + HyDE + Jev | C — Lương Quang Huy |
| Lấy bộ đời thường làm benchmark chính; bổ sung câu hỏi do người ngoài nhóm viết, không nhìn vào văn bản luật | C + B |
| Thêm câu `out_of_scope`, tách tập dev/test, chọn lại ngưỡng trên dev | C + B |
| Query decomposition cho câu multi | A — Mai Phan Anh Tùng |
| Chấm tay `correct` / `citation_ok` cho 40 câu | E — Nguyễn Anh Tú |
| Guardrail 2 tầng; đo latency/chi phí trong runner | D — Nguyễn Quốc Tuấn |

