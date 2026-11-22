# Baseline trước giai đoạn 1 rule engine (HEAD 2ec031a, nhánh w03 → w04-rules-engine)

Chạy từ `app/team-4.2/` bằng `.venv/Scripts/python.exe -m pytest`.

## GATE
`tests/test_bridge_*.py tests/test_contract_graph_tools.py tests/test_ask_contract_graph.py tests/test_contract_graph_agent.py tests/test_contracts_api.py`
→ **323 passed, 1 skipped, 1 xfailed**.

## Toàn bộ suite
`pytest -q --ignore=tests/test_agent_partial_review.py` (file này lỗi import `_partition_claims` từ trước)
→ **35 failed, 1755 passed, 22 skipped, 16 xfailed** (≈10 phút). Các test fail nằm ở module không liên quan
(`test_dated_agent_e2e`, `test_warehouse_migration`, `test_pipeline`); danh sách tên đầy đủ: xem mục cuối.

## Golden
`tests/fixtures/rules/golden/engine_results.json`: 2571 ca, 1455 KB, sinh bằng engine cũ chưa sửa.
