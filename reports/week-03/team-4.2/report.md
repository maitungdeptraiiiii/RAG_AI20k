# Báo cáo tuần 3 — Team 4.2

## Scope and version

- **Team:** 4.2 — chuyển trọng tâm từ hỏi đáp luật chung sang **soát hợp đồng lao động (HĐLĐ) bằng đồ thị hợp đồng + đồ thị luật**.
- **Thành viên và đóng góp** (vai trò theo `app/team-4.2/docs/phan_cong_w03_hop_dong_luat.md`; vai trò mang tính danh nghĩa, **cần team xác nhận phần đã làm**):

| Ký hiệu | Họ tên | Vai trò tuần 3 |
|---|---|---|
| A | Mai Phan Anh Tùng | HĐ (dữ kiện + đồ thị hợp đồng, tích hợp) và EV (gold set, harness, ablation) |
| C | Lương Quang Huy | LU: đồ thị luật (cấu trúc, dẫn chiếu, hướng dẫn, phiên bản theo ngày), Legal Graph HĐLĐ |
| E | Nguyễn Anh Tú | CN: danh mục khái niệm, gán điều khoản → khái niệm → điều luật |
| D | Nguyễn Quốc Tuấn | RU: rule ngưỡng, ứng viên xung đột, quyền ↔ nghĩa vụ, báo cáo soát |
| B | Nguyễn Gia Khánh | TR: nhánh hybrid clause → luật (baseline), router và guardrail |

- **Phương pháp chuyên sâu (chọn theo lỗi tuần 2):** quan hệ → **graph**. Hypothesis đặt trước khi code: mỗi điều khoản hợp đồng cần được nối với điều luật *đúng phiên bản tại ngày ký* và với điều khoản khác trong hợp đồng (dẫn chiếu, phụ lục sửa đổi); chunk-level hybrid không làm được hai việc này. Hybrid RAG (BM25 + Dense + RRF) giữ làm baseline.
- **Đã hoàn thành:**
  - **Đồ thị luật** (Neo4j): 114 văn bản, 56.792 điều khoản, 72.088 phiên bản điều khoản, 39 phụ lục; truy vấn theo ngày (`text_at`, `applicable`, `guidance`, `changes`, `appendices`).
  - **Đồ thị hợp đồng**: cây điều khoản → dữ kiện (lương, thử việc, thời hạn, phép, vùng…) → nút/cạnh dẫn chiếu, phụ lục sửa đổi (`AMENDS`).
  - **Lớp cầu nối**: danh mục 39 khái niệm (`0.2-draft`), gán điều khoản → khái niệm → điều luật, rule engine ngưỡng, báo cáo soát có trích dẫn.
  - **Agent hỏi đáp trên đồ thị hợp đồng** (công cụ `find_concept`, `expand`, `check_concept`, `cypher_query`, có hậu kiểm).
  - Contract Studio: trang demo, SSE streaming, hai đồ thị song song, report canvas, Think chat.
  - Corpus luật lao động: 69 tài liệu chốt cho profile HĐLĐ (43 có sẵn + 26 bổ sung), gói bundle có manifest.
- **Chưa hoàn thành:**
  - **Chưa có ablation Hybrid vs Hybrid + graph trên ≥40 câu cùng điều kiện** (yêu cầu của tuần); chưa có latency/chi phí theo loại câu hỏi.
  - Đồ thị luật chưa có phiên bản sửa đổi cho Luật BHXH 41/2024; danh mục địa bàn vùng lương NĐ 74/2024, NĐ 293/2025 không có trong nội dung vbpl.
  - Router và guardrail cho chat luật thường; bộ hợp đồng có nhãn 5–10 hợp đồng.
- **Commit / snapshot / cấu hình:**
  - Nhánh `feat/team-4.2/w03-labor-contract-kg-v2`, HEAD `2ec031a`.
  - Legal Graph: snapshot `s20261117024643-c06f0c`, build `12622da3d53bc9ed`, Neo4j 5.26 (Docker `rag-legal-graph-dev`, `bolt://127.0.0.1:17687`). Hợp đồng demo: `data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.pdf` (PII giả).
  - Model: gán khái niệm `anthropic/claude-haiku-5.5` (`CONCEPT_TAG_MODEL`); trích dữ kiện, kiểm lại, agent `gpt-6-luna`; embedding Jina v5; rerank Jev.
- **Chạy lại:**

  ```bash
  cd app/team-4.2
  uv run python scripts/check_contract_concepts.py ../../data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.pdf <out>
  uv run python scripts/score_concept_check.py <out> tests/fixtures/bridge/demo_gold.yaml
  uv run python scripts/ask_contract_graph.py ../../data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt "<câu hỏi>" --trace --out <out>
  python scripts/team-4.2/eval_legal_graph.py --publish    # cần Neo4j, xem legal_graph_labor_v1.README.md
  ```

  Demo/video và slides: chưa có.

## Design decisions

### Bảng ánh xạ loại câu hỏi → phương pháp → bằng chứng

| Loại câu hỏi | Ví dụ | Phương pháp | Bằng chứng trả về |
|---|---|---|---|
| Trực tiếp | "Lúc thử việc tôi được trả bao nhiêu?" | `find_concept` → `expand` trên đồ thị hợp đồng | Câu trích + nút `Value` + đường đi Điều 6 → Điều 2 |
| Metadata / thời điểm | "Điều 25 BLLĐ tại 01/03/2025 quy định gì?" | Đồ thị luật `text_at`, `applicable` (phiên bản theo ngày) | `pid` + phiên bản + ngày hiệu lực + nguồn |
| Tính toán / ngưỡng | "Lương thử việc có đạt 85% không?" | Rule engine trên dữ kiện hợp đồng + giá trị luật tại ngày ký | Dữ kiện nguồn, ngưỡng, điều luật, kết luận |
| Nhiều bước / quan hệ | Điều khoản dẫn chiếu, phụ lục sửa đổi lương | Duyệt cạnh `REFERS_TO`, `AMENDS`, `GUIDES` | Đường đi cạnh, `valid_from` của phụ lục |
| Không đủ dữ liệu | Thiếu ngày ký, vùng lương | Trả `cannot_conclude` / "cần thêm dữ kiện" | Danh sách dữ kiện thiếu |

### Quyết định

| Bài toán | Lựa chọn | Phương án đã cân nhắc | Trade-off |
|---|---|---|---|
| Nối hợp đồng với luật | Hai đồ thị riêng, cạnh nối lưu bên hợp đồng, tham chiếu luật bằng `pid` | Một đồ thị chung | Không cạnh vật lý chéo DB; truy vấn hai bước nhưng luật dùng lại cho nhiều hợp đồng |
| Gán điều khoản → khái niệm | Danh mục khái niệm có slot + LLM gán, kiểm lại khái niệm vắng mặt | Regex/từ khoá; hybrid clause → luật thuần | Tổng quát hơn từ khoá nhưng phụ thuộc LLM |
| Mâu thuẫn | LLM chỉ đề xuất, trạng thái `candidate`, người duyệt | Tự kết luận | Chậm hơn; không có kết luận pháp lý do LLM tự tạo |
| Model gán khái niệm | Claude Haiku 5.5 (0,10 / 0,50 USD mỗi triệu token) | gpt-6-luna, Sonnet 5.5, DeepSeek, Gemini, Qwen | Cùng giá gpt-6-luna nhưng slot 5/5; chỉ đo trên 1 hợp đồng, 1 lần |
| Ngôn ngữ ngày | Tính theo ngày ký; mỗi `ProvisionVersion` có khoảng hiệu lực | Dùng phiên bản hiện hành | Cần ngày ký đúng; khi sai, chọn sai giá trị luật |
| Phụ lục luật chưa duyệt | Giữ trạng thái `needs_review`, không coi retrieval pass là phê duyệt | Tự duyệt | Báo cáo kèm cảnh báo; an toàn pháp lý hơn |

## Evaluation

**Dataset.** Mọi số dưới đây đo trên bộ nhỏ, chưa đạt yêu cầu "≥40 câu tổng" cho so sánh baseline/graph:

- Legal Graph: `legal_graph_labor_v1.jsonl`, 28 ca soạn tay (độc lập với đầu ra hệ thống), gồm phiên bản/ranh giới ngày, dẫn chiếu, phạm vi hướng dẫn, phụ lục.
- Concept check: 1 hợp đồng demo, 18 khái niệm có mặt, 3 khái niệm mơ hồ không tính (`demo_gold.yaml`); nhãn do người lập kế hoạch gán, chưa rà lại.
- Agent: 4 câu × 5 lần chạy, trước/sau khi sửa đường đi.
- Trích dữ kiện: CUAD v1, 30 hợp đồng tiếng Anh (hạt giống 20261113).

| Cấu hình | Nhóm / số câu | Recall@5 | MRR@5 | Độ đúng/citation | Latency | Chi phí |
|---|---|---|---|---|---|---|
| BM25 / Dense / Hybrid RRF (baseline) | HĐLĐ | N/A | N/A | N/A | N/A | N/A |
| Hybrid + graph | HĐLĐ | N/A | N/A | N/A | N/A | N/A |
| Legal Graph API (Neo4j thật) | Cấu trúc + thời gian / 28 | N/A (không chấm chunk) | N/A | 28/28 ca đạt | p50 ≈ 16,6 ms, p95 ≈ 199,2 ms | 0 (không LLM) |
| Gán khái niệm (Haiku 5.5) | Hợp đồng demo / 18 khái niệm | N/A | N/A | P 1,0 / R 1,0; slot 5/5 | 37 s cả lần soát | ≈ giá gpt-6-luna |
| Gán khái niệm (gpt-6-luna, lần đầu) | Hợp đồng demo / 18 | N/A | N/A | P 0,944 / R 0,944 (17/18); slot 4/5; 0 báo nhầm "không nhắc tới" | 55,6 s; 11 lời gọi LLM | N/A |
| Agent, before | Hợp đồng demo / 4 câu × 5 | N/A | N/A | đúng 18/20; `answer` 10/20 | bước TB 1,4–3,4 | N/A |
| Agent, after | Hợp đồng demo / 4 câu × 5 | N/A | N/A | đúng 17/20; `answer` 18/20 | bước TB 1,0–2,4 | N/A |
| Trích các bên (gpt-6-luna) | CUAD / 30 hợp đồng | N/A | N/A | P 0,953 / R 0,783 / F1 0,860 | 834 s cộng dồn (4 luồng) | 137 lời gọi LLM |

Nguồn: [`legal-graph-labor-v1`](../../../evals/team-4.2/results/legal-graph-labor-v1/README.md), [`tag-model-compare`](../../../app/team-4.2/docs/superpowers/notes/2026-11-14-tag-model-compare.md), [`concept-check-first-run`](../../../app/team-4.2/docs/superpowers/notes/2026-11-14-concept-check-first-run.md), [`contract-agent-bench-2026-11-16`](../../../app/team-4.2/docs/superpowers/notes/contract-agent-bench-2026-11-16/summary.md), [`cuad-facts-benchmark`](../../../app/team-4.2/docs/superpowers/notes/2026-11-13-cuad-facts-benchmark.md).

**Đồ thị luật, kiểm tra snapshot trước đó** (`s20261112174549-ca73d5`, 92 văn bản): 9.784 dẫn chiếu được phân tích, **92,3% đích giải được** (14.187 / 15.375), 814 `provision_not_found`, 374 `doc_not_in_store`.

Điều kiện: một hợp đồng demo, Neo4j local, một lần chạy; latency là đo local một luồng, không phải tải đồng thời.

## Failure analysis

| Case | Kỳ vọng / thực tế | Bằng chứng | Bước gây lỗi | Cách sửa / kết quả chạy lại |
|---|---|---|---|---|
| Ngày ký trống trên hợp đồng demo | Ngày ký 02/01/2025; thực tế `sign_date` trống, báo cáo dùng 01/01/2021 | `contract-graph-agent-first-run`, phát hiện 1 | Trích dữ kiện: chỉ đặt `sign_date` khi có đúng 1 ứng viên, demo có 2 (hợp đồng + phụ lục) | Chưa sửa; đề xuất ưu tiên ứng viên ở hợp đồng chính. Kết luận ngưỡng 85% vẫn đúng nhưng ngày soát sai |
| Thử việc bị loại do slot bịa | Giữ khái niệm thử việc; LLM trả `probation.duration` cho khái niệm không có slot, item bị loại `unknown_slot` | `concept-check-first-run`, lỗi 1 | Gán khái niệm (prompt) | Bỏ slot lạ, giữ khái niệm, ghi `tag_rejected` (prompt `concept-tag-2`); sau sửa mọi model gán 18/18 |
| Gán nhầm chấm dứt thay vì đào tạo | Câu "hoàn trả 100% phí đào tạo" chỉ thuộc `training.cost_repayment`; bị gán thêm `termination.employee_unilateral` | `concept-check-first-run`, lỗi 2 | Gán khái niệm | Thêm `not_about`/ví dụ âm cho khái niệm chấm dứt; sau sửa 18/18 ở cả 7 model |
| Agent Q3 kết luận thiếu | Phải đọc đủ phụ lục; Q3 #0 chỉ `expand` Phụ lục 1, kết luận "chưa đủ dữ liệu" | `contract-agent-bench`, "After Q3 #0 sai thật" | Agent: không gọi `find_units`/`cypher_query` | Chưa sửa; kết quả vẫn trung thực (`partial`). Q3: 5/5 → 4/5 |
| Q4 mơ hồ về thời điểm | "Lương căn bản của tôi?" trả 17 triệu từ 01/07/2025, thiếu mức 15 triệu ban đầu | `contract-agent-bench` | Đánh giá: tiêu chí chấm quá chặt | Chấm lại "có 17 triệu kèm ngày 01/07/2025" → 5/5 ở cả hai cấu hình |
| Danh sách các bên lặp | Mỗi bên một mục; thực tế 88/166 mục (53%) trùng tên ở hợp đồng nhiều lô | `cuad-facts-benchmark`, phát hiện 1 | Trích dữ kiện: gộp chỉ loại trùng theo chuỗi vai trò | Đã ghi nhận; F1 không bắt được lỗi này vì mục lặp vẫn khớp đáp án |
| Danh mục địa bàn vùng lương | Dùng được để biết vùng của hợp đồng; NĐ 74/2024, NĐ 293/2025 không có danh mục trong nội dung vbpl | `legal-corpus-graph-check`, mục "Không đạt" | Ingest nguồn: raw text vbpl thiếu | Chưa sửa; cần nguồn khác hoặc nhập tay có nhãn nguồn |
| Số hiệu trong Điều 29 Luật Dân số 113/2025/QH15 | Số hiệu luật nhất quán trong một điều; thực tế không nhất quán cả ở HTML công khai và PDF Công báo | `legal-graph-labor-v1/README.md` | Nguồn gốc | Giữ nguyên, gắn cờ khi hợp nhất; cần người có chuyên môn pháp lý quyết định |

## Findings and limitations

**Được dữ liệu hỗ trợ**

- Đồ thị luật trả đúng phiên bản theo ngày và quan hệ hướng dẫn: 28/28 ca soạn tay đạt, p95 ≈ 199 ms trên Neo4j local.
- Gán khái niệm đúng 18/18 ở 7 model sau khi sửa slot lạ và `not_about`; model rẻ nhất vẫn đạt, nên chọn theo slot đúng và giá, không theo độ lớn.
- Sửa đường đi của agent không đổi độ đúng đáng kể (18/20 → 17/20, mẫu quá nhỏ) nhưng tăng câu qua hậu kiểm `answer` 10/20 → 18/20 và giảm số bước (Q1 3,2 → 1,8).

**Không được hỗ trợ / chưa kiểm chứng**

- **Giả thuyết "graph tốt hơn hybrid chunk" chưa được kiểm**: chưa có ablation BM25 / Dense / Hybrid / Hybrid + graph trên cùng bộ câu và cùng generation. Không nên coi 28/28 hay P/R 1,0 là bằng chứng graph vượt baseline.
- Tuần 2 đã khuyến nghị đo độ đúng/citation, latency, chi phí; các cột này vẫn N/A cho so sánh baseline.
- Chưa đo việc router/guardrail.

**Giới hạn**

- **Một hợp đồng demo, một lần chạy**; nhãn do người lập kế hoạch gán, chưa rà lại; PII giả. Model không nhận temperature nên mỗi lần chạy có thể khác.
- 28 ca Legal Graph không đo độ phủ pháp lý đầy đủ và không đo precision/recall dẫn chiếu; báo cáo còn dẫn chiếu chưa giải được; 6 kết quả `needs_review`.
- Phụ lục đã trích vẫn `needs_review`; chưa có chuyên gia pháp lý duyệt.
- Trích dữ kiện đo trên hợp đồng tiếng Anh (CUAD), không phải HĐLĐ tiếng Việt; recall các bên bị đánh giá thấp do nhiễu đáp án.
- Hợp đồng demo gửi qua OpenRouter tới nhiều nhà cung cấp; hợp đồng thật cần che tên người trước.
- Chưa chạy toàn bộ legal test suite (một lần chạy rộng bị treo và dừng); chỉ 125 test nhắm mục tiêu và 8 test tích hợp Neo4j đạt.

**Hành động tiếp theo**

| Việc | Owner |
|---|---|
| Dựng bộ ≥40 câu HĐLĐ có gold, đủ 5 loại câu; chạy BM25 / Dense / Hybrid / Hybrid + graph cùng snapshot, đo latency và chi phí theo loại | A — Mai Phan Anh Tùng |
| Sửa lỗi ngày ký (ưu tiên ứng viên ở hợp đồng chính) | A — Mai Phan Anh Tùng |
| Bộ 5–10 hợp đồng có nhãn, chạy lặp, rà lại nhãn bằng người thứ hai | E — Nguyễn Anh Tú |
| Bổ sung phiên bản sửa đổi Luật BHXH 41/2024; nguồn danh mục vùng lương | C — Lương Quang Huy |
| Router và guardrail cho chat luật thường | B — Nguyễn Gia Khánh |
| Quay demo, làm slides, cập nhật tracker | D — Nguyễn Quốc Tuấn |
