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

## Việc để lại cho các kế hoạch sau (từ các lượt review)

- Task 1: minor (deferred): bare "đ" currency (30.000.000đ) and "tỉ" variant not recognised
- Task 1: minor (deferred): [.\s] / \s* cross newlines; prefer [ \t]
- Task 1: minor (deferred): more regression tests (decimal percent, USD, no match)
- Task 1: minor (deferred): space-grouped number ambiguous with preceding integer ("cọc 5 100 000 đồng" -> 5100000) — inherent
- Task 2: minor (deferred): uppercase body line "PHỤ LỤC kèm theo gồm 02 trang" accepted as appendix part (number=2)
- Task 2: minor (deferred): "PHỤ LỤC HỢP ĐỒNG SỐ 01/2024" number=1 taken from contract number
- Task 2: minor (deferred): TOC rule only covers first entry after MỤC LỤC; page_at rebuilds offsets per call; thin tests (blank-before rule, DANH MỤC, \r\n)
- Task 3: minor (deferred): dotted clause regex optional trailing dot — body line "2.5 lần giá thuê" under Điều 2 becomes k5 with false gap
- Task 3: minor (deferred): first point letter may be "d" (step 4 from start)
- Task 4: minor (deferred): duplicate _EXTERNAL_RE match / redundant guard; no word boundary at match start
- Task 4: minor (deferred): list forms "khoản 1, 2 Điều 5" also add an extra article-level edge to p0.d5
- Task 4: minor (deferred): "điểm a, b khoản 1" lists not handled; bare-number raws ("2") in lists
- Task 5: minor (deferred): no tests for appendix title-only preamble drop / appendix intro kept; CRLF/NFC path via assemble not probed
- Task 6: minor (deferred): set_review no status validation; supersede of already-rejected op overwrites first rejection's reviewer/note; from_json drops duplicate ids silently; no contract_id consistency check; thin tests (KeyError, layout, reviewed_at round-trip)
- Task 6: minor (deferred): import pytest inside test function
- Task 7: minor (deferred): edges with missing endpoint uid skipped silently (not recorded as problem); norm keys could overwrite contract_id/build_id; no tests for overlap rule/unknown edge/unresolved_refs
- Task 8: minor (deferred): edges with missing endpoints dropped silently by MATCH; integration test asserts nodes only (add edge count); no fake-driver test for GraphUnavailable mapping / allowlist ValueError; run(**params) name collision; driver ctor (bad URI) raises ConfigurationError outside _guard
- Task 9: minor (deferred): no test that lock is released when with-body raises; unexpected-error test doesn't assert published empty / log noise
- Task 10: minor (deferred): corrupted format-2 file raises non-KeyError (contained by listed() fix only); _unconvertible remembered until restart; converted facts/old reports keep old u* uids; no test for GraphBusy on party/sign-date
- Task 10: minor (deferred): partial review (unit_ids / topics via by_label) not capped at 30; disk/Neo4j may hold newer build if store.update fails after publish; run() report save outside lock (pre-existing)
- Parked: PARSER_VERSION bump — saved contracts re-parse doc on load but keep old graph status/build_id until next change; Neo4j may hold a v1 build until then — Ruling: branch unreleased; no saved real contracts yet; clear dev data / rebuild on next change — if wrong, an old v1 build (possibly with unmasked Value nodes) stays in a local Neo4j until the contract is touched.
- Parked: _new_report reads build_id after the LLM call (race with a concurrent layout change) — Ruling: defer to plan 2 (capture build_id at review start) — rare, single-user demo.
