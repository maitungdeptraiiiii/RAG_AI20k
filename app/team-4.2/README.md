# app — Team 4.2

[Trang team](../../teams/team-4.2/README.md) · [Quy chuẩn chung](../README.md)

Baseline Hybrid RAG (BM25 + Dense + RRF) cho văn bản luật tiếng Việt. Sản phẩm phát triển liên tục qua 5 tuần trong thư mục này, không sao chép code theo tuần.

Tài liệu ingestion/data quality: [schema và interface](docs/SCHEMA_AND_INTERFACES.md) · [luồng xử lý](docs/workflow.md).

## Think trên thanh chat

Nút **Think** mặc định tắt, chuyển sang chữ/icon xanh trên nền xanh nhạt khi bật.
UI gửi `think: true/false` theo từng câu hỏi; đổi nút khi đang chờ không thay đổi request đã gửi.
Mở/tạo đoạn chat khác đặt Think về tắt. Lịch sử từng lượt lưu lựa chọn `think`.

`POST /api/chat` không có `think` hoặc có `think: false` dùng RAG hiện tại, bao gồm
condense/decomposition và các phương pháp retrieval đang cấu hình. `think: true` chỉ đi vào
`get_agent_pipeline()` trong `ui/server.py`, cho cả JSON và SSE. Agent multi-hop đã được nối:
lập requirements → tìm kiếm/rerank → đánh giá phần thiếu → search/xref bổ sung → compose → verify.
Mặc định tối đa 3 vòng, 8 search và 12 đích xref; state/ngân sách riêng theo request.
SSE hiển thị tiến độ, chỉ phát đáp án sau kiểm chứng; có trạng thái partial/clarify/abstain/error.
V1 trả lời theo snapshot corpus, chưa xác nhận hiệu lực pháp luật hiện hành.
Xem [hướng dẫn, cấu hình và giới hạn](docs/MULTIHOP_AGENT.md),
[bản thiết kế](docs/plans/2026-11-10-multihop-agent-architecture.md).
CLI: `python scripts/team-4.2/ask.py --think "Câu hỏi nhiều bước"`.

## Cấu trúc

```text
app/team-4.2/
├── pyproject.toml        # package `rag` (src layout), extras: jev, dev
├── .env.example          # biến môi trường mẫu, chỉ placeholder
├── src/rag/
│   ├── schema.py         # hợp đồng dữ liệu chung (Page, Chunk, Hit, Answer, ...)
│   ├── models/           # Source/Version/Block/ChunkV2 và quality records
│   ├── versioning/       # lập kế hoạch, SQLite catalog và phạm vi hiệu lực
│   ├── quality/          # validation contracts và review queue
│   ├── config.py         # Settings đọc .env / biến môi trường
│   ├── ingest/           # loaders (PDF/URL/TXT), chunker, vbpl (crawler vbpl.vn)
│   ├── index/            # store (chunks.jsonl), bm25_index, embedder, vector_index
│   ├── retrieve/         # fusion (RRF), hybrid, rerank (Jev), context (chọn đoạn cho LLM)
│   ├── generate/         # llm (gpt-6-luna + cache), answer (prompt + citation)
│   ├── advanced/         # phương pháp nâng cao dạng plugin: hyde, contextual (bật bằng ADVANCED)
│   ├── eval/             # metrics (Recall@k, MRR@k), runner
│   └── pipeline.py       # RAGPipeline: ingest(), ask(), ask_debug()
├── ui/                   # server.py + index.html (Just-ice ChatGPT-style UI)
├── tests/                # mỗi module một test_<module>.py
└── docs/
    ├── tech_stack.md     # lựa chọn stack và lý do (nên tách thành ADR)
    ├── phan_cong_sprint1.md
    └── plans/2026-11-01-baseline-rag.md
```

Dữ liệu, evaluation, thí nghiệm, scripts và báo cáo nằm ở thư mục team tương ứng ngoài `app/`:
`data/team-4.2/`, `evals/team-4.2/`, `experiments/team-4.2/`, `scripts/team-4.2/`, `reports/week-0N/team-4.2/`.

## Cài đặt và chạy (tại gốc repo)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "app/team-4.2[dev]"          # thêm [jev] nếu dùng reranker Jev
cp app/team-4.2/.env.example app/team-4.2/.env   # điền key, KHÔNG commit .env
pytest app/team-4.2/tests -v
```

Các lệnh (tại gốc repo, sau khi điền `.env`):

```bash
python scripts/team-4.2/crawl_vbpl.py 36/2005/QH11              # crawl văn bản từ vbpl.vn theo số hiệu -> data/team-4.2/raw/vbpl/
python scripts/team-4.2/ingest.py data/team-4.2/raw/            # ingest PDF/TXT/MD trong thư mục, hoặc URL
python scripts/team-4.2/ask.py "Câu hỏi ..."                     # trả lời + citation + kết quả từng arm
python app/team-4.2/ui/server.py                                  # UI chat Just-ice (Starlette + Canvas)
python evals/team-4.2/runners/run_eval.py --answers              # Recall@5, MRR@5 (BM25/Dense/Hybrid) + từ chối
python evals/team-4.2/runners/draft_references.py               # nháp đáp án mẫu, người viết câu hỏi kiểm tra lại
python evals/team-4.2/runners/export_ragas.py                   # dữ liệu đầu vào cho RAGAS
```

Chưa có: guardrail (TV5), bước chấm bằng RAGAS (chờ chốt version `ragas`). Toàn bộ test hiện chạy với
client giả; cần chạy thử một lần với PyMuPDF, trafilatura, pyvi, OpenAI, Qdrant và Jev thật.

## Query decomposition

`QUERY_REWRITE_ENABLED=true` bật một rewrite trung thành với toàn bộ câu hỏi cho Jev.
Trong mode hybrid, BM25 của nhánh câu gốc cũng dùng rewrite; Dense/HyDE vẫn dùng câu gốc,
các nhánh câu con vẫn dùng câu con. Câu hỏi trả lời cuối vẫn là câu gốc. Mặc định tắt,
độc lập với `DECOMP_ENABLED`. Rewrite lỗi thì giữ câu gốc và ghi lỗi trong kết quả.
`BM25_RRF_WEIGHT=1.0` là fusion ngang trọng số với Dense; ví dụ `0.3` giảm đóng góp BM25
theo công thức `sum(weight_arm / (RRF_K + rank_arm))`. Không ảnh hưởng mode Dense.
Đặt `QUERY_REWRITE_ENABLED=true`, `REWRITE_FOR_RERANK=false` để chỉ dùng rewrite cho BM25
và giữ câu gốc cho Jev. Khi đó mode Dense không gọi rewriter.

`COVERAGE_ENABLED=true` bật bước chọn bằng chứng sau Jev khi có ít nhất hai nhánh câu con
và bật gộp Điều. Mặc định tắt. Bước này không gọi thêm model và không đổi pool hoặc xác suất Jev:
giữ `COVERAGE_ANCHOR_K=2` vị trí đầu; chọn các vị trí còn lại theo điểm Jev và độ phủ mới của
câu con, với `COVERAGE_WEIGHT=0.25`, `COVERAGE_MIN_P=0.5`, `COVERAGE_BRANCH_K=5`.
Độ phủ dùng thứ hạng retrieval làm tín hiệu thay thế, không phải kiểm chứng ngữ nghĩa.
Thứ tự mới áp dụng cho cả top-k benchmark và danh sách chọn context; điểm hiển thị vẫn là
xác suất Jev gốc, nên thứ tự có thể không giảm dần theo điểm. Chạy fallback/non-Jev thì bỏ qua bước này.
Benchmark offline một cấu hình bằng cache: `python evals/team-4.2/runners/run_coverage_benchmark_offline.py`.

Bật bằng `DECOMP_ENABLED=true`, tắt bằng `false` (mặc định). Không cần ingest/index lại.
Độc lập với HyDE và mode retrieval: `--mode dense` không tìm BM25; `--mode hybrid` tìm cả hai.

```dotenv
ADVANCED=hyde
DECOMP_ENABLED=true
DECOMP_MAX_SUBQUERIES=3
DECOMP_INCLUDE_ORIGINAL=true
DECOMP_PER_QUERY_K=10
DECOMP_POOL_SIZE=30
DECOMP_MAX_NEW_ARTICLES=10
RERANK_BACKEND=jev
```

Flow: câu gốc → LLM phân rã → câu gốc + tối đa 3 câu con → retrieve từng câu
(Dense dùng HyDE nếu bật) → giữ nguyên pool câu gốc; RRF chọn các Điều mới từ câu con
→ bổ sung tối đa 10 Điều mới → Jev chấm một lần bằng câu gốc
→ chọn context → trả lời câu gốc với citation. Khi gộp Điều bật, giới hạn pool tính theo Điều;
một Điều có thể có nhiều chunk được Jev chấm riêng. Khi `DECOMP_INCLUDE_ORIGINAL=true`,
giữ toàn bộ pool câu gốc (`RERANK_N=20`) và thứ tự của nó; `DECOMP_PER_QUERY_K=10` chỉ cắt
nhánh câu con. Điều đã có trong pool gốc không được tính là Điều mới. Tổng ngân sách mặc định
30 Điều; số Điều mới luôn không vượt `DECOMP_MAX_NEW_ARTICLES=10`, kể cả khi pool gốc ít hơn 20.
Giữ giới hạn context hiện tại.

System prompt nằm trong `src/rag/advanced/decomposition.py`. Câu đơn ý giữ nguyên flow baseline;
JSON sai hoặc LLM lỗi thì dùng câu gốc và lưu lỗi trong trace. Câu con phải giữ dữ kiện, phủ định,
điều kiện; không tự thêm số Điều hay kết luận pháp lý. Đoạn HyDE không được đưa vào context trả lời.
CLI và UI hiển thị các truy vấn trong chi tiết retrieval.

```powershell
$env:DECOMP_ENABLED='true'
python scripts/team-4.2/ask.py --mode dense "Điều kiện hưởng trợ cấp thất nghiệp và hồ sơ cần nộp?"
python evals/team-4.2/runners/run_decomposition_benchmark.py
```

Runner chỉ chạy decomposition trên **64 câu** trong `benchmark_doi_thuong.jsonl`,
không chạy lại baseline và không dùng BM25. Mặc định tạo thư mục kết quả mới theo thời gian.
Muốn đối chiếu offline, truyền `--baseline-csv <file kết quả cũ>` và `--baseline-config <tên cấu hình>`;
các tham số này chỉ đọc CSV đã lưu, không gọi API cho baseline. Dữ liệu/index/cấu hình của hai lần
chạy cần tương thích; cùng ID câu hỏi chưa đủ bảo đảm khả năng so sánh. Kết quả gồm CSV từng câu, truy vấn con,
cấu hình không chứa key và bảng tổng hợp. Dừng nếu HyDE/Jev lỗi; không coi fallback là kết quả của
cấu hình được đo. Đây là benchmark retrieval; thời gian có ảnh hưởng cache. Decomposition dùng tối đa 30 Điều sau fusion khi thực sự có tách câu.


## Mốc baseline cố định và kiểm tra offline

Kết quả kiểm tra nằm trong `evals/team-4.2/results/baseline-audit-64q/report.md`.
Các artifact đối chứng được chụp vào `baseline-audit-64q/frozen/`, có SHA-256 trong `manifest.json`:

- Mốc sản phẩm chính: `historical.csv`, cấu hình `dense+rerank` (Recall@5 0.848958, MRR@5 0.826042).
- Mốc phân tích tác động có trace/cache tương thích: `controlled.csv`, cấu hình `hyde+jev`
  (Recall@5 0.835938, MRR@5 0.800000).

Không thay mốc lịch sử bằng mốc thấp hơn để tuyên bố cải thiện. Lần sau chỉ chạy cấu hình mới;
đối chiếu bằng CSV đã lưu, không gọi lại API cho baseline. Cùng số câu/model name chưa chứng minh
cùng điều kiện: lần lịch sử thiếu fingerprint của input/prompt/điểm và trace từng câu.

`python evals/team-4.2/runners/audit_baseline_offline.py` chỉ đọc CSV, trace và SQLite cache read-only,
tính lại metric và sắp xếp điểm đã lưu; không gọi retriever hoặc API. Phép bootstrap trong báo cáo
chỉ mô tả độ bất định trên bộ 64 câu đang có, không thay thế đánh giá trên bộ câu hỏi độc lập.
