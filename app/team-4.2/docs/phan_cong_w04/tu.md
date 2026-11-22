# Phân công W04 — Tùng (nhận phần của Tú): bộ hồ sơ demo + Contract Studio cho mạng tăng dần

> Đường dẫn `src/`, `docs/`, `tests/`, `ui/`, `contract-studio/` tính từ `app/team-4.2/`.
> Thiết kế engine (đọc §5.6, §6 "Mạng phụ thuộc tăng dần", §8 "Giải thích và câu hỏi"): `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md`.
> Người quyết định: **Tùng**. Chỗ nào file này không nói rõ → hỏi Tùng, không tự chọn.

## 0. Vai trò trong 5 dòng

- Phần join của mạng chỉ "đáng dùng" khi dữ liệu có **lịch sử theo thời gian** (phụ lục) và **quan hệ giữa văn bản** (nhiều hợp
  đồng của một NLĐ). Tú soạn đúng những hồ sơ làm lộ ra hai điều đó.
- Tú cập nhật **Contract Studio** để người xem *thấy* mạng tăng dần làm việc: cái gì thay đổi, vì sao, hỏi gì tiếp.
- UI làm trên **JSON mẫu** (§4) từ ngày 1, ngày 4 mới nối vào engine thật — không chờ engine.
- Nhãn đúng/sai (gold) là của Tuấn; Tú chỉ soạn văn bản + kịch bản.
- Khi trình bày: Tú bảo vệ "bộ dữ liệu được thiết kế để kiểm cái gì" và demo UI.

## 1. Việc chi tiết

### D1 — Bộ A: một hợp đồng + phụ lục theo thời gian (xong ngày 2)

Thư mục `tests/fixtures/rete/a1/`. Văn bản `.txt` viết theo mẫu `tests/fixtures/bridge/hdld_tvpl_2025_filled.txt`
(giữ cấu trúc Điều/Khoản để parser hiện có đọc được). Mỗi phụ lục **phải** có câu "có hiệu lực kể từ ngày dd/mm/yyyy"
và câu dẫn chiếu kiểu "sửa đổi Khoản 1 Điều 5 của Hợp đồng" (để `rag.contracts.amendments` bắt được).

| Văn bản | Hiệu lực | Nội dung | Mục đích |
|---|---|---|---|
| HĐ xác định thời hạn 36 tháng, vùng I | 01/03/2023 | Lương 4.700.000 | Hợp lệ lúc ký |
| (mốc luật) | 01/07/2024 | lương tối thiểu vùng I tăng | Vi phạm phát sinh dù hợp đồng không đổi |
| Phụ lục 1 | 01/09/2024 | Tăng lương 5.000.000 | Hết vi phạm |
| Phụ lục 2 | 01/02/2025 | Sửa thời hạn hợp đồng lần 1 | Hợp lệ |
| Phụ lục 3 | 01/08/2025 | Sửa thời hạn lần 2 | Vi phạm (Tuấn xác nhận căn cứ) |
| (mốc luật) | 01/01/2026 | lương tối thiểu vùng I tăng | Vi phạm lại |

### D2 — Bộ B: nhiều hợp đồng của một NLĐ (xong ngày 3)

Mỗi tình huống một thư mục `tests/fixtures/rete/b1/` … `b5/`. Nội dung pháp lý chính xác lấy theo bản liệt kê của
Tuấn (`docs/rule_inventory/labor_w04.yaml`) — nếu Tuấn chưa xong, soạn khung văn bản trước, điền chi tiết sau.

| Hồ sơ | Văn bản | Ý định kiểm |
|---|---|---|
| b1 | HĐ1 XĐTH 2022, HĐ2 XĐTH 2023, HĐ3 XĐTH 2024 | Giới hạn số lần ký HĐ xác định thời hạn |
| b2 | Như b1, NLĐ thuộc một trường hợp ngoại lệ (Tuấn chọn) | Ngoại lệ ghi đè quy tắc chung |
| b3 | HĐ1 hết hạn 31/12/2022, NLĐ vẫn làm, HĐ2 ký 15/03/2023 | Kết luận trung gian "trở thành HĐ không xác định thời hạn" |
| b4 | Như b3 + một HĐ ký 10/01/2023 bị "sót" (thêm ở bước sau của kịch bản) | Kết luận trung gian tự rút lại |
| b5 | HĐ2 có thử việc lại cho cùng công việc với HĐ1 | Join theo công việc |

### D3 — Hợp đồng vay mẫu (xong ngày 3)

`tests/fixtures/rete/loan/` — 5–10 hợp đồng vay giữa cá nhân / cá nhân với doanh nghiệp: lãi hợp lệ, lãi vượt trần,
lãi ghi theo tháng (cần quy đổi), không ghi lãi, có điều khoản phạt chậm trả, có điều khoản trả trước hạn. Mỗi hợp đồng
một dòng trong `tests/fixtures/rete/loan/README.md` nói nó kiểm gì. Nhãn gold do Tuấn điền.

### D4 — Kịch bản demo theo bước (ngày 3)

`tests/fixtures/rete/<dossier_id>/scenario.yaml` cho a1, b1/b2, b3/b4:

```yaml
dossier_id: b3
steps:
  - {do: load, docs: [hd1_2022, hd2_2023], review_date: 2023-06-01, say: "Kết quả ban đầu"}
  - {do: add, docs: [hd_sot_2023], say: "Bổ sung hợp đồng bị sót → kết luận trung gian rút lại"}
  - {do: answer, facts: {employee_is_elderly: true}, say: "Người dùng trả lời câu hỏi gợi ý"}
  - {do: set_review_date, value: 2026-01-15, say: "Đổi ngày soát"}
```

### D5 — Contract Studio: hiển thị mạng tăng dần (ngày 1–4)

Làm trong `contract-studio/` (React/Vite) — Huy hướng dẫn codebase ngày 1. Bốn phần:
1. **Diff lan truyền**: nhận sự kiện `evaluation_diff` (§4), tô các rule đổi trạng thái, hiện "nguyên nhân" (dữ kiện
   / văn bản vừa thêm) và số node được tính lại.
2. **Cây giải thích**: click một kết quả → vẽ `ExplanationTree` (§4) từ kết luận tới **câu trích trong hợp đồng**;
   ngoại lệ bị loại hiển thị mờ kèm lý do.
3. **Dòng thời gian**: trục ngày, các khoảng PASS/FAIL theo `periods` (cho bộ A).
4. **Câu hỏi gợi ý**: danh sách `Question` (§4) xếp theo `resolves_min`; trả lời → gửi `answer` → nhận diff.
5. Chế độ **chạy kịch bản**: đọc `scenario.yaml`, bấm "bước tiếp" để chạy từng bước (dùng khi thuyết trình).

Mock: `contract-studio/src/live/mocks/rete/*.json` — viết tay theo §4 cho a1 và b3/b4.

## 2. Không được làm

- Không sửa `src/rag/rules/**`, `src/rag/bridge/engine.py`, `pack.yaml`, phần `rules` của `concepts.yaml`.
- Không tự quyết nội dung pháp lý (số lần ký, ngoại lệ, mức lương) — lấy từ Tuấn; chưa có thì để `TODO(Tuấn)`.
- Không tự điền `gold.yaml`.
- Không tự đổi định dạng JSON §4 hay `dossier.yaml`; cần thêm trường → hỏi Tùng.
- UI không tự tính lại kết quả rule ở phía client — chỉ hiển thị cái engine trả.
- Không dùng dữ liệu cá nhân thật (tên, CCCD) trong văn bản mẫu.

## 3. `dossier.yaml` (chốt ngày 1 với Tùng + Huy)

```yaml
dossier_id: b1
review_date: 2024-03-01
employee: {id: e1, name: "Nguyễn Văn A", cccd: "001090000001", birth_date: 1990-05-01}
documents:
  - {doc_id: hd1_2022, file: hd1_2022.txt, kind: labor_contract, employee: e1}
  - {doc_id: hd2_2023/pl1, file: hd2_2023_pl1.txt, kind: amendment, contract: hd2_2023}
user_facts: {wage_region: I}
```

## 4. JSON mẫu (Tùng chốt ngày 1; đây là bản nháp để bắt đầu)

```json
{"type": "evaluation_diff", "step": 2,
 "cause": {"kind": "add_document", "docs": ["hd_sot_2023"]},
 "changed": [{"concept_id": "contract.type_conversion", "rule_id": "r1", "object": "hd1_2022",
              "before": {"status": "PASS", "finding": "ok"}, "after": {"status": "NOT_APPLICABLE", "finding": "ok"}}],
 "stats": {"nodes_recomputed": 12, "ms": 0.4}}
```

```json
{"node": "rule", "id": "wage.minimum_regional/r1", "object": "hd_2023", "status": "FAIL",
 "children": [
   {"node": "condition", "label": "Lương ≥ lương tối thiểu vùng", "tri": "F", "children": [
      {"node": "fact", "name": "base_salary_vnd", "value": 4700000, "unit": "vnd", "source": "contract",
       "uid": "p0.d5.k1", "quote": "Mức lương chính: 4.700.000 đồng/tháng"},
      {"node": "law_value", "name": "min_wage", "value": 4960000, "unit": "vnd", "source": "nghi-dinh:74/2024/NĐ-CP"}]},
   {"node": "exception", "id": "…", "tri": "F", "reason": "không áp dụng", "dimmed": true}]}
```

```json
{"fact": "employee_is_elderly", "question": "Người lao động có phải người cao tuổi không?", "type": "bool",
 "options": [true, false], "resolves_min": 3, "affected": ["contract.fixed_term_limit/r1"]}
```

## 5. Nghiệm thu

| # | Tiêu chí |
|---|---|
| D1–D3 | Parser hiện có đọc được mọi văn bản (Điều/Khoản, phụ lục, ngày hiệu lực); Huy chạy `dossier_objects` không lỗi |
| D4 | Mỗi kịch bản chạy hết trên UI bằng mock, sau đó bằng engine thật |
| D5 | Bốn phần UI + chế độ kịch bản chạy được trên a1, b3/b4; không lỗi console |

## 6. Mốc kiểm tra với Tùng

| Ngày | Mốc |
|---|---|
| 1 (23/11) | Chốt `dossier.yaml`, JSON §4; Huy hướng dẫn `contract-studio/`; dựng mock |
| 2 | Nộp bộ A; UI diff + cây giải thích trên mock |
| 3 | Nộp bộ B, hợp đồng vay, kịch bản; UI dòng thời gian + câu hỏi |
| 4 | Nối engine thật (cùng Tùng/Huy) |
| 5 | Diễn tập demo; chuẩn bị phần trình bày |

## 7. Câu hỏi mở (ghi vào đây, Tùng trả lời)

-
