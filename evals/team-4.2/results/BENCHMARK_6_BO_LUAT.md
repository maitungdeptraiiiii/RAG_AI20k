# Kết quả benchmark — 6 Bộ luật (40 câu)

So sánh 4 cấu hình trên cùng bộ câu hỏi, cùng index. Baseline là hybrid thuần.

| Cấu hình | Retrieval | Context cho LLM | Kết quả gốc |
|---|---|---|---|
| **Hybrid** (baseline) | BM25 + Dense, gộp RRF (k=60) | Top-5 cố định | [`bench6-40q-gpt6luna/`](bench6-40q-gpt6luna/) |
| **+ Jev** | Hybrid, rerank Jev 20 ứng viên RRF | Theo ngưỡng p ≥ 0.6 | [`bench6-40q-jev-p06/`](bench6-40q-jev-p06/) |
| **+ HyDE** | BM25 + Dense + arm HyDE, gộp RRF | Top-5 cố định | [`bench6-40q-hyde/`](bench6-40q-hyde/) |
| **+ HyDE + Jev** | BM25 + Dense + HyDE, rerank Jev | Theo ngưỡng p ≥ 0.6 | [`bench6-40q-hyde-jev-p06/`](bench6-40q-hyde-jev-p06/) |

**HyDE:** LLM viết một đoạn trả lời giả theo văn phong văn bản luật, rồi tìm bằng embedding của
"câu hỏi + đoạn giả" trên index Dense. Đây là một arm riêng gộp vào RRF; BM25 vẫn tìm bằng câu hỏi gốc.
Tốn thêm 1 lần gọi LLM mỗi câu hỏi.

**Context theo ngưỡng:** chỉ đưa cho LLM các đoạn có xác suất liên quan do Jev chấm p ≥ 0.6 (tối đa 8 đoạn /
2400 từ). Không đoạn nào qua ngưỡng thì từ chối luôn, không gọi LLM.

## Thiết lập chung

- **Corpus:** 6 Bộ luật từ vbpl.vn (Hình sự 2015, Tố tụng hình sự 2015, Lao động 2019, Dân sự 2015,
  Tố tụng dân sự 2015, Hàng hải 2015), 3.422 chunk (`MAX_SYLLABLES=300`). Snapshot trong `data/team-4.2/`.
- **Embedding:** `text-embedding-3-small` (1536 chiều), Qdrant local. **BM25:** tách từ pyvi.
- **LLM** (trả lời và viết đoạn HyDE): `gpt-6-luna`, temperature mặc định (model không nhận temperature=0).
- **Bộ câu hỏi:** [`datasets/benchmark_6_bo_luat.jsonl`](../datasets/benchmark_6_bo_luat.jsonl), 40 câu:
  16 lookup (hỏi sát câu chữ luật), 16 paraphrase (diễn đạt đời thường), 8 multi (cần nối 2-3 Điều,
  có câu nối hai bộ luật). Gold = section của Điều; một chunk khớp gold nếu thuộc Điều đó.
- **Chỉ số retrieval:** chấm trên top-5 cố định ở mọi cấu hình. Context theo ngưỡng chỉ ảnh hưởng phần trả lời.

## Retrieval

### Toàn bộ (n=40)

| Chỉ số | Hybrid | + Jev | + HyDE | + HyDE + Jev |
|---|---|---|---|---|
| Recall@5 | 0.633 | 0.775 | 0.742 | **0.821** |
| Hit@5 | 0.700 | 0.850 | 0.825 | **0.900** |
| MRR@5 | 0.658 | 0.838 | 0.703 | **0.875** |
| Recall@20 | 0.783 | 0.783 | **0.838** | **0.838** |

Chênh lệch so với baseline: + Jev +0.142 Recall@5 / +0.180 MRR@5; + HyDE +0.109 / +0.045;
+ HyDE + Jev **+0.188 / +0.217**.

### Theo loại câu hỏi (Recall@5 / MRR@5)

| Loại | n | Hybrid | + Jev | + HyDE | + HyDE + Jev |
|---|---|---|---|---|---|
| lookup | 16 | 1.000 / 0.969 | 1.000 / 1.000 | 1.000 / 0.969 | 1.000 / 1.000 |
| paraphrase | 16 | 0.375 / 0.344 | 0.750 / 0.750 | 0.688 / 0.412 | **0.812 / 0.781** |
| multi | 8 | 0.417 / 0.667 | 0.375 / 0.688 | 0.333 / 0.750 | **0.479 / 0.812** |

Recall@20 (trần của rerank): paraphrase 0.750 → 0.812 và multi 0.417 → 0.562 khi thêm HyDE; lookup luôn 1.000.

### Ghi chú: arm HyDE chạy riêng

Chỉ dùng arm HyDE (không BM25, không Dense gốc) cho Recall@5 0.812, MRR@5 0.811, Recall@20 0.892:
cao hơn khi gộp HyDE với BM25 + Dense bằng RRF (0.742 / 0.703 / 0.838). Với câu đời thường, BM25 và Dense
gốc kéo các đoạn sai lên và làm loãng kết quả của HyDE. Cấu hình này chưa chạy phần trả lời và chưa thử
kèm Jev.

## Trả lời

| Chỉ số | Hybrid | + Jev | + HyDE | + HyDE + Jev |
|---|---|---|---|---|
| Từ chối (cả 40 câu đều trong phạm vi) | 11/40 | 8/40 | 9/40 | 8/40 |
| Context chứa ít nhất một Điều gold | 0.700 | 0.825 | 0.825 | **0.875** |
| Số đoạn context trung bình | 5.0 | 1.58 | 5.0 | 1.75 |

Chưa chấm tay đúng/sai từng câu trả lời: cột `correct`/`citation_ok` trong `answers.csv` còn trống.

## Chi tiết từng câu

Viết tắt: LĐ = Lao động, DS = Dân sự, HS = Hình sự, TTHS = Tố tụng hình sự, TTDS = Tố tụng dân sự, HH = Hàng hải.

| Câu | Loại | Điều gold | R@5 Hybrid | R@5 +Jev | R@5 +HyDE | R@5 +HyDE+Jev | Trả lời Hybrid | +Jev | +HyDE | +HyDE+Jev |
|---|---|---|---|---|---|---|---|---|---|---|
| q01 | lookup | LĐ Đ105 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q02 | lookup | LĐ Đ113 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q03 | lookup | DS Đ20 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q04 | lookup | TTHS Đ118 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q05 | lookup | TTDS Đ273 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q06 | lookup | HH Đ219 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q07 | lookup | DS Đ623 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q08 | lookup | HS Đ9 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q09 | paraphrase | LĐ Đ35 | 0.00 | 1.00 | 1.00 | 1.00 | từ chối | trả lời | trả lời | trả lời |
| q10 | paraphrase | LĐ Đ139 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q11 | paraphrase | DS Đ468 | 0.00 | 1.00 | 1.00 | 1.00 | từ chối | trả lời | trả lời | trả lời |
| q12 | paraphrase | DS Đ651 | 0.00 | 1.00 | 1.00 | 1.00 | từ chối | trả lời | trả lời | trả lời |
| q13 | paraphrase | LĐ Đ25 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q14 | paraphrase | LĐ Đ169 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q15 | paraphrase | HS Đ260 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q16 | paraphrase | TTDS Đ39 | 0.00 | 0.00 | 0.00 | 0.00 | trả lời | trả lời | trả lời | trả lời |
| q17 | multi | HS Đ12, HS Đ173, HS Đ9 | 0.33 | 0.33 | 0.33 | 0.33 | trả lời | trả lời | từ chối | từ chối |
| q18 | multi | DS Đ468, DS Đ429 | 0.00 | 0.00 | 0.00 | 0.00 | trả lời | từ chối | trả lời | từ chối |
| q19 | multi | LĐ Đ190, LĐ Đ41 | 0.00 | 0.00 | 0.00 | 0.50 | từ chối | từ chối | từ chối | từ chối |
| q20 | multi | HS Đ173, HS Đ9, TTHS Đ173 | 0.67 | 0.33 | 0.33 | 0.33 | từ chối | từ chối | từ chối | từ chối |
| q21 | lookup | LĐ Đ98 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q22 | lookup | LĐ Đ112 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q23 | lookup | HS Đ27 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q24 | lookup | HS Đ32 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q25 | lookup | TTHS Đ147 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q26 | lookup | TTDS Đ203 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q27 | lookup | HH Đ52 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q28 | lookup | DS Đ625 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q29 | paraphrase | LĐ Đ115 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q30 | paraphrase | LĐ Đ46 | 0.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q31 | paraphrase | HS Đ174 | 0.00 | 0.00 | 0.00 | 1.00 | từ chối | từ chối | từ chối | trả lời |
| q32 | paraphrase | DS Đ601 | 0.00 | 0.00 | 0.00 | 0.00 | từ chối | từ chối | từ chối | từ chối |
| q33 | paraphrase | TTHS Đ76 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q34 | paraphrase | HH Đ151 | 0.00 | 1.00 | 0.00 | 1.00 | từ chối | trả lời | từ chối | trả lời |
| q35 | paraphrase | HH Đ8 | 0.00 | 1.00 | 1.00 | 1.00 | từ chối | trả lời | trả lời | trả lời |
| q36 | paraphrase | TTDS Đ147 | 0.00 | 0.00 | 0.00 | 0.00 | từ chối | từ chối | từ chối | từ chối |
| q37 | multi | LĐ Đ107, LĐ Đ98 | 1.00 | 1.00 | 1.00 | 1.00 | trả lời | trả lời | trả lời | trả lời |
| q38 | multi | HS Đ174, HS Đ9, HS Đ27 | 0.33 | 0.33 | 0.33 | 0.67 | từ chối | từ chối | từ chối | từ chối |
| q39 | multi | DS Đ625, DS Đ650, DS Đ651 | 0.67 | 0.67 | 0.33 | 0.67 | trả lời | từ chối | từ chối | từ chối |
| q40 | multi | HH Đ169, DS Đ4, DS Đ429 | 0.33 | 0.33 | 0.33 | 0.33 | trả lời | trả lời | trả lời | trả lời |

## Nhận xét

1. **Jev và HyDE bổ sung cho nhau.** HyDE kéo thêm gold vào 20 ứng viên (Recall@20 0.783 → 0.838); Jev đưa
   gold trong 20 ứng viên lên top-5. Kết hợp cho kết quả tốt nhất ở mọi chỉ số.
2. **HyDE cứu được câu mà rerank một mình không cứu được.** q31 ("lừa người ta lấy 30 triệu"): gold Điều 174
   BLHS nằm ngoài top-20 của hybrid; có HyDE thì vào được, Jev đưa lên top-5 và câu được trả lời đúng khung
   6 tháng – 3 năm. Ở cấu hình + HyDE + Jev, q19 và q38 (multi) cũng lấy thêm được một Điều gold vào top-5.
3. **HyDE một mình (không rerank) xếp hạng kém.** MRR@5 chỉ 0.703 so với 0.838 của Jev: gold vào được top-5 nhưng
   ít khi đứng đầu. q34 (tàu gặp bão) có gold khi dùng Jev nhưng mất khi chỉ dùng HyDE.
4. **Câu multi vẫn là điểm yếu.** Recall@5 cao nhất chỉ 0.479. Nhiều câu multi bị từ chối ở mọi cấu hình
   (q19, q20, q38) vì context thiếu Điều nền tảng mà câu hỏi không nhắc tới (Điều 9 BLHS phân loại tội phạm,
   Điều 650 BLDS). q17 có Điều 12 BLHS trong context ở cả hai cấu hình HyDE nhưng LLM vẫn từ chối vì thiếu
   Điều 173 và Điều 9 để nối suy luận. Cần tách câu hỏi thành nhiều truy vấn.
5. **Ba câu paraphrase vẫn trượt ở mọi cấu hình** (q16 tòa án theo lãnh thổ, q32 mượn ô tô gây tai nạn, q36 án
   phí khi bị bác đơn): gold không vào được top-5 dù có HyDE.

## Chọn ngưỡng context

Ngưỡng mặc định `CONTEXT_MIN_P=0.7` quá chặt. Jev thường chấm đoạn đúng ở mức 0.6-0.7 (q20 BLTTHS Đ173 = 0.68,
q34 BLHH Đ151 = 0.64, q37 BLLĐ Đ107 = 0.65). Quét ngưỡng trên điểm Jev đã cache, cấu hình + Jev (không HyDE),
không gọi LLM:

| min_p | Context có gold | Độ phủ gold trong context | Context rỗng | Số đoạn TB | Độ phủ gold (multi) |
|---|---|---|---|---|---|
| 0.3 | 0.825 | 0.758 | 5 | 2.45 | 0.292 |
| 0.5 | 0.825 | 0.758 | 6 | 1.77 | 0.292 |
| 0.6 | 0.825 | 0.758 | 6 | 1.57 | 0.292 |
| 0.7 | 0.775 | 0.713 | 7 | 1.35 | 0.188 |

Ở 0.7, q20 trả lời **sai** "tạm giam tối đa 20 ngày" (lấy từ Điều 459 BLTTHS, p=0.88, vì Điều 173 p=0.68 bị loại);
ở 0.6 câu này từ chối thay vì trả lời sai. Kết quả ở 0.7 lưu tại [`bench6-40q-jev/`](bench6-40q-jev/).

## Lưu ý

- Ngưỡng 0.6 được chọn trên chính bộ benchmark này (chưa có tập dev riêng), nên các cấu hình có Jev có thể
  lạc quan.
- Mẫu nhỏ: 1 câu = 0.025 điểm trên tổng, 0.0625 trong nhóm 16 câu, 0.125 trong nhóm multi.
- `gpt-6-luna` không nhận temperature=0. Đoạn HyDE và câu trả lời có cache nên chạy lại cho cùng kết quả, nhưng
  xoá cache thì kết quả có thể khác.
- HyDE chưa được đo trên câu ngoài phạm vi: đoạn giả "nghe hợp lý" có thể làm tăng trả lời nhầm. Bộ này chưa
  có câu out_of_scope.

## Chạy lại (tại gốc repo)

Đặt rõ `RERANK_BACKEND` ở mỗi lệnh, vì giá trị trong `.env` sẽ được dùng nếu không truyền.

```bash
Q=evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl
R=evals/team-4.2/runners/run_eval.py

# Hybrid (baseline)
RERANK_BACKEND=none ADVANCED= python $R --questions $Q --answers --out evals/team-4.2/results/bench6-40q-gpt6luna

# + Jev, ngưỡng 0.6 (cần TYPESAFE_API_KEY)
RERANK_BACKEND=jev ADVANCED= CONTEXT_MIN_P=0.6 python $R --questions $Q \
    --configs hybrid hybrid+rerank --answers --out evals/team-4.2/results/bench6-40q-jev-p06

# + HyDE
RERANK_BACKEND=none ADVANCED=hyde python $R --questions $Q \
    --configs hybrid hyde hybrid+hyde --answers --out evals/team-4.2/results/bench6-40q-hyde

# + HyDE + Jev, ngưỡng 0.6 (cấu hình "all" = mọi arm đang bật + rerank)
RERANK_BACKEND=jev ADVANCED=hyde CONTEXT_MIN_P=0.6 python $R --questions $Q \
    --configs hybrid hybrid+hyde hybrid+rerank all --answers --out evals/team-4.2/results/bench6-40q-hyde-jev-p06
```
