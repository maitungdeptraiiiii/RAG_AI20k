# Benchmark multi-hop khó: 25 câu mới

Đánh giá retrieval theo cấu hình project tại ngày 06/11/2026. Không chạy generation trả lời cuối.

## Dữ liệu và kiểm tra chất lượng

- Bộ cũ: `evals/team-4.2/datasets/benchmark_doi_thuong.jsonl` (64 câu), không thay đổi; SHA-256 xác nhận trước/sau.
- Pipeline benchmark gốc: `evals/team-4.2/runners/run_eval.py` → `rag.eval.runner.retrieval_rows` → `RAGPipeline.retriever`; runner decomposition 64 câu tại `runners/run_decomposition_benchmark.py`. Runner mới dùng cùng retriever và hàm metric của repo, bổ sung trace, kiểm tra lỗi nghiêm ngặt và all-gold coverage.
- Bộ mới: `evals/team-4.2/datasets/benchmark_multihop_hard25.jsonl`; 25 câu `multi`, 25/25 nối ít nhất hai bộ luật; 12 câu có 3 gold, 12 có 4, 1 có 5.
- Gold theo `source` + `section` đúng schema `Question`/`GoldRef`; kèm `reference`, `gold_articles`, `gold_chunk_ids`, `reasoning_steps`, `evidence` để kiểm tra từng mắt xích.
- Không gold nào thiếu trong index; văn bản evidence và tập chunk liên quan được đối chiếu chính xác với corpus.
- Không trùng nguyên văn hoặc trùng toàn bộ tập gold với bộ cũ. Sàng lọc từ vựng và rà soát tình huống/chủ đề, không chỉ đổi tên hoặc con số. Có thể dùng chung Điều nền tảng (ví dụ nghĩa vụ chứng minh) mà không trùng bài toán pháp lý.
- Jaccard từ cao nhất so bộ cũ: 0.163; trong bộ mới: 0.269. Đây là chỉ báo sàng lọc, không phải chứng minh không trùng ngữ nghĩa.
- Ground truth là bản tác giả rà soát theo snapshot repo, chưa có vòng chuyên gia pháp lý độc lập; không xác nhận hiệu lực pháp luật hiện hành. Các câu phân biệt điều kiện, ngoại lệ; reference tránh khẳng định khi dữ kiện còn thiếu.

## Cấu hình chạy

- Index: `data\team-4.2\ablation\decomposition-anchor20-add10`; 3422 chunk, 6 nguồn.
- Embedding: `jina-embeddings-v5-text-small`, 1024 chiều; LLM hỗ trợ retrieval: `gpt-6-luna`; reranker: `jev-1.13.0`.
- Giữ cấu hình .env: HyDE bật, decomposition bật, Jev rerank bật, listwise bật; rewrite tắt sẵn, coverage tắt sẵn. Không sửa .env.
- ARM_K=20, RERANK_N=20, TOP_K=5, RRF_K=60, BM25_RRF_WEIGHT=0.0; vẫn gọi các arm đang cấu hình, trọng số BM25 bằng 0.
- Gộp theo Điều; article_pool_factor=2; decomposition tối đa 3 câu con + câu gốc, mỗi nhánh k=10, pool=30, thêm tối đa 10 Điều mới sau khi giữ pool câu gốc.
- Listwise chỉ chạy khi qua gate: có >=2 câu con, shortlist đủ Điều đạt min_p, khoảng cách quanh ngưỡng top5 đủ nhỏ; không phải bật là luôn gọi.
- Runner chỉ gọi `retriever.retrieve`; chặn `ask`, `ask_debug`, `answer_question` bằng hàm báo lỗi. HyDE vẫn có thể sinh đoạn giả để tìm kiếm; đó không phải câu trả lời cuối.
- Xử lý lỗi nghiêm ngặt: HyDE không âm thầm quay về dense gốc; lỗi decomposition, rerank hoặc listwise dừng run và giữ checkpoint. Các attempt kết nối thất bại được tách riêng, không đưa vào metrics xác nhận.
- Model/config, commit, phiên bản thư viện và hash dữ liệu được ghi trong `config.json`.

## Metrics

| Metric | Kết quả |
|---|---:|
| recall@5 | 0.8020 |
| hit@5 | 1.0000 |
| mrr@5 | 0.9600 |
| recall@20 | 0.8900 |
| all_gold@5 | 0.4400 |
| all_gold@20 | 0.6800 |
| merged_recall@5 | 0.8020 |
| merged_recall@20 | 0.8900 |
| candidate recall (toàn pool trước rerank) | 0.8900 |

Recall/Hit/MRR giữ cách chấm chunk đại diện của repo. `merged_recall` và `all_gold` kiểm tra cả các chunk gộp của từng Điều; `all_gold` = tỷ lệ câu đủ tất cả căn cứ, phù hợp đo multi-hop. Recall là macro trung bình theo câu, không phải tỷ lệ chunk.
Run xác nhận: 25/25 câu, 0 câu lỗi, generation calls = 0. Tổng latency từng câu 636.5s; có ảnh hưởng cache nên không dùng làm latency production.
LLM retrieval: 128 lượt gọi logic, 25 cache hit, 103 lượt gọi SDK. SDK có thể retry nội bộ; đây không phải bộ đếm toàn bộ HTTP/token/chi phí của mọi dịch vụ. Không tính các attempt bị hủy hoặc chẩn đoán mạng.

## Lỗi retrieval và thiếu mắt xích

Các nhóm dưới đây đếm gold bị thiếu trong top5, phân biệt mất từ pool với có trong pool nhưng xếp hạng thấp:

- `missing_from_candidate_pool`: 10 căn cứ.
- `in_top20_but_not_top5`: 8 căn cứ.

Listwise được kích hoạt 8/25 câu. Gate: `{'clear_cutoff': 8, 'ambiguous_cutoff': 8, 'few_eligible_candidates': 9}`.
Trong 9 lần qua gate, so với thứ tự Jev ngay trước chọn listwise trên cùng pool, 4 câu tăng recall@5, 5 câu giữ nguyên, không câu nào giảm; chi tiết trong `failure_analysis.json`.
Không suy nguyên nhân tuyệt đối từ thứ hạng: trace chỉ xác định khâu mất căn cứ; muốn quy trách nhiệm HyDE/decomposition/rerank riêng cần ablation trên cùng bộ mới.

| ID | Recall@5 | Recall@20 | Căn cứ thiếu ở top5 và vị trí thất lạc |
|---|---:|---:|---|
| mh25_01 | 1.000 | 1.000 | Đủ gold |
| mh25_02 | 1.000 | 1.000 | Đủ gold |
| mh25_03 | 0.333 | 0.667 | bo_luat_to_tung_dan_su_2015 Điều 91 (missing_from_candidate_pool); bo_luat_to_tung_dan_su_2015 Điều 94 (in_top20_but_not_top5) |
| mh25_04 | 0.667 | 0.667 | bo_luat_to_tung_dan_su_2015 Điều 126 (missing_from_candidate_pool) |
| mh25_05 | 0.333 | 1.000 | bo_luat_dan_su_2015 Điều 166 (in_top20_but_not_top5); bo_luat_to_tung_dan_su_2015 Điều 91 (in_top20_but_not_top5) |
| mh25_06 | 1.000 | 1.000 | Đủ gold |
| mh25_07 | 1.000 | 1.000 | Đủ gold |
| mh25_08 | 1.000 | 1.000 | Đủ gold |
| mh25_09 | 1.000 | 1.000 | Đủ gold |
| mh25_10 | 0.750 | 1.000 | bo_luat_dan_su_2015 Điều 579 (in_top20_but_not_top5) |
| mh25_11 | 0.500 | 0.500 | bo_luat_dan_su_2015 Điều 554 (missing_from_candidate_pool); bo_luat_to_tung_dan_su_2015 Điều 91 (missing_from_candidate_pool) |
| mh25_12 | 1.000 | 1.000 | Đủ gold |
| mh25_13 | 1.000 | 1.000 | Đủ gold |
| mh25_14 | 1.000 | 1.000 | Đủ gold |
| mh25_15 | 1.000 | 1.000 | Đủ gold |
| mh25_16 | 1.000 | 1.000 | Đủ gold |
| mh25_17 | 0.800 | 1.000 | bo_luat_to_tung_dan_su_2015 Điều 32 (in_top20_but_not_top5) |
| mh25_18 | 0.667 | 0.667 | bo_luat_to_tung_hinh_su_2015 Điều 85 (missing_from_candidate_pool) |
| mh25_19 | 0.500 | 0.500 | bo_luat_hinh_su_2015 Điều 57 (missing_from_candidate_pool); bo_luat_to_tung_hinh_su_2015 Điều 85 (missing_from_candidate_pool) |
| mh25_20 | 0.750 | 1.000 | bo_luat_to_tung_hinh_su_2015 Điều 447 (in_top20_but_not_top5) |
| mh25_21 | 0.750 | 1.000 | bo_luat_hinh_su_2015 Điều 341 (in_top20_but_not_top5) |
| mh25_22 | 0.750 | 0.750 | bo_luat_to_tung_dan_su_2015 Điều 91 (missing_from_candidate_pool) |
| mh25_23 | 0.750 | 0.750 | bo_luat_to_tung_dan_su_2015 Điều 94 (missing_from_candidate_pool) |
| mh25_24 | 0.750 | 1.000 | bo_luat_to_tung_dan_su_2015 Điều 91 (in_top20_but_not_top5) |
| mh25_25 | 0.750 | 0.750 | bo_luat_to_tung_dan_su_2015 Điều 184 (missing_from_candidate_pool) |

## Rà soát tính mới theo nội dung

Bộ cũ chỉ được dùng để nhận diện văn phong và kiểm tra loại trừ sau khi soạn. Các nhóm gần về lĩnh vực nhưng khác bài toán đã được xem xét:

- Thừa kế (d10/d38/d39/d44) khác việc người bị tuyên chết trở về và xử lý người cố tình giấu tin (mh25_01).
- Trộm tài sản của người chưa thành niên (d12/d26) khác quyền đòi lại tài sản qua người mua ngay tình (mh25_05).
- Cho vay, lãi và đòi nợ (d08/d32) khác chuyển quyền yêu cầu không báo, bảo lãnh trả thay và bắt đầu lại thời hiệu hợp đồng thiết kế (mh25_06–08).
- Nghỉ việc/sa thải/trợ cấp thôi việc (d04–06/d50) khác chuyển loại hợp đồng, điều chuyển vượt hạn, tạm đình chỉ rồi minh oan, ký sai thẩm quyền và cắt giảm do tự động hóa (mh25_13–17).
- Tai nạn tàu/cứu hộ/hành lý (d61–64) khác kho lạnh và mất quyền giới hạn, ký hậu vận đơn, ưu tiên cầm giữ và phân bổ tổn thất chung (mh25_22–25).
- Các tình huống còn lại đặt trọng tâm mới ở tự giao dịch của giám hộ, vượt đại diện, tặng cho giả tạo, ưu tiên mua phần sở hữu, tiền chuyển nhầm sinh lợi, gửi giữ trái phép, trách nhiệm vật chất, hành vi vượt quá của đồng phạm, nguyên nhân dừng hành vi, năng lực ở hai thời điểm và giấy tờ giả liên kết vô hiệu.

## Chạy lại và kiểm chứng

Tại gốc repo (PowerShell):

```powershell
$env:PYTHONPATH='app/team-4.2/src'
$env:PYTHONIOENCODING='utf-8'
python evals/team-4.2/runners/build_multihop_hard25.py
python evals/team-4.2/runners/run_multihop_hard25.py --out evals/team-4.2/results/<thu-muc-moi>
python evals/team-4.2/runners/analyze_multihop_hard25.py --out evals/team-4.2/results/<thu-muc-moi>
```

Cần cùng .env và snapshot index như `config.json`; runner đọc .env tại thời điểm chạy, không tự khôi phục cấu hình. Dùng `--resume` với cùng `--out` nếu run nghiêm ngặt dừng; runner kiểm tra hash/config trước khi nối tiếp. Phân tích offline không gọi mô hình.

Artifacts: `quality_audit.json`, `config.json`, `retrieval_provenance.json` (model rerank, hash prompt/code), `retrieval_llm_outputs.json` (đầu ra LLM hỗ trợ retrieval đã dùng), `retrieval_per_question.csv`, `query_traces.json`, `metrics.json`, `failure_analysis.json`, `call_counts.json`, `summary.md`.
