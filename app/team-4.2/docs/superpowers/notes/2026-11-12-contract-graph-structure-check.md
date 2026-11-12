# Kiểm tra lớp cấu trúc đồ thị hợp đồng (kế hoạch 1)

- Ngày: 2026-11-12
- Commit kiểm tra: 34b598a (nhánh feat/team-4.2/w02-merge-integration)
- Phạm vi: Docker không chạy trên máy này, nên không bật Neo4j, không chạy server. Phần chạy được đã kiểm bằng kịch bản dùng `ui/contracts_api.py` với FakeStore (giống `tests/test_contracts_graph_api.py`). Phần cần Docker liệt kê ở cuối.

## 1. Bộ kiểm thử

| Lệnh | Kết quả |
|---|---|
| `uv run --extra dev pytest tests -q` | 2 failed, 1223 passed, 2 skipped (730 giây) |
| `uv run --extra dev pytest tests -q -k contracts` | 132 passed, 1 skipped, 1094 deselected (đúng kỳ vọng) |

Hai test lỗi, đều không thuộc hợp đồng (file test không đổi so với e91c4c8, không có commit nào của kế hoạch này chạm `src/rag/legal`):

1. `tests/test_legal_upload_api.py::test_first_runtime_is_bm25_then_same_snapshot_dense_upgrade` — khẳng định thời gian `time.monotonic() - start < 5`, đo được 9,8 giây khi chạy riêng (kiểm tra độ trễ, phụ thuộc tải máy). Chạy lại riêng vẫn lỗi trên máy này; cần chạy lại khi máy rảnh hoặc xác nhận trên e91c4c8.
2. `tests/test_pipeline.py::test_settings_load_does_not_override_existing_env` — lỗi khi chạy cả bộ (`arm_k=9`, `max_syllables=300` lấy từ môi trường), nhưng chạy riêng thì pass: nhiễm biến môi trường giữa các test, phụ thuộc thứ tự.

## 2. Kịch bản đầu cuối (không Neo4j)

Script tạm ngoài repo: `scratchpad/e2e.py`; chạy bằng `uv run --quiet python -I`. Tất cả 8 kiểm tra đạt.

a. Hợp đồng demo `hop_dong_thue_nha_2023.docx`: PASS.
   - 13 đơn vị (Phần mở đầu + 12 Điều); counts: article 12, clause 13, point 0; gaps `[]`, warnings `[]`.
   - Đồ thị đã publish 1 lần (FakeStore): 40 nút, 60 cạnh; `problems == []`.

b. Hợp đồng tự soạn 45 Điều + 2 phụ lục + CCCD giả `001203004567` ở phần mở đầu (.txt):
   - Đơn vị: 49 (preamble + 45 + 3 Điều phụ lục); counts: article 48, clause 18, point 18; gaps `[]`. PASS.
   - parts: main, "PHỤ LỤC 01" (appendix), "PHỤ LỤC 02" (appendix) = 2 phụ lục. PASS.
   - coverage `{"reviewed": 30, "total": 49}`. PASS.
   - Bản dựng: 110 nút (Unit 85, Value 21, Part 3, Contract 1), cạnh: HAS_UNIT 85, CHILD_OF 36, HAS_VALUE 21, REFERS_TO 9, HAS_PART 3.
   - Nút chứa `001203004567`: 0. PASS. REFERS_TO = 9 (>0). PASS. node_id 110/110 duy nhất. PASS. problems `[]`.

c. Đổi ngày ký (Lan, 2023-04-01): build_id `bda3f7cc31e7` -> `b7583ab5398e`, `len(builds) == 2`. PASS.
   FakeStore lỗi rồi đổi ngày ký lần nữa (2023-05-01): graph `{published: False, error: "Không kết nối được Neo4j"}`, ngày ký vẫn cập nhật, `chat_answer` trả "Theo Điều 1." (hợp đồng vẫn hỏi được). PASS.

Lưu ý: yêu cầu ghi "48 đơn vị gốc"; thực tế card có 49 đơn vị (48 Điều + Phần mở đầu), nhất quán với mô tả "kèm phần mở đầu".

## 3. Cần chạy trên máy có Docker

- [ ] Mở Docker Desktop, chờ daemon sẵn sàng (`docker info`).
- [ ] Đặt mật khẩu: `$env:NEO4J_PASSWORD = "<mật khẩu>"` (PowerShell).
- [ ] Từ `app/team-4.2`: `docker compose -f docker/neo4j-compose.yml up -d`.
- [ ] Chạy kiểm thử Neo4j thật (kỳ vọng 2 passed):
  `$env:NEO4J_TEST_URI = "bolt://localhost:7687"; $env:NEO4J_TEST_PASSWORD = $env:NEO4J_PASSWORD; uv run --extra dev --extra graph pytest tests/test_contracts_neo4j.py -q`
- [ ] Bật đồ thị và chạy server theo README: `$env:CONTRACT_GRAPH = "1"` rồi lệnh chạy server trong README.
- [ ] Nạp `data/team-4.2/contracts_demo/hop_dong_thue_nha_2023.docx` qua giao diện: thẻ có 12 Điều, không cảnh báo đứt số, đồ thị đã publish.
- [ ] Trong Neo4j Browser (`http://localhost:7474`), với `:param id => "<contract_id>"`:
  - `MATCH (n:CGNode {contract_id:$id}) RETURN labels(n)[1] AS l, count(*)` (kỳ vọng như kịch bản a: tổng 40 nút).
  - `MATCH (:CGNode {contract_id:$id})-[e]->() RETURN type(e), count(*)` (kỳ vọng tổng 60 cạnh).
  - Soát `text` không còn CCCD / số điện thoại gốc.
- [ ] Nạp hợp đồng ≥ 40 Điều có 2 phụ lục (tự soạn như kịch bản b): thẻ báo đủ Điều và "2 phụ lục"; soát toàn bộ báo `30/49`.
- [ ] Tắt Docker (`docker compose -f docker/neo4j-compose.yml stop`), sửa ngày ký: thẻ hiện "Đồ thị chưa cập nhật", hợp đồng vẫn hỏi được.
- [ ] Chụp ảnh đồ thị (nếu có) và đính vào file này.
