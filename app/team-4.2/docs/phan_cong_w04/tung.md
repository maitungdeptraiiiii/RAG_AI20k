# Kế hoạch W04 — Tùng: rule engine + phần của Tú (hồ sơ, UI) + phần của Tuấn (phân tích luật, gold)

> Thiết kế: `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md` (giai đoạn P1–P7).
> Việc gốc: `tu.md` (D1–D5), `tuan.md` (T1–T5). Người phụ thuộc vào mình: Huy (`huy.md`), Khánh (`khanh.md`).

## 0. Thực tế khối lượng

Ước tính thô (ngày làm việc tập trung):

| Nhóm | Việc | Ước tính |
|---|---|---|
| Chốt định dạng + stub | formats ngày 1, `evaluator.py` stub, JSON mẫu | 0,5 |
| Engine | P1 tách lõi + Reference + pack labor + golden · P2 mạng điều kiện · P3 suy ra + ngoại lệ · P4 explain/questions/diff · P5 pack civil · P7 join (phía engine) | 5–6 |
| Phần Tuấn | T1 lao động · T2–T3 BLDS · T4 kind · T5 gold | 2–2,5 |
| Phần Tú | D1–D4 hồ sơ + kịch bản · D5 UI | 2–2,5 |
| **Tổng** | | **≈ 10 ngày** cho 5 ngày lịch |

→ Không làm hết được. Kế hoạch dưới đây cắt theo mức ưu tiên; phần "Could" chỉ làm khi phần trên xong.

## 1. Ưu tiên

**Must — thiếu là không có demo**
- P1 (Reference + pack labor, kết quả giống hệt engine cũ), P2 (mạng điều kiện, đối chiếu = Reference), P3 (kết luận trung gian
  + ngoại lệ), `evaluation_diff` + `explain()` (một phần P4).
- T1 (Đ20, Đ22.2, Đ25 BLLĐ) → rule trong pack labor.
- D1 bộ A, D2 b1–b4, gold cho a1 + b1–b4, kịch bản b3/b4.
- P7 tối thiểu: join đủ cho b1 (đếm HĐ XĐTH) và b3/b4 (kết luận trung gian xuyên hợp đồng), dùng `dossier_objects` của Huy.
- UI tối thiểu: diff lan truyền + cây giải thích + chạy kịch bản từng bước.

**Should — "đa luật"**
- T3 + P5 pack `civil_loan` (chỉ Đ468 lãi suất trần + lãi chậm trả) + D3 3 hợp đồng vay + gold.
- T4 danh sách kind (Huy cần cho tagger — làm sớm dù là Should).
- `next_questions()` + UI câu hỏi.

**Could**
- T2 BLDS phần chung đầy đủ, `civil_general` + `extends`.
- UI dòng thời gian, b5, Đ22.2 đếm phụ lục sửa thời hạn trong bộ A.

**Không làm tuần này**: tự nhận diện hồ sơ theo CCCD, thuê nhà, người tiêu dùng, Phreak/lazy.

## 2. Lịch theo ngày

Nguyên tắc: **sáng = code engine** (cần tập trung), **chiều = dữ liệu/UI**, **tối = đọc luật** (T1–T3).
Việc gỡ chặn cho Huy/Khánh luôn làm đầu ngày.

### Ngày 0 — CN 22/11 (tối, ~1 giờ)
- [ ] Duyệt spec engine (sửa §12 nếu không đồng ý); bổ sung P7 join vào spec.
- [ ] Commit spec + `docs/phan_cong_w04/`; gửi `huy.md`, `khanh.md`.

### Ngày 1 — T2 23/11
Sáng (gỡ chặn):
- [ ] `src/rag/rules/evaluator.py`: Protocol `Evaluator`/`Session`/`Diff` + `make_evaluator` stub trả dữ liệu giả đúng
      kiểu → báo Khánh.
- [ ] Chốt `dossier.yaml`, `gold.yaml`, JSON `evaluation_diff`/`ExplanationTree`/`Question`, `WorkingObject` → báo Huy.
- [ ] **Đóng băng golden**: chạy engine cũ trên mọi fixture hợp đồng hiện có, lưu `RuleResult` (làm TRƯỚC khi sửa
      engine).
Chiều:
- [ ] P1: `semantics.py` (chuyển nguyên logic cũ), `model.py`, `loader.py`, `packs/labor/pack.yaml`.
- [ ] T4 bản nháp danh sách kind → gửi Huy.
Tối:
- [ ] T1: đọc Đ20, Đ22, Đ25 BLLĐ + NĐ 145 phần liên quan; ghi `docs/rule_inventory/labor_w04.yaml`.

**Hết ngày**: Khánh có stub; Huy có định dạng + kind nháp.

### Ngày 2 — T3 24/11
Sáng:
- [ ] P1 xong: `ReferenceEvaluator`, lớp tương thích `bridge/engine.py`, `catalog.py`; test cũ + golden xanh.
Chiều:
- [ ] D1 bộ A (`tests/fixtures/rete/a1/`) → báo Huy chạy `dossier_objects`.
- [ ] D2 khung văn bản b1–b4 (theo T1).
Tối:
- [ ] T1 xong (ngoại lệ Đ20.2 đầy đủ, có quote); viết rule tương ứng ở dạng inventory.

**Hết ngày**: P1 merge được; bộ A có.
**Điểm cắt**: P1 chưa xanh golden → ngày 3 dồn hết vào P1, bỏ Should.

### Ngày 3 — T4 25/11
Sáng:
- [ ] P2 mạng điều kiện: `network/network.py` (alpha dùng chung, node ba trị có bộ đếm), `session.py` (`update`, `fork`, diff).
- [ ] Test đối chiếu ngẫu nhiên Network = Reference (seed cố định).
Chiều:
- [ ] **P7a** (spec §5.6, checklist D23–D25): ngữ nghĩa đối tượng / đếm / phủ định ba trị trong `semantics.py` +
      `ReferenceEvaluator` có đối tượng + bảng chân lý. Cần `dossier_objects` của Huy (H2).
- [ ] D2 hoàn tất b1–b4 + `dossier.yaml`.
Tối:
- [ ] T5 gold cho a1, b1–b4 (viết trước khi chạy engine trên hồ sơ).
- [ ] D4 `scenario.yaml` cho b3/b4 và a1.

**Hết ngày**: mạng điều kiện qua đối chiếu; Reference chạy được hồ sơ có đối tượng; đủ hồ sơ + gold Must.
**Điểm cắt**: mạng còn lệch Reference → dùng Reference cho demo, mạng chỉ trình bày benchmark; không trễ P3 và P7a.

### Ngày 4 — T5 26/11
Sáng:
- [ ] P3: dữ kiện suy ra (cây ngoại lệ §5.3) + `exception_of` giữa rule (§5.4) ở cả hai evaluator; viết rule Đ20.2 vào
      pack labor.
Chiều:
- [ ] **P7b** (D26–D29): rule xuyên văn bản b1–b5 vào pack; `ObjectMemory` / `GroupMatchNode` / `ObjectLeaf` trong mạng;
      đối chiếu ngẫu nhiên Network = Reference có đối tượng; soát theo kỳ a1 khớp gold.
- [ ] Báo Khánh engine thật sẵn sàng (benchmark trục 2 + eval chạy số thật).
Tối:
- [ ] T3: đọc BLDS Đ463–471 (tập trung Đ466, Đ468) → `docs/rule_inventory/civil_loan.yaml`.
- [ ] (Should) P5 pack `civil_loan` + D3 3 hợp đồng vay + gold.

**Hết ngày**: b1–b4 chạy bằng engine thật (qua test / CLI; chưa nối API).

### Ngày 5 — T6 27/11
Sáng:
- [ ] Nối `check_contract` + `tools.check_concept` vào session; `evaluation_diff`; `explain()`; endpoint SSE (E1–E3, D17, D19).
- [ ] D5 UI tối thiểu trong `contract-studio/`: diff lan truyền + cây giải thích + nút "bước tiếp" theo `scenario.yaml`.
      (Nếu trễ: chỉ làm chạy kịch bản + cây giải thích; đã có mock từ ngày 1.)
Chiều:
- [ ] Đọc bảng eval + benchmark của Khánh; sửa lỗi nhãn / lỗi engine (ghi kết luận cho từng ca).
- [ ] (Should) `next_questions()` + hiển thị câu hỏi.
- [ ] Diễn tập demo: a1 (thời gian), b1→b2 (ngoại lệ), b3→b4 (rút lại kết luận), benchmark, (vay nếu có).

## 3. Phụ thuộc với người khác

| Khi | Mình giao | Cho ai |
|---|---|---|
| Ngày 1 sáng | stub `Evaluator`, định dạng, `WorkingObject` | Khánh, Huy |
| Ngày 1 chiều | danh sách kind nháp | Huy (tagger) |
| Ngày 2 chiều | bộ A | Huy (`dossier_objects`) |
| Ngày 3 | b1–b4 + gold | Huy, Khánh (eval) |
| Ngày 4 chiều | engine thật | Khánh |

| Khi | Mình cần | Từ ai |
|---|---|---|
| Ngày 2 | BLDS trong kho (để đọc + pid đúng) | Khánh K1 |
| Ngày 3 chiều | `dossier_objects` chạy trên a1, b1–b4 (cần cho P7a) | Huy H1 |
| Ngày 5 sáng | bảng benchmark + eval | Khánh K2–K3 |

## 4. Nếu quá tải — cắt theo thứ tự

1. UI dòng thời gian, câu hỏi gợi ý (demo bằng JSON / CLI thay vì UI).
2. `civil_loan` (nói "đa luật" bằng thiết kế pack + benchmark, không bằng pack thật).
3. P7b join cho b1/b5 (giữ b3/b4 vì demo rút lại kết luận trực quan hơn); D30 (`network+beta`).
4. Nhờ Huy làm UI tối thiểu (Huy là tác giả `contract-studio/`), đổi lại bỏ H3 của Huy.

Không bao giờ cắt: golden P1, đối chiếu Network = Reference, quote nguyên văn trong inventory/gold.

## 5. Kỷ luật làm việc (giữ đúng ý thiết kế khi tự làm hết)

- Đọc luật trước khi viết rule/gold — không viết rule từ trí nhớ (kể cả các số điều trong spec).
- Gold viết **trước** khi chạy engine trên hồ sơ đó, để gold không bị "chỉnh theo engine".
- Mỗi giai đoạn engine: test trước (TDD), merge khi golden + đối chiếu xanh.
- Kế hoạch triển khai chi tiết từng giai đoạn engine (task, file, test) viết riêng sau khi duyệt spec.
