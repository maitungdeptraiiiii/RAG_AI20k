# W04 — Toàn bộ việc của Tùng (checklist)

> Gộp: engine (spec bản 2 `2026-11-22-rete-rule-engine-design.md`, giai đoạn 1–7) + phần của Tuấn (`tuan.md`, T1–T5)
> + phần của Tú (`tu.md`, D1–D5) + tích hợp + demo. Thứ tự trong mỗi nhóm = thứ tự làm.
> Ký hiệu "→ ai" = xong việc này thì báo người đó. Mã việc D1–D30 là mã trong file này (không phải D1–D5 của `tu.md`).
> Bản 2: mạng điều kiện tăng dần + join kiểu TREAT; evaluator tên `reference` / `network`.

## A. Chuẩn bị và gỡ chặn (ngày 0–1)

- [ ] A1. Duyệt spec engine bản 2 (đã thêm giai đoạn 7, §5.6, §4.2); chốt §12; kiểm với bài gốc TREAT việc xử lý
      phủ định (spec §4.2 ghi "chưa xác minh").
- [ ] A2. Commit spec + `docs/phan_cong_w04/`; gửi `huy.md`, `khanh.md`.
- [x] A3. `src/rag/rules/evaluator.py`: Protocol `Evaluator`, `Session`, `Diff`, `make_evaluator` (stub, đúng kiểu). → Khánh
- [ ] A4. Chốt định dạng: `dossier.yaml`, `gold.yaml` (theo kỳ), `scenario.yaml`, bản liệt kê rule, JSON
      `evaluation_diff` / `ExplanationTree` / `Question`, `WorkingObject`. → Huy, Khánh
- [x] A5. **Golden**: chạy engine cũ trên mọi fixture hợp đồng hiện có, lưu `RuleResult` vào
      `tests/fixtures/rules/golden/`. Làm trước khi sửa bất kỳ dòng engine nào.

## B. Phân tích luật (phần Tuấn)

- [ ] B1. (T4) Danh sách `kind` + slot chung từ 39 concept lao động; danh sách concept "không vừa". → Huy
- [ ] B2. (T1) Đ20 BLLĐ: nghĩa vụ ký mới, hệ quả không ký, giới hạn số lần ký HĐ XĐTH, **đủ mọi ngoại lệ** (đọc cả
      các điều được dẫn chiếu) → `docs/rule_inventory/labor_w04.yaml`.
- [ ] B3. (T1) Đ22.2 (phụ lục sửa thời hạn), Đ25 (thử việc một lần / một công việc), NĐ 145 phần liên quan.
- [ ] B4. (T3) BLDS Đ463–471 hợp đồng vay → `docs/rule_inventory/civil_loan.yaml` (Đ466, Đ468 kỹ nhất).
- [ ] B5. (T2) BLDS phần chung hợp đồng (hình thức, hợp đồng mẫu, phạt vi phạm, bồi thường, đơn phương chấm dứt,
      vô hiệu) → `docs/rule_inventory/civil_general.yaml`.
- [ ] B6. Kiểm lại mọi số điều đã ghi trong spec / file phân công theo văn bản gốc.

Mỗi mục: pid, quote nguyên văn, type, kind, derogation, facts_needed, threshold, exceptions (mỗi cái có pid + quote),
conclusion, on_silence, ≥3 ví dụ (PASS / FAIL / UNKNOWN).

## C. Dữ liệu hồ sơ (phần Tú)

- [ ] C1. (D1) Bộ A `tests/fixtures/rete/a1/`: HĐ 2023 + 3 phụ lục (lương, sửa thời hạn ×2), câu "có hiệu lực kể từ
      ngày", dẫn chiếu "sửa đổi Khoản … Điều …". → Huy
- [ ] C2. (D2) b1 (3 HĐ XĐTH), b2 (b1 + ngoại lệ), b3 (hết hạn vẫn làm, ký muộn), b4 (b3 + HĐ bị sót), b5 (thử việc
      lại cùng công việc) + `dossier.yaml` mỗi bộ. → Huy
- [ ] C3. (D3) `tests/fixtures/rete/loan/`: 5–10 hợp đồng vay (hợp lệ, vượt trần, lãi theo tháng, không ghi lãi,
      phạt chậm trả, trả trước hạn) + `README.md`.
- [ ] C4. (T5) `gold.yaml` cho a1, b1–b5, loan — **viết trước khi chạy engine trên hồ sơ đó**; mỗi nhãn có basis.
- [ ] C5. (D4) `scenario.yaml` cho a1, b1→b2, b3→b4.
- [ ] C6. Kiểm parser hiện có đọc được mọi văn bản (Điều/Khoản, phụ lục, ngày hiệu lực).

## D. Engine

**P1 — lõi + Reference + pack labor**
- [x] D1. `src/rag/rules/semantics.py`: chuyển nguyên `compare`, `convert` (bảng đơn vị từ pack), `eval_cond`,
      `resolve_law`, bảng trạng thái `_evaluate_rule`; thêm `UNKNOWN`.
- [x] D2. `model.py`, `loader.py`: Pack, Rule, Concept; `pack.yaml`; kiểm + báo hết lỗi một lần; `extends`; trùng id.
- [x] D3. Hai hook lao động → khai báo: `document_facts`, `unstated_false` (bộ nạp tự suy cho YAML cũ).
- [x] D4. `packs/labor/` (chuyển `concepts.yaml`, viết `pack.yaml`), `catalog.DEFAULT_PATH`; báo Huy đường dẫn mới.
- [x] D5. `reference.py`: `ReferenceEvaluator` (thứ tự topo).
- [x] D6. Lớp tương thích `bridge/engine.py`, `bridge/catalog.py` (giữ tên công khai, `legality`/`employee_impact`).
- [x] D7. Nghiệm thu P1: toàn bộ `tests/test_bridge_*.py`, `test_contract_graph_tools.py` + golden xanh.

**P2 — mạng điều kiện (mệnh đề, tăng dần)**
- [ ] D8. `network/nodes.py`: Fact, Alpha (dùng chung), And/Or/Not (bộ đếm T/F/U), Law, LawLeaf, Presence, Rule.
- [ ] D9. `network/network.py`: biên dịch từ pack, rank topo, cache theo (packs, version).
- [ ] D10. `network/session.py`: `results`, `update` (hàng đợi theo rank, mỗi node tính ≤1 lần), `fork`, `Diff`.
- [ ] D11. Test đối chiếu ngẫu nhiên Network = Reference (pack + dữ kiện + chuỗi update, seed cố định, vài nghìn ca).
- [ ] D12. Bất biến: dữ kiện chuyển sang thiếu không làm rule nào thành `FAIL`.

**P3 — kết luận trung gian + ngoại lệ**
- [ ] D13. `derived` + cây ngoại lệ (§5.3) ở cả hai evaluator; phát hiện vòng; `missing_facts` mở ra dữ kiện đầu vào.
- [ ] D14. `exception_of` giữa rule / giữa pack (§5.4), bảng ba hàng T/F/U.
- [ ] D15. Test bảng chân lý §5.3, §5.4.
- [ ] D16. Rule từ B2–B3 vào `packs/labor/` (Đ20.2 kết luận trung gian + giới hạn số lần ký + ngoại lệ; Đ22.2; Đ25).

**P4 — giải thích, câu hỏi, sự kiện**
- [ ] D17. `explain.py`: cây tới quote hợp đồng, nguồn giá trị luật, ngoại lệ bị loại; JSON + markdown.
- [ ] D18. `questions.py`: `next_questions()` bằng `fork` + `update`, điểm = số UNKNOWN chắc chắn giải quyết.
- [ ] D19. Sự kiện stream `evaluation_diff`.

**P5 — pack dân sự**
- [ ] D20. `packs/civil_loan/` từ B4 (đơn vị `percent_per_year`, quy đổi tháng → năm).
- [ ] D21. `packs/civil_general/` từ B5; `civil_loan` extends `civil_general`; ngoại lệ luật chuyên ngành.
- [ ] D22. Trường `kind` trong concept + kiểm slot khớp kind (B1).

**P7a — ngữ nghĩa đối tượng trong Reference (làm ngay sau P1, song song P2; Reference là chuẩn đúng nên có trước mạng)**
- [ ] D23. Spec §5.6 trong `semantics.py`: ba trị của ứng viên, đếm theo khoảng `[n_T, n_T + n_U]`, `exists` /
      `not exists`, thành viên theo ngày soát, nhóm; trường `RuleResult.object`.
- [ ] D24. Cú pháp YAML `over` / `group_by` / `check.count` + loader kiểm (biến, kiểu, không vòng).
- [ ] D25. `ReferenceEvaluator` nhận `objects`; test bảng chân lý §5.6 (mọi toán tử, ứng viên U, `valid_from` chưa biết,
      khóa nhóm chưa biết).
- [ ] D26. Rule xuyên văn bản vào `packs/labor/`: số lần ký HĐ XĐTH (b1/b2), chuyển loại HĐ (b3/b4), thử việc lại
      (b5), đếm phụ lục sửa thời hạn (a1).

**P7b — join kiểu TREAT trong mạng (sau P3)**
- [ ] D27. `network/objects.py`: `ObjectMemory`, `GroupMatchNode`, `ObjectLeaf`; `update(objects=...)` chỉ tính lại
      nhóm bị ảnh hưởng, không lưu kết quả nối trung gian.
- [ ] D28. Soát theo kỳ cho bộ A (kết quả theo khoảng thời gian, khớp `gold.yaml`).
- [ ] D29. Đối chiếu ngẫu nhiên Network = Reference có đối tượng (thêm / xóa / đổi đối tượng).
- [ ] D30. (Could) biến thể `network+beta` (nối lưu bộ nhớ beta kiểu Rete) chỉ để Khánh so với TREAT trên trục 2.

## E. Tích hợp

- [ ] E1. `check_contract`: tham số `packs=`, `evaluator=` (mặc định `network`), biến môi trường
      `RAG_RULE_EVALUATOR`; sau recheck chỉ `update` dữ kiện mới.
- [ ] E2. `tools.check_concept` + `ask_contract_graph` dùng session.
- [ ] E3. Endpoint SSE trong `ui/contract_studio.py`: chạy hồ sơ / kịch bản, phát `evaluation_diff`, trả `explain`,
      `next_questions`, nhận `answer`.
- [ ] E4. Báo Khánh engine thật sẵn sàng. → Khánh

## F. UI Contract Studio (phần Tú)

- [ ] F1. Mock JSON `contract-studio/src/live/mocks/rete/` cho a1, b3/b4.
- [ ] F2. Diff lan truyền (rule đổi trạng thái, nguyên nhân, số node tính lại).
- [ ] F3. Cây giải thích (tới quote; ngoại lệ bị loại hiển thị mờ).
- [ ] F4. Dòng thời gian theo kỳ (bộ A).
- [ ] F5. Câu hỏi gợi ý + trả lời → diff.
- [ ] F6. Chạy kịch bản từng bước từ `scenario.yaml`.
- [ ] F7. Nối API thật (E3); không lỗi console.

## G. Đánh giá, demo, báo cáo

- [ ] G1. Đọc benchmark của Khánh (đủ 6 kịch bản, hai trục: số rule và số đối tượng; 0 ca lệch); biểu đồ cho slide.
- [ ] G2. Đọc eval của Khánh; mỗi ca lệch gold: kết luận lỗi engine hay lỗi nhãn, sửa, ghi lại.
- [ ] G3. ≥5 failure case cho báo cáo.
- [ ] G4. Slide: vấn đề → khảo sát (Rete và các biến thể, DMN, Catala, OIA, …) → lựa chọn → kiến trúc → demo →
      benchmark → giới hạn (spec §4.2).
- [ ] G5. Diễn tập demo: a1, b1→b2, b3→b4, hợp đồng vay, benchmark.
- [ ] G6. Chuẩn bị hỏi đáp: vì sao mạng điều kiện + join kiểu TREAT thay vì Rete đầy đủ / Phreak / LEAPS; vì sao ba
      trị và đếm theo khoảng `[n_T, n_T + n_U]`; vì sao gold độc lập với engine; phần nào chưa có tài liệu công bố.

## H. Theo dõi người khác

- [ ] H1. Ngày 2: Khánh nạp xong BLDS (cần cho B4–B5 có pid).
- [ ] H2. Ngày 3: Huy `dossier_objects` chạy trên a1, b1–b5 (cần cho D25–D28).
- [ ] H3. Ngày 3–4: Huy tagger theo kind + nhận diện loại hợp đồng trên C3.
- [ ] H4. Ngày 5: Khánh bảng benchmark + eval.

## Tổng

| Nhóm | Số việc |
|---|---|
| A Chuẩn bị | 5 |
| B Phân tích luật | 6 |
| C Dữ liệu | 6 |
| D Engine | 30 (trong đó D30 là Could) |
| E Tích hợp | 4 |
| F UI | 7 |
| G Đánh giá + demo | 6 |
| H Theo dõi | 4 |
| **Cộng** | **68** (67 không tính Could) |

Đường găng (trễ là trễ cả tuần): A5 → D1–D7 → D23–D25 (Reference có đối tượng) → D8–D11 → D13–D16 → D26–D29 → E3 →
F6/F7 → G5. Mạng điều kiện (D8–D11) và Reference có đối tượng (D23–D25) có thể xen kẽ vì dùng chung `semantics.py`.
Việc đọc luật (B) và soạn dữ liệu (C) chạy song song, nhưng B2–B3 phải xong trước D16 và D26, C1–C2 trước H2.

Nếu quá tải, cắt theo thứ tự: D30 → UI phụ → gói vay → D26 cho b1/b5 (giữ b3/b4). Không cắt: golden (A5), đối chiếu
Network = Reference (D11, D29), trích nguyên văn trong inventory / gold.
