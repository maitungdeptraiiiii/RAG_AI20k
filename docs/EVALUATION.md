# Evaluation guidelines

Mỗi team lưu dataset/config/kết quả riêng trong `evals/team-4.1/` hoặc `evals/team-4.2/`. Các yêu cầu số lượng câu hỏi áp dụng **cho từng team**, không cộng gộp. Chỉ so sánh điểm giữa hai team khi dataset, snapshot, rubric và điều kiện chạy tương đương; nếu khác lĩnh vực, đánh giá tiến bộ của từng team so với baseline của chính team đó.

## Dataset and labels

Mỗi câu hỏi cần: `id`, câu hỏi, nhóm tác vụ, snapshot dữ liệu, đáp án/rubric, vị trí bằng chứng nguồn, hành vi mong đợi (`answer`, `clarify`, `abstain`), split (`dev`, `test`), người gán nhãn và reviewer.

Gán nhãn theo đoạn/vị trí nguồn ổn định rồi ánh xạ sang chunk của mỗi cấu hình. Không để thay đổi chunk size làm mất khả năng so sánh ground truth. Lưu liên kết nguồn và phiên bản; câu hỏi mẫu trong repo không phải kết quả đánh giá thật.

Tuần 1: ≥10 câu/bộ tài liệu. Tuần 3: ≥40 câu tổng. Tuần 4: ≥50 câu tổng, dành một phần chưa dùng để tuning làm test (gợi ý ít nhất 10 câu). Chốt split trước tuning; giữ rubric/đáp án test ngoài luồng phát triển hoặc nhờ mentor quản lý nếu cần đánh giá độc lập.

## Retrieval

Với câu hỏi q, Rq là tập đơn vị bằng chứng liên quan và Tq là tối đa 5 kết quả đầu:

- `Recall@5(q) = |Rq ∩ Tq| / |Rq|`.
- `RR@5(q) = 1/r` nếu bằng chứng liên quan đầu tiên ở vị trí r ≤ 5; ngược lại là 0.
- `MRR@5 = trung bình RR@5(q)`; báo cáo Recall@5 trung bình và số câu được tính.

Thống nhất đơn vị bằng chứng và cách ánh xạ kết quả trước khi chạy; không trộn chunk-level và document-level metrics. Loại kết quả trùng theo chính sách cố định. Khi có hơn 5 đơn vị liên quan, Recall@5 không thể đạt 1.

Câu không có bằng chứng trong corpus được đánh giá khả năng báo thiếu dữ liệu riêng, không chia cho mẫu số 0. Với câu nhiều bước, đo thêm đủ toàn bộ bằng chứng. SQL/graph cần metric phù hợp như đúng phép tính hoặc đủ quan hệ, không ép mọi đầu ra thành chunk.

## Generation and behavior

Chấm riêng độ đúng/đủ, mức độ được nguồn hỗ trợ, citation đúng vị trí và thực sự hỗ trợ phát biểu. Báo cáo tỷ lệ hỏi lại hoặc báo thiếu dữ liệu đúng theo nhóm tương ứng. Nếu dùng LLM judge, ghi model/prompt/version và đối chiếu thủ công một phần; không coi judge là ground truth.

## Experiment design

- Giữ cố định câu hỏi, snapshot, generation và điều kiện chạy khi so sánh retrieval.
- So sánh BM25, Dense, Hybrid RRF, Hybrid + phương pháp mới.
- Thay từng yếu tố trong ablation; ghi config, commit, model và thời điểm.
- Báo cáo theo nhóm câu hỏi, số mẫu, latency và chi phí; không chỉ điểm trung bình.
- Agent so với baseline: task success, citation, tool selection, số bước, giới hạn và chi phí.
- Không đặt ngưỡng chất lượng tùy tiện sau khi xem kết quả. Chốt ngưỡng và cách xử lý regression trước khi phát hành tuần 5.

## Failure analysis

Mỗi case ghi: câu hỏi → kỳ vọng → thực tế → bằng chứng → bước gây lỗi → giả thuyết nguyên nhân → cách sửa → kết quả chạy lại. Phân loại: dữ liệu thiếu/sai, parsing, chunking, retrieval, routing/tool, generation hoặc nhãn đánh giá.

Không cam kết “không hallucinate”; báo cáo kết quả quan sát, kích thước mẫu và giới hạn.
