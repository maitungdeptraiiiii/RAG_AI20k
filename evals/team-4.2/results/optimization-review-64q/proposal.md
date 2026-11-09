# Đề xuất tối ưu sau benchmark rewrite/BM25

Phân tích offline, không chạy benchmark hoặc API model mới. Cấu hình tham chiếu là v2: Dense+HyDE, decompose, giữ 20 Điều câu gốc + tối đa 10 Điều mới, Jev chấm câu gốc.

## Bằng chứng từ kết quả

- 95 GoldRef đếm theo từng câu: 81 nằm trong top 5, 8 có trong pool nhưng dưới top 5, 6 không có trong pool. Đây là đếm GoldRef, khác Recall@5 macro 0.895833.
- Multi: 23/27 câu đã có đủ gold trong pool, nhưng chỉ 16/27 có đủ trong top 5. Bảy câu có thể được sửa ở bước chọn/xếp hạng mà không cần thêm retrieval; bốn câu multi còn thiếu ứng viên.
- Nếu chọn hoàn hảo trên chính pool này, Recall@5 macro tối đa là 0.953125, và số câu multi đủ gold tối đa 23/27. Đây là trần dùng gold để chẩn đoán, không phải kết quả dự báo hoặc đạt được.
- Tám gold dưới top 5 thuộc d04 (2), d10, d17, d26, d52, d59, d62. Phần lớn ở hạng 6–9; riêng Điều 39 ở d04 là hạng 21.
- Cả tám đã có đủ chunk của Điều tương ứng trong pool. Lấy thêm các chunk còn lại của cùng Điều không bổ sung nội dung cho chúng, dù thay cách chấm toàn Điều vẫn có thể làm điểm thay đổi.
- Đã tái lập chính xác pool v2 của 64/64 câu từ các danh sách Dense lưu trong lượt hybrid. Trong 8 gold bị xếp thấp, 5 từng ở hạng Điều <=5 của một câu con: d04/Điều 41 hạng 1; d10/Điều 650 hạng 3; d52/Điều 143 hạng 3; d59/Điều 326 hạng 5; d62/Điều 213 hạng 5.

## Ưu tiên 1: Chọn top 5 theo độ liên quan và độ phủ nhu cầu

Giữ nguyên pool và điểm Jev của v2. Dùng thêm nguồn gốc nhánh và thứ hạng câu con đã lưu để tránh bỏ bằng chứng tốt của một nhu cầu phụ. Bắt đầu bằng mô phỏng offline, không gọi lại LLM, embedding hay Jev.

Một phương án ban đầu: bảo vệ các vị trí đầu có độ liên quan cao, các vị trí còn lại ưu tiên Điều có điểm Jev đủ tốt và bổ sung nhu cầu chưa được đại diện. Không bắt buộc mỗi câu con phải có một Điều: câu con có thể sai hoặc trùng ý, và thứ hạng retrieval chỉ là tín hiệu thay thế, không chứng minh đoạn văn trả lời được câu con.

Ví dụ d04: Điều 41 ở hạng 6 toàn cục, nhưng hạng 1 của câu con hỏi quyền/nghĩa vụ sau chấm dứt hợp đồng. Thay vì chỉ cộng thêm các Điều cùng chủ đề vào top 5, cần cân nhắc bằng chứng cho nhu cầu đó.

Cần kiểm tra cả Recall@5, MRR@5, full-gold multi và các câu bị giảm; không chỉ đếm số câu tăng. Không dùng gold để chỉ định slot, Điều cần đưa lên hoặc quyết định routing. Tham số phải được cố định trước khi chấm tập độc lập.

## Ưu tiên 2: Nếu tín hiệu rank chưa đủ, dùng listwise selection có giới hạn

Jev hiện chấm từng chunk riêng. Một mô hình so sánh chung các Điều có thể chọn một bộ bằng chứng ít trùng vai trò hơn, thay vì chỉ chọn 5 điểm cao nhất.

Đề xuất riêng: với câu nhiều nhu cầu và thứ hạng chưa rõ, đưa câu gốc, các nhu cầu/câu con, và 8–12 ứng viên vào một lần gọi để chọn 5 ID. Nội dung gồm heading và đoạn đại diện đủ điều kiện áp dụng; chỉ được trả ID có sẵn, không sinh Điều mới. Lỗi định dạng hoặc ID lạ thì giữ kết quả Jev. Không dùng rewrite để thay câu gốc. Đây là một lần gọi bổ sung cho câu được chọn, vẫn có chi phí token cần đo, không mặc nhiên rẻ hơn Jev.

Giữ pool v2 khi thử để đo riêng tác động xếp hạng. Việc chọn top 8–12 không thể cứu gold nằm ngoài shortlist như d04/Điều 39, nên cần công bố giới hạn đó.

Nghiên cứu liên quan: RankGPT nghiên cứu LLM cho reranking https://aclanthology.org/2023.emnlp-main.923/ . Stage-Aware Decomposition cho thấy decomposition có tác dụng khác nhau ở retrieval/reranking https://aclanthology.org/2026.findings-emnlp.1644/ . Các bộ dữ liệu đó khác bài toán pháp luật Việt Nam và không chứng minh mức cải thiện cho dự án này.

## Ưu tiên 3: Sửa retrieval cho các gold còn ngoài pool

Không fusion BM25 theo cách thay thế ứng viên v2 trước Jev. Một ablation phù hợp hơn là giữ nguyên toàn bộ pool v2, chỉ thêm tối đa vài Điều BM25 thật sự mới, có giới hạn riêng; đánh giá candidate recall trước khi trả tiền Jev. Bảo vệ pool chỉ bảo đảm giữ ứng viên, không bảo đảm giữ thứ hạng top 5 sau rerank.

BM25 có thể được thử với ngữ cảnh cấu trúc: tên tài liệu, chương/mục, tiêu đề Điều và nội dung. Chunk.index_text hiện chỉ là context nếu có + text; section không tự động được ghép vào. Phiên bản dùng metadata có thể dựng offline, không cần LLM; không đồng nhất với cách dùng LLM sinh context của Anthropic. Tham khảo nguyên lý Contextual Retrieval: https://www.anthropic.com/research/contextual-retrieval . Chưa nên trả chi phí re-embed toàn corpus trước khi thấy độ phủ tốt hơn.

Một hướng rẻ khác cần audit trước là liên kết trích dẫn Điều luật (xref): xem 1 hop từ các Điều tốt có chạm đến gold còn thiếu hay không. Chỉ khi có bằng chứng tiếp cận được ứng viên mới nên thêm nhánh này; phải phân biệt tham chiếu cùng văn bản và văn bản khác. Chưa có đo đạc xref trong phân tích này.

## Những việc chưa ưu tiên

- Thử tiếp nhiều trọng số BM25 mà chưa bảo vệ pool.
- Rewrite toàn bộ rồi thay câu gốc cho reranker: đã có cả tăng và giảm, chưa giải quyết tính đầy đủ bằng chứng.
- Tăng top-k từ 5 để báo điểm cao hơn: làm thay đổi bài đánh giá; context và top-5 benchmark đang là hai khái niệm riêng.
- Nới quota 10 Điều mới như một lời giải mặc định. Audit trước đây của prompt v1 không thấy gold bị mất tại quota cuối; không được suy rộng kết luận đó sang v2 nếu chưa audit v2 đầy đủ.
- GraphRAG toàn corpus, sinh nhiều HyDE hoặc re-index bằng embedding khác trước khi xử lý 8 gold đã có trong pool.

## Kiểm soát chất lượng đánh giá

Giữ bộ 64 câu để so sánh lịch sử, nhưng cần thêm tập kiểm tra độc lập và thước đo tìm đủ gold cho multi. Rà soát các nhãn chứa giả định chưa được câu hỏi xác nhận: ví dụ d02 chưa nói người bị đẩy đã chết, nhưng gold có Điều 128. Cần mô tả rõ đây là bằng chứng cho nhánh điều kiện nào, không ép prompt khẳng định hậu quả để khớp gold và không đổi nhãn chỉ để điểm tăng.

Chỉ dùng gold sau retrieval để chẩn đoán/chấm điểm. Không cho gold vào planner, selector, prompt hoặc routing.
