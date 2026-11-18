# Agent trên đồ thị hợp đồng: lần chạy thật đầu tiên (2026-11-16)

Spec: `specs/2026-11-16-contract-graph-agent-design.md` · Plan: `plans/2026-11-16-contract-graph-agent.md`
Đầu ra đầy đủ: `contract-graph-agent-run-2026-11-16/` (answer.json có vết từng bước, report.md của bước soát).

Lệnh: `uv run python scripts/ask_contract_graph.py ../../data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt "<câu hỏi>" --trace --out …`
Môi trường: Neo4j **không chạy** (cổng 7687 đóng, Docker tắt) → `backend = memory`, công cụ luật trả
`legal_graph_unavailable`. Agent và các bước soát dùng LLM của app (`gpt-6-luna`); gán khái niệm dùng `CONCEPT_TAG_MODEL`.

## Câu 1: "Lúc thử việc tôi được trả bao nhiêu?"

Trả lời (confidence `answer`, không cảnh báo):
> Trong thời gian thử việc từ ngày 02/01/2025 đến 01/03/2025, bạn được hưởng 85% mức lương căn bản 15.000.000
> đồng/tháng, tức **12.750.000 đồng/tháng**. Phụ lục điều chỉnh lương lên 17.000.000 đồng/tháng có hiệu lực từ
> 01/07/2025, sau thời gian thử việc.

| Bước | Công cụ | Thấy gì |
|---|---|---|
| 1 | `find_concept(probation.pay)` | ConceptInstance gắn Điều 6, câu trích "hưởng 85% mức lương căn bản quy định tại Điều 2" |
| 2 | `expand(Điều 2, [HAS_VALUE, REFERS_TO, AMENDS])` | Điều 6 → Điều 2 (REFERS_TO), Phụ lục 2 → Điều 2 (AMENDS, `valid_from` 2025-07-01), giá trị 15.000.000 |

Đường đi: Điều 6 → Điều 2 → giá trị lương 15.000.000. 2 bước, 3 lời gọi LLM, 15,6 s (bước soát trước đó: 11 lời gọi, 57,5 s).

So với kịch bản slide "Ví dụ": đủ ba ý (dẫn chiếu Điều 6 → Điều 2, sửa đổi của Phụ lục 2 không áp dụng cho thử việc,
con số 12,75 triệu). Thiếu ý thứ tư (BLLĐ 2019 Điều 26) vì không có đồ thị luật và agent không gọi `check_concept`; câu
trả lời không nói đúng/sai luật nên không bị hạ mức.

## Câu 2: "Lương thử việc trong hợp đồng có đúng luật không?"

Trả lời (confidence `answer`): "Có. Hợp đồng quy định lương thử việc bằng 85% mức lương căn bản tại Điều 2; mức này đạt
ngưỡng tối thiểu 85% theo kết quả kiểm tra tại ngày 01/01/2021." Agent đi `find_concept(probation.pay)` →
`check_concept(probation.pay)`, đúng rào chắn "kết luận pháp lý qua bộ kiểm luật".

## Phát hiện

1. **Ngày ký trống trên hợp đồng demo** (có từ trước, không do thay đổi này): `extract_facts` chỉ đặt `sign_date` khi có
   đúng một ứng viên; demo có hai (ngày hợp đồng 02/01/2025 và ngày của phụ lục) → báo cáo "Không có ngày ký: tạm dùng
   giá trị luật từ 2021-01-01", và câu 2 nói "tại ngày 01/01/2021". Kết luận vẫn đúng (ngưỡng 85% không đổi) nhưng
   ngày soát sai; với ngữ nghĩa theo ngày (spec §7) thì ngày soát sai cũng làm chọn sai giá trị có sửa đổi. Cần sửa
   riêng: ưu tiên ứng viên thuộc hợp đồng chính (`p0`) khi các ứng viên khác nằm ở phụ lục.
2. Câu 1 đường đi kết thúc bằng nút `Value` không có nhãn: hiển thị nên lấy `raw` của Value.
3. Chưa chạy được bản Neo4j (cả `Neo4jGraphView` lẫn công cụ luật) trên máy này.

## Chạy lại với Neo4j (cùng ngày, sau khi bật container `docker-neo4j-1`)

- Bộ test `tests/test_contract_graph_view.py` trên Neo4j thật: 21 passed (gồm 9 test bản Neo4j, trước đó bị bỏ qua);
  `tests/test_contracts_neo4j.py`: 3 passed. Hai bản chạy cho cùng láng giềng, đồ thị con, đường đi.
- Đồ thị luật đọc được (build `51cdbb888d7eca95`, snapshot `s20261112174549-ca73d5`); `text_at(BLLĐ 2019 Điều 26, 02/01/2025)` có lời văn.
- "Lúc thử việc tôi được trả bao nhiêu? Mức đó có đúng luật không?" (`neo4j/`): agent dừng sau `find_concept` →
  `check_concept`, không sang Điều 2, trả `partial` và nói rõ chưa có số tiền. Câu trả lời trung thực nhưng chưa đi đủ đường.
- "… bao nhiêu tiền mỗi tháng, có đúng luật không và căn cứ điều luật nào?" (`neo4j-law/`, backend `neo4j`, 6 bước):
  `find_concept` → `expand(Điều 2)` → `find_units(Điều 2)` → `check_concept` → `concept_basis` → `expand(Điều 6, REFERS_TO)`.
  Trả lời `answer`: 12.750.000 đồng/tháng, đạt mức tối thiểu 85% theo Điều 26 BLLĐ 2019; law = `bo-luat:45/2019/QH14#d26`.
  Đủ bốn ý của kịch bản slide.
- Hành vi agent dao động giữa các lần chạy (cùng model `gpt-6-luna`): câu hỏi ngắn có lần không đi sang Điều 2. Đây là
  việc của bước 5 (đo so với truy vấn viết sẵn) và có thể của prompt (bắt buộc đi theo REFERS_TO khi câu trích có "quy định tại Điều N").

## Text2Cypher có rào chắn (spec §5.8) — chạy thật trên Neo4j

Câu "Hợp đồng có bao nhiêu điều khoản, những điều khoản nào bị phụ lục sửa đổi và từ ngày nào?" (`cypher/`):
- Lần đầu (trước khi sửa luật neo): agent bị từ chối 2 lần — ghi cứng contract_id; rồi `OPTIONAL MATCH (main)…` với
  `main` neo gián tiếp (bị chặn nhầm) — lần 3 chạy được: "7 Điều trong hợp đồng chính; Phụ lục 2 sửa Điều 2 từ 01/07/2025".
  Vòng tự sửa (lỗi trả về agent kèm lý do) hoạt động như LAST-CQ mô tả.
- Sau khi sửa luật neo (theo dõi biến đã neo qua MATCH / WITH) và tính mã nút trong dòng Cypher là "đã thấy": 1 bước,
  confidence `answer`, không cảnh báo, đường đi Phụ lục 2 — Mục 1 → Điều 2. Agent đếm 22 đơn vị (cả hai phụ lục) và nói
  rõ cách đếm; lần trước đếm 7 (chỉ hợp đồng chính) — câu hỏi mơ hồ, mỗi lần hiểu một kiểu.
