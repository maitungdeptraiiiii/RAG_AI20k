# Soát theo danh mục khái niệm: lần chạy đầu trên hợp đồng demo

Ngày: 2026-11-14. Spec: `specs/2026-11-14-contract-concept-check-design.md`. Kế hoạch: `plans/2026-11-14-contract-concept-check.md`.

## Cách chạy

```
uv run python scripts/check_contract_concepts.py ../../data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.pdf <out>
uv run python scripts/score_concept_check.py <out> tests/fixtures/bridge/demo_gold.yaml
```

- Model: model LLM cấu hình trong `.env` của app (cùng model với lần chạy thật 14/11).
- Danh mục `0.2-draft` (39 khái niệm). Neo4j tắt: đồ thị dựng được nhưng không công bố; báo cáo không có lời văn luật
  (`basis_unavailable`), chỉ có neo.
- Nhãn tay: `tests/fixtures/bridge/demo_gold.yaml` (18 khái niệm có mặt, 3 khái niệm mơ hồ không tính). Nhãn do
  người lập kế hoạch gán, A cần rà lại.

## Số đo

| Chỉ số | Kết quả |
|---|---|
| Precision gán khái niệm | 0,944 (17/18) |
| Recall gán khái niệm | 0,944 (17/18) |
| Độ đúng slot | 4/5 |
| **Báo nhầm "không được nhắc tới"** (quyền ẩn / thiếu nội dung cho khái niệm có trong hợp đồng) | **0** |
| Lời gọi LLM | 11 (1 dữ kiện + 1 gán khái niệm theo lô… + 9 kiểm lại) |
| Thời gian | 55,6 giây |
| Khái niệm được kiểm lại | 9; 8 xác nhận vắng mặt, 1 tìm thấy |

Không đặt ngưỡng; đây là mốc đầu để so các lần sau.

## Kết quả báo cáo, tóm tắt

- **Thiếu nội dung bắt buộc (1):** trang bị bảo hộ lao động. Đúng theo nhãn (khái niệm này để "mơ hồ": hợp đồng chỉ
  nói cấp phát thiết bị, công cụ).
- **Quyền hợp đồng không nhắc (7):** tiền làm thêm giờ, tiền làm đêm, nghỉ việc riêng, trợ cấp thôi việc, thời hạn
  thanh toán khi chấm dứt, hủy thử việc không cần báo trước, không bị sa thải vì kết hôn / mang thai. Đều đúng là hợp
  đồng không ghi.
- **Mâu thuẫn (1):** lương 15 triệu (hợp đồng chính) và 17 triệu (Phụ lục 2). Đây là sửa đổi theo phụ lục, chưa xử lý
  (`AMEND_UNIT`, mục "để sau" của spec).
- **Có thể có quyền (6):** toàn bộ nhóm P1 thai sản, vì chưa hỏi người dùng.
- **Cần thêm dữ kiện (9):** phép năm 12 ngày (chưa biết loại công việc), thời gian thử việc (chưa biết trình độ công
  việc), lương tối thiểu (chưa biết vùng), và một số rule cấm (xem lỗi 3).

## Lỗi đáng chú ý

1. **Thử việc bị loại vì slot bịa.** LLM trả `slots: {"probation.duration": "02 tháng"}` cho khái niệm không có slot,
   item bị loại `unknown_slot`. Sửa đề xuất: bỏ slot lạ, giữ khái niệm (ghi slot bị bỏ vào `tag_rejected`). Engine vẫn
   xét thử việc qua dữ kiện cấp hợp đồng nên báo cáo không mất.
2. **Gán nhầm `termination.employee_unilateral`** cho câu "không tiếp tục hợp tác ... phải hoàn trả 100% phí đào tạo".
   Câu này thuộc `training.cost_repayment` (cũng được gán đúng). Sửa đề xuất: thêm `traps` / ví dụ âm cho khái niệm
   chấm dứt.
3. **Rule cấm kiểu bool ra "cần thêm dữ kiện" khi điều khoản không nói tới hành vi cấm** (bảo hiểm "theo quy định của
   pháp luật", NSDLĐ chấm dứt "theo quy định của pháp luật", hoàn trả phí đào tạo không nói có hợp đồng đào tạo riêng).
   LLM đúng khi không điền slot. Sửa đề xuất: với `mode: prohibited`, khái niệm có mặt mà slot cấm không được điền thì
   coi là không có hành vi cấm (`PASS`), trừ `training.cost_repayment` nên đổi thành câu hỏi cho người dùng.
4. **Dữ kiện `job_level` không được trích** dù Điều 1 ghi "Nhân viên kế toán tổng hợp". Đây là việc của `facts.py`
   (chọn 1 trong 4 trình độ từ chức danh); có thể hỏi người dùng.
5. **Báo cáo hiển thị "Thiếu dữ kiện: <slot>" cho quyền ẩn** (hợp đồng im lặng thì đương nhiên không có slot). Chỉ là
   cách trình bày.
6. **Che PII:** tên người vẫn đi vào payload LLM (lỗi đã biết, theo spec che PII; test `test_payload_masks_person_names`
   đang `xfail`). CCCD, số điện thoại đã được che.

## Đề xuất sửa `describe` / `phrasing`

- `termination.employee_unilateral`: thêm vào `describe` "Không gồm điều khoản hoàn trả phí đào tạo khi nghỉ việc".
- `content.protective_equipment`: thêm "không gồm thiết bị, công cụ làm việc thông thường".
- Thêm `traps` vào danh mục (đã nằm trong mục "để sau" của spec) để chứa các câu dễ gán nhầm như trên.
