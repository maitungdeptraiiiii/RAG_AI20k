# Phân công — Tuần 3: Soát hợp đồng lao động bằng đồ thị hợp đồng + đồ thị luật

> **Quy ước đường dẫn:** `src/`, `docs/`, `tests/` tính từ `app/team-4.2/`; `data/`, `evals/`, `reports/` tính từ gốc repo.
> **Phương pháp chuyên sâu của tuần 3:** quan hệ → graph. Hybrid RAG (BM25 + Dense + RRF) giữ nguyên làm baseline;
> phương pháp mới = Hybrid + đồ thị luật + lớp cầu nối (khái niệm, rule, quan hệ quyền ↔ nghĩa vụ).
> **Lĩnh vực:** hợp đồng lao động (BLLĐ 45/2019, NĐ 145/2020, TT 10/2020, chuỗi NĐ lương tối thiểu vùng, Luật BHXH + NĐ 158/2025, NĐ 12/2022).
> **Spec liên quan:** `2026-11-13-legal-corpus-graph-design.md`, `2026-11-13-contract-fact-verification-design.md`,
> `2026-11-11-contract-review-design.md`. Lớp cầu nối chưa có spec — viết ngày 1 (việc C1).

---

## 1. Vai trò

Điền tên thật vào cột "Thành viên" (A–E theo `teams/team-4.2/README.md`).

| Vai trò | Thành viên | Phần sở hữu |
|---|---|---|
| **HĐ** — Hợp đồng + tích hợp | A (Tùng) | Dữ kiện hợp đồng, đồ thị hợp đồng, ghép pipeline, owner tích hợp tuần 3 |
| **LU** — Luật | Huy | Đồ thị luật (cấu trúc + dẫn chiếu + hướng dẫn) và chú giải thực thể theo điều luật lao động |
| **CN** — Cầu nối | Tú | Danh mục khái niệm, gán điều khoản hợp đồng → khái niệm → điều luật |
| **RU** — Rule + quyền lợi | Tuấn | Rule ngưỡng, ứng viên xung đột, duyệt quyền ↔ nghĩa vụ, báo cáo soát |
| **EV** — Evaluation | A (Tùng) | Phân loại câu hỏi, gold set, harness, ablation, failure analysis |
| **TR** — Truy xuất + router + guardrail | Khánh | Nhánh hybrid clause → luật (baseline + dự phòng); router (liên quan / cache) và guardrail cho chat hỏi đáp luật thường. Không làm gì trên đồ thị |

**CN** và **RU** được thiết kế thành một mạch liên tục nối thẳng vào phần **HĐ**: cùng đọc dữ kiện hợp đồng
(`fact_catalog.json`), cùng ghi vào đồ thị hợp đồng qua oplog, cùng nằm trong một package `src/rag/bridge/`.
Thứ tự làm tự nhiên: HĐ → CN → RU.

Lưu ý Q&A: rubric yêu cầu mỗi người hiểu toàn bộ pipeline và bảo vệ phần mình. Người đứng tên CN / RU cần đọc
mục 4 và spec cầu nối trước demo.

---

## 2. Luồng dữ liệu

```
HĐ:  Hợp đồng (PDF/DOCX) ─► cây điều khoản ─► dữ kiện (lương, thử việc, thời hạn, phép, vùng…) ─► đồ thị hợp đồng
                                                        │
CN:                          Clause ──ABOUT──► LegalConcept ──ANCHORED_AT──► Provision (pid)
                                                        │                         ▲
LU:                                                     │      đồ thị luật: phiên bản theo ngày, REFERS_TO,
                                                        │      GUIDES, chuỗi REPLACES, chú giải điều luật
                                                        ▼
RU:   Rule(dữ kiện, ngưỡng tại ngày ký) ─► MAY_CONFLICT_WITH (ứng viên, có bằng chứng, trạng thái duyệt)
      LegalConcept ──CORRELATES──► concept đối ứng ──LEADS_TO──► quyền phát sinh + checklist điều kiện
                                                        │
                                              Báo cáo soát (rủi ro + quyền lợi + trích dẫn)
                                                        │
TR:   Clause ─► hybrid + rerank (lọc văn bản lao động, hiệu lực tại ngày ký) ─► pid  (baseline + dự phòng cho CN)
      Chat hỏi đáp luật: câu hỏi ─► guardrail vào ─► router: ngoài phạm vi? → từ chối │ có cache? → trả lại
                                  │ không ─► RAG / agent hiện có ─► guardrail ra ─► ghi cache
                                                        │
EV:   gold set + câu hỏi ─► BM25 / Dense / Hybrid / Hybrid+graph ─► chất lượng theo loại, latency, chi phí
```

Nguyên tắc chung:
- Văn bản gốc là nguồn sự thật; mọi kết luận trỏ về `pid` + phiên bản tại ngày ký + đoạn hợp đồng.
- Cạnh nối hai đồ thị lưu bên đồ thị hợp đồng, tham chiếu luật bằng `pid` (chuỗi), không tạo cạnh vật lý chéo DB.
- Không có cạnh xung đột nào do LLM tạo mà được coi là sự thật: LLM chỉ đề xuất, trạng thái `candidate`.

---

## 3. Interface chốt ngày 1 (CN viết, cả nhóm review)

```yaml
# src/rag/bridge/concepts.yaml — viết tay, ~25–35 khái niệm
- id: probation.max_duration
  label: Thời gian thử việc tối đa
  modality: threshold            # right | duty | prohibition | threshold
  holder: NSDLĐ                  # bên chịu ràng buộc / bên có quyền
  correlative: null              # id khái niệm đối ứng (quyền ↔ nghĩa vụ)
  leads_to: []                   # khái niệm phát sinh khi bị vi phạm
  anchors: ["bo-luat:45/2019/QH14#d25"]
  facts: [probation_days, job_level]

# src/rag/bridge/rules.yaml
- id: R-PROBATION-MAX
  concept: probation.max_duration
  check: "probation_days <= lookup(probation_cap, job_level)"
  anchor: "bo-luat:45/2019/QH14#d25"
  severity: illegal              # illegal | unfavorable | info
```

Cạnh mới trong đồ thị hợp đồng (bổ sung `contracts/graph/schema.json`):
`Clause -ABOUT-> Concept`, `Clause -MAY_CONFLICT_WITH {rule_id|llm, evidence, confidence, state}-> pid`,
`Contract -HAS_RIGHT_CANDIDATE {concept, conditions[], anchors[]}`.

API phía luật mà cầu nối được gọi (LU cung cấp, khớp §6 spec đồ thị luật):
`text_at(pid, date)`, `applicable(chain, date)`, `guidance(pid)`, `refs(pid, direction)`, `annotations(pid)`.

---

## 4. Việc chi tiết

### HĐ — A (Tùng)
| # | Việc | Nghiệm thu |
|---|---|---|
| H1 | Hoàn tất danh mục dữ kiện lao động trong `fact_catalog.json` (lương, phụ cấp, vùng, thử việc + lương thử việc, loại/thời hạn HĐ, số lần ký, giờ làm, phép năm, báo trước, phạt, bồi thường, giấy tờ giữ lại) | Mỗi rule của RU có đủ dữ kiện đầu vào |
| H2 | Trích + xác minh dữ kiện theo spec fact-verification | Dữ kiện có trạng thái và trỏ đoạn gốc |
| H3 | Dẫn chiếu trong hợp đồng: phụ lục sửa điều nào, điều khoản viện dẫn nội quy | Cạnh trong đồ thị hợp đồng |
| H4 | Ghép pipeline end-to-end, endpoint soát trong `ui/contracts_api.py` | Upload 1 HĐ → báo cáo có trích dẫn |

### LU — Luật(Huy)
| # | Việc | Nghiệm thu |
|---|---|---|
| L1 | Theo §11 spec đồ thị luật: sửa kho (§7), dựng cấu trúc, `GUIDES`/`BASED_ON`, `REFERS_TO`, phụ lục. Ưu tiên 17 văn bản lao động | Nghiệm thu §8 spec, đặc biệt 5 ca cụ thể |
| L2 | Bổ sung seeds tầng 1–2 (TT 10/2020, NĐ 12/2022, Luật Việc làm 74/2025, NĐ 158/2025, chuỗi NĐ lương tối thiểu) | Có trong snapshot |
| L3 | **Chú giải thực thể theo điều luật** — chỉ cho điều luật lao động ưu tiên (BLLĐ ch. III, VI, VII, VIII; NĐ 145 phần tương ứng; TT 10): `holder`, `modality`, `condition`, `exception_of`, `defines`. Model nhỏ đề xuất → người duyệt → lưu `ProvisionAnnotation` có trạng thái duyệt. **Không** chạy trên toàn kho | ≥80 điều/khoản đã duyệt; tỉ lệ sửa khi duyệt được ghi lại |
| L4 | Lớp truy vấn cho cầu nối (`text_at`, `applicable`, `guidance`, `refs`, `annotations`) | Test cho 5 ca §8 + 1 ca chú giải |

### CN — Cầu nối (HĐ → luật) Tú
| # | Việc | Nghiệm thu |
|---|---|---|
| C1 | Spec cầu nối ngắn (1–2 trang) + `concepts.yaml` 25–35 khái niệm, mỗi khái niệm neo vào `pid` (LU xác nhận neo) | Mọi `anchors` giải được trên đồ thị luật |
| C2 | Gán Clause → Concept: phân loại vào danh sách đóng bằng model nhỏ, ghi cạnh `ABOUT` qua oplog (`candidate`) | Đo độ chính xác trên gold của EV |
| C3 | Concept → điều luật tại ngày ký qua API LU; clause không thuộc khái niệm nào thì gọi nhánh hybrid của TR (T1) | Mỗi clause có ≥1 điều luật hoặc ghi "không xác định" |

### RU — Rule + quyền lợi (Tuấn)
| # | Việc | Nghiệm thu |
|---|---|---|
| R1 | `rules.yaml` ~15 rule ngưỡng: thử việc (thời gian, 85%), thời hạn ≤36 tháng / số lần ký, lương ≥ tối thiểu vùng tại ngày ký, phép năm ≥12, làm thêm (giới hạn, 150/200/300%), báo trước 3/30/45, cấm phạt tiền, cấm giữ giấy tờ / đặt cọc | Mỗi rule có test đúng / sai |
| R2 | Ứng viên `MAY_CONFLICT_WITH`: rule tất định + LLM cho điều khoản không định lượng (kèm trích dẫn hai bên, `candidate`) | Không cạnh nào thiếu bằng chứng |
| R3 | Khám phá quyền lợi tối thiểu: `CORRELATES` + `LEADS_TO` từ khái niệm bị vi phạm, sinh checklist điều kiện cho người dùng xác nhận (không tự kết luận) | 3 chuỗi demo: chậm lương → nghỉ không báo trước → trợ cấp thôi việc; làm thêm → tiền làm thêm; thử việc quá hạn |
| R4 | Báo cáo soát (JSON + hiển thị): rủi ro, căn cứ, quyền lợi, điều kiện | Dùng được cho demo |

### EV — Evaluation (A — Tùng tự thiết kế)
Phạm vi phải phủ deliverable tuần 3: bảng loại câu hỏi → phương pháp → bằng chứng (W03-01), ≥40 câu theo loại +
latency + chi phí cùng điều kiện (W03-03), ablation + ≥5 failure case (W03-04). Chi tiết do A quyết.
Hai điểm nối với người khác: bảng loại câu hỏi chốt **ngày 1** vì router của TR dùng nó; LU kiểm nhãn điều luật trong gold.

### TR — Truy xuất + router + guardrail (Khánh)
Router và guardrail áp cho **chat hỏi đáp luật thường**
(`RAGPipeline` / `AgentPipeline` hiện có), không áp cho luồng soát hợp đồng.

| # | Việc | Nghiệm thu |
|---|---|---|
| T1 | **Nhánh hybrid clause → luật**: dùng `HybridRetriever` + rerank sẵn có, lọc theo văn bản lao động và hiệu lực tại ngày ký (metadata + temporal filter), trả `pid` + phiên bản + điểm + provenance theo định dạng A chốt ngày 1. Vừa là baseline cho eval vừa là dự phòng của C3. Chỉ dùng index vector/BM25, không gọi đồ thị | Chạy được trên gold của EV |
| T2 | **Router — kiểm tra liên quan**: câu hỏi có thuộc phạm vi kho luật không (pháp luật trong kho vs chào hỏi / ngoài phạm vi / không phải câu hỏi pháp lý). Ngoài phạm vi thì trả lời định hướng, không gọi retrieval / LLM sinh. Bắt đầu bằng luật đơn giản + model nhỏ | Bộ ≥50 câu có nhãn trong/ngoài phạm vi; báo precision/recall, nhất là tỉ lệ chặn nhầm câu hợp lệ |
| T3 | **Router — cache câu trả lời**: tìm câu đã trả lời gần nghĩa (embedding sẵn có), trúng thì trả lại kèm citation cũ. Khóa cache phải gồm snapshot kho luật (`CURRENT`) và ngày áp dụng — đổi snapshot thì không dùng lại. Chặn trúng nhầm: hai câu gần nghĩa nhưng khác số / vùng / điều / ngày (vd. "lương tối thiểu vùng I" vs "vùng II") không được coi là trùng. Khác với `LLMCache` hiện có (chỉ khớp chính xác prompt) | Tỉ lệ trúng, **tỉ lệ trúng nhầm** (phải ≈0 trên bộ cặp câu gần nghĩa có chủ đích), latency + chi phí tiết kiệm |
| T4 | **Guardrail**: mở rộng phần từ chối sẵn có trong `pipeline.py` / `generate/answer.py` thay vì viết mới. Vào: prompt injection, che dữ liệu cá nhân (CCCD, SĐT, STK) trước khi gửi LLM. Ra: mọi khẳng định phải có citation hợp lệ, không trích văn bản hết hiệu lực tại ngày hỏi, câu nhắc "không thay thế tư vấn pháp lý" | Bộ ca kiểm thử cho từng luật chặn; không làm giảm điểm eval chat hiện có |

Thứ tự: T1 trước (A và Tú cần), rồi T2 → T3 → T4. Số liệu T2–T4 (độ chính xác, latency, chi phí) đưa vào báo cáo
tuần 3 cùng phần eval của A.

---

## 5. Lịch 5 ngày

| Ngày | HĐ (A) | LU (Huy) | CN (Tú) | RU (Tuấn) | EV (A) | TR (Khánh) |
|---|---|---|---|---|---|---|
| 1 | Chốt interface §3, H1 | L1 sửa kho + cấu trúc, L2 | C1 spec + concepts | Danh sách rule R1 | Bảng loại câu hỏi, bắt đầu gold | Đọc `retrieve/`, `pipeline.py`; bắt đầu T1 |
| 2 | H2, H3 | L1 `REFERS_TO`/`GUIDES`, bắt đầu L3 | C2 | R1 code + test | Gold set | T1 xong, bộ câu T2 |
| 3 | H4 ghép end-to-end | L3, L4 | C3 | R2 | Harness, baseline | T2, T3 |
| 4 | Sửa lỗi tích hợp | L3 tiếp, nghiệm thu §8 | Đo C2 trên gold | R3, R4 | Ablation + failure | T3 đo trúng nhầm, T4 |
| 5 | Demo | Demo | Demo | Demo | Số liệu slides | Số liệu router/cache/guardrail + demo |

Ngoài tuần 3 (tuần 4–5): mở rộng L3, khám phá quyền lợi đầy đủ, UI xem quan hệ điều khoản ↔ luật, HĐLĐ điện tử (NĐ 337/2025, TT 08/2026).

---

## 6. Ánh xạ tracker tuần 3

| ID | Owner | Reviewer |
|---|---|---|
| T4.2-W03-01 | A (EV) | Khánh |
| T4.2-W03-02 | A (tích hợp), Tú, Tuấn, Huy, Khánh (T1) | Khánh |
| T4.2-W03-03 | A (EV) | Huy |
| T4.2-W03-04 | A (EV) | Khánh |
| T4.2-W03-05 | Cả nhóm | A |

Khảo sát phương pháp (mục 1 scope tuần 3) chưa có người — A nhận hoặc chia lại.
