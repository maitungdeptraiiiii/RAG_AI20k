# Phân tích — rerank Jev + context theo ngưỡng (40 câu, gpt-6-luna)

Hai lượt: `bench6-40q-jev/` (CONTEXT_MIN_P=0.7, mặc định) và `bench6-40q-jev-p06/` (CONTEXT_MIN_P=0.6).
Retrieval chấm trên top-5 cố định; context cho LLM = các đoạn có xác suất Jev p ≥ min_p (tối đa 8 đoạn, 2400 từ).

## Retrieval (top-5)

| config | lookup R@5 | paraphrase R@5 | multi R@5 | tổng R@5 | tổng MRR@5 |
|---|---|---|---|---|---|
| hybrid | 1.000 | 0.375 | 0.417 | 0.633 | 0.658 |
| hybrid+rerank | 1.000 | **0.750** | 0.375 | **0.775** | **0.838** |

Rerank đưa gold từ hạng 6-20 lên top-5 cho paraphrase. Không cứu được câu mà gold nằm ngoài top-20
(Recall@20 = 0.783 là trần của rerank với RERANK_N=20).

## Context theo ngưỡng (quét min_p trên điểm Jev đã cache)

| min_p | context có gold | độ phủ gold trong context | context rỗng | số đoạn TB | độ phủ gold (multi) |
|---|---|---|---|---|---|
| 0.3 | 0.825 | 0.758 | 5 | 2.45 | 0.292 |
| 0.5 | 0.825 | 0.758 | 6 | 1.77 | 0.292 |
| 0.6 | 0.825 | 0.758 | 6 | 1.57 | 0.292 |
| 0.7 | 0.775 | 0.713 | 7 | 1.35 | 0.188 |

Jev thường chấm đoạn đúng ở mức 0.6-0.7 (q20 BLTTHS Đ173 = 0.68, q34 BLHH Đ151 = 0.64, q37 BLLĐ Đ107 = 0.65),
nên 0.7 cắt mất gold. 0.6 giữ độ phủ như 0.3 với context gọn hơn.

## Câu trả lời

| | không rerank (top-5) | jev, min_p 0.7 | jev, min_p 0.6 |
|---|---|---|---|
| từ chối (trong phạm vi) | 11/40 | 8/40 | 8/40 |
| context có gold | 0.700 | 0.775 | 0.825 |
| số đoạn context TB | 5.0 | 1.35 | 1.58 |

- min_p 0.7 → q20 trả lời **sai** "20 ngày" dựa trên Điều 459 BLTTHS (thủ tục rút gọn, p=0.88) vì Điều 173 (p=0.68) bị loại.
  min_p 0.6 → q20 từ chối thay vì trả lời sai.
- min_p 0.6 cứu thêm q34 (miễn trách nhiệm khi gặp bão) và q37 (đủ cả giới hạn 40 giờ/tháng và mức 200%).
- Với min_p 0.6, 8 câu từ chối: 6 câu không có đoạn nào qua ngưỡng nên không gọi LLM (q18, q19, q31, q32, q36, q38:
  gold ngoài top-20 hoặc Jev chấm thấp, vd. q38 Điều 174 chỉ 0.13); 2 câu LLM từ chối vì context thiếu Điều để nối
  suy luận (q20, q39).

## Lưu ý

- min_p 0.6 được chọn trên chính bộ benchmark này (không có tập dev riêng) → có thể lạc quan; nên kiểm lại khi có thêm câu.
- Multi vẫn yếu (độ phủ gold 0.29): rerank chấm từng đoạn với cả câu hỏi, Điều nền tảng (Điều 9 BLHS, Điều 4 BLDS)
  không "liên quan trực tiếp" nên bị chấm thấp. Cần tách truy vấn (query decomposition).
