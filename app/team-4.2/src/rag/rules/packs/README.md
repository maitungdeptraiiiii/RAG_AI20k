# Thêm một loại hợp đồng mới (gói luật)

Một loại hợp đồng = một thư mục `packs/<id>/` gồm `pack.yaml` + `concepts.yaml`. **Không sửa file code nào.**
Test mẫu chứng minh điều này: `tests/test_pack_plugin.py` (gói giả `thue_thu` chạy qua toàn bộ `check_contract`).
Thiết kế: `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md` §5.5 (bản 3).

## `pack.yaml`

| Khóa | Dùng để | Ví dụ |
|---|---|---|
| `id`, `version`, `extends` | tên gói, gói cha (thừa kế đơn vị, dữ kiện, rule) | `extends: [civil_general]` |
| `document_kinds`, `document_labels` | loại văn bản gói soát (chọn gói theo loại: `packs_for_kind`); tên loại đưa vào prompt | `document_labels: {lease_contract: "hợp đồng thuê nhà ở"}` |
| `units`, `conversions` | đơn vị và quy đổi về đơn vị gốc | `percent_per_month: {base: percent_per_year, factor: 12}` |
| `unit_forms` | cách viết đơn vị ngay sau con số trong hợp đồng (bộ đọc slot tra theo đây, không đoán) | `percent_per_year: ["/năm", "một năm"]` |
| `document_facts` | dữ kiện cấp hợp đồng: `{unit, from: <trường trích>, parse: <bộ đọc>}` | `monthly_rent_vnd: {unit: vnd, from: rent, parse: money}` |
| `extract_fields` | trường cần LLM trích thêm (nếu chưa có trong `contracts/fact_catalog.json`) | `[{key: rent, label: "Giá thuê", kind: text}]` |
| `user_facts`, `user_fact_units`, `user_fact_questions` | dữ kiện người dùng trả lời, đơn vị mặc định, câu hỏi gợi ý | |
| `findings`, `silences` | kết quả thêm ngoài lõi; kết quả khi hợp đồng không nói tới khái niệm | |
| `derived` | dữ kiện suy ra (cây ngoại lệ, §5.3); `object_type` nếu theo đối tượng hồ sơ | |
| `object_types` | kiểu đối tượng cho hồ sơ nhiều văn bản (§5.6) | `Lease: {attrs: [...], refs: [tenant]}` |
| `concept_kinds` | CHỈ kind riêng của gói; kind chung nằm ở `packs/kinds.yaml` (mọi gói thấy, không được khai lại khác đi). Mỗi khái niệm khai `kind:` hoặc nằm trong `not_fitting` của `kinds.yaml` (test `tests/test_kinds.py`) | `my_kind: {slot_kinds: [bool]}` |

Bộ đọc (`parse`) có sẵn: `duration`, `duration_to_unit`, `money`, `percent`, `flag`, `enum` (`values: {nhãn: mã}`),
`contains` (`contains: [[cụm chữ, mã], ...]`, theo thứ tự ưu tiên). Cần bộ đọc khác thì mới phải sửa code
(`bridge/facts_map._PARSERS` + `rules/model.DOCUMENT_PARSERS`).

## `concepts.yaml`

`roles` (id, `label`, tùy chọn `aliases`: chữ mô tả bên trong hợp đồng, vd. "công ty"), `concepts` (slot, anchors,
rules) như gói `labor`. Mỗi rule viết sau khi đọc văn bản luật; trích dẫn ghi ở `docs/rule_inventory/<gói>.yaml`.
`outcome: {legality: illegal|unknown, party_impact: unfavorable|neutral}` — `party_impact` là tác động lên bên giữ quyền
(`holder`); tên cũ `employee_impact` vẫn được nhận và đổi thành `party_impact` (`tests/test_party_impact.py`).

## Còn phải sửa code ở đâu (chưa là module — xem `reports/week-04/team-4.2/han_che_va_loi_ton_dong.md` mục M)

- Giao diện: `ui/contracts_api.py`, `ui/contract_studio.py` gọi gói labor; `bridge/view.py` nhãn hiển thị tĩnh.
- Nhận diện loại hợp đồng tự động (`classify_contract`, Huy): hiện người gọi truyền `document_kind` hoặc `packs`.
