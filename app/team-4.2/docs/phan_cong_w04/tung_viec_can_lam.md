# W04 — Toàn bộ việc của Tùng (checklist)

> Gộp: engine (spec bản 2 `2026-11-22-rete-rule-engine-design.md`, giai đoạn 1–7) + phần của Tuấn (`tuan.md`, T1–T5)
> + phần của Tú (`tu.md`, D1–D5) + tích hợp + demo. Thứ tự trong mỗi nhóm = thứ tự làm.
> Ký hiệu "→ ai" = xong việc này thì báo người đó. Mã việc D1–D30 là mã trong file này (không phải D1–D5 của `tu.md`).
> Bản 2: mạng điều kiện tăng dần + join kiểu TREAT; evaluator tên `reference` / `network`.
> **Bản 3 (23/11): định hướng phủ rộng nhiều loại hợp đồng** — ba miền ngang hàng (lao động, vay, thuê nhà); thêm
> B7, C3b, C7, mục P8 (D31–D37), E5; sửa B1, C4, C5 và thứ tự cắt. Spec bản 3 đã duyệt (Tùng, 23/11).

## A. Chuẩn bị và gỡ chặn (ngày 0–1)

- [x] A1. Duyệt spec engine bản 2 (đã thêm giai đoạn 7, §5.6, §4.2); chốt §12; kiểm với bài gốc TREAT việc xử lý
      phủ định (spec §4.2 ghi "chưa xác minh").
- [ ] A2. Commit spec + `docs/phan_cong_w04/`; gửi `huy.md`, `khanh.md`.
- [x] A3. `src/rag/rules/evaluator.py`: Protocol `Evaluator`, `Session`, `Diff`, `make_evaluator` (stub, đúng kiểu). → Khánh
- [ ] A4. Chốt định dạng: `dossier.yaml`, `gold.yaml` (theo kỳ), `scenario.yaml`, bản liệt kê rule, JSON
      `evaluation_diff` / `ExplanationTree` / `Question`, `WorkingObject`. → Huy, Khánh
- [x] A5. **Golden**: chạy engine cũ trên mọi fixture hợp đồng hiện có, lưu `RuleResult` vào
      `tests/fixtures/rules/golden/`. Làm trước khi sửa bất kỳ dòng engine nào.

## B. Phân tích luật (phần Tuấn)

- [x] B1. (T4) Danh sách `kind` + slot chung **cho cả ba miền** (bắt đầu từ 39 concept lao động); kind dùng chung có
      concept của ≥2 miền; danh sách concept "không vừa". → Huy. *(23/11: danh sách chung `src/rag/rules/packs/kinds.yaml`, bộ nạp đọc; 10 kind, 4 kind
      dùng ở ≥2 miền (required_content, time_limit, notice, termination); 5 khái niệm thai sản "không vừa". Bản nháp
      cũ `docs/rule_inventory/kinds.yaml` đã gộp vào và xóa. Cần duyệt.)*
- [x] B2. (T1) Đ20 BLLĐ: nghĩa vụ ký mới, hệ quả không ký, giới hạn số lần ký HĐ XĐTH, **đủ mọi ngoại lệ** (đọc cả
      các điều được dẫn chiếu) → `docs/rule_inventory/labor_w04.yaml`. *(Claude soạn, cần duyệt)*
- [x] B3. (T1) Đ22.2 (phụ lục sửa thời hạn), Đ25 (thử việc một lần / một công việc). *(NĐ 145/2020 không có trong kho:
      ghi open_questions.)*
- [x] B4. (T3) BLDS Đ463–471 hợp đồng vay → `docs/rule_inventory/civil_loan.yaml` (11 mục). *(cần duyệt)*
- [x] B5. (T2) BLDS phần chung hợp đồng → `docs/rule_inventory/civil_general.yaml` (9 mục). *(cần duyệt; Luật Thương
      mại không có trong kho nên trần phạt 8% chưa trích được)*
- [x] B7. (T6) Thuê nhà ở: BLDS Đ472–482 + Luật Nhà ở 27/2023 Đ163–173 → `docs/rule_inventory/civil_lease.yaml`; quy
      định Luật Nhà ở đè BLDS ghi thành `exceptions`. *(9 mục, trích theo kỳ Luật Nhà ở 2014 / 2023 (`periods`);
      Luật 27/2023 hiệu lực 01/08/2024 theo Luật 43/2024. Quan hệ BLDS ↔ Luật Nhà ở ghi ở open_questions thay vì
      exceptions vì BLDS Đ472 dẫn thẳng sang Luật Nhà ở. Cần duyệt.)*
- [ ] B6. Kiểm lại mọi số điều đã ghi trong spec / file phân công theo văn bản gốc.

Mỗi mục: pid, quote nguyên văn, type, kind, derogation, facts_needed, threshold, exceptions (mỗi cái có pid + quote),
conclusion, on_silence, ≥3 ví dụ (PASS / FAIL / UNKNOWN).

## C. Dữ liệu hồ sơ (phần Tú)

- [ ] C1. (D1) Bộ A `tests/fixtures/rete/a1/`: HĐ 2023 + 3 phụ lục (lương, sửa thời hạn ×2), câu "có hiệu lực kể từ
      ngày", dẫn chiếu "sửa đổi Khoản … Điều …". → Huy
- [ ] C2. (D2) b1 (3 HĐ XĐTH), b2 (b1 + ngoại lệ), b3 (hết hạn vẫn làm, ký muộn), b4 (b3 + HĐ bị sót), b5 (thử việc
      lại cùng công việc) + `dossier.yaml` mỗi bộ. → Huy
- [x] C3. (D3) `tests/fixtures/rete/loan/`: 5–10 hợp đồng vay (hợp lệ, vượt trần, lãi theo tháng, không ghi lãi,
      phạt chậm trả, trả trước hạn) + `README.md`. *(7 hợp đồng; chưa có: lãi không ghi kỳ, phạt + lãi quá hạn, hợp đồng
      của tổ chức tín dụng)*
- [~] C3b. (D3b) `tests/fixtures/rete/lease/`: ≥5 hợp đồng thuê nhà (có `hop_dong_thue_nha_2023.txt`) + hồ sơ nhiều
      văn bản `r1/` (HĐ thuê + phụ lục gia hạn + phụ lục tăng giá) + `README.md`. *(Có 6 hợp đồng + facts + gold 11
      nhãn. Chưa có: hồ sơ `r1/` (xem D37), `hop_dong_thue_nha_2023.txt` không có trong repo, README.)*
- [ ] C4. (T5) `gold.yaml` cho a1, b1–b5, loan, **lease, r1** — **viết trước khi chạy engine trên hồ sơ đó**; mỗi nhãn
      có basis.
- [ ] C5. (D4) `scenario.yaml` cho a1, b1→b2, b3→b4, **r1**.
- [ ] C7. `dossier.yaml` theo định dạng tổng quát (`tu.md` §3 bản 3: `packs`, `parties` theo vai trò, `documents[].refs`).
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
- [x] D8. `network/nodes.py`: Fact, Alpha (dùng chung), And/Or/Not (bộ đếm T/F/U), Law, LawLeaf, Presence, Rule.
- [x] D9. `network/network.py`: biên dịch từ pack, rank topo, cache theo (packs, version).
- [x] D10. `network/session.py`: `results`, `update` (hàng đợi theo rank, mỗi node tính ≤1 lần), `fork`, `Diff`.
- [x] D11. Test đối chiếu ngẫu nhiên Network = Reference (pack + dữ kiện + chuỗi update, seed cố định, vài nghìn ca).
- [x] D12. Bất biến: dữ kiện chuyển sang thiếu không làm rule nào thành `FAIL`.

**P3 — kết luận trung gian + ngoại lệ**
- [x] D13. `derived` + cây ngoại lệ (§5.3) ở cả hai evaluator; phát hiện vòng; `missing_facts` mở ra dữ kiện đầu vào.
- [x] D14. `exception_of` giữa rule / giữa pack (§5.4), bảng ba hàng T/F/U.
- [x] D15. Test bảng chân lý §5.3, §5.4.
- [ ] D16. Rule từ B2–B3 vào `packs/labor/` (Đ20.2 kết luận trung gian + giới hạn số lần ký + ngoại lệ; Đ22.2; Đ25).
      Xong phần Đ20.2 (đọc văn bản gốc: Đ20, 149.1, 151.2, 177.4): `contract_kind_effective`, `content.term/r3` (+ 4 ngoại lệ
      `r3_*`), `r4`; 7 dữ kiện người dùng mới trong `pack.yaml` (Tú / Huy: cần hỏi người dùng; nhãn ở `bridge/view.py`).
      **Chưa làm, chuyển sang giai đoạn 7b:** Đ22.2 (phụ lục sửa thời hạn: cần đối tượng phụ lục) và "một lần một công việc"
      của Đ25 (cần nhiều hợp đồng; theo từng văn bản đã có `probation.duration`, `probation.once`). Khi 7b xong, nguồn của
      `fixed_term_contract_count` đổi từ người dùng sang phép đếm đối tượng, rule `r3` giữ nguyên.

**P4 — giải thích, câu hỏi, sự kiện**
- [x] D17. `explain.py`: cây tới quote hợp đồng, nguồn giá trị luật, ngoại lệ bị loại; JSON + markdown.
- [x] D18. `questions.py`: `next_questions()` bằng `fork` + `update`, điểm = số UNKNOWN chắc chắn giải quyết.
- [x] D19. Sự kiện stream `evaluation_diff`. (`rules/events.py`; `check_contract` phát sau recheck. Miền câu hỏi: `user_fact_questions` trong `pack.yaml`.)

**P5 — pack dân sự**
- [x] D20. `packs/civil_loan/` từ B4 (đơn vị `percent_per_year`, quy đổi tháng → năm). (Mới có trần lãi Đ468.1 + ngoại lệ luật chuyên ngành; đã đọc Đ463–471, chưa viết rule cho Đ466.4, Đ468.2, Đ470.)
- [x] D21. `packs/civil_general/` từ B5; `civil_loan` extends `civil_general`; ngoại lệ luật chuyên ngành. (Mới có Đ428.2 phải thông báo khi đơn phương chấm dứt.)
- [x] D22. Trường `kind` trong concept + kiểm slot khớp kind (B1). (Kiểm theo *loại* slot, không ép tên slot; danh sách kind của B1 chưa có, mới khai `rate_cap`.)

**P7a — ngữ nghĩa đối tượng trong Reference (làm ngay sau P1, song song P2; Reference là chuẩn đúng nên có trước mạng)**
- [x] D23. Spec §5.6 trong `semantics.py`: ba trị của ứng viên, đếm theo khoảng `[n_T, n_T + n_U]`, `exists` /
      `not exists`, thành viên theo ngày soát, nhóm; trường `RuleResult.object`.
- [x] D24. Cú pháp YAML `over` / `group_by` / `check.count` + loader kiểm (biến, kiểu, không vòng).
- [x] D25. `ReferenceEvaluator` nhận `objects`; test bảng chân lý §5.6 (mọi toán tử, ứng viên U, `valid_from` chưa biết,
      khóa nhóm chưa biết).
- [x] D26. Rule xuyên văn bản vào `packs/labor/`: số lần ký HĐ XĐTH (b1/b2), chuyển loại HĐ (b3/b4), thử việc lại
      (b5), đếm phụ lục sửa thời hạn (a1).

**P7b — join kiểu TREAT trong mạng (sau P3)**
      Đã có: `content.term/r5` (Đ20.2.c đếm HĐ), `r6` (Đ20.2.b theo từng HĐ), `r7` (Đ22.2), `probation.once/r2` (Đ25).
- [x] D27. `network/objects.py`: `ObjectMemory`, `GroupMatchNode`, `ObjectLeaf`; `update(objects=...)` chỉ tính lại
      nhóm bị ảnh hưởng, không lưu kết quả nối trung gian.
- [x] D28. Soát theo kỳ cho bộ A (kết quả theo khoảng thời gian, khớp `gold.yaml`). (`rules/timeline.py`; chưa so với `gold.yaml` vì bộ A — C1/C4 — chưa có.)
- [x] D29. Đối chiếu ngẫu nhiên Network = Reference có đối tượng (thêm / xóa / đổi đối tượng).
- [ ] D30. (Could) biến thể `network+beta` (nối lưu bộ nhớ beta kiểu Rete) chỉ để Khánh so với TREAT trên trục 2.

**P8 — phủ rộng (bản 3, Must)**
- [x] D31. Gói `packs/civil_lease/` (extends `civil_general`) từ B7; `document_kinds: [lease_contract]`, `object_types`
      `Lease` / `Amendment`, `roles` bên cho thuê / bên thuê. *(6 khái niệm; chưa khai `object_types` vì chưa có rule
      xuyên văn bản có căn cứ, xem D37.)*
- [x] D32. `document_kinds` của mọi gói thành nguồn chọn gói: `packs_for_kind(kind) -> list[str]`; `check_contract`
      không truyền `packs` thì chọn theo `classify_contract` (H2 của Huy); `unknown` → không chạy gói nào + cảnh báo.
      *(Phía engine xong: `packs_for_kind`, `check_contract(document_kind=)`. Chưa có `classify_contract` nên khi không
      truyền gì vẫn dùng gói labor — chuyển tiếp, xem E5.)*
- [x] D33. `party_impact` trung tính: YAML mới dùng `outcome.party_impact`; bộ nạp nhận `employee_impact` cũ; thêm
      `RuleResult.outcome` (dict) đúng spec §5.2; `employee_impact` giữ làm tên tương thích. *(Xong 23/11: `tests/test_party_impact.py`.)*
- [ ] D34. *(UI — để sau, 23/11)* Nhãn hiển thị theo gói: `bridge/view.py` (`VERDICTS`, `FACT_LABELS` viết cứng "người lao động") lấy từ
      `pack.yaml` (`findings` kèm nhãn, `user_fact_questions` / nhãn dữ kiện).
- [x] D35. `kind` chung: sửa `kinds.yaml` theo B1, khai `kind` cho concept dân sự (`civil.unilateral_termination` → notice),
      test mọi concept của mọi gói có kind hoặc nằm trong "không vừa".
- [x] D36. Test ba miền: nạp `labor` + `civil_loan` + `civil_lease` cùng lúc không xung đột; hợp đồng thuê nhà mẫu không
      ra kết quả gói `labor`; khi soát vay / thuê, không prompt / nhãn nào có chữ "lao động".
- [x] D38. `bridge/facts_map.normalize_slot` theo `slot.unit` của gói: `percent` kèm kỳ ("/năm", "/tháng") ra
      `percent_per_year` / `percent_per_month`, `money` đúng đơn vị gói; hiện luôn trả `percent` / `vnd` nên lãi vay
      "30%/năm" ra UNKNOWN rỗng `missing_facts` (thử nghiệm 23/11).
- [x] D39. `document_facts` của gói khai cách trích (`pack.yaml`: khóa trường trích + bộ chuẩn hóa trong sổ đăng ký);
      `facts_map._CONTRACT_MAP` (7 dữ kiện lao động viết cứng) đọc từ gói; gói không khai thì không có dữ kiện hợp đồng.
- [ ] D40. Gói được chọn đi suốt luồng: `ui/contracts_api.py` (dòng 437, 514), `ui/contract_studio.py` (34, 268) và
      `contracts/graph/build.py:164` gọi `load_catalog()` (labor) không `packs`; đồ thị bỏ cạnh `HOLDER` im lặng cho khái
      niệm gói khác. Truyền `catalog` / `packs` từ `check_contract` xuống.
      *(Phần logic xong: vai trò các bên theo `roles` của gói, ASSERT khái niệm ghi `holder`, đồ thị nối `HOLDER` cho mọi
      gói. **Còn phần UI** (`ui/contracts_api.py`, `ui/contract_studio.py`): để sau theo yêu cầu 23/11.)*
- [x] D41. Mẫu gói: `src/rag/rules/packs/README.md` + test `tests/test_pack_plugin.py` "thêm gói giả không sửa file code nào" (chạy gói tổng
      hợp qua `check_contract` với LLM giả, kiểm trích slot, đơn vị, nhãn, đồ thị).
- [x] D37. Rule xuyên văn bản cho thuê nhà (hồ sơ r1: gia hạn, tăng giá giữa kỳ) sau khi đọc luật (B7). *(Đọc luật
      23/11: giá thuê mới luôn "do các bên thỏa thuận" (Luật Nhà ở 2023 Đ170.2), nên phụ lục gia hạn / tăng giá hai bên
      ký là hợp lệ — chưa tìm được rule vi phạm có căn cứ; Tùng duyệt 23/11: không viết rule; r1 thành hồ sơ kiểm phụ lục hợp lệ không ra vi phạm.)*

## E. Tích hợp

- [x] E1. `check_contract`: tham số `packs=`, `evaluator=` (mặc định `network`), biến môi trường
      `RAG_RULE_EVALUATOR`; sau recheck chỉ `update` dữ kiện mới. *(phần `packs=` chưa làm: giai đoạn 5)*
- [x] E2. `tools.check_concept` + `ask_contract_graph` dùng session.
- [ ] E3. Endpoint SSE trong `ui/contract_studio.py`: chạy hồ sơ / kịch bản, phát `evaluation_diff`, trả `explain`,
      `next_questions`, nhận `answer`. Chạy được hồ sơ của cả ba miền.
- [ ] E5. Nối `classify_contract` (Huy) vào `check_contract` / `ask_contract_graph` theo D32. → Huy
- [x] E4. Báo Khánh engine thật sẵn sàng. → Khánh (`reports/team-4.2/w04/engine_interface.md`; cần gửi cho Khánh và Huy)

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
| B Phân tích luật | 7 |
| C Dữ liệu | 8 |
| D Engine | 41 (trong đó D30 là Could) |
| E Tích hợp | 5 |
| F UI | 7 |
| G Đánh giá + demo | 6 |
| H Theo dõi | 4 |
| **Cộng** | **83** (82 không tính Could) |

Đường găng (trễ là trễ cả tuần): A5 → D1–D7 → D23–D25 (Reference có đối tượng) → D8–D11 → D13–D16 → D26–D29 → E3 →
F6/F7 → G5. Mạng điều kiện (D8–D11) và Reference có đối tượng (D23–D25) có thể xen kẽ vì dùng chung `semantics.py`.
Việc đọc luật (B) và soạn dữ liệu (C) chạy song song, nhưng B2–B3 phải xong trước D16 và D26, C1–C2 trước H2.

Nếu quá tải, cắt theo thứ tự (bản 3): D30 → UI phụ (dòng thời gian, câu hỏi) → b5 → bớt số rule mỗi miền (giữ ≥3 rule
có gold mỗi miền). **Không bỏ miền nào.** Không cắt: golden (A5), đối chiếu Network = Reference (D11, D29), trích
nguyên văn trong inventory / gold, ba miền chạy end-to-end (P8).
