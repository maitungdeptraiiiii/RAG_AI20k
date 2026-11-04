# Tracker tuần 1 — Team 4.2

[Kế hoạch](README.md) · [Tiến độ toàn khóa](../../docs/PROGRESS.md)

Thời gian: 01/11/2026 – 04/11/2026 (theo commit; **cần nhóm xác nhận lịch chính thức**). Status: In review. Owner tích hợp: A — Mai Phan Anh Tùng (nhánh `feat/team-4.2/w01-integration`). Team: 4.2.

Ký hiệu thành viên: A Mai Phan Anh Tùng · B Nguyễn Gia Khánh · C Lương Quang Huy · D Nguyễn Quốc Tuấn · E Nguyễn Anh Tú ([trang team](../../teams/team-4.2/README.md)).

## Tasks and acceptance criteria

Trạng thái: Not started / In progress / Blocked / In review / Done. Tách task lớn thành các dòng nhỏ; mỗi dòng có một owner và reviewer.

Reviewer ghi theo người merge PR trên GitHub; cần nhóm xác nhận nếu người review thực tế khác.

| ID | Task / acceptance criteria | Owner | Reviewer | Status | Issue / PR / evidence |
|---|---|---|---|---|---|
| T4.2-W01-01 | App có UI chạy upload → ingest → hỏi → trả lời có citation. | D | A (merge PR #11) | Done | PR #11 · [`streamlit_app.py`](../../app/team-4.2/ui/streamlit_app.py): upload PDF/TXT/MD, bảng top-5 từng arm + kết quả cuối, citation |
| T4.2-W01-01a | Ingestion: loader PDF/URL/TXT/MD, chunk theo Điều, metadata `source` + `section`. | B | A (merge PR #5) | Done | PR #5 · `app/team-4.2/src/rag/ingest/` · snapshot 3.422 chunk ([data](../../data/team-4.2/README.md)) |
| T4.2-W01-01b | Generation + citation; từ chối khi context rỗng (không gọi LLM). | E | E (tự merge PR #10) — **cần người khác review** | Done | PR #10 · `app/team-4.2/src/rag/generate/answer.py` |
| T4.2-W01-02a | BM25 (pyvi) và RRF fusion (k=60) chạy độc lập. | A | C (cần xác nhận) | Done | PR #7 · BM25 0.633 / Hybrid 0.633 R@5 trên 40 câu ([`bench6-40q-gpt6luna`](../../evals/team-4.2/results/bench6-40q-gpt6luna/summary.md)) |
| T4.2-W01-02b | Dense (embedding + Qdrant local) chạy độc lập. | C | A (merge PR #9) | Done | PR #9 · Dense 0.600 R@5 (OpenAI) / 0.912 (Jina, 100 câu) ([`bench6-100q-emb-jina`](../../evals/team-4.2/results/bench6-100q-emb-jina/summary.md)) |
| T4.2-W01-03a | Evaluation ≥10 câu/bộ tài liệu, Recall@5 và MRR@5. | C | A (cần xác nhận) | Done | [`benchmark_6_bo_luat.jsonl`](../../evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl) 100 câu, [`benchmark_doi_thuong.jsonl`](../../evals/team-4.2/datasets/benchmark_doi_thuong.jsonl) 64 câu, [`run_eval.py`](../../evals/team-4.2/runners/run_eval.py) |
| T4.2-W01-03b | Failure analysis ≥3 case (trên bộ đời thường). | A | Cần điền | In review | [report.md › Failure analysis](../../reports/week-01/team-4.2/report.md#failure-analysis): 6 case |
| T4.2-W01-03c | Chấm tay `correct` / `citation_ok` câu trả lời. | E | Cần điền | Not started | Cột trong `answers.csv` còn trống |
| T4.2-W01-04a | README cài đặt/chạy lại, `.env.example` không có bí mật. | D | A (merge PR #11) | Done | [`app/team-4.2/README.md`](../../app/team-4.2/README.md), [`.env.example`](../../app/team-4.2/.env.example) |
| T4.2-W01-04b | 5–10 slides. | Cần điền | Cần điền | In progress | Bản nháp 9 slide; còn sửa kiến trúc (Jina, HyDE trong Dense), biểu đồ slide 8, thêm slide bộ eval dễ/khó và failure case |
| T4.2-W01-04c | Báo cáo tuần + link demo/video. | A | Cần điền | In progress | [report.md](../../reports/week-01/team-4.2/report.md); demo/video chưa có |
| T4.2-W01-05 | Bonus: crawler vbpl.vn, HyDE, rerank Jev, so sánh embedding. | C | A | Done | [`crawl_vbpl.py`](../../scripts/team-4.2/README.md), các thư mục `evals/team-4.2/results/` |

## Daily log

Ghi theo ngày có commit. Các ngày không có commit để nhóm bổ sung (họp, gán nhãn, đọc tài liệu...).

| Ngày | Hoàn thành và bằng chứng | Blocker | Bước tiếp theo / owner |
|---|---|---|---|
| 1 (01/11) | Chốt stack và phân công: [`tech_stack.md`](../../app/team-4.2/docs/tech_stack.md), [`phan_cong_sprint1.md`](../../app/team-4.2/docs/phan_cong_sprint1.md), [plan baseline](../../app/team-4.2/docs/plans/2026-11-01-baseline-rag.md) | — | Code module theo schema chung / cả nhóm |
| 2 | Cần nhóm bổ sung | — | — |
| 3 (03/11) | Merge PR #5 ingestion (B), #7 BM25 + RRF + reranker (A), #9 Dense + eval + HyDE (C), #10 generation + citation (E), #11 schema + pipeline + UI (D). Benchmark 6 Bộ luật 40 câu: Hybrid R@5 0.633, + HyDE + Jev 0.821 | Bộ 6 Bộ luật soạn từ nguyên văn Điều → quá dễ (lookup 1.000 ở mọi cấu hình) | Xây bộ câu đời thường / C |
| 4 (04/11) | Bộ đời thường 64 câu: Hybrid OpenAI chỉ 0.175 (20 câu) → đổi Jina v5, HyDE vào arm Dense, bỏ BM25 → R@5 0.849. Commit `7a182a9` (nhánh `feat/team-4.2/w01-report-eval`): embedding Jina, gộp chunk theo Điều, report tuần 1 | UI/`ask.py` mặc định vẫn chạy Hybrid, chưa khớp cấu hình tốt nhất; chưa chấm tay câu trả lời | Thêm `RETRIEVE_MODE`, sửa `.env.example` / A; chấm tay / E |
| 5 | Cần nhóm bổ sung (slides, demo, nộp bài) | — | — |

Bài nộp: [Team 4.2](../../reports/week-01/team-4.2/README.md).

## Acceptance review and retrospective

- Commit/tag: `7a182a9` trên `feat/team-4.2/w01-report-eval` (chưa merge vào `main`; cập nhật lại sau khi merge và gắn tag).
- Báo cáo và demo: báo cáo đã có ([report.md](../../reports/week-01/team-4.2/report.md)); slides đang sửa; demo/video chưa có.
- Kết luận mentor: chưa đánh giá.
- Điều làm tốt: chia module theo schema chung nên 5 người code song song và merge trong một ngày; mọi số liệu trong báo cáo đều có thư mục kết quả đi kèm; phát hiện bộ eval ban đầu quá dễ nhờ xây thêm bộ câu đời thường.
- Điều cần đổi: không soạn câu hỏi eval trong khi nhìn đáp án; chốt split dev/test trước khi tuning (ngưỡng `CONTEXT_MIN_P`, bỏ BM25 đều chọn trên chính benchmark); có người review khác người viết cho mỗi PR và mỗi bộ nhãn.
- Việc chuyển tuần sau, owner và lý do:
  - Câu `out_of_scope` + tách dev/test / C + B — chưa đo được tỉ lệ từ chối đúng, số hiện tại có thể lạc quan.
  - Query decomposition cho câu multi / A — câu nhiều vế vẫn thiếu Điều (vd. d01).
  - Chấm tay câu trả lời / E — chưa có số về độ đúng và citation.
  - Guardrail 2 tầng, đo latency/chi phí / D — chưa làm trong tuần 1.
