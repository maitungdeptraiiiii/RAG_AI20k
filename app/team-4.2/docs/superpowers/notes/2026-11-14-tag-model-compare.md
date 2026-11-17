# So model cho bước gán khái niệm (hợp đồng demo)

Ngày: 2026-11-14. Hợp đồng `data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.pdf`, nhãn
`tests/fixtures/bridge/demo_gold.yaml`, danh mục `0.2-draft`, prompt `concept-tag-2` (đã sửa slot lạ + `not_about`).
Chỉ đổi model ở bước gán khái niệm; trích dữ kiện và kiểm lại giữ `gpt-6-luna`. Một lần chạy mỗi model, không cache.

```
uv run python scripts/check_contract_concepts.py <hợp đồng> <out> --tag-model <id OpenRouter> [--tag-temp 0]
uv run python scripts/score_concept_check.py <out> tests/fixtures/bridge/demo_gold.yaml
```

| Model | Giá vào / ra (USD / 1 triệu token) | temperature | P / R khái niệm | Slot | Thời gian cả lần soát |
|---|---|---|---|---|---|
| gpt-6-luna (app) | 0,10 / 0,50 | không | 1,0 / 1,0 | 4/5: phép năm ra 1 ngày (đúng 12) | 54 s |
| anthropic/claude-haiku-5.5 | 0,10 / 0,50 | không | 1,0 / 1,0 | 5/5 | 37 s |
| anthropic/claude-sonnet-5.5 | 2 / 10 | không | 1,0 / 1,0 | 5/5 | 18 s |
| deepseek/deepseek-v4.1-flash | 0,05 / 0,20 | có (0) | 1,0 / 1,0 | 5/5; 1 item quote sai bị loại | 188 s |
| google/gemini-3.8-flash | 0,83 / 4,12 | có (0) | 1,0 / 1,0 | 4/5 (bảo hiểm để trống) | 36 s |
| openai/gpt-6.1-terra | 1 / 5 | không | 1,0 / 1,0 | 4/5 (bảo hiểm để trống) | 37 s |
| qwen/qwen3.8-flash | 0,15 / 0,47 | có (0) | 1,0 / 1,0 | 4/5 (bảo hiểm để trống) | 491 s |

- Sau khi sửa lỗi 1 (slot lạ) và lỗi 2 (`not_about`), mọi model đều gán khái niệm đúng 18/18.
- "Bảo hiểm để trống": hợp đồng ghi "theo quy định của pháp luật"; để trống có lý (lỗi 3, chưa sửa).
- Chọn **Claude Haiku 5.5** làm mặc định (`CONCEPT_TAG_MODEL`, `rag.bridge.llm`): cùng giá gpt-6-luna, slot 5/5.
- Hạn chế: một hợp đồng, một lần chạy, model không nhận temperature nên mỗi lần có thể khác. Cần bộ 5–10 hợp đồng
  có nhãn và chạy lặp trước khi coi là kết luận.
- Hợp đồng demo (PII giả) được gửi qua OpenRouter tới các nhà cung cấp trên. Hợp đồng thật: phải che tên người trước.
