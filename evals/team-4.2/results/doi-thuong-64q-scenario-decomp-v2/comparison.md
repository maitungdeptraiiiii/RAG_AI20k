# Benchmark decomposition v2 — 64 câu

Chỉ chạy cấu hình mới. Các số đối chiếu lấy từ kết quả đã lưu; không chạy lại baseline.

| Chỉ số | Cấu hình trước: 20+10, Jev partial | Prompt decompose v2 | Chênh lệch |
|---|---:|---:|---:|
| Recall@5 | 0.880208 | 0.895833 | +0.015625 |
| Hit@5 | 0.968750 | 0.984375 | +0.015625 |
| MRR@5 | 0.848698 | 0.842188 | -0.006510 |
| Recall@20 | 0.937500 | 0.947917 | +0.010417 |
| Candidate recall (toàn bộ pool) | 0.937500 | 0.953125 | +0.015625 |
| Câu tìm đủ gold trong top 5 | 51/64 | 52/64 | +1 |
| Câu multi tìm đủ gold trong top 5 | 16/27 | 16/27 | 0 |
| Câu được phân tách | 14 | 50 | +36 |
| Tổng truy vấn, gồm câu gốc | 94 | 165 | +75.5% |
| Tổng cặp query–chunk đầu vào rerank | 1629 | 1774 | +8.9% |

## Thay đổi theo câu

- d09: Recall@5 0 → 1; MRR 0 → 0.25, tức gold ở hạng 4. Câu con giúp tìm thêm Điều 174 BLHS mà pool cũ chưa có.
- d22: Recall giữ 1; MRR 1 → 0.5, gold đầu tiên từ hạng 1 xuống 2.
- d31: Recall giữ 1; MRR 0.5 → 0.333333, gold đầu tiên từ hạng 2 xuống 3. Câu này hỏi lần đầu vi phạm, tội nhẹ, có con nhỏ, muốn tránh ngồi tù.
- 61 câu còn lại giữ nguyên Recall@5 và MRR@5. Chỉ một câu tăng Recall@5, không câu nào giảm.
- Nhóm multi: Recall@5 giữ 0.790123; MRR giảm 0.808025 → 0.789506. Chưa khắc phục được việc thiếu toàn bộ bằng chứng cho 11/27 câu multi.

## Kiểm chứng và giới hạn

64/64 câu rerank thành công, không lỗi/fallback; toàn bộ ứng viên gốc giữ nguyên thứ tự, thêm tối đa 10 Điều mới, pool không quá 30 Điều. Mọi thứ hạng và metric đã được tính lại offline từ cache Jev full-input-v2. Dataset, index snapshot, HyDE, Jev prompt/model và giới hạn retrieval khớp cấu hình trước; chỉ prompt decompose thay đổi. Kế hoạch phân tách của benchmark khớp đủ 64 bản preflight đã cache.

Tổng truy vấn/cặp rerank phản ánh khối lượng xử lý, không phải số API trả phí thực tế: cache được tái sử dụng và thời gian có ảnh hưởng cache. Không đánh giá câu trả lời cuối hay chất lượng context. Đây là kết quả trên bộ 64 câu đã dùng để phát triển, chưa phải bằng chứng cải thiện trên tập độc lập.

Prompt mới tăng độ phủ nhưng giảm MRR, chưa tạo cải thiện cho nhóm multi. Không thể kết luận tốt hơn trên mọi tiêu chí. Chưa đổi .env để bật cấu hình mới trong ứng dụng.

Chi tiết máy đọc được: verification.json, query_traces.json và rank_and_context_analysis.json. Có thể tái kiểm tra offline bằng analyze_saved_run.py; script cấm kết nối mạng.
